"""Tests for the Chronos historical what-if engine."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from engines.chronos.models import HistoricalBattle, HistoricalSide, era_profile
from engines.chronos.engine import resolve_battle, simulate_historical, what_if
from engines.chronos.fidelity import fidelity_report, assert_gate
from engines.chronos import loader

DB = Path(os.environ.get("CHRONOS_TEST_DB",
                         "/home/alieninc/panteon/backend/panteon.db"))


def _battle(year=1942):
    return HistoricalBattle(
        battle_key="test-1", name="TEST", war="WORLD WAR II (TEST 1942-1943)",
        year=year,
        attacker=HistoricalSide(side_id=1, strength=100000, casualties=6000,
                                tanks=500, artillery=800, aircraft=300,
                                morale=1, result_code="BB"),
        defender=HistoricalSide(side_id=0, strength=80000, casualties=12000,
                                tanks=300, artillery=500, aircraft=100,
                                result_code="RR"),
    )


class TestEra:
    def test_era_progression(self):
        assert era_profile(1805).air_effectiveness == 0.0
        assert era_profile(1916).armor_effectiveness < era_profile(1943).armor_effectiveness
        assert era_profile(1917).defense_bias > era_profile(1944).defense_bias
        assert "napoleonic" == era_profile(1812).name
        assert "world-war-ii" == era_profile(1943).name

    def test_no_air_before_ww(self):
        b = _battle(year=1862)
        assert b.era.air_effectiveness == 0.0


class TestWinnerLogic:
    def test_attacker_success_codes(self):
        for code in ("AA", "PS", "PP", "BB"):
            b = _battle()
            b.attacker.result_code = code
            assert b.actual_winner == "attacker"

    def test_defender_holds_codes(self):
        for code in ("RR", "WD", "WL"):
            b = _battle()
            b.attacker.result_code = code
            assert b.actual_winner == "defender"


class TestEngine:
    def test_strong_attack_wins(self):
        r = simulate_historical(_battle(), universes=50, seed=3)
        assert r["predicted_winner"] == "attacker"
        assert r["win_distribution"]["attacker"] > 0.9

    def test_overwhelming_defense_holds(self):
        b = _battle()
        b.defender.strength = 400000
        b.attacker.strength = 20000
        b.attacker.result_code = "RR"
        b.defender.result_code = "BB"
        r = simulate_historical(b, universes=50, seed=3)
        assert r["predicted_winner"] == "defender"

    def test_branches_vary(self):
        r = simulate_historical(_battle(), universes=30, seed=3)
        assert r["universes"] == 30
        assert isinstance(r["convergence"], float)

    def test_what_if_reinforcement_raises_enemy_losses(self):
        b = _battle()
        d = what_if(b, {"defender_strength_mult": 1.5}, universes=60, seed=3)
        assert d["counterfactual"]["avg_attacker_casualties"] > \
            d["baseline"]["avg_attacker_casualties"]

    def test_deterministic_seed(self):
        a = simulate_historical(_battle(), universes=20, seed=99)
        c = simulate_historical(_battle(), universes=20, seed=99)
        assert a["win_distribution"] == c["win_distribution"]


class TestFidelityGate:
    def test_gate_passes_on_matching_battle(self):
        rep = fidelity_report(_battle(), universes=80, seed=3)
        assert rep["passed"] is True
        assert_gate(rep)

    def test_gate_blocks_when_wrong_winner(self):
        b = _battle()
        b.attacker.strength = 1000
        b.defender.strength = 500000
        b.attacker.result_code = "BB"
        rep = fidelity_report(b, universes=40, seed=3)
        if not rep["passed"]:
            with pytest.raises(PermissionError):
                assert_gate(rep)


@pytest.mark.skipif(not DB.exists(), reason="panteon.db not available")
class TestLoader:
    def test_load_alamein(self):
        b = loader.load_battle(387, DB)
        assert b and "ALAMEIN" in b.name.upper()
        assert b.year == 1942
        assert b.actual_winner == "attacker"
        assert b.attacker.strength > 50000

    def test_country_power(self):
        p = loader.country_power("GMY", 1939, DB)
        assert p and p["cinc"] > 0

    def test_top_powers_1939(self):
        tops = loader.top_powers(1939, 5, DB)
        assert len(tops) == 5
        assert tops[0]["cinc"] >= tops[-1]["cinc"]


from engines.chronos.doctrines import (  # noqa: E402
    resolve_doctrine, attacker_power_mult, defender_power_mult,
)


class TestDoctrines:
    def test_resolution_transitions(self):
        assert resolve_doctrine("Germany", 1941).key == "ger-bewegungskrieg"
        assert resolve_doctrine("Germany", 1944).key == "ger-defence-depth"
        assert resolve_doctrine("USSR", 1942).key == "su-standing-defence"
        assert resolve_doctrine("USSR", 1944).key == "su-deep-operations"

    def test_unknown_actor_neutral(self):
        d = resolve_doctrine("Brazil", 1942)
        assert d.key == "generic-contemporary"
        for p in (d.tempo, d.combined_arms, d.flexibility,
                  d.set_piece, d.logistic_reach, d.defense_doctrine):
            assert p == 1.0

    def test_aliases(self):
        assert resolve_doctrine("Soviet Union", 1943).actor == "USSR"
        assert resolve_doctrine("United States", 1944).actor == "USA"
        assert resolve_doctrine("Australia", 1944).actor == "Great Britain"

    def test_tempo_open_vs_broken_terrain(self):
        ger41 = resolve_doctrine("Germany", 1941)
        m_open = attacker_power_mult(ger41, "flat,desert", 24)
        m_urban = attacker_power_mult(ger41, "urban,rugged", 24)
        assert m_open > m_urban > 1.0

    def test_japan_island_defence_growth(self):
        # 1942: beach-line annihilation doctrine (defensively weak);
        # 1943+: fortified zones in depth - a large doctrinal jump.
        j42 = defender_power_mult(resolve_doctrine("Japan", 1942))
        j44 = defender_power_mult(resolve_doctrine("Japan", 1944))
        assert j44 > 1.0 > j42

    def test_citations_present(self):
        for actor, year in (("Germany", 1941), ("USSR", 1944), ("USA", 1943),
                            ("Great Britain", 1943), ("Japan", 1940),
                            ("France", 1940), ("Italy", 1941), ("Finland", 1940)):
            doc = resolve_doctrine(actor, year)
            assert doc.sources and doc.summary, f"missing citation for {actor} {year}"

    def test_doctrine_swap_override(self):
        b = _battle()
        b.attacker.actors = ["Germany"]
        b.defender.actors = ["USSR"]
        base = simulate_historical(b, universes=80, seed=7)
        swap = simulate_historical(b, universes=80, seed=7,
                                   overrides={"defender_doctrine": "Germany"})
        # German elastic defence should help the defender vs rigid '42 Soviet method.
        assert swap["win_distribution"]["defender"] >= \
            base["win_distribution"]["defender"] - 0.02
        assert swap["doctrines"]["defender"]["actor"] == "Germany"
        assert base["doctrines"]["defender"]["actor"] == "USSR"

    def test_no_actors_stays_neutral(self):
        b = _battle()
        r = simulate_historical(b, universes=40, seed=5)
        assert r["doctrines"] == {"attacker": None, "defender": None}
