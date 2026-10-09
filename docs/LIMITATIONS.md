# Limitations (V1)

Known limits of the current **Normalization + Intent + Grounding** milestone.  
These are intentional or deferred — not silent bugs (unless noted).

Last updated: 2026-09-21

---

## 1. Pipeline scope

| Limitation | Detail |
|------------|--------|
| ~~No Grounding~~ | **Added:** deterministic `GroundingEngine` resolves entities/metrics/joins from `kb.json` → `GroundedContext` |
| ~~No Query IR~~ | **Added:** `compile_query_ir` → pure `QueryIR` + `QueryIRResult` (+ thin Postgres `sql_preview`) |
| ~~No SQLGlot~~ | **Added:** `render_sql` via SQLGlot (postgres); thin `to_sql_postgres` is fallback only |
| No end-to-end execute | No database execution, retry, or repair loop |
| Stub LLM fallback only | **Updated:** Groq Intent fallback is available when `GROQ_API_KEY` is set; rules still run first. LLM must emit `intent-v1` and pass `AstValidator`. Grounding has **no** LLM path. |

**Stops at:** validated SQL + optional Postgres execute (demo UI Validate / Execute).

---

## 2. Normalization — text & punctuation

| Limitation | Detail |
|------------|--------|
| ~~Punctuation is destroyed~~ | **Improved:** `matching_text` retains `?` `!` `;` `.` for splitting; vocab match uses a punct-stripped view |
| ~~No multi-question split~~ | **Improved:** clauses split on `?` `!` `;` → `NormalizedQuestion.clauses[]`; Intent via `Pipeline.run_all` / multi `run` |
| No clause segmentation on “also / and then” | Conjunction-based splits not implemented yet |
| Lowercase-only matching | Casing is not preserved in the matching representation |
| No general English spellcheck | RapidFuzz runs **only** against domain KB forms, not a full dictionary |
| No grammar / NLP parse | No dependency parse, NER model, or lemmatizer library beyond our rules |

**Example (now):**

```text
Input:  What is total revenue? Show top 10 grades by revenue
→ Clause 1: "What is total revenue?"
→ Clause 2: "Show top 10 grades by revenue"
→ each normalized + Intent-parsed independently
```

---

## 3. Normalization — vocabulary & spelling

| Limitation | Detail |
|------------|--------|
| Fixture KB by default | Demo unit tests may use `domain_vocab.json`; **runtime default is project `kb.json`** via `Pipeline.from_kb()` / `KbVocabularyProvider` |
| Thin slice of KB only | Normalization loads `semantic.entities`, `semantic.measures`, and `metrics` (+ synonyms). It does **not** load rules, joins, dimensions, SQL maps, or few-shots |
| Fuzzy needs enough signal | Typos too far from any form (`xyzabc`) stay unresolved |
| Near-tie rejection | Two domain candidates within `min_margin` → **no** correction (safe, but may leave typos) |
| Thresholds are heuristic | Default `min_score=80`, `min_margin=5` are not calibrated per tenant |
| Intent lexicon is curated | `top` / `max` / `please` / … are a maintained list, not learned |
| Fillers vs operators | `please` can appear in `unresolved_tokens`; operators usually do not |
| Plural rules are simple | Deterministic `-s` / `-ies` heuristics only |
| Multi-word domain phrases | Exact/fuzzy is primarily token-oriented; complex multi-word entity names may need synonyms listed |
| Time map is fixed | Only listed phrases (`this yr`, `last mnth`, …); arbitrary dates like `2023-01-15` are not fully modeled as TIME concepts in Normalization |
| Language | English-oriented tokens and patterns only |

---

## 4. Intent Engine — coverage

| Limitation | Detail |
|------------|--------|
| Schema ≠ parser | Full `intent-v1` node types exist (e.g. `WINDOW`, `EXISTS`); V1 **patterns** do not cover all of them |
| Unsupported → status | Window-style / uncovered asks return `UNSUPPORTED`, not a guessed AST |
| Pattern catalog is finite | New phrasings need new YAML patterns + builders |
| English pattern bias | Patterns assume English-like order (`top N … by …`) |
| Nested language limits | Recursive AST is supported in the model; only some nestings (e.g. “greater than the average”) are wired in V1 |
| “Maximum … by …” ambiguity | Rules → `AMBIGUOUS`; with LLM fallback on, Groq may resolve to a VALID AST |
| Multi-intent questions | Combined asks (total + top-N in one string) are not cleanly decomposed |
| No dialogue / context | No follow-ups, pronouns (“that metric”), or session memory |
| No classifier path | `parser` may be `RULE_ENGINE` or `LLM_FALLBACK`; classifier path still unused |

