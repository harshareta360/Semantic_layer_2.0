from __future__ import annotations

from typing import Protocol

from semantic_layer.intent.models.result import IntentResult
from semantic_layer.normalization.models import NormalizedQuestion


class IntentFallback(Protocol):
    def parse(
        self,
        normalized_question: NormalizedQuestion,
        schema_version: str = "intent-v1",
        *,
        prior: IntentResult | None = None,
    ) -> IntentResult:
        """Produce IntentResult using the same intent-v1 contract.

        ``prior`` is the deterministic rule-engine result (UNSUPPORTED /
        AMBIGUOUS / INVALID) so the LLM can resolve with context.
        """
        ...


class StubIntentFallback:
    """Stub — raises unless a real LLM fallback is wired."""

    def parse(
        self,
        normalized_question: NormalizedQuestion,
        schema_version: str = "intent-v1",
        *,
        prior: IntentResult | None = None,
    ) -> IntentResult:
        raise NotImplementedError("LLM IntentFallback not enabled")
