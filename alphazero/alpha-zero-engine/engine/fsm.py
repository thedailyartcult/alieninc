"""Deterministic Finite-State Machine — the core simulation loop."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from engine.character import Character
from engine.relations import RelationGraph, Relation, RelationType, RelationStatus
from engine.events import EventEngine, build_life_events

# Phase 3: Finance Engine — algorithmic portfolio management
try:
    from finance.portfolio import PortfolioEngine
    from finance.market import MarketSimulator
except ImportError:  # pragma: no cover - finance module optional
    PortfolioEngine = None
    MarketSimulator = None

# Annual salary by occupation (Phase 3)
SALARY_TABLE = {
    "Unemployed": 0.0,
    "Manual Labor": 25000.0,
    "Entry Level": 35000.0,
    "Mid Career": 65000.0,
    "Senior": 110000.0,
    "Executive": 250000.0,
    "Retired": 24000.0,
}

# Annual living expenses by life stage (Phase 3)
EXPENSE_TABLE = {
    "infant": 8000.0,
    "child": 10000.0,
    "teen": 15000.0,
    "young_adult": 30000.0,
    "adult": 42000.0,
    "midlife": 48000.0,
    "senior": 40000.0,
    "elder": 35000.0,
}


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

    def __init__(self, seed: int = 42, strategy: str = "balanced"):
        self.event_engine = EventEngine()
        self.seed = seed
        self.strategy = strategy
        self.market_sim = MarketSimulator(seed=seed) if MarketSimulator else None

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

        # Health recovers naturally while young (young bodies heal fast),
        # countering small event damage so characters don't death-spiral.
        if character.age < 30:
            target = 85
            if character.health < target:
                delta = character.roll(2, 4)
                character.modify("health", delta)
                changes["health"] = delta
        elif character.age < 40:
            target = 75
            if character.health < target:
                delta = character.roll(1, 3)
                character.modify("health", delta)
                changes["health"] = delta
        elif character.age < 60 and character.health < 60:
            delta = character.roll(1, 2)
            character.modify("health", delta)
            changes["health"] = delta

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

    def _career_progression(self, character: Character) -> dict:
        """Promote occupation at career milestones (Phase 3)."""
        changes = {}
        if not character.is_employed:
            return changes

        if character.age == 30 and character.occupation == "Entry Level":
            character.occupation = "Mid Career"
            changes["occupation"] = "Mid Career"
        elif character.age == 45 and character.occupation == "Mid Career":
            character.occupation = "Senior"
            changes["occupation"] = "Senior"
        elif (
            character.age == 55
            and character.occupation == "Senior"
            and character.smarts >= 60
        ):
            character.occupation = "Executive"
            changes["occupation"] = "Executive"
        return changes

    def _job_search(self, character: Character) -> dict:
        """Adults without a job try to find work (Phase 3)."""
        changes = {}
        if character.age < 22 or character.age >= 65 or character.is_employed:
            return changes

        chance = 20 + character.smarts // 2  # smarts 50 -> 45% per year
        if character.roll(1, 100) <= chance:
            if character.smarts >= 40:
                character.occupation = "Entry Level"
            else:
                character.occupation = "Manual Labor"
            character.is_employed = True
            changes["occupation"] = character.occupation
            changes["is_employed"] = True
        return changes

    def _finance_step(self, character: Character) -> dict:
        """
        Apply annual income, expenses, investment, and portfolio returns (Phase 3).

        Flow:
        1. Earn salary (or pension after retirement)
        2. Pay living expenses
        3. Invest a portion of income into the portfolio
        4. Apply market returns to the portfolio
        5. Withdraw 4% of portfolio after retirement
        6. Rebalance toward target allocations every 5 years
        """
        changes = {}

        if not PortfolioEngine or not self.market_sim:
            return changes

        salary = SALARY_TABLE.get(character.occupation, 0.0)

        # Retirement: 4% safe withdrawal from portfolio
        if character.age >= 65 and not character.is_employed:
            withdrawal = character.portfolio_value * 0.04
            character.money += withdrawal
            changes["retirement_withdrawal"] = round(withdrawal, 2)

        # Income
        character.money += salary
        changes["salary"] = round(salary, 2)

        # Expenses by life stage
        stage = self.get_life_stage(character.age).value
        expenses = EXPENSE_TABLE.get(stage, 30000.0)
        character.money -= expenses
        changes["expenses"] = round(expenses, 2)

        # Invest portion of income (smarts raise the invest rate)
        if salary > 0:
            invest_rate = 0.10 + character.smarts / 500.0  # smarts 50 -> 20%
            invest = min(max(0, salary * invest_rate), max(0, character.money))
            character.money -= invest
            character.portfolio_value += invest
            changes["invested"] = round(invest, 2)

        # Handle debt
        if character.money < 0:
            character.debt += -character.money
            character.money = 0.0
            changes["new_debt"] = round(character.debt, 2)

        # Apply market return to portfolio
        if character.portfolio_value > 0:
            year_return = self.market_sim.get_year_return(character.year)
            portfolio_return = PortfolioEngine.apply_annual_return(
                character, year_return, self.strategy
            )
            changes["portfolio_return"] = round(portfolio_return, 4)

        # Rebalance every 5 years
        if character.portfolio_value > 0 and character.age % 5 == 0:
            PortfolioEngine.rebalance(character, self.strategy)
            changes["rebalanced"] = True

        character._recalc_net_worth()
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

        # Health modifies mortality (capped at 4x so low health is risky
        # but not a guaranteed death sentence)
        health_factor = max(0.25, character.health / 100.0)
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

        # Career progression (Phase 3)
        career_changes = self._career_progression(character)

        # Job search for unemployed adults (Phase 3)
        job_changes = self._job_search(character)

        # Finance: income, expenses, investment, portfolio returns (Phase 3)
        finance_changes = self._finance_step(character)

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
