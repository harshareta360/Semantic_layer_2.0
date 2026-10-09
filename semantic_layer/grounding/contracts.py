from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

_DEFAULT_CONTRACTS_PATH = Path(__file__).resolve().parents[2] / "grounding_contracts.json"


class MetricContract(BaseModel):
    display_name: str | None = None
    description: str | None = None
    aliases: list[str] = Field(default_factory=list)
    grain_entities: list[str] = Field(default_factory=list)
    required_entities: list[str] = Field(default_factory=list)
    preferred_path_id: str | None = None
    default_time_column: str | None = None
    default_filters: list[str] = Field(default_factory=list)
    sql_expression_override: str | None = None


class PreferredJoinPath(BaseModel):
    id: str
    description: str | None = None
    for_metrics: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)


class GroundingContracts(BaseModel):
    version: int = 1
    metric_contracts: dict[str, MetricContract] = Field(default_factory=dict)
    preferred_join_paths: list[PreferredJoinPath] = Field(default_factory=list)

    # Derived indexes (not serialized from disk; built after load)
    alias_to_canonical: dict[str, str] = Field(default_factory=dict)
    paths_by_id: dict[str, PreferredJoinPath] = Field(default_factory=dict)

    def resolve_metric_key(self, concept: str) -> str:
        """Map alias / display-ish name → canonical metric contract key."""
        if concept in self.metric_contracts:
            return concept
        return self.alias_to_canonical.get(concept, concept)

    def contract_for(self, concept: str) -> MetricContract | None:
        key = self.resolve_metric_key(concept)
        return self.metric_contracts.get(key)

    def build_indexes(self) -> None:
        alias_map: dict[str, str] = {}
        for canonical, contract in self.metric_contracts.items():
            alias_map[canonical] = canonical
            for alias in contract.aliases:
                alias_map[alias] = canonical
        self.alias_to_canonical = alias_map
        self.paths_by_id = {p.id: p for p in self.preferred_join_paths}


def load_grounding_contracts(
    path: Path | str | None = None,
) -> GroundingContracts | None:
    """Load overlay JSON. Returns None if file is missing."""
    p = Path(path) if path is not None else _DEFAULT_CONTRACTS_PATH
    if not p.is_file():
        return None
    raw: dict[str, Any] = json.loads(p.read_text(encoding="utf-8"))
    contracts = GroundingContracts.model_validate(raw)
    contracts.build_indexes()
    return contracts
