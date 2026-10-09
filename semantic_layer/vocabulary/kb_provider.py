from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from semantic_layer.vocabulary.provider import VocabEntry, VocabularyProvider

# Project root / kb_k21.yml (semantic_layer/vocabulary/ → ../..)
_DEFAULT_KB_PATH = Path(__file__).resolve().parents[2] / "kb_k21.yml"


def _humanize(name: str) -> str:
    return name.replace("_", " ").strip().lower()


def _pick_display(canonical: str, synonyms: list[str]) -> str:
    """Prefer readable surface: last humanized token if present, else short synonym."""
    human = _humanize(canonical)
    syn_l = [s.lower().strip() for s in synonyms if s and s.strip()]
    last = human.split()[-1] if human else ""
    if last and last in syn_l:
        return last
    if human in syn_l:
        return human
    singles = [s for s in syn_l if " " not in s]
    if singles:
        return min(singles, key=len)
    return human


def _expand_simple_plurals(forms: set[str]) -> set[str]:
    """Add simple English plurals for single-token forms (grade → grades)."""
    out = set(forms)
    for f in list(forms):
        if " " in f or len(f) < 3:
            continue
        if f.endswith("y") and f[-2:] not in ("ay", "ey", "oy", "uy"):
            out.add(f[:-1] + "ies")
        elif not f.endswith("s"):
            out.add(f + "s")
    return out


def _dep_table(dep: str) -> str:
    return dep.split(".", 1)[0] if dep else ""


def _metric_tables(metric: dict) -> set[str]:
    return {_dep_table(str(d)) for d in (metric.get("dependencies") or []) if d}


def _bare_name(qualified: str) -> str:
    """org_0101digitall.public_academic_bag.id → last segment."""
    text = str(qualified or "").strip()
    if not text:
        return ""
    return text.rsplit(".", 1)[-1]


def _looks_like_k21(doc: dict[str, Any]) -> bool:
    return isinstance(doc.get("entities"), list) and isinstance(doc.get("tables"), list)


def adapt_k21_document(doc: dict[str, Any]) -> dict[str, Any]:
    """Map kb_k21.yml into the internal KB shape Normalization and Grounding already read.

    Table names are stored unqualified (``public_academic_bag``) so BO allow-lists
    still match. SQL expressions stay as written in the YAML.
    """
    columns_by_table: dict[str, list[str]] = {}
    for table in doc.get("tables") or []:
        full = str(table.get("name") or "")
        bare = _bare_name(full)
        cols = [
            str(c.get("name"))
            for c in (table.get("columns") or [])
            if isinstance(c, dict) and c.get("name")
        ]
        if bare:
            columns_by_table[bare] = cols
        if full:
            columns_by_table[full] = cols

    entities: list[dict[str, Any]] = []
    for ent in doc.get("entities") or []:
        full_table = str((ent.get("base") or {}).get("table") or "")
        source_table = _bare_name(full_table)
        pk_raw = ent.get("primary_key") or []
        primary_key = _bare_name(pk_raw[0]) if isinstance(pk_raw, list) and pk_raw else None
        columns = list(columns_by_table.get(full_table) or columns_by_table.get(source_table) or [])
        label = ent.get("label_column")
        if label:
            label_col = _bare_name(str(label))
            if label_col and label_col not in columns:
                columns.append(label_col)
        entities.append(
            {
                "entity": ent.get("name"),
                "name": ent.get("name"),
                "source_table": source_table,
                "primary_key": primary_key,
                "columns": columns,
                "synonyms": list(ent.get("synonyms") or []),
                "description": ent.get("description"),
                "time_column": _bare_name(str(ent["time_column"])) if ent.get("time_column") else None,
            }
        )

    measures: list[dict[str, Any]] = []
    for meas in doc.get("measures") or []:
        measures.append(
            {
                "name": meas.get("name"),
                "entity": meas.get("entity"),
                "sql": meas.get("sql"),
                "synonyms": list(meas.get("synonyms") or []),
                "aggregation_type": meas.get("agg"),
                "description": meas.get("description"),
            }
        )

    dimensions: list[dict[str, Any]] = []
    for dim in doc.get("dimensions") or []:
        dimensions.append(
            {
                "name": dim.get("name"),
                "entity": dim.get("entity"),
                "table": _bare_name(str(dim.get("table") or "")),
                "column": dim.get("column"),
                "synonyms": list(dim.get("synonyms") or []),
                "type": dim.get("type"),
                "values": dim.get("values") or [],
            }
        )

    relationships: list[dict[str, Any]] = []
    for rel in doc.get("relationships") or []:
        relationships.append(
            {
                "name": rel.get("name"),
                "from_entity": rel.get("from") or rel.get("from_entity"),
                "to_entity": rel.get("to") or rel.get("to_entity"),
                "on": rel.get("on"),
                "join_type": rel.get("join_type"),
                "cardinality": rel.get("cardinality"),
            }
        )

    return {
        "kb": {
            "db_id": doc.get("db_id"),
            "display_name": "kb_k21",
            "semantic": {
                "entities": entities,
                "measures": measures,
                "dimensions": dimensions,
                "relationships": relationships,
            },
            "metrics": [],
            "rules": [],
            "join_paths": [],
            "column_hints": {},
        }
    }


