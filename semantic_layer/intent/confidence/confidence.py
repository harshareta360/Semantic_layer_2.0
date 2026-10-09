from __future__ import annotations

from dataclasses import dataclass

from semantic_layer.intent.models.enums import IntentStatus


@dataclass
class ConfidencePolicy:
    """Semantic AST confidence thresholds (not model probability)."""

    accept: float = 0.90
    review: float = 0.70

    def apply(
        self,
        confidence: float,
        *,
        has_hard_ambiguity: bool,
        validation_errors: list[str],
        has_ast: bool,
        unsupported: bool = False,
    ) -> IntentStatus:
        if has_hard_ambiguity:
            return IntentStatus.AMBIGUOUS
        if unsupported:
            return IntentStatus.UNSUPPORTED
        if validation_errors:
            return IntentStatus.INVALID
        if not has_ast:
            return IntentStatus.UNSUPPORTED
        if confidence < self.review:
            return IntentStatus.AMBIGUOUS
        if confidence < self.accept:
            # Mid band: still accept if AST validated (extra deterministic pass done upstream)
            return IntentStatus.VALID
        return IntentStatus.VALID
