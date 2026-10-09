"""Keep original surface text when recording vocab matches (no display rewrite)."""

from semantic_layer.normalization import NormalizationService
from semantic_layer.vocabulary.kb_provider import KbVocabularyProvider


def test_exact_match_keeps_original_words_not_display_form():
    nq = NormalizationService(KbVocabularyProvider(bo_id="Finance")).normalize(
        "Show academic bags whose payment is completed.",
        bo_id="Finance",
    )
    low = nq.normalized_question.lower()
    assert "academic bags" in low
    assert "bag count" not in low
    assert "bag counts" not in low
    hit = next(c for c in nq.recognized_concepts if c.canonical == "AcademicBag")
    assert "bag" in hit.text.lower()
    assert hit.category == "ENTITY"


def test_fuzzy_match_keeps_typo_surface_but_records_canonical():
    from semantic_layer.vocabulary import FixtureVocabularyProvider

    nq = NormalizationService(FixtureVocabularyProvider()).normalize("grds")
    assert nq.normalized_question == "grds"
    assert nq.recognized_concepts[0].canonical == "Grade"
    assert nq.recognized_concepts[0].text == "grds"
