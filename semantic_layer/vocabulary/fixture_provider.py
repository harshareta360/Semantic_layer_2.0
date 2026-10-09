from __future__ import annotations

import json
from pathlib import Path

from semantic_layer.vocabulary.provider import VocabEntry, VocabularyProvider

_DEFAULT_FIXTURE = Path(__file__).parent / "fixtures" / "domain_vocab.json"


class FixtureVocabularyProvider:
    """Load thin domain vocabulary from a JSON fixture file."""

    def __init__(self, path: Path | str | None = None) -> None:
        self._path = Path(path) if path else _DEFAULT_FIXTURE

    def load_entries(self) -> list[VocabEntry]:
        data = json.loads(self._path.read_text(encoding="utf-8"))
        return [VocabEntry.model_validate(item) for item in data]


# Satisfy Protocol statically
_: VocabularyProvider = FixtureVocabularyProvider()  # type: ignore[assignment]
