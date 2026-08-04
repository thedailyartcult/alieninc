"""Deterministic Finite-State Machine — the core simulation loop."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from engine.character import Character
from engine.relations import RelationGraph, Relation, RelationType, RelationStatus
from engine.events import EventEngine, build_life_events


class LifeStage(Enum):
    INFANT = "infant"       # 0-2
    CHILD = "child"         # 3-12
    TEEN = "teen"           # 13-19
    YOUNG_ADULT = "young_adult"  # 20-30
    ADULT = "adult"         # 31-50
    MIDLIFE = "midlife"     # 51-65
    SENIOR = "senior"       # 66-80
    ELDER = "elder"         # 81+


@dataclass
class SimulationStep:
    """Result of one simulation tick (one year)."""

    age: int
    year: int
    life_stage: str
    attributes_before: dict
    attributes_after: dict
    events: list
    relation_changes: list
    is_alive: bool
    universe_id: str


class FSM:
    """
    Deterministic finite-state machine for life simulation.

    States = LifeStage (infant, child, teen, young_adult, adult, midlife, senior, elder)
    Transitions = Age +1 Year
    Outputs = Attribute changes, events, relation updates
    """

    def __init__(self, seed: int = 42):
        self.event_engine = EventEngine()
        self.seed = seed

    @staticmethod
    def get_life_stage(age: int) -> LifeStage:
        if age <= 2:
            return LifeStage.INFANT
        elif age <= 12:
            return LifeStage.CHILD
        elif age <= 19:
            return LifeStage.TEEN
        elif age <= 30:
            return LifeStage.YOUNG_ADULT
        elif age <= 50:
            return LifeStage.ADULT
        elif age <= 65:
            return LifeStage.MIDLIFE
        elif age <= 80:
            return LifeStage.SENIOR
        else:
            return LifeStage.ELDER

    def _natural_decay(self, character: Character) -> dict:
        """Apply natural attribute changes that happen every year."""
        changes = {}

        # Health naturally declines after 40
        if character.age > 40:
            decline = max(1, (character.age - 40) // 10)
            delta = -character.roll(1, decline)
            character.modify("health", delta)
            changes["health"] = delta

        # Happiness mean-reverts toward 50
        if character.happiness > 60:
            delta = -character.roll(0, 2)
            character.modify("happiness", delta)
            changes["happiness"] = delta
        elif character.happiness < 40:
            delta = character.roll(0, 2)
            character.modify("happiness", delta)
            changes["happiness"] = delta

        # Smarts can grow slowly
        if character.age < 30:
            delta = character.roll(0, 2)
            character.modify("smarts", delta)
            changes["smarts"] = delta

        # Looks peak around 25-35
        if character.age > 35:
            delta = -character.roll(0, 1)
            character.modify("looks", delta)
            changes["looks"] = delta

        return changes

    def _life_stage_transition(self, character: Character, relations: RelationGraph) -> dict:
        """Apply changes specific to life stage transitions."""
        changes = {}
        stage = self.get_life_stage(character.age)

        if character.age == 6:
            # Start school
            character.education_level = "Elementary"
            changes["education_level"] = "Elementary"

        elif character.age == 13:
            # Start high school
            character.education_level = "High School"
            changes["education_level"] = "High School"

        elif character.age == 18:
            # Graduate high school
            character.education_level = "High School Graduate"
            changes["education_level"] = "High School Graduate"

        elif character.age == 22:
            # Possible college graduate
            if character.smarts >= 55:
                character.education_level = "College Graduate"
                character.is_employed = True
                character.occupation = "Entry Level"
                character.money += 2000
                changes["education_level"] = "College Graduate"
                changes["is_employed"] = True

        elif character.age == 65:
            # Retirement age
            if character.is_employed:
                character.is_employed = False
                character.occupation = "Retired"
                changes["is_employed"] = False

        return changes

    def _check_death(self, character: Character) -> bool:
        """Deterministic death check based on health, age, and random factors."""
        if character.health <= 0:
            return True

        # Base mortality rate increases with age
        age = character.age
        if age < 30:
            mortality = 0.001
        elif age < 50:
            mortality = 0.005
        elif age < 70:
            mortality = 0.02
        elif age < 85:
            mortality = 0.08
        else:
            mortality = 0.15

        # Health modifies mortality
        health_factor = max(0.1, character.health / 100.0)
        adjusted_mortality = mortality / health_factor

        return character.roll(1, 1000) <= int(adjusted_mortality * 1000)

    def _update_relations(self, character: Character, relations: RelationGraph) -> list[dict]:
        """Update all relations for this year."""
        changes = []

        for rel in relations.get_active():
            # Age relations
            rel.age += 1

            # Natural closeness drift
            drift = character.roll(-5, 5)
            rel.modify_closeness(drift)

            # Check for relation-specific events
            if rel.relation_type == RelationType.PARTNER:
                if rel.closeness > 70 and rel.status != RelationStatus.MARRIED:
                    rel.status = RelationStatus.MARRIED
                    character.relationship_status = "Married"
                    changes.append({"relation": rel.name, "event": "Married"})
                elif rel.closeness < 20 and rel.status == RelationStatus.MARRIED:
                    rel.status = RelationStatus.DIVORCED
                    character.relationship_status = "Divorced"
                    changes.append({"relation": rel.name, "event": "Divorced"})

            # Random relation events
            event_roll = character.roll(1, 100)
            if event_roll <= 3:
                # Conflict
                rel.modify_closeness(-15)
                changes.append({"relation": rel.name, "event": "Conflict", "closeness_delta": -15})
            elif event_roll >= 97:
                # Bonding moment
                rel.modify_closeness(10)
                changes.append({"relation": rel.name, "event": "Bonding", "closeness_delta": 10})

        return changes

    def step(self, character: Character, relations: RelationGraph) -> SimulationStep:
        """
        Execute one simulation tick (Age +1 Year).

        This is the core BitLife-style progression:
        1. Record state before
        2. Apply natural decay
        3. Apply life stage transitions
        4. Roll events
        5. Update relations
        6. Check death
        7. Record state after
        """
        # Record before state
        before = character.to_dict()

        # Advance time
        character.age += 1
        character.year += 1

        # Natural decay
        natural_changes = self._natural_decay(character)

        # Life stage transitions
        stage_changes = self._life_stage_transition(character, relations)

        # Roll events
        events = self.event_engine.roll_events(character, relations)

        # Update relations
        relation_changes = self._update_relations(character, relations)

        # Check death
        is_dead = self._check_death(character)
        if is_dead:
            character.is_alive = False

        # Record after state
        after = character.to_dict()

        return SimulationStep(
            age=character.age,
            year=character.year,
            life_stage=self.get_life_stage(character.age).value,
            attributes_before=before,
            attributes_after=after,
            events=events,
            relation_changes=relation_changes,
            is_alive=character.is_alive,
            universe_id=character.universe_id,
        )

    def run_simulation(self, character: Character, relations: RelationGraph, max_age: int = 100) -> list[SimulationStep]:
        """Run a complete life simulation from current age to death or max_age."""
        steps = []

        while character.is_alive and character.age < max_age:
            step = self.step(character, relations)
            steps.append(step)
            if not character.is_alive:
                character.add_event(character.age, character.year, "death", "Passed away")
                break

        return steps
