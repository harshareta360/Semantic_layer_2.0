"""Only bind concepts when the match is unambiguous / high-confidence."""

from semantic_layer.normalization import NormalizationService
from semantic_layer.vocabulary import FixtureVocabularyProvider
from semantic_layer.vocabulary.kb_provider import KbVocabularyProvider


def _finance() -> NormalizationService:
    return NormalizationService(KbVocabularyProvider(bo_id="Finance"))


def test_academic_bags_binds_entity_not_bag_count():
    nq = _finance().normalize(
        "Show academic bags whose payment is completed.",
        bo_id="Finance",
    )
    canons = {c.canonical for c in nq.recognized_concepts}
    assert "bag_count" not in canons
    assert "AcademicBag" in canons


def test_bag_items_not_forced_to_item_count():
    """'bag items' is measure-only in KB but entity has singular 'bag item' → leave unbound."""
    nq = _finance().normalize(
        "Show bag items with net price above 5000.",
        bo_id="Finance",
    )
    canons = {c.canonical for c in nq.recognized_concepts}
    assert "item_count" not in canons


def test_learners_prefers_entity_not_count_measure():
    nq = _finance().normalize(
        "Show learners whose first name starts with A.",
        bo_id="Finance",
    )
    canons = {c.canonical for c in nq.recognized_concepts}
    assert "learner_count" not in canons
    assert "Learner" in canons


def test_clear_entity_still_binds():
    nq = _finance().normalize(
        "Show each bag with the learner full name.",
        bo_id="Finance",
    )
    canons = {c.canonical for c in nq.recognized_concepts}
    assert "AcademicBag" in canons
    assert "Learner" in canons


def test_fixture_typos_still_bind():
    nq = NormalizationService(FixtureVocabularyProvider()).normalize(
        "show top 10 grds by revnue"
    )
    canons = {c.canonical for c in nq.recognized_concepts}
    assert "Grade" in canons
    assert "Revenue" in canons
