from __future__ import annotations

import re

from semantic_layer.grounding.models import (
    GroundedContext,
    GroundedEntity,
    GroundedJoin,
    GroundedMetric,
    GroundingStatus,
)
from semantic_layer.intent.models.ast import QueryNode, Rank
from semantic_layer.intent.models.result import IntentResult
from semantic_layer.ir.models import (
    IrColumnRef,
    IrFrom,
    IrJoin,
    IrOrder,
    IrPredicate,
    IrPredicateSource,
    IrSelectItem,
    IrSelectKind,
    IrStatus,
    QueryIR,
    QueryIRResult,
)
from semantic_layer.ir.sqlglot_renderer import render_sql_safe

# Stable short aliases for known Finance/Logistics tables
_TABLE_ALIASES: dict[str, str] = {
    "public_payment_details": "pd",
    "public_academic_bag": "ab",
    "public_academic_bag_items": "abi",
    "public_learner_enrollment": "le",
    "public_grades_master": "gm",
    "public_curriculum_master": "cm",
    "public_session_master": "sm",
    "public_learners": "lr",
    "public_logistics_orders": "lo",
    "public_logistics_order_items": "loi",
    "public_logistics_shipments": "ls",
    "public_master_list_value": "mlv",
}

_EQ_ON = re.compile(
    r"^\s*([a-zA-Z_][\w]*)\.([a-zA-Z_][\w]*)\s*=\s*([a-zA-Z_][\w]*)\.([a-zA-Z_][\w]*)\s*$"
)


def _metric_sql(metric: GroundedMetric) -> str:
    """Apply kb_k21 ``agg`` when the expression is not already wrapped."""
    sql = (metric.sql_expression or "").strip()
    agg = (metric.aggregation_type or "").strip().lower()
    if agg not in {"sum", "avg", "min", "max", "count"} or not sql:
        return sql
    if sql.upper().startswith(f"{agg.upper()}("):
        return sql
    return f"{agg.upper()}({sql})"


def _alias_for(table: str, used: set[str]) -> str:
    base = _TABLE_ALIASES.get(table) or "".join(
        p[0] for p in table.replace("public_", "").split("_") if p
    )[:3] or "t"
    alias = base
    n = 2
    while alias in used:
        alias = f"{base}{n}"
        n += 1
    used.add(alias)
    return alias


def _parse_on(on: str) -> dict[str, str | None]:
    m = _EQ_ON.match(on or "")
    if not m:
        return {
            "left_table": None,
            "left_column": None,
            "operator": None,
            "right_table": None,
            "right_column": None,
        }
    return {
        "left_table": m.group(1),
        "left_column": m.group(2),
        "operator": "=",
        "right_table": m.group(3),
        "right_column": m.group(4),
    }


def _entity_map(grounded: GroundedContext) -> dict[str, GroundedEntity]:
    return {e.concept: e for e in grounded.entities}


def _walk_rank(ast: QueryNode) -> Rank | None:
    for op in ast.operations or []:
        if isinstance(op, Rank) or getattr(op, "type", None) == "RANK" or (
            hasattr(op, "model_dump") and op.model_dump(by_alias=True).get("type") == "RANK"
        ):
            return op  # type: ignore[return-value]
    return None


def _concept_of(ref) -> str | None:
    if ref is None:
        return None
    if hasattr(ref, "concept"):
        return str(ref.concept)
    if isinstance(ref, dict):
        return ref.get("concept")
    return None


def _required_concepts(ast: QueryNode) -> set[str]:
    concepts: set[str] = set()
    dump = ast.model_dump(mode="json", by_alias=True)

    def walk(node):
        if isinstance(node, dict):
            t = node.get("type")
            if t in {"ENTITY_REF", "DIMENSION_REF", "METRIC_REF"} and node.get("concept"):
                concepts.add(str(node["concept"]))
            if t == "METRIC_EXPRESSION" and node.get("metric"):
                concepts.add(str(node["metric"]))
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for i in node:
                walk(i)

    walk(dump)
    return concepts


