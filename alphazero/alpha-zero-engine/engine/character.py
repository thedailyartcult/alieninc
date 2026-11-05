"""Character model — BitLife-style attributes as deterministic state integers."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from engine.social_variables import SocialVariable, get_all_variables, get_variable


class Gender(Enum):
    MALE = "male"
    FEMALE = "female"
    NON_BINARY = "non_binary"


@dataclass
class Character:
    """Deterministic character state. All attributes are bounded integers 0-100."""

    # Core attributes (BitLife-style)
    happiness: int = 50
    health: int = 70
    smarts: int = 50
    looks: int = 50
    karma: int = 50

    # Financial state
    money: float = 0.0
    debt: float = 0.0
    net_worth: float = 0.0

    # Demographics
    name: str = "Unknown"
    age: int = 0
    gender: Gender = Gender.MALE
    birthplace: str = "Unknown"
    current_city: str = "Unknown"

    # Life state
    is_alive: bool = True
    is_employed: bool = False
    occupation: str = "Unemployed"
    education_level: str = "None"
    relationship_status: str = "Single"

    # Portfolio state (for finance simulation)
    portfolio_value: float = 0.0
    portfolio_allocations: dict = field(default_factory=dict)

    # Relations graph (relation_id -> Relation)
    relations: dict = field(default_factory=dict)

    # Event log
    event_log: list = field(default_factory=list)

    # Simulation metadata
    universe_id: str = "anchor"
    seed: int = 0
    year: int = 2026

    # Social variables (34 variables across 5 layers)
    social_variables: dict = field(default_factory=dict)

    # Causal chain tracking
    causal_chain: list = field(default_factory=list)

    # Desire-driven state
    desires: dict = field(default_factory=dict)

    # Environment events witnessed
    environment_events: list = field(default_factory=list)

    # Layered memory (short-term, medium-term, long-term)
    memory_short: list = field(default_factory=list)
    memory_medium: list = field(default_factory=list)
    memory_long: list = field(default_factory=list)

    # Random state (deterministic per universe)
    _rng: Optional[random.Random] = field(default=None, repr=False)

    def __post_init__(self):
        if not self.social_variables:
            self.social_variables = {v.var_id: v.value for v in get_all_variables()}
        if not self.desires:
            self.desires = self._init_desires()
        if self._rng is None:
            self._rng = random.Random(self.seed)
        self._recalc_net_worth()

    def _recalc_net_worth(self):
        self.net_worth = self.money + self.portfolio_value - self.debt

    def _init_desires(self) -> dict:
        return {
            "wealth": self.money > 10000,
            "fame": self.happiness > 60,
            "security": self.health > 60,
            "knowledge": self.smarts > 60,
            "belonging": self.karma > 50,
            "power": self.is_employed,
            "freedom": self.relationship_status == "Single",
        }

    def get_social_variable(self, var_id: str) -> int:
        return self.social_variables.get(var_id, 50)

    def set_social_variable(self, var_id: str, value: int) -> int:
        var = get_variable(var_id)
        if var:
            clamped = max(0, min(100, value))
            self.social_variables[var_id] = clamped
            return clamped
        return 50

    def modify_social_variable(self, var_id: str, delta: int) -> int:
        current = self.get_social_variable(var_id)
        return self.set_social_variable(var_id, current + delta)

    def get_layer_score(self, layer: str) -> float:
        from engine.social_variables import get_variables_by_layer
        vars = get_variables_by_layer(layer)
        if not vars:
            return 50.0
        return sum(self.get_social_variable(v.var_id) for v in vars) / len(vars)

    def get_overall_social_score(self) -> float:
        return sum(self.social_variables.values()) / len(self.social_variables) if self.social_variables else 50.0

    def add_causal_chain(self, cause: str, effect: str, result: str) -> None:
        self.causal_chain.append({"cause": cause, "effect": effect, "result": result})

    def add_desire(self, desire: str, strength: float) -> None:
        self.desires[desire] = strength

    def get_dominant_desire(self) -> Optional[str]:
        if not self.desires:
            return None
        return max(self.desires, key=self.desires.get)

    def add_memory(self, category: str, entry: dict) -> None:
        if category == "short":
            self.memory_short.append(entry)
            if len(self.memory_short) > 10:
                self.memory_medium.append(self.memory_short.pop(0))
        elif category == "medium":
            self.memory_medium.append(entry)
            if len(self.memory_medium) > 20:
                self.memory_long.append(self.memory_medium.pop(0))
        elif category == "long":
            self.memory_long.append(entry)

    def add_environment_event(self, year: int, description: str, category: str) -> None:
        self.environment_events.append({"year": year, "description": description, "category": category})

    @property
    def rng(self) -> random.Random:
        return self._rng

    def roll(self, min_val: int = 1, max_val: int = 100) -> int:
        """Deterministic dice roll using this character's RNG."""
        return self._rng.randint(min_val, max_val)

    def weighted_choice(self, choices: list, weights: list):
        """Weighted random choice using this character's RNG."""
        return self._rng.choices(choices, weights=weights, k=1)[0]

    def clamp_attr(self, attr: str, value: int) -> int:
        """Clamp an attribute to 0-100 and return the new value."""
        clamped = max(0, min(100, value))
        setattr(self, attr, clamped)
        return clamped

    def modify(self, attr: str, delta: int) -> int:
        """Modify an attribute by delta, clamped to 0-100."""
        current = getattr(self, attr)
        return self.clamp_attr(attr, current + delta)

    def add_event(self, age: int, year: int, event_type: str, description: str, impact: dict = None):
        """Log an event to the character's timeline."""
        self.event_log.append({
            "age": age,
            "year": year,
            "type": event_type,
            "description": description,
            "impact": impact or {},
        })

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "age": self.age,
            "year": self.year,
            "gender": self.gender.value,
            "happiness": self.happiness,
            "health": self.health,
            "smarts": self.smarts,
            "looks": self.looks,
            "karma": self.karma,
            "money": self.money,
            "debt": self.debt,
            "net_worth": self.net_worth,
            "portfolio_value": self.portfolio_value,
            "is_alive": self.is_alive,
            "is_employed": self.is_employed,
            "occupation": self.occupation,
            "education_level": self.education_level,
            "relationship_status": self.relationship_status,
            "universe_id": self.universe_id,
            "seed": self.seed,
            "event_count": len(self.event_log),
            "social_variables": self.social_variables,
            "causal_chain": self.causal_chain,
            "desires": self.desires,
            "environment_events": self.environment_events,
            "memory_short": self.memory_short,
            "memory_medium": self.memory_medium,
            "memory_long": self.memory_long,
        }

    def copy(self, universe_id: str = None, seed: int = None) -> Character:
        """Create a deep copy for parallel universe branching."""
        new_seed = seed if seed is not None else self._rng.randint(0, 2**32)
        return Character(
            happiness=self.happiness,
            health=self.health,
            smarts=self.smarts,
            looks=self.looks,
            karma=self.karma,
            money=self.money,
            debt=self.debt,
            net_worth=self.net_worth,
            name=self.name,
            age=self.age,
            gender=self.gender,
            birthplace=self.birthplace,
            current_city=self.current_city,
            is_alive=self.is_alive,
            is_employed=self.is_employed,
            occupation=self.occupation,
            education_level=self.education_level,
            relationship_status=self.relationship_status,
            portfolio_value=self.portfolio_value,
            portfolio_allocations=dict(self.portfolio_allocations),
            relations=dict(self.relations),
            event_log=list(self.event_log),
            universe_id=universe_id or f"branch-{new_seed}",
            seed=new_seed,
            year=self.year,
            social_variables=dict(self.social_variables),
            causal_chain=list(self.causal_chain),
            desires=dict(self.desires),
            environment_events=list(self.environment_events),
            memory_short=list(self.memory_short),
            memory_medium=list(self.memory_medium),
            memory_long=list(self.memory_long),
        )
