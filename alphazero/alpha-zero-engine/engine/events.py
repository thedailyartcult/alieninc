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
            impacts={"happiness": 5, "karma": -10, "health": -5},
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
            impacts={"happiness": -25, "health": -5},
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
            impacts={"happiness": 15, "money": 8000, "health": -5},
            tags=["career"],
        ),
        EventTemplate(
            event_id="health_scare",
            name="Health Scare",
            description="A routine checkup revealed something concerning.",
            min_age=35, max_age=60, weight=5.0,
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
            impacts={"health": -20, "happiness": -10},
            tags=["health"],
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
            # Boost events that match character's current state
            if "health" in event.tags and character.health < 40:
                w *= 1.5
            if "career" in event.tags and character.is_employed:
                w *= 1.3
            if "finance" in event.tags and character.money > 10000:
                w *= 1.2
            weighted.append((event, w))

        events_list = [e for e, _ in weighted]
        weights = [w for _, w in weighted]

        triggered = []
        for _ in range(min(max_events, len(events_list))):
            if not events_list:
                break
            chosen = character.weighted_choice(events_list, weights)
            idx = events_list.index(chosen)
            changes = chosen.apply(character, relations)
            triggered.append({
                "event_id": chosen.event_id,
                "name": chosen.name,
                "description": chosen.description,
                "changes": changes,
            })
            events_list.pop(idx)
            weights.pop(idx)

        return triggered
