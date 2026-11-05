"""The Scenario contract — the single object every station passes along the pipeline.

Flow:
    Platoon ──objective──▶ Alpha Zero ──world_states──▶ Daily Art Cult
                                │
                                ▼
                           Kriegspiel ──scenarios──┐
                         ┌──────┴──────┐           │
                         ▼             ▼           ▼
                    Remnants       CC           Awareness

A ``Scenario`` is created at Platoon (the objective) and accumulates state as it
flows through each station. Each station reads what it needs and writes its
output back into the same object (or a branch of it).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class Station(str, Enum):
    """The seven stations of the simulation stack."""

    PLATOON = "platoon"            # 1 — define the objective
    ALPHA_ZERO = "alpha_zero"      # 2 — branch across populations
    TDAC = "tdac"                  # 3 — publish / render narrative
    KRIEGSPIEL = "kriegspiel"      # 4 — generate combat scenarios
    REMNANTS = "remnants"          # 5 — filter for survivors
    CC = "cc"                    # 6 — mirror inward on infra
    AWARENESS = "awareness"        # 7 — incident response


@dataclass
class ScenarioResult:
    """What one station produced for one scenario."""

    station: Station
    universes: int = 0             # how many parallel branches were simulated
    convergence: Optional[float] = None   # fraction of branches agreeing on outcome
    outcome: Optional[str] = None         # winning/surviving outcome label
    metrics: dict[str, Any] = field(default_factory=dict)
    duration_ms: Optional[float] = None
    ts: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())


@dataclass
class Scenario:
    """The shared payload that flows through the pipeline.

    Created by Platoon with just ``objective``; each downstream station fills in
    its field and appends to ``results``.
    """

    objective: str                              # the single starting condition (from Platoon)
    station: Station = Station.PLATOON          # which station last touched this
    world_state: dict[str, Any] = field(default_factory=dict)   # Alpha Zero population state
    branches: list[dict[str, Any]] = field(default_factory=list)  # Kriegspiel scenario branches
    survivors: list[dict[str, Any]] = field(default_factory=list)  # Remnants: what outlasts conflict
    breaks: list[dict[str, Any]] = field(default_factory=list)     # CC: infra weak points
    narrative: Optional[str] = None             # Daily Art Cult: rendered editorial/audio script
    response_playbooks: list[dict[str, Any]] = field(default_factory=list)  # Awareness: IR playbooks
    results: list[ScenarioResult] = field(default_factory=list)
    seed: Optional[int] = None
    created_at: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())

    def advance_to(self, station: Station) -> None:
        """Mark that this scenario has been processed by ``station``."""
        self.station = station

    def add_result(self, result: ScenarioResult) -> None:
        self.results.append(result)
