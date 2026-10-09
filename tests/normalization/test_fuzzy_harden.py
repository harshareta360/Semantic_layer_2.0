"""Harden fuzzy matching so common English words are not mapped to KB."""

from semantic_layer.normalization import NormalizationService
from semantic_layer.normalization.fuzzy_corrector import DomainFuzzyCorrector, FuzzyConfig
from semantic_layer.vocabulary import FixtureVocabularyProvider
from semantic_layer.vocabulary.kb_provider import KbVocabularyProvider


def _finance_svc() -> NormalizationService:
    return NormalizationService(KbVocabularyProvider(bo_id="Finance"))


def test_common_words_not_fuzzy_mapped_on_finance():
    nq = _finance_svc().normalize(
        "Label each bag as high medium or low value using net price.",
        bo_id="Finance",
    )
    canons = {c.canonical for c in nq.recognized_concepts}
    assert "Grade" not in canons  # was: as → Grade
    assert "avg_bag_net_value" not in canons  # was: value → avg_bag_net_value


def test_active_and_pay_not_fuzzy_mapped():
    nq = _finance_svc().normalize(
        "How many academic bags are currently active?",
        bo_id="Finance",
    )
    canons = {c.canonical for c in nq.recognized_concepts}
    assert "active_credits_count" not in canons

    nq2 = _finance_svc().normalize(
        "Show payment records that have no pay date.",
        bo_id="Finance",
    )
    canons2 = {c.canonical for c in nq2.recognized_concepts}
    assert "average_payment_amount" not in canons2


def test_real_typos_still_fuzzy_bind():
    nq = NormalizationService(FixtureVocabularyProvider()).normalize(
        "show top 10 grds by revnue"
    )
    canons = {c.canonical for c in nq.recognized_concepts}
    assert "Grade" in canons
    assert "Revenue" in canons


def test_fuzzy_rejects_long_form_for_short_token():
    entries = KbVocabularyProvider(bo_id="Finance").load_entries()
    fz = DomainFuzzyCorrector(entries, FuzzyConfig())
    assert fz.correct("as") is None
    assert fz.correct("pay") is None
    assert fz.correct("active") is None
    assert fz.correct("value") is None
