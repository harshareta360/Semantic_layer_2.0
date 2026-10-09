from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class IrStatus(str, Enum):
    VALID = "VALID"
    FAILED = "FAILED"


class IrFrom(BaseModel):
    entity: str
    table: str
    alias: str


class IrJoin(BaseModel):
    join_type: str = "inner"
    entity: str
    table: str
    alias: str
    # Opaque ON from Grounding (renderer input)
    on: str
    # Optional structured endpoints when parseable
    left_table: str | None = None
    left_column: str | None = None
    operator: str | None = None
    right_table: str | None = None
    right_column: str | None = None


class IrSelectKind(str, Enum):
    COLUMN = "column"
    EXPRESSION = "expression"


class IrSelectItem(BaseModel):
    kind: IrSelectKind
    alias: str
    table: str | None = None
    column: str | None = None
    # Only from GroundedMetric.sql_expression — never invented by IR
    sql: str | None = None


class IrPredicateSource(str, Enum):
    DEFAULT_FILTER = "default_filter"
    TIME_FILTER = "time_filter"


class IrPredicate(BaseModel):
    sql: str  # opaque renderer input from Grounding / compiled time range
    source: IrPredicateSource
    range: str | None = None


class IrColumnRef(BaseModel):
    table: str
    column: str
    alias: str | None = None


class IrOrder(BaseModel):
    expr_alias: str
    direction: str = "DESC"


class QueryIR(BaseModel):
    """Pure executable query plan (no status/errors)."""

    bo_id: str | None = None
    from_: IrFrom = Field(alias="from")
    joins: list[IrJoin] = Field(default_factory=list)
    select: list[IrSelectItem] = Field(default_factory=list)
    where: list[IrPredicate] = Field(default_factory=list)
    group_by: list[IrColumnRef] = Field(default_factory=list)
    order_by: list[IrOrder] = Field(default_factory=list)
    limit: int | None = None

    model_config = {"populate_by_name": True}


class QueryIRResult(BaseModel):
    status: IrStatus = IrStatus.FAILED
    ir: QueryIR | None = None
    sql_preview: str | None = None
    errors: list[str] = Field(default_factory=list)
