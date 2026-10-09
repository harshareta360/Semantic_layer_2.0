from __future__ import annotations

from dataclasses import dataclass, field

from semantic_layer.intent.models.ast import DimensionRef, EntityRef, MetricRef, TimeFilter
from semantic_layer.intent.models.enums import TimeRange
from semantic_layer.normalization.models import NormalizedQuestion, RecognizedConcept


@dataclass
class ConceptBindings:
    entities: list[EntityRef] = field(default_factory=list)
    metrics: list[MetricRef] = field(default_factory=list)
    times: list[TimeFilter] = field(default_factory=list)
    raw_concepts: list[RecognizedConcept] = field(default_factory=list)

    def as_dimension(self, concept: str) -> DimensionRef:
        """Assign dimension role without changing canonical concept."""
        return DimensionRef(concept=concept)

    def first_entity(self) -> EntityRef | None:
        return self.entities[0] if self.entities else None

    def first_metric(self) -> MetricRef | None:
        return self.metrics[0] if self.metrics else None

    def first_time(self) -> TimeFilter | None:
        return self.times[0] if self.times else None


class ConceptBinder:
    """Map recognized_concepts → semantic AST references (role assigned by pattern)."""

    def bind(self, normalized: NormalizedQuestion) -> ConceptBindings:
        bindings = ConceptBindings(raw_concepts=list(normalized.recognized_concepts))
        seen_e: set[str] = set()
        seen_m: set[str] = set()
        seen_t: set[str] = set()
        for concept in normalized.recognized_concepts:
            if concept.category in ("ENTITY", "DIMENSION"):
                if concept.canonical not in seen_e:
                    seen_e.add(concept.canonical)
                    bindings.entities.append(EntityRef(concept=concept.canonical))
            elif concept.category == "MEASURE":
                if concept.canonical not in seen_m:
                    seen_m.add(concept.canonical)
                    bindings.metrics.append(MetricRef(concept=concept.canonical))
            elif concept.category == "TIME":
                if concept.canonical not in seen_t:
                    seen_t.add(concept.canonical)
                    try:
                        tr = TimeRange(concept.canonical)
                    except ValueError:
                        continue
                    bindings.times.append(TimeFilter(range=tr))
        return bindings
