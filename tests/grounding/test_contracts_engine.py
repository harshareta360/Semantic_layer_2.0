from pathlib import Path

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


def _rank_intent(metric: str = "total_revenue") -> IntentResult:
    ast = QueryNode(
        select=[DimensionRef(concept="Grade"), MetricRef(concept=metric)],
        operations=[
            Rank(
                dimension=DimensionRef(concept="Grade"),
                metric=MetricRef(concept=metric),
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


def _nq() -> NormalizedQuestion:
    return NormalizedQuestion(
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


def test_preferred_path_for_total_revenue():
    engine = GroundingEngine()
    grounded = engine.ground(_rank_intent(), _nq())
    assert grounded.status == GroundingStatus.VALID
    assert "cash_revenue_to_grade" in grounded.applied_path_ids
    pairs = {(j.from_entity, j.to_entity) for j in grounded.joins} | {
        (j.to_entity, j.from_entity) for j in grounded.joins
    }
    assert ("Payment", "AcademicBag") in pairs
    assert ("AcademicBag", "LearnerEnrollment") in pairs
    assert ("LearnerEnrollment", "Grade") in pairs
    assert (
        grounded.time_filters[0].suggested_columns[0]
        == "public_payment_details.created_at"
    )
    assert any("payment_status" in f for f in grounded.default_filters)
    assert all(isinstance(f, str) for f in grounded.default_filters)


def test_no_overlay_falls_back_to_bfs(tmp_path: Path):
    engine = GroundingEngine(contracts_path=tmp_path / "missing.json")
    grounded = engine.ground(_rank_intent(), _nq())
    assert grounded.status in {GroundingStatus.VALID, GroundingStatus.PARTIAL}
    assert grounded.joins
    assert grounded.applied_path_ids == []
    assert grounded.default_filters == []


def test_pipeline_uses_preferred_path():
    full = Pipeline.from_kb(enable_llm_fallback=False).run_full(
        "show top 10 grds by revnue this yr"
    )
    g = full.clauses[0].grounded
    assert g is not None
    assert "cash_revenue_to_grade" in g.applied_path_ids
    assert g.default_filters
