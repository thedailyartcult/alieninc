"""Persona model — one sampled person as a readable profile.

A :class:`Persona` is a dict of dimension_id -> value under the shared schema,
plus natural-language descriptions so it reads as a *profile* rather than a
vector of categorical codes (MatrAIx: "the result reads as a profile rather
than a list of categorical values"). Personas are the atomic unit the
simulation stack branches over: Alpha Zero simulates one person's life,
Kriegspiel pairs a persona's psychology with a doctrine, Platoon captures the
population an objective affects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from sims_core.persona.schema import DIMENSIONS, TOPOLOGICAL_ORDER, categories


@dataclass
class Persona:
    """One fully-specified persona under the shared schema.

    ``values`` maps every dimension id to one allowed value. ``descriptions``
    maps the same ids to natural-language phrases for the same value, so the
    profile reads as prose.
    """

    values: dict[str, str]
    descriptions: dict[str, str] = field(default_factory=dict)
    provenance: Optional[dict] = None

    def __post_init__(self) -> None:
        if not self.descriptions:
            self.descriptions = {
                dim_id: DIMENSIONS[dim_id].description(value)
                for dim_id, value in self.values.items()
                if dim_id in DIMENSIONS
            }

    def get(self, dim_id: str, default: Optional[str] = None) -> Optional[str]:
        """The assigned value for a dimension (or ``default`` if unassigned)."""
        return self.values.get(dim_id, default)

    def profile_text(self) -> str:
        """Render the persona as a readable natural-language profile."""
        ordered = [dim_id for dim_id in TOPOLOGICAL_ORDER if dim_id in self.values]
        parts = []
        for dim_id in ordered:
            desc = self.descriptions.get(dim_id)
            if desc:
                parts.append(desc)
        if not parts:
            return "A person."
        # Smooth grammar: first fragment becomes the subject.
        opening = parts[0]
        rest = parts[1:]
        if not rest:
            return opening.capitalize() + "."
        text = opening + ", " + ", ".join(rest) + "."
        return text[:1].upper() + text[1:]

    def summary(self) -> str:
        """A compact one-line summary (for dashboards / logs)."""
        return ", ".join(
            f"{dim_id}={v}" for dim_id, v in self.values.items()
        )

    def to_dict(self) -> dict:
        return {
            "values": dict(self.values),
            "descriptions": dict(self.descriptions),
            "profile": self.profile_text(),
            "provenance": self.provenance,
        }

    def subset(self, dim_ids: list[str]) -> dict:
        """Values limited to the given dimensions (for cohort analysis)."""
        return {d: self.values[d] for d in dim_ids if d in self.values}


@dataclass
class PersonaCohortQuery:
    """A population query: which personas belong to the evaluation cohort.

    Mirrors MatrAIx's 'cohort = population query + sampling procedure'. A query
    is a set of dimension==value filters; ``max_tries`` bounds the rejection
    sampling effort so an unsatisfiable filter fails loudly instead of
    spinning.
    """

    filters: dict[str, str] = field(default_factory=dict)
    max_tries: int = 4000

    def matches(self, persona: Persona) -> bool:
        for dim_id, value in self.filters.items():
            if persona.get(dim_id) != value:
                return False
        return True

    def to_dict(self) -> dict:
        return {
            "filters": dict(self.filters),
            "max_tries": self.max_tries,
        }


def render_schema_summary() -> dict:
    """Schema overview for the API: categories, dimensions, value counts."""
    cats: list[dict] = []
    for cat in categories():
        dims = []
        for dim_id in TOPOLOGICAL_ORDER:
            dim = DIMENSIONS[dim_id]
            if dim.category != cat:
                continue
            dims.append({
                "id": dim_id,
                "values": list(dim.values),
                "parents": list(dim.parents),
            })
        cats.append({"category": cat, "dimensions": dims})
    return {
        "dimension_count": len(DIMENSIONS),
        "categories": cats,
        "order": list(TOPOLOGICAL_ORDER),
    }