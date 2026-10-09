from __future__ import annotations

import sqlglot
from sqlglot import exp

from semantic_layer.ir.models import IrSelectKind, QueryIR
from semantic_layer.ir.sql_preview import to_sql_postgres


def _parse_fragment(sql: str, dialect: str) -> exp.Expression:
    """Parse an opaque SQL fragment produced by Grounding / IR time compile."""
    return sqlglot.parse_one(sql, read=dialect)


def _table(name: str, alias: str) -> exp.Table:
    return exp.Table(
        this=exp.to_identifier(name, quoted=False),
        alias=exp.TableAlias(this=exp.to_identifier(alias)),
    )


def _table_alias_map(ir: QueryIR) -> dict[str, str]:
    mapping = {ir.from_.table: ir.from_.alias}
    for j in ir.joins:
        mapping[j.table] = j.alias
    return mapping


def _rewrite_tables_to_aliases(sql: str, table_to_alias: dict[str, str]) -> str:
    """Rewrite public_foo.col → alias.col so Postgres accepts aliased FROM/JOIN."""
    out = sql
    for table, alias in sorted(table_to_alias.items(), key=lambda kv: -len(kv[0])):
        out = out.replace(f"{table}.", f"{alias}.")
    return out


def _join_on(ir_join, dialect: str, table_to_alias: dict[str, str]) -> exp.Expression:
    if (
        ir_join.left_table
        and ir_join.left_column
        and ir_join.right_table
        and ir_join.right_column
        and (ir_join.operator or "=") == "="
    ):
        left_t = table_to_alias.get(ir_join.left_table, ir_join.left_table)
        right_t = table_to_alias.get(ir_join.right_table, ir_join.right_table)
        return exp.EQ(
            this=exp.column(ir_join.left_column, table=left_t),
            expression=exp.column(ir_join.right_column, table=right_t),
        )
    rewritten = _rewrite_tables_to_aliases(ir_join.on, table_to_alias)
    return _parse_fragment(rewritten, dialect)


def render_sql(ir: QueryIR, *, dialect: str = "postgres") -> str:
    """Render QueryIR to dialect SQL via SQLGlot.

    Opaque fragments (join ON, metric expressions, predicates) are parsed with
    SQLGlot — not invented. Falls back to the thin string preview on failure.
    """
    try:
        return _render_sqlglot(ir, dialect=dialect)
    except Exception:
        # Keep UI/pipeline usable if a fragment is not SQLGlot-parseable
        return to_sql_postgres(ir)


def _render_sqlglot(ir: QueryIR, *, dialect: str) -> str:
    aliases = _table_alias_map(ir)

    select_exprs: list[exp.Expression] = []
    for item in ir.select:
        if item.kind == IrSelectKind.COLUMN:
            assert item.table and item.column
            table = aliases.get(item.table, item.table)
            col = exp.column(item.column, table=table)
            select_exprs.append(exp.alias_(col, item.alias, quoted=False))
        else:
            assert item.sql
            # Metric SQL often already uses short aliases (pd, ab) from KB
            expr = _parse_fragment(item.sql, dialect)
            select_exprs.append(exp.alias_(expr, item.alias, quoted=False))

    from_tbl = _table(ir.from_.table, ir.from_.alias)
    query: exp.Select = exp.select(*select_exprs).from_(from_tbl)

    for j in ir.joins:
        jt = (j.join_type or "inner").lower()
        side = jt.replace(" join", "").strip()
        join_kw = side if side in {"inner", "left", "right", "full", "cross"} else "inner"
        on_expr = _join_on(j, dialect, aliases)
        query = query.join(
            _table(j.table, j.alias),
            on=on_expr,
            join_type=join_kw,
        )

    if ir.where:
        pred: exp.Expression | None = None
        for w in ir.where:
            piece = _parse_fragment(
                _rewrite_tables_to_aliases(w.sql, aliases), dialect
            )
            pred = piece if pred is None else exp.and_(pred, piece)
        if pred is not None:
            query = query.where(pred)

    if ir.group_by:
        groups = [
            exp.column(g.column, table=aliases.get(g.table, g.table))
            for g in ir.group_by
        ]
        query = query.group_by(*groups)

    if ir.order_by:
        orders: list[exp.Ordered] = []
        for o in ir.order_by:
            ident = exp.column(o.expr_alias)
            desc = str(o.direction).upper() == "DESC"
            orders.append(exp.Ordered(this=ident, desc=desc))
        query = query.order_by(*orders)

    if ir.limit is not None:
        query = query.limit(int(ir.limit))

    return query.sql(dialect=dialect, pretty=True) + ";"


def render_sql_safe(ir: QueryIR, *, dialect: str = "postgres") -> tuple[str, list[str]]:
    """Like render_sql but returns (sql, warnings) when falling back."""
    try:
        return _render_sqlglot(ir, dialect=dialect), []
    except Exception as exc:  # noqa: BLE001
        return to_sql_postgres(ir), [f"sqlglot render failed; used thin preview: {exc}"]
