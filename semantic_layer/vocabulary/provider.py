from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, Field


class VocabEntry(BaseModel):
    """Thin KB vocabulary entry: canonical name + synonyms only."""

    canonical: str
    category: Literal["ENTITY", "MEASURE"]
    synonyms: list[str] = Field(default_factory=list)
    display_form: str | None = None


class VocabularyProvider(Protocol):
    def load_entries(self) -> list[VocabEntry]:
        """Return domain entity/measure vocabulary entries."""
        ...
