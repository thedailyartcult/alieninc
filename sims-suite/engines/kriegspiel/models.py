"""Kriegspiel data models — forces, units, terrain, doctrines.

These are the atomic building blocks of a battlefield scenario. A ``Battle``
is seeded with two ``Force`` objects deployed on a ``Battlefield`` (a geographic
region), each following a ``Doctrine``. The Monte Carlo engine branches by
varying doctrine choices, terrain effects, and stochastic engagement outcomes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class UnitType(str, Enum):
    INFANTRY = "infantry"
    ARMOR = "armor"
    ARTILLERY = "artillery"
    AIR = "air"
    NAVAL = "naval"
    LOGISTICS = "logistics"
    RECON = "recon"
    CYBER = "cyber"


class TerrainType(str, Enum):
    OPEN = "open"
    URBAN = "urban"
    MOUNTAIN = "mountain"
    FOREST = "forest"
    DESERT = "desert"
    COASTAL = "coastal"
    WETLAND = "wetland"


class Doctrine(str, Enum):
    """Strategic doctrines — each biases the scenario toward different outcomes."""

    ATTRITION = "attrition"        # grind down enemy forces
    MANEUVER = "maneuver"          # outflank and encircle
    SHOCK = "shock"                # rapid concentrated breakthrough
    DEFENSIVE = "defensive"        # hold ground, force enemy to attack
    GUERRILLA = "guerrilla"        # harassment, disruption, retreat
    LOGISTICAL = "logistical"      # target enemy supply lines
    INFORMATION = "information"    # cyber/ISR dominance


@dataclass
class Unit:
    """A combat unit within a force."""

    unit_type: UnitType
    strength: float = 100.0         # 0-100 combat effectiveness
    morale: float = 80.0            # 0-100
    supply: float = 100.0           # 0-100 supply level
    position: tuple[float, float] = (0.0, 0.0)   # lat, lng
    speed_kmh: float = 30.0         # movement speed in km/h
    engagement_range_km: float = 5.0

    def effective_strength(self, terrain: TerrainType) -> float:
        """Combat strength adjusted for terrain."""
        modifiers = {
            TerrainType.URBAN: {UnitType.INFANTRY: 1.3, UnitType.ARMOR: 0.6,
                                 UnitType.ARTILLERY: 0.7, UnitType.AIR: 0.5},
            TerrainType.MOUNTAIN: {UnitType.INFANTRY: 1.2, UnitType.ARMOR: 0.3,
                                   UnitType.ARTILLERY: 0.5, UnitType.AIR: 0.6},
            TerrainType.FOREST: {UnitType.INFANTRY: 1.15, UnitType.ARMOR: 0.5,
                                 UnitType.ARTILLERY: 0.6, UnitType.AIR: 0.4},
            TerrainType.DESERT: {UnitType.ARMOR: 1.2, UnitType.INFANTRY: 0.9,
                                 UnitType.AIR: 1.1, UnitType.ARTILLERY: 1.1},
            TerrainType.COASTAL: {UnitType.NAVAL: 1.3, UnitType.AIR: 1.1,
                                  UnitType.INFANTRY: 1.0},
            TerrainType.WETLAND: {UnitType.INFANTRY: 0.7, UnitType.ARMOR: 0.2,
                                  UnitType.NAVAL: 1.1},
            TerrainType.OPEN: {UnitType.ARMOR: 1.3, UnitType.AIR: 1.2,
                               UnitType.ARTILLERY: 1.2, UnitType.INFANTRY: 0.9},
        }
        mod = modifiers.get(terrain, {}).get(self.unit_type, 1.0)
        return self.strength * mod * (self.morale / 100) * (self.supply / 100)


@dataclass
class Force:
    """A military force — a collection of units with a doctrine."""

    name: str
    doctrine: Doctrine
    units: list[Unit] = field(default_factory=list)
    side: str = "red"               # "red" or "blue"

    @property
    def total_strength(self) -> float:
        return sum(u.strength for u in self.units)

    @property
    def avg_morale(self) -> float:
        return sum(u.morale for u in self.units) / len(self.units) if self.units else 0

    @property
    def avg_supply(self) -> float:
        return sum(u.supply for u in self.units) / len(self.units) if self.units else 0

    def effective_strength(self, terrain: TerrainType) -> float:
        return sum(u.effective_strength(terrain) for u in self.units)


@dataclass
class Battlefield:
    """The geographic context of a battle."""

    name: str
    center: tuple[float, float]          # lat, lng
    terrain: TerrainType
    area_km2: float = 1000.0
    bounds: tuple[float, float, float, float] = (0, 0, 0, 0)  # west, south, east, north

    def to_geojson(self) -> dict:
        """Render battlefield bounds as a GeoJSON polygon."""
        w, s, e, n = self.bounds or (
            self.center[1] - 0.5, self.center[0] - 0.5,
            self.center[1] + 0.5, self.center[0] + 0.5,
        )
        return {
            "type": "Polygon",
            "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]],
        }


@dataclass
class Battle:
    """A complete battle setup — the seed for scenario branching.

    ``provenance`` is set by the LLM synthesis layer to record where this
    battle came from (procedural fallback vs LLM provider/model/hashes).
    It is None for battles created before the LLM layer existed, so existing
    callers never see a change.
    """

    battlefield: Battlefield
    red_force: Force
    blue_force: Force
    objective: str = ""
    duration_hours: int = 48
    seed: Optional[int] = None
    provenance: Optional[dict] = None


@dataclass
class BattleOutcome:
    """The result of one branched scenario."""

    winner: str                        # "red", "blue", or "stalemate"
    red_casualties_pct: float          # 0-100
    blue_casualties_pct: float
    duration_hours: float
    decisive: bool = False             # was there a clear winner?
    key_event: str = ""                # the turning point
    terrain_advantage: str = ""        # who benefited from terrain
    score: float = 0.0                 # for best_branch() aggregation
    outcome: str = ""                  # label for convergence_rate()
    # Final force state (populated by combat.simulate_battle; 0.0 for outcomes
    # produced before the adherence layer existed). Used by the doctrine
    # adherence probes to measure supply_focus / morale_drain behavior.
    red_final_supply_pct: float = 0.0
    red_final_morale_pct: float = 0.0
    blue_final_supply_pct: float = 0.0
    blue_final_morale_pct: float = 0.0
    # True when a high-breakthrough doctrine converted a local advantage into
    # a decisive penetration that ended the battle early (not an attrition
    # grind). Populated by combat.simulate_battle. Used by the adherence probes
    # to verify breakthrough really changes behavior.
    breakthrough_by: str = ""        # "red", "blue", or ""
    # Doctrine tags populated by scenarios.generate_scenarios so the
    # self-learning layer (engines.kriegspiel.learning) can attribute
    # outcomes to (doctrine, terrain) pairs. Empty for outcomes created
    # before the learning layer existed — the tracker skips those branches.
    red_doctrine: str = ""
    blue_doctrine: str = ""


# Predefined battlefields (real-world regions for the dashboard)
BATTLEFIELDS: list[Battlefield] = [
    Battlefield("South China Sea", (15.0, 115.0), TerrainType.COASTAL, 1500000,
                (108, 0, 122, 25)),
    Battlefield("Taiwan Strait", (24.5, 120.0), TerrainType.COASTAL, 80000,
                (118, 22, 124, 27)),
    Battlefield("Eastern Europe", (50.0, 30.0), TerrainType.OPEN, 500000,
                (22, 44, 40, 55)),
    Battlefield("Levant", (33.0, 38.0), TerrainType.DESERT, 200000,
                (34, 29, 42, 37)),
    Battlefield("Korean Peninsula", (38.0, 127.5), TerrainType.MOUNTAIN, 220000,
                (124, 33, 131, 43)),
    Battlefield("Persian Gulf", (26.5, 51.5), TerrainType.COASTAL, 250000,
                (47, 23, 57, 30)),
    Battlefield("Sahel", (15.0, 5.0), TerrainType.DESERT, 3000000,
                (-18, 5, 25, 25)),
    Battlefield("Andes", (-15.0, -70.0), TerrainType.MOUNTAIN, 800000,
                (-78, -25, -62, -5)),
]


# Mutable pool of LLM-synthesized battlefields. Kept separate from the
# canonical ``BATTLEFIELDS`` list so the procedural set is never mutated.
# The gateway exposes both via the ``/api/kriegspiel/battlefields`` endpoint
# (canonical first, LLM-synthesized appended with a ``source`` tag).
BATTLEFIELDS_LLM: list[Battlefield] = []


def register_llm_battlefield(bf: Battlefield) -> None:
    """Add an LLM-synthesized battlefield to the runtime pool.

    De-duplicates by name. The pool is process-local and not persisted; a
    contractor who wants durable LLM battlefields should store them via CMB.
    """
    if not any(existing.name == bf.name for existing in BATTLEFIELDS_LLM):
        BATTLEFIELDS_LLM.append(bf)
