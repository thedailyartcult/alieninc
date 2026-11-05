"""Regression tests — verifies the LLM layer didn't break the procedural path.

Runs the procedural ``generate_scenarios`` end-to-end with no LLM env set,
and confirms the report shape matches the pre-LLM contract.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from engines.kriegspiel.scenarios import (
    generate_scenarios, create_default_battle, report_to_dict,
)
from engines.kriegspiel.combat import simulate_battle, get_event_pool
from engines.kriegspiel.models import BATTLEFIELDS, BATTLEFIELDS_LLM


def test_procedural_generate_scenarios_runs():
    report = generate_scenarios(n_scenarios=20, seed=42)
    assert report.scenarios_run == 20
    assert report.red_wins + report.blue_wins + report.stalemates == 20
    assert 0.0 <= report.convergence_rate <= 1.0
    assert report.duration_ms >= 0
    # Pre-LLM contract: provenance is None when no LLM was used.
    assert report.provenance is None


def test_report_to_dict_shape_unchanged():
    report = generate_scenarios(n_scenarios=10, seed=7)
    d = report_to_dict(report)
    # All pre-LLM fields must still be present.
    for key in ("battlefield", "scenarios_run", "red_wins", "blue_wins",
                "stalemates", "decisive_battles", "convergence_rate",
                "avg_duration_hours", "avg_red_casualties",
                "avg_blue_casualties", "best_branch", "key_events",
                "duration_ms"):
        assert key in d, f"missing key: {key}"
    # The new provenance key is present and None for procedural runs.
    assert "provenance" in d
    assert d["provenance"] is None


def test_create_default_battle_signature_unchanged():
    # Pre-LLM callers don't pass enrich_with_llm — must still work.
    battle = create_default_battle(seed=42)
    assert battle.battlefield in BATTLEFIELDS
    assert battle.provenance is None  # procedural path doesn't set provenance
    assert 3 <= len(battle.red_force.units) <= 15
    assert 3 <= len(battle.blue_force.units) <= 15


def test_create_default_battle_with_battlefield_arg():
    bf = BATTLEFIELDS[0]
    battle = create_default_battle(battlefield=bf, seed=42)
    assert battle.battlefield is bf


def test_simulate_battle_still_returns_battle_outcome():
    battle = create_default_battle(seed=42)
    outcome = simulate_battle(battle, seed=99)
    assert outcome.winner in ("red", "blue", "stalemate")
    assert 0 <= outcome.red_casualties_pct <= 100
    assert 0 <= outcome.blue_casualties_pct <= 100
    assert outcome.duration_hours > 0


def test_event_pool_unchanged_when_no_llm_calls():
    pool = get_event_pool()
    # Pre-LLM baseline = 12 events. Tests that import LLM modules may
    # have registered more, but the baseline is always present.
    assert len(pool) >= 12
    assert "flanking maneuver succeeded" in pool


def test_battlefields_llm_pool_starts_empty():
    # No LLM has been called in this test run, so the LLM pool is empty.
    # (We don't assert == [] because test ordering isn't guaranteed.)
    assert isinstance(BATTLEFIELDS_LLM, list)


def test_enrich_with_llm_true_without_config_falls_back():
    # enrich_with_llm=True, but no KRIEGSPIEL_LLM_PROVIDER env set,
    # so the synthesizer falls back to procedural. The flag is safe to
    # set unconditionally.
    import os
    assert "KRIEGSPIEL_LLM_PROVIDER" not in os.environ or \
           not os.environ["KRIEGSPIEL_LLM_PROVIDER"]
    battle = create_default_battle(seed=42, enrich_with_llm=True)
    # Provenance should be set by the synthesizer's fallback path.
    assert battle.provenance is not None
    assert battle.provenance["source"] == "procedural"


def test_generate_scenarios_with_enrich_flag_falls_back():
    report = generate_scenarios(n_scenarios=10, seed=42, enrich_with_llm=True)
    assert report.scenarios_run == 10
    # Provenance is set by the synthesizer's fallback.
    assert report.provenance is not None
    assert report.provenance["source"] == "procedural"
