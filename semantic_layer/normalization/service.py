from __future__ import annotations

import re
from pathlib import Path

from semantic_layer.normalization.clause_splitter import split_clauses
from semantic_layer.normalization.concept_matcher import IndexHit, VocabularyIndex
from semantic_layer.normalization.fuzzy_corrector import DomainFuzzyCorrector, FuzzyConfig
from semantic_layer.normalization.intent_lexicon import (
    INTENT_OPERATORS,
    is_fuzzy_skip_token,
)
from semantic_layer.normalization.models import (
    NormalizedClause,
    NormalizedQuestion,
    RecognizedConcept,
)
from semantic_layer.normalization.text_cleanup import for_vocab_match, to_matching_text
from semantic_layer.normalization.time_phrases import find_time_spans
from semantic_layer.vocabulary.kb_provider import KbVocabularyProvider
from semantic_layer.vocabulary.provider import VocabularyProvider

_TOKEN_RE = re.compile(r"[a-zA-Z']+|\d+")


class NormalizationService:
    """Domain-aware Normalization: clauses → exact KB → RapidFuzz → time → rewrite.

    When constructed from ``KbVocabularyProvider`` (or ``kb_path``), pass ``bo_id``
    to ``normalize`` so only that business object's vocab is used.
    """

    def __init__(
        self,
        vocabulary: VocabularyProvider | None = None,
        fuzzy_config: FuzzyConfig | None = None,
        *,
        kb_path: Path | str | None = None,
        bo_path: Path | str | None = None,
    ) -> None:
        self._fuzzy_config = fuzzy_config
        self._bo_path = Path(bo_path) if bo_path is not None else None
        self._kb_path: Path | None = None
        self._static_provider: VocabularyProvider | None = None

        if vocabulary is not None and isinstance(vocabulary, KbVocabularyProvider):
            self._kb_path = vocabulary._path  # noqa: SLF001 — scoped reloads
            self._bo_path = vocabulary._bo_path or self._bo_path  # noqa: SLF001
            # If provider already pinned a BO, treat as static scoped vocab.
            if vocabulary._bo_id is not None:  # noqa: SLF001
                self._static_provider = vocabulary
        elif vocabulary is not None:
            self._static_provider = vocabulary
        elif kb_path is not None:
            self._kb_path = Path(kb_path)
        else:
            self._kb_path = None
            self._static_provider = KbVocabularyProvider()

        self._cache: dict[
            str | None,
            tuple[VocabularyIndex, VocabularyIndex, DomainFuzzyCorrector, set[str]],
        ] = {}

        # Eager default (unscoped or static) so existing call sites keep working
        (
            self._entity_index,
            self._measure_index,
            self._fuzzy,
            self._entity_forms,
        ) = self._engines(None)

    def _engines(
        self, bo_id: str | None
    ) -> tuple[VocabularyIndex, VocabularyIndex, DomainFuzzyCorrector, set[str]]:
        if bo_id in self._cache:
            return self._cache[bo_id]

        if self._static_provider is not None and (
            bo_id is None or not isinstance(self._static_provider, KbVocabularyProvider)
        ):
            entries = self._static_provider.load_entries()
        elif self._kb_path is not None or isinstance(
            self._static_provider, KbVocabularyProvider
        ):
            path = self._kb_path
            if path is None and isinstance(self._static_provider, KbVocabularyProvider):
                path = self._static_provider._path  # noqa: SLF001
            entries = KbVocabularyProvider(
                path, bo_id=bo_id, bo_path=self._bo_path
            ).load_entries()
        else:
            entries = KbVocabularyProvider(bo_id=bo_id, bo_path=self._bo_path).load_entries()

        entity_index = VocabularyIndex(entries, categories={"ENTITY", "DIMENSION"})
        measure_index = VocabularyIndex(entries, categories={"MEASURE"})
        fuzzy = DomainFuzzyCorrector(entries, config=self._fuzzy_config)
        entity_forms = entity_index.surface_forms()
        packed = (entity_index, measure_index, fuzzy, entity_forms)
        self._cache[bo_id] = packed
        return packed

    def normalize(
        self, question: str, *, bo_id: str | None = None
    ) -> NormalizedQuestion:
        (
            self._entity_index,
            self._measure_index,
            self._fuzzy,
            self._entity_forms,
        ) = self._engines(bo_id)
        # Back-compat attribute used by older helpers/tests
        self._index = self._entity_index

        matching_text = to_matching_text(question)
        raw_parts = split_clauses(question)
        if not raw_parts:
            raw_parts = [question.strip()] if question.strip() else [""]

        clauses: list[NormalizedClause] = []
        for idx, original_clause in enumerate(raw_parts):
            clauses.append(self._normalize_clause(idx, original_clause))

        # Flat aggregates (back-compat): merge concepts / unresolved; join surfaces
        all_concepts: list[RecognizedConcept] = []
        all_unresolved: list[str] = []
        seen_u: set[str] = set()
        for clause in clauses:
            all_concepts.extend(clause.recognized_concepts)
            for tok in clause.unresolved_tokens:
                if tok not in seen_u:
                    seen_u.add(tok)
                    all_unresolved.append(tok)

        joined = " ".join(c.normalized_question for c in clauses).strip()

        return NormalizedQuestion(
            original_question=question,
            matching_text=matching_text,
            normalized_question=joined,
            clauses=clauses,
            recognized_concepts=all_concepts,
            unresolved_tokens=all_unresolved,
        )

    @staticmethod
    def _measure_uncertain_vs_entity(form: str, entity_forms: set[str]) -> bool:
        """True when a MEASURE surface looks like a plural/variant of an ENTITY form.

        In that case we do not commit the measure — Intent should decide.
        """
        form = form.lower().strip()
        if not form:
            return False
        if form in entity_forms:
            return True
        candidates: list[str] = []
        if form.endswith("ies") and len(form) > 3:
            candidates.append(form[:-3] + "y")
        if form.endswith("es") and len(form) > 2:
            candidates.append(form[:-2])
        if form.endswith("s") and len(form) > 1:
            candidates.append(form[:-1])
        if " " in form:
            parts = form.split()
            last = parts[-1]
            if last.endswith("ies") and len(last) > 3:
                candidates.append(" ".join(parts[:-1] + [last[:-3] + "y"]))
            if last.endswith("es") and len(last) > 2:
                candidates.append(" ".join(parts[:-1] + [last[:-2]]))
            if last.endswith("s") and len(last) > 1:
                candidates.append(" ".join(parts[:-1] + [last[:-1]]))
        return any(c in entity_forms for c in candidates)

    def _normalize_clause(self, index: int, original_clause: str) -> NormalizedClause:
        matching = to_matching_text(original_clause)
        # Vocab / fuzzy / time operate on punctuation-stripped matching text
        cleaned = for_vocab_match(matching)
        occupied = [False] * len(cleaned)
        replacements: list[tuple[int, int, str]] = []
        concepts: list[RecognizedConcept] = []

        # 1) Confident ENTITY hits first
        for hit in self._entity_index.find_exact_matches(cleaned, occupied=occupied):
            self._commit_domain_hit(cleaned, hit, occupied, replacements, concepts)

        # 2) MEASURE only on free spans, and only if not an entity-plural lookalike
        for hit in self._measure_index.find_exact_matches(cleaned, occupied=occupied):
            if self._measure_uncertain_vs_entity(hit.matched_form, self._entity_forms):
                continue
            self._commit_domain_hit(cleaned, hit, occupied, replacements, concepts)

        # 3) Fuzzy on remaining tokens — skip uncertain measure lookalikes
        for start, end, token in self._iter_tokens(cleaned):
            if any(occupied[i] for i in range(start, end)):
                continue
            if token.isdigit() or is_fuzzy_skip_token(token):
                continue
            match = self._fuzzy.correct(token)
            if match is None:
                continue
            if match.entry.category == "MEASURE" and self._measure_uncertain_vs_entity(
                match.matched_form, self._entity_forms
            ):
                continue
            hit = IndexHit(
                start=start,
                end=end,
                entry=match.entry,
                matched_form=match.matched_form,
                score=match.score,
                source="fuzzy",
            )
            self._commit_domain_hit(cleaned, hit, occupied, replacements, concepts)

        for start, end, display, canonical in find_time_spans(cleaned):
            if any(occupied[i] for i in range(start, end)):
                continue
            for i in range(start, end):
                occupied[i] = True
            replacements.append((start, end, display))
            concepts.append(
                RecognizedConcept(
                    text=display,
                    canonical=canonical,
                    category="TIME",
                    start=start,
                    end=end,
                    confidence=1.0,
                )
            )

        normalized = self._apply_replacements(cleaned, replacements)
        unresolved = self._collect_unresolved(normalized, concepts)
        concepts.sort(key=lambda c: (c.start is None, c.start or 0))

        return NormalizedClause(
            clause_index=index,
            original_clause=original_clause.strip(),
            matching_text=matching,
            normalized_question=normalized,
            recognized_concepts=concepts,
            unresolved_tokens=unresolved,
            ambiguous_candidates=[],
        )

    def _commit_domain_hit(
        self,
        text: str,
        hit: IndexHit,
        occupied: list[bool],
        replacements: list[tuple[int, int, str]],
        concepts: list[RecognizedConcept],
    ) -> None:
        if any(occupied[i] for i in range(hit.start, hit.end)):
            return
        # Keep the original surface in normalized text; canonical lives in metadata.
        original = text[hit.start : hit.end]
        for i in range(hit.start, hit.end):
            occupied[i] = True
        # No-op replacement preserves spans for bookkeeping consistency with time hits
        replacements.append((hit.start, hit.end, original))
        confidence = 1.0 if hit.source == "exact" else min(1.0, hit.score / 100.0)
        concepts.append(
            RecognizedConcept(
                text=original,
                canonical=hit.entry.canonical,
                category=hit.entry.category,
                start=hit.start,
                end=hit.end,
                confidence=confidence,
            )
        )

    @staticmethod
    def _iter_tokens(text: str) -> list[tuple[int, int, str]]:
        return [(m.start(), m.end(), m.group(0)) for m in _TOKEN_RE.finditer(text)]

    @staticmethod
    def _apply_replacements(text: str, replacements: list[tuple[int, int, str]]) -> str:
        if not replacements:
            return text
        parts: list[str] = []
        last = 0
        for start, end, surface in sorted(replacements, key=lambda r: r[0]):
            parts.append(text[last:start])
            parts.append(surface)
            last = end
        parts.append(text[last:])
        return re.sub(r"\s+", " ", "".join(parts)).strip()

    @staticmethod
    def _collect_unresolved(
        normalized: str, concepts: list[RecognizedConcept]
    ) -> list[str]:
        known_surfaces = {c.text.lower() for c in concepts}
        known_canonicals = {c.canonical.lower() for c in concepts}
        covered_tokens: set[str] = set()
        for surface in known_surfaces:
            for part in _TOKEN_RE.findall(surface):
                covered_tokens.add(part.lower())

        unresolved: list[str] = []
        seen: set[str] = set()
        for tok in _TOKEN_RE.findall(normalized):
            low = tok.lower()
            if low.isdigit():
                continue
            if low in INTENT_OPERATORS:
                continue
            if low in known_surfaces or low in known_canonicals or low in covered_tokens:
                continue
            if low.endswith("s") and low[:-1] in known_surfaces:
                continue
            if low not in seen:
                seen.add(low)
                unresolved.append(low)
        return unresolved
