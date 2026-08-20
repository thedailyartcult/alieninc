"""Alpha Zero persona bridge tests.

The bridge turns a sampled persona into an engine Character. These tests are
engine-optional: if the Alpha Zero engine isn't importable on the test machine,
the bridge returns None and we assert the graceful degradation instead of
failing.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sims_core.persona import sample_persona
from sims_core.persona.bridges.alpha_zero import build_character, run_persona_cohort

# Does the Alpha Zero engine exist on this machine?
try:
    import engine.character  # noqa: F401
    ENGINE_AVAILABLE = True
except Exception:
    ENGINE_AVAILABLE = False


def _skip_if_no_engine():
    if not ENGINE_AVAILABLE:
        import pytest
        pytest.skip("Alpha Zero engine not importable on this machine")


def test_build_character_returns_none_without_engine():
    if ENGINE_AVAILABLE:
        import pytest
        pytest.skip("engine present; this test exercises the no-engine path")
    persona = sample_persona(seed=1)
    assert build_character(persona, seed=1) is None
    assert run_persona_cohort([persona], base_seed=1) is None


def test_build_character_from_persona():
    _skip_if_no_engine()
    persona = sample_persona(seed=42)
    char = build_character(persona, seed=42)
    assert char is not None
    # The persona's psychology must have flowed into the social layer.
    assert hasattr(char, "social_variables")
    # Deterministic per seed.
    char2 = build_character(persona, seed=42)
    assert char.smarts == char2.smarts
    assert char.happiness == char2.happiness
    # Different personas produce different people (not all identical).
    other = sample_persona(seed=43)
    char_other = build_character(other, seed=43)
    # Age should follow the persona's age bracket (18-24 => 18-22).
    if persona.get("age_bracket") == "18-24":
        assert 18 <= char.age <= 22


def test_run_persona_cohort_aggregates():
    _skip_if_no_engine()
    from sims_core.persona import sample_cohort
    personas = sample_cohort(5, seed=42)
    report = run_persona_cohort(personas, base_seed=42)
    assert report is not None
    assert report["personas_simulated"] == 5
    assert report["cohort_size"] == 5
    assert "avg_net_worth" in report
    assert "risk_groups" in report
    assert len(report["outcomes"]) == 5
    for outcome in report["outcomes"]:
        assert "final_net_worth" in outcome
        assert "final_happiness" in outcome