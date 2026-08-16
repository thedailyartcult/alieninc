"""Validator — the verification gate for LLM-synthesized battles.

Every LLM-proposed battle must pass schema + domain-sanity checks before it
can enter the Monte Carlo pool. Rejections are logged with a reason so a
contractor reviewing the audit trail can see exactly what the LLM got wrong.

This is the contractor-learning surface: every rejection is a lesson about
what the LLM does and does not understand about modern combat.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional

from engines.kriegspiel.models import (
    Battle,
    Battlefield,
    Doctrine,
    Force,
    TerrainType,
    Unit,
    UnitType,
)


class ValidationError(Exception):
    """Raised when an LLM-proposed battle fails validation."""


@dataclass
class ValidationResult:
    ok: bool
    reasons: list[str] = field(default_factory=list)
    battle: Optional[Battle] = None


# ---------------------------------------------------------------------------
# JSON schema check
# ---------------------------------------------------------------------------

_VALID_TERRAINS = {t.value for t in TerrainType}
_VALID_DOCTRINES = {d.value for d in Doctrine}
_VALID_UNIT_TYPES = {u.value for u in UnitType}


def _require(d: dict, key: str, expected_type: type, reasons: list[str]):
    if key not in d:
        reasons.append(f"missing field: {key}")
        return None
    val = d[key]
    if not isinstance(val, expected_type):
        reasons.append(f"field {key!r} must be {expected_type.__name__}, got {type(val).__name__}")
        return None
    return val


def _check_range(val, lo: float, hi: float, label: str, reasons: list[str]) -> bool:
    if not isinstance(val, (int, float)):
        reasons.append(f"{label} must be numeric, got {type(val).__name__}")
        return False
    if not (lo <= val <= hi):
        reasons.append(f"{label} out of range [{lo}, {hi}]: {val}")
        return False
    return True


# ---------------------------------------------------------------------------
# Parse + validate one battle dict
# ---------------------------------------------------------------------------

def parse_and_validate_battle(data: dict) -> ValidationResult:
    """Parse an LLM JSON dict into a validated Battle, or return reasons."""
    reasons: list[str] = []

    bf_raw = _require(data, "battlefield", dict, reasons)
    obj = _require(data, "objective", str, reasons)
    dur = _require(data, "duration_hours", int, reasons)
    red_raw = _require(data, "red_force", dict, reasons)
    blue_raw = _require(data, "blue_force", dict, reasons)
    # situational_events is optional; we don't validate it here.

    if reasons:
        return ValidationResult(ok=False, reasons=reasons)

    # --- battlefield ---
    bf_name = _require(bf_raw, "name", str, reasons) or "Unnamed"
    bf_center = _require(bf_raw, "center", list, reasons)
    bf_terrain = _require(bf_raw, "terrain", str, reasons)
    bf_area = _require(bf_raw, "area_km2", (int, float), reasons)
    bf_bounds = _require(bf_raw, "bounds", list, reasons)

    if bf_terrain and bf_terrain not in _VALID_TERRAINS:
        reasons.append(f"invalid terrain: {bf_terrain!r}")
    if bf_center and (len(bf_center) != 2 or
                      not _check_range(bf_center[0], -90, 90, "center.lat", reasons) or
                      not _check_range(bf_center[1], -180, 180, "center.lng", reasons)):
        pass
    if bf_bounds and len(bf_bounds) != 4:
        reasons.append("bounds must be [west, south, east, north]")
    elif bf_bounds and bf_center and len(bf_center) == 2:
        w, s, e, n = bf_bounds
        if not _check_range(w, -180, 180, "bounds.west", reasons): pass
        if not _check_range(s, -90, 90, "bounds.south", reasons): pass
        if not _check_range(e, -180, 180, "bounds.east", reasons): pass
        if not _check_range(n, -90, 90, "bounds.north", reasons): pass
        if w >= e: reasons.append("bounds.west must be < bounds.east")
        if s >= n: reasons.append("bounds.south must be < bounds.north")
        # center must be inside bounds
        if not (s <= bf_center[0] <= n and w <= bf_center[1] <= e):
            reasons.append("center must lie inside bounds box")
    if bf_area and not _check_range(bf_area, 100, 5_000_000, "area_km2", reasons):
        pass

    # --- duration ---
    if dur and not _check_range(dur, 6, 168, "duration_hours", reasons):
        pass

    # --- forces ---
    red = _validate_force(red_raw, "red_force", reasons)
    blue = _validate_force(blue_raw, "blue_force", reasons)

    if reasons:
        return ValidationResult(ok=False, reasons=reasons)

    battlefield = Battlefield(
        name=bf_name,
        center=(float(bf_center[0]), float(bf_center[1])),
        terrain=TerrainType(bf_terrain),
        area_km2=float(bf_area),
        bounds=(float(bf_bounds[0]), float(bf_bounds[1]),
                float(bf_bounds[2]), float(bf_bounds[3])),
    )
    battle = Battle(
        battlefield=battlefield,
        red_force=red,
        blue_force=blue,
        objective=obj or "Secure strategic corridor",
        duration_hours=int(dur),
        seed=None,
    )
    return ValidationResult(ok=True, battle=battle, reasons=[])


def _validate_force(raw: dict, label: str, reasons: list[str]) -> Optional[Force]:
    name = _require(raw, "name", str, reasons) or label
    doctrine = _require(raw, "doctrine", str, reasons)
    units_raw = _require(raw, "units", list, reasons)

    if doctrine and doctrine not in _VALID_DOCTRINES:
        reasons.append(f"{label}.doctrine invalid: {doctrine!r}")
    if units_raw is not None:
        if not (3 <= len(units_raw) <= 15):
            reasons.append(f"{label}.units count must be 3-15, got {len(units_raw)}")

    if reasons:
        return None

    units: list[Unit] = []
    for i, u_raw in enumerate(units_raw):
        if not isinstance(u_raw, dict):
            reasons.append(f"{label}.units[{i}] must be an object")
            continue
        ut = _require(u_raw, "unit_type", str, reasons)
        strength = _require(u_raw, "strength", (int, float), reasons)
        morale = _require(u_raw, "morale", (int, float), reasons)
        supply = _require(u_raw, "supply", (int, float), reasons)
        speed = _require(u_raw, "speed_kmh", (int, float), reasons)
        rng = _require(u_raw, "engagement_range_km", (int, float), reasons)

        if ut and ut not in _VALID_UNIT_TYPES:
            reasons.append(f"{label}.units[{i}].unit_type invalid: {ut!r}")
        if strength is not None: _check_range(strength, 0, 100, f"{label}.units[{i}].strength", reasons)
        if morale is not None:   _check_range(morale, 0, 100, f"{label}.units[{i}].morale", reasons)
        if supply is not None:   _check_range(supply, 0, 100, f"{label}.units[{i}].supply", reasons)
        if speed is not None:    _check_range(speed, 5, 100, f"{label}.units[{i}].speed_kmh", reasons)
        if rng is not None:      _check_range(rng, 1, 50, f"{label}.units[{i}].engagement_range_km", reasons)

        if ut and ut in _VALID_UNIT_TYPES and all(v is not None for v in
                (strength, morale, supply, speed, rng)):
            units.append(Unit(
                unit_type=UnitType(ut),
                strength=float(strength),
                morale=float(morale),
                supply=float(supply),
                speed_kmh=float(speed),
                engagement_range_km=float(rng),
            ))

    if reasons or not units:
        if not units and not reasons:
            reasons.append(f"{label} has no valid units")
        return None

    return Force(
        name=name,
        doctrine=Doctrine(doctrine),
        units=units,
        side="red" if label == "red_force" else "blue",
    )


# ---------------------------------------------------------------------------
# Validate an already-built Battle (defense in depth)
# ---------------------------------------------------------------------------

def validate_battle(battle: Battle) -> tuple[bool, list[str]]:
    """Sanity-check a constructed Battle object. Returns (ok, reasons)."""
    reasons: list[str] = []
    bf = battle.battlefield
    lat, lng = bf.center
    if not (-90 <= lat <= 90): reasons.append(f"battlefield center lat out of range: {lat}")
    if not (-180 <= lng <= 180): reasons.append(f"battlefield center lng out of range: {lng}")
    w, s, e, n = bf.bounds
    if w >= e: reasons.append("bounds west >= east")
    if s >= n: reasons.append("bounds south >= north")
    if not (s <= lat <= n and w <= lng <= e):
        reasons.append("center outside bounds box")
    if not (3 <= len(battle.red_force.units) <= 15):
        reasons.append(f"red_force units count out of range: {len(battle.red_force.units)}")
    if not (3 <= len(battle.blue_force.units) <= 15):
        reasons.append(f"blue_force units count out of range: {len(battle.blue_force.units)}")
    if not (6 <= battle.duration_hours <= 168):
        reasons.append(f"duration_hours out of range: {battle.duration_hours}")
    return (len(reasons) == 0, reasons)


# ---------------------------------------------------------------------------
# Event validation
# ---------------------------------------------------------------------------

def validate_event(event: str) -> tuple[bool, str]:
    """Check one event label. Returns (ok, reason)."""
    if not isinstance(event, str):
        return False, "event must be a string"
    if not (3 <= len(event) <= 120):
        return False, f"event length out of range: {len(event)}"
    return True, ""


def parse_events_response(text: str) -> tuple[list[str], list[str]]:
    """Parse the LLM events JSON. Returns (events, errors)."""
    errors: list[str] = []
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return [], [f"events JSON parse failed: {exc}"]
    if not isinstance(data, dict) or "events" not in data:
        return [], ["events response missing 'events' field"]
    raw_events = data["events"]
    if not isinstance(raw_events, list):
        return [], ["'events' must be a list"]
    events: list[str] = []
    for i, e in enumerate(raw_events):
        ok, reason = validate_event(e if isinstance(e, str) else "")
        if ok:
            events.append(e)
        else:
            errors.append(f"events[{i}]: {reason}")
    return events, errors
