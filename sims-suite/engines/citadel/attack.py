"""Citadel attack simulation — run attack paths through the infra graph.

This is the "Kriegspiel turned inward" engine. It uses the same Monte Carlo
branching primitive from sims_core, but instead of military forces maneuvering
across terrain, it simulates an attacker moving laterally through your
infrastructure — exploiting vulnerabilities, escalating trust, and reaching
crown jewels.

Each branch varies the attacker's starting point, exploitation success, and
trust escalation. The aggregated report shows which nodes fall most often,
which attack paths reach crown jewels, and where the walls give first.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Optional

from sims_core.monte_carlo import monte_carlo_branch, best_branch, convergence_rate
from engines.citadel.infra_graph import (
    InfraGraph,
    InfraNode,
    NodeType,
    Vulnerability,
    create_sample_infra,
)


@dataclass
class AttackPath:
    """One simulated attack path through the infrastructure."""

    path: list[str]                     # sequence of node names compromised
    crown_jewel_reached: bool           # did the attacker reach a crown jewel?
    depth: int                          # how many hops from entry point
    nodes_compromised: int              # total nodes fallen
    entry_point: str                    # where the attacker started
    score: float = 0.0                  # for best_branch() aggregation
    outcome: str = ""                   # label for convergence_rate()
    key_vulnerability: str = ""         # the vuln that enabled the deepest progression
    duration_ticks: int = 0             # how many simulation ticks


@dataclass
class CitadelReport:
    """Aggregated report across all branched attack scenarios."""

    infra_name: str
    scenarios_run: int
    crown_jewel_breaches: int           # how many paths reached a crown jewel
    avg_depth: float                    # average attack depth
    avg_nodes_compromised: float
    most_vulnerable_nodes: list[tuple[str, int]]  # (node_name, times_compromised)
    best_attack_path: Optional[AttackPath]
    convergence_rate: float             # fraction agreeing on crown jewel breach/no-breach
    attack_paths: list[AttackPath] = field(default_factory=list)
    duration_ms: float = 0.0
    entry_points: list[str] = field(default_factory=list)


def simulate_attack(graph: InfraGraph, seed: Optional[int] = None) -> dict:
    """Simulate one attack path through the infrastructure.

    This is the per-branch function. ``generate_attack_scenarios()`` calls it
    N times with different seeds.
    """
    rng = random.Random(seed or 42)
    crown_jewels = set(graph.crown_jewels())

    # Attacker starts at a random external node
    external_nodes = [n for n in graph.nodes.values() if n.is_external]
    if not external_nodes:
        external_nodes = list(graph.nodes.values())
    entry = rng.choice(external_nodes)

    compromised: list[str] = [entry.name]
    current = entry.name
    max_ticks = 15
    key_vuln = ""

    for tick in range(max_ticks):
        neighbors = graph.neighbors(current)
        if not neighbors:
            break

        # Try to move to each neighbor — success depends on trust + vuln
        moved = False
        rng.shuffle(neighbors)
        for neighbor_name, trust in neighbors:
            if neighbor_name in compromised:
                continue
            node = graph.nodes.get(neighbor_name)
            if not node:
                continue

            # Exploitation success = function of trust, attack surface, and luck
            exploit_chance = (trust / 100) * (node.attack_surface / 100) * rng.uniform(0.5, 1.5)
            exploit_chance = min(exploit_chance, 0.95)

            if rng.random() < exploit_chance:
                compromised.append(neighbor_name)
                if node.vulnerabilities:
                    key_vuln = rng.choice(node.vulnerabilities).value
                current = neighbor_name
                moved = True
                break

        if not moved:
            break

        # Check if we reached a crown jewel
        if current in crown_jewels:
            break

    crown_reached = any(n in crown_jewels for n in compromised)
    score = len(compromised) * 10 + (100 if crown_reached else 0)

    return {
        "path": compromised,
        "crown_jewel_reached": crown_reached,
        "depth": len(compromised) - 1,
        "nodes_compromised": len(compromised),
        "entry_point": entry.name,
        "score": float(score),
        "outcome": "breach" if crown_reached else "contained",
        "key_vulnerability": key_vuln,
        "duration_ticks": tick + 1 if "tick" in dir() else 0,
    }


def generate_attack_scenarios(
    graph: Optional[InfraGraph] = None,
    n_scenarios: int = 5000,
    seed: Optional[int] = None,
) -> CitadelReport:
    """Generate N branched attack scenarios and aggregate the results."""
    t0 = time.perf_counter()
    if graph is None:
        graph = create_sample_infra()

    raw_branches = monte_carlo_branch(
        lambda s: simulate_attack(graph, s),
        n_scenarios,
        seed=seed,
    )

    paths = [AttackPath(
        path=b["path"],
        crown_jewel_reached=b["crown_jewel_reached"],
        depth=b["depth"],
        nodes_compromised=b["nodes_compromised"],
        entry_point=b["entry_point"],
        score=b["score"],
        outcome=b["outcome"],
        key_vulnerability=b["key_vulnerability"],
        duration_ticks=b["duration_ticks"],
    ) for b in raw_branches]

    breaches = sum(1 for p in paths if p.crown_jewel_reached)
    avg_depth = sum(p.depth for p in paths) / len(paths) if paths else 0
    avg_compromised = sum(p.nodes_compromised for p in paths) / len(paths) if paths else 0

    # Count which nodes were compromised most often
    node_compromise_count: dict[str, int] = {}
    for p in paths:
        for node_name in p.path:
            node_compromise_count[node_name] = node_compromise_count.get(node_name, 0) + 1
    most_vulnerable = sorted(node_compromise_count.items(), key=lambda x: x[1], reverse=True)[:10]

    convergence = convergence_rate(raw_branches, outcome_key="outcome")
    best_raw = best_branch(raw_branches, key="score")
    best = AttackPath(
        path=best_raw["path"], crown_jewel_reached=best_raw["crown_jewel_reached"],
        depth=best_raw["depth"], nodes_compromised=best_raw["nodes_compromised"],
        entry_point=best_raw["entry_point"], score=best_raw["score"],
        outcome=best_raw["outcome"], key_vulnerability=best_raw["key_vulnerability"],
        duration_ticks=best_raw["duration_ticks"],
    ) if best_raw else None

    entry_points = list(set(p.entry_point for p in paths))

    return CitadelReport(
        infra_name=graph.name,
        scenarios_run=len(paths),
        crown_jewel_breaches=breaches,
        avg_depth=round(avg_depth, 1),
        avg_nodes_compromised=round(avg_compromised, 1),
        most_vulnerable_nodes=most_vulnerable,
        best_attack_path=best,
        convergence_rate=round(convergence, 4),
        attack_paths=paths,
        duration_ms=round((time.perf_counter() - t0) * 1000, 1),
        entry_points=entry_points,
    )


def report_to_dict(report: CitadelReport) -> dict:
    """Serialize a CitadelReport to a JSON-friendly dict."""
    return {
        "infra_name": report.infra_name,
        "scenarios_run": report.scenarios_run,
        "crown_jewel_breaches": report.crown_jewel_breaches,
        "breach_rate": round(report.crown_jewel_breaches / report.scenarios_run, 4) if report.scenarios_run else 0,
        "avg_depth": report.avg_depth,
        "avg_nodes_compromised": report.avg_nodes_compromised,
        "most_vulnerable_nodes": [{"name": n, "times_compromised": c} for n, c in report.most_vulnerable_nodes],
        "best_attack_path": {
            "path": report.best_attack_path.path,
            "crown_jewel_reached": report.best_attack_path.crown_jewel_reached,
            "depth": report.best_attack_path.depth,
            "nodes_compromised": report.best_attack_path.nodes_compromised,
            "key_vulnerability": report.best_attack_path.key_vulnerability,
            "score": report.best_attack_path.score,
        } if report.best_attack_path else None,
        "convergence_rate": report.convergence_rate,
        "entry_points": report.entry_points,
        "duration_ms": report.duration_ms,
    }
