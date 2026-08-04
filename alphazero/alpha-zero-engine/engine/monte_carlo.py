"""Monte Carlo engine — parallel universe branching and convergence analysis."""

from __future__ import annotations

import concurrent.futures
import json
import statistics
from dataclasses import dataclass, field
from pathlib import Path
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
    convergence_score: float = 0.0
    social_variables: dict = field(default_factory=dict)
    desires: dict = field(default_factory=dict)
    causal_chain: list = field(default_factory=list)
    environment_events: list = field(default_factory=list)
    memory_short: list = field(default_factory=list)
    memory_medium: list = field(default_factory=list)
    memory_long: list = field(default_factory=list)
    event_log: list = field(default_factory=list)


@dataclass
class ClusterResult:
    """Result of clustering universes by outcome similarity."""

    cluster_id: str
    members: list[str]
    avg_net_worth: float
    avg_happiness: float
    count: int
    representative_universe: Optional[str] = None


@dataclass
class MultiverseReport:
    """Aggregated report across all parallel universes."""

    anchor_universe: UniverseResult
    parallel_universes: list[UniverseResult]
    total_simulations: int
    best_net_worth: UniverseResult
    best_happiness: UniverseResult
    convergence_rate: float
    sharpe_ratio: float = 0.0
    alpha: float = 0.0
    beta: float = 0.0
    avg_years_lived: float = 0.0
    outcome_distribution: dict = field(default_factory=dict)
    high_probability_path: bool = False
    convergence_threshold: float = 0.85
    chaotic_injections: int = 0
    clusters: list[ClusterResult] = field(default_factory=list)


