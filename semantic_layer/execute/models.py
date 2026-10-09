from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ValidationStatus(str, Enum):
    VALID = "VALID"
    FAILED = "FAILED"


class ValidationResult(BaseModel):
    status: ValidationStatus = ValidationStatus.FAILED
    sql: str = ""
    tables_referenced: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ExecuteStatus(str, Enum):
    OK = "OK"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class ExecuteResult(BaseModel):
    status: ExecuteStatus = ExecuteStatus.FAILED
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    row_count: int = 0
    error: str | None = None
    validation: ValidationResult | None = None
