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
        ],
    )


def test_finance_scopes_revenue_path():
    grounded = GroundingEngine().ground(_rank_intent(), _nq(), bo_id="Finance")
    assert grounded.bo_id == "Finance"
    assert grounded.status == GroundingStatus.VALID
    assert "cash_revenue_to_grade" in grounded.applied_path_ids
    assert "public_payment_details" in grounded.tables
    assert all(not t.startswith("public_logistics") for t in grounded.tables)


def test_logistics_excludes_finance_metric():
    grounded = GroundingEngine().ground(_rank_intent(), _nq(), bo_id="Logistics")
    assert grounded.bo_id == "Logistics"
    assert grounded.status in {GroundingStatus.PARTIAL, GroundingStatus.FAILED}
    assert "total_revenue" in grounded.unresolved_concepts
    assert "public_payment_details" not in grounded.tables
    assert grounded.applied_path_ids == []


def test_unknown_bo_fails():
    grounded = GroundingEngine().ground(_rank_intent(), _nq(), bo_id="Marketing")
    assert grounded.status == GroundingStatus.FAILED
    assert grounded.bo_id == "Marketing"
    assert grounded.errors


def test_pipeline_with_bo_id():
    full = Pipeline.from_kb(enable_llm_fallback=False).run_full(
        "show top 10 grds by revnue this yr",
        bo_id="Finance",
    )
    assert full.bo_id == "Finance"
    g = full.clauses[0].grounded
    assert g is not None
    assert g.bo_id == "Finance"
    assert g.status == GroundingStatus.VALID
