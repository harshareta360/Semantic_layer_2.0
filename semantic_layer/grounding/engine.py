from __future__ import annotations

import json
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from semantic_layer.grounding.business_objects import (
    BusinessObject,
    BusinessObjectRegistry,
    load_business_objects,
)
from semantic_layer.grounding.contracts import (
    GroundingContracts,
    MetricContract,
    PreferredJoinPath,
    load_grounding_contracts,
)
from semantic_layer.grounding.models import (
    GroundedContext,
    GroundedDimension,
    GroundedEntity,
    GroundedJoin,
    GroundedMetric,
    GroundedTimeFilter,
    GroundingStatus,
)
from semantic_layer.intent.models.result import IntentResult
from semantic_layer.normalization.models import NormalizedQuestion

_DEFAULT_KB_PATH = Path(__file__).resolve().parents[2] / "kb.json"


class KbIndex:
    """Indexed view of kb.json for deterministic grounding lookups."""

    def __init__(self, kb_doc: dict[str, Any]) -> None:
        kb = kb_doc.get("kb", kb_doc)
        self.raw = kb
        self.entities: dict[str, dict[str, Any]] = {}
        self.metrics: dict[str, dict[str, Any]] = {}
        self.measures: dict[str, dict[str, Any]] = {}
        self.dimensions: dict[str, dict[str, Any]] = {}
        self.relationships: list[dict[str, Any]] = list(
            (kb.get("semantic") or {}).get("relationships") or []
        )
        self.rules: list[str] = [str(r) for r in (kb.get("rules") or [])]
        self.join_paths: list[str] = [str(j) for j in (kb.get("join_paths") or [])]
        self.column_hints: dict[str, Any] = dict(kb.get("column_hints") or {})

        for ent in (kb.get("semantic") or {}).get("entities") or []:
            name = ent.get("entity") or ent.get("name")
            if name:
                self.entities[str(name)] = ent

        for metric in kb.get("metrics") or []:
            name = metric.get("name")
            if name:
                self.metrics[str(name)] = metric

        for meas in (kb.get("semantic") or {}).get("measures") or []:
            name = meas.get("name")
            if name:
                self.measures[str(name)] = meas

        for dim in (kb.get("semantic") or {}).get("dimensions") or []:
            name = dim.get("name")
            if name:
                self.dimensions[str(name)] = dim

        # Undirected adjacency for join BFS: entity → list[(neighbor, rel)]
        self._adjacency: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
        for rel in self.relationships:
            a = rel.get("from_entity")
            b = rel.get("to_entity")
            if not a or not b:
                continue
            self._adjacency[str(a)].append((str(b), rel))
            rev = {
                **rel,
                "from_entity": b,
                "to_entity": a,
                "on": rel.get("on"),
                "_reversed": True,
            }
            self._adjacency[str(b)].append((str(a), rev))

    @classmethod
    def from_path(cls, path: Path | str | None = None) -> KbIndex:
        p = Path(path) if path else _DEFAULT_KB_PATH
        doc = json.loads(p.read_text(encoding="utf-8"))
        return cls(doc)

    def find_relationship(
        self, entity_a: str, entity_b: str
    ) -> dict[str, Any] | None:
        """Return the original relationship dict between two entities, if any."""
        for neighbor, rel in self._adjacency.get(entity_a, []):
            if neighbor == entity_b:
                # Prefer non-reversed original orientation when available
                if not rel.get("_reversed"):
                    return rel
        for neighbor, rel in self._adjacency.get(entity_a, []):
            if neighbor == entity_b:
                return {
                    "from_entity": rel.get("to_entity"),
                    "to_entity": rel.get("from_entity"),
                    "on": rel.get("on"),
                    "join_type": rel.get("join_type"),
                    "cardinality": rel.get("cardinality"),
                    "name": rel.get("name"),
                }
        return None

    @staticmethod
    def _dep_table(dep: str) -> str:
        return dep.split(".", 1)[0] if dep else ""

    def metric_tables(self, metric: dict[str, Any]) -> set[str]:
        return {
            self._dep_table(str(d))
            for d in (metric.get("dependencies") or [])
            if d
        }

    def scoped_to(self, allowed_tables: set[str]) -> KbIndex:
        """Return a KB view limited to the given physical tables."""
        idx = KbIndex.__new__(KbIndex)
        idx.raw = self.raw
        idx.entities = {
            name: ent
            for name, ent in self.entities.items()
            if str(ent.get("source_table") or "") in allowed_tables
        }
        idx.metrics = {
            name: m
            for name, m in self.metrics.items()
            if self.metric_tables(m) <= allowed_tables
        }
        idx.measures = {}
        for name, meas in self.measures.items():
            ent_name = meas.get("entity")
            if ent_name and ent_name in idx.entities:
                idx.measures[name] = meas
            elif not ent_name:
                # keep measure only if no entity binding (rare)
                idx.measures[name] = meas
        idx.dimensions = {}
        for name, dim in self.dimensions.items():
            ent_name = dim.get("entity")
            if ent_name and ent_name in idx.entities:
                idx.dimensions[name] = dim
        idx.relationships = [
            rel
            for rel in self.relationships
            if str(rel.get("from_entity")) in idx.entities
            and str(rel.get("to_entity")) in idx.entities
        ]
        idx.rules = [
            r
            for r in self.rules
            if any(t in r for t in allowed_tables)
        ]
        idx.join_paths = [
            j
            for j in self.join_paths
            if any(t in j for t in allowed_tables)
        ]
        idx.column_hints = {
            k: v
            for k, v in self.column_hints.items()
            if self._dep_table(str(k)) in allowed_tables
        }
        idx._adjacency = defaultdict(list)
        for rel in idx.relationships:
            a = rel.get("from_entity")
            b = rel.get("to_entity")
            if not a or not b:
                continue
            idx._adjacency[str(a)].append((str(b), rel))
            rev = {
                **rel,
                "from_entity": b,
                "to_entity": a,
                "on": rel.get("on"),
                "_reversed": True,
            }
            idx._adjacency[str(b)].append((str(a), rev))
        return idx


