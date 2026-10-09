from __future__ import annotations

import os
from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg
from dotenv import load_dotenv

from semantic_layer.execute.models import (
    ExecuteResult,
    ExecuteStatus,
    ValidationResult,
    ValidationStatus,
)
from semantic_layer.execute.validator import validate_sql
from semantic_layer.grounding.models import GroundedContext
from semantic_layer.ir.models import QueryIRResult

load_dotenv()

DEFAULT_MAX_ROWS = 500
DEFAULT_STATEMENT_TIMEOUT_MS = 15_000


def _pg_conninfo() -> str:
    host = os.getenv("PG_HOST", "localhost")
    port = os.getenv("PG_PORT", "5432")
    db = os.getenv("PG_DB", "")
    user = os.getenv("PG_USER", "")
    password = os.getenv("PG_PASS", "")
    if not db or not user:
        raise RuntimeError(
            "Postgres not configured: set PG_HOST, PG_PORT, PG_DB, PG_USER, PG_PASS in .env"
        )
    # dbname may contain dots/hyphens — pass via conninfo keywords
    return (
        f"host={host} port={port} dbname={db} user={user} password={password}"
    )


def _jsonable(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, UUID):
        return str(value)
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:  # noqa: BLE001
            return str(value)
    return value


def _ensure_limit(sql: str, max_rows: int) -> str:
    upper = sql.upper()
    if "LIMIT" in upper:
        return sql
    stripped = sql.rstrip().rstrip(";")
    return f"{stripped}\nLIMIT {int(max_rows)};"


def execute_sql(
    sql: str,
    *,
    bo_id: str | None = None,
    grounded: GroundedContext | None = None,
    ir_result: QueryIRResult | None = None,
    max_rows: int = DEFAULT_MAX_ROWS,
    statement_timeout_ms: int = DEFAULT_STATEMENT_TIMEOUT_MS,
    skip_validation: bool = False,
) -> ExecuteResult:
    """Validate (unless skipped) then run a read-only SELECT against Postgres."""
    validation: ValidationResult
    if skip_validation:
        validation = ValidationResult(
            status=ValidationStatus.VALID,
            sql=sql,
            warnings=["validation skipped"],
        )
    else:
        validation = validate_sql(
            sql, bo_id=bo_id, grounded=grounded, ir_result=ir_result
        )
        if validation.status != ValidationStatus.VALID:
            return ExecuteResult(
                status=ExecuteStatus.FAILED,
                error="validation failed",
                validation=validation,
            )

    try:
        conninfo = _pg_conninfo()
    except RuntimeError as exc:
        return ExecuteResult(
            status=ExecuteStatus.FAILED,
            error=str(exc),
            validation=validation,
        )

    run_sql = _ensure_limit(validation.sql or sql, max_rows)

    try:
        with psycopg.connect(conninfo, connect_timeout=5) as conn:
            conn.execute(
                "SELECT set_config('statement_timeout', %s, true)",
                (str(int(statement_timeout_ms)),),
            )
            with conn.cursor() as cur:
                cur.execute(run_sql)
                if cur.description is None:
                    return ExecuteResult(
                        status=ExecuteStatus.OK,
                        columns=[],
                        rows=[],
                        row_count=0,
                        validation=validation,
                    )
                columns = [d.name for d in cur.description]
                raw_rows = cur.fetchmany(max_rows + 1)
                truncated = len(raw_rows) > max_rows
                raw_rows = raw_rows[:max_rows]
                rows = [[_jsonable(c) for c in row] for row in raw_rows]
                warnings = list(validation.warnings)
                if truncated:
                    warnings.append(f"result truncated to {max_rows} rows")
                validation.warnings = warnings
                return ExecuteResult(
                    status=ExecuteStatus.OK,
                    columns=columns,
                    rows=rows,
                    row_count=len(rows),
                    validation=validation,
                )
    except Exception as exc:  # noqa: BLE001
        return ExecuteResult(
            status=ExecuteStatus.FAILED,
            error=str(exc),
            validation=validation,
        )
