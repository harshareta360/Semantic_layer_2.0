# Normalization + Intent Engine V1 Design

**Date:** 2026-09-21  
**Status:** Approved for implementation

## Scope

Greenfield Python package implementing:

1. Deterministic **Normalization** with `VocabularyProvider` + fixture provider
2. Deterministic **Intent Engine** (pattern catalog + recursive builders + validator)
3. Validated **intent-v1** AST envelope
4. `IntentFallback` Protocol/stub only (no LLM in V1)

Out of scope: Grounding, Query IR, SQLGlot, real LLM fallback, real KB adapter.

## Normalization (updated)

```text
RAW QUESTION
  → 1. Basic cleanup
  → 2. Matching representation (lowercase / spaces)
  → 3. Exact KB vocab match (Entity / Measure)
  → 4. RapidFuzz vs domain vocab only (min_score + min_margin; near-ties rejected)
  → 5. Time phrase normalize
  → 6–7. Surface rewrite + concept attachment
  → 8. Preserve intent words (top / max / count / …)
  → NormalizedQuestion
```

Intent operators are skipped by fuzzy correction. Fillers like `please` are also
skipped by fuzzy matching but may appear in `unresolved_tokens`.


## Data flow

```text
User Question
  → NormalizationService (VocabularyProvider)
  → NormalizedQuestion
  → ConceptBinder
  → PatternCatalog (priority desc, id tie-break)
  → Recursive AST builders → fragment merge
  → Ambiguity check (hard ambiguity wins)
  → ASTValidator
  → ConfidencePolicy
  → IntentResult
```

## Contracts

### NormalizedQuestion

- `original_question`, `normalized_question`, `recognized_concepts`, `unresolved_tokens`
- Domains default to ENTITY; Intent assigns role
- Equal-length vocab ties → leave unresolved
- `display_form` separates canonical concept from readable surface
- Intent operators (`top`, `max`, …) stay in text

### IntentResult

- `schema_version=intent-v1`
- `status`: VALID | AMBIGUOUS | UNSUPPORTED | INVALID
- `parser`: RULE_ENGINE in V1 (CLASSIFIER / LLM_FALLBACK reserved)
- `matched_patterns`: contributing patterns only
- `confidence`: semantic AST confidence, not model probability
- Hard ambiguity always → AMBIGUOUS even if confidence high

### Boundaries

- Normalization does not interpret query operations
- Intent never emits tables, columns, joins, or SQL

## V1 parser families

Aggregate±group, count, rank top/bottom, threshold filters, time filter,
period compare, change/growth, subquery-threshold, ratio/percentage.

Full AST node set exists in schema; unsupported patterns → UNSUPPORTED.