def _walk_concepts(node: Any, concepts: set[str], times: list[dict[str, Any]]) -> None:
    if node is None:
        return
    if isinstance(node, dict):
        t = node.get("type")
        if t in {"ENTITY_REF", "DIMENSION_REF", "METRIC_REF"} and node.get("concept"):
            concepts.add(str(node["concept"]))
        if t == "TIME_FILTER":
            times.append(
                {
                    "range": str(node.get("range")),
                    "start": node.get("start"),
                    "end": node.get("end"),
                }
            )
        if t == "METRIC_EXPRESSION" and node.get("metric"):
            concepts.add(str(node["metric"]))
        for v in node.values():
            _walk_concepts(v, concepts, times)
        return
    if isinstance(node, list):
        for item in node:
            _walk_concepts(item, concepts, times)
        return
    if hasattr(node, "model_dump"):
        _walk_concepts(node.model_dump(mode="json", by_alias=True), concepts, times)
        return
    if hasattr(node, "__dict__"):
        for v in vars(node).values():
            _walk_concepts(v, concepts, times)


class GroundingEngine:
    """Deterministic grounding: Intent AST concepts × kb.json (+ contracts) → GroundedContext."""

    def __init__(
        self,
        kb_index: KbIndex | None = None,
        kb_path: Path | str | None = None,
        contracts: GroundingContracts | None = None,
        contracts_path: Path | str | None = None,
        business_objects: BusinessObjectRegistry | None = None,
        business_objects_path: Path | str | None = None,
        *,
        use_contracts: bool = True,
    ) -> None:
        self._kb = kb_index or KbIndex.from_path(kb_path)
        if not use_contracts:
            self._contracts = None
        elif contracts is not None:
            self._contracts = contracts
        else:
            self._contracts = load_grounding_contracts(contracts_path)
        if business_objects is not None:
            self._bo_registry = business_objects
        else:
            self._bo_registry = load_business_objects(business_objects_path)

    def ground(
        self,
        intent_result: IntentResult,
        normalized_question: NormalizedQuestion | None = None,
        *,
        bo_id: str | None = None,
    ) -> GroundedContext:
        if intent_result.intent_ast is None:
            return GroundedContext(
                status=GroundingStatus.FAILED,
                bo_id=bo_id,
                errors=["intent_ast is null; cannot ground"],
            )

        bo: BusinessObject | None = None
        kb = self._kb
        if bo_id is not None:
            if self._bo_registry is None:
                return GroundedContext(
                    status=GroundingStatus.FAILED,
                    bo_id=bo_id,
                    errors=[
                        f"business_objects registry missing; cannot scope to '{bo_id}'"
                    ],
                )
            try:
                bo = self._bo_registry.require(bo_id)
            except KeyError as exc:
                return GroundedContext(
                    status=GroundingStatus.FAILED,
                    bo_id=bo_id,
                    errors=[str(exc)],
                )
            kb = self._kb.scoped_to(bo.table_names)

        # Temporarily bind scoped kb for this call
        previous_kb = self._kb
        self._kb = kb
        try:
            ctx = self._ground_with_kb(
                intent_result,
                normalized_question,
                bo=bo,
                bo_id=bo_id,
            )
        finally:
            self._kb = previous_kb
        return ctx

    def _ground_with_kb(
        self,
        intent_result: IntentResult,
        normalized_question: NormalizedQuestion | None,
        *,
        bo: BusinessObject | None,
        bo_id: str | None,
    ) -> GroundedContext:
        concepts: set[str] = set()
        times: list[dict[str, Any]] = []
        _walk_concepts(intent_result.intent_ast, concepts, times)

        if normalized_question is not None:
            for c in normalized_question.recognized_concepts:
                if c.category != "TIME":
                    concepts.add(c.canonical)

        # Alias remap via overlay (Intent-stable canonicals)
        if self._contracts is not None:
            concepts = {self._contracts.resolve_metric_key(c) for c in concepts}

        entities: list[GroundedEntity] = []
        metrics: list[GroundedMetric] = []
        dimensions: list[GroundedDimension] = []
        unresolved: list[str] = []
        entity_names: set[str] = set()
        tables: set[str] = set()
        default_filters: list[str] = []
        preferred_path_ids: list[str] = []
        primary_time_columns: list[str] = []
        contracted_metrics: set[str] = set()
        errors: list[str] = []

        for concept in sorted(concepts):
            if concept in self._kb.entities:
                ge = self._ground_entity(
                    concept, self._kb.entities[concept], bo=bo
                )
                entities.append(ge)
                entity_names.add(concept)
                tables.add(ge.source_table)
                continue

            contract = (
                self._contracts.contract_for(concept) if self._contracts else None
            )
            metric_key = (
                self._contracts.resolve_metric_key(concept)
                if self._contracts
                else concept
            )

            if metric_key in self._kb.metrics:
                gm = self._ground_metric_from_metrics(
                    metric_key, self._kb.metrics[metric_key], contract
                )
                metrics.append(gm)
                for dep in gm.dependencies:
                    if "." not in dep:
                        tables.add(dep)
                    else:
                        tables.add(dep.split(".", 1)[0])
                if contract:
                    contracted_metrics.add(metric_key)
                    self._apply_contract_side_effects(
                        contract,
                        entity_names=entity_names,
                        default_filters=default_filters,
                        preferred_path_ids=preferred_path_ids,
                        primary_time_columns=primary_time_columns,
                    )
                continue

            if concept in self._kb.measures or metric_key in self._kb.measures:
                key = metric_key if metric_key in self._kb.measures else concept
                gm = self._ground_metric_from_measure(key, self._kb.measures[key])
                metrics.append(gm)
                if gm.entity:
                    entity_names.add(gm.entity)
                    ent = self._kb.entities.get(gm.entity)
                    if ent and ent.get("source_table"):
                        tables.add(str(ent["source_table"]))
                if contract:
                    contracted_metrics.add(key)
                    self._apply_contract_side_effects(
                        contract,
                        entity_names=entity_names,
                        default_filters=default_filters,
                        preferred_path_ids=preferred_path_ids,
                        primary_time_columns=primary_time_columns,
                    )
                continue

            if concept in self._kb.dimensions:
                gd = self._ground_dimension(concept, self._kb.dimensions[concept])
                dimensions.append(gd)
                if gd.entity:
                    entity_names.add(gd.entity)
                continue

            unresolved.append(concept)

        # Legacy heuristics only for metrics without a contract
        for gm in metrics:
            if gm.concept in contracted_metrics:
                continue
            for dep in gm.dependencies:
                tables.add(dep.split(".", 1)[0])
            if any("payment_details" in d for d in gm.dependencies):
                if "Payment" in self._kb.entities:
                    entity_names.add("Payment")
                if "AcademicBag" in self._kb.entities:
                    entity_names.add("AcademicBag")
            if any("academic_bag" in d and "items" not in d for d in gm.dependencies):
                if "AcademicBag" in self._kb.entities:
                    entity_names.add("AcademicBag")

        # Paths that declare for_metrics for grounded metrics without their own path id
        if self._contracts is not None:
            for path in self._contracts.preferred_join_paths:
                matched = [m for m in metrics if m.concept in path.for_metrics]
                if not matched:
                    continue
                needs_for_metrics_path = any(
                    (self._contracts.contract_for(m.concept) is None)
                    or (
                        not self._contracts.contract_for(m.concept).preferred_path_id  # type: ignore[union-attr]
                    )
                    for m in matched
                )
                if needs_for_metrics_path and path.id not in preferred_path_ids:
                    preferred_path_ids.append(path.id)

            for path_id in preferred_path_ids:
                path = self._contracts.paths_by_id.get(path_id)
                if path:
                    for name in path.entities:
                        entity_names.add(name)

        # Drop entities not in scoped KB
        entity_names = {n for n in entity_names if n in self._kb.entities}

        existing = {e.concept for e in entities}
        for name in sorted(entity_names):
            if name not in existing and name in self._kb.entities:
                ge = self._ground_entity(name, self._kb.entities[name], bo=bo)
                entities.append(ge)
                tables.add(ge.source_table)
                existing.add(name)

        joins: list[GroundedJoin] = []
        applied_path_ids: list[str] = []
        unique_path_ids = list(dict.fromkeys(preferred_path_ids))

        if self._contracts is not None and unique_path_ids:
            if len(unique_path_ids) > 1:
                errors.append(
                    f"conflicting preferred join paths: {', '.join(unique_path_ids)}"
                )
            else:
                path_id = unique_path_ids[0]
                path = self._contracts.paths_by_id.get(path_id)
                if path is None:
                    errors.append(f"preferred path id not found: {path_id}")
                elif bo is not None and any(
                    name not in self._kb.entities for name in path.entities
                ):
                    missing = [
                        name for name in path.entities if name not in self._kb.entities
                    ]
                    errors.append(
                        f"preferred path '{path_id}' leaves BO '{bo_id}': "
                        f"missing entities {', '.join(missing)}"
                    )
                else:
                    path_joins, path_errs = self._joins_from_entity_chain(path)
                    joins.extend(path_joins)
                    errors.extend(path_errs)
                    if not path_errs:
                        applied_path_ids.append(path_id)
                    for name in path.entities:
                        if name not in existing and name in self._kb.entities:
                            ge = self._ground_entity(
                                name, self._kb.entities[name], bo=bo
                            )
                            entities.append(ge)
                            tables.add(ge.source_table)
                            existing.add(name)
                            entity_names.add(name)

        if not joins:
            joins = self._resolve_joins(sorted(entity_names))

        # Enforce BO table allow-list on collected tables
        if bo is not None:
            tables = {t for t in tables if bo.allows_table(t)}

        time_filters = [
            self._ground_time(
                t,
                tables=tables,
                entities=entities,
                primary_time_columns=primary_time_columns,
            )
            for t in times
        ]

        hay_terms = {c.lower() for c in concepts} | {t.lower() for t in tables}
        hay_terms |= {e.concept.lower() for e in entities}
        rules = self._select_text(self._kb.rules, hay_terms, limit=12)
        guidance = self._select_text(self._kb.join_paths, hay_terms, limit=8)

        seen_f: set[str] = set()
        uniq_filters: list[str] = []
        for f in default_filters:
            if f not in seen_f:
                seen_f.add(f)
                uniq_filters.append(f)

        if unresolved and (entities or metrics):
            status = GroundingStatus.PARTIAL
        elif unresolved and not entities and not metrics:
            status = GroundingStatus.FAILED
        elif not entities and not metrics and not time_filters:
            status = GroundingStatus.FAILED
        elif errors and (entities or metrics):
            status = GroundingStatus.PARTIAL
        else:
            status = GroundingStatus.VALID

        if status == GroundingStatus.FAILED and not errors:
            errors.append("could not resolve any groundable concepts from intent AST")
        if unresolved:
            msg = f"unresolved concepts: {', '.join(unresolved)}"
            if bo_id is not None:
                msg += f" (scoped to BO '{bo_id}')"
            errors.append(msg)

        base_entity: str | None = None
        if applied_path_ids and self._contracts is not None:
            path = self._contracts.paths_by_id.get(applied_path_ids[0])
            if path and path.entities:
                base_entity = path.entities[0]
        if base_entity is None:
            for gm in metrics:
                if self._contracts is None:
                    break
                contract = self._contracts.contract_for(gm.concept)
                if contract and contract.grain_entities:
                    candidate = contract.grain_entities[0]
                    if candidate in {e.concept for e in entities}:
                        base_entity = candidate
                        break
        if base_entity is None and entities:
            # Fallback: first grounded entity by name (stable); IR still does not invent joins
            base_entity = sorted(e.concept for e in entities)[0]

        return GroundedContext(
            status=status,
            bo_id=bo_id,
            base_entity=base_entity,
            entities=entities,
            metrics=metrics,
            dimensions=dimensions,
            joins=joins,
            time_filters=time_filters,
            tables=sorted(tables),
            rules=rules,
            join_guidance=guidance,
            unresolved_concepts=unresolved,
            errors=errors,
            default_filters=uniq_filters,
            applied_path_ids=applied_path_ids,
        )

    @staticmethod
    def _apply_contract_side_effects(
        contract: MetricContract,
        *,
        entity_names: set[str],
        default_filters: list[str],
        preferred_path_ids: list[str],
        primary_time_columns: list[str],
    ) -> None:
        for name in contract.grain_entities:
            entity_names.add(name)
        for name in contract.required_entities:
            entity_names.add(name)
        default_filters.extend(contract.default_filters)
        if contract.preferred_path_id:
            preferred_path_ids.append(contract.preferred_path_id)
        if contract.default_time_column:
            primary_time_columns.append(contract.default_time_column)

    def _joins_from_entity_chain(
        self, path: PreferredJoinPath
    ) -> tuple[list[GroundedJoin], list[str]]:
        joins: list[GroundedJoin] = []
        errs: list[str] = []
        entities = path.entities
        for i in range(len(entities) - 1):
            a, b = entities[i], entities[i + 1]
            rel = self._kb.find_relationship(a, b)
            if rel is None:
                errs.append(
                    f"no relationship edge for preferred path "
                    f"'{path.id}': {a} — {b}"
                )
                continue
            joins.append(
                GroundedJoin(
                    from_entity=str(rel.get("from_entity")),
                    to_entity=str(rel.get("to_entity")),
                    on=str(rel.get("on") or ""),
                    join_type=str(rel.get("join_type") or "inner"),
                    cardinality=rel.get("cardinality"),
                    name=rel.get("name"),
                )
            )
        return joins, errs

    def _ground_entity(
        self,
        concept: str,
        ent: dict[str, Any],
        *,
        bo: BusinessObject | None = None,
    ) -> GroundedEntity:
        columns = [str(c) for c in (ent.get("columns") or [])]
        source_table = str(ent.get("source_table") or "")
        if bo is not None:
            allowed = bo.allowed_columns(source_table)
            if allowed is not None:
                allow_set = set(allowed)
                columns = [c for c in columns if c in allow_set] or list(allowed)
        display = None
        for candidate in ("name", "title", "label", "code"):
            if candidate in columns:
                display = candidate
                break
        return GroundedEntity(
            concept=concept,
            source_table=source_table,
            primary_key=str(ent["primary_key"]) if ent.get("primary_key") else None,
            columns=columns,
            display_column=display,
            synonyms=[str(s) for s in (ent.get("synonyms") or [])],
            description=ent.get("description"),
        )

    def _ground_metric_from_metrics(
        self,
        concept: str,
        metric: dict[str, Any],
        contract: MetricContract | None = None,
    ) -> GroundedMetric:
        sql = str(metric.get("sql_expression") or "")
        if contract and contract.sql_expression_override:
            sql = contract.sql_expression_override
        return GroundedMetric(
            concept=concept,
            sql_expression=sql,
            unit=metric.get("unit"),
            dependencies=[str(d) for d in (metric.get("dependencies") or [])],
            description=metric.get("description"),
            source="metrics",
        )

    def _ground_metric_from_measure(
        self, concept: str, meas: dict[str, Any]
    ) -> GroundedMetric:
        return GroundedMetric(
            concept=concept,
            sql_expression=str(meas.get("sql") or ""),
            unit=None,
            dependencies=[],
            entity=str(meas["entity"]) if meas.get("entity") else None,
            column=str(meas["column"]) if meas.get("column") else None,
            aggregation_type=str(meas["aggregation_type"])
            if meas.get("aggregation_type")
            else None,
            description=meas.get("description"),
            source="measures",
        )

    def _ground_dimension(self, concept: str, dim: dict[str, Any]) -> GroundedDimension:
        return GroundedDimension(
            concept=concept,
            column=str(dim["column"]) if dim.get("column") else None,
            entity=str(dim["entity"]) if dim.get("entity") else None,
            data_type=str(dim["type"]) if dim.get("type") else None,
            description=dim.get("description"),
        )

    def _ground_time(
        self,
        time_spec: dict[str, Any],
        *,
        tables: set[str],
        entities: list[GroundedEntity],
        primary_time_columns: list[str] | None = None,
    ) -> GroundedTimeFilter:
        suggested: list[str] = []
        for col in primary_time_columns or []:
            if col not in suggested:
                suggested.append(col)

        for table in sorted(tables):
            for col in ("created_at", "payment_date", "paid_at", "enrollment_date"):
                key = f"{table}.{col}"
                if key in self._kb.column_hints or col in {
                    c for e in entities if e.source_table == table for c in e.columns
                }:
                    candidate = (
                        key if key in self._kb.column_hints else f"{table}.{col}"
                    )
                    if candidate not in suggested:
                        suggested.append(candidate)

        notes = None
        if suggested:
            if primary_time_columns:
                notes = (
                    f"Primary time column from contract: {primary_time_columns[0]}; "
                    f"also consider: {', '.join(suggested[1:3])}"
                    if len(suggested) > 1
                    else f"Primary time column from contract: {suggested[0]}"
                )
            else:
                notes = f"Prefer filtering date window on: {', '.join(suggested[:3])}"
        return GroundedTimeFilter(
            range=str(time_spec.get("range")),
            start=time_spec.get("start"),
            end=time_spec.get("end"),
            suggested_columns=suggested[:5],
            notes=notes,
        )

    def _resolve_joins(self, entity_names: list[str]) -> list[GroundedJoin]:
        if len(entity_names) < 2:
            return []
        needed = set(entity_names)
        start = entity_names[0]
        visited = {start}
        parent: dict[str, tuple[str, dict[str, Any]] | None] = {start: None}
        q: deque[str] = deque([start])
        while q:
            cur = q.popleft()
            for neighbor, rel in self._kb._adjacency.get(cur, []):
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                parent[neighbor] = (cur, rel)
                q.append(neighbor)
                if needed.issubset(visited):
                    break

        edges: list[GroundedJoin] = []
        seen_edge: set[tuple[str, str, str]] = set()
        for target in entity_names[1:]:
            if target not in parent:
                continue
            node = target
            while parent.get(node) is not None:
                prev, rel = parent[node]  # type: ignore[misc]
                fr = str(rel.get("from_entity"))
                to = str(rel.get("to_entity"))
                on = str(rel.get("on") or "")
                key = (fr, to, on)
                if key not in seen_edge:
                    seen_edge.add(key)
                    edges.append(
                        GroundedJoin(
                            from_entity=fr,
                            to_entity=to,
                            on=on,
                            join_type=str(rel.get("join_type") or "inner"),
                            cardinality=rel.get("cardinality"),
                            name=rel.get("name"),
                        )
                    )
                node = prev
        return edges

    @staticmethod
    def _select_text(items: list[str], terms: set[str], limit: int) -> list[str]:
        scored: list[tuple[int, str]] = []
        for text in items:
            low = text.lower()
            score = sum(1 for t in terms if t and t in low)
            if score:
                scored.append((score, text))
        scored.sort(key=lambda x: (-x[0], x[1]))
        return [t for _, t in scored[:limit]]
