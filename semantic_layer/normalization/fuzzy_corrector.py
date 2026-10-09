from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz, process

from semantic_layer.vocabulary.provider import VocabEntry


@dataclass(frozen=True)
class FuzzyConfig:
    """Configurable RapidFuzz thresholds for domain spelling correction."""

    min_score: float = 80.0
    min_margin: float = 5.0
    # Short common words (as, pay, …) must not fuzzy-map to KB forms.
    min_token_len: int = 4
    # Max |len(form) - len(token)|; no fallback to longer junk matches.
    max_length_delta: int | None = None  # default: max(2, len(token) // 3)


@dataclass(frozen=True)
class FuzzyMatch:
    token: str
    matched_form: str
    entry: VocabEntry
    score: float


class DomainFuzzyCorrector:
    """Fuzzy-correct tokens against KB domain vocabulary only (RapidFuzz).

    Candidates are restricted to short (mostly single-token) surface forms so
    long multi-word synonyms do not dominate WRatio for short typos like 'grds'.
    Exact multi-word matching is handled separately by VocabularyIndex.

    Underscored canonical ids (e.g. ``active_credits_count``) are excluded from
    the fuzzy index — only human-readable single-token forms are candidates.
    """

    def __init__(
        self,
        entries: list[VocabEntry],
        config: FuzzyConfig | None = None,
    ) -> None:
        self._config = config or FuzzyConfig()
        form_to_entries: dict[str, list[VocabEntry]] = {}
        for entry in entries:
            forms = {entry.canonical.lower(), *(s.lower() for s in entry.synonyms)}
            if entry.display_form:
                forms.add(entry.display_form.lower())
            for form in forms:
                form = form.strip()
                if not form:
                    continue
                # Fuzzy index: single-token human forms only
                if " " in form or "_" in form:
                    continue
                if len(form) < 3:
                    continue
                form_to_entries.setdefault(form, [])
                if entry not in form_to_entries[form]:
                    form_to_entries[form].append(entry)
        self._form_to_entries = form_to_entries
        self._forms = list(form_to_entries.keys())

    def correct(self, token: str) -> FuzzyMatch | None:
        """Return a unique domain correction, or None if weak / ambiguous."""
        if not token or not self._forms:
            return None
        query = token.lower()
        if len(query) < self._config.min_token_len:
            return None

        if query in self._form_to_entries:
            entries = self._form_to_entries[query]
            if len({e.canonical for e in entries}) != 1:
                return None
            return FuzzyMatch(
                token=token,
                matched_form=query,
                entry=entries[0],
                score=100.0,
            )

        ranked = process.extract(
            query,
            self._forms,
            scorer=fuzz.WRatio,
            limit=5,
        )
        if not ranked:
            return None

        max_delta = self._config.max_length_delta
        if max_delta is None:
            max_delta = max(2, len(query) // 3)

        length_ok = [
            (form, score, idx)
            for form, score, idx in ranked
            if abs(len(form) - len(query)) <= max_delta
        ]
        # Do NOT fall back to length-mismatched junk (e.g. active → active_credits_count)
        if not length_ok:
            return None
        ranked = length_ok

        best_form, best_score, _ = ranked[0]
        if best_score < self._config.min_score:
            return None

        if len(ranked) > 1:
            second_form, second_score, _ = ranked[1]
            best_canons = {e.canonical for e in self._form_to_entries[best_form]}
            second_canons = {e.canonical for e in self._form_to_entries[second_form]}
            if (
                second_score >= self._config.min_score
                and best_score - second_score < self._config.min_margin
                and best_canons != second_canons
            ):
                return None

        entries = self._form_to_entries[best_form]
        if len({e.canonical for e in entries}) != 1:
            return None

        return FuzzyMatch(
            token=token,
            matched_form=best_form,
            entry=entries[0],
            score=float(best_score),
        )
