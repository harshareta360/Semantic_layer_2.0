from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from semantic_layer.grounding.engine import GroundingEngine
from semantic_layer.grounding.models import GroundedContext
from semantic_layer.intent.fallback.groq_fallback import GroqIntentFallback
from semantic_layer.intent.models.result import IntentResult
from semantic_layer.intent.service import IntentEngine
from semantic_layer.ir import QueryIRResult, compile_query_ir
from semantic_layer.llm.groq_client import GroqLLMClient
from semantic_layer.normalization.models import NormalizedClause, NormalizedQuestion
from semantic_layer.normalization.service import NormalizationService
from semantic_layer.vocabulary.fixture_provider import FixtureVocabularyProvider
from semantic_layer.vocabulary.kb_provider import KbVocabularyProvider

load_dotenv()


def clause_as_normalized_question(
    clause: NormalizedClause,
    original_question: str,
) -> NormalizedQuestion:
    """Wrap a single clause so IntentEngine can parse it in isolation."""
    return NormalizedQuestion(
        original_question=original_question,
        matching_text=clause.matching_text,
        normalized_question=clause.normalized_question,
        clauses=[clause],
        recognized_concepts=list(clause.recognized_concepts),
        unresolved_tokens=list(clause.unresolved_tokens),
    )


class ClauseResult(BaseModel):
    """One clause through normalize → intent → grounding → IR."""

    clause: NormalizedClause
    intent: IntentResult
    grounded: GroundedContext | None = None
    ir: QueryIRResult | None = None


class PipelineResult(BaseModel):
    original_question: str
    bo_id: str | None = None
    normalized: NormalizedQuestion
    clauses: list[ClauseResult] = Field(default_factory=list)


class Pipeline:
    """normalize → intent → grounding."""

    def __init__(
        self,
        normalization: NormalizationService,
        intent: IntentEngine,
        grounding: GroundingEngine | None = None,
    ) -> None:
        self.normalization = normalization
        self.intent = intent
        self.grounding = grounding

    @classmethod
    def from_kb(
        cls,
        path: Path | str | None = None,
        *,
        enable_llm_fallback: bool = True,
    ) -> Pipeline:
        """Default: thin vocab + grounding from project kb_k21.yml."""
        vocab = KbVocabularyProvider(path)
        return cls(
            normalization=NormalizationService(vocab, kb_path=path),
            intent=cls._build_intent(enable_llm_fallback=enable_llm_fallback),
            grounding=GroundingEngine(kb_path=path),
        )

    @classmethod
    def from_fixtures(cls, *, enable_llm_fallback: bool = False) -> Pipeline:
        """Fixture vocab for unit tests; grounding still uses kb_k21.yml if present."""
        vocab = FixtureVocabularyProvider()
        grounding = None
        try:
            grounding = GroundingEngine()
        except FileNotFoundError:
            grounding = None
        return cls(
            normalization=NormalizationService(vocab),
            intent=cls._build_intent(enable_llm_fallback=enable_llm_fallback),
            grounding=grounding,
        )

    @staticmethod
    def _build_intent(*, enable_llm_fallback: bool) -> IntentEngine:
        fallback = None
        if enable_llm_fallback:
            client = GroqLLMClient()
            if client.configured:
                fallback = GroqIntentFallback(client=client)
        return IntentEngine(
            fallback=fallback,
            use_llm_fallback=bool(fallback),
        )

    def run_full(self, question: str, *, bo_id: str | None = None) -> PipelineResult:
        """Full path: Normalization + Intent + Grounding per clause.

        Pass ``bo_id`` (e.g. ``\"Finance\"`` / ``\"Logistics\"``) to scope
        Normalization vocabulary and Grounding to that business object's tables.
        """
        normalized = self.normalization.normalize(question, bo_id=bo_id)
        clauses = normalized.clauses or [
            NormalizedClause(
                clause_index=0,
                original_clause=question,
                matching_text=normalized.matching_text,
                normalized_question=normalized.normalized_question,
                recognized_concepts=normalized.recognized_concepts,
                unresolved_tokens=normalized.unresolved_tokens,
            )
        ]
        results: list[ClauseResult] = []
        for clause in clauses:
            nq = clause_as_normalized_question(clause, normalized.original_question)
            intent = self.intent.parse(nq)
            grounded = None
            ir = None
            if self.grounding is not None and intent.intent_ast is not None:
                grounded = self.grounding.ground(intent, nq, bo_id=bo_id)
                ir = compile_query_ir(intent, grounded)
            results.append(
                ClauseResult(clause=clause, intent=intent, grounded=grounded, ir=ir)
            )
        return PipelineResult(
            original_question=question,
            bo_id=bo_id,
            normalized=normalized,
            clauses=results,
        )

    def run_all(self, question: str, *, bo_id: str | None = None) -> list[IntentResult]:
        """Normalize and parse **each clause** independently (intent only)."""
        return [c.intent for c in self.run_full(question, bo_id=bo_id).clauses]

    def run(
        self, question: str, *, bo_id: str | None = None
    ) -> IntentResult | list[IntentResult]:
        """Single-clause → one IntentResult; multi-clause → list[IntentResult]."""
        results = self.run_all(question, bo_id=bo_id)
        return results[0] if len(results) == 1 else results
