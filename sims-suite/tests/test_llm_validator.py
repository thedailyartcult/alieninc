"""Validator tests — runs without any LLM, exercises accept + reject paths.

These are the contractor-learning surface: every rejection reason is a
lesson about what malformed LLM output looks like.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from engines.kriegspiel.llm.validator import (
    parse_and_validate_battle,
    parse_events_response,
    validate_battle,
    validate_event,
)
from engines.kriegspiel.models import (
    Battle, Battlefield, Doctrine, Force, TerrainType, Unit, UnitType,
)


# ---------------------------------------------------------------------------
# Valid battle
# ---------------------------------------------------------------------------

VALID_BATTLE_DICT = {
    "battlefield": {
        "name": "Test Strait",
        "center": [25.0, 120.0],
        "terrain": "coastal",
        "area_km2": 50000,
        "bounds": [118, 22, 122, 27],
    },
    "objective": "Secure the strait",
    "duration_hours": 48,
    "red_force": {
        "name": "Red Fleet",
        "doctrine": "shock",
        "units": [
            {"unit_type": "infantry", "strength": 90, "morale": 80,
             "supply": 100, "speed_kmh": 25, "engagement_range_km": 5},
            {"unit_type": "armor", "strength": 85, "morale": 75,
             "supply": 90, "speed_kmh": 40, "engagement_range_km": 8},
            {"unit_type": "air", "strength": 95, "morale": 88,
             "supply": 95, "speed_kmh": 80, "engagement_range_km": 30},
        ],
    },
    "blue_force": {
        "name": "Blue Fleet",
        "doctrine": "defensive",
        "units": [
            {"unit_type": "infantry", "strength": 80, "morale": 70,
             "supply": 85, "speed_kmh": 22, "engagement_range_km": 4},
            {"unit_type": "artillery", "strength": 75, "morale": 65,
             "supply": 80, "speed_kmh": 15, "engagement_range_km": 20},
            {"unit_type": "recon", "strength": 70, "morale": 60,
             "supply": 75, "speed_kmh": 50, "engagement_range_km": 12},
        ],
    },
    "situational_events": ["amphibious landing repulsed", "carrier group sortied"],
}


def test_valid_battle_parses():
    res = parse_and_validate_battle(VALID_BATTLE_DICT)
    assert res.ok, f"expected ok, got reasons: {res.reasons}"
    assert res.battle is not None
    assert res.battle.battlefield.name == "Test Strait"
    assert res.battle.red_force.doctrine == Doctrine.SHOCK
    assert res.battle.blue_force.doctrine == Doctrine.DEFENSIVE
    assert len(res.battle.red_force.units) == 3
    assert len(res.battle.blue_force.units) == 3


def test_valid_battle_passes_defense_in_depth():
    res = parse_and_validate_battle(VALID_BATTLE_DICT)
    ok, reasons = validate_battle(res.battle)
    assert ok, f"defense-in-depth failed: {reasons}"


# ---------------------------------------------------------------------------
# Rejection paths
# ---------------------------------------------------------------------------

def test_missing_field_rejected():
    bad = dict(VALID_BATTLE_DICT)
    del bad["objective"]
    res = parse_and_validate_battle(bad)
    assert not res.ok
    assert any("objective" in r for r in res.reasons)


def test_bad_terrain_rejected():
    bad = dict(VALID_BATTLE_DICT)
    bad = {**bad, "battlefield": {**bad["battlefield"], "terrain": "jungle"}}
    res = parse_and_validate_battle(bad)
    assert not res.ok
    assert any("terrain" in r for r in res.reasons)


def test_bad_doctrine_rejected():
    bad = dict(VALID_BATTLE_DICT)
    bad = {**bad, "red_force": {**bad["red_force"], "doctrine": "blitzkrieg"}}
    res = parse_and_validate_battle(bad)
    assert not res.ok
    assert any("doctrine" in r for r in res.reasons)


def test_unit_count_too_small_rejected():
    bad = dict(VALID_BATTLE_DICT)
    bad = {**bad, "red_force": {**bad["red_force"], "units":
        bad["red_force"]["units"][:2]}}  # only 2 units
    res = parse_and_validate_battle(bad)
    assert not res.ok
    assert any("3-15" in r for r in res.reasons)


def test_unit_count_too_large_rejected():
    bad = dict(VALID_BATTLE_DICT)
    units = list(bad["red_force"]["units"])
    while len(units) < 16:
        units.append(dict(units[0]))
    bad = {**bad, "red_force": {**bad["red_force"], "units": units}}
    res = parse_and_validate_battle(bad)
    assert not res.ok
    assert any("3-15" in r for r in res.reasons)


def test_strength_out_of_range_rejected():
    bad = dict(VALID_BATTLE_DICT)
    units = list(bad["red_force"]["units"])
    units[0] = {**units[0], "strength": 150}
    bad = {**bad, "red_force": {**bad["red_force"], "units": units}}
    res = parse_and_validate_battle(bad)
    assert not res.ok
    assert any("strength" in r and "out of range" in r for r in res.reasons)


def test_center_outside_bounds_rejected():
    bad = dict(VALID_BATTLE_DICT)
    bad = {**bad, "battlefield": {**bad["battlefield"],
        "center": [50.0, 200.0]}}  # outside both bounds and lat/lng range
    res = parse_and_validate_battle(bad)
    assert not res.ok
    # Should report either range or bounds issue
    assert res.reasons


def test_bounds_inverted_rejected():
    bad = dict(VALID_BATTLE_DICT)
    bad = {**bad, "battlefield": {**bad["battlefield"],
        "bounds": [122, 27, 118, 22]}}  # west > east, south > north
    res = parse_and_validate_battle(bad)
    assert not res.ok
    assert any("west" in r or "south" in r for r in res.reasons)


def test_duration_out_of_range_rejected():
    bad = dict(VALID_BATTLE_DICT)
    bad = {**bad, "duration_hours": 200}
    res = parse_and_validate_battle(bad)
    assert not res.ok
    assert any("duration_hours" in r for r in res.reasons)


def test_non_json_rejected():
    res = parse_and_validate_battle({"foo": "bar"})
    assert not res.ok
    assert res.reasons  # multiple missing fields


# ---------------------------------------------------------------------------
# Event validation
# ---------------------------------------------------------------------------

def test_valid_event_passes():
    ok, reason = validate_event("flanking maneuver succeeded")
    assert ok, reason


def test_short_event_rejected():
    ok, reason = validate_event("x")
    assert not ok
    assert "length" in reason


def test_long_event_rejected():
    ok, reason = validate_event("x" * 200)
    assert not ok
    assert "length" in reason


def test_events_response_parses():
    events, errors = parse_events_response(
        '{"events": ["flanking maneuver", "supply convoy hit", "air sortie"]}')
    assert events == ["flanking maneuver", "supply convoy hit", "air sortie"]
    assert errors == []


def test_events_response_rejects_non_json():
    events, errors = parse_events_response("not json at all")
    assert events == []
    assert errors


def test_events_response_rejects_missing_field():
    events, errors = parse_events_response('{"foo": 1}')
    assert events == []
    assert errors


def test_events_response_partial_validation():
    # Mix of valid (3-120 chars) and invalid (too short) events.
    events, errors = parse_events_response(
        '{"events": ["ok event here", "x", "also ok here"]}')
    assert events == ["ok event here", "also ok here"]
    assert len(errors) == 1


# ---------------------------------------------------------------------------
# Defense-in-depth on a constructed Battle
# ---------------------------------------------------------------------------

def test_constructed_battle_with_bad_bounds_fails_defense_in_depth():
    bf = Battlefield("Bad", (0.0, 0.0), TerrainType.OPEN, 1000, (10, 10, 5, 5))
    red = Force("Red", Doctrine.ATTRITION, [Unit(UnitType.INFANTRY)] * 5, "red")
    blue = Force("Blue", Doctrine.DEFENSIVE, [Unit(UnitType.INFANTRY)] * 5, "blue")
    battle = Battle(bf, red, blue, "test", 48)
    ok, reasons = validate_battle(battle)
    assert not ok
    assert any("west" in r or "south" in r for r in reasons)
