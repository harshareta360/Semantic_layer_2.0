from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from semantic_layer.intent.models.ast import QueryNode
from semantic_layer.intent.models.enums import (
    INTENT_SCHEMA_VERSION,
    IntentStatus,
    ParserSource,
)


class IntentResult(BaseModel):
    schema_version: str = INTENT_SCHEMA_VERSION
    status: IntentStatus
    confidence: float = 0.0
    parser: ParserSource = ParserSource.RULE_ENGINE
    intent_ast: QueryNode | dict[str, Any] | None = None
    matched_patterns: list[str] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