def compile_query_ir(
    intent_result: IntentResult,
    grounded: GroundedContext | None,
    *,
    with_sql_preview: bool = True,
) -> QueryIRResult:
    """Mechanically compile Intent + GroundedContext → QueryIR (no path rediscovery)."""
    errors: list[str] = []

    if intent_result.intent_ast is None:
        return QueryIRResult(
            status=IrStatus.FAILED,
            errors=["intent_ast is null; cannot compile IR"],
        )
    if grounded is None:
        return QueryIRResult(
            status=IrStatus.FAILED,
            errors=["grounded context is null; cannot compile IR"],
        )
    if grounded.status == GroundingStatus.FAILED:
        return QueryIRResult(
            status=IrStatus.FAILED,
            errors=["grounding FAILED; cannot compile IR"] + list(grounded.errors),
        )

    ast = intent_result.intent_ast
    if not isinstance(ast, QueryNode):
        # Accept duck-typed validated AST
        pass

    required = _required_concepts(ast)  # type: ignore[arg-type]
    resolved = {e.concept for e in grounded.entities} | {
        m.concept for m in grounded.metrics
    }
    missing = sorted(required - resolved)
    # TIME concepts are not entities/metrics
    missing = [c for c in missing if c not in {"THIS_YEAR", "LAST_YEAR", "THIS_MONTH", "LAST_MONTH"}]
    if missing:
        return QueryIRResult(
            status=IrStatus.FAILED,
            errors=[f"unresolved required concepts for IR: {', '.join(missing)}"],
        )

    entities = _entity_map(grounded)
    if not grounded.base_entity:
        return QueryIRResult(
            status=IrStatus.FAILED,
            errors=["grounded.base_entity is missing; Grounding must set the FROM entity"],
        )
    base = entities.get(grounded.base_entity)
    if base is None:
        return QueryIRResult(
            status=IrStatus.FAILED,
            errors=[f"base_entity '{grounded.base_entity}' not in grounded.entities"],
        )

    used_aliases: set[str] = set()
    base_alias = _alias_for(base.source_table, used_aliases)
    ir_from = IrFrom(entity=base.concept, table=base.source_table, alias=base_alias)

    # Map entity → alias as we emit joins (for tracing; ON stays table-qualified opaque)
    entity_alias = {base.concept: base_alias}
    ir_joins: list[IrJoin] = []
    for gj in grounded.joins:
        # Prefer the "to" side as the newly joined entity when possible
        join_entity = _pick_join_entity(gj, entity_alias, entities)
        if join_entity is None:
            errors.append(f"could not map join edge {gj.from_entity}->{gj.to_entity}")
            continue
        ge = entities[join_entity]
        alias = _alias_for(ge.source_table, used_aliases)
        entity_alias[join_entity] = alias
        parsed = _parse_on(gj.on)
        ir_joins.append(
            IrJoin(
                join_type=gj.join_type or "inner",
                entity=join_entity,
                table=ge.source_table,
                alias=alias,
                on=gj.on,
                left_table=parsed["left_table"],
                left_column=parsed["left_column"],
                operator=parsed["operator"],
                right_table=parsed["right_table"],
                right_column=parsed["right_column"],
            )
        )

    metrics_by = {m.concept: m for m in grounded.metrics}
    select: list[IrSelectItem] = []
    group_by: list[IrColumnRef] = []
    order_by: list[IrOrder] = []
    limit: int | None = getattr(ast, "limit", None)

    rank = _walk_rank(ast)  # type: ignore[arg-type]
    dim_concept = _concept_of(getattr(rank, "dimension", None)) if rank else None
    metric_concept = _concept_of(getattr(rank, "metric", None)) if rank else None

    # Select / group from AST select + group_by, preferring RANK refs
    dim_concepts: list[str] = []
    if dim_concept:
        dim_concepts.append(dim_concept)
    for ref in getattr(ast, "group_by", None) or []:
        c = _concept_of(ref)
        if c and c not in dim_concepts:
            dim_concepts.append(c)
    for ref in getattr(ast, "select", None) or []:
        dump = ref.model_dump(by_alias=True) if hasattr(ref, "model_dump") else ref
        if isinstance(dump, dict) and dump.get("type") == "DIMENSION_REF":
            c = dump.get("concept")
            if c and c not in dim_concepts:
                dim_concepts.append(str(c))

    for c in dim_concepts:
        ent = entities.get(c)
        if ent is None:
            errors.append(f"dimension entity '{c}' not grounded")
            continue
        col = ent.display_column or ent.primary_key or "id"
        alias = c.lower()
        select.append(
            IrSelectItem(
                kind=IrSelectKind.COLUMN,
                alias=alias,
                table=ent.source_table,
                column=col,
            )
        )
        group_by.append(IrColumnRef(table=ent.source_table, column=col, alias=alias))

    metric_concepts: list[str] = []
    if metric_concept:
        metric_concepts.append(metric_concept)
    for ref in getattr(ast, "select", None) or []:
        dump = ref.model_dump(by_alias=True) if hasattr(ref, "model_dump") else ref
        if isinstance(dump, dict) and dump.get("type") == "METRIC_REF":
            c = dump.get("concept")
            if c and str(c) not in metric_concepts:
                metric_concepts.append(str(c))

    for c in metric_concepts:
        gm = metrics_by.get(c)
        if gm is None:
            errors.append(f"metric '{c}' not grounded")
            continue
        select.append(
            IrSelectItem(
                kind=IrSelectKind.EXPRESSION,
                alias=c,
                sql=_metric_sql(gm),
            )
        )

    if rank is not None:
        direction = getattr(rank, "direction", None)
        direction_s = (
            direction.value if hasattr(direction, "value") else str(direction or "DESC")
        )
        if metric_concept:
            order_by.append(IrOrder(expr_alias=metric_concept, direction=direction_s))
        rlimit = getattr(rank, "limit", None)
        if rlimit is not None:
            limit = int(rlimit)

    where: list[IrPredicate] = []
    for filt in grounded.default_filters:
        where.append(
            IrPredicate(sql=filt, source=IrPredicateSource.DEFAULT_FILTER)
        )

    for tf in grounded.time_filters:
        col = (tf.suggested_columns or [None])[0]
        if not col:
            errors.append(f"time filter {tf.range} has no suggested column")
            continue
        if str(tf.range) == "THIS_YEAR":
            where.append(
                IrPredicate(
                    sql=(
                        f"{col} >= date_trunc('year', CURRENT_DATE) AND "
                        f"{col} < date_trunc('year', CURRENT_DATE) + interval '1 year'"
                    ),
                    source=IrPredicateSource.TIME_FILTER,
                    range=str(tf.range),
                )
            )
        else:
            errors.append(f"unsupported time range for IR V1: {tf.range}")

    if errors and not select:
        return QueryIRResult(status=IrStatus.FAILED, errors=errors)

    if not select:
        return QueryIRResult(
            status=IrStatus.FAILED,
            errors=errors + ["IR select list is empty"],
        )

    ir = QueryIR(
        bo_id=grounded.bo_id,
        from_=ir_from,
        joins=ir_joins,
        select=select,
        where=where,
        group_by=group_by,
        order_by=order_by,
        limit=limit,
    )

    sql = None
    if with_sql_preview:
        sql, render_warnings = render_sql_safe(ir, dialect="postgres")
        errors.extend(render_warnings)
    return QueryIRResult(
        status=IrStatus.VALID,
        ir=ir,
        sql_preview=sql,
        errors=errors,
    )


def _pick_join_entity(
    gj: GroundedJoin,
    already: dict[str, str],
    entities: dict[str, GroundedEntity],
) -> str | None:
    """Choose which side of the edge is the newly joined entity."""
    if gj.to_entity not in already and gj.to_entity in entities:
        return gj.to_entity
    if gj.from_entity not in already and gj.from_entity in entities:
        return gj.from_entity
    # Both already present (or missing) — prefer to_entity if grounded
    if gj.to_entity in entities:
        return gj.to_entity
    if gj.from_entity in entities:
        return gj.from_entity
    return None
