from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

from semantic_layer.intent.models.enums import (
    AggregateFunction,
    ChangeType,
    ComparisonType,
    LiteralDataType,
    LogicalOperator,
    PredicateOperator,
    RatioOutput,
    SetOperationType,
    SortDirection,
    TimeRange,
)


class ASTNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str


class EntityRef(ASTNode):
    type: Literal["ENTITY_REF"] = "ENTITY_REF"
    concept: str


class DimensionRef(ASTNode):
    type: Literal["DIMENSION_REF"] = "DIMENSION_REF"
    concept: str


class MetricRef(ASTNode):
    type: Literal["METRIC_REF"] = "METRIC_REF"
    concept: str


class LiteralNode(ASTNode):
    type: Literal["LITERAL"] = "LITERAL"
    value: Any
    data_type: LiteralDataType


class Parameter(ASTNode):
    type: Literal["PARAMETER"] = "PARAMETER"
    name: str


class Aggregate(ASTNode):
    type: Literal["AGGREGATE"] = "AGGREGATE"
    function: AggregateFunction
    argument: Any | None = None


class BinaryPredicate(ASTNode):
    type: Literal["BINARY_PREDICATE"] = "BINARY_PREDICATE"
    operator: PredicateOperator
    left: Any
    right: Any


class InPredicate(ASTNode):
    type: Literal["IN_PREDICATE"] = "IN_PREDICATE"
    expression: Any
    values: list[Any] = Field(default_factory=list)
    negated: bool = False


class BetweenPredicate(ASTNode):
    type: Literal["BETWEEN_PREDICATE"] = "BETWEEN_PREDICATE"
    expression: Any
    lower: Any
    upper: Any


class NullPredicate(ASTNode):
    type: Literal["NULL_PREDICATE"] = "NULL_PREDICATE"
    expression: Any
    negated: bool = False


class Logical(ASTNode):
    type: Literal["LOGICAL"] = "LOGICAL"
    operator: LogicalOperator
    conditions: list[Any] = Field(default_factory=list)


class GroupBy(ASTNode):
    type: Literal["GROUP_BY"] = "GROUP_BY"
    expressions: list[Any] = Field(default_factory=list)


class OrderBy(ASTNode):
    type: Literal["ORDER_BY"] = "ORDER_BY"
    expression: Any
    direction: SortDirection = SortDirection.ASC


class Rank(ASTNode):
    type: Literal["RANK"] = "RANK"
    dimension: DimensionRef | EntityRef
    metric: MetricRef | Aggregate
    direction: SortDirection = SortDirection.DESC
    limit: int


class MetricExpression(ASTNode):
    type: Literal["METRIC_EXPRESSION"] = "METRIC_EXPRESSION"
    metric: str
    period: TimeRange | None = None


class Compare(ASTNode):
    type: Literal["COMPARE"] = "COMPARE"
    left: Any
    right: Any
    comparison_type: ComparisonType = ComparisonType.PERIOD_OVER_PERIOD


class Change(ASTNode):
    type: Literal["CHANGE"] = "CHANGE"
    metric: MetricRef
    current_period: TimeRange
    previous_period: TimeRange
    change_type: ChangeType = ChangeType.PERCENT_CHANGE


class Ratio(ASTNode):
    type: Literal["RATIO"] = "RATIO"
    numerator: Any
    denominator: Any
    output: RatioOutput = RatioOutput.PERCENTAGE


class TimeFilter(ASTNode):
    type: Literal["TIME_FILTER"] = "TIME_FILTER"
    range: TimeRange
    start: str | None = None
    end: str | None = None


class Subquery(ASTNode):
    type: Literal["SUBQUERY"] = "SUBQUERY"
    query: QueryNode


class Exists(ASTNode):
    type: Literal["EXISTS"] = "EXISTS"
    query: QueryNode
    negated: bool = False


class CaseWhen(BaseModel):
    model_config = ConfigDict(extra="forbid")

    when: Any
    then: Any


class Case(ASTNode):
    type: Literal["CASE"] = "CASE"
    branches: list[CaseWhen] = Field(default_factory=list)
    else_value: Any | None = None


class Window(ASTNode):
    type: Literal["WINDOW"] = "WINDOW"
    function: str
    argument: Any | None = None
    partition_by: list[Any] = Field(default_factory=list)
    order_by: list[OrderBy] = Field(default_factory=list)


class SetOperation(ASTNode):
    type: Literal["SET_OPERATION"] = "SET_OPERATION"
    operation: SetOperationType
    left: QueryNode
    right: QueryNode


class Filter(ASTNode):
    type: Literal["FILTER"] = "FILTER"
    predicate: Any


class QueryNode(ASTNode):
    type: Literal["QUERY"] = "QUERY"
    select: list[Any] = Field(default_factory=list)
    from_: list[Any] = Field(default_factory=list, alias="from")
    where: Any | None = None
    group_by: list[Any] = Field(default_factory=list)
    having: Any | None = None
    order_by: list[OrderBy] = Field(default_factory=list)
    limit: int | None = None
    offset: int | None = None
    distinct: bool = False
    set_operation: SetOperation | None = None
    operations: list[Any] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


# Alias kept for readability in exports
Literal = LiteralNode  # type: ignore[misc]

Subquery.model_rebuild()
Exists.model_rebuild()
SetOperation.model_rebuild()
QueryNode.model_rebuild()
