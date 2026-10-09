from __future__ import annotations

import re
from typing import Any

from semantic_layer.intent.builder.concept_binder import ConceptBindings
from semantic_layer.intent.models.ast import (
    Aggregate,
    BetweenPredicate,
    BinaryPredicate,
    Change,
    Compare,
    DimensionRef,
    EntityRef,
    LiteralNode,
    MetricExpression,
    MetricRef,
    NullPredicate,
    OrderBy,
    QueryNode,
    Rank,
    Ratio,
    Subquery,
    TimeFilter,
)
from semantic_layer.intent.models.enums import (
    AggregateFunction,
    ChangeType,
    ComparisonType,
    LiteralDataType,
    PredicateOperator,
    RatioOutput,
    SortDirection,
    TimeRange,
)
from semantic_layer.intent.parser.types import PatternMatch, SemanticFragment


_OP_MAP = {
    ">": PredicateOperator.GT,
    "<": PredicateOperator.LT,
    ">=": PredicateOperator.GTE,
    "<=": PredicateOperator.LTE,
    "=": PredicateOperator.EQ,
}


def _dimension_from_phrase(phrase: str, bindings: ConceptBindings) -> DimensionRef:
    """Map a filter phrase to a bound concept when possible; else keep surface text."""
    needle = phrase.strip().lower()
    for concept in bindings.raw_concepts:
        if concept.text.lower() == needle or concept.canonical.lower() == needle:
            return DimensionRef(concept=concept.canonical)
        if needle in concept.text.lower() or concept.text.lower() in needle:
            return DimensionRef(concept=concept.canonical)
    if bindings.metrics:
        for metric in bindings.metrics:
            if metric.concept.lower() in needle or needle in metric.concept.lower():
                return DimensionRef(concept=metric.concept)
    return DimensionRef(concept=phrase.strip().replace(" ", "_"))


