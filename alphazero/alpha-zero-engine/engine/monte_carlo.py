"""Monte Carlo engine — parallel universe branching and convergence analysis."""

from __future__ import annotations

import concurrent.futures
import statistics
from dataclasses import dataclass, field
from typing import Optional

from engine.character import Character
from engine.relations import RelationGraph, Relation, RelationType
from engine.fsm import FSM, SimulationStep


@dataclass
class UniverseResult:
    """Result of one parallel universe simulation."""

    universe_id: str
    seed: int
    steps: list
    final_state: dict
    total_events: int
    final_net_worth: float
    final_happiness: float
    final_health: float
    years_lived: int
    convergence_score: float = 0.0  # How similar this universe is to others


@dataclass
class MultiverseReport:
    """Aggregated report across all parallel universes."""

    anchor_universe: UniverseResult
    parallel_universes: list[UniverseResult]
    total_simulations: int
    best_net_worth: UniverseResult
    best_happiness: UniverseResult
    convergence_rate: float  # % of universes that land on similar outcomes
    sharpe_ratio: float = 0.0
    alpha: float = 0.0
    beta: float = 0.0
    avg_years_lived: float = 0.0
    outcome_distribution: dict = field(default_factory=dict)


class MonteCarloEngine:
    """
    Runs N parallel universe simulations from the same anchor character.

    Each universe gets a different seed, causing different dice rolls and event triggers.
    After all simulations complete, we analyze convergence and surface the best branches.
    """

    def __init__(self, fsm: FSM = None):
        self.fsm = fsm or FSM()

    def _run_single_universe(self, character: Character, relations: RelationGraph, universe_id: str, seed: int) -> UniverseResult:
        """Run one complete simulation in isolation."""
        char_copy = character.copy(universe_id=universe_id, seed=seed)

        # Deep copy relations
        rel_copy = RelationGraph()
        for rid, rel in relations.relations.items():
            rel_copy.relations[rid] = Relation(
                relation_id=rel.relation_id,
                name=rel.name,
                relation_type=rel.relation_type,
                status=rel.status,
                closeness=rel.closeness,
                influence=rel.influence,
                age=rel.age,
                is_alive=rel.is_alive,
                occupation=rel.occupation,
            )

        steps = self.fsm.run_simulation(char_copy, rel_copy)

        return UniverseResult(
            universe_id=universe_id,
            seed=seed,
            steps=steps,
            final_state=char_copy.to_dict(),
            total_events=sum(len(s.events) for s in steps),
            final_net_worth=char_copy.net_worth,
            final_happiness=char_copy.happiness,
            final_health=char_copy.health,
            years_lived=char_copy.age,
        )

    def run_multiverse(
        self,
        character: Character,
        relations: RelationGraph,
        num_universes: int = 100,
        max_workers: int = 4,
    ) -> MultiverseReport:
        """
        Run N parallel universes concurrently.

        Args:
            character: The anchor character state
            relations: The anchor relation graph
            num_universes: Number of parallel simulations
            max_workers: Thread pool size

        Returns:
            MultiverseReport with aggregated results
        """
        # Run anchor universe first
        anchor = self._run_single_universe(
            character, relations,
            universe_id="anchor",
            seed=character.seed,
        )

        # Run parallel universes
        futures = []
        results = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            for i in range(num_universes):
                seed = character.rng.randint(0, 2**32)
                future = executor.submit(
                    self._run_single_universe,
                    character, relations,
                    universe_id=f"universe-{i+1}",
                    seed=seed,
                )
                futures.append(future)

            for future in concurrent.futures.as_completed(futures):
                results.append(future.result())

        # Analyze convergence
        net_worths = [r.final_net_worth for r in results]
        happiness_scores = [r.final_happiness for r in results]
        years_lived = [r.years_lived for r in results]

        # Convergence: % of universes within 1 std dev of mean
        if len(net_worths) > 1:
            nw_mean = statistics.mean(net_worths)
            nw_std = statistics.stdev(net_worths) if len(net_worths) > 1 else 0
            if nw_std > 0:
                converged = sum(1 for nw in net_worths if abs(nw - nw_mean) <= nw_std)
                convergence_rate = converged / len(net_worths)
            else:
                convergence_rate = 1.0
        else:
            convergence_rate = 1.0

        # Find best universes
        best_nw = max(results, key=lambda r: r.final_net_worth)
        best_happy = max(results, key=lambda r: r.final_happiness)

        # Sharpe-like ratio: (mean return - risk_free) / std_dev
        risk_free = 0.02  # 2% baseline
        if len(net_worths) > 1 and statistics.stdev(net_worths) > 0:
            avg_return = statistics.mean(net_worths) / max(1, character.net_worth) - 1
            sharpe = (avg_return - risk_free) / (statistics.stdev(net_worths) / max(1, character.net_worth))
        else:
            sharpe = 0.0

        # Beta: volatility relative to anchor
        if anchor.final_net_worth != 0:
            beta = statistics.mean(net_worths) / anchor.final_net_worth
        else:
            beta = 1.0

        # Alpha: excess return over benchmark
        alpha = statistics.mean(net_worths) - anchor.final_net_worth

        # Outcome distribution buckets
        buckets = {"excellent": 0, "good": 0, "average": 0, "poor": 0}
        for r in results:
            if r.final_net_worth > nw_mean + nw_std:
                buckets["excellent"] += 1
            elif r.final_net_worth > nw_mean:
                buckets["good"] += 1
            elif r.final_net_worth > nw_mean - nw_std:
                buckets["average"] += 1
            else:
                buckets["poor"] += 1

        return MultiverseReport(
            anchor_universe=anchor,
            parallel_universes=results,
            total_simulations=num_universes + 1,
            best_net_worth=best_nw,
            best_happiness=best_happy,
            convergence_rate=convergence_rate,
            sharpe_ratio=sharpe,
            alpha=alpha,
            beta=beta,
            avg_years_lived=statistics.mean(years_lived),
            outcome_distribution=buckets,
        )

    def branch_from_point(
        self,
        character: Character,
        relations: RelationGraph,
        branch_age: int,
        modification: dict,
        num_branches: int = 50,
    ) -> MultiverseReport:
        """
        Fork from a specific age point with a modification.

        This is the "what if I made a different choice at age X" simulation.
        """
        # Create modified character at branch point
        branch_char = character.copy(universe_id=f"branch-point-{branch_age}")
        branch_char.age = branch_age

        # Apply modification
        for attr, value in modification.items():
            if hasattr(branch_char, attr):
                setattr(branch_char, attr, value)

        return self.run_multiverse(branch_char, relations, num_universes=num_branches)
