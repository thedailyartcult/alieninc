"""
Alpha Zero — Deterministic State-Branching & Parallel Universe Simulation Engine.

A standalone module that forks historical market data into N isolated parallel
timelines, injects macroeconomic micro-variables, and resolves them to an
optimized financial portfolio.

Phase 1: Core State classes + baseline data fetcher (yfinance).
"""

import asyncio
import dataclasses
import math
import random
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf


# ---------------------------------------------------------------------------
# Anchor State — the real-world historical "input" for every simulation
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class AnchorState:
    """A single observation of market reality used as the simulation root."""

    symbol: str
    timestamp: datetime
    price: float
    volume: float
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    macro_indicators: Dict[str, float] = dataclasses.field(default_factory=dict)
    metadata: Dict[str, Any] = dataclasses.field(default_factory=dict)

    def to_vector(self) -> np.ndarray:
        """Return a numeric feature vector for this anchor state."""
        return np.array([
            self.price,
            self.volume,
            self.open_price,
            self.high_price,
            self.low_price,
            self.close_price,
        ], dtype=np.float64)


@dataclasses.dataclass
class TimelineState:
    """The state of a single universe branch at a given simulation step."""

    symbol: str
    step_index: int
    timestamp: datetime
    price: float
    volume: float
    cumulative_return: float = 0.0
    cash_position: float = 0.0
    holdings: float = 0.0
    agent_action: str = "HOLD"
    drift_applied: float = 0.0
    volatility_applied: float = 0.0
    macro_shock: Dict[str, float] = dataclasses.field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "step_index": self.step_index,
            "timestamp": self.timestamp.isoformat(),
            "price": round(self.price, 6),
            "volume": round(self.volume, 2),
            "cumulative_return": round(self.cumulative_return, 6),
            "cash_position": round(self.cash_position, 2),
            "holdings": round(self.holdings, 6),
            "agent_action": self.agent_action,
            "drift_applied": round(self.drift_applied, 6),
            "volatility_applied": round(self.volatility_applied, 6),
            "macro_shock": {k: round(v, 6) for k, v in self.macro_shock.items()},
        }


# ---------------------------------------------------------------------------
# Baseline Data Fetcher
# ---------------------------------------------------------------------------

class BaselineFetcher:
    """Fetches historical anchor data via yfinance for use as simulation roots."""

    DEFAULT_PERIOD = "1y"
    DEFAULT_INTERVAL = "1d"

    @staticmethod
    def fetch(
        symbol: str,
        period: str = DEFAULT_PERIOD,
        interval: str = DEFAULT_INTERVAL,
    ) -> List[AnchorState]:
        """Download historical OHLCV + macro data for a ticker symbol."""
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period, interval=interval)

        if hist.empty:
            raise ValueError(f"No data returned for symbol '{symbol}'")

        anchors: List[AnchorState] = []
        for idx, row in hist.iterrows():
            anchors.append(
                AnchorState(
                    symbol=symbol,
                    timestamp=idx.to_pydatetime(),
                    price=float(row["Close"]),
                    volume=float(row["Volume"]),
                    open_price=float(row["Open"]),
                    high_price=float(row["High"]),
                    low_price=float(row["Low"]),
                    close_price=float(row["Close"]),
                    macro_indicators={},
                    metadata={"adj_close": float(row.get("Adj Close", row["Close"]))},
                )
            )

        return anchors

    @staticmethod
    def fetch_macro(
        symbol: str,
        period: str = DEFAULT_PERIOD,
        interval: str = DEFAULT_INTERVAL,
    ) -> List[AnchorState]:
        """Fetch with macro indicators (interest rate proxy, sentiment proxy)."""
        anchors = BaselineFetcher.fetch(symbol, period, interval)
        for i, anchor in enumerate(anchors):
            anchor.macro_indicators = {
                "interest_rate_proxy": 0.05 + 0.01 * math.sin(i * 0.1),
                "consumer_sentiment": 100.0 + 5.0 * math.cos(i * 0.05),
                "supply_chain_index": 1.0 + 0.02 * math.sin(i * 0.2),
            }
        return anchors


