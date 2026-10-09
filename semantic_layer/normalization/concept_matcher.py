from __future__ import annotations

from dataclasses import dataclass

from semantic_layer.vocabulary.provider import VocabEntry


@dataclass(frozen=True)
class IndexHit:
    start: int
    end: int
    entry: VocabEntry
    matched_form: str
    score: float = 100.0
    source: str = "exact"  # exact | fuzzy


class VocabularyIndex:
    """Longest-first exact vocabulary matcher built from thin KB entries."""

    def __init__(
        self,
        entries: list[VocabEntry],
        *,
        categories: set[str] | None = None,
    ) -> None:
        forms: dict[str, list[VocabEntry]] = {}
        for entry in entries:
            if categories is not None and entry.category not in categories:
                continue
            surface_forms = {entry.canonical.lower(), *(s.lower() for s in entry.synonyms)}
            if entry.display_form:
                surface_forms.add(entry.display_form.lower())
            for form in surface_forms:
                forms.setdefault(form, [])
                if entry not in forms[form]:
                    forms[form].append(entry)
        self._forms = forms
        self._sorted_forms = sorted(forms.keys(), key=len, reverse=True)
        self.entries = [e for e in entries if categories is None or e.category in categories]

    def surface_forms(self) -> set[str]:
        return set(self._forms.keys())

    def find_exact_matches(
        self,
        text: str,
        *,
        occupied: list[bool] | None = None,
    ) -> list[IndexHit]:
        """Greedy longest exact match; competing canonicals for same form → skip.

        When ``occupied`` is provided, those character spans are already claimed
        (e.g. by a prior ENTITY pass) and are left untouched.
        """
        lower = text.lower()
        n = len(lower)
        used = list(occupied) if occupied is not None else [False] * n
        hits: list[IndexHit] = []

        for form in self._sorted_forms:
            start = 0
            while True:
                idx = lower.find(form, start)
                if idx < 0:
                    break
                end = idx + len(form)
                if not self._is_token_boundary(lower, idx, end):
                    start = idx + 1
                    continue
                if any(used[i] for i in range(idx, end)):
                    start = idx + 1
                    continue
                candidates = self._forms[form]
                unique_canonicals = {c.canonical for c in candidates}
                if len(unique_canonicals) > 1:
                    # Ambiguous — do not guess; leave for Intent.
                    start = end
                    continue
                entry = candidates[0]
                for i in range(idx, end):
                    used[i] = True
                hits.append(
                    IndexHit(
                        start=idx,
                        end=end,
                        entry=entry,
                        matched_form=form,
                        score=100.0,
                        source="exact",
                    )
                )
                start = end

        hits.sort(key=lambda h: h.start)
        return hits

    # Back-compat
    def find_matches(self, text: str) -> list[IndexHit]:
        return self.find_exact_matches(text)

    @staticmethod
    def _is_token_boundary(text: str, start: int, end: int) -> bool:
        before_ok = start == 0 or not text[start - 1].isalnum()
        after_ok = end == len(text) or not text[end].isalnum()
        return before_ok and after_ok
