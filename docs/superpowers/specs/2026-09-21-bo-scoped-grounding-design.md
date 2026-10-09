# Business Object–Scoped Grounding Design

Date: 2026-09-21  
Status: Approved  
Depends on: Grounding V1 + `grounding_contracts.json` overlay

## Goal

Scope Grounding to an explicitly provided **Business Object (BO)** so the engine only uses KB entities, metrics, relationships, and guidance whose tables fall inside that BO’s allow-list.

Caller always supplies `bo_id` with the question (no picker / no LLM).

```text
(question, bo_id)
      ↓
Normalization + Intent   (unchanged; full thin vocab OK for V1)
      ↓
BO registry → table/column allow-list
      ↓
KbSlice(bo) ⊂ kb_k21.yml
      ↓
contracts (preferred paths) validated against BO
      ↓
GroundedContext (+ bo_id)
```

## Non-goals

- Inferring BO from the question
- Scoping Normalization / Intent vocab in V1 (can follow later)
- Query IR / SQL
- Changing `kb_k21.yml` contents

## Business objects (locked)

### Finance — 9 tables

| Table | Columns (allow-list) |
|-------|----------------------|
| `public_learner_enrollment` | id, learner_id, enrollment_date, curriculum_id, grade_id, session_id, is_rollover |
| `public_grades_master` | id, name, code, sort_order, is_active |
| `public_curriculum_master` | id, name, code, is_active |
| `public_session_master` | id, code, name, is_active, start_time, end_time |
| `public_academic_bag` | id, learner_id, enrollment_id, bag_status, payment_status, gross_price, bag_type, gst_per, gst_total, net_price, overall_discount_total, taxable_price, total_commitment_amount, is_active, created_at, created_by |
| `public_academic_bag_items` | id, academic_bag_id, product_name, quantity, selected_qty, gross_price, discount_name, discount_value, discount_type, taxable_price, gst_per, gst_amount, net_price, is_mandatory, is_active |
| `public_academic_bag_installment` | id, academic_bag_id, installment_type, is_draft, payment_via, updated_at |
| `public_payment_details` | id, academic_bag_id, learner_enroll_id, amount, payment_mode, payment_status, payment_type, pay_date, installment_type, created_at |
| `public_learners` | id, first_name, last_name |

### Logistics — 8 tables

| Table | Columns (allow-list) |
|-------|----------------------|
| `public_learner_enrollment` | id, learner_id, enrollment_date, curriculum_id, grade_id, is_current |
| `public_grades_master` | id, name, code, sort_order, is_active |
| `public_curriculum_master` | id, name, code, is_active |
| `public_logistics_orders` | id, enrollment_id, academic_bag_id, logistics_status, address_verification_status, city, state_id, country_id, zip_code, shipment_fee_amount, shipment_fee_currency, shipment_fee_status, total_amount, total_amount_currency, reinitiation_fee_waived, logistics_line_type, is_active, created_at |
| `public_logistics_order_items` | id, logistics_order_id, logistics_shipment_id, product_name, quantity, product_price, gst_per, gst_amount, net_price, item_status, is_additional_item, is_active, academic_bag_id |
| `public_logistics_shipments` | id, logistics_order_id, shipment_number, tracking_id, shipment_status, shipped_at, delivered_at, delivery_failure_reason, is_active, created_at |
| `public_learners` | id, first_name, last_name |
| `public_master_list_value` | id, name |

Shared spine tables may appear in both BOs with **BO-specific column lists**.

## File

Project root: `business_objects.json`

```json
{
  "version": 1,
  "business_objects": {
    "Finance": {
      "tables": {
        "public_payment_details": ["id", "amount", "..."]
      }
    },
    "Logistics": { "tables": { "...": ["..."] } }
  }
}
```

Ids are case-sensitive keys: `Finance`, `Logistics`.

## Slice rules (KbSlice)

Given `bo_id`:

1. **Entities** — keep if `source_table` ∈ BO tables; optionally intersect entity `columns` with BO column allow-list when emitting `GroundedEntity`.
2. **Metrics** — keep if every dependency table (bare name or `table.col` prefix) ∈ BO tables. Else exclude (treat as unresolved if Intent asked for it).
3. **Measures / dimensions** — keep if owning entity’s table ∈ BO (or measure table if present).
4. **Relationships** — keep edge if **both** endpoint entities resolve to tables ∈ BO.
5. **Rules / join_paths** — keep only strings that mention at least one BO table name (reduce cross-BO noise).
6. **Contracts** — preferred path allowed only if every path entity’s table ∈ BO; else error / `PARTIAL`.

Unknown `bo_id` → Grounding `FAILED` with clear error (do not silently use full KB).

## API

```python
Pipeline.run_full(question, bo_id="Finance")
GroundingEngine.ground(intent, nq, bo_id="Finance")
```

`PipelineResult` / `GroundedContext` record `bo_id` used.

If `bo_id` is omitted: **V1 behavior** = full KB (backward compatible for existing tests), documented as “unscoped.”

## Interaction with `grounding_contracts.json`

Contracts stay global for now. When `bo_id` is set, preferred paths that leave the BO fail closed. Finance cash path stays valid; a path touching logistics tables is rejected under `bo_id=Finance`.

Later optional: nest contracts under BO keys.

## Testing

- Finance + rank-by-revenue → VALID, tables ⊆ Finance, `applied_path_ids` includes cash path.
- Same question + `Logistics` → metric/path not in BO → PARTIAL/FAILED (no payment tables).
- Unknown bo_id → FAILED.
- `bo_id=None` → existing tests still pass.

## Docs

Update FLOW / LIMITATIONS / README: explicit `bo_id`, link `business_objects.json`.
