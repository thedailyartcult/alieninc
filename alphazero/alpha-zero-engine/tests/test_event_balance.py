"""Event balance tests — Phase 4 side-quest: stacked health damage no longer
kills healthy young characters, and fragile characters can't death-spiral.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.character import Character
from engine.events import EventEngine, build_life_events
from engine.simulation import SimulationOrchestrator, SimulationConfig
from finance.portfolio import PortfolioEngine


def make_character(health: int = 70, age: int = 25, seed: int = 42) -> Character:
    return Character(
        name="Test", age=age, happiness=50, health=health,
        smarts=50, looks=50, karma=50, money=0, seed=seed,
    )


def test_single_tick_health_damage_capped():
    """Even three unlucky health events can't drop health by more than 30 in one tick."""
    engine = EventEngine(build_life_events())
    for seed in range(30):
        char = make_character(health=90, age=40, seed=seed)
        results = engine.roll_events(char, max_events=3)
        total_health_damage = sum(
            r["changes"].get("health", 0)
            for r in results
            if r["changes"].get("health", 0) < 0
        )
        assert total_health_damage >= -30.000001, seed


def test_fragile_character_does_not_spiral():
    """A character at low health rarely gets more health damage; recovery is boosted."""
    engine = EventEngine(build_life_events())
    fragile = make_character(health=25, age=40, seed=99)
    results = engine.roll_events(fragile, max_events=3)
    health_after = fragile.health
    assert health_after >= 10, f"death spiral: health dropped to {health_after}"
    # No severe event (health_scare/chronic/pandemic/war) can fire below 31 health
    severe = {"health_scare", "chronic_illness", "pandemic", "war"}
    assert not (severe & {r["event_id"] for r in results})


def test_young_character_survives_20s():
    """A normal 20-year-old with bad luck should not die in their 20s."""
    from engine.fsm import FSM
    engine = EventEngine(build_life_events())
    deaths = 0
    for seed in range(50):
        char = make_character(health=70, age=20, seed=seed)
        fsm = FSM(seed=seed)
        for year in range(20):  # ages 20..39
            fsm._natural_decay(char)
            engine.roll_events(char, max_events=3)
            if char.health <= 0:
                deaths += 1
                break
            char.age += 1
    assert deaths == 0, f"{deaths}/50 characters died in their 20s"


def test_full_life_balance_avg_lifespan():
    """Multiverse average lifespan should exceed 60 (healthy adults)."""
    cfg = SimulationConfig(name="Balance", age=25, num_universes=100, max_workers=2, seed=42)
    orch = SimulationOrchestrator(cfg)
    report = orch.run_multiverse()
    assert report.avg_years_lived >= 60, f"avg lifespan only {report.avg_years_lived:.1f}"


def test_portfolio_still_works_with_balance_changes():
    """The portfolio hot path is untouched by event balance changes."""
    cfg = SimulationConfig(name="Fin", age=25, initial_portfolio=100000, seed=5)
    orch = SimulationOrchestrator(cfg)
    result = orch.run_with_portfolio("balanced")
    assert result["steps"] > 20
    assert result["final_portfolio_value"] > 0
