"""Persona sampler tests — schema, determinism, dependencies, masks, cohorts.

Validates the MatrAIx-inspired DAG sampling core: correlated draws, the
compatibility-mask guarantee (primary language English => English proficiency
cannot be "none"), deterministic reproduction per seed, and filtered cohort
sampling.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sims_core.persona import (
    sample_persona, sample_cohort, parse_query, render_schema_summary,
    PersonaSampler, PersonaCohortQuery,
)
from sims_core.persona.schema import DIMENSIONS, TOPOLOGICAL_ORDER, validate_value


def test_schema_has_correlated_dimensions_across_groups():
    schema = render_schema_summary()
    assert schema["dimension_count"] == 25
    cats = [c["category"] for c in schema["categories"]]
    assert "background" in cats
    assert "psychology" in cats
    assert "capability" in cats
    assert "behavior" in cats
    assert "lifestyle" in cats
    # Every dimension has at least two values and a normalized prior.
    for dim_id, dim in DIMENSIONS.items():
        assert len(dim.values) >= 2, dim_id
        assert abs(sum(dim.prior.values()) - 1.0) < 1e-6, dim_id


def test_sampler_is_deterministic_per_seed():
    p1 = sample_persona(seed=7)
    p2 = sample_persona(seed=7)
    assert p1.values == p2.values
    assert p1.profile_text() == p2.profile_text()
    assert len(p1.profile_text()) > 40  # reads as prose, not a code vector


def test_sampler_produces_valid_values_only():
    for seed in range(50):
        p = sample_persona(seed=seed)
        for dim_id, value in p.values.items():
            assert validate_value(dim_id, value), f"{dim_id}={value!r} invalid"


def test_english_proficiency_mask_is_enforced():
    """The paper's canonical compatibility rule: a native English speaker
    cannot have English proficiency 'none'."""
    for seed in range(200):
        p = sample_persona(seed=seed)
        if p.get("primary_language") == "english":
            assert p.get("english_proficiency") != "none", (
                f"mask violated at seed {seed}: {p.summary()}"
            )


def test_dependency_relationships_hold_statistically():
    """Correlated draws: education_level should be high in the 25-34 bracket
    more often than in the 65+ bracket."""
    young_high_edu = 0
    old_high_edu = 0
    N = 400
    for seed in range(N):
        p = sample_persona(seed=seed)
        if p.get("age_bracket") == "25-34" and p.get("education_level") in (
            "bachelors", "postgrad"):
            young_high_edu += 1
        if p.get("age_bracket") == "65+" and p.get("education_level") in (
            "bachelors", "postgrad"):
            old_high_edu += 1
    # 25-34 should have more postgrad/bachelors than 65+ given our priors.
    assert young_high_edu > old_high_edu


def test_cohort_filter_is_exact():
    cohort = sample_cohort(
        30,
        seed=42,
        query=parse_query({
            "age_bracket": "25-34",
            "region": "europe",
            "risk_tolerance": "high",
        }),
    )
    assert len(cohort) == 30
    for p in cohort:
        assert p.get("age_bracket") == "25-34"
        assert p.get("region") == "europe"
        assert p.get("risk_tolerance") == "high"


def test_cohort_reproducible_per_seed():
    a = sample_cohort(10, seed=5)
    b = sample_cohort(10, seed=5)
    assert [p.values for p in a] == [p.values for p in b]


def test_unsatisfiable_query_fails_loudly():
    import pytest
    with pytest.raises(ValueError):
        # Primary language English + English proficiency "none" is impossible.
        sample_persona(
            seed=1,
            query=PersonaCohortQuery(
                filters={"primary_language": "english", "english_proficiency": "none"},
                max_tries=50,
            ),
        )


def test_parse_query_rejects_unknown_dimension():
    import pytest
    with pytest.raises(ValueError):
        parse_query({"not_a_dimension": "x"})


def test_parse_query_rejects_invalid_value():
    import pytest
    with pytest.raises(ValueError):
        parse_query({"age_bracket": "999"})