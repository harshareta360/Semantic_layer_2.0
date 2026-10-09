from semantic_layer.grounding import GroundingEngine, GroundingStatus
from semantic_layer.intent.models.ast import (
    DimensionRef,
    MetricRef,
    QueryNode,
    Rank,
    TimeFilter,
)
from semantic_layer.intent.models.enums import (
    IntentStatus,
    ParserSource,
    SortDirection,
    TimeRange,
)
from semantic_layer.intent.models.result import IntentResult
from semantic_layer.normalization.models import NormalizedQuestion, RecognizedConcept
from semantic_layer.pipeline import Pipeline


def _rank_intent() -> IntentResult:
    ast = QueryNode(
        select=[DimensionRef(concept="Grade"), MetricRef(concept="total_revenue")],
        operations=[
            Rank(
                dimension=DimensionRef(concept="Grade"),
                metric=MetricRef(concept="total_revenue"),
                direction=SortDirection.DESC,
                limit=10,
            )
        ],
        where=TimeFilter(range=TimeRange.THIS_YEAR),
        limit=10,
        group_by=[DimensionRef(concept="Grade")],
    )
    return IntentResult(
        status=IntentStatus.VALID,
        parser=ParserSource.RULE_ENGINE,
        confidence=0.9,
        intent_ast=ast,
        matched_patterns=["rank_top_n_by_metric", "time_filter"],
    )


def test_ground_rank_revenue_by_grade():
    engine = GroundingEngine()
    intent = _rank_intent()
    nq = NormalizedQuestion(
        original_question="show top 10 grades by revenue this year",
        matching_text="show top 10 grades by revenue this year",
        normalized_question="show top 10 grades by revenue this year",
        recognized_concepts=[
            RecognizedConcept(text="grades", canonical="Grade", category="ENTITY"),
            RecognizedConcept(
                text="revenue", canonical="total_revenue", category="MEASURE"
            ),
            RecognizedConcept(
                text="this year", canonical="THIS_YEAR", category="TIME"
            ),
        ],
    )
    grounded = engine.ground(intent, nq)
    assert grounded.status in {GroundingStatus.VALID, GroundingStatus.PARTIAL}
    assert any(e.concept == "Grade" for e in grounded.entities)
    assert any(e.source_table == "public_grades_master" for e in grounded.entities)
    assert any(m.concept == "total_revenue" for m in grounded.metrics)
    metric = next(m for m in grounded.metrics if m.concept == "total_revenue")
    assert "SUM" in metric.sql_expression.upper()
    assert any("payment" in t for t in grounded.tables)
    assert grounded.time_filters
    assert grounded.time_filters[0].range == "THIS_YEAR"
    # Should find a join path connecting payment/bag world to Grade
    assert grounded.joins


def test_pipeline_run_full_includes_grounding():
    full = Pipeline.from_kb(enable_llm_fallback=False).run_full(
        "show top 10 grds by revnue this yr"
    )
    assert full.clauses
    cr = full.clauses[0]
    assert cr.intent.status == IntentStatus.VALID
    assert cr.grounded is not None
    assert cr.grounded.status in {GroundingStatus.VALID, GroundingStatus.PARTIAL}
    assert any(m.concept == "total_revenue" for m in cr.grounded.metrics)
