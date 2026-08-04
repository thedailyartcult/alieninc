"""Event table — predefined scenario events with weighted triggers and attribute impacts."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable, Optional

from engine.character import Character
from engine.relations import RelationGraph, RelationStatus, RelationType


@dataclass
class EventTemplate:
    """A single event that can trigger during simulation."""

    event_id: str
    name: str
    description: str
    min_age: int = 0
    max_age: int = 100
    weight: float = 1.0  # Base probability weight
    required_conditions: dict = field(default_factory=dict)  # e.g. {"is_employed": True, "smarts": (60, 100)}
    impacts: dict = field(default_factory=dict)  # e.g. {"happiness": 10, "money": 5000}
    relation_impacts: dict = field(default_factory=dict)  # e.g. {"partner": {"closeness": -20}}
    tags: list = field(default_factory=list)  # e.g. ["career", "education", "health"]

    def check_conditions(self, character: Character) -> bool:
        """Check if this event can trigger for the given character state."""
        if character.age < self.min_age or character.age > self.max_age:
            return False

        for attr, condition in self.required_conditions.items():
            if hasattr(character, attr):
                value = getattr(character, attr)
                if isinstance(condition, tuple):
                    if not (condition[0] <= value <= condition[1]):
                        return False
                elif isinstance(condition, bool):
                    if value != condition:
                        return False
                elif isinstance(condition, (int, float)):
                    if value != condition:
                        return False
            else:
                return False
        return True

    def apply(self, character: Character, relations: RelationGraph = None) -> dict:
        """Apply this event's impacts to the character and return the actual changes."""
        changes = {}

        for attr, delta in self.impacts.items():
            if attr == "money":
                character.money += delta
                changes["money"] = delta
            elif attr == "debt":
                character.debt += delta
                changes["debt"] = delta
            elif attr == "portfolio_value":
                character.portfolio_value += delta
                changes["portfolio_value"] = delta
            elif hasattr(character, attr):
                old_val = getattr(character, attr)
                if isinstance(delta, int) and attr in ("happiness", "health", "smarts", "looks", "karma"):
                    character.clamp_attr(attr, old_val + delta)
                else:
                    setattr(character, attr, delta)
                changes[attr] = getattr(character, attr) - old_val

        character._recalc_net_worth()

        if relations and self.relation_impacts:
            for rel_type_str, impacts in self.relation_impacts.items():
                try:
                    rel_type = RelationType(rel_type_str)
                    for rel in relations.get_by_type(rel_type):
                        for attr, delta in impacts.items():
                            if attr == "closeness":
                                rel.modify_closeness(delta)
                            elif attr == "status":
                                rel.status = RelationStatus(delta)
                except ValueError:
                    pass

        return changes


# ─── Event Tables ────────────────────────────────────────────────────────────

