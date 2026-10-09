from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SemanticFragment:
    """Partial AST contribution from one contributing pattern."""

    pattern_id: str
    kind: str
    payload: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.95
    ambiguity: str | None = None


@dataclass
class PatternMatch:
    pattern_id: str
    builder: str
    priority: int
    slots: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.95
    ambiguity: str | None = None
