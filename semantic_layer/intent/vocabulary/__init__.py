"""Intent operator vocabulary helpers."""

from pathlib import Path

import yaml

_PATH = Path(__file__).parent / "intent_vocabulary.yaml"


def load_intent_vocabulary() -> dict:
    return yaml.safe_load(_PATH.read_text(encoding="utf-8")) or {}