def build_life_events() -> list[EventTemplate]:
    """Build the complete event table for life simulation."""

    events = [
        # ── Childhood (0-12) ──
        EventTemplate(
            event_id="child_illness",
            name="Childhood Illness",
            description="You caught a bad flu. Doctor says rest is the best medicine.",
            min_age=2, max_age=12, weight=8.0,
            impacts={"health": -10, "happiness": -5},
            tags=["health"],
        ),
        EventTemplate(
            event_id="school_award",
            name="School Award",
            description="You won an award for outstanding performance at school.",
            min_age=6, max_age=12, weight=5.0,
            required_conditions={"smarts": (60, 100)},
            impacts={"happiness": 15, "smarts": 5},
            tags=["education"],
        ),
        EventTemplate(
            event_id="first_friend",
            name="New Friend",
            description="You made your first real friend at school.",
            min_age=4, max_age=10, weight=10.0,
            impacts={"happiness": 10},
            tags=["social"],
        ),

        # ── Teenage (13-19) ──
        EventTemplate(
            event_id="teen_rebellion",
            name="Rebellious Phase",
            description="You got into trouble at school for breaking the rules.",
            min_age=13, max_age=17, weight=6.0,
            impacts={"happiness": 5, "karma": -10},
            tags=["social"],
        ),
        EventTemplate(
            event_id="first_crush",
            name="First Crush",
            description="You developed feelings for someone in your class.",
            min_age=12, max_age=18, weight=12.0,
            impacts={"happiness": 10},
            tags=["romance"],
        ),
        EventTemplate(
            event_id="exam_failure",
            name="Failed Exam",
            description="You failed an important exam. Time to study harder.",
            min_age=14, max_age=19, weight=7.0,
            impacts={"happiness": -15, "smarts": 3},
            tags=["education"],
        ),
        EventTemplate(
            event_id="sports_victory",
            name="Sports Victory",
            description="Your team won the championship!",
            min_age=13, max_age=19, weight=4.0,
            impacts={"happiness": 20, "health": 5, "looks": 3},
            tags=["health", "social"],
        ),

        # ── Young Adult (20-30) ──
        EventTemplate(
            event_id="college_acceptance",
            name="College Acceptance",
            description="You got accepted into your dream university!",
            min_age=18, max_age=22, weight=8.0,
            required_conditions={"smarts": (50, 100)},
            impacts={"happiness": 25, "smarts": 10, "debt": 20000},
            tags=["education"],
        ),
        EventTemplate(
            event_id="first_job",
            name="First Job Offer",
            description="You landed your first real job!",
            min_age=20, max_age=28, weight=10.0,
            required_conditions={"is_employed": False},
            impacts={"happiness": 20, "money": 3000},
            tags=["career"],
        ),
        EventTemplate(
            event_id="heartbreak",
            name="Heartbreak",
            description="Your relationship ended. It hurts, but you'll grow from it.",
            min_age=18, max_age=35, weight=8.0,
            impacts={"happiness": -25},
            relation_impacts={"partner": {"closeness": -50, "status": 7}},
            tags=["romance"],
        ),
        EventTemplate(
            event_id="investment_opportunity",
            name="Investment Opportunity",
            description="A friend told you about a promising investment.",
            min_age=22, max_age=40, weight=5.0,
            required_conditions={"money": (5000, 999999)},
            impacts={"money": -2000},
            tags=["finance"],
        ),

        # ── Adult (30-50) ──
        EventTemplate(
            event_id="career_promotion",
            name="Career Promotion",
            description="You got promoted! More responsibility, more pay.",
            min_age=28, max_age=50, weight=6.0,
            required_conditions={"is_employed": True, "smarts": (55, 100)},
            impacts={"happiness": 15, "money": 8000},
            tags=["career"],
        ),
        EventTemplate(
            event_id="health_scare",
            name="Health Scare",
            description="A routine checkup revealed something concerning.",
            min_age=35, max_age=60, weight=5.0,
            required_conditions={"health": (31, 100)},
            impacts={"health": -15, "happiness": -10},
            tags=["health"],
        ),
        EventTemplate(
            event_id="market_crash",
            name="Market Crash",
            description="The stock market took a massive hit.",
            min_age=25, max_age=65, weight=3.0,
            impacts={"portfolio_value": -0.30, "happiness": -15},
            tags=["finance"],
        ),
        EventTemplate(
            event_id="bull_market",
            name="Bull Market",
            description="The market is booming. Your investments are soaring.",
            min_age=25, max_age=65, weight=4.0,
            impacts={"portfolio_value": 0.25, "happiness": 10},
            tags=["finance"],
        ),

        # ── Midlife (50-65) ──
        EventTemplate(
            event_id="midlife_crisis",
            name="Midlife Reflection",
            description="You're questioning your life choices and considering big changes.",
            min_age=45, max_age=60, weight=7.0,
            impacts={"happiness": -10},
            tags=["social"],
        ),
        EventTemplate(
            event_id="inheritance",
            name="Inheritance",
            description="A relative left you a substantial inheritance.",
            min_age=40, max_age=65, weight=3.0,
            impacts={"money": 50000, "happiness": 10},
            tags=["finance"],
        ),

        # ── Senior (65+) ──
        EventTemplate(
            event_id="retirement",
            name="Retirement",
            description="You retired from your career. Time to enjoy life.",
            min_age=60, max_age=70, weight=10.0,
            required_conditions={"is_employed": True},
            impacts={"happiness": 20, "health": 5},
            tags=["career"],
        ),
        EventTemplate(
            event_id="grandchild",
            name="New Grandchild",
            description="Your child had a baby. You're a grandparent now!",
            min_age=50, max_age=75, weight=6.0,
            impacts={"happiness": 25},
            tags=["social"],
        ),
        EventTemplate(
            event_id="chronic_illness",
            name="Chronic Condition",
            description="You were diagnosed with a chronic health condition.",
            min_age=55, max_age=85, weight=8.0,
            required_conditions={"health": (31, 100)},
            impacts={"health": -20, "happiness": -10},
            tags=["health"],
        ),
        # ── Additional Childhood Events ──
        EventTemplate(
            event_id="family_move",
            name="Family Moves",
            description="Your family relocated to a new city. You had to start over.",
            min_age=3, max_age=12, weight=6.0,
            impacts={"happiness": -10, "smarts": 3},
            tags=["social"],
        ),
        EventTemplate(
            event_id="bullying",
            name="Bullying",
            description="You were bullied at school. It left a mark.",
            min_age=6, max_age=14, weight=7.0,
            impacts={"happiness": -15, "karma": -5},
            tags=["social"],
        ),
        EventTemplate(
            event_id="mentor_childhood",
            name="Childhood Mentor",
            description="A teacher or neighbor took you under their wing.",
            min_age=5, max_age=12, weight=4.0,
            required_conditions={"smarts": (40, 100)},
            impacts={"happiness": 10, "smarts": 5, "karma": 5},
            tags=["education", "social"],
        ),
        EventTemplate(
            event_id="sibling_born",
            name="Sibling Born",
            description="A new sibling entered the family.",
            min_age=2, max_age=10, weight=8.0,
            impacts={"happiness": 5, "karma": 3},
            tags=["social"],
        ),
        EventTemplate(
            event_id="parent_divorce",
            name="Parent Divorce",
            description="Your parents divorced. The household changed forever.",
            min_age=5, max_age=16, weight=5.0,
            impacts={"happiness": -20, "karma": -10},
            tags=["social"],
        ),
        # ── Additional Teen Events ──
        EventTemplate(
            event_id="driving_license",
            name="Driving License",
            description="You got your driver's license. Freedom at last.",
            min_age=16, max_age=19, weight=10.0,
            required_conditions={"happiness": (30, 100)},
            impacts={"happiness": 15, "looks": 2},
            tags=["social"],
        ),
        EventTemplate(
            event_id="teen_pregnancy",
            name="Teen Pregnancy",
            description="An unexpected pregnancy changed your teen years.",
            min_age=13, max_age=19, weight=3.0,
            impacts={"happiness": -20, "health": -10, "karma": -5},
            tags=["social", "health"],
        ),
        EventTemplate(
            event_id="drug_exposure",
            name="Drug Exposure",
            description="You were offered drugs at a party. You tried them.",
            min_age=14, max_age=20, weight=4.0,
            impacts={"happiness": -10, "health": -10, "karma": -15},
            tags=["health", "social"],
        ),
        EventTemplate(
            event_id="volunteering",
            name="Volunteering",
            description="You started volunteering at a local organization.",
            min_age=14, max_age=19, weight=5.0,
            impacts={"happiness": 10, "karma": 10, "smarts": 3},
            tags=["social"],
        ),
        # ── Additional Young Adult Events ──
        EventTemplate(
            event_id="graduate_school",
            name="Graduate School",
            description="You pursued advanced education.",
            min_age=22, max_age=30, weight=6.0,
            required_conditions={"smarts": (55, 100)},
            impacts={"smarts": 15, "debt": 30000, "happiness": 10},
            tags=["education"],
        ),
        EventTemplate(
            event_id="startup_launch",
            name="Startup Launch",
            description="You launched your own company. The risk was enormous.",
            min_age=22, max_age=35, weight=3.0,
            required_conditions={"is_employed": True},
            impacts={"money": -10000, "happiness": 20, "stress": 0},
            tags=["career", "finance"],
        ),
        EventTemplate(
            event_id="marriage",
            name="Marriage",
            description="You found your partner and got married.",
            min_age=20, max_age=35, weight=8.0,
            required_conditions={"relationship_status": "Single"},
            impacts={"happiness": 25, "karma": 10},
            tags=["romance", "social"],
        ),
        EventTemplate(
            event_id="house_purchase",
            name="House Purchase",
            description="You bought your first home. A major milestone.",
            min_age=22, max_age=40, weight=6.0,
            required_conditions={"money": (20000, 999999)},
            impacts={"money": -50000, "happiness": 20, "debt": 100000},
            tags=["finance"],
        ),
        EventTemplate(
            event_id="job_loss",
            name="Job Loss",
            description="You were laid off. The uncertainty is terrifying.",
            min_age=20, max_age=50, weight=5.0,
            required_conditions={"is_employed": True},
            impacts={"happiness": -20, "money": -2000},
            tags=["career"],
        ),
        EventTemplate(
            event_id="promotion_fast_track",
            name="Fast-Track Promotion",
            description="Your exceptional performance earned you a rapid rise.",
            min_age=25, max_age=40, weight=4.0,
            required_conditions={"is_employed": True, "smarts": (65, 100)},
            impacts={"happiness": 15, "money": 15000, "stress": 0},
            tags=["career"],
        ),
        # ── Additional Adult Events ──
        EventTemplate(
            event_id="divorce",
            name="Divorce",
            description="Your marriage ended in divorce. Financially and emotionally draining.",
            min_age=25, max_age=55, weight=5.0,
            required_conditions={"relationship_status": "Married"},
            impacts={"happiness": -20, "money": -10000},
            relation_impacts={"partner": {"closeness": -100, "status": 6}},
            tags=["romance", "finance"],
        ),
        EventTemplate(
            event_id="child_born",
            name="Child Born",
            description="You became a parent. Life changed forever.",
            min_age=20, max_age=45, weight=8.0,
            impacts={"happiness": 20, "karma": 15, "money": -5000},
            tags=["social"],
        ),
        EventTemplate(
            event_id="home_renovation",
            name="Home Renovation",
            description="You renovated your home. Expensive but worth it.",
            min_age=25, max_age=55, weight=4.0,
            impacts={"money": -30000, "happiness": 10},
            tags=["finance"],
        ),
        EventTemplate(
            event_id="career_change",
            name="Career Change",
            description="You left your career and started something new.",
            min_age=28, max_age=50, weight=5.0,
            required_conditions={"is_employed": True},
            impacts={"happiness": 10, "money": -5000, "smarts": 5},
            tags=["career"],
        ),
        EventTemplate(
            event_id="betrayal",
            name="Betrayal",
            description="A close friend or partner betrayed your trust.",
            min_age=20, max_age=55, weight=4.0,
            impacts={"happiness": -20, "karma": -15},
            tags=["social"],
        ),
        EventTemplate(
            event_id="discovery",
            name="Major Discovery",
            description="You made a breakthrough discovery or invention.",
            min_age=25, max_age=50, weight=2.0,
            required_conditions={"smarts": (70, 100)},
            impacts={"happiness": 20, "money": 50000, "smarts": 10},
            tags=["education", "career"],
        ),
        EventTemplate(
            event_id="natural_disaster",
            name="Natural Disaster",
            description="A natural disaster struck your area. You lost possessions.",
            min_age=18, max_age=70, weight=3.0,
            impacts={"money": -20000, "happiness": -15, "health": -5},
            tags=["health", "finance"],
        ),
        # ── Additional Midlife Events ──
        EventTemplate(
            event_id="empty_nest",
            name="Empty Nest",
            description="Your children left home. You feel a mix of pride and loneliness.",
            min_age=45, max_age=65, weight=6.0,
            impacts={"happiness": -5, "karma": 5},
            tags=["social"],
        ),
        EventTemplate(
            event_id="second_marriage",
            name="Second Marriage",
            description="You found love again and remarried.",
            min_age=40, max_age=60, weight=4.0,
            impacts={"happiness": 20, "karma": 10},
            tags=["romance"],
        ),
        EventTemplate(
            event_id="career_peak",
            name="Career Peak",
            description="You reached the pinnacle of your professional life.",
            min_age=40, max_age=55, weight=3.0,
            required_conditions={"is_employed": True},
            impacts={"happiness": 20, "money": 50000},
            tags=["career"],
        ),
        EventTemplate(
            event_id="health_recovery",
            name="Health Recovery",
            description="You recovered from a serious health scare.",
            min_age=40, max_age=70, weight=5.0,
            required_conditions={"health": (20, 60)},
            impacts={"health": 20, "happiness": 15},
            tags=["health"],
        ),
        EventTemplate(
            event_id="financial_crisis",
            name="Financial Crisis",
            description="You faced a severe financial setback. Investments lost value.",
            min_age=30, max_age=60, weight=4.0,
            impacts={"money": -30000, "happiness": -15, "debt": 15000},
            tags=["finance"],
        ),
        EventTemplate(
            event_id="mentorship",
            name="Mentorship Role",
            description="You became a mentor to a younger colleague.",
            min_age=35, max_age=55, weight=5.0,
            required_conditions={"is_employed": True},
            impacts={"happiness": 15, "karma": 10, "smarts": 3},
            tags=["career", "social"],
        ),
        # ── Additional Senior Events ──
        EventTemplate(
            event_id="grandparent_role",
            name="Grandparent Role",
            description="You became a grandparent. A new generation of joy.",
            min_age=55, max_age=80, weight=7.0,
            impacts={"happiness": 25, "karma": 10},
            tags=["social"],
        ),
        EventTemplate(
            event_id="retirement_party",
            name="Retirement Party",
            description="Your colleagues threw you a retirement celebration.",
            min_age=60, max_age=70, weight=8.0,
            required_conditions={"is_employed": True},
            impacts={"happiness": 20, "karma": 5},
            tags=["career"],
        ),
        EventTemplate(
            event_id="late_invention",
            name="Late-Invention",
            description="You created something meaningful in your later years.",
            min_age=60, max_age=80, weight=2.0,
            required_conditions={"smarts": (60, 100)},
            impacts={"happiness": 20, "money": 10000, "smarts": 5},
            tags=["career", "education"],
        ),
        EventTemplate(
            event_id="wisdom",
            name="Wisdom Gathering",
            description="You reflected on your life and found peace with your choices.",
            min_age=65, max_age=90, weight=6.0,
            impacts={"happiness": 15, "karma": 10},
            tags=["social"],
        ),
        EventTemplate(
            event_id="loneliness",
            name="Loneliness",
            description="The years have left you feeling isolated.",
            min_age=70, max_age=95, weight=5.0,
            impacts={"happiness": -15, "health": -5},
            tags=["social", "health"],
        ),
        EventTemplate(
            event_id="legacy",
            name="Building Legacy",
            description="You focused on leaving something behind for future generations.",
            min_age=60, max_age=85, weight=4.0,
            impacts={"happiness": 15, "karma": 15, "money": -10000},
            tags=["social"],
        ),
        # ── Environment Events (national/international) ──
        EventTemplate(
            event_id="recession",
            name="Economic Recession",
            description="The economy entered a recession. Jobs and investments suffered.",
            min_age=18, max_age=70, weight=4.0,
            impacts={"money": -15000, "happiness": -10},
            tags=["finance", "national"],
        ),
        EventTemplate(
            event_id="tech_boom",
            name="Technology Boom",
            description="A tech boom created new opportunities and wealth.",
            min_age=20, max_age=50, weight=3.0,
            impacts={"money": 20000, "happiness": 10, "smarts": 5},
            tags=["finance", "national"],
        ),
        EventTemplate(
            event_id="war",
            name="War",
            description="Armed conflict disrupted your life and country.",
            min_age=18, max_age=70, weight=2.0,
            required_conditions={"health": (31, 100)},
            impacts={"happiness": -30, "health": -15, "money": -20000},
            tags=["national", "international"],
        ),
        EventTemplate(
            event_id="pandemic",
            name="Pandemic",
            description="A global pandemic changed life as you knew it.",
            min_age=18, max_age=80, weight=3.0,
            required_conditions={"health": (31, 100)},
            impacts={"health": -15, "happiness": -15, "money": -5000},
            tags=["health", "national", "international"],
        ),
        EventTemplate(
            event_id="policy_change",
            name="Policy Change",
            description="New government policies affected your financial situation.",
            min_age=25, max_age=65, weight=4.0,
            impacts={"money": -5000, "happiness": -5},
            tags=["national"],
        ),
        EventTemplate(
            event_id="climate_event",
            name="Climate Event",
            description="An extreme weather event caused damage and disruption.",
            min_age=18, max_age=75, weight=3.0,
            impacts={"happiness": -10, "health": -5, "money": -10000},
            tags=["health", "national"],
        ),
        # ── Desire-Driven Events ──
        EventTemplate(
            event_id="pursue_fame",
            name="Pursuit of Fame",
            description="You chased recognition and public acclaim.",
            min_age=20, max_age=50, weight=3.0,
            impacts={"happiness": 10, "looks": 2},
            tags=["career", "social"],
        ),
        EventTemplate(
            event_id="seek_security",
            name="Seeking Security",
            description="You prioritized stability over risk. You played it safe.",
            min_age=25, max_age=55, weight=5.0,
            impacts={"happiness": 5, "money": 5000},
            tags=["finance"],
        ),
        EventTemplate(
            event_id="knowledge_quest",
            name="Knowledge Quest",
            description="You devoted yourself to learning and intellectual growth.",
            min_age=18, max_age=60, weight=4.0,
            impacts={"smarts": 10, "happiness": 5},
            tags=["education"],
        ),
    ]

    return events


