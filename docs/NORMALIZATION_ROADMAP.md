# Normalization Improvement Roadmap

Locked improvement track for the Normalization layer.  
Intent remains responsible for query operations (`top` / `max` / …).

**Architectural rule:** Normalization preserves structure, corrects language safely, recognizes domain concepts, and normalizes time — it does **not** interpret analytical intent.

---

## Already done

| Item | Status |
|------|--------|
| RapidFuzz domain-only spelling correction | Done |
| Real KB thin vocabulary (`KbVocabularyProvider` ← `kb.json`) | Done — entities, measures, metrics |
| Intent/filler lexicon separate from domain KB | Done |
| Preserve punctuation + clause splitting (`clauses[]`) | Done |

---

## Ordered roadmap

```text
V1 Current
   ↓
1. Preserve punctuation + clause splitting          ✅ Done
   ↓
2. Phrase-aware domain matching
   ↓
3. Better fuzzy matching + candidate reporting
   ↓
4. Rich date/time normalization
   ↓
5. Morphology improvements (match-only)
   ↓
6. Observability + threshold calibration
   ↓
7. Optional general English spellcheck (later, gated)
```

---

## 1. Punctuation preserve + clause splitting — High priority

**Problem:** `?` is destroyed; multi-part questions flatten into one string.

**Target flow:**

```text
Raw Question
  → Sentence / Clause Splitter (uses punctuation)
  → Clause 1, Clause 2, …
  → Normalize each independently
```

**Example:**

```text
"What is total revenue? Show top 10 grades by revenue"
→ Clause 1: "What is total revenue?"
→ Clause 2: "Show top 10 grades by revenue"
```

**Contract change:**

```python
class NormalizedClause(BaseModel):
    clause_index: int
    original_clause: str
    normalized_question: str
    recognized_concepts: list[RecognizedConcept]
    unresolved_tokens: list[str] = []
    ambiguous_candidates: list[AmbiguousCandidate] = []  # from step 3

class NormalizedQuestion(BaseModel):
    original_question: str
    matching_text: str          # lowercase; punctuation retained for split metadata
    normalized_question: str    # joined or primary; see notes
    clauses: list[NormalizedClause]
    # retain flat fields for back-compat / single-clause case
    recognized_concepts: list[RecognizedConcept] = []
    unresolved_tokens: list[str] = []
```

**Two representations:**

| Field | Role |
|-------|------|
| `original_question` / `original_clause` | User-facing, punctuation intact |
| `matching_text` | Lowercased; punctuation kept for splitting, ignored during vocab char-span match |

Pipeline/Intent should eventually accept **one clause at a time** (or a list of IntentResults).

---

## 2. Phrase-aware domain matching — High priority

**Order (longest-match-first):**

```text
Exact phrase match
  → Exact token match
  → Fuzzy phrase match
  → Fuzzy token match
```

Supports multi-word KB surfaces: `academic bag`, `net revenue`, `admission conversion`, `payment status`.

More important than general English spellcheck.

---

## 3. Better fuzzy + ambiguity reporting — High priority

```text
Exact
  → Fuzzy candidates
  → min_score
  → min_margin
  → length-aware threshold (short tokens stricter)
  → accept | ambiguous | unresolved
```

**Do not add SymSpell yet.**

Ambiguous output (no silent guess):

```json
{
  "text": "rev",
  "ambiguous_candidates": [
    {"canonical": "total_revenue", "score": 91},
    {"canonical": "avg_payment", "score": 89}
  ]
}
```

| Outcome | Meaning |
|---------|---------|
| clear | attach canonical concept |
| ambiguous | `ambiguous_candidates` |
| unknown | `unresolved_tokens` |

---

## 4. Richer date/time — High priority

Expand beyond fixed phrases (`this yr`, `last mnth`) to:

- relative: last 3 months, this/last quarter  
- absolute: January 2026, Jan 2026, 2026-01-15  
- ranges: between January and March, from Jan 1 to Mar 31  

**Semantic output only** (no DB column):

```json
{
  "category": "TIME",
  "canonical": "DATE_RANGE",
  "value": { "...": "structured range" }
}
```

Optional `dateparser` later, behind strict allowlists.

---

## 5. Morphology (match-only)

Lightweight plurals/inflection for **matching** (`grade` ↔ `grades`).  
Do not aggressively rewrite user wording beyond preferred `display_form`.

---

## 6. Observability

Log per token/span:

- original token  
- match type: `EXACT` / `FUZZY` / `TIME` / `PHRASE`  
- candidates, score, margin  
- accepted / rejected / ambiguous  
- canonical  

Used to calibrate `min_score` / `min_margin` from benchmarks.

---

## Explicitly NOT in Normalization

| Item | Where it belongs |
|------|------------------|
| General English spellcheck | Optional later fallback only |
| Intent operators (`top`, `max`, `count`, …) | Intent lexicon |
| Dialogue / session context | Future conversation layer |
| Tables, joins, SQL, metric formulas | Grounding |

---

## Implementation note for Intent

After clause splitting, Prefer:

```text
for clause in normalized.clauses:
    intent.parse(clause_as_normalized_question)
```

rather than one Intent AST for a multi-question blob.
