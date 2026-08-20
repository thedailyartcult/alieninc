"""Kriegspiel geography — terrain analysis and spatial helpers.

Computes distances, line-of-sight, and terrain effects on movement/engagement.
All functions are pure (no external GIS dependencies) so the engine stays
lightweight and can run 10k scenarios in under a minute.
"""

from __future__ import annotations

import math
from typing import Optional

from engines.kriegspiel.models import Battlefield, Force, TerrainType, Unit, UnitType


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km between two lat/lng points."""
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def terrain_speed_modifier(terrain: TerrainType, unit_type: UnitType) -> float:
    """How fast a unit moves through terrain (1.0 = normal speed)."""
    table = {
        TerrainType.URBAN: {UnitType.INFANTRY: 0.5, UnitType.ARMOR: 0.3,
                            UnitType.ARTILLERY: 0.3, UnitType.AIR: 1.0},
        TerrainType.MOUNTAIN: {UnitType.INFANTRY: 0.4, UnitType.ARMOR: 0.15,
                               UnitType.ARTILLERY: 0.2, UnitType.AIR: 0.9},
        TerrainType.FOREST: {UnitType.INFANTRY: 0.6, UnitType.ARMOR: 0.35,
                             UnitType.ARTILLERY: 0.4, UnitType.AIR: 0.8},
        TerrainType.DESERT: {UnitType.INFANTRY: 0.8, UnitType.ARMOR: 0.9,
                             UnitType.ARTILLERY: 0.85, UnitType.AIR: 1.0},
        TerrainType.COASTAL: {UnitType.INFANTRY: 0.7, UnitType.NAVAL: 1.0,
                              UnitType.AIR: 1.0, UnitType.ARMOR: 0.6},
        TerrainType.WETLAND: {UnitType.INFANTRY: 0.3, UnitType.ARMOR: 0.1,
                              UnitType.NAVAL: 0.9, UnitType.ARTILLERY: 0.15},
        TerrainType.OPEN: {UnitType.INFANTRY: 1.0, UnitType.ARMOR: 1.1,
                           UnitType.ARTILLERY: 0.95, UnitType.AIR: 1.0},
    }
    return table.get(terrain, {}).get(unit_type, 0.8)


def has_line_of_sight(
    terrain: TerrainType,
    dist_km: float,
    unit_type: UnitType,
) -> bool:
    """Rough LOS check — terrain blocks beyond a type-dependent range."""
    max_los = {
        UnitType.AIR: 200.0,
        UnitType.ARTILLERY: 30.0,
        UnitType.RECON: 50.0,
        UnitType.ARMOR: 15.0,
        UnitType.INFANTRY: 5.0,
    }
    terrain_reduction = {
        TerrainType.MOUNTAIN: 0.5, TerrainType.URBAN: 0.6,
        TerrainType.FOREST: 0.7,
    }
    effective_range = max_los.get(unit_type, 10.0) * terrain_reduction.get(terrain, 1.0)
    return dist_km <= effective_range


def deploy_force(
    force: Force,
    battlefield: Battlefield,
    side: str = "red",
    seed: Optional[int] = None,
) -> None:
    """Deploy a force's units into a coherent tactical engagement zone.

    Battlefields span real-world theaters (thousands of km), but combat
    engagement ranges are tactical (km). Spreading units across the full
    theater put them thousands of km apart — they never engaged, so per-tick
    supply/morale attrition dominated every outcome (the 'supply_focus meta').

    Fix: deploy each side into a small engagement zone near the battlefield
    center, with a narrow gap between the two forces. Units start within a
    few km of each other so the doctrine's aggression *actually engages*.
    The zone is ~6 km wide, centered on the theater, with red on the west of
    the center line and blue on the east.
    """
    import random
    rng = random.Random(seed)
    w, s, e, n = battlefield.bounds
    center_lat = (s + n) / 2.0
    center_lng = (w + e) / 2.0
    # A small tactical zone (~6 km ≈ 0.05 lng/lat at these latitudes).
    zone = 0.03
    for unit in force.units:
        # Offset west (red) or east (blue) of the center line by ~1-3 km.
        lat_offset = rng.uniform(-zone, zone)
        if side == "red":
            lng = center_lng - rng.uniform(0.01, 0.03)
        else:
            lng = center_lng + rng.uniform(0.01, 0.03)
        unit.position = (
            center_lat + lat_offset,
            lng,
        )


def unit_to_geojson(unit: Unit, side: str) -> dict:
    """Render a unit as a GeoJSON point feature."""
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [unit.position[1], unit.position[0]]},
        "properties": {
            "unit_type": unit.unit_type.value,
            "side": side,
            "strength": round(unit.strength, 1),
            "morale": round(unit.morale, 1),
            "supply": round(unit.supply, 1),
        },
    }


def force_to_geojson(force: Force) -> dict:
    """Render an entire force as a GeoJSON FeatureCollection."""
    return {
        "type": "FeatureCollection",
        "features": [unit_to_geojson(u, force.side) for u in force.units],
    }


def battlefield_to_geojson(battlefield: Battlefield) -> dict:
    """Render the battlefield boundary + center as GeoJSON."""
    w, s, e, n = battlefield.bounds
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": battlefield.to_geojson(),
                "properties": {
                    "name": battlefield.name,
                    "terrain": battlefield.terrain.value,
                    "area_km2": battlefield.area_km2,
                },
            },
            {
                "type": "Feature",
                "geometry": {"type": "Point",
                             "coordinates": [battlefield.center[1], battlefield.center[0]]},
                "properties": {"name": battlefield.name, "center": True},
            },
        ],
    }
