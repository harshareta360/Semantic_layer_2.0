from __future__ import annotations

# Intent-adjacent time phrases — NOT domain KB.
# Maps surface phrase → (display phrase, canonical TIME token)
TIME_PHRASES: list[tuple[str, str, str]] = [
    ("this year", "this year", "THIS_YEAR"),
    ("this yr", "this year", "THIS_YEAR"),
    ("last year", "last year", "LAST_YEAR"),
    ("last yr", "last year", "LAST_YEAR"),
    ("this month", "this month", "THIS_MONTH"),
    ("this mnth", "this month", "THIS_MONTH"),
    ("last month", "last month", "LAST_MONTH"),
    ("last mnth", "last month", "LAST_MONTH"),
    ("this quarter", "this quarter", "THIS_QUARTER"),
    ("last quarter", "last quarter", "LAST_QUARTER"),
    ("this week", "this week", "THIS_WEEK"),
    ("last week", "last week", "LAST_WEEK"),
    ("today", "today", "TODAY"),
    ("yesterday", "yesterday", "YESTERDAY"),
    ("year over year", "year over year", "YOY"),
    ("yoy", "year over year", "YOY"),
]

# Re-export for older imports
from semantic_layer.normalization.intent_lexicon import (  # noqa: E402
    INTENT_OPERATORS as INTENT_STOPWORDS,
)


def find_time_spans(text: str) -> list[tuple[int, int, str, str]]:
    """Return (start, end, display, canonical) for time phrases, longest first."""
    lower = text.lower()
    phrases = sorted(TIME_PHRASES, key=lambda p: len(p[0]), reverse=True)
    used = [False] * len(lower)
    results: list[tuple[int, int, str, str]] = []
    for surface, display, canonical in phrases:
        start = 0
        while True:
            idx = lower.find(surface, start)
            if idx < 0:
                break
            end = idx + len(surface)
            if any(used[i] for i in range(idx, end)):
                start = idx + 1
                continue
            before_ok = idx == 0 or not lower[idx - 1].isalnum()
            after_ok = end == len(lower) or not lower[end].isalnum()
            if not (before_ok and after_ok):
                start = idx + 1
                continue
            for i in range(idx, end):
                used[i] = True
            results.append((idx, end, display, canonical))
            start = end
    results.sort(key=lambda r: r[0])
    return results


def pluralize_display(display: str, matched_form: str) -> str:
    """Deterministic plural preservation when matched form looks plural."""
    if matched_form.endswith("s") and not display.endswith("s"):
        if display.endswith("y") and display[-2:] not in ("ay", "ey", "oy", "uy"):
            return display[:-1] + "ies"
        return display + "s"
    return display
