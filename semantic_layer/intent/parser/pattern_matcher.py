from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from semantic_layer.intent.builder.concept_binder import ConceptBindings
from semantic_layer.intent.parser.types import PatternMatch
from semantic_layer.normalization.models import NormalizedQuestion

_DEFAULT_CATALOG = Path(__file__).parent / "patterns.yaml"


@dataclass(frozen=True)
class PatternDef:
    id: str
    priority: int
    builder: str
    # Simple trigger: all of these regexes must match (case-insensitive)
    requires: list[str]
    # Optional: if any of these match, treat as ambiguity candidate
    ambiguity_if: list[str] | None = None
    params: dict[str, Any] | None = None


class PatternCatalog:
    """Priority-ordered pattern catalog (priority desc, id asc tie-break)."""

    def __init__(self, path: Path | str | None = None) -> None:
        catalog_path = Path(path) if path else _DEFAULT_CATALOG
        raw = yaml.safe_load(catalog_path.read_text(encoding="utf-8")) or []
        defs: list[PatternDef] = []
        for item in raw:
            defs.append(
                PatternDef(
                    id=item["id"],
                    priority=int(item["priority"]),
                    builder=item["builder"],
                    requires=list(item.get("requires", [])),
                    ambiguity_if=list(item["ambiguity_if"])
                    if item.get("ambiguity_if")
                    else None,
                    params=dict(item.get("params") or {}),
                )
            )
        defs.sort(key=lambda d: (-d.priority, d.id))
        self._defs = defs

    @property
    def definitions(self) -> list[PatternDef]:
        return list(self._defs)

    def match(
        self, normalized: NormalizedQuestion, bindings: ConceptBindings
    ) -> list[PatternMatch]:
        text = normalized.normalized_question.lower()
        matches: list[PatternMatch] = []
        for dfn in self._defs:
            if not all(re.search(rx, text, re.I) for rx in dfn.requires):
                continue
            slots = self._extract_slots(dfn, text, bindings)
            if not self._slots_ok(dfn.builder, slots, bindings, text):
                continue
            ambiguity = None
            if dfn.ambiguity_if and any(
                re.search(rx, text, re.I) for rx in dfn.ambiguity_if
            ):
                ambiguity = f"{dfn.id}: ambiguous trigger"
            matches.append(
                PatternMatch(
                    pattern_id=dfn.id,
                    builder=dfn.builder,
                    priority=dfn.priority,
                    slots={**(dfn.params or {}), **slots},
                    confidence=0.96,
                    ambiguity=ambiguity,
                )
            )
        return matches

    def _extract_slots(
        self, dfn: PatternDef, text: str, bindings: ConceptBindings
    ) -> dict[str, Any]:
        slots: dict[str, Any] = {}
        m = re.search(r"\b(?:top|bottom)\s+(\d+)\b", text, re.I)
        if m:
            slots["limit"] = int(m.group(1))
        if "limit" not in slots and dfn.params and "limit" in dfn.params:
            slots["limit"] = int(dfn.params["limit"])

        m = re.search(
            r"(?:greater|more|higher)\s+than\s+(\d+(?:\.\d+)?)", text, re.I
        )
        if m:
            slots["threshold"] = float(m.group(1))
            slots["comparator"] = ">"
        m = re.search(r"(?:less|lower)\s+than\s+(\d+(?:\.\d+)?)", text, re.I)
        if m:
            slots["threshold"] = float(m.group(1))
            slots["comparator"] = "<"
        m = re.search(r"\b(?:above|over)\s+(\d+(?:\.\d+)?)", text, re.I)
        if m and "threshold" not in slots:
            slots["threshold"] = float(m.group(1))
            slots["comparator"] = ">"
        m = re.search(r"\b(?:below|under)\s+(\d+(?:\.\d+)?)", text, re.I)
        if m and "threshold" not in slots:
            slots["threshold"] = float(m.group(1))
            slots["comparator"] = "<"
        m = re.search(r"\bat\s+least\s+(\d+(?:\.\d+)?)", text, re.I)
        if m:
            slots["threshold"] = float(m.group(1))
            slots["comparator"] = ">="
        m = re.search(r"\bat\s+most\s+(\d+(?:\.\d+)?)", text, re.I)
        if m:
            slots["threshold"] = float(m.group(1))
            slots["comparator"] = "<="
        m = re.search(r">=\s*(\d+(?:\.\d+)?)", text, re.I)
        if m and "threshold" not in slots:
            slots["threshold"] = float(m.group(1))
            slots["comparator"] = ">="
        m = re.search(r"<=\s*(\d+(?:\.\d+)?)", text, re.I)
        if m and "threshold" not in slots:
            slots["threshold"] = float(m.group(1))
            slots["comparator"] = "<="

        m = re.search(
            r"\bbetween\s+(\d+(?:\.\d+)?)\s+and\s+(\d+(?:\.\d+)?)", text, re.I
        )
        if m:
            slots["lower"] = float(m.group(1))
            slots["upper"] = float(m.group(2))

        # "with/having more|less than N" for group-count patterns
        m = re.search(
            r"\b(?:with|having)\s+(?:more|less|fewer)\s+than\s+(\d+(?:\.\d+)?)",
            text,
            re.I,
        )
        if m and "threshold" not in slots:
            slots["threshold"] = float(m.group(1))
            if re.search(r"\b(?:less|fewer)\s+than\b", text, re.I):
                slots["comparator"] = "<"
            else:
                slots["comparator"] = ">"

        m = re.search(r"\blast\s+(\d+)\s+days?\b", text, re.I)
        if m:
            slots["relative_days"] = int(m.group(1))

        m = re.search(
            r"\b(?:whose|where|with|having)\s+([a-z][a-z0-9_ ]{0,40}?)\s+"
            r"(?:is|are|=)\s+([a-z0-9_\-]+)",
            text,
            re.I,
        )
        if m:
            left = m.group(1).strip()
            right = m.group(2).strip()
            # Skip metric-threshold lookalikes: "whose revenue is greater than …"
            bad_right = {
                "greater",
                "less",
                "more",
                "higher",
                "lower",
                "above",
                "below",
                "over",
                "under",
                "between",
                "null",
                "not",
            }
            if right.lower() not in bad_right and not re.search(
                r"\b(greater|less|more|higher|lower|above|below|over|under)\b",
                left,
                re.I,
            ):
                slots["eq_left"] = left
                slots["eq_right"] = right

        # Prefer "is|are <status>" even without whose/where when entity-bound retrieve.
        if "eq_left" not in slots:
            m = re.search(
                r"\b([a-z][a-z0-9_ ]{0,30}?)\s+(?:is|are)\s+([a-z0-9_\-]+)\b",
                text,
                re.I,
            )
            if m:
                left = m.group(1).strip()
                right = m.group(2).strip()
                bad_right = {
                    "greater",
                    "less",
                    "more",
                    "higher",
                    "lower",
                    "above",
                    "below",
                    "over",
                    "under",
                    "between",
                    "null",
                    "not",
                    "a",
                    "an",
                    "the",
                }
                # Drop leading intent verbs from left phrase
                left = re.sub(
                    r"^(?:show|list|get|display|find|retrieve|give)\s+",
                    "",
                    left,
                    flags=re.I,
                ).strip()
                if (
                    left
                    and right.lower() not in bad_right
                    and not re.search(
                        r"\b(greater|less|more|higher|lower|how|what|which)\b",
                        left,
                        re.I,
                    )
                ):
                    slots["eq_left"] = left
                    slots["eq_right"] = right

        m = re.search(
            r"\b([a-z][a-z0-9_ ]{0,30}?)\s+"
            r"(?:is\s+not\s+null|are\s+not\s+null|has\s+been|have\s+been|"
            r"is\s+null|are\s+null|has\s+no|without|missing)\b",
            text,
            re.I,
        )
        if m:
            slots["null_expr"] = m.group(1).strip()

        m = re.search(
            r"\b(?:starts?\s+with|begins?\s+with|ends?\s+with|contains|includes|like)\s+"
            r"['\"]?([a-z0-9_\-]+)['\"]?",
            text,
            re.I,
        )
        if m:
            slots["like_value"] = m.group(1).strip()
        m = re.search(
            r"\b([a-z][a-z0-9_ ]{0,30}?)\s+"
            r"(?:starts?\s+with|begins?\s+with|ends?\s+with|contains|includes|like)\b",
            text,
            re.I,
        )
        if m:
            slots["like_expr"] = m.group(1).strip()

        if bindings.entities:
            slots["entity"] = bindings.entities[0].concept
        if bindings.metrics:
            slots["metric"] = bindings.metrics[0].concept
        if len(bindings.metrics) > 1:
            slots["metric_b"] = bindings.metrics[1].concept
        if bindings.times:
            slots["time"] = bindings.times[0].range.value
        if len(bindings.times) > 1:
            slots["time_b"] = bindings.times[1].range.value
        return slots

    @staticmethod
    def _slots_ok(
        builder: str,
        slots: dict[str, Any],
        bindings: ConceptBindings,
        text: str,
    ) -> bool:
        if builder == "rank":
            return "limit" in slots and bool(bindings.entities) and bool(bindings.metrics)
        if builder in ("aggregate", "aggregate_group"):
            # Prefer retrieve+filter over bare "total/sum" inside a SHOW … WHERE.
            if re.search(r"\b(show|list|get|display|find|retrieve)\b", text, re.I) and (
                "threshold" in slots
                or "lower" in slots
                or "eq_left" in slots
                or re.search(
                    r"\b(greater|less|more|higher|lower|above|below|between)\b",
                    text,
                    re.I,
                )
            ):
                return False
            return bool(bindings.metrics) or "count" in builder
        if builder == "count":
            return bool(bindings.entities) or bool(bindings.metrics)
        if builder == "threshold_filter":
            return "threshold" in slots and bool(bindings.metrics)
        if builder == "between_filter":
            return "lower" in slots and "upper" in slots and bool(bindings.metrics)
        if builder == "group_count_threshold":
            # Prefer metric threshold when a measure is bound (revenue > N).
            if bindings.metrics and re.search(
                r"\b(revenue|amount|price|fee|value|cost)\b", text, re.I
            ):
                return False
            return "threshold" in slots and bool(bindings.entities)
        if builder == "relative_time_filter":
            return "relative_days" in slots
        if builder == "equality_filter":
            # Avoid stealing threshold phrasing; need a concrete equality pair.
            if "threshold" in slots or "lower" in slots:
                return False
            return "eq_left" in slots and "eq_right" in slots and bool(bindings.entities)
        if builder == "null_filter":
            return bool(bindings.entities) and (
                "null_expr" in slots
                or re.search(
                    r"\b(is\s+null|is\s+not\s+null|has\s+no|have\s+no|without|missing|"
                    r"has\s+been|have\s+been)\b",
                    text,
                    re.I,
                )
            )
        if builder == "like_filter":
            return "like_value" in slots and bool(bindings.entities)
        if builder == "order_by_metric":
            # newest/oldest can order without a bound metric
            if re.search(
                r"\b(newest|oldest|latest|earliest|most\s+recent)\b", text, re.I
            ):
                return bool(bindings.entities) or bool(bindings.metrics)
            return bool(bindings.metrics) and bool(bindings.entities)
        if builder == "list_entity":
            return bool(bindings.entities)
        if builder == "time_filter":
            return bool(bindings.times)
        if builder == "compare":
            return bool(bindings.metrics)
        if builder == "change":
            return bool(bindings.metrics)
        if builder == "subquery_threshold":
            return bool(bindings.metrics) and bool(bindings.entities)
        if builder == "ratio":
            return bool(bindings.metrics)
        if builder == "unsupported_window":
            return True
        return True
