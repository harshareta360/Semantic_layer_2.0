# BO-Scoped Grounding Implementation Plan

> **For agentic workers:** Inline execution. Steps use checkbox syntax.

**Goal:** Scope Grounding to an explicit `bo_id` (Finance | Logistics) via `business_objects.json` allow-lists.

**Architecture:** Load BO registry; when `bo_id` set, filter KbIndex (entities/metrics/relationships/rules) to BO tables; validate preferred paths against BO; record `bo_id` on results. Omit `bo_id` → unscoped (backward compatible).

**Tech Stack:** Python, Pydantic, existing GroundingEngine / Pipeline.

## Global Constraints

- Caller provides `bo_id`; no inference
- Unknown `bo_id` → Grounding FAILED
- `default_filters` remain metadata only
- Do not rewrite kb.json

---

### Task 1: Registry file + loader

- Create: `business_objects.json` (Finance 9 + Logistics 8 with columns)
- Create: `semantic_layer/grounding/business_objects.py`
- Test: `tests/grounding/test_business_objects.py`

### Task 2: Engine slice + ground(bo_id)

- Modify: `engine.py`, `models.py` (`bo_id` on GroundedContext)
- Filter entities/metrics/relationships/rules/paths
- Test: Finance revenue VALID; Logistics revenue fails closed; unknown FAILED; None unscoped

### Task 3: Pipeline + docs + demo

- Modify: `orchestrator.py` `run_full(..., bo_id=)`, `PipelineResult.bo_id`
- Modify: `pipeline.py` pass `bo_id="Finance"`
- Update FLOW / LIMITATIONS / README
