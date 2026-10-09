from semantic_layer.intent.models import (
    INTENT_SCHEMA_VERSION,
    Aggregate,
    DimensionRef,
    LiteralNode,
    MetricRef,
    QueryNode,
    Rank,
)
from semantic_layer.intent.models.enums import (
    AggregateFunction,
    LiteralDataType,
    SortDirection,
)
from semantic_layer.intent.validator import AstValidator


def test_schema_version_constant():
    assert INTENT_SCHEMA_VERSION == "intent-v1"


def test_rank_model():
    node = Rank(
        dimension=DimensionRef(concept="Grade"),
        metric=MetricRef(concept="Revenue"),
        direction=SortDirection.DESC,
        limit=10,
    )
    assert node.type == "RANK"
    assert node.limit == 10


def test_query_from_alias():
    q = QueryNode(from_=[DimensionRef(concept="Grade")])
    dumped = q.model_dump(by_alias=True)
    assert "from" in dumped
    assert dumped["from"][0]["concept"] == "Grade"


def test_validator_accepts_valid_rank_query():
    q = QueryNode(
        select=[DimensionRef(concept="Grade"), MetricRef(concept="Revenue")],
        operations=[
            Rank(
                dimension=DimensionRef(concept="Grade"),
                metric=MetricRef(concept="Revenue"),
                limit=10,
            )
        ],
        limit=10,
    )
    assert AstValidator().validate(q) == []


def test_validator_rejects_physical_concept():
    q = QueryNode(select=[MetricRef(concept="public_grades.revenue")])
    errors = AstValidator().validate(q)
    assert errors


def test_validator_rejects_bad_rank_limit():
    q = QueryNode(
        operations=[
            Rank(
                dimension=DimensionRef(concept="Grade"),
                metric=MetricRef(concept="Revenue"),
                limit=0,
            )
        ]
    )
    errors = AstValidator().validate(q)
    assert any("limit" in e.lower() for e in errors)


def test_aggregate_and_literal():
    agg = Aggregate(
        function=AggregateFunction.SUM,
        argument=MetricRef(concept="Revenue"),
    )
    lit = LiteralNode(value=5000, data_type=LiteralDataType.NUMBER)
    assert agg.type == "AGGREGATE"
    assert lit.type == "LITERAL"
