from __future__ import annotations

from semantic_layer.intent.builder.ast_builder import AstBuilder
from semantic_layer.intent.builder.concept_binder import ConceptBinder
from semantic_layer.intent.builder.fragment_merger import FragmentMerger
from semantic_layer.intent.confidence.confidence import ConfidencePolicy
from semantic_layer.intent.fallback.llm_fallback import IntentFallback
from semantic_layer.intent.models.enums import IntentStatus, ParserSource
from semantic_layer.intent.models.result import IntentResult
from semantic_layer.intent.parser.pattern_matcher import PatternCatalog
from semantic_layer.intent.validator.ast_validator import AstValidator
from semantic_layer.normalization.models import NormalizedQuestion


class IntentEngine:
    """Deterministic Intent Engine with optional Groq LLM fallback."""

    def __init__(
        self,
        pattern_catalog: PatternCatalog | None = None,
        validator: AstValidator | None = None,
        confidence_policy: ConfidencePolicy | None = None,
        fallback: IntentFallback | None = None,
        *,
        use_llm_fallback: bool = True,
    ) -> None:
        self._catalog = pattern_catalog or PatternCatalog()
        self._binder = ConceptBinder()
        self._builder = AstBuilder()
        self._merger = FragmentMerger()
        self._validator = validator or AstValidator()
        self._confidence = confidence_policy or ConfidencePolicy()
        self._fallback = fallback
        self._use_llm_fallback = use_llm_fallback

    def parse(self, normalized_question: NormalizedQuestion) -> IntentResult:
        deterministic = self._parse_deterministic(normalized_question)
        if deterministic.status == IntentStatus.VALID:
            return deterministic
        if not self._use_llm_fallback or self._fallback is None:
            return deterministic
        # Escalate when rules are UNSUPPORTED, AMBIGUOUS, or INVALID.
        return self._fallback.parse(normalized_question, prior=deterministic)

    def _parse_deterministic(self, normalized_question: NormalizedQuestion) -> IntentResult:
        bindings = self._binder.bind(normalized_question)
        matches = self._catalog.match(normalized_question, bindings)

        if not matches:
            return IntentResult(
                status=IntentStatus.UNSUPPORTED,
                confidence=0.0,
                parser=ParserSource.RULE_ENGINE,
                intent_ast=None,
                matched_patterns=[],
                errors=["no patterns matched"],
            )

        selected = self._select_matches(matches)
        fragments = [self._builder.build_fragment(m, bindings) for m in selected]
        merged = self._merger.merge(fragments)

        has_hard_ambiguity = bool(merged.ambiguities)
        if has_hard_ambiguity:
            return IntentResult(
                status=IntentStatus.AMBIGUOUS,
                confidence=merged.confidence or 0.58,
                parser=ParserSource.RULE_ENGINE,
                intent_ast=None,
                matched_patterns=[],
                ambiguities=merged.ambiguities,
            )

        if merged.unsupported or merged.query is None:
            return IntentResult(
                status=IntentStatus.UNSUPPORTED,
                confidence=0.0,
                parser=ParserSource.RULE_ENGINE,
                intent_ast=None,
                matched_patterns=merged.contributing_patterns,
                errors=["unsupported intent pattern"],
            )

        errors = self._validator.validate(merged.query)
        status = self._confidence.apply(
            merged.confidence,
            has_hard_ambiguity=False,
            validation_errors=errors,
            has_ast=True,
            unsupported=False,
        )

        return IntentResult(
            status=status,
            confidence=merged.confidence,
            parser=ParserSource.RULE_ENGINE,
            intent_ast=merged.query if status == IntentStatus.VALID else None,
            matched_patterns=merged.contributing_patterns,
            ambiguities=[],
            errors=errors,
        )

    @staticmethod
    def _select_matches(matches: list) -> list:
        for m in matches:
            if m.builder == "unsupported_window":
                return [m]

        complementary = {
            "time_filter",
            "relative_time_filter",
            "threshold_filter",
            "between_filter",
            "equality_filter",
            "null_filter",
            "like_filter",
            "order_by_metric",
        }
        primary = {
            "rank",
            "aggregate",
            "aggregate_group",
            "count",
            "compare",
            "change",
            "subquery_threshold",
            "ratio",
            "list_entity",
            "group_count_threshold",
        }
        selected = []
        seen_primary = False
        for m in sorted(matches, key=lambda x: (-x.priority, x.pattern_id)):
            if m.builder in complementary:
                selected.append(m)
                continue
            if m.builder in primary:
                # One primary only (priority wins) — avoids rank vs aggregate AMBIGUOUS.
                if seen_primary:
                    continue
                seen_primary = True
                selected.append(m)
                continue
            selected.append(m)
        return selected
