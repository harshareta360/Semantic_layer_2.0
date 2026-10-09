from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

_DEFAULT_BO_PATH = Path(__file__).resolve().parents[2] / "business_objects.json"


class BusinessObject(BaseModel):
    id: str
    description: str | None = None
    tables: dict[str, list[str]] = Field(default_factory=dict)

    @property
    def table_names(self) -> set[str]:
        return set(self.tables.keys())

    def allows_table(self, table: str) -> bool:
        return table in self.tables

    def allowed_columns(self, table: str) -> list[str] | None:
        cols = self.tables.get(table)
        return list(cols) if cols is not None else None


class BusinessObjectRegistry(BaseModel):
    version: int = 1
    business_objects: dict[str, BusinessObject] = Field(default_factory=dict)

    def get(self, bo_id: str) -> BusinessObject | None:
        return self.business_objects.get(bo_id)

    def require(self, bo_id: str) -> BusinessObject:
        bo = self.get(bo_id)
        if bo is None:
            known = ", ".join(sorted(self.business_objects)) or "(none)"
            raise KeyError(f"unknown business object '{bo_id}'; known: {known}")
        return bo


def load_business_objects(
    path: Path | str | None = None,
) -> BusinessObjectRegistry | None:
    """Load BO registry. Returns None if file is missing."""
    p = Path(path) if path is not None else _DEFAULT_BO_PATH
    if not p.is_file():
        return None
    raw: dict[str, Any] = json.loads(p.read_text(encoding="utf-8"))
    bos: dict[str, BusinessObject] = {}
    for bo_id, body in (raw.get("business_objects") or {}).items():
        bos[str(bo_id)] = BusinessObject(
            id=str(bo_id),
            description=(body or {}).get("description"),
            tables=dict((body or {}).get("tables") or {}),
        )
    return BusinessObjectRegistry(
        version=int(raw.get("version") or 1),
        business_objects=bos,
    )