class MonteCarloEngine:
    """
    Runs N parallel universe simulations from the same anchor character.

    Each universe gets a different seed, causing different dice rolls and event triggers.
    After all simulations complete, we analyze convergence and surface the best branches.

    Phase 2: Supports 10,000+ universes, chaotic micro-variable injection,
    universe serialization, convergence probability analysis, best branch surfacing,
    and universe clustering.
    """

    def __init__(self, fsm: FSM = None):
        self.fsm = fsm or FSM()

    def _inject_chaos(self, char: Character, injection_rate: float = 0.15) -> int:
        """Inject chaotic micro-variables into a character's social variables.

        Returns the number of injections performed.
        """
        count = 0
        if not hasattr(char, 'social_variables') or not char.social_variables:
            return count
        var_ids = list(char.social_variables.keys())
        for var_id in var_ids:
            if char._rng.random() < injection_rate:
                delta = int(char._rng.gauss(0, 5))
                current = char.social_variables.get(var_id, 50)
                char.social_variables[var_id] = max(0, min(100, current + delta))
                count += 1
        return count

    def _run_single_universe(self, character: Character, relations: RelationGraph, universe_id: str, seed: int, inject_chaos: bool = False) -> UniverseResult:
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

        # Inject chaotic micro-variables if requested
        injections = 0
        if inject_chaos:
            injections = self._inject_chaos(char_copy)

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
            social_variables=dict(char_copy.social_variables) if hasattr(char_copy, 'social_variables') else {},
            desires=dict(char_copy.desires) if hasattr(char_copy, 'desires') else {},
            causal_chain=list(char_copy.causal_chain) if hasattr(char_copy, 'causal_chain') else [],
            environment_events=list(char_copy.environment_events) if hasattr(char_copy, 'environment_events') else [],
            memory_short=list(char_copy.memory_short) if hasattr(char_copy, 'memory_short') else [],
            memory_medium=list(char_copy.memory_medium) if hasattr(char_copy, 'memory_medium') else [],
            memory_long=list(char_copy.memory_long) if hasattr(char_copy, 'memory_long') else [],
            event_log=list(char_copy.event_log) if hasattr(char_copy, 'event_log') else [],
        )

    def run_multiverse(
        self,
        character: Character,
        relations: RelationGraph,
        num_universes: int = 100,
        max_workers: int = 4,
        inject_chaos: bool = False,
        injection_rate: float = 0.15,
    ) -> MultiverseReport:
        """
        Run N parallel universes concurrently.

        Args:
            character: The anchor character state
            relations: The anchor relation graph
            num_universes: Number of parallel simulations (supports 10,000+)
            max_workers: Thread pool size
            inject_chaos: Enable chaotic micro-variable injection per universe
            injection_rate: Probability of injecting chaos into each social variable

        Returns:
            MultiverseReport with aggregated results
        """
        # Run anchor universe first
        anchor = self._run_single_universe(
            character, relations,
            universe_id="anchor",
            seed=character.seed,
            inject_chaos=False,
        )

        # Run parallel universes
        futures = []
        results = []
        total_injections = 0

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            for i in range(num_universes):
                seed = character.rng.randint(0, 2**32)
                future = executor.submit(
                    self._run_single_universe,
                    character, relations,
                    universe_id=f"universe-{i+1}",
                    seed=seed,
                    inject_chaos=inject_chaos,
                )
                futures.append(future)

            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                results.append(result)
                if inject_chaos:
                    total_injections += sum(1 for v in result.social_variables.values() if v != 50)

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

        # Convergence probability analysis (85% threshold for high-probability)
        high_probability = convergence_rate >= 0.85

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
            high_probability_path=high_probability,
            convergence_threshold=0.85,
            chaotic_injections=total_injections,
        )

    def branch_from_point(
        self,
        character: Character,
        relations: RelationGraph,
        branch_age: int,
        modification: dict,
        num_branches: int = 50,
        inject_chaos: bool = False,
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

        return self.run_multiverse(branch_char, relations, num_universes=num_branches, inject_chaos=inject_chaos)

    def find_best_branch(
        self,
        report: MultiverseReport,
        metric: str = "net_worth",
    ) -> UniverseResult:
        """Surface the best-performing branch across all universes by a given metric.

        Metric can be 'net_worth', 'happiness', or 'convergence'.
        """
        if metric == "net_worth":
            return report.best_net_worth
        elif metric == "happiness":
            return report.best_happiness
        elif metric == "convergence":
            # Best = most typical universe (closest to mean)
            nw_mean = statistics.mean(r.final_net_worth for r in report.parallel_universes)
            return min(report.parallel_universes, key=lambda r: abs(r.final_net_worth - nw_mean))
        else:
            raise ValueError(f"Unknown metric '{metric}'. Use 'net_worth', 'happiness', or 'convergence'.")

    def cluster_universes(
        self,
        report: MultiverseReport,
        num_clusters: int = 4,
    ) -> list[ClusterResult]:
        """Group similar universe outcomes into clusters and surface representative branches.

        Uses net worth and happiness as clustering dimensions.
        """
        results = report.parallel_universes
        if not results:
            return []

        nw_values = [r.final_net_worth for r in results]
        happy_values = [r.final_happiness for r in results]

        nw_min = min(nw_values)
        nw_max = max(nw_values)
        nw_range = nw_max - nw_min if nw_max != nw_min else 1
        happy_min = min(happy_values)
        happy_max = max(happy_values)
        happy_range = happy_max - happy_min if happy_max != happy_min else 1

        # Initialize clusters
        clusters: dict[str, dict] = {}
        for i in range(num_clusters):
            clusters[f"cluster_{i}"] = {"members": [], "total_nw": 0.0, "total_happy": 0.0, "count": 0}

        for r in results:
            nw_norm = (r.final_net_worth - nw_min) / nw_range
            happy_norm = (r.final_happiness - happy_min) / happy_range
            # Simple clustering based on normalized values
            cluster_idx = min(int((nw_norm + happy_norm) / 2 * num_clusters), num_clusters - 1)
            cluster_key = f"cluster_{cluster_idx}"
            clusters[cluster_key]["members"].append(r.universe_id)
            clusters[cluster_key]["total_nw"] += r.final_net_worth
            clusters[cluster_key]["total_happy"] += r.final_happiness
            clusters[cluster_key]["count"] += 1

        # Build ClusterResult objects and find representatives
        cluster_results = []
        for key, data in clusters.items():
            if data["count"] > 0:
                avg_nw = data["total_nw"] / data["count"]
                avg_happy = data["total_happy"] / data["count"]
                # Find representative (closest to cluster average)
                cluster_members = [r for r in results if r.universe_id in data["members"]]
                representative = min(cluster_members, key=lambda r: abs(r.final_net_worth - avg_nw) + abs(r.final_happiness - avg_happy))
                cluster_results.append(ClusterResult(
                    cluster_id=key,
                    members=data["members"],
                    avg_net_worth=avg_nw,
                    avg_happiness=avg_happy,
                    count=data["count"],
                    representative_universe=representative.universe_id,
                ))

        return cluster_results

    def serialize_universe(
        self,
        result: UniverseResult,
        output_path: str = "/tmp/alpha_zero_universe.json",
    ) -> dict:
        """Serialize a universe state to a JSON file for save/load capability."""
        state = {
            "universe_id": result.universe_id,
            "seed": result.seed,
            "final_net_worth": result.final_net_worth,
            "final_happiness": result.final_happiness,
            "final_health": result.final_health,
            "years_lived": result.years_lived,
            "social_variables": result.social_variables,
            "desires": result.desires,
            "causal_chain": result.causal_chain,
            "environment_events": result.environment_events,
            "memory_short": result.memory_short,
            "memory_medium": result.memory_medium,
            "memory_long": result.memory_long,
            "event_log": result.event_log,
            "total_events": result.total_events,
            "convergence_score": result.convergence_score,
        }

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w") as f:
            json.dump(state, f, indent=2, default=str)

        return {"status": "serialized", "universe_id": result.universe_id, "output_path": str(output_file), "size_bytes": output_file.stat().st_size}

    def deserialize_universe(self, input_path: str = "/tmp/alpha_zero_universe.json") -> dict:
        """Load a previously serialized universe state from a JSON file."""
        input_file = Path(input_path)
        if not input_file.exists():
            return {"error": f"File not found: {input_path}"}

        with open(input_file) as f:
            state = json.load(f)

        return {
            "status": "deserialized",
            "universe_id": state.get("universe_id", "unknown"),
            "seed": state.get("seed", 0),
            "final_net_worth": state.get("net_worth", 0),
            "final_happiness": state.get("happiness", 50),
            "final_health": state.get("final_health", 70),
            "years_lived": state.get("years_lived", 0),
            "social_variables": state.get("social_variables", {}),
            "desires": state.get("desires", {}),
            "causal_chain": state.get("causal_chain", []),
            "environment_events": state.get("environment_events", []),
            "memory_short": state.get("memory_short", []),
            "memory_medium": state.get("memory_medium", []),
            "memory_long": state.get("memory_long", []),
            "total_events": state.get("total_events", 0),
            "convergence_score": state.get("convergence_score", 0.0),
            "serialized_at": state.get("serialized_at", "unknown"),
            "file_size": input_file.stat().st_size,
        }