# ─── Event Engine ────────────────────────────────────────────────────────────

class EventEngine:
    """Deterministic event engine — rolls against the event table each simulation tick."""

    def __init__(self, events: list[EventTemplate] = None):
        self.events = events or build_life_events()

    def roll_events(self, character: Character, relations: RelationGraph = None, max_events: int = 3) -> list[dict]:
        """Roll for events this tick. Returns list of triggered events with their impacts."""
        candidates = [e for e in self.events if e.check_conditions(character)]

        if not candidates:
            return []

        # Weight by character state
        weighted = []
        for event in candidates:
            w = event.weight
            # Health events become LESS likely when the character is already
            # fragile (prevents the mid-20s death spiral from stacked hits),
            # and recovery becomes much more likely.
            if "health" in event.tags:
                if character.health < 40:
                    w *= 0.4
                elif character.health < 60:
                    w *= 0.8
            if event.event_id == "health_recovery" and character.health < 40:
                w *= 2.5
            if "career" in event.tags and character.is_employed:
                w *= 1.3
            if "finance" in event.tags and character.money > 10000:
                w *= 1.2
            weighted.append((event, w))

        events_list = [e for e, _ in weighted]
        weights = [w for _, w in weighted]

        # Cap stacked health damage per tick so several unlucky rolls in one
        # year can't drop a character from healthy to dead.
        year_health_damage = 0.0
        MAX_HEALTH_DAMAGE_PER_TICK = 20

        triggered = []
        for _ in range(min(max_events, len(events_list))):
            if not events_list:
                break
            chosen = character.weighted_choice(events_list, weights)
            idx = events_list.index(chosen)

            # Dampen further health damage once the per-tick cap is hit.
            health_delta = chosen.impacts.get("health", 0)
            if isinstance(health_delta, (int, float)) and health_delta < 0:
                remaining = MAX_HEALTH_DAMAGE_PER_TICK - year_health_damage
                if remaining <= 0:
                    health_delta = 0
                elif health_delta < -remaining:
                    health_delta = -remaining
                if health_delta != chosen.impacts.get("health", 0):
                    dampened_impacts = dict(chosen.impacts)
                    dampened_impacts["health"] = health_delta
                    chosen = EventTemplate(
                        event_id=chosen.event_id,
                        name=chosen.name,
                        description=chosen.description,
                        min_age=chosen.min_age,
                        max_age=chosen.max_age,
                        weight=chosen.weight,
                        required_conditions=dict(chosen.required_conditions),
                        impacts=dampened_impacts,
                        relation_impacts=dict(chosen.relation_impacts),
                        tags=list(chosen.tags),
                    )

            changes = chosen.apply(character, relations)
            year_health_damage += changes.get("health", 0) if changes.get("health", 0) < 0 else 0
            triggered.append({
                "event_id": chosen.event_id,
                "name": chosen.name,
                "description": chosen.description,
                "changes": changes,
            })
            events_list.pop(idx)
            weights.pop(idx)

        return triggered
