"""BO-scoped vocabulary for Normalization."""

from semantic_layer.normalization import NormalizationService
from semantic_layer.pipeline import Pipeline
from semantic_layer.vocabulary.kb_provider import KbVocabularyProvider


def test_finance_vocab_excludes_logistics_concepts():
    canons = {e.canonical for e in KbVocabularyProvider(bo_id="Finance").load_entries()}
    assert "AcademicBag" in canons
    assert "BagItem" in canons
    assert "Learner" in canons
    assert "Grade" in canons
    assert "LogisticsOrder" not in canons
    assert "LogisticsShipment" not in canons
    assert "LogisticsOrderItem" not in canons
    assert "avg_days_to_deliver" not in canons


def test_logistics_vocab_excludes_finance_bag_concepts():
    canons = {e.canonical for e in KbVocabularyProvider(bo_id="Logistics").load_entries()}
    assert "LogisticsOrder" in canons
    assert "LogisticsShipment" in canons
    assert "AcademicBag" not in canons
    assert "BagItem" not in canons
    assert "bag_count" not in canons
    assert "total_bag_net_value" not in canons


def test_normalize_with_finance_bo_skips_logistics_order_word():
    nq = NormalizationService(KbVocabularyProvider(bo_id="Finance")).normalize(
        "Number each payment in date order for every learner."
    )
    canons = {c.canonical for c in nq.recognized_concepts}
    assert "LogisticsOrder" not in canons
    assert "LogisticsShipment" not in canons
    assert "Learner" in canons


def test_pipeline_run_full_scopes_normalization_by_bo_id():
    pipe = Pipeline.from_kb(enable_llm_fallback=False)
    result = pipe.run_full(
        "Number each payment in date order for every learner.",
        bo_id="Finance",
    )
    canons = {c.canonical for c in result.normalized.recognized_concepts}
    assert "LogisticsOrder" not in canons
    assert "LogisticsShipment" not in canons
