from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RecognizedConcept(BaseModel):
    text: str
    canonical: str
    category: Literal["ENTITY", "MEASURE", "DIMENSION", "TIME", "OTHER"]
    start: int | None = None
    end: int | None = None
    confidence: float = 1.0


class AmbiguousCandidate(BaseModel):
    """Reserved for fuzzy ambiguity reporting (roadmap step 3)."""

    canonical: str
    score: float
    matched_form: str | None = None


class NormalizedClause(BaseModel):
    """One independently normalized clause from a (possibly multi-part) question."""

    clause_index: int
    original_clause: str
    matching_text: str
    normalized_question: str
    recognized_concepts: list[RecognizedConcept] = Field(default_factory=list)
    unresolved_tokens: list[str] = Field(default_factory=list)
    ambiguous_candidates: list[AmbiguousCandidate] = Field(default_factory=list)


class NormalizedQuestion(BaseModel):
    original_question: str
    matching_text: str = ""
    normalized_question: str
    clauses: list[NormalizedClause] = Field(default_factory=list)
    # Flat aggregates for single-clause back-compat / convenience
    recognized_concepts: list[RecognizedConcept] = Field(default_factory=list)
    unresolved_tokens: list[str] = Field(default_factory=list)
