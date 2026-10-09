# SQL Validation + Execute V1 Design

Date: 2026-09-22  
Status: Approved  
Depends on: Query IR + SQLGlot `sql_preview`

## Goal

Before any database round-trip:

1. **Validate** generated SQL (and IR) against BO allow-list + SQL shape rules  
2. Optionally **EXECUTE** (read-only SELECT) against Postgres using `PG_*` from `.env`

```text
QueryIRResult.sql_preview
        ↓
SqlValidator  →  ValidationResult
        ↓ (if VALID and execute requested)
PostgresExecutor → rows / error
```

## Non-goals (V1)

- No write queries (INSERT/UPDATE/DELETE/DDL)  
- No LLM repair loop yet  
- No connection pooling service  
- Do not log passwords or full connection strings  

## Config (`.env`)

```text
PG_HOST=localhost
PG_PORT=5432
PG_DB=...
PG_USER=...
PG_PASS=...
```

Loaded via existing `python-dotenv`. Update `.env.example` with placeholders only (never real secrets).

Dependency: `psycopg[binary]>=3` (or `psycopg2-binary`) for execute.

## Validation checks (ordered)

| # | Check | Fail if |
|---|--------|---------|
| 1 | Pipeline gate | Intent/Grounding/IR not VALID, or `sql_preview` empty |
| 2 | Single statement | SQLGlot parse ≠ exactly one statement |
| 3 | Read-only shape | Root not `SELECT` / `WITH`…`SELECT` |
| 4 | No dangerous nodes | DDL/DML/`INTO`/multiple statements / `COPY` etc. |
| 5 | BO table allow-list | Any referenced table ∉ `business_objects[bo_id].tables` (when `bo_id` set) |
| 6 | Grounded table set | Referenced tables ⊈ `grounded.tables` ∪ join/from tables (soft or hard — **hard** in V1) |

Optional V1.1: `EXPLAIN` dry-run (no fetch) as schema check.

## Models

```text
ValidationStatus: VALID | FAILED
ValidationResult: status, errors[], warnings[], sql, tables_referenced[]

ExecuteResult: status, rows[], columns[], row_count, error?, validation: ValidationResult
```

## API

```python
from semantic_layer.execute import validate_sql, execute_sql

v = validate_sql(sql, bo_id="Finance", grounded=grounded)
if v.status == VALID:
    r = execute_sql(sql, limit=100)  # server-side LIMIT clamp if missing
```

Wire into `Pipeline.run_full(..., execute=False)` later or separate demo UI button **Validate** / **Run SQL**.

## Security

- Read-only intent; reject non-SELECT  
- Clamp `LIMIT` (e.g. max 500) on execute  
- Statement timeout (e.g. 15s) via `SET LOCAL statement_timeout`  
- Prefer a DB user with SELECT-only grants in production (document; V1 may use provided `PG_USER`)  

## Demo UI

Add buttons:
- **Validate SQL** → show ValidationResult  
- **Execute** → show table of rows (only if validation passed)

## Acceptance

Finance happy-path SQL → validation VALID; execute returns rows (or empty) without error when DB has data.