def load_kb_document(path: Path | str) -> dict[str, Any]:
    """Load kb_k21.yml (adapted). A `.json` path is still accepted if one is passed explicitly."""
    kb_path = Path(path)
    text = kb_path.read_text(encoding="utf-8")
    if kb_path.suffix.lower() in {".yml", ".yaml"}:
        doc = yaml.safe_load(text) or {}
        if not isinstance(doc, dict):
            raise ValueError(f"KB YAML root must be a mapping: {kb_path}")
        if _looks_like_k21(doc):
            return adapt_k21_document(doc)
        return doc
    doc = json.loads(text)
    if not isinstance(doc, dict):
        raise ValueError(f"KB JSON root must be an object: {kb_path}")
    return doc


def extract_vocab_entries(
    kb_doc: dict,
    *,
    allowed_tables: set[str] | None = None,
) -> list[VocabEntry]:
    """Build thin Normalization vocabulary from KB entities, measures, and metrics.

    When ``allowed_tables`` is set (BO scope), keep only:
    - entities whose ``source_table`` is allowed
    - measures whose ``entity`` is among those entities
    - metrics whose dependency tables are non-empty and ⊆ allowed

    Does NOT load relationships, rules, join_paths, SQL synonyms map, or dimensions
    (those belong to Grounding / later stages).
    """
    kb = kb_doc.get("kb", kb_doc)
    semantic = kb.get("semantic") or {}
    by_canonical: dict[str, VocabEntry] = {}

    def _upsert(canonical: str, category: str, synonyms: list[str]) -> None:
        forms = {canonical.lower(), _humanize(canonical), *(s.lower() for s in synonyms if s)}
        forms = {f.strip() for f in forms if f and f.strip()}
        forms = _expand_simple_plurals(forms)
        forms.discard("")
        if canonical in by_canonical:
            existing = by_canonical[canonical]
            merged = list(dict.fromkeys([*existing.synonyms, *sorted(forms)]))
            by_canonical[canonical] = VocabEntry(
                canonical=canonical,
                category=existing.category,  # type: ignore[arg-type]
                synonyms=merged,
                display_form=existing.display_form or _pick_display(canonical, merged),
            )
        else:
            syn_list = sorted(forms)
            by_canonical[canonical] = VocabEntry(
                canonical=canonical,
                category=category,  # type: ignore[arg-type]
                synonyms=syn_list,
                display_form=_pick_display(canonical, syn_list),
            )

    allowed_entities: set[str] = set()
    for ent in semantic.get("entities") or []:
        name = ent.get("entity") or ent.get("name")
        if not name:
            continue
        table = str(ent.get("source_table") or "")
        if allowed_tables is not None and table not in allowed_tables:
            continue
        allowed_entities.add(str(name))
        _upsert(str(name), "ENTITY", list(ent.get("synonyms") or []))

    for meas in semantic.get("measures") or []:
        name = meas.get("name")
        if not name:
            continue
        ent_name = meas.get("entity")
        if allowed_tables is not None:
            if not ent_name or str(ent_name) not in allowed_entities:
                continue
        _upsert(str(name), "MEASURE", list(meas.get("synonyms") or []))

    for metric in kb.get("metrics") or []:
        name = metric.get("name")
        if not name:
            continue
        if allowed_tables is not None:
            tables = _metric_tables(metric)
            # Empty deps would match every BO under ⊆; exclude when scoping.
            if not tables or not tables <= allowed_tables:
                continue
        _upsert(str(name), "MEASURE", list(metric.get("synonyms") or []))

    return sorted(by_canonical.values(), key=lambda e: e.canonical.lower())


class KbVocabularyProvider:
    """Load thin domain vocabulary from project kb_k21.yml.

    Pass ``bo_id`` (e.g. ``\"Finance\"``) to restrict entries to that business
    object's table allow-list from ``business_objects.json``.
    """

    def __init__(
        self,
        path: Path | str | None = None,
        *,
        bo_id: str | None = None,
        bo_path: Path | str | None = None,
    ) -> None:
        self._path = Path(path) if path else _DEFAULT_KB_PATH
        self._bo_id = bo_id
        self._bo_path = Path(bo_path) if bo_path is not None else None

    def load_entries(self) -> list[VocabEntry]:
        if not self._path.exists():
            raise FileNotFoundError(f"KB file not found: {self._path}")
        doc = load_kb_document(self._path)
        allowed: set[str] | None = None
        if self._bo_id is not None:
            # Lazy import avoids cycle: vocabulary → grounding → intent → normalization
            from semantic_layer.grounding.business_objects import load_business_objects

            reg = load_business_objects(self._bo_path)
            if reg is None:
                raise FileNotFoundError(
                    "business_objects.json missing; cannot scope vocabulary "
                    f"to BO '{self._bo_id}'"
                )
            allowed = reg.require(self._bo_id).table_names
        return extract_vocab_entries(doc, allowed_tables=allowed)


_: VocabularyProvider = KbVocabularyProvider()  # type: ignore[assignment]
