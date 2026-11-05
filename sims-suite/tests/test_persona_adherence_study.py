"""Controlled-adherence study tests (MatrAIx 400-trial design).

Covers ``sims_core.persona.adherence.run_controlled_study`` — the core
validation primitive that checks whether a persona's *declared* attribute is
actually expressed (or correctly suppressed) in observed behavior. This is the
highest-value untested module.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pytest

from sims_core.persona import sample_cohort, parse_query, Persona
from sims_core.persona.adherence import run_controlled_study
from sims_core.persona.schema import DIMENSIONS


def _perfect_behavior(persona, seed):
    """A behavior that ALWAYS expresses the declared value -> 100% adherence."""
    return (persona.get("risk_tolerance"), {"source": "perfect"})


def _inverted_behavior(persona, seed):
    """A behavior that expresses the OPPOSITE of declared -> 0% adherence."""
    declared = persona.get("risk_tolerance")
    # risk_tolerance values: very_low, low, moderate, high, very_high
    inverted = {"very_low": "very_high", "low": "high", "moderate": "moderate",
                "high": "low", "very_high": "very_low"}
    return (inverted[declared], {"source": "inverted"})


def _random_behavior(persona, seed):
    """Random behavior -> ~50% adherence."""
    import random
    rng = random.Random(seed)
    vals = list(DIMENSIONS["risk_tolerance"].values)
    return (rng.choice(vals), {"source": "random"})


def test_perfect_behavior_gives_full_adherence():
    # The study only tests personas whose declared value matches the arm poles
    # (default: first and last schema values). Use personas at those poles.
    personas = sample_cohort(40, seed=1, query=parse_query({"risk_tolerance": "very_high"}))
    study = run_controlled_study(personas, "risk_tolerance", _perfect_behavior, seed=5)
    assert study.n_trials == len(personas)
    assert study.overall_rate == 1.0
    assert study.n_match == len(personas)
    # The negative arm (declared 'very_high' = values[-1]) is populated.
    assert "negative" in study.per_attribute["risk_tolerance"]


def test_inverted_behavior_gives_zero_adherence():
    personas = sample_cohort(40, seed=1, query=parse_query({"risk_tolerance": "very_high"}))
    study = run_controlled_study(personas, "risk_tolerance", _inverted_behavior, seed=5)
    assert study.overall_rate == 0.0
    assert study.n_match == 0


def test_random_behavior_near_fifty_percent():
    # Mix of both poles so both arms are populated.
    personas = (sample_cohort(150, seed=1, query=parse_query({"risk_tolerance": "very_high"}))
                + sample_cohort(150, seed=1, query=parse_query({"risk_tolerance": "very_low"})))
    study = run_controlled_study(personas, "risk_tolerance", _random_behavior, seed=7)
    # With a 5-value attribute, random expression gives ~20% direct + suppression
    # logic; overall rate should be well above 0 and well below 1.
    assert 0.1 < study.overall_rate < 0.9
    assert "positive" in study.per_attribute["risk_tolerance"]
    assert "negative" in study.per_attribute["risk_tolerance"]


def test_correct_suppression_counts_as_match():
    """A persona declared 'very_high' that expresses 'high' (not the opposite
    'very_low') correctly suppresses and counts as a match."""
    # Force a persona with risk_tolerance='very_high' and a behavior that
    # returns a nearby value ('high') -> should be a match (correct suppression).
    personas = sample_cohort(20, seed=1, query=parse_query({"risk_tolerance": "very_high"}))
    def _nearby(persona, seed):
        return ("high", {"source": "nearby"})

    study = run_controlled_study(personas, "risk_tolerance", _nearby, seed=5)
    # All personas are in the positive arm (declared 'very_high'); behavior says
    # 'high' which is NOT the opposite ('very_low'), so all are matches.
    assert study.overall_rate == 1.0


def test_unknown_attribute_raises():
    personas = sample_cohort(5, seed=1)
    with pytest.raises(ValueError):
        run_controlled_study(personas, "not_a_dim", _perfect_behavior, seed=1)


def test_arm_poles_custom():
    """A custom arm_poles mapping is honored."""
    personas = sample_cohort(20, seed=1, query=parse_query({"risk_tolerance": "high"}))
    study = run_controlled_study(
        personas, "risk_tolerance", _perfect_behavior,
        arm_poles={"aggressive": "high", "defensive": "low"}, seed=5,
    )
    # Only the 'aggressive' arm has personas (all 'high'); no 'low' personas.
    assert "aggressive" in study.per_attribute["risk_tolerance"]
    assert "defensive" not in study.per_attribute["risk_tolerance"]


def test_evidence_and_trials_are_recorded():
    # 'very_high' is values[-1] -> the negative arm in the default mapping.
    personas = sample_cohort(10, seed=1, query=parse_query({"risk_tolerance": "very_high"}))
    study = run_controlled_study(personas, "risk_tolerance", _perfect_behavior, seed=5)
    assert len(study.trials) == len(personas)
    first = study.trials[0]
    assert first.evidence == {"source": "perfect"}
    assert first.match is True
    assert first.arm == "negative"
    assert first.declared == first.observed


def test_deterministic_per_seed():
    personas = sample_cohort(40, seed=1, query=parse_query({"risk_tolerance": "very_high"}))
    a = run_controlled_study(personas, "risk_tolerance", _random_behavior, seed=11)
    b = run_controlled_study(personas, "risk_tolerance", _random_behavior, seed=11)
    assert a.overall_rate == b.overall_rate
    assert [t.observed for t in a.trials] == [t.observed for t in b.trials]


def test_to_dict_serializable():
    personas = sample_cohort(10, seed=1, query=parse_query({"risk_tolerance": "very_high"}))
    study = run_controlled_study(personas, "risk_tolerance", _perfect_behavior, seed=5)
    d = study.to_dict()
    assert d["n_trials"] == len(personas)
    assert d["overall_rate"] == 1.0
    assert len(d["trials"]) == len(personas)
    assert "per_attribute" in d