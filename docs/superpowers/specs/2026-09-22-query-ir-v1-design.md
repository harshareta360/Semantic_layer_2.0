# Query IR V1 Design

Date: 2026-09-22  
Status: Approved (with amendments)  
Depends on: Intent AST + GroundedContext (VALID) + optional `bo_id`

## Goal

Compile **Intent AST + GroundedContext** into a pure **QueryIR** plan. Wrap outcomes in **QueryIRResult** (status / errors / optional SQL preview). IR does **not** rediscover joins or metric SQL — it mechanically assembles what Grounding already resolved.

```text
User Question
      ↓
Normalization → Intent AST → Grounding → GroundedContext
      ↓
QueryIR Compiler  (mechanical)
      ↓
QueryIRResult { status, ir, sql_preview, errors }
      ↓
V1: thin Postgres SQL preview
Later: SQLGlot
```

## Non-goals (V1)

- No DB execution / repair loop  
- No LLM in IR  
- No full Intent coverage (WINDOW, EXISTS, set ops deferred)  
- No inventing base table / join path / metric formulas in the compiler  

## Amendments (locked)

1. **QueryIR is pure** — no `status` / `errors` inside IR; those live on `QueryIRResult` (same pattern as `IntentResult` → `intent_ast`).
2. **IR does not re-decide base/joins** — Grounding exposes `base_entity` + `joins`; compiler only maps them into IR.
3. **Metric SQL only from Grounding** — `expression = grounded_metric.sql_expression` (from `kb.json` via Grounding); compiler never hardcodes `SUM(pd.amount::numeric)`.
4. **SQL-aware fragments are opaque / structured renderer input** — join `ON` and `default_filters` are resolved predicates from Grounding, not invented by IR. Prefer structured join endpoints when available; opaque strings allowed in V1 and clearly marked.
5. **THIS_YEAR is a half-open range** —  
   `time_col >= date_trunc('year', CURRENT_DATE)`  
   `AND time_col < date_trunc('year', CURRENT_DATE) + interval '1 year'`.

## Gate

| Grounding | IR |
|-----------|-----|
| `VALID` | Compile |
| `PARTIAL` | Compile only if every Intent-required concept is resolved; else `FAILED` |
| `FAILED` / null | `QueryIRResult` FAILED, `ir=null` |

## GroundedContext additions (for IR)

```text
base_entity: str | None   # first entity on applied preferred path, else metric grain / leftmost
```

Grounding sets this when applying preferred paths (e.g. `Payment` for `cash_revenue_to_grade`). IR reads it; does not choose again.

Existing `joins`, `metrics`, `entities`, `time_filters`, `default_filters` remain the physical truth.

## Models

### QueryIR (pure plan)

```text
from: IrFrom          # entity, table, alias (from base_entity + entity map)
joins: list[IrJoin]   # join_type, entity, table, alias, on (opaque) + optional structured ends
select: list[IrSelectItem]   # column | expression (expression.sql from grounded metric only)
where: list[IrPredicate]     # opaque sql + source (default_filter | time_filter)
group_by: list[IrColumnRef]
order_by: list[IrOrder]
limit: int | None
bo_id: str | None     # echo for tracing only
```

`IrJoin` V1:

```text
join_type, entity, table, alias
on: str                         # opaque, from GroundedJoin.on
# optional structured (when parseable / later from Grounding):
left_table, left_column, operator, right_table, right_column
```

`IrPredicate`:

```text
sql: str              # opaque renderer input
source: default_filter | time_filter
range: str | None     # e.g. THIS_YEAR
```

### QueryIRResult

```text
status: VALID | FAILED
ir: QueryIR | None
sql_preview: str | None
errors: list[str]
```

## Compilation rules (mechanical)

1. Require grounding + Intent AST; resolve entity concept → `GroundedEntity`.
2. **`from`** ← `grounded.base_entity` (+ its table/alias). If missing → FAILED.
3. **`joins`** ← iterate `grounded.joins` in order; map entities to tables/aliases; copy `on` opaque; try parse `a.b = c.d` into structured fields when possible.
4. **Select dimensions** ← Intent DIMENSION_REF / RANK dimension → `display_column` (else PK).
5. **Select metrics** ← Intent METRIC_REF / RANK metric → **only** `GroundedMetric.sql_expression`, alias = concept.
6. **Group by** ← Intent `group_by` or RANK dimension columns.
7. **Where** ← copy each `default_filters` string as opaque predicate; compile time ranges with exclusive upper bound for `THIS_YEAR` using `time_filters[0].suggested_columns[0]` (contract primary).
8. **Order / limit** ← RANK direction/limit or Intent limit.
9. Never embed metric SQL literals in compiler source code.

## SQL preview (thin Postgres)

`to_sql_postgres(QueryIR) -> str` concatenates FROM / JOIN … ON / SELECT / WHERE / GROUP BY / ORDER BY / LIMIT. Opaque fragments inserted as-is. Not a dialect engine — replaceable by SQLGlot later.

## API

```python
from semantic_layer.ir import compile_query_ir

result = compile_query_ir(intent_result, grounded_context)
# result.status, result.ir, result.sql_preview, result.errors
```

`Pipeline.run_full` → `ClauseResult.ir: QueryIRResult | None`  
Demo UI + `pipeline.py` show IR + SQL preview.

## Happy-path acceptance

`show top 10 grds by revnue this yr` + `bo_id=Finance`

- Grounding sets `base_entity=Payment`, joins cash path, metric expr from KB  
- IR VALID; select grade display + grounded revenue expr; where default_filter + THIS_YEAR half-open; ORDER DESC; LIMIT 10  
- `sql_preview` is one SELECT string  

## Files

- `semantic_layer/ir/models.py`, `compiler.py`, `sql_preview.py`, `__init__.py`
- Grounding: set `base_entity` on `GroundedContext`
- Pipeline / demo_ui / tests / FLOW / LIMITATIONS / README