# ---------------------------------------------------------------------------
# Phase 1 entry point — fetch and return baseline
# ---------------------------------------------------------------------------

def get_baseline(
    symbol: str,
    period: str = BaselineFetcher.DEFAULT_PERIOD,
    interval: str = BaselineFetcher.DEFAULT_INTERVAL,
    include_macro: bool = False,
) -> List[AnchorState]:
    """Public helper: fetch baseline anchor data for a simulation run."""
    if include_macro:
        return BaselineFetcher.fetch_macro(symbol, period, interval)
    return BaselineFetcher.fetch(symbol, period, interval)


# ---------------------------------------------------------------------------
# Phase 2: Multi-Universe Forking Logic
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class MicroVariableVector:
    """A unique weighted random vector applied to one universe branch."""

    drift: float
    volatility: float
    interest_rate_shift: float
    sentiment_shift: float
    supply_chain_shift: float
    seed: int

    def to_dict(self) -> Dict[str, float]:
        return {
            "drift": round(self.drift, 8),
            "volatility": round(self.volatility, 8),
            "interest_rate_shift": round(self.interest_rate_shift, 8),
            "sentiment_shift": round(self.sentiment_shift, 8),
            "supply_chain_shift": round(self.supply_chain_shift, 8),
            "seed": self.seed,
        }


class MicroVariableGenerator:
    """Generates unique weighted random vectors for each universe branch."""

    DRIFT_RANGE = (-0.002, 0.002)
    VOLATILITY_RANGE = (0.01, 0.08)
    INTEREST_RATE_RANGE = (-0.005, 0.005)
    SENTIMENT_RANGE = (-10.0, 10.0)
    SUPPLY_CHAIN_RANGE = (-0.05, 0.05)

    @staticmethod
    def generate(branch_id: int, seed: Optional[int] = None) -> MicroVariableVector:
        rng = random.Random(seed or (branch_id * 1000 + 42))
        return MicroVariableVector(
            drift=rng.uniform(*MicroVariableGenerator.DRIFT_RANGE),
            volatility=rng.uniform(*MicroVariableGenerator.VOLATILITY_RANGE),
            interest_rate_shift=rng.uniform(*MicroVariableGenerator.INTEREST_RATE_RANGE),
            sentiment_shift=rng.uniform(*MicroVariableGenerator.SENTIMENT_RANGE),
            supply_chain_shift=rng.uniform(*MicroVariableGenerator.SUPPLY_CHAIN_RANGE),
            seed=seed or (branch_id * 1000 + 42),
        )

    @staticmethod
    def generate_batch(count: int) -> List[MicroVariableVector]:
        return [
            MicroVariableGenerator.generate(i) for i in range(count)
        ]


