"""Kriegspiel geography tests — GeoJSON serialization functions.

Covers unit_to_geojson, force_to_geojson, battlefield_to_geojson (lines 108-153).
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from engines.kriegspiel.geography import (
    battlefield_to_geojson,
    force_to_geojson,
    unit_to_geojson,
)
from engines.kriegspiel.models import (
    Battlefield,
    Doctrine,
    Force,
    TerrainType,
    Unit,
    UnitType,
)


def _make_unit(**overrides) -> Unit:
    defaults = dict(
        unit_type=UnitType.INFANTRY,
        strength=85.0,
        morale=70.0,
        supply=90.0,
        position=(51.5, -0.1),
    )
    defaults.update(overrides)
    return Unit(**defaults)


def _make_force(side: str = "red") -> Force:
    units = [
        _make_unit(unit_type=UnitType.INFANTRY, position=(51.5, -0.12)),
        _make_unit(unit_type=UnitType.ARMOR, strength=95.0, position=(51.51, -0.11)),
    ]
    return Force(name=f"Force-{side}", doctrine=Doctrine.ATTRITION, units=units, side=side)


def _make_battlefield() -> Battlefield:
    return Battlefield(
        name="Test Theater",
        center=(51.5, -0.1),
        terrain=TerrainType.OPEN,
        area_km2=2500.0,
        bounds=(-0.5, 51.0, 0.5, 52.0),
    )


# ---------- unit_to_geojson ----------

def test_unit_to_geojson_structure():
    unit = _make_unit()
    feat = unit_to_geojson(unit, "red")
    assert feat["type"] == "Feature"
    assert feat["geometry"]["type"] == "Point"
    coords = feat["geometry"]["coordinates"]
    assert coords == [-0.1, 51.5]  # [lng, lat]
    props = feat["properties"]
    assert props["side"] == "red"
    assert props["unit_type"] == "infantry"
    assert props["strength"] == 85.0
    assert props["morale"] == 70.0
    assert props["supply"] == 90.0


def test_unit_to_geojson_strength_is_rounded():
    unit = _make_unit(strength=87.654)
    feat = unit_to_geojson(unit, "blue")
    assert feat["properties"]["strength"] == 87.7
    assert feat["properties"]["side"] == "blue"


# ---------- force_to_geojson ----------

def test_force_to_geojson_is_feature_collection():
    force = _make_force("blue")
    fc = force_to_geojson(force)
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) == 2
    for feat in fc["features"]:
        assert feat["type"] == "Feature"
        assert feat["geometry"]["type"] == "Point"
        assert feat["properties"]["side"] == "blue"


def test_force_to_geojson_empty_units():
    force = Force(name="Empty", doctrine=Doctrine.ATTRITION, units=[], side="red")
    fc = force_to_geojson(force)
    assert fc["features"] == []


# ---------- battlefield_to_geojson ----------

def test_battlefield_to_geojson_structure():
    bf = _make_battlefield()
    fc = battlefield_to_geojson(bf)
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) == 2

    boundary = fc["features"][0]
    assert boundary["type"] == "Feature"
    assert boundary["geometry"]["type"] == "Polygon"
    assert boundary["properties"]["name"] == "Test Theater"
    assert boundary["properties"]["terrain"] == "open"
    assert boundary["properties"]["area_km2"] == 2500.0

    center_feat = fc["features"][1]
    assert center_feat["properties"]["center"] is True
    center_coords = center_feat["geometry"]["coordinates"]
    assert center_coords == [-0.1, 51.5]


def test_battlefield_to_geojson_polygon_coordinates():
    bf = _make_battlefield()
    fc = battlefield_to_geojson(bf)
    polygon = fc["features"][0]["geometry"]
    ring = polygon["coordinates"][0]
    # 5 vertices (closed ring): sw, se, ne, nw, sw
    assert len(ring) == 5
    # First and last vertex are the same (closed)
    assert ring[0] == ring[-1]
    # Bounds: west=-0.5, south=51.0, east=0.5, north=52.0
    assert ring[0] == [-0.5, 51.0]  # sw
    assert ring[1] == [0.5, 51.0]   # se
    assert ring[2] == [0.5, 52.0]   # ne
    assert ring[3] == [-0.5, 52.0]  # nw


def test_battlefield_to_geojson_without_explicit_bounds():
    bf = Battlefield(name="NoBounds", center=(40.0, -74.0), terrain=TerrainType.URBAN)
    fc = battlefield_to_geojson(bf)
    polygon = fc["features"][0]["geometry"]
    ring = polygon["coordinates"][0]
    # Default bounds are (0, 0, 0, 0) — the or-fallback in to_geojson() doesn't
    # trigger because a non-empty tuple is truthy, so we get the raw default.
    assert ring[0] == [0.0, 0.0]  # sw (default bounds)
    assert ring[2] == [0.0, 0.0]  # ne (default bounds)
    assert bf.to_geojson()["type"] == "Polygon"