class AstBuilder:
    """Build semantic fragments from pattern matches; recursive composition."""

    def build_fragment(
        self, match: PatternMatch, bindings: ConceptBindings
    ) -> SemanticFragment:
        handler = getattr(self, f"_build_{match.builder}", None)
        if handler is None:
            return SemanticFragment(
                pattern_id=match.pattern_id,
                kind="unsupported",
                payload={},
                confidence=0.0,
                ambiguity=f"unknown builder {match.builder}",
            )
        return handler(match, bindings)

    def _build_unsupported_window(
        self, match: PatternMatch, bindings: ConceptBindings
    ) -> SemanticFragment:
        return SemanticFragment(
            pattern_id=match.pattern_id,
            kind="unsupported",
            payload={"reason": "WINDOW not implemented in V1 parser"},
            confidence=0.0,
        )

    def _build_rank(
        self, match: PatternMatch, bindings: ConceptBindings
    ) -> SemanticFragment:
        entity = bindings.first_entity()
        metric = bindings.first_metric()
        assert entity and metric
        direction = SortDirection(match.slots.get("direction", "DESC"))
        limit = int(match.slots["limit"])
        rank = Rank(
            dimension=DimensionRef(concept=entity.concept),
            metric=metric,
            direction=direction,
            limit=limit,
        )
        return SemanticFragment(
            pattern_id=match.pattern_id,
            kind="rank",
            payload={"rank": rank},
            confidence=match.confidence,
            ambiguity=match.ambiguity,
        )

    def _build_aggregate(
        self, match: PatternMatch, bindings: ConceptBindings
    ) -> SemanticFragment:
        metric = bindings.first_metric()
        fn = AggregateFunction(match.slots.get("function", "SUM"))
        agg = Aggregate(function=fn, argument=metric)
        return SemanticFragment(
            pattern_id=match.pattern_id,
            kind="aggregate",
            payload={"aggregate": agg, "group_by": None},
            confidence=match.confidence,
            ambiguity=match.ambiguity,
        )

    def _build_aggregate_group(
        self, match: PatternMatch, bindings: ConceptBindings
    ) -> SemanticFragment:
        metric = bindings.first_metric()
        entity = bindings.first_entity()
        fn = AggregateFunction(match.slots.get("function", "SUM"))
        agg = Aggregate(function=fn, argument=metric)
        group = DimensionRef(concept=entity.concept) if entity else None
        return SemanticFragment(
            pattern_id=match.pattern_id,
            kind="aggregate",
            payload={"aggregate": agg, "group_by": group},
            confidence=match.confidence,
            ambiguity=match.ambiguity,
        )

    def _build_count(
        self, match: PatternMatch, bindings: ConceptBindings
    ) -> SemanticFragment:
        entity = bindings.first_entity()
        arg: EntityRef | MetricRef | None = entity or bindings.first_metric()
        agg = Aggregate(function=AggregateFunction.COUNT, argument=arg)
        return SemanticFragment(
            pattern_id=match.pattern_id,
            kind="aggregate",
            payload={"aggregate": agg, "group_by": None},
            confidence=match.confidence,
            ambiguity=match.ambiguity,
        )

    def _build_threshold_filter(
        self, match: PatternMatch, bindings: ConceptBindings
    ) -> SemanticFragment:
        metric = bindings.first_metric()
        assert metric
        threshold = float(match.slots["threshold"])
        op = _OP_MAP[match.slots.get("comparator", ">")]
        pred = BinaryPredicate(
            operator=op,
            left=metric,
            right=LiteralNode(value=threshold, data_type=LiteralDataType.NUMBER),
        )
        return SemanticFragment(
            pattern_id=match.pattern_id,
            kind="filter",
            payload={"predicate": pred},
            confidence=match.confidence,
        )

    def _build_time_filter(
        self, match: PatternMatch, bindings: ConceptBindings
    ) -> SemanticFragment:
        tf = bindings.first_time()
        assert tf
        return SemanticFragment(
            pattern_id=match.pattern_id,
            kind="time_filter",
            payload={"time_filter": tf},
            confidence=match.confidence,
        )

    def _build_compare(
        self, match: PatternMatch, bindings: ConceptBindings
    ) -> SemanticFragment:
        metric = bindings.first_metric()
        assert metric
        t1 = bindings.times[0].range if bindings.times else TimeRange.THIS_YEAR
        t2 = (
            bindings.times[1].range
            if len(bindings.times) > 1
            else TimeRange.LAST_YEAR
        )
        compare = Compare(
            left=MetricExpression(metric=metric.concept, period=t1),
            right=MetricExpression(metric=metric.concept, period=t2),
            comparison_type=ComparisonType.PERIOD_OVER_PERIOD,
        )
        return SemanticFragment(
            pattern_id=match.pattern_id,
            kind="compare",
            payload={"compare": compare},
            confidence=match.confidence,
        )

    def _build_change(
        self, match: PatternMatch, bindings: ConceptBindings
    ) -> SemanticFragment:
        metric = bindings.first_metric()
        assert metric
        change = Change(
            metric=metric,
            current_period=TimeRange.THIS_YEAR,
            previous_period=TimeRange.LAST_YEAR,
            change_type=ChangeType.PERCENT_CHANGE,
        )
        return SemanticFragment(
            pattern_id=match.pattern_id,
            kind="change",
            payload={"change": change},
            confidence=match.confidence,
        )

    def _build_subquery_threshold(
        self, match: PatternMatch, bindings: ConceptBindings
    ) -> SemanticFragment:
        metric = bindings.first_metric()
        entity = bindings.first_entity()
        assert metric and entity
        sub = Subquery(
            query=QueryNode(
                select=[
                    Aggregate(function=AggregateFunction.AVG, argument=metric)
                ],
                from_=[entity],
            )
        )
        pred = BinaryPredicate(
            operator=PredicateOperator.GT,
            left=metric,
            right=sub,
        )
        return SemanticFragment(
            pattern_id=match.pattern_id,
            kind="filter",
            payload={
                "predicate": pred,
                "select_dim": DimensionRef(concept=entity.concept),
            },
            confidence=match.confidence,
        )

    def _build_ratio(
        self, match: PatternMatch, bindings: ConceptBindings
    ) -> SemanticFragment:
        metric = bindings.first_metric()
        assert metric
        entity = bindings.first_entity()
        numerator: Any = metric
        if entity:
            # percentage of total for a group — numerator filtered conceptually
            numerator = Aggregate(function=AggregateFunction.SUM, argument=metric)
        denominator = Aggregate(function=AggregateFunction.SUM, argument=metric)
        ratio = Ratio(
            numerator=numerator,
            denominator=denominator,
            output=RatioOutput.PERCENTAGE,
        )
        return SemanticFragment(
            pattern_id=match.pattern_id,
            kind="ratio",
            payload={"ratio": ratio, "group": entity},
            confidence=match.confidence,
        )

    def _build_list_entity(
        self, match: PatternMatch, bindings: ConceptBindings
    ) -> SemanticFragment:
        entity = bindings.first_entity()
        assert entity
        select: list[Any] = [entity]
        metric = bindings.first_metric()
        if metric is not None:
            select.append(metric)
        return SemanticFragment(
            pattern_id=match.pattern_id,
            kind="list",
            payload={
                "select": select,
                "from": [entity],
                "distinct": bool(match.slots.get("distinct", False)),
            },
            confidence=match.confidence,
            ambiguity=match.ambiguity,
        )

    def _build_order_by_metric(
        self, match: PatternMatch, bindings: ConceptBindings
    ) -> SemanticFragment:
        metric = bindings.first_metric()
        entity = bindings.first_entity()
        expression: Any = metric or entity
        assert expression is not None
        direction = SortDirection(match.slots.get("direction", "ASC"))
        return SemanticFragment(
            pattern_id=match.pattern_id,
            kind="order",
            payload={
                "order_by": OrderBy(expression=expression, direction=direction),
            },
            confidence=match.confidence,
        )

    def _build_relative_time_filter(
        self, match: PatternMatch, bindings: ConceptBindings
    ) -> SemanticFragment:
        days = int(match.slots["relative_days"])
        tf = TimeFilter(
            range=TimeRange.RELATIVE_DATE_RANGE,
            start=f"-{days}d",
            end="0d",
        )
        return SemanticFragment(
            pattern_id=match.pattern_id,
            kind="time_filter",
            payload={"time_filter": tf},
            confidence=match.confidence,
        )

    def _build_group_count_threshold(
        self, match: PatternMatch, bindings: ConceptBindings
    ) -> SemanticFragment:
        entity = bindings.first_entity()
        assert entity
        threshold = float(match.slots["threshold"])
        op = _OP_MAP[match.slots.get("comparator", ">")]
        agg = Aggregate(function=AggregateFunction.COUNT, argument=entity)
        dim = DimensionRef(concept=entity.concept)
        pred = BinaryPredicate(
            operator=op,
            left=agg,
            right=LiteralNode(value=threshold, data_type=LiteralDataType.NUMBER),
        )
        return SemanticFragment(
            pattern_id=match.pattern_id,
            kind="aggregate",
            payload={"aggregate": agg, "group_by": dim, "having": pred},
            confidence=match.confidence,
            ambiguity=match.ambiguity,
        )

    def _build_between_filter(
        self, match: PatternMatch, bindings: ConceptBindings
    ) -> SemanticFragment:
        metric = bindings.first_metric()
        assert metric
        pred = BetweenPredicate(
            expression=metric,
            lower=LiteralNode(
                value=float(match.slots["lower"]), data_type=LiteralDataType.NUMBER
            ),
            upper=LiteralNode(
                value=float(match.slots["upper"]), data_type=LiteralDataType.NUMBER
            ),
        )
        return SemanticFragment(
            pattern_id=match.pattern_id,
            kind="filter",
            payload={"predicate": pred},
            confidence=match.confidence,
        )

    def _build_equality_filter(
        self, match: PatternMatch, bindings: ConceptBindings
    ) -> SemanticFragment:
        left = _dimension_from_phrase(str(match.slots["eq_left"]), bindings)
        right_raw = str(match.slots["eq_right"])
        right: Any
        if re.fullmatch(r"\d+(?:\.\d+)?", right_raw):
            right = LiteralNode(
                value=float(right_raw), data_type=LiteralDataType.NUMBER
            )
        else:
            right = LiteralNode(value=right_raw, data_type=LiteralDataType.STRING)
        pred = BinaryPredicate(
            operator=PredicateOperator.EQ,
            left=left,
            right=right,
        )
        return SemanticFragment(
            pattern_id=match.pattern_id,
            kind="filter",
            payload={"predicate": pred},
            confidence=match.confidence,
        )

    def _build_null_filter(
        self, match: PatternMatch, bindings: ConceptBindings
    ) -> SemanticFragment:
        phrase = str(match.slots.get("null_expr") or "")
        if phrase:
            expr: Any = _dimension_from_phrase(phrase, bindings)
        else:
            entity = bindings.first_entity()
            assert entity
            expr = entity
        negated = bool(match.slots.get("negated", False))
        pred = NullPredicate(expression=expr, negated=negated)
        return SemanticFragment(
            pattern_id=match.pattern_id,
            kind="filter",
            payload={"predicate": pred},
            confidence=match.confidence,
        )

    def _build_like_filter(
        self, match: PatternMatch, bindings: ConceptBindings
    ) -> SemanticFragment:
        phrase = str(match.slots.get("like_expr") or "")
        if phrase:
            left: Any = _dimension_from_phrase(phrase, bindings)
        else:
            entity = bindings.first_entity()
            assert entity
            left = entity
        value = str(match.slots["like_value"])
        mode = str(match.slots.get("mode", "CONTAINS")).upper()
        if mode == "STARTS_WITH":
            pattern = f"{value}%"
        elif mode == "ENDS_WITH":
            pattern = f"%{value}"
        else:
            pattern = f"%{value}%"
        pred = BinaryPredicate(
            operator=PredicateOperator.LIKE,
            left=left,
            right=LiteralNode(value=pattern, data_type=LiteralDataType.STRING),
        )
        return SemanticFragment(
            pattern_id=match.pattern_id,
            kind="filter",
            payload={"predicate": pred},
            confidence=match.confidence,
        )
