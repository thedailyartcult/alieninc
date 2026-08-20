"""Population-context enrichment tests.

The persona cohort is now wired into Remnants / CC / Awareness as an
'affected population' context: a sampled cohort is distilled into readability
and vulnerability profiles that a station can reason over, and attached to the
report additively (no regression to existing engine contracts).
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sims_core.persona import sample_cohort, parse_query
from sims_core.persona.bridges.population_context import (
    population_context, enrich_report, sample_population_context,
    digital_defense_quality, population_resilience, population_reach,
)


def test_empty_cohort_returns_notes():
    ctx = population_context([], "empty")
    assert ctx["cohort_size"] == 0
    assert "notes" in ctx


def test_population_context_distributions():
    cohort = sample_cohort(50, seed=42)
    ctx = population_context(cohort, "test")
    assert ctx["cohort_size"] == 50
    assert ctx["cohort_label"] == "test"
    assert "age_bracket" in ctx["distributions"]
    assert "region" in ctx["distributions"]
    assert "digital_fluency" in ctx["distributions"]
    # Distributions sum to ~1.
    for dist in ctx["distributions"].values():
        assert abs(sum(dist.values()) - 1.0) < 0.02
    assert 0.0 <= ctx["readability"]["readability_index"] <= 100.0
    assert 0.0 <= ctx["readability"]["vulnerability_index"] <= 100.0


def test_readability_and_vulnerability_contrast():
    """The whole point: a rural, low-fluency, low-income population is harder to
    reach and more vulnerable than an urban, high-fluency, affluent one."""
    poor = sample_cohort(100, seed=42, query=parse_query({
        "urbanicity": "rural", "income_bracket": "low", "digital_fluency": "low"}))
    affluent = sample_cohort(100, seed=7, query=parse_query({
        "urbanicity": "urban", "income_bracket": "very_high", "digital_fluency": "high"}))

    poor_r = population_context(poor, "poor")["readability"]
    affluent_r = population_context(affluent, "affluent")["readability"]

    assert poor_r["readability_index"] < affluent_r["readability_index"]
    assert poor_r["vulnerability_index"] > affluent_r["vulnerability_index"]
    assert poor_r["low_fluency_share"] > affluent_r["low_fluency_share"]


def test_enrich_report_is_additive():
    report = {"scenarios_run": 10, "survival_rate": 0.8}
    cohort = sample_cohort(20, seed=1)
    enriched = enrich_report(report, cohort, "x")
    # Original report untouched; enriched copy carries the context.
    assert "population_context" not in report
    assert enriched["scenarios_run"] == 10
    assert enriched["survival_rate"] == 0.8
    assert "population_context" in enriched
    assert enriched["population_context"]["cohort_size"] == 20


def test_sample_population_context_raw_query():
    ctx = sample_population_context({"urbanicity": "urban"}, n=40, seed=1, cohort_label="t")
    assert ctx["cohort_size"] == 40
    assert ctx["cohort_label"] == "t"


def test_sample_population_context_invalid_query():
    import pytest
    with pytest.raises(ValueError):
        sample_population_context({"not_a_dim": "x"}, n=10, seed=1)


def _cohort_ctx(seed, query):
    cohort = sample_cohort(60, seed=seed, query=parse_query(query))
    return population_context(cohort, "t")


def test_digital_defense_quality():
    """A low-fluency, low-trust population must yield a lower defense quality
    than a high-fluency, high-trust one — driving the engine-internal CC effect."""
    vuln = _cohort_ctx(42, {"digital_fluency": "low", "income_bracket": "low"})
    res = _cohort_ctx(7, {"digital_fluency": "high", "income_bracket": "very_high"})
    vq = digital_defense_quality(vuln)
    rq = digital_defense_quality(res)
    assert vq < rq
    assert 0.3 <= vq <= 1.0
    assert 0.3 <= rq <= 1.0


def test_cc_engine_internal_vulnerability_effect():
    """The affected population's defense quality must change the CC attack
    simulation's breach rate *inside the engine*, not just the report."""
    from engines.cc.attack import generate_attack_scenarios, report_to_dict

    vuln = _cohort_ctx(42, {"digital_fluency": "low", "income_bracket": "low"})
    res = _cohort_ctx(7, {"digital_fluency": "high", "income_bracket": "very_high"})
    vq = digital_defense_quality(vuln)
    rq = digital_defense_quality(res)

    vd = report_to_dict(generate_attack_scenarios(n_scenarios=200, seed=1, defense_quality=vq))
    rd = report_to_dict(generate_attack_scenarios(n_scenarios=200, seed=1, defense_quality=rq))
    assert vd["breach_rate"] > rd["breach_rate"]


def test_population_resilience_and_remnants_effect():
    """A fragile population must yield lower resilience, and the Remnants
    engine itself must produce fewer survivors (engine-internal, not post-hoc)."""
    from engines.remnants.continuity import generate_continuity_scenarios, report_to_dict

    vuln = _cohort_ctx(42, {"income_bracket": "low", "age_bracket": "65+"})
    res = _cohort_ctx(7, {"income_bracket": "very_high", "age_bracket": "25-34"})
    vr = population_resilience(vuln)
    rr = population_resilience(res)
    assert vr < rr
    assert 0.3 <= vr <= 1.0

    vd = report_to_dict(generate_continuity_scenarios(n_scenarios=300, seed=1, population_resilience=vr))
    rd = report_to_dict(generate_continuity_scenarios(n_scenarios=300, seed=1, population_resilience=rr))
    assert vd["survival_rate"] < rd["survival_rate"]


def test_population_reach_and_awareness_effect():
    """A hard-to-reach population must yield lower reach, and the Awareness
    engine itself must produce lower response success (engine-internal)."""
    from engines.awareness.response import generate_response_scenarios, report_to_dict

    vuln = _cohort_ctx(42, {"digital_fluency": "low", "urbanicity": "rural"})
    res = _cohort_ctx(7, {"digital_fluency": "high", "urbanicity": "urban"})
    vr = population_reach(vuln)
    rr = population_reach(res)
    assert vr < rr
    assert 0.3 <= vr <= 1.0

    vd = report_to_dict(generate_response_scenarios(n_scenarios=300, seed=1, population_reach=vr))
    rd = report_to_dict(generate_response_scenarios(n_scenarios=300, seed=1, population_reach=rr))
    assert vd["best_playbook"]["success_rate"] < rd["best_playbook"]["success_rate"]