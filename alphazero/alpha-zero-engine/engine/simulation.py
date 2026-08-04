"""Main simulation orchestrator — ties FSM, Monte Carlo, and Finance together."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from engine.character import Character, Gender
from engine.relations import RelationGraph, Relation, RelationType, RelationStatus
from engine.fsm import FSM, SimulationStep
from engine.monte_carlo import MonteCarloEngine, MultiverseReport
from finance.portfolio import PortfolioEngine
from finance.market import MarketSimulator
from finance.metrics import compute_metrics


@dataclass
class SimulationConfig:
    """Configuration for a simulation run."""

    # Character setup
    name: str = "Player"
    age: int = 0
    gender: Gender = Gender.MALE
    birthplace: str = "Manila"
    current_city: str = "Manila"

    # Initial attributes
    happiness: int = 50
    health: int = 70
    smarts: int = 50
    looks: int = 50
    karma: int = 50

    # Financial setup
    starting_money: float = 0.0
    starting_debt: float = 0.0

    # Simulation parameters
    seed: int = 42
    num_universes: int = 100
    max_workers: int = 4
    max_age: int = 100

    # Finance parameters
    initial_portfolio: float = 0.0
    portfolio_strategy: str = "balanced"


class SimulationOrchestrator:
    """
    High-level simulation interface.

    Usage:
        orchestrator = SimulationOrchestrator(SimulationConfig(name="John", age=20))
        result = orchestrator.run_single()       # Single universe
        report = orchestrator.run_multiverse()   # Parallel universes
    """

    def __init__(self, config: SimulationConfig = None):
        self.config = config or SimulationConfig()
        self.fsm = FSM(seed=self.config.seed)
        self.monte_carlo = MonteCarloEngine(fsm=self.fsm)
        self.portfolio_engine = PortfolioEngine()
        self.market_sim = MarketSimulator(seed=self.config.seed)

    def create_character(self) -> Character:
        """Create a character from config."""
        return Character(
            name=self.config.name,
            age=self.config.age,
            gender=self.config.gender,
            birthplace=self.config.birthplace,
            current_city=self.config.current_city,
            happiness=self.config.happiness,
            health=self.config.health,
            smarts=self.config.smarts,
            looks=self.config.looks,
            karma=self.config.karma,
            money=self.config.starting_money,
            debt=self.config.starting_debt,
            portfolio_value=self.config.initial_portfolio,
            seed=self.config.seed,
            year=2026,
        )

    def create_default_relations(self, character: Character) -> RelationGraph:
        """Create a default relation graph based on character age."""
        graph = RelationGraph()

        age = character.age

        # Parents (always exist if age < 60)
        if age < 60:
            graph.add(Relation(
                relation_id="parent_mother",
                name="Mother",
                relation_type=RelationType.PARENT,
                status=RelationStatus.CLOSE,
                closeness=70,
                influence=1.5,
                age=age + 25,
            ))
            graph.add(Relation(
                relation_id="parent_father",
                name="Father",
                relation_type=RelationType.PARENT,
                status=RelationStatus.CLOSE,
                closeness=60,
                influence=1.2,
                age=age + 28,
            ))

        # Sibling (50% chance)
        if character.roll(1, 100) <= 50:
            graph.add(Relation(
                relation_id="sibling_1",
                name="Sibling",
                relation_type=RelationType.SIBLING,
                status=RelationStatus.CLOSE,
                closeness=65,
                influence=0.8,
                age=age + character.rng.randint(-5, 5),
            ))

        # Partner (if age >= 18)
        if age >= 18:
            graph.add(Relation(
                relation_id="partner_1",
                name="Partner",
                relation_type=RelationType.PARTNER,
                status=RelationStatus.ROMANTIC if age < 30 else RelationStatus.MARRIED,
                closeness=75 if age >= 25 else 60,
                influence=1.3,
                age=age + character.rng.randint(-3, 3),
            ))

        # Friend
        graph.add(Relation(
            relation_id="friend_1",
            name="Best Friend",
            relation_type=RelationType.FRIEND,
            status=RelationStatus.CLOSE,
            closeness=80,
            influence=0.6,
            age=age + character.rng.randint(-5, 5),
        ))

        return graph

    def run_single(self) -> list[SimulationStep]:
        """Run a single universe simulation."""
        character = self.create_character()
        relations = self.create_default_relations(character)

        # Run FSM
        steps = self.fsm.run_simulation(character, relations)

        # Apply portfolio simulation
        if self.config.initial_portfolio > 0:
            for step in steps:
                year_return = self.market_sim.get_year_return(step.year)
                self.portfolio_engine.apply_annual_return(
                    character, year_return, self.config.portfolio_strategy
                )

        return steps

    def run_multiverse(self) -> MultiverseReport:
        """Run parallel universe simulation."""
        character = self.create_character()
        relations = self.create_default_relations(character)

        # Run Monte Carlo
        report = self.monte_carlo.run_multiverse(
            character, relations,
            num_universes=self.config.num_universes,
            max_workers=self.config.max_workers,
        )

        # Compute finance metrics
        metrics = compute_metrics(report)

        return report

    def run_with_portfolio(self, strategy: str = "balanced") -> dict:
        """Run simulation with portfolio tracking."""
        character = self.create_character()
        relations = self.create_default_relations(character)

        if character.portfolio_value <= 0:
            character.portfolio_value = 100000  # Default P100k

        character.portfolio_allocations = self.portfolio_engine.get_default_allocation(strategy)

        steps = self.fsm.run_simulation(character, relations)

        # Track portfolio per year
        portfolio_history = []
        for step in steps:
            year_return = self.market_sim.get_year_return(step.year)
            self.portfolio_engine.apply_annual_return(character, year_return, strategy)
            portfolio_history.append({
                "age": step.age,
                "year": step.year,
                "portfolio_value": character.portfolio_value,
                "net_worth": character.net_worth,
                "year_return": year_return,
            })

        return {
            "character": character.to_dict(),
            "steps": len(steps),
            "portfolio_history": portfolio_history,
            "final_portfolio_value": character.portfolio_value,
            "final_net_worth": character.net_worth,
            "total_return": (character.portfolio_value / 100000 - 1) * 100,
        }
