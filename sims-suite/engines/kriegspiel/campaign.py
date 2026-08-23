"""Kriegspiel campaign layer — multi-engagement operations.

A battle answers "who won the fight." A campaign answers "what did the
fighting achieve": ground taken or held, force preserved or spent. Real
operations are sequences — attack, consolidate, reinforce, advance again —
and several warfare lessons only exist at that level:

  - *Pyrrhic trap*: a doctrine that wins battles expensively can lose the
    campaign once attrition carries over (tactical victory != operational
    success).
  - *Tempo vs sustainability*: reinforcement rate bounds how long any
    offensive can keep advancing.
  - *Trading space for time*: a defender that keeps losing engagements may
    still preserve the force that wins the campaign.

Model
-----
A campaign is N engagements between two persistent forces on one battlefield.
Between engagements an interlude applies:

  - recovery: both sides regain morale (rest/rally) and restore supply toward
    full (strategic rear logistics are assumed to work between engagements);
  - reinforcement: each side regains ``reinforcement_rate`` of its *missing*
    per-unit strength (drafts/replacements), capped at each unit's starting
    strength;
  - front movement: the engagement winner pushes the front toward the loser's
    homeland by a step scaled by how the engagement was won (breakthrough >
    ordinary win; repulse = no movement).

The campaign ends early if a side's total effective strength falls below
``_COLLAPSE_PCT`` of its initial strength — it has ceased to exist as an
operational formation.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional

from engines.kriegspiel.models import (
    Battlefield,
    Doctrine,
    Force,
    UnitType,
)
from engines.kriegspiel.combat import _simulate_forces
from engines.kriegspiel.geography import deploy_force

# --- tuning constants -------------------------------------------------------
_INTERLUDE_MORALE_RECOVERY = 12.0   # rest/rally between engagements
_INTERLUDE_SUPPLY_RESET = 90.0      # rear logistics refill floor
_COLLAPSE_PCT = 20.0                # force below this share -> operational collapse
_FRONT_STEP_BREAKTHROUGH = 14.0     # % of theater depth per decisive penetration
_FRONT_STEP_ORDINARY = 7.0          # % per ordinary engagement win

# Doctrine composition templates reused from scenarios.py so campaign forces
# look like the forces scenario branching produces.
from engines.kriegspiel.scenarios import _COMPOSITION_TEMPLATES


@dataclass
class EngagementRecord:
    """One engagement inside a campaign."""

    index: int
    winner: str                       # "red" | "blue" | "stalemate"
    decisive: bool
    withdrawn_by: str
    breakthrough_by: str
    red_casualties_pct: float
    blue_casualties_pct: float
    duration_hours: float
    key_event: str


@dataclass
class CampaignReport:
    """Aggregate result of one campaign."""

    battlefield_name: str
    n_engagements_planned: int
    engagements_fought: int
    red_doctrine: str = ""            # for the campaign learning tracker
    blue_doctrine: str = ""
    engagement_winners: list[str] = field(default_factory=list)
    red_wins: int = 0
    blue_wins: int = 0
    stalemates: int = 0
    # Front position as % of theater depth from RED's homeland edge.
    # 50 = start line; >50 means red advanced into blue territory.
    front_final_pct: float = 50.0
    front_moved_toward: str = ""      # "red" | "blue" | ""
    red_remaining_pct: float = 100.0  # final effective strength / initial
    blue_remaining_pct: float = 100.0
    collapsed: str = ""               # side that operationally collapsed, if any
    campaign_winner: str = ""         # "red" | "blue" | "stalemate"
    seed: Optional[int] = None
    records: list[EngagementRecord] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "battlefield": self.battlefield_name,
            "engagements_fought": self.engagements_fought,
            "red_wins": self.red_wins,
            "blue_wins": self.blue_wins,
            "stalemates": self.stalemates,
            "front_final_pct": round(self.front_final_pct, 1),
            "front_moved_toward": self.front_moved_toward,
            "red_remaining_pct": round(self.red_remaining_pct, 1),
            "blue_remaining_pct": round(self.blue_remaining_pct, 1),
            "collapsed": self.collapsed,
            "campaign_winner": self.campaign_winner,
            "seed": self.seed,
            "engagements": [
                {
                    "index": r.index, "winner": r.winner,
                    "decisive": r.decisive, "withdrawn_by": r.withdrawn_by,
                    "breakthrough_by": r.breakthrough_by,
                    "red_casualties_pct": r.red_casualties_pct,
                    "blue_casualties_pct": r.blue_casualties_pct,
                    "duration_hours": r.duration_hours,
                    "key_event": r.key_event,
                } for r in self.records
            ],
        }


def _build_force(name: str, side: str, doctrine: Doctrine,
                 battlefield: Battlefield, seed: int) -> Force:
    """Materialize a doctrine-appropriate force on the battlefield."""
    from engines.kriegspiel.models import Unit
    rng = random.Random(seed)
    built = []
    for unit_type, lo, hi in _COMPOSITION_TEMPLATES[doctrine]:
        for _ in range(rng.randint(lo, hi)):
            built.append(Unit(
                unit_type=unit_type,
                strength=rng.uniform(80, 100),
                morale=rng.uniform(75, 95),
                supply=rng.uniform(85, 100),
                speed_kmh=rng.uniform(25, 45),
                engagement_range_km=rng.uniform(6, 15),
            ))
    force = Force(name=name, doctrine=doctrine, units=built[:15], side=side)
    deploy_force(force, battlefield, side, seed)
    return force


def run_campaign(
    red_doctrine: Doctrine = Doctrine.MANEUVER,
    blue_doctrine: Doctrine = Doctrine.DEFENSIVE,
    battlefield: Optional[Battlefield] = None,
    n_engagements: int = 8,
    engagement_duration_hours: int = 24,
    red_reinforcement: float = 0.30,
    blue_reinforcement: float = 0.30,
    seed: Optional[int] = None,
) -> CampaignReport:
    """Run one multi-engagement campaign and return its operational report.

    ``*_reinforcement`` is the fraction of *missing* unit strength restored
    during each interlude (0.0 = no replacements ever; 1.0 = fully rebuilt
    before every engagement). Asymmetric rates model strategic mobilization
    differences and are the campaign-level tempo lever.
    """
    from engines.kriegspiel.models import BATTLEFIELDS

    if battlefield is None:
        rng0 = random.Random(seed)
        battlefield = rng0.choice(BATTLEFIELDS)

    master = random.Random(seed)
    red = _build_force("Red Operational Group", "red", red_doctrine, battlefield,
                       master.randrange(2 ** 31))
    blue = _build_force("Blue Operational Group", "blue", blue_doctrine, battlefield,
                        master.randrange(2 ** 31))

    terrain = battlefield.terrain
    red_start_eff = red.effective_strength(terrain)
    blue_start_eff = blue.effective_strength(terrain)
    # Per-unit starting strengths cap reinforcement (replacements fill existing
    # formations up to establishment; they do not conjure super-units).
    red_establishment = [u.strength for u in red.units]
    blue_establishment = [u.strength for u in blue.units]

    report = CampaignReport(
        battlefield_name=battlefield.name,
        n_engagements_planned=n_engagements,
        engagements_fought=0,
        red_doctrine=red_doctrine.value,
        blue_doctrine=blue_doctrine.value,
        seed=seed,
    )
    front = 50.0   # % of theater depth from red's edge; red advances ->
    collapsed = ""

    for idx in range(n_engagements):
        outcome, red, blue = _simulate_forces(
            red, blue, battlefield,
            duration_hours=engagement_duration_hours,
            seed=master.randrange(2 ** 31),
        )
        report.records.append(EngagementRecord(
            index=idx,
            winner=outcome.winner,
            decisive=outcome.decisive,
            withdrawn_by=outcome.withdrawn_by,
            breakthrough_by=outcome.breakthrough_by,
            red_casualties_pct=outcome.red_casualties_pct,
            blue_casualties_pct=outcome.blue_casualties_pct,
            duration_hours=outcome.duration_hours,
            key_event=outcome.key_event,
        ))
        report.engagements_fought += 1
        report.engagement_winners.append(outcome.winner)
        if outcome.winner == "red":
            report.red_wins += 1
        elif outcome.winner == "blue":
            report.blue_wins += 1
        else:
            report.stalemates += 1

        # --- front movement: the winner pushes toward the loser's homeland ---
        if outcome.winner == "red":
            step = (_FRONT_STEP_BREAKTHROUGH if outcome.breakthrough_by == "red"
                    else _FRONT_STEP_ORDINARY)
            front = min(100.0, front + step)
        elif outcome.winner == "blue":
            step = (_FRONT_STEP_BREAKTHROUGH if outcome.breakthrough_by == "blue"
                    else _FRONT_STEP_ORDINARY)
            front = max(0.0, front - step)
        # stalemate / mutual withdrawal: line holds
        report.front_final_pct = front

        # --- operational collapse check ---
        red_now = red.effective_strength(terrain)
        blue_now = blue.effective_strength(terrain)
        if red_now < red_start_eff * (_COLLAPSE_PCT / 100.0):
            collapsed = "red"
            break
        if blue_now < blue_start_eff * (_COLLAPSE_PCT / 100.0):
            collapsed = "blue"
            break

        # --- interlude: recovery + reinforcement (skip after last fight) ---
        if idx == n_engagements - 1:
            break
        for force in (red, blue):
            for unit in force.units:
                if unit.strength > 0:
                    unit.morale = min(100.0, unit.morale + _INTERLUDE_MORALE_RECOVERY)
                    unit.supply = max(unit.supply, _INTERLUDE_SUPPLY_RESET)
        rate_r, est_r = red_reinforcement, red_establishment
        rate_b, est_b = blue_reinforcement, blue_establishment
        for unit, start_strength in zip(red.units, est_r):
            missing = max(0.0, start_strength - unit.strength)
            unit.strength = min(start_strength, unit.strength + missing * rate_r)
        for unit, start_strength in zip(blue.units, est_b):
            missing = max(0.0, start_strength - unit.strength)
            unit.strength = min(start_strength, unit.strength + missing * rate_b)

    # --- aggregate -----------------------------------------------------------
    report.front_moved_toward = (
        "red" if report.front_final_pct > 52.5
        else ("blue" if report.front_final_pct < 47.5 else "")
    )
    red_remaining = red.effective_strength(terrain) / max(red_start_eff, 1) * 100.0
    blue_remaining = blue.effective_strength(terrain) / max(blue_start_eff, 1) * 100.0
    report.red_remaining_pct = red_remaining
    report.blue_remaining_pct = blue_remaining
    report.collapsed = collapsed

    if collapsed == "red":
        report.campaign_winner = "blue"
    elif collapsed == "blue":
        report.campaign_winner = "red"
    elif report.front_final_pct >= 65.0:
        report.campaign_winner = "red"      # red seized operational depth
    elif report.front_final_pct <= 35.0:
        report.campaign_winner = "blue"
    else:
        report.campaign_winner = "stalemate"

    return report
