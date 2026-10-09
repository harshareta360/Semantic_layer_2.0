from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class GroundingStatus(str, Enum):
    VALID = "VALID"
    PARTIAL = "PARTIAL"  # some concepts resolved, some missing
    FAILED = "FAILED"


class GroundedEntity(BaseModel):
    concept: str
    source_table: str
    primary_key: str | None = None
    columns: list[str] = Field(default_factory=list)
    display_column: str | None = None
    synonyms: list[str] = Field(default_factory=list)
    description: str | None = None


class GroundedMetric(BaseModel):
    concept: str
    sql_expression: str
    unit: str | None = None
    dependencies: list[str] = Field(default_factory=list)
    entity: str | None = None
    column: str | None = None
    aggregation_type: str | None = None
    description: str | None = None
    source: str = "metrics"  # metrics | measures


class GroundedDimension(BaseModel):
    concept: str
    column: str | None = None
    entity: str | None = None
    data_type: str | None = None
    description: str | None = None


class GroundedJoin(BaseModel):
    from_entity: str
    to_entity: str
    on: str
    join_type: str = "inner"
    cardinality: str | None = None
    name: str | None = None


class GroundedTimeFilter(BaseModel):
    range: str
    start: str | None = None
    end: str | None = None
    # Physical date column(s) suggested from KB hints / entity columns
    suggested_columns: list[str] = Field(default_factory=list)
    notes: str | None = None


class GroundedContext(BaseModel):
    """Physical/semantic resolution of an Intent AST against kb_k21.yml."""

    status: GroundingStatus = GroundingStatus.VALID
    bo_id: str | None = None
    # First entity on preferred path (or metric grain) — IR uses this as FROM; does not re-pick
    base_entity: str | None = None
    entities: list[GroundedEntity] = Field(default_factory=list)
    metrics: list[GroundedMetric] = Field(default_factory=list)
    dimensions: list[GroundedDimension] = Field(default_factory=list)
    joins: list[GroundedJoin] = Field(default_factory=list)
    time_filters: list[GroundedTimeFilter] = Field(default_factory=list)
    tables: list[str] = Field(default_factory=list)
    rules: list[str] = Field(default_factory=list)
    join_guidance: list[str] = Field(default_factory=list)
    unresolved_concepts: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    # From grounding_contracts.json — metadata for later IR (not executed here)
    default_filters: list[str] = Field(default_factory=list)
    applied_path_ids: list[str] = Field(default_factory=list)
    extras: dict[str, Any] = Field(default_factory=dict)
