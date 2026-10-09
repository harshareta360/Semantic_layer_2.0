from __future__ import annotations

import re

_WHITESPACE_RE = re.compile(r"\s+")
# Keep sentence / clause delimiters for splitting; drop other punctuation noise.
_NON_CLAUSE_PUNCT_RE = re.compile(r"[^\w\s'\-?!;.]+")
_VOCAB_PUNCT_RE = re.compile(r"[?!;.,]+")


def to_matching_text(text: str) -> str:
    """Lowercase + collapse spaces; preserve ? ! ; . for clause splitting."""
    cleaned = text.strip().lower()
    cleaned = _NON_CLAUSE_PUNCT_RE.sub(" ", cleaned)
    cleaned = _WHITESPACE_RE.sub(" ", cleaned).strip()
    return cleaned


def for_vocab_match(text: str) -> str:
    """Strip sentence punctuation for vocabulary / fuzzy matching spans."""
    cleaned = _VOCAB_PUNCT_RE.sub(" ", text)
    cleaned = _WHITESPACE_RE.sub(" ", cleaned).strip()
    return cleaned


def basic_cleanup(text: str) -> str:
    """Back-compat single-blob cleanup (no clause punct retained)."""
    return for_vocab_match(to_matching_text(text))
