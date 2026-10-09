# Pipeline Flow Guide

End-to-end deterministic flow for **Normalization + Intent + Grounding V1**.

```text
RAW USER QUESTION
        │
        ▼
┌───────────────────┐
│  NORMALIZATION    │
└───────────────────┘
        │
        ▼
  NormalizedQuestion
        │
        ▼
┌───────────────────┐
│  INTENT ENGINE    │
└───────────────────┘
        │
        ▼
    IntentResult
   (intent-v1 AST)
        │
        ▼
┌───────────────────┐
│  GROUNDING        │
└───────────────────┘
        │
        ▼
  GroundedContext
 (tables / joins / SQL exprs)
        │
        ▼
┌───────────────────┐
│  QUERY IR         │
└───────────────────┘
        │
        ▼
   QueryIRResult
 (+ sql_preview)
```

SQLGlot / DB execute are **out of scope** for this milestone.

See also: [`LIMITATIONS.md`](LIMITATIONS.md) for a full list of V1 limits (including multi-question / `?` handling).

### Domain vocabulary source

Normalization’s thin KB layer is loaded from project-root **[`kb_k21.yml`](../kb_k21.yml)** via `KbVocabularyProvider` / `Pipeline.from_kb()`:

- `entities` → `ENTITY`
- `measures` → `MEASURE` (e.g. `total_revenue` with synonym `revenue`)

Grounding loads the **full** KB slice: entities, measures, dimensions, and relationships. The loader maps `kb_k21.yml` into the internal shape those stages already read.

Execution-oriented overlay (optional): project-root **[`grounding_contracts.json`](../grounding_contracts.json)** — metric contracts + preferred entity join paths. Spec: [`superpowers/specs/2026-09-21-grounding-contracts-overlay-design.md`](superpowers/specs/2026-09-21-grounding-contracts-overlay-design.md).

Business Object scope (explicit): project-root **[`business_objects.json`](../business_objects.json)** — Finance / Logistics table+column allow-lists. Pass `bo_id` into `Pipeline.run_full(..., bo_id="Finance")`. Spec: [`superpowers/specs/2026-09-21-bo-scoped-grounding-design.md`](superpowers/specs/2026-09-21-bo-scoped-grounding-design.md).

---

## Running example (same question through every step)

**Input (raw):**

```text
show me top 10 grds having max revnue in this yr please
```

---

# Part A — Normalization

Normalization answers: *“What did the user say — cleaned and canonicalized?”*  
It does **not** decide ranking, aggregation, or SQL.

## Step 1 — Basic text cleanup + clause split

| | |
|---|---|
| **Does** | Lowercase; keep `?` `!` `;` `.` in `matching_text`; split into `clauses[]`; strip punct only for vocab matching inside each clause |
| **Does not** | Fix domain typos yet, attach concepts, interpret `top`/`max` |

**Multi-question example:**

```text
Input: What is the total revenue? Show top 10 grades by revenue

matching_text: "what is the total revenue? show top 10 grades by revenue"

clauses:
  [0] original: "What is the total revenue?"
  [1] original: "Show top 10 grades by revenue"
```

Each clause is normalized independently; `Pipeline.run_all` / multi-clause `run` parses Intent per clause.

**Input:**

```text
show me top 10 grds having max revnue in this yr please
```

**Output (matching representation):**

```text
show me top 10 grds having max revnue in this yr please
```

(Already clean in this example; punctuation like `?` / `,` would be removed.)

---

## Step 2 — Exact KB vocabulary match

| | |
|---|---|
| **Does** | Longest exact match against Entity/Measure names + synonyms from `VocabularyProvider` |
| **Does not** | Fuzzy guess; match Intent words (`top`, `max`, …) |

Fixture example synonyms:

- Grade → `grade`, `grades`, `grd`, `grds`, …
- Revenue → `revenue`, `rev`, `revnue`, …

**If `grds` / `revnue` are listed as synonyms → exact hit here.**  
**If not listed → they fall through to Step 3 (RapidFuzz).**

Exact hits occupy those character spans so later steps don't re-match them.

---

## Step 3 — Fuzzy spelling correction (RapidFuzz)

