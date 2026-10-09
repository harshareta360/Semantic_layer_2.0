from semantic_layer.normalization import NormalizationService
from semantic_layer.normalization.fuzzy_corrector import DomainFuzzyCorrector, FuzzyConfig
from semantic_layer.vocabulary import FixtureVocabularyProvider, VocabEntry


def _svc(fuzzy: FuzzyConfig | None = None) -> NormalizationService:
    return NormalizationService(FixtureVocabularyProvider(), fuzzy_config=fuzzy)


def test_typo_and_time_normalization():
    result = _svc().normalize("show me top 10 grds having max revnue in this yr please")
    # Typos stay in text; canonicals live on recognized_concepts
    assert "grds" in result.normalized_question
    assert "revnue" in result.normalized_question
    assert "this year" in result.normalized_question  # time phrases still expand
    canons = {c.canonical for c in result.recognized_concepts}
    assert "Grade" in canons
    assert "Revenue" in canons
    assert "THIS_YEAR" in canons
    assert "please" in result.unresolved_tokens
    assert "top" in result.normalized_question
    assert "max" in result.normalized_question


def test_entity_not_forced_to_dimension():
    result = _svc().normalize("total revenue by grade")
    grade = next(c for c in result.recognized_concepts if c.canonical == "Grade")
    assert grade.category == "ENTITY"


def test_display_form_not_rewritten():
    """Fuzzy hit records canonical Grade but keeps original typo surface."""
    result = _svc().normalize("grds")
    assert result.normalized_question == "grds"
    assert result.recognized_concepts[0].canonical == "Grade"
    assert result.recognized_concepts[0].text == "grds"


def test_unresolved_is_not_error():
    result = _svc().normalize("show revenue please")
    assert "please" in result.unresolved_tokens
    assert any(c.canonical == "Revenue" for c in result.recognized_concepts)


def test_fuzzy_corrects_typo_not_in_synonym_list():
    """Typos absent from synonyms still bind via RapidFuzz; surface text unchanged."""
    result = _svc().normalize("total revenu by gradse")
    assert "revenu" in result.normalized_question
    assert "gradse" in result.normalized_question
    canons = {c.canonical for c in result.recognized_concepts}
    assert "Revenue" in canons
    assert "Grade" in canons


def test_fuzzy_does_not_correct_intent_words():
    result = _svc().normalize("top max count having please")
    assert result.normalized_question == "top max count having please"
    assert result.recognized_concepts == []
    assert "please" in result.unresolved_tokens


def test_fuzzy_rejects_low_score():
    result = _svc(FuzzyConfig(min_score=95, min_margin=5)).normalize("xyzabc")
    assert "xyzabc" in result.normalized_question
    assert result.recognized_concepts == []
    assert "xyzabc" in result.unresolved_tokens


def test_fuzzy_near_tie_rejected_when_margin_large():
    entries = [
        VocabEntry(
            canonical="Alpha",
            category="ENTITY",
            synonyms=["alpha"],
            display_form="alpha",
        ),
        VocabEntry(
            canonical="Alpho",
            category="ENTITY",
            synonyms=["alpho"],
            display_form="alpho",
        ),
    ]
    # Large margin forces near-ties to be rejected
    corrector = DomainFuzzyCorrector(entries, FuzzyConfig(min_score=50, min_margin=30))
    assert corrector.correct("alph") is None


def test_time_mnth_alias():
    result = _svc().normalize("total revenue last mnth")
    assert "last month" in result.normalized_question
    assert any(c.canonical == "LAST_MONTH" for c in result.recognized_concepts)


def test_pipeline_still_works_with_fuzzy():
    from semantic_layer.intent.models.enums import IntentStatus
    from semantic_layer.pipeline import Pipeline

    result = Pipeline.from_fixtures().run("show top 10 gradse by revenu this yr")
    assert result.status == IntentStatus.VALID
    assert "rank_top_n_by_metric" in result.matched_patterns
