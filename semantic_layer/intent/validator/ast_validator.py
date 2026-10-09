from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel

from semantic_layer.intent.models.ast import (
    Aggregate,
    BetweenPredicate,
    Change,
    Compare,
    DimensionRef,
    EntityRef,
    Exists,
    InPredicate,
    MetricRef,
    OrderBy,
    QueryNode,
    Rank,
    Ratio,
    Subquery,
    Window,
)
from semantic_layer.intent.models.enums import AggregateFunction, SortDirection


_PHYSICAL_CONCEPT_RE = re.compile(r"(?i)^(public_|.*\..*|.*\bjoin\b.*)$")


class AstValidator:
    """Structural + semantic validation; reject physical DB identifiers."""

    def validate(self, node: QueryNode | Any) -> list[str]:
        errors: list[str] = []
        if node is None:
            return ["intent_ast is null"]
        if not isinstance(node, QueryNode):
            errors.append(f"root must be QUERY, got {getattr(node, 'type', type(node))}")
            return errors
        self._walk(node, errors)
        return errors

    def _walk(self, node: Any, errors: list[str], path: str = "root") -> None:
        if node is None:
            return

        if isinstance(node, (EntityRef, DimensionRef, MetricRef)):
            if self._looks_physical(node.concept):
                errors.append(f"{path}: physical identifier in concept '{node.concept}'")

        if isinstance(node, Rank):
            if node.limit is None or int(node.limit) <= 0:
                errors.append(f"{path}: RANK.limit must be a positive integer")
            if node.dimension is None:
                errors.append(f"{path}: RANK requires dimension")
            if node.metric is None:
                errors.append(f"{path}: RANK requires metric")
            if node.direction not in (SortDirection.ASC, SortDirection.DESC):
                errors.append(f"{path}: RANK.direction invalid")
            self._walk(node.dimension, errors, f"{path}.dimension")
            self._walk(node.metric, errors, f"{path}.metric")
            return

        if isinstance(node, Aggregate):
            try:
                AggregateFunction(node.function)
            except ValueError:
                errors.append(f"{path}: invalid aggregate function")
            if (
                node.function != AggregateFunction.COUNT
                and node.argument is None
            ):
                errors.append(f"{path}: AGGREGATE requires argument")
            self._walk(node.argument, errors, f"{path}.argument")
            return

        if isinstance(node, BetweenPredicate):
            if node.lower is None or node.upper is None:
                errors.append(f"{path}: BETWEEN requires lower and upper")
            self._walk(node.expression, errors, f"{path}.expression")
            self._walk(node.lower, errors, f"{path}.lower")
            self._walk(node.upper, errors, f"{path}.upper")
            return

        if isinstance(node, InPredicate):
            if not node.values:
                errors.append(f"{path}: IN requires values list")
            self._walk(node.expression, errors, f"{path}.expression")
            for i, v in enumerate(node.values):
                self._walk(v, errors, f"{path}.values[{i}]")
            return

        if isinstance(node, Subquery):
            if not isinstance(node.query, QueryNode):
                errors.append(f"{path}: SUBQUERY must contain QUERY")
            else:
                self._walk(node.query, errors, f"{path}.query")
            return

        if isinstance(node, Exists):
            if not isinstance(node.query, QueryNode):
                errors.append(f"{path}: EXISTS must contain QUERY")
            else:
                self._walk(node.query, errors, f"{path}.query")
            return

        if isinstance(node, OrderBy):
            if node.direction not in (SortDirection.ASC, SortDirection.DESC):
                errors.append(f"{path}: ORDER_BY direction invalid")
            self._walk(node.expression, errors, f"{path}.expression")
            return

        if isinstance(node, Compare):
            if node.left is None or node.right is None:
                errors.append(f"{path}: COMPARE requires left and right")
            self._walk(node.left, errors, f"{path}.left")
            self._walk(node.right, errors, f"{path}.right")
            return

        if isinstance(node, Change):
            if node.metric is None:
                errors.append(f"{path}: CHANGE requires metric")
            self._walk(node.metric, errors, f"{path}.metric")
            return

        if isinstance(node, Ratio):
            if node.numerator is None or node.denominator is None:
                errors.append(f"{path}: RATIO requires numerator and denominator")
            self._walk(node.numerator, errors, f"{path}.numerator")
            self._walk(node.denominator, errors, f"{path}.denominator")
            return

        if isinstance(node, Window):
            self._walk(node.argument, errors, f"{path}.argument")
            return

        if isinstance(node, QueryNode):
            for i, expr in enumerate(node.select):
                self._walk(expr, errors, f"{path}.select[{i}]")
            for i, src in enumerate(node.from_):
                self._walk(src, errors, f"{path}.from[{i}]")
            if node.where is not None:
                self._walk(node.where, errors, f"{path}.where")
            for i, g in enumerate(node.group_by):
                self._walk(g, errors, f"{path}.group_by[{i}]")
            if node.having is not None:
                self._walk(node.having, errors, f"{path}.having")
            for i, o in enumerate(node.order_by):
                self._walk(o, errors, f"{path}.order_by[{i}]")
            for i, op in enumerate(node.operations):
                self._walk(op, errors, f"{path}.operations[{i}]")
            if node.set_operation is not None:
                self._walk(node.set_operation, errors, f"{path}.set_operation")
            return

        if isinstance(node, BaseModel):
            for name in type(node).model_fields:
                child = getattr(node, name, None)
                if isinstance(child, list):
                    for i, item in enumerate(child):
                        if hasattr(item, "type"):
                            self._walk(item, errors, f"{path}.{name}[{i}]")
                elif hasattr(child, "type"):
                    self._walk(child, errors, f"{path}.{name}")

    @staticmethod
    def _looks_physical(concept: str) -> bool:
        if "." in concept:
            return True
        if concept.lower().startswith("public_"):
            return True
        return bool(re.search(r"(?i)\b(join|select)\b", concept))
