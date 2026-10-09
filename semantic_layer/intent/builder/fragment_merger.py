from __future__ import annotations

from dataclasses import dataclass, field

from semantic_layer.intent.models.ast import (
    BinaryPredicate,
    Logical,
    QueryNode,
    Rank,
    TimeFilter,
)
from semantic_layer.intent.models.enums import LogicalOperator
from semantic_layer.intent.parser.types import SemanticFragment


@dataclass
class MergeResult:
    query: QueryNode | None = None
    contributing_patterns: list[str] = field(default_factory=list)
    ambiguities: list[str] = field(default_factory=list)
    unsupported: bool = False
    confidence: float = 0.0


class FragmentMerger:
    """Combine compatible semantic fragments; conflict → AMBIGUOUS."""

    def merge(self, fragments: list[SemanticFragment]) -> MergeResult:
        if not fragments:
            return MergeResult(unsupported=True, confidence=0.0)

        if any(f.kind == "unsupported" for f in fragments):
            return MergeResult(
                unsupported=True,
                contributing_patterns=[f.pattern_id for f in fragments if f.kind == "unsupported"],
                confidence=0.0,
            )

        ambiguities = [f.ambiguity for f in fragments if f.ambiguity]
        # Explicit maximum-by ambiguity: aggregate_max with by → ambiguous
        kinds = [f.kind for f in fragments]
        pattern_ids = [f.pattern_id for f in fragments]
        if "aggregate_max" in pattern_ids or "aggregate_min" in pattern_ids:
            if any(f.ambiguity for f in fragments):
                return MergeResult(
                    ambiguities=[
                        a
                        or "maximum/minimum with BY may mean aggregation or ranking"
                        for a in ambiguities
                    ]
                    or ["maximum/minimum with BY may mean aggregation or ranking"],
                    contributing_patterns=[],
                    confidence=0.58,
                )

        # Deduplicate by kind preference for primary ops
        primary_kinds = {"rank", "aggregate", "compare", "change", "ratio", "list"}
        primaries = [f for f in fragments if f.kind in primary_kinds]
        # Conflicting primaries of different kinds that aren't mergeable
        if len({f.kind for f in primaries}) > 1:
            kinds_set = {f.kind for f in primaries}
            if "rank" in kinds_set and "aggregate" in kinds_set:
                return MergeResult(
                    ambiguities=["conflicting primary operations: rank vs aggregate"],
                    confidence=0.5,
                )
            if "compare" in kinds_set and "change" in kinds_set:
                return MergeResult(
                    ambiguities=["conflicting primary operations: compare vs change"],
                    confidence=0.55,
                )
            if "list" in kinds_set and kinds_set - {"list"}:
                return MergeResult(
                    ambiguities=[
                        f"conflicting primary operations: list vs {sorted(kinds_set - {'list'})}"
                    ],
                    confidence=0.5,
                )

        # Conflicting limits / directions within rank
        ranks = [f for f in fragments if f.kind == "rank"]
        if len(ranks) > 1:
            limits = {f.payload["rank"].limit for f in ranks}
            dirs = {f.payload["rank"].direction for f in ranks}
            if len(limits) > 1 or len(dirs) > 1:
                return MergeResult(
                    ambiguities=["conflicting RANK limit or direction"],
                    confidence=0.5,
                )

        query = QueryNode()
        contributing: list[str] = []
        confidences: list[float] = []

        for frag in fragments:
            contributing.append(frag.pattern_id)
            confidences.append(frag.confidence)

            if frag.kind == "rank":
                rank: Rank = frag.payload["rank"]
                query.operations.append(rank)
                query.select = [rank.dimension, rank.metric]
                query.group_by = [rank.dimension]
                query.order_by = []
                query.limit = rank.limit
                query.from_ = []
            elif frag.kind == "list":
                for item in frag.payload.get("select") or []:
                    if item not in query.select:
                        query.select.append(item)
                for item in frag.payload.get("from") or []:
                    if item not in query.from_:
                        query.from_.append(item)
                if frag.payload.get("distinct"):
                    query.distinct = True
            elif frag.kind == "order":
                order = frag.payload["order_by"]
                query.order_by.append(order)
            elif frag.kind == "aggregate":
                agg = frag.payload["aggregate"]
                group = frag.payload.get("group_by")
                having = frag.payload.get("having")
                query.select.append(agg)
                if group is not None:
                    query.group_by.append(group)
                    if group not in query.select:
                        query.select.insert(0, group)
                if having is not None:
                    query.having = (
                        having
                        if query.having is None
                        else self._and_where(query.having, having)
                    )
            elif frag.kind == "filter":
                pred = frag.payload["predicate"]
                dim = frag.payload.get("select_dim")
                if dim is not None and dim not in query.select:
                    query.select.append(dim)
                query.where = self._and_where(query.where, pred)
            elif frag.kind == "time_filter":
                tf: TimeFilter = frag.payload["time_filter"]
                query.where = self._and_where(query.where, tf)
            elif frag.kind == "compare":
                query.operations.append(frag.payload["compare"])
                query.select.append(frag.payload["compare"])
            elif frag.kind == "change":
                query.operations.append(frag.payload["change"])
                query.select.append(frag.payload["change"])
            elif frag.kind == "ratio":
                query.operations.append(frag.payload["ratio"])
                query.select.append(frag.payload["ratio"])

        # Deduplicate contributing pattern ids preserving order
        seen: set[str] = set()
        uniq: list[str] = []
        for p in contributing:
            if p not in seen:
                seen.add(p)
                uniq.append(p)

        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
        return MergeResult(
            query=query,
            contributing_patterns=uniq,
            confidence=avg_conf,
        )

    @staticmethod
    def _and_where(existing, new_pred):
        if existing is None:
            return new_pred
        if isinstance(existing, Logical) and existing.operator == LogicalOperator.AND:
            return Logical(
                operator=LogicalOperator.AND,
                conditions=[*existing.conditions, new_pred],
            )
        return Logical(operator=LogicalOperator.AND, conditions=[existing, new_pred])
