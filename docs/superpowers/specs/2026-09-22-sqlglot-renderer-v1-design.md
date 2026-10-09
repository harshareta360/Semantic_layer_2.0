# SQLGlot Renderer V1 Design

Date: 2026-09-22  
Status: Approved  
Depends on: Query IR V1 (`QueryIR` pure plan)

## Goal

Render **QueryIR → dialect SQL** via **SQLGlot**, without changing how Intent/Grounding/IR decide business meaning.

```text
QueryIR
   ↓
sqlglot renderer (postgres default)
   ↓
sql string  (replaces thin to_sql_postgres as primary)
```

Thin `to_sql_postgres` remains as fallback if SQLGlot parse/build fails on an opaque fragment.

## Non-goals

- No DB execute / repair  
- No rewriting metric formulas or inventing joins  
- No multi-dialect UI yet (API accepts `dialect=`, default `postgres`)

## Approaches

| # | Approach | Pros | Cons |
|---|----------|------|------|
| **A (recommended)** | Build SQLGlot `exp.Select` from structured IR fields; `parse_one` opaque fragments (`on`, metric `sql`, where predicates) in postgres dialect | Proper quoting/dialect; keeps opaque Grounding strings | Opaque fragments must be valid SQL-ish |
| **B** | Dump IR to SQL string then `parse_one` + `sql(dialect=)` | Minimal code | Fragile; less control |
| **C** | Fully structured only (no opaque parse) | Cleanest AST | Requires rewriting Grounding ON/filters first |

**Recommendation: A**

## Mapping

| QueryIR | SQLGlot |
|---------|---------|
| `from_` | `exp.Table` + alias |
| `joins` | `exp.Join` + `on=parse_one(join.on)` (or structured EQ if columns present) |
| select column | `exp.column` / `Alias` |
| select expression | `parse_one(item.sql)` + `Alias` |
| where | `and_(parse_one(p.sql)…)` |
| group_by | columns |
| order_by | `Ordered` on alias / column |
| limit | `Limit` |

Dialect default: **`postgres`**. Output pretty-printed for UI.

## API

```python
from semantic_layer.ir import render_sql

sql = render_sql(ir, dialect="postgres")  # primary
# compile_query_ir sets sql_preview via render_sql; falls back to to_sql_postgres on error
```

`QueryIRResult.sql_preview` keeps the same field name (now SQLGlot-backed).

## Files

- Add dep: `sqlglot` in `pyproject.toml`
- Create `semantic_layer/ir/sqlglot_renderer.py`
- Wire `compiler.py` / `__init__.py`
- Tests: Finance happy path SQL contains joins/metric/where/limit; dialect postgres
- Docs: FLOW / LIMITATIONS / README

## Acceptance

Same Finance question → SQLGlot postgres SQL equivalent to current preview (semantically), with IR unchanged.
