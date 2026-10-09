# Pipeline Module Test Limitations

Living notes from **module-by-module testing** (Finance first, then Logistics).  
Fill each section as that block is tested. Broader product limits: [`LIMITATIONS.md`](LIMITATIONS.md).

**Test set:** `Finance_logistics.xlsx` (50 Finance / 50 Logistics)  
**Order:** Normalization → Intent → Grounding → Query IR → Validate → Execute  

Last updated: 2026-09-23 (Intent P1 + hybrid LLM fallback)

---

## 1. Normalization

**Status:** Finance + Logistics Norm batches done (`bo_id=Finance` / `Logistics`, 50 Q each).

### What it does
- Clean text (lowercase, clause split, time phrases like `this yr` → `THIS_YEAR`)
- Bind **confident** domain concepts from **BO-scoped KB** only
- Does **not** build Intent/SQL

### Choices locked
- **BO-scoped vocab** — Finance run ≠ Logistics concepts (and reverse)
- **No text rewrite** — original words stay; canonical only in concepts
- **Confident-only** — ENTITY first; skip ambiguous / entity-plural lookalike measures
- **Hardened fuzzy** — short/common English not mapped to KB; domain typos only

### Remaining limitations
- **KB synonym clashes** (KB not edited) — e.g. Finance `bags` on entity and `bag_count` → prefer entity or leave unbound
- **Unresolved English is normal** — `paid`, `name`, `date`, `amount`, … left for Intent
- **Conservative binds** — e.g. Finance `academic bags` → `AcademicBag` (not `bag_count`); `bag items` / Logistics `order items` not forced to count measures
- **Unique measure synonyms still bind** when KB has a single clear mapping
- **Some questions get zero / thin concepts** — Intent must work from text (Finance had several; Logistics mainly `Q46` shipped_at/delivered_at)
- **Typos bind in metadata, not in string** — `grds` stays `grds`, concept = `Grade`
- **Verb-like synonyms** (Logistics) — e.g. `ordered` can bind `LogisticsOrder`; Intent must not over-read that

### Examples
1. Finance: `Show academic bags whose payment is completed.` → `AcademicBag` (not `bag_count`)
2. Logistics: `Show logistics shipments that have been delivered.` → `LogisticsShipment`; no Finance bag/payment concepts  
   Cross-check: **0 Finance concept leaks** on Logistics batch; **0 Logistics leaks** on Finance batch

---

## 2. Intent

**Status:** Finance + Logistics Intent re-tested after **P0 + P1 patterns** and **hybrid LLM fallback** (Groq when rules miss).

### What it does
- Bind Norm concepts → AST slots
- Match NL against YAML pattern catalog → `intent-v1` AST (deterministic first)
- If status ≠ `VALID` → optional **LLM fallback** fills the **same** `intent-v1` AST (validated)
- Status: `VALID` / `UNSUPPORTED` / `AMBIGUOUS` / `INVALID`

### Batch results (Excel 50+50)
| Mode | Finance VALID | Logistics VALID | Combined VALID |
|------|--------------:|----------------:|---------------:|
| Rules only (pre-P0) | 14/50 (28%) | 4/50 (8%) | 18/100 (18%) |
| Rules only (P0) | 32/50 (64%) | 24/50 (48%) | 56/100 (56%) |
| Rules only (P0+P1) | **36/50 (72%)** | **25/50 (50%)** | **61/100 (61%)** |
| Hybrid rules+LLM | **40/50 (80%)** | **28/50 (56%)** | **68/100 (68%)** |

Hybrid note: 61 stayed `RULE_ENGINE`; 39 escalated to `LLM_FALLBACK` → +7 VALID. Remaining miss = hard windows/set/CASE, thin Norm concepts, or LLM still UNSUPPORTED/INVALID.

### What works now (deterministic)
- List/retrieve (+ pull/fetch/return), distinct
- WHERE: thresholds / between / equality / null / LIKE
- Sort cues + newest/oldest first
- Relative `last N days`
- Rank: top/bottom N, cheapest/expensive, **which … highest/lowest**
- Group having: `with more than N` (count)
- Count, aggregates (± by), time, ratio / compare / change / subquery-vs-average

### Hybrid LLM (architecture path)
- Escalates on **UNSUPPORTED / AMBIGUOUS / INVALID** only (never overrides VALID rules)
- Prompt includes rule-engine prior (errors / ambiguities / patterns)
- Must emit `intent-v1` + pass `AstValidator`; no free SQL
- Requires `GROQ_API_KEY`; demo UI uses `enable_llm_fallback=True` when key present

### Remaining limitations
- P2/P3 gaps: windows, set ops, CASE, hard joins/subqueries
- Norm/KB thin metrics still block some rule slots (`amount`, some `payment` phrasings)
- LLM can still return UNSUPPORTED / INVALID / rare AMBIGUOUS
- AST schema still wider than patterns implement

### Examples
1. Finance `Q17` VALID (rules): Top 5 bags by net price → `rank_top_n_by_metric`
2. Finance `Q03` VALID (rules): Show bags whose payment is completed → list + equality
3. Hard window / set-ops: often still UNSUPPORTED (rules + sometimes LLM)

---

## 3. Grounding

**Status:** Not tested yet in this cycle.

### What it does
- *(fill)*

### Choices locked
- *(fill)*

### Remaining limitations
- *(fill)*

### Examples
- *(fill)*

---

## 4. Query IR + SQL render

**Status:** Not tested yet in this cycle.

### What it does
- *(fill)*

### Choices locked
- *(fill)*

### Remaining limitations
- *(fill)*

### Examples
- *(fill)*

---

## 5. SQL validate

**Status:** Not tested yet in this cycle.

### What it does
- *(fill)*

### Choices locked
- *(fill)*

### Remaining limitations
- *(fill)*

### Examples
- *(fill)*

---

## 6. Execute (Postgres)

**Status:** Not tested yet in this cycle.

### What it does
- *(fill)*

### Choices locked
- *(fill)*

### Remaining limitations
- *(fill)*

### Examples
- *(fill)*

---

## Cross-cutting (optional)

- Generic vs BO/KB config
- Demo UI / `pipeline.py` gaps
- *(add as needed)*
