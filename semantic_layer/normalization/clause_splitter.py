from __future__ import annotations

import re

# Split after clause terminators when followed by whitespace.
_CLAUSE_SPLIT_RE = re.compile(r"(?<=[?!;])\s+")


def split_clauses(text: str) -> list[str]:
    """Split a question into clauses using ? ! ; delimiters.

    Punctuation stays on the preceding clause when present.
    If no delimiter is found, returns a single clause.
    """
    text = text.strip()
    if not text:
        return []
    parts = _CLAUSE_SPLIT_RE.split(text)
    return [p.strip() for p in parts if p.strip()]
