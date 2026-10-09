from semantic_layer.intent.confidence import ConfidencePolicy
from semantic_layer.intent.models.enums import IntentStatus


def test_hard_ambiguity_wins_over_high_confidence():
    policy = ConfidencePolicy()
    status = policy.apply(
        0.93,
        has_hard_ambiguity=True,
        validation_errors=[],
        has_ast=True,
    )
    assert status == IntentStatus.AMBIGUOUS


def test_validation_errors_mean_invalid():
    policy = ConfidencePolicy()
    status = policy.apply(
        0.99,
        has_hard_ambiguity=False,
        validation_errors=["bad"],
        has_ast=True,
    )
    assert status == IntentStatus.INVALID


def test_unsupported_flag():
    policy = ConfidencePolicy()
    status = policy.apply(
        0.0,
        has_hard_ambiguity=False,
        validation_errors=[],
        has_ast=False,
        unsupported=True,
    )
    assert status == IntentStatus.UNSUPPORTED
