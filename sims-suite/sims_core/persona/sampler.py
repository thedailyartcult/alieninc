"""Persona sampling — dependency-aware forward sampling over the schema DAG.

Implements MatrAIx's synthesis idea: each dimension is drawn conditional on its
parents, in parent-first topological order, with

    p(x_i = v | x_Pa(i))  ∝  prior_i(v) · Π adjust_i(v; parent=p) · mask_i(v)

The prior supplies the population marginal, contextual adjustments re-weight
values that are more/less common given the drawn parents, and the compatibility
mask hard-rejects impossible combinations (e.g. primary language English with
English proficiency "none"). Rare-but-valid profiles survive because adjustment
only re-weights; only the mask can zero a value out.

Determinism: all draws flow from a single ``random.Random(seed)`` in a fixed
topological order, so the same seed reproduces the same persona / cohort.
"""

from __future__ import annotations

import random
from typing import Optional

from sims_core.persona.schema import (
    DIMENSIONS,
    TOPOLOGICAL_ORDER,
    validate_value,
)
from sims_core.persona.models import Persona, PersonaCohortQuery


class PersonaSampler:
    """Forward-samples personas from the dependency graph."""

    def __init__(self, seed: Optional[int] = None) -> None:
        self._seed = seed

    def sample(self, seed: Optional[int] = None, query: Optional[PersonaCohortQuery] = None) -> Persona:
        """Draw one full persona.

        When ``query`` is given, rejection-samples until the persona matches the
        query filters (retrying up to ``query.max_tries``), so a cohort drawn
        with the same seed is reproducible. A hard filter that cannot be
        satisfied raises ``ValueError``.
        """
        rng = random.Random(seed if seed is not None else self._seed)
        query = query or PersonaCohortQuery()

        for _ in range(query.max_tries):
            values: dict[str, str] = {}
            for dim_id in TOPOLOGICAL_ORDER:
                values[dim_id] = self._draw_dimension(rng, dim_id, values)
            persona = Persona(values=values)
            if query.matches(persona):
                return persona

        raise ValueError(
            f"no persona matched the query within {query.max_tries} attempts: "
            f"{query.filters!r}"
        )

    def sample_cohort(
        self,
        n: int,
        seed: Optional[int] = None,
        query: Optional[PersonaCohortQuery] = None,
    ) -> list[Persona]:
        """Draw ``n`` personas, optionally filtered by a cohort query.

        Every persona uses an independent seed derived from the base seed, so
        the cohort is reproducible and order-stable.
        """
        rng = random.Random(seed if seed is not None else self._seed)
        out: list[Persona] = []
        for i in range(n):
            out.append(self.sample(seed=rng.randint(0, 2**31 - 1), query=query))
        return out

    # ------------------------------------------------------------------ draw
    def _draw_dimension(self, rng: random.Random, dim_id: str, values: dict[str, str]) -> str:
        dim = DIMENSIONS[dim_id]
        weights: dict[str, float] = {}
        for value in dim.values:
            weight = dim.prior.get(value, 0.0)
            for parent_id in dim.parents:
                parent_value = values.get(parent_id)
                if parent_value is None:
                    continue
                table = dim.adjustments.get(parent_id)
                if table:
                    weight *= table.get(parent_value, {}).get(value, 1.0)
                mask = dim.masks.get(parent_id, {}).get(parent_value)
                if mask and value in mask:
                    weight = 0.0
            if weight > 0:
                weights[value] = weight
        if not weights:
            raise ValueError(
                f"no valid value for {dim_id} given parents {values!r}"
            )
        return rng.choices(list(weights.keys()), weights=list(weights.values()), k=1)[0]


def sample_persona(seed: Optional[int] = None, query: Optional[PersonaCohortQuery] = None) -> Persona:
    """Convenience wrapper around :class:`PersonaSampler`."""
    return PersonaSampler(seed=seed).sample(seed=seed, query=query)


def sample_cohort(
    n: int,
    seed: Optional[int] = None,
    query: Optional[PersonaCohortQuery] = None,
) -> list[Persona]:
    """Convenience wrapper around :class:`PersonaSampler.sample_cohort`."""
    return PersonaSampler(seed=seed).sample_cohort(n, seed=seed, query=query)


def personas_to_dicts(personas: list[Persona]) -> list[dict]:
    """Serialize a list of personas for API responses."""
    return [p.to_dict() for p in personas]


def parse_query(filters: Optional[dict]) -> PersonaCohortQuery:
    """Build a :class:`PersonaCohortQuery` from a raw JSON dict.

    Unknown dimensions / invalid values raise ``ValueError`` so the API can
    respond with a 400 rather than silently sampling unfiltered.
    """
    if not filters:
        return PersonaCohortQuery()
    for dim_id, value in filters.items():
        if dim_id not in DIMENSIONS:
            raise ValueError(f"unknown persona dimension: {dim_id}")
        if not validate_value(dim_id, value):
            raise ValueError(
                f"invalid value {value!r} for dimension {dim_id} "
                f"(allowed: {list(DIMENSIONS[dim_id].values)})"
            )
    return PersonaCohortQuery(filters=dict(filters))