class UniverseBranch:
    """An isolated parallel timeline that evolves independently."""

    def __init__(
        self,
        branch_id: int,
        anchor: AnchorState,
        micro_vars: MicroVariableVector,
    ):
        self.branch_id = branch_id
        self.anchor = anchor
        self.micro_vars = micro_vars
        self.states: List[TimelineState] = []
        self._rng = random.Random(micro_vars.seed)

    def fork(self) -> TimelineState:
        """Create the initial forked state from the anchor."""
        initial = TimelineState(
            symbol=self.anchor.symbol,
            step_index=0,
            timestamp=self.anchor.timestamp,
            price=self.anchor.price,
            volume=self.anchor.volume,
            cumulative_return=0.0,
            cash_position=10000.0,
            holdings=0.0,
            agent_action="HOLD",
            drift_applied=0.0,
            volatility_applied=0.0,
            macro_shock={},
        )
        self.states.append(initial)
        return initial

    def advance_step(
        self,
        prev_state: TimelineState,
        anchor_price: float,
        macro_indicators: Dict[str, float],
    ) -> TimelineState:
        """Advance this branch one simulation step."""
        dt = 1.0 / 252.0

        drift = self.micro_vars.drift
        vol = self.micro_vars.volatility

        macro_drift = 0.0
        if macro_indicators:
            rate_shift = macro_indicators.get("interest_rate_proxy", 0.05)
            sentiment = macro_indicators.get("consumer_sentiment", 100.0)
            supply = macro_indicators.get("supply_chain_index", 1.0)
            macro_drift = (rate_shift - 0.05) * 0.3 + (sentiment - 100.0) * 0.001 + (supply - 1.0) * 0.02

        total_drift = drift + macro_drift
        shock = self._rng.gauss(0.0, 1.0)
        volatility_shock = vol * shock * math.sqrt(dt)

        new_price = prev_state.price * math.exp(total_drift + volatility_shock)
        new_volume = prev_state.volume * (1.0 + self._rng.gauss(0.0, 0.02))

        cumulative_return = (new_price / self.anchor.price) - 1.0

        macro_shock = {
            "interest_rate_shift": round(total_drift, 8),
            "sentiment_shift": round(macro_drift, 8),
            "supply_chain_shift": round(volatility_shock, 8),
        }

        new_state = TimelineState(
            symbol=self.anchor.symbol,
            step_index=prev_state.step_index + 1,
            timestamp=prev_state.timestamp + timedelta(days=1),
            price=new_price,
            volume=new_volume,
            cumulative_return=cumulative_return,
            cash_position=prev_state.cash_position,
            holdings=prev_state.holdings,
            agent_action="HOLD",
            drift_applied=round(total_drift, 8),
            volatility_applied=round(volatility_shock, 8),
            macro_shock=macro_shock,
        )
        self.states.append(new_state)
        return new_state


class ForkingEngine:
    """Duplicates baseline state into N isolated universe branches."""

    def __init__(
        self,
        anchors: List[AnchorState],
        num_branches: int = 100,
        steps_per_branch: int = 21,
    ):
        self.anchors = anchors
        self.num_branches = num_branches
        self.steps_per_branch = steps_per_branch
        self.branches: List[UniverseBranch] = []
        self.micro_vars: List[MicroVariableVector] = []

    def fork(self) -> None:
        """Duplicate the anchor states into N isolated branches."""
        self.micro_vars = MicroVariableGenerator.generate_batch(self.num_branches)
        self.branches = []
        for i, anchor in enumerate(self.anchors):
            for b in range(self.num_branches):
                branch = UniverseBranch(
                    branch_id=i * self.num_branches + b,
                    anchor=anchor,
                    micro_vars=self.micro_vars[b],
                )
                branch.fork()
                self.branches.append(branch)

    async def advance_all_async(self) -> None:
        """Advance all branches step-by-step asynchronously."""
        for step in range(1, self.steps_per_branch + 1):
            tasks = []
            for branch in self.branches:
                tasks.append(
                    asyncio.to_thread(
                        self._advance_branch, branch, step
                    )
                )
            await asyncio.gather(*tasks)

    def _advance_branch(self, branch: UniverseBranch, step: int) -> None:
        """Advance a single branch one step (thread-safe)."""
        prev_state = branch.states[-1]
        anchor_idx = min(step, len(self.anchors) - 1)
        anchor = self.anchors[anchor_idx]
        branch.advance_step(prev_state, anchor.price, anchor.macro_indicators)

    def get_all_timeline_data(self) -> List[Dict[str, Any]]:
        """Return all branch timeline data as serializable dicts."""
        results = []
        for branch in self.branches:
            for state in branch.states:
                d = state.to_dict()
                d["branch_id"] = branch.branch_id
                d["drift"] = branch.micro_vars.drift
                d["volatility"] = branch.micro_vars.volatility
                results.append(d)
        return results