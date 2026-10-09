# Grounding Contracts Overlay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (inline) or superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `grounding_contracts.json` overlay so Grounding resolves metric entities, preferred join paths, primary time columns, and default_filters metadata deterministically without changing `kb_k21.yml` or using an LLM.

**Architecture:** Load optional overlay next to `kb_k21.yml`. Contracts alias Intent concepts → metric keys, expand `required_entities`, select preferred entity-chain paths (edges from `kb.semantic.relationships`), prefer `default_time_column`, and attach `default_filters` as GroundedContext metadata only. Missing overlay → existing BFS behavior.

**Tech Stack:** Python 3.12, Pydantic v2, pytest, existing `GroundingEngine` / `KbIndex`.

## Global Constraints

- No LLM in Grounding
- Do not edit bulk `kb_k21.yml` for this feature
- SQL expressions remain in `kb_k21.yml` unless `sql_expression_override` is set
- Preferred paths are ordered **entity** chains; resolve ON/join_type from relationships
- `default_filters` are metadata only — never execute/interpret as SQL in Grounding
- Missing overlay file must not break existing tests (BFS fallback)

---

### Task 1: Overlay file + contract models

**Files:**
- Create: `grounding_contracts.json`
- Create: `semantic_layer/grounding/contracts.py`
- Modify: `semantic_layer/grounding/models.py` (add `default_filters`, `applied_path_ids` on `GroundedContext`)
- Modify: `semantic_layer/grounding/__init__.py` (export loader types if useful)
- Test: `tests/grounding/test_contracts_loader.py`

**Interfaces:**
- Produces: `load_grounding_contracts(path) -> GroundingContracts | None`
- Produces: `GroundingContracts`, `MetricContract`, `PreferredJoinPath`
- Produces: `GroundedContext.default_filters: list[str]`, `applied_path_ids: list[str]`

- [ ] **Step 1: Write failing loader test**

```python
from pathlib import Path
from semantic_layer.grounding.contracts import load_grounding_contracts

def test_load_default_overlay():
    contracts = load_grounding_contracts()
    assert contracts is not None
    assert "total_revenue" in contracts.metric_contracts
    assert contracts.resolve_metric_key("revenue") == "total_revenue"
    path = contracts.paths_by_id["cash_revenue_to_grade"]
    assert path.entities[0] == "Payment"
    assert path.entities[-1] == "Grade"

def test_missing_overlay_returns_none(tmp_path: Path):
    assert load_grounding_contracts(tmp_path / "missing.json") is None
```

- [ ] **Step 2: Run test — expect ImportError / fail**

Run: `pytest tests/grounding/test_contracts_loader.py -v`

- [ ] **Step 3: Add models + loader + seed JSON**

`grounding_contracts.json` seeds `total_revenue` + `bag_net_value` and paths `cash_revenue_to_grade`, `bag_net_to_grade`.

`contracts.py` parses JSON into Pydantic models; builds alias → canonical map; returns `None` if path missing.

Extend `GroundedContext` with `default_filters` and `applied_path_ids` defaulting to `[]`.

- [ ] **Step 4: Run loader tests — expect PASS**

Run: `pytest tests/grounding/test_contracts_loader.py -v`

---

### Task 2: Engine — contracts, preferred joins, time, filters metadata

**Files:**
- Modify: `semantic_layer/grounding/engine.py`
- Test: `tests/grounding/test_grounding.py` (extend) + `tests/grounding/test_contracts_engine.py`

**Interfaces:**
- Consumes: `load_grounding_contracts`, `GroundingContracts`
- Modifies: `GroundingEngine.__init__(..., contracts_path=...)` loads overlay (or None)
- Produces: preferred-path joins when contract applies; BFS otherwise

- [ ] **Step 1: Write failing engine tests**

```python
def test_preferred_path_for_total_revenue():
    engine = GroundingEngine()  # loads default overlay
    grounded = engine.ground(_rank_intent(), nq)
    assert grounded.status == GroundingStatus.VALID
    assert "cash_revenue_to_grade" in grounded.applied_path_ids
    pairs = {(j.from_entity, j.to_entity) for j in grounded.joins} | {
        (j.to_entity, j.from_entity) for j in grounded.joins
    }
    assert ("Payment", "AcademicBag") in pairs or ("AcademicBag", "Payment") in pairs
    assert ("LearnerEnrollment", "Grade") in pairs or ("Grade", "LearnerEnrollment") in pairs
    assert grounded.time_filters[0].suggested_columns[0] == "public_payment_details.created_at"
    assert any("payment_status" in f for f in grounded.default_filters)
    # metadata only — filters are plain strings
    assert all(isinstance(f, str) for f in grounded.default_filters)

def test_no_overlay_falls_back_to_bfs(tmp_path):
    # engine with contracts_path pointing at missing file
    ...
    assert grounded.joins  # still works
    assert grounded.applied_path_ids == []
```

- [ ] **Step 2: Run — expect FAIL (no applied_path_ids)**

- [ ] **Step 3: Implement engine wiring**

In `ground()`:
1. Remap concepts via `contracts.resolve_metric_key` before lookup.
2. After grounding a metric, if contract: add grain/required entities; collect `default_filters`; optional SQL override; record `preferred_path_id`.
3. Resolve joins: if unique preferred path(s) compatible → `_joins_from_entity_chain`; on missing edge → error + PARTIAL; on conflicting path ids → PARTIAL; else `_resolve_joins` BFS.
4. Time: prepend contract `default_time_column` to suggested_columns / notes.
5. Keep payment/bag heuristics only when **no** contract matched that metric (backward compatible).

`_find_relationship(a, b) -> rel dict | None` using adjacency (either direction; emit GroundedJoin with original from/to/on).

- [ ] **Step 4: Run grounding tests — expect PASS**

Run: `pytest tests/grounding -v`

---

### Task 3: Pipeline demo + docs

**Files:**
- Modify: `pipeline.py` (print `applied_path_ids`, `default_filters`)
- Modify: `docs/FLOW.md` Part C
- Modify: `docs/LIMITATIONS.md` §8
- Modify: `README.md`
- Modify: spec status → Approved

- [ ] **Step 1: Update docs + demo output fields**
- [ ] **Step 2: Run full suite**

Run: `pytest -q`  
Expected: all pass

- [ ] **Step 3: Smoke demo**

Run: `python pipeline.py`  
Expect GROUNDING section shows `applied_path_ids: ['cash_revenue_to_grade']` and primary time column from contract.

---

## Spec coverage check

| Spec item | Task |
|-----------|------|
| Overlay file, no kb_k21.yml rewrite | 1 |
| metric_contracts + preferred_join_paths schema | 1 |
| Alias remap | 2 |
| required/grain entities | 2 |
| Preferred path via relationships | 2 |
| Conflict → PARTIAL | 2 |
| BFS fallback if missing overlay | 2 |
| default_time_column primary | 2 |
| default_filters metadata only | 2 |
| GroundedContext new fields | 1–2 |
| Docs / FLOW / LIMITATIONS / README | 3 |
| Seed total_revenue (+ bag_net_value) | 1 |
