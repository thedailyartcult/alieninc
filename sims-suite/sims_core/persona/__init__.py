"""Persona core — the MatrAIx-inspired population layer for the sims stack.

Provides a correlated categorical schema, a dependency-aware DAG sampler, a
readable Persona model, and adherence/statistics helpers. Every station can
sample a persona (or a filtered cohort) and use it to seed a simulation.

Public surface:
    Persona, PersonaCohortQuery          # models
    PersonaSampler                       # DAG forward-sampler
    sample_persona, sample_cohort        # convenience wrappers
    render_schema_summary                # API schema overview
    run_controlled_study, AdherenceStudy # controlled adherence studies
    benjamini_hochberg, two_proportion_z # multiple-testing + stats helpers
    parse_query, personas_to_dicts       # API helpers
"""

from __future__ import annotations

from sims_core.persona.models import (
    Persona,
    PersonaCohortQuery,
    render_schema_summary,
)
from sims_core.persona.sampler import (
    PersonaSampler,
    sample_persona,
    sample_cohort,
    personas_to_dicts,
    parse_query,
)
from sims_core.persona.adherence import (
    AdherenceResult,
    AdherenceStudy,
    run_controlled_study,
    benjamini_hochberg,
    two_proportion_z,
)

__all__ = [
    "Persona",
    "PersonaCohortQuery",
    "render_schema_summary",
    "PersonaSampler",
    "sample_persona",
    "sample_cohort",
    "personas_to_dicts",
    "parse_query",
    "AdherenceResult",
    "AdherenceStudy",
    "run_controlled_study",
    "benjamini_hochberg",
    "two_proportion_z",
]