---

## 5. Intent Engine — semantics & validation

| Limitation | Detail |
|------------|--------|
| Confidence is not probability | Score reflects rule/pattern strength, not a calibrated model probability |
| No business-rule validation | Intent does not know metric definitions or allowed grain |
| Physical IDs rejected | Correct for Intent; real mapping must wait for Grounding |
| ENTITY vs DIMENSION | Normalization usually emits `ENTITY`; Intent assigns dimension role by pattern — may be wrong for edge phrasings |
| Limited set operations / CASE / WINDOW | Present in schema; little or no V1 parsing into those nodes |

---

## 6. Data & tenancy

| Limitation | Detail |
|------------|--------|
| One fixture domain | Academic-style sample (Grade, Revenue, Learner, …) |
| Per-DB vocab not wired | `VocabularyProvider` Protocol is ready; production KB adapter not shipped |
| Intent vocab is global | Shared across DBs (by design); cannot yet customize per tenant without code/config change |
| No auth / tenancy in pipeline | Orchestrator is single-tenant in-process |

---

## 7. Observability & ops

| Limitation | Detail |
|------------|--------|
| Minimal structured logging | Relies on `matched_patterns` / status on `IntentResult`; no metrics/tracing export |
| Snapshot / golden suite | ~100 golden questions — not a full production query log |
| No A/B or shadow LLM | Cannot compare rule AST vs LLM AST in V1 |

---

## 8. Grounding — resolution limits

| Limitation | Detail |
|------------|--------|
| Deterministic only | No LLM / fuzzy grounding; missing KB entries stay unresolved |
| ~~Join BFS is only strategy~~ | **Improved:** `grounding_contracts.json` preferred entity paths; BFS is fallback when overlay missing or no contract |
| Metric aliases as tables | Dependency strings that are bare table names are collected into `tables`, not always as entity nodes (contracts reduce reliance on this) |
| Rules / join_paths are guidance | Keyword-ranked text; not validated SQL and not applied automatically |
| Time columns | Contract `default_time_column` is preferred; otherwise suggestions from hints — still not a proven calendar filter predicate |
| `default_filters` are metadata | Attached to `GroundedContext` for IR; **not** interpreted/executed inside Grounding |
| BO scope is explicit | Pass `bo_id`; no automatic BO/table picker. Unknown id → FAILED. Omit → unscoped full KB |
| No SQL assembly | Full SELECT / dialect / SQLGlot is deferred to Query IR |

---

## 9. Deliberate non-goals (do not “fix” inside Intent)

- Emitting SQL strings or dialect keywords in the AST  
- Inventing joins or metric formulas not present in `kb.json`  
- Guessing when fuzzy or patterns are ambiguous  

---

## Likely next upgrades (not done)

1. ~~Multi-question / clause splitter~~ → **Done** (`clauses[]`, see FLOW / NORMALIZATION_ROADMAP)
2. ~~Grounding (tables / joins / metric SQL)~~ → **Done** (`GroundingEngine` / `Pipeline.run_full`)
3. ~~Preferred join paths + metric contracts overlay~~ → **Done** (`grounding_contracts.json`)
4. ~~BO-scoped grounding (explicit `bo_id`)~~ → **Done** (`business_objects.json`)
5. Phrase-aware domain matching (longest phrase first)
6. Fuzzy `ambiguous_candidates` + length-aware thresholds
7. Richer date/time normalize
8. Morphology (match-only) + observability
9. ~~Query IR + thin SQL preview~~ → **Done** (`semantic_layer/ir`)
10. ~~SQLGlot dialect SQL~~ → **Done** (`sqlglot_renderer.py`, postgres default)
11. ~~SQL validate + Postgres execute~~ → **Done** (`semantic_layer/execute`)
12. Repair loop / richer schema EXPLAIN checks

---

## Related docs

- [`FLOW.md`](FLOW.md) — step-by-step happy path with examples  
- [`README.md`](../README.md) — setup and quick start  
- [`superpowers/specs/2026-09-21-normalization-intent-v1-design.md`](superpowers/specs/2026-09-21-normalization-intent-v1-design.md) — locked design  
