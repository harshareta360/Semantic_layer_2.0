from pathlib import Path

from semantic_layer.vocabulary.kb_provider import KbVocabularyProvider, extract_vocab_entries


def test_kb_file_loads():
    provider = KbVocabularyProvider()
    entries = provider.load_entries()
    assert len(entries) > 20
    canons = {e.canonical for e in entries}
    assert "Grade" in canons
    assert "Learner" in canons
    assert "total_revenue" in canons
    # revenue is a synonym of total_revenue
    rev = next(e for e in entries if e.canonical == "total_revenue")
    assert any("revenue" == s.lower() for s in rev.synonyms)


def test_kb_entities_are_entity_category():
    entries = KbVocabularyProvider().load_entries()
    grade = next(e for e in entries if e.canonical == "Grade")
    assert grade.category == "ENTITY"
    assert grade.display_form


def test_normalization_uses_kb_revenue_synonym():
    from semantic_layer.normalization import NormalizationService

    nq = NormalizationService(KbVocabularyProvider()).normalize(
        "show me top 10 grades by revenue this year please"
    )
    canons = {c.canonical for c in nq.recognized_concepts}
    assert "Grade" in canons
    assert "total_revenue" in canons
    assert "THIS_YEAR" in canons
    assert "revenue" in nq.normalized_question
    assert "please" in nq.unresolved_tokens
    # Surface stays as spoken ("revenue"); canonical is total_revenue on the concept
    assert any(c.canonical == "total_revenue" for c in nq.recognized_concepts)


def test_pipeline_from_kb():
    from semantic_layer.intent.models.enums import IntentStatus
    from semantic_layer.pipeline import Pipeline

    result = Pipeline.from_kb().run("show top 10 grades by revenue")
    assert result.status == IntentStatus.VALID
    assert "rank_top_n_by_metric" in result.matched_patterns