| | |
|---|---|
| **Does** | For remaining tokens, fuzzy-match **only against domain KB forms** |
| **Skips** | Intent / filler tokens: `top`, `max`, `having`, `please`, `show`, … |
| **Rejects** | Score &lt; `min_score` (default 80), or near-tie within `min_margin` (default 5) |

**Example (typo not in synonym list):**

```text
token "gradse"  → RapidFuzz vs [grade, grades, revenue, …]  → Grade
token "revenu"  → → Revenue
token "top"     → skipped (intent)
token "xyzabc"  → no confident match → stays unresolved
```

Configurable:

```python
from semantic_layer.normalization import NormalizationService, FuzzyConfig

NormalizationService(vocab, fuzzy_config=FuzzyConfig(min_score=80, min_margin=5))
```

---

## Step 4 — Time expression normalize

| | |
|---|---|
| **Does** | Map time phrases via a fixed time map (not domain KB) |
| **Examples** | `this yr` → `this year` + `THIS_YEAR`; `last mnth` → `last month` + `LAST_MONTH` |

**Input span:** `this yr`  
**Output span:** `this year`  
**Concept:**

```json
{
  "text": "this year",
  "canonical": "THIS_YEAR",
  "category": "TIME"
}
```

---

## Step 5–6 — Surface rewrite + concept attachment

Matched domain spans are rewritten to preferred `display_form` (with simple plural rules), and structured concepts are attached.

| Raw span | Display surface | Canonical | Category |
|----------|-----------------|-----------|----------|
| `grds` / `gradse` | `grades` | `Grade` | `ENTITY` |
| `revnue` / `revenu` | `revenue` | `Revenue` | `MEASURE` |
| `this yr` | `this year` | `THIS_YEAR` | `TIME` |

---

## Step 7 — Preserve everything else

These stay in the sentence unchanged for the Intent Engine:

```text
top   max   having   please   10   show   me   …
```

---

## Normalization output

**Final `NormalizedQuestion`:**

```json
{
  "original_question": "show me top 10 grds having max revnue in this yr please",
  "normalized_question": "show me top 10 grades having max revenue in this year please",
  "recognized_concepts": [
    {
      "text": "grades",
      "canonical": "Grade",
      "category": "ENTITY",
      "confidence": 1.0
    },
    {
      "text": "revenue",
      "canonical": "Revenue",
      "category": "MEASURE",
      "confidence": 1.0
    },
    {
      "text": "this year",
      "canonical": "THIS_YEAR",
      "category": "TIME",
      "confidence": 1.0
    }
  ],
  "unresolved_tokens": ["please"]
}
```

Notes:

- `please` is **not** a domain concept → `unresolved_tokens` (not an error).
- `top` / `max` / `having` are Intent operators → preserved in text, not unresolved.
- Fuzzy matches may have `confidence` &lt; 1.0 (score / 100).

### Code

```python
from semantic_layer.normalization import NormalizationService
from semantic_layer.vocabulary import FixtureVocabularyProvider

norm = NormalizationService(FixtureVocabularyProvider())
nq = norm.normalize("show me top 10 grds having max revnue in this yr please")
print(nq.normalized_question)
print(nq.recognized_concepts)
```

---

# Part B — Intent Engine

Intent answers: *“What operations does the user want?”*  
It does **not** map tables/columns or generate SQL.

## Step 1 — Concept binder

| Recognized concept | Bound as (role assigned by pattern later) |
|--------------------|-------------------------------------------|
| Grade / ENTITY | can become `DIMENSION_REF("Grade")` in RANK |
| Revenue / MEASURE | `METRIC_REF("Revenue")` |
| THIS_YEAR / TIME | `TIME_FILTER(THIS_YEAR)` |

Canonical names stay semantic — never `public_grades.name`.

---

## Step 2 — Pattern catalog match

YAML patterns, sorted by **priority desc**, then **pattern id**.  
Only **contributing** pattern ids are recorded on the result.

Example matches for our question:

| Pattern id | Meaning |
|------------|---------|
| `rank_top_n_by_metric` | TOP N + BY metric |
| `time_filter` | this year |

