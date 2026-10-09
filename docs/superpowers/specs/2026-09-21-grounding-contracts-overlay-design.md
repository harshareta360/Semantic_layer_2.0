# Grounding V1.1 — Contracts Overlay Design

Date: 2026-09-21  
Status: Approved  
Scope: First grounding improvement slice (deterministic, **no LLM**)

## Goal

Keep `kb_k21.yml` as the domain knowledge source. Add an execution-oriented overlay `grounding_contracts.json` that makes metric grounding and join selection **explicit and deterministic**.

```text
Existing kb_k21.yml  (unchanged)
        │
        └── grounding_contracts.json
                ├── metric_contracts
                └── preferred_join_paths
                        ↓
                 GroundingEngine
                        ↓
                 GroundedContext
```

## Non-goals

- No LLM in Grounding
- No Query IR / full SQL assembly
- No rewrite of free-text `kb.rules` / `kb.join_paths` into typed rules (later slice)
- No edits to the bulk of `kb_k21.yml`

## Concept naming

Intent already emits **canonical concept keys** from Normalization/KB (e.g. `total_revenue`, `Grade`), not display labels.

Overlay keys must match those Intent concepts:

| Intent concept | Overlay key | Notes |
|----------------|-------------|--------|
| `total_revenue` | `metric_contracts.total_revenue` | Cash / collections (KB metric) |
| `bag_net_value` | `metric_contracts.bag_net_value` | “Net revenue” bag value |
| `Grade` | entity in preferred path | Master entity |

Display names (`Net Revenue`, etc.) are optional metadata for humans / debugging only — **not** what Intent emits.

## File location

Project root: `grounding_contracts.json`  
Loaded by `GroundingEngine` / `KbIndex` alongside `kb_k21.yml` (default path next to KB; overridable).

## Schema

```json
{
  "version": 1,
  "metric_contracts": {
    "total_revenue": {
      "display_name": "Total Revenue",
      "description": "Canonical cash revenue from payment_details",
      "aliases": ["revenue", "Revenue"],
      "grain_entities": ["Payment"],
      "required_entities": ["Payment", "AcademicBag"],
      "preferred_path_id": "cash_revenue_to_grade",
      "default_time_column": "public_payment_details.created_at",
      "default_filters": [
        "public_payment_details.payment_status::integer = 3"
      ],
      "sql_expression_override": null
    }
  },
  "preferred_join_paths": [
    {
      "id": "cash_revenue_to_grade",
      "description": "Cash path: Payment → Bag → Enrollment → Grade",
      "for_metrics": ["total_revenue"],
      "entities": [
        "Payment",
        "AcademicBag",
        "LearnerEnrollment",
        "Grade"
      ]
    }
  ]
}
```

### Field rules

**`metric_contracts[name]`**

| Field | Required | Meaning |
|-------|----------|---------|
| `display_name` | no | Human label |
| `description` | no | Docs |
| `aliases` | no | Extra names that map → this contract (if AST still has a synonym) |
| `grain_entities` | yes | Entities that define metric grain |
| `required_entities` | yes | Must be present for joins / tables |
| `preferred_path_id` | no | Points at `preferred_join_paths[].id` |
| `default_time_column` | no | Primary date column for TIME_FILTER |
| `default_filters` | no | Predicate strings for later IR (stored on GroundedContext) |
| `sql_expression_override` | no | If set, overrides `kb.metrics[].sql_expression`; if null/absent, use KB |

SQL expressions stay in **`kb_k21.yml` metrics** by default (single source of truth). The overlay **enriches** grounding behavior; it does not duplicate SQL unless override is intentional.

**`preferred_join_paths[]`**

| Field | Required | Meaning |
|-------|----------|---------|
| `id` | yes | Stable id |
| `entities` | yes | Ordered entity chain (not raw tables) |
| `for_metrics` | no | Metrics that prefer this path |
| `description` | no | Docs |

Edges between consecutive entities are resolved from `kb.semantic.relationships` (same ON / join_type as today). If an edge is missing → grounding error / `PARTIAL`.

## Engine behavior (changes)

1. **Load overlay** when constructing `GroundingEngine` (missing file = current V1 behavior).
2. **Alias map**: contract name + `aliases` → canonical metric key before KB lookup.
3. **After metric resolve**: if contract exists, union `required_entities` / `grain_entities` into entity set (replaces payment/bag string heuristics for contracted metrics).
4. **Joins**:
   - If any grounded metric has `preferred_path_id` (or a path lists `for_metrics`), materialize joins along that entity chain via relationship lookup.
   - If multiple metrics disagree on path → `PARTIAL` + error listing conflict (do not silently pick).
   - Else fall back to existing BFS.
5. **Time**: if contract has `default_time_column`, set it as the first/primary `suggested_columns` entry (and mark in notes).
6. **Default filters**: attach to `GroundedContext` (new field `default_filters: list[str]`) for IR later — not applied as SQL yet.
7. **Status**: unchanged VALID / PARTIAL / FAILED semantics; add errors when preferred path cannot be wired.

## GroundedContext additions

```text
default_filters: list[str]          # from contracts
applied_path_ids: list[str]         # which preferred paths were used
```

Existing fields unchanged.

## Initial overlay content (V1.1 ship)

Seed with the happy-path academic cash rank case:

- `total_revenue` contract + path `cash_revenue_to_grade`
- Optionally `bag_net_value` contract + bag-centric path (same enrollment → Grade spine)

Keep the file small; expand metrics as needed.

## Flow

```text
Intent AST
   ↓
Concepts: Grade, total_revenue (+ TIME)
   ↓
grounding_contracts.json  (alias → contract → preferred_path_id)
   ↓
kb_k21.yml  (entity tables, metric SQL, relationship ON clauses)
   ↓
GroundedContext
```

## Testing

- Unit: load overlay; resolve `total_revenue` + `Grade` → preferred path edges (Payment–Bag–Enrollment–Grade), primary time column set.
- Pipeline: `run_full("show top 10 grds by revnue this yr")` uses preferred path (not arbitrary BFS).
- Missing overlay file → prior tests still pass (BFS fallback).
- Conflicting path ids → `PARTIAL`.

## Docs

Update `docs/FLOW.md` Part C, `docs/LIMITATIONS.md` §8, `README.md` one-liner about `grounding_contracts.json`.

## Open points (defaults if you approve as-is)

1. SQL stays in `kb_k21.yml`; overlay override optional — **yes**.
2. Preferred paths are **entity chains**, not table name lists — **yes** (tables come from entity `source_table`).
3. Missing overlay = graceful V1 fallback — **yes**.
