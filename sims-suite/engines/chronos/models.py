"""Chronos data models — historical battles, sides, outcomes, eras."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class EraProfile:
    """Technology context of a given year. Multipliers apply to side combat power.

    ``attacker_casualty_scale`` / ``defender_casualty_scale`` are calibrated
    against CDB90-era ground truth (measured casualty fractions by period):
    modern dispersal and medicine cut attacker losses to roughly a third of
    pre-1900 rates, while defender losses fell less.
    """

    name: str
    year: int
    air_effectiveness: float      # 0 = air power not yet a factor
    armor_effectiveness: float
    artillery_effectiveness: float
    cavalry_effectiveness: float
    defense_bias: float           # how much defending helps (trenches, AT guns)
    attrition_rate: float         # baseline casualties per engagement day
    attacker_casualty_scale: float = 1.0
    defender_casualty_scale: float = 1.0


def era_profile(year: int) -> EraProfile:
    if year < 1850:
        return EraProfile("napoleonic", year, 0.0, 0.0, 0.55, 1.25, 1.15, 0.06, 2.10, 1.45)
    if year < 1905:
        return EraProfile("rifled", year, 0.0, 0.05, 0.95, 0.85, 1.3, 0.07, 1.90, 1.40)
    if year < 1919:
        return EraProfile("great-war", year, 0.12, 0.22, 1.35, 0.35, 1.75, 0.10, 1.25, 1.05)
    if year < 1936:
        return EraProfile("interwar", year, 0.35, 0.5, 1.2, 0.3, 1.45, 0.08, 1.15, 1.00)
    if year < 1946:
        return EraProfile("world-war-ii", year, 1.0, 1.0, 1.15, 0.18, 1.35, 0.09, 0.50, 0.52)
    if year < 1991:
        return EraProfile("cold-war", year, 1.15, 1.25, 1.1, 0.08, 1.4, 0.08, 0.55, 0.68)
    return EraProfile("modern", year, 1.25, 1.35, 1.05, 0.05, 1.3, 0.06, 0.55, 0.65)


def _quality_mult(score: Optional[float], step: float = 0.12,
                  scale: float = 4.0) -> float:
    """Map a CDB90 ordinal rating to a combat-power multiplier.

    These are *advantage* scales: 0 means "no recorded advantage", not a
    broken force — so 0 maps to neutral 1.0 and each positive point adds
    ``step``. Morale uses a larger step (corpus: +1 morale advantage lifts
    attacker-win probability from 70% to 87%).
    """
    if score is None:
        return 1.0
    clamped = max(0.0, min(scale, score))
    return 1.0 + step * clamped


def _morale_mult(score: Optional[float]) -> float:
    return _quality_mult(score, step=0.28)


@dataclass
class HistoricalSide:
    """One belligerent in a historical battle, from verified CDB90 data.

    ``side_id`` follows CDB90's belligerents.attacker column: 1 = the
    attacking force, 0 = the defending force.
    """

    side_id: int                    # 1 = attacker, 0 = defender
    unit_name: str = ""
    commander: str = ""
    actors: list[str] = field(default_factory=list)
    strength: float = 0.0
    casualties: float = 0.0
    tanks: int = 0
    artillery: int = 0
    aircraft: int = 0
    cavalry: int = 0
    leadership: Optional[float] = None
    training: Optional[float] = None
    morale: Optional[float] = None
    logistics: Optional[float] = None
    tech: Optional[float] = None
    surprise: Optional[float] = None
    result_code: Optional[str] = None   # actual historical result (RR/WD/AA/...)

    @property
    def is_attacker(self) -> bool:
        return self.side_id == 1

    def quality_multiplier(self) -> float:
        """Composite CDB90 quality effect.

        Morale is weighted hardest: in the corpus, a recorded morale
        advantage raises attacker-win probability from the 70% base to 87%
        (n=132) — the strongest single predictor available.
        """
        m = 1.0
        for q in (self.leadership, self.training, self.logistics, self.tech):
            if q is not None:
                m *= _quality_mult(q)
        if self.morale is not None:
            m *= _morale_mult(self.morale)
        return m

    def equipment_multiplier(self, era: EraProfile) -> float:
        total = max(self.strength, 1.0)
        armor_ratio = min(self.tanks / total * 100, 8.0)
        arty_ratio = min(self.artillery / total * 100, 8.0)
        air_ratio = min(self.aircraft / total * 100, 8.0)
        cav_ratio = min(self.cavalry / total * 100, 8.0)
        base = 1.0
        base += armor_ratio * 0.02 * era.armor_effectiveness
        base += arty_ratio * 0.015 * era.artillery_effectiveness
        base += air_ratio * 0.03 * era.air_effectiveness
        base += cav_ratio * 0.01 * era.cavalry_effectiveness
        return base

    def to_dict(self) -> dict:
        return {
            "side": "attacker" if self.is_attacker else "defender",
            "actors": self.actors,
            "strength": self.strength,
            "casualties": self.casualties,
            "tanks": self.tanks,
            "artillery": self.artillery,
            "aircraft": self.aircraft,
            "cavalry": self.cavalry,
            "result_code": self.result_code,
            "quality_multiplier": round(self.quality_multiplier(), 4),
        }


@dataclass
class HistoricalBattle:
    battle_key: str
    name: str
    war: str
    year: int
    terrain: str = "open"
    weather: str = ""
    duration_hours: float = 24.0
    attacker: HistoricalSide = field(default_factory=lambda: HistoricalSide(1))
    defender: HistoricalSide = field(default_factory=lambda: HistoricalSide(0))
    source: str = "CDB90"

    @property
    def era(self) -> EraProfile:
        return era_profile(self.year)

    @property
    def actual_winner(self) -> str:
        """Victor per the historical record, from the attacking force's result.

        CDB90 attack-success codes: AA (annihilated), PS (pursued),
        PP (penetration), BB (breakthrough). Anything else for the attacking
        force (RR repulse / WD withdrew / WL heavy losses / SS stalemate)
        means the defense held.
        """
        attacker = self.attacker
        code = (attacker.result_code or "").strip().upper()
        if not code and not self.defender.result_code:
            return "stalemate"
        if any(c in code for c in ("AA", "PS", "PP", "BB")):
            return "attacker"
        return "defender"

    def actual_casualty_ratio(self) -> Optional[float]:
        if self.attacker.strength <= 0 or self.defender.strength <= 0:
            return None
        att_frac = self.attacker.casualties / self.attacker.strength
        dfd_frac = self.defender.casualties / self.defender.strength
        if dfd_frac <= 0:
            return None
        return att_frac / dfd_frac

    def to_dict(self) -> dict:
        return {
            "battle_key": self.battle_key,
            "name": self.name,
            "war": self.war,
            "year": self.year,
            "terrain": self.terrain,
            "weather": self.weather,
            "duration_hours": self.duration_hours,
            "era": self.era.name,
            "actual_winner": self.actual_winner,
            "attacker": self.attacker.to_dict(),
            "defender": self.defender.to_dict(),
            "source": self.source,
        }


@dataclass
class ChronosOutcome:
    winner: str                     # attacker | defender | stalemate
    attacker_casualties: float
    defender_casualties: float
    duration_hours: float
    decisive: bool
    key_event: str = ""

    def to_dict(self) -> dict:
        return {
            "winner": self.winner,
            "attacker_casualties": round(self.attacker_casualties, 1),
            "defender_casualties": round(self.defender_casualties, 1),
            "duration_hours": round(self.duration_hours, 1),
            "decisive": self.decisive,
            "key_event": self.key_event,
        }