`max` in “having max revenue” may also trigger aggregation patterns; the engine keeps complementary fragments and treats hard conflicts as `AMBIGUOUS`.

---

## Step 3 — Recursive AST builders + merge

Each match builds a **semantic fragment**; compatible fragments merge into one `QUERY`.

Example merge:

```text
RANK(Grade, Revenue, DESC, 10)
+ TIME_FILTER(THIS_YEAR)
        ↓
QUERY
  select: [Grade, Revenue]
  operations: [RANK(...)]
  where: TIME_FILTER(THIS_YEAR)
  limit: 10
```

Conflict (e.g. two different limits) → `AMBIGUOUS`, `intent_ast = null`.

---

## Step 4 — Validate + confidence → IntentResult

| Status | Meaning |
|--------|---------|
| `VALID` | Usable AST |
| `AMBIGUOUS` | Multiple interpretations / merge conflict (hard ambiguity wins over high confidence) |
| `UNSUPPORTED` | No V1 pattern covers it (e.g. window function) |
| `INVALID` | AST failed validation |

**Example `IntentResult` (shape):**

```json
{
  "schema_version": "intent-v1",
  "status": "VALID",
  "confidence": 0.96,
  "parser": "RULE_ENGINE",
  "matched_patterns": ["rank_top_n_by_metric", "time_filter"],
  "ambiguities": [],
  "errors": [],
  "intent_ast": {
    "type": "QUERY",
    "select": [
      {"type": "DIMENSION_REF", "concept": "Grade"},
      {"type": "METRIC_REF", "concept": "Revenue"}
    ],
    "where": {"type": "TIME_FILTER", "range": "THIS_YEAR"},
    "limit": 10,
    "operations": [
      {
        "type": "RANK",
        "dimension": {"type": "DIMENSION_REF", "concept": "Grade"},
        "metric": {"type": "METRIC_REF", "concept": "Revenue"},
        "direction": "DESC",
        "limit": 10
      }
    ]
  }
}
```

### Code (full pipeline)

```python
from semantic_layer.pipeline import Pipeline

pipeline = Pipeline.from_fixtures()
result = pipeline.run("show me top 10 grds having max revnue in this yr please")

print(result.status)
print(result.matched_patterns)
print(result.intent_ast)
```

---

# Part C — Grounding

Grounding answers: *“Which physical tables, joins, and SQL expressions back this Intent AST?”*  
It does **not** emit final SQL or Query IR.

## Step 1 — Walk Intent AST concepts

Collect every `ENTITY_REF` / `DIMENSION_REF` / `METRIC_REF` concept, plus `TIME_FILTER` ranges. Soft-merge `NormalizedQuestion.recognized_concepts` (non-TIME).

## Step 2 — Deterministic KB lookup

| Concept kind | KB source | Grounded output |
|--------------|-----------|-----------------|
| Entity | `semantic.entities` | `source_table`, PK, columns, display column |
| Metric | `metrics` (preferred) or `semantic.measures` | `sql_expression`, dependencies |
| Dimension | `semantic.dimensions` | column + owning entity |
| Time | AST `TIME_FILTER` + `column_hints` | suggested date columns |

Unresolved concepts → `unresolved_concepts` and status `PARTIAL` / `FAILED`.

## Step 3 — Join path (preferred contracts, else relationship BFS)

If `grounding_contracts.json` defines a `preferred_path_id` for a grounded metric, materialize joins along that **entity chain**, resolving each consecutive edge from `semantic.relationships`.

Otherwise BFS over relationships among involved entities (bridge entities allowed). Conflicting preferred path ids → `PARTIAL`.

## Step 4 — Time + default_filters (metadata)

Contract `default_time_column` becomes the primary `suggested_columns[0]`.  
Contract `default_filters` are attached to `GroundedContext.default_filters` for later IR — **not** executed as SQL in Grounding.

## Step 5 — Rules & join guidance (keyword filter)

Score `kb.rules` and `kb.join_paths` by keyword overlap with tables/concepts; attach top hits as guidance for later IR/SQL (not executed here).

## Overlay file

Project-root [`grounding_contracts.json`](../grounding_contracts.json) (optional). Missing file → V1 BFS-only behavior. `kb_k21.yml` stays the knowledge source.

## Step 0 — Business Object scope (optional but recommended)

Caller passes `bo_id` (`Finance` | `Logistics`) from [`business_objects.json`](../business_objects.json). Grounding loads only KB entities/metrics/relationships whose tables are in that BO. Unknown `bo_id` → `FAILED`. Omit `bo_id` → unscoped full KB (backward compatible).

```python
full = Pipeline.from_kb(enable_llm_fallback=False).run_full(
    "show top 10 grds by revnue this yr",
    bo_id="Finance",
)
```

## Grounding output (shape)

```json
{
  "status": "VALID",
  "entities": [
    {"concept": "Grade", "source_table": "public_grades_master", "primary_key": "id"}
  ],
  "metrics": [
    {
      "concept": "total_revenue",
      "sql_expression": "SUM(pd.amount::numeric)",
      "dependencies": ["payment_details.amount", "…"],
      "source": "metrics"
    }
  ],
  "joins": [
    {"from_entity": "Payment", "to_entity": "AcademicBag", "on": "…"}
  ],
  "time_filters": [
    {"range": "THIS_YEAR", "suggested_columns": ["payment_details.created_at"]}
  ],
  "tables": ["payment_details", "public_grades_master", "…"],
  "applied_path_ids": ["cash_revenue_to_grade"],
  "default_filters": ["public_payment_details.payment_status::integer = 3"],
  "rules": ["…"],
  "join_guidance": ["…"]
}
```

### Code

```python
from semantic_layer.pipeline import Pipeline

full = Pipeline.from_kb(enable_llm_fallback=False).run_full(
    "show top 10 grds by revnue this yr"
)
print(full.clauses[0].grounded.status)
print(full.clauses[0].grounded.tables)
```

Demo script: project-root [`pipeline.py`](../pipeline.py) prints Normalization + Intent + Grounding + Query IR.

---

# Part D — Query IR

IR answers: *“Assemble the grounded pieces into one executable plan.”*  
It does **not** rediscover joins or invent metric SQL.

- Pure `QueryIR` (from / joins / select / where / group_by / order / limit)
- Wrapped in `QueryIRResult` (`status`, `ir`, `sql_preview`, `errors`)
- `from` ← `GroundedContext.base_entity`; joins ← `grounded.joins`; metric expr ← `grounded.metrics[].sql_expression`
- `THIS_YEAR` → half-open `date_trunc` range on primary time column
- Thin Postgres `sql_preview` via **SQLGlot** (`render_sql`); string preview is fallback only
- Specs: [`query-ir`](superpowers/specs/2026-09-22-query-ir-v1-design.md) · [`sqlglot`](superpowers/specs/2026-09-22-sqlglot-renderer-v1-design.md)

---

## Boundaries (do not mix)

| Layer | Owns | Does not own |
|-------|------|----------------|
| **Normalization** | Cleanup, domain spelling, time phrases, concepts | Query meaning of `top`/`max`, SQL |
| **Intent** | RANK / AGG / FILTER / … AST | Tables, columns, joins, SQL |
| **Grounding** | Tables, columns, joins, metric SQL exprs from KB | Final SQL / dialects / execution |
| **Query IR** | Assemble grounded plan | DB execute |
| **SQLGlot renderer** | Dialect SQL from QueryIR | Inventing joins/metrics |
| **Domain vocab** | Per DB / KB via `VocabularyProvider` | — |
| **Intent vocab** | Shared across databases (`top`, `max`, …) | — |

---

## More examples

| Raw input | Normalized text (approx.) | Intent (approx.) |
|-----------|---------------------------|------------------|
| `What is the total revenue?` | `what is the total revenue` | `AGGREGATE(SUM, Revenue)` |
| `total revenue by grade` | same + concepts | `SUM(Revenue) GROUP BY Grade` |
| `Show the maximum revenue by grade.` | … | often `AMBIGUOUS` (MAX vs ranking) |
| `Rank grades using a complex window function…` | … | `UNSUPPORTED` |

Golden regression set: `tests/fixtures/golden_questions.json` (~100 cases).
