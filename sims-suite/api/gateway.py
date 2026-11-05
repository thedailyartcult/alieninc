"""Sims-suite gateway — the single API that feeds alieninc.tech/index.html.

Aggregates live simulation metrics from all 7 engines and exposes them under
``/api/simulations/*`` (proxied same-origin via nginx). In Phase 0, only the
Alpha Zero engine is online; the gateway runs a light background loop of *real*
Alpha Zero simulations so the numbers on index.html are genuine, not faked.

index.html integration (line ~3699):
    window.ALIEN_SIMS = { getValue: () => <polled count> };

Endpoints:
    GET /api/simulations/today      — { count, runs, last_24h, by_engine,
                                       cumulative, by_engine_cumulative,
                                       window_seconds, as_of }
                                      count/last_24h/by_engine are a true
                                      rolling 24h UTC window; cumulative fields
                                      are the all-time totals.
    GET /api/simulations/coverage   — { stage, engines_online, total_engines }
    GET /api/simulations/engine     — { code, engines, engines_detail }
    GET /api/companies/{name}       — { name, station, simulations }
    GET /api/health                 — { status, uptime, engines }

Run:
    cd /home/alieninc/sims-suite && python -m api.gateway
    # or: uvicorn api.gateway:app --host 127.0.0.1 --port 8090
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Optional

# --- make sibling packages importable ---
_SUITE_ROOT = Path(__file__).resolve().parents[1]
if str(_SUITE_ROOT) not in sys.path:
    sys.path.insert(0, str(_SUITE_ROOT))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

logger = logging.getLogger("sims-suite.gateway")

# ---------------------------------------------------------------------------
# Engine registry — which stations are online
# ---------------------------------------------------------------------------

AZ_ENGINE_PATH = Path(
    os.environ.get("ALIEN_AZ_ENGINE_PATH", "/home/alieninc/alphazero/alpha-zero-engine")
)

# Map company name -> station
COMPANY_STATIONS: dict[str, str] = {
    "platoon": "platoon",
    "alphazero": "alpha_zero",
    "tdac": "tdac",
    "kriegspiel": "kriegspiel",
    "remnants": "remnants",
    "cc": "cc",
    "awareness": "awareness",
}

TOTAL_ENGINES = 7

# Friendly display names for the engine dropdown on index.html.
ENGINE_DISPLAY_NAMES: dict[str, str] = {
    "platoon": "Platoon",
    "alpha_zero": "Alpha Zero",
    "tdac": "TDAC",
    "kriegspiel": "Kriegspiel",
    "cc": "Collective Consciousness",
    "remnants": "Remnants",
    "awareness": "Awareness",
}

# ---------------------------------------------------------------------------
# Persistent cumulative counter — survives restarts, never trims
# ---------------------------------------------------------------------------

_COUNT_FILE = _SUITE_ROOT / "api" / ".sim_count.json"


def _read_count() -> dict[str, int]:
    """Read the persistent cumulative counter."""
    try:
        import json
        if _COUNT_FILE.exists():
            counts = json.loads(_COUNT_FILE.read_text())
            if "citadel" in counts:
                counts["cc"] = counts.get("cc", 0) + counts.pop("citadel")
            return counts
    except Exception:
        pass
    return {"alpha_zero": 0, "kriegspiel": 0}


def _write_count(counts: dict[str, int]) -> None:
    """Write the persistent cumulative counter atomically."""
    try:
        tmp = _COUNT_FILE.parent / (_COUNT_FILE.name + ".tmp")
        tmp.write_text(json.dumps(counts))
        tmp.replace(_COUNT_FILE)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Rolling 24h (UTC) event log — timestamps every real increment so the
# /api/simulations/today endpoint can report a true last-24-hours window
# instead of the all-time cumulative total. Unix timestamps are inherently
# UTC, so the window is Universal Standard Time by construction.
# ---------------------------------------------------------------------------

_EVENT_FILE = _SUITE_ROOT / "api" / ".sim_events.jsonl"
_WINDOW_S = 86400  # 24 hours

# In-memory ring of (ts, engine, n) for the current window; fast reads.
_events_24h: "deque[tuple[float, str, int]]" = deque()


def _load_events_24h() -> None:
    """Load timestamped events from the last 24h into memory on startup, then
    compact the on-disk log so it never grows unbounded across restarts."""
    global _events_24h
    cutoff = time.time() - _WINDOW_S
    loaded: "deque[tuple[float, str, int]]" = deque()
    try:
        if _EVENT_FILE.exists():
            with _EVENT_FILE.open("r") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue
                    try:
                        ts = float(rec.get("ts", 0))
                        engine = str(rec.get("engine", ""))
                        n = int(rec.get("n", 0))
                    except Exception:
                        continue
                    if ts >= cutoff and engine and n:
                        loaded.append((ts, engine, n))
    except Exception:
        pass
    _events_24h = loaded
    _rewrite_events()


def _append_event(ts: float, engine: str, n: int) -> None:
    """Append a single timestamped event to the on-disk JSONL log."""
    try:
        with _EVENT_FILE.open("a") as fh:
            fh.write(json.dumps({"ts": ts, "engine": engine, "n": n}) + "\n")
    except Exception:
        pass


def _rewrite_events() -> None:
    """Atomically rewrite the on-disk log from the in-memory deque (trimmed)."""
    try:
        tmp = _EVENT_FILE.with_suffix(".jsonl.tmp")
        with tmp.open("w") as fh:
            for ts, engine, n in _events_24h:
                fh.write(json.dumps({"ts": ts, "engine": engine, "n": n}) + "\n")
        tmp.replace(_EVENT_FILE)
    except Exception:
        pass


def _evict_old_events() -> None:
    """Drop events that have aged out of the 24h window. Caller holds the lock."""
    cutoff = time.time() - _WINDOW_S
    while _events_24h and _events_24h[0][0] < cutoff:
        _events_24h.popleft()


def _sum_24h() -> tuple[int, dict[str, int]]:
    """Return (total, by_engine) for the rolling 24h UTC window."""
    with _count_lock:
        _evict_old_events()
        by_engine: dict[str, int] = {}
        total = 0
        for _ts, engine, n in _events_24h:
            by_engine[engine] = by_engine.get(engine, 0) + n
            total += n
    return total, by_engine


async def _event_trim_loop() -> None:
    """Periodically evict aged events and compact the on-disk log."""
    while True:
        await asyncio.sleep(600)
        try:
            with _count_lock:
                _evict_old_events()
                _rewrite_events()
        except asyncio.CancelledError:
            raise
        except Exception:
            pass


def _add_count(engine: str, n: int) -> None:
    """Add n to the persistent cumulative counter for the given engine and
    record a timestamped event so a true rolling 24h (UTC) window is available."""
    now = time.time()
    with _count_lock:
        _counts[engine] = _counts.get(engine, 0) + n
        _write_count(_counts)
        _events_24h.append((now, engine, n))
        _evict_old_events()
    _append_event(now, engine, n)


_count_lock = threading.Lock()
_counts = _read_count()

# ---------------------------------------------------------------------------
# Alpha Zero engine — imported lazily (degrade gracefully if unavailable)
# ---------------------------------------------------------------------------

_az_available = False
_az_analytics: Any = None
_az_sim_orchestrator: Any = None
_az_sim_config: Any = None
_az_gender: Any = None


def _load_alpha_zero() -> bool:
    """Try to import the Alpha Zero engine. Return True if available."""
    global _az_available, _az_analytics, _az_sim_orchestrator, _az_sim_config, _az_gender
    if _az_available:
        return True
    if not AZ_ENGINE_PATH.exists():
        logger.warning("Alpha Zero engine not found at %s", AZ_ENGINE_PATH)
        return False
    engine_src = str(AZ_ENGINE_PATH)
    if engine_src not in sys.path:
        sys.path.insert(0, engine_src)
    try:
        from infra import analytics as _az_analytics_mod  # noqa: F401
        from engine.simulation import SimulationOrchestrator, SimulationConfig
        from engine.character import Gender

        _az_analytics = _az_analytics_mod
        _az_sim_orchestrator = SimulationOrchestrator
        _az_sim_config = SimulationConfig
        _az_gender = Gender
        _az_available = True
        logger.info("Alpha Zero engine loaded from %s", engine_src)
        return True
    except Exception as exc:
        logger.warning("Could not load Alpha Zero engine: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Background simulation loop — runs REAL Alpha Zero simulations
# ---------------------------------------------------------------------------

AZ_BATCH_SIZE = int(os.environ.get("ALIEN_AZ_BATCH", "100"))
AZ_INTERVAL_S = float(os.environ.get("ALIEN_AZ_INTERVAL", "3"))
SIM_INTERVAL_S = float(os.environ.get("ALIEN_SIM_INTERVAL", "8"))
SIM_ENABLED = os.environ.get("ALIEN_SIM_DISABLE", "0") != "1"


def _run_sim_batch() -> int:
    """Run a batch of real Alpha Zero simulations. Return count of simulated decisions.

    Each universe simulates ~41 years of life with ~123 decision events (career,
    health, relationship, financial events). We count the ACTUAL events from each
    simulation — so "simulated decisions" = total decision events across all
    universes, not just universe count.
    """
    if not _az_available:
        return 0
    try:
        config = _az_sim_config(
            name="Population",
            age=20,
            gender=_az_gender("male"),
            birthplace="Manila",
            current_city="Manila",
            happiness=50,
            health=70,
            smarts=50,
            looks=50,
            karma=50,
            starting_money=0,
            initial_portfolio=100000,
            seed=42,
            portfolio_strategy="balanced",
        )
        t0 = time.perf_counter()
        total_decisions = 0
        for _ in range(AZ_BATCH_SIZE):
            orchestrator = _az_sim_orchestrator(config)
            steps = orchestrator.run_single()
            total_decisions += sum(len(step.events) for step in steps)
        duration_ms = (time.perf_counter() - t0) * 1000
        if _az_analytics:
            _az_analytics.record_simulation(
                "batch",
                {"name": "Population", "age": 20, "strategy": "balanced",
                 "years": 80, "universes": AZ_BATCH_SIZE,
                 "decisions": total_decisions},
                duration_ms=round(duration_ms, 2),
            )
        _add_count("alpha_zero", total_decisions)
        return total_decisions
    except Exception as exc:
        logger.debug("Background sim batch failed: %s", exc)
        return 0


async def _background_sim_loop() -> None:
    """High-volume loop: run a batch of simulations every few seconds."""
    if not SIM_ENABLED:
        logger.info("Background simulation loop disabled (ALIEN_SIM_DISABLE=1)")
        return
    logger.info("Background AZ sim loop started (batch=%d, interval=%.1fs)", AZ_BATCH_SIZE, AZ_INTERVAL_S)
    while True:
        try:
            await asyncio.to_thread(_run_sim_batch)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        await asyncio.sleep(AZ_INTERVAL_S)


# ---------------------------------------------------------------------------
# Kriegspiel engine — imported lazily
# ---------------------------------------------------------------------------

_ks_available = False
_ks_generate: Any = None
_ks_report_to_dict: Any = None
_ks_battlefields: Any = None
_ks_create_battle: Any = None
_ks_battlefields_llm: Any = None
_ks_register_llm_battlefield: Any = None
_ks_llm_available = False
_ks_synthesize_battle_seed: Any = None
_ks_synthesize_events: Any = None
_ks_get_llm_client: Any = None

_ks_sim_count = 0  # in-memory (also persisted via _add_count)
_ks_last_report: dict[str, Any] = {}


def _load_kriegspiel() -> bool:
    """Try to import the Kriegspiel engine. Return True if available."""
    global _ks_available, _ks_generate, _ks_report_to_dict, _ks_battlefields, _ks_create_battle
    global _ks_llm_available, _ks_synthesize_battle_seed, _ks_synthesize_events, _ks_get_llm_client
    global _ks_register_llm_battlefield, _ks_battlefields_llm
    if _ks_available:
        return True
    # Re-prioritize sims-suite root on sys.path.
    if str(_SUITE_ROOT) not in sys.path:
        sys.path.insert(0, str(_SUITE_ROOT))
    else:
        sys.path.remove(str(_SUITE_ROOT))
        sys.path.insert(0, str(_SUITE_ROOT))
    try:
        from engines.kriegspiel.scenarios import (
            generate_scenarios as _gs,
            report_to_dict as _rtd,
            create_default_battle as _cdb,
        )
        from engines.kriegspiel.models import (
            BATTLEFIELDS as _bf,
            BATTLEFIELDS_LLM as _bf_llm,
            register_llm_battlefield as _rlb,
        )

        _ks_generate = _gs
        _ks_report_to_dict = _rtd
        _ks_battlefields = _bf
        _ks_battlefields_llm = _bf_llm
        _ks_register_llm_battlefield = _rlb
        _ks_create_battle = _cdb

        # LLM synthesis layer — optional. If imports fail (e.g. missing env
        # config or a Python version issue) we just leave the LLM flag off
        # and the procedural engine answers every call.
        try:
            from engines.kriegspiel.llm import (
                synthesize_battle_seed as _sbs,
                synthesize_events as _sev,
                get_llm_client as _glc,
            )
            _ks_synthesize_battle_seed = _sbs
            _ks_synthesize_events = _sev
            _ks_get_llm_client = _glc
            _ks_llm_available = True
            logger.info("Kriegspiel LLM synthesis layer loaded")
        except Exception as llm_exc:
            logger.warning("Kriegspiel LLM layer not available: %s", llm_exc)
            _ks_llm_available = False
        _ks_available = True
        logger.info("Kriegspiel engine loaded")
        return True
    except Exception as exc:
        logger.warning("Could not load Kriegspiel engine: %s", exc)
        return False


def _ks_learn(report: Any) -> None:
    """Feed a ScenarioReport to the self-learning tracker. Swallows errors
    so on-demand runs never block on the research layer."""
    try:
        from engines.kriegspiel.learning import get_tracker
        get_tracker().observe(report)
    except Exception as learn_exc:
        logger.debug("Learning layer observe failed: %s", learn_exc)


def _run_ks_background_batch() -> int:
    """Run a small batch of Kriegspiel scenarios for the live counter.

    The report is fed to the self-learning tracker so the engine distills
    findings and self-improves its doctrine parameters over time. Learning
    failures are swallowed — the live counter must never block on research.
    """
    global _ks_sim_count
    if not _ks_available:
        return 0
    try:
        report = _ks_generate(n_scenarios=100, seed=None)
        _ks_sim_count += report.scenarios_run
        _add_count("kriegspiel", report.scenarios_run)
        _ks_last_report = _ks_report_to_dict(report)
        _ks_learn(report)
        return report.scenarios_run
    except Exception as exc:
        logger.debug("Kriegspiel background batch failed: %s", exc)
        return 0


async def _background_ks_loop() -> None:
    """Light loop: run a small batch of Kriegspiel scenarios periodically."""
    if not SIM_ENABLED:
        return
    ks_interval = SIM_INTERVAL_S * 3
    logger.info("Kriegspiel background loop started (interval=%.1fs)", ks_interval)
    while True:
        try:
            await asyncio.to_thread(_run_ks_background_batch)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        await asyncio.sleep(ks_interval)


# ---------------------------------------------------------------------------
# CC engine — imported lazily (Kriegspiel turned inward on infra)
# ---------------------------------------------------------------------------

_cc_available = False
_cc_generate: Any = None
_cc_report_to_dict: Any = None
_cc_create_infra: Any = None


def _load_cc() -> bool:
    global _cc_available, _cc_generate, _cc_report_to_dict, _cc_create_infra
    if _cc_available:
        return True
    if str(_SUITE_ROOT) not in sys.path:
        sys.path.insert(0, str(_SUITE_ROOT))
    try:
        from engines.cc.attack import (
            generate_attack_scenarios as _gas,
            report_to_dict as _rtd,
        )
        from engines.cc.infra_graph import create_sample_infra as _csi

        _cc_generate = _gas
        _cc_report_to_dict = _rtd
        _cc_create_infra = _csi
        _cc_available = True
        logger.info("CC engine loaded")
        return True
    except Exception as exc:
        logger.warning("Could not load CC engine: %s", exc)
        return False


def _run_cc_background_batch() -> int:
    if not _cc_available:
        return 0
    try:
        report = _cc_generate(n_scenarios=100, seed=None)
        _add_count("cc", report.scenarios_run)
        return report.scenarios_run
    except Exception:
        return 0


async def _background_cc_loop() -> None:
    if not SIM_ENABLED:
        return
    interval = SIM_INTERVAL_S * 4
    logger.info("CC background loop started (interval=%.1fs)", interval)
    while True:
        try:
            await asyncio.to_thread(_run_cc_background_batch)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        await asyncio.sleep(interval)


# ---------------------------------------------------------------------------
# Remnants engine — imported lazily (what survives)
# ---------------------------------------------------------------------------

_rem_available = False
_rem_generate: Any = None
_rem_report_to_dict: Any = None
_rem_survivors: Any = None
_rem_conflict: Any = None


def _load_remnants() -> bool:
    global _rem_available, _rem_generate, _rem_report_to_dict, _rem_survivors, _rem_conflict
    if _rem_available:
        return True
    if str(_SUITE_ROOT) not in sys.path:
        sys.path.insert(0, str(_SUITE_ROOT))
    try:
        from engines.remnants.continuity import (
            generate_continuity_scenarios as _gcs,
            report_to_dict as _rtd,
            SAMPLE_SURVIVORS as _ss,
            ConflictCondition as _cc,
        )

        _rem_generate = _gcs
        _rem_report_to_dict = _rtd
        _rem_survivors = _ss
        _rem_conflict = _cc
        _rem_available = True
        logger.info("Remnants engine loaded")
        return True
    except Exception as exc:
        logger.warning("Could not load Remnants engine: %s", exc)
        return False


def _run_rem_background_batch() -> int:
    if not _rem_available:
        return 0
    try:
        report = _rem_generate(n_scenarios=100, seed=None)
        _add_count("remnants", report.scenarios_run)
        return report.scenarios_run
    except Exception:
        return 0


async def _background_rem_loop() -> None:
    if not SIM_ENABLED:
        return
    interval = SIM_INTERVAL_S * 4
    logger.info("Remnants background loop started (interval=%.1fs)", interval)
    while True:
        try:
            await asyncio.to_thread(_run_rem_background_batch)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        await asyncio.sleep(interval)


# ---------------------------------------------------------------------------
# Awareness engine — imported lazily (SOAR/IR layer)
# ---------------------------------------------------------------------------

_aw_available = False
_aw_generate: Any = None
_aw_report_to_dict: Any = None
_aw_threats: Any = None
_aw_playbooks: Any = None


def _load_awareness() -> bool:
    global _aw_available, _aw_generate, _aw_report_to_dict, _aw_threats, _aw_playbooks
    if _aw_available:
        return True
    if str(_SUITE_ROOT) not in sys.path:
        sys.path.insert(0, str(_SUITE_ROOT))
    try:
        from engines.awareness.response import (
            generate_response_scenarios as _grs,
            report_to_dict as _rtd,
        )
        from engines.awareness.models import SAMPLE_THREATS as _st, SAMPLE_PLAYBOOKS as _sp

        _aw_generate = _grs
        _aw_report_to_dict = _rtd
        _aw_threats = _st
        _aw_playbooks = _sp
        _aw_available = True
        logger.info("Awareness engine loaded")
        return True
    except Exception as exc:
        logger.warning("Could not load Awareness engine: %s", exc)
        return False


def _run_aw_background_batch() -> int:
    if not _aw_available:
        return 0
    try:
        import random
        threat = random.choice(_aw_threats)
        report = _aw_generate(threat=threat, n_scenarios=100, seed=None)
        _add_count("awareness", report.scenarios_run)
        return report.scenarios_run
    except Exception:
        return 0


async def _background_aw_loop() -> None:
    if not SIM_ENABLED:
        return
    interval = SIM_INTERVAL_S * 4
    logger.info("Awareness background loop started (interval=%.1fs)", interval)
    while True:
        try:
            await asyncio.to_thread(_run_aw_background_batch)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        await asyncio.sleep(interval)


# ---------------------------------------------------------------------------
# Platoon engine — imported lazily (objective capture)
# ---------------------------------------------------------------------------

_pl_available = False
_pl_generate: Any = None
_pl_objectives: Any = None


def _load_platoon() -> bool:
    global _pl_available, _pl_generate, _pl_objectives
    if _pl_available:
        return True
    if str(_SUITE_ROOT) not in sys.path:
        sys.path.insert(0, str(_SUITE_ROOT))
    try:
        from engines.platoon.objective import (
            generate_objective_scenarios as _gos,
            SAMPLE_OBJECTIVES as _so,
        )
        _pl_generate = _gos
        _pl_objectives = _so
        _pl_available = True
        logger.info("Platoon engine loaded")
        return True
    except Exception as exc:
        logger.warning("Could not load Platoon engine: %s", exc)
        return False


def _run_pl_background_batch() -> int:
    if not _pl_available:
        return 0
    try:
        import random
        obj = random.choice(_pl_objectives)
        d = _pl_generate(objective=obj, n_scenarios=100, seed=None)
        _add_count("platoon", d["scenarios_run"])
        return d["scenarios_run"]
    except Exception:
        return 0


async def _background_pl_loop() -> None:
    if not SIM_ENABLED:
        return
    interval = SIM_INTERVAL_S * 4
    logger.info("Platoon background loop started (interval=%.1fs)", interval)
    while True:
        try:
            await asyncio.to_thread(_run_pl_background_batch)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        await asyncio.sleep(interval)


# ---------------------------------------------------------------------------
# TDAC engine — imported lazily (narrative bridge)
# ---------------------------------------------------------------------------

_td_available = False
_td_generate: Any = None
_td_sources: Any = None


def _load_tdac() -> bool:
    global _td_available, _td_generate, _td_sources
    if _td_available:
        return True
    if str(_SUITE_ROOT) not in sys.path:
        sys.path.insert(0, str(_SUITE_ROOT))
    try:
        from engines.tdac.narrative import (
            generate_narrative_scenarios as _gns,
            SAMPLE_SOURCES as _ss,
        )
        _td_generate = _gns
        _td_sources = _ss
        _td_available = True
        logger.info("TDAC engine loaded")
        return True
    except Exception as exc:
        logger.warning("Could not load TDAC engine: %s", exc)
        return False


def _run_td_background_batch() -> int:
    if not _td_available:
        return 0
    try:
        import random
        src = random.choice(_td_sources)
        d = _td_generate(source=src, n_scenarios=100, seed=None)
        _add_count("tdac", d["scenarios_run"])
        return d["scenarios_run"]
    except Exception:
        return 0


async def _background_td_loop() -> None:
    if not SIM_ENABLED:
        return
    interval = SIM_INTERVAL_S * 4
    logger.info("TDAC background loop started (interval=%.1fs)", interval)
    while True:
        try:
            await asyncio.to_thread(_run_td_background_batch)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        await asyncio.sleep(interval)


# ---------------------------------------------------------------------------
# Metrics aggregation
# ---------------------------------------------------------------------------

_started_at = time.time()


def _az_simulation_summary() -> dict[str, Any]:
    """Read Alpha Zero's on-disk analytics for real run counts."""
    if not _az_available or _az_analytics is None:
        return {"total_runs": 0, "total_universes": _az_sim_count, "runs_last_24h": 0}
    try:
        return _az_analytics.simulation_summary()
    except Exception:
        return {"total_runs": 0, "total_universes": _az_sim_count, "runs_last_24h": 0}


def _engines_online() -> list[str]:
    online = []
    if _pl_available:
        online.append("platoon")
    if _az_available:
        online.append("alpha_zero")
    if _td_available:
        online.append("tdac")
    if _ks_available:
        online.append("kriegspiel")
    if _cc_available:
        online.append("cc")
    if _rem_available:
        online.append("remnants")
    if _aw_available:
        online.append("awareness")
    return online


def _coverage_stage(online: int) -> str:
    if online <= 1:
        return "Early-stage"
    if online <= 3:
        return "Population-scale"
    if online <= 5:
        return "Multi-domain"
    return "Full-spectrum"


def _engine_code(online: list[str]) -> str:
    if not online:
        return "—"
    if len(online) == 1:
        return "A-Z"
    return "A-Z+" + "".join(s[0].upper() for s in online[1:])


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="Alien Inc Sims Suite", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class SimTodayResponse(BaseModel):
    count: int
    runs: int
    last_24h: int
    by_engine: dict[str, int]
    cumulative: int
    by_engine_cumulative: dict[str, int]
    window_seconds: int
    as_of: float
    # Counting unit, made explicit after the pentest flagged the number as
    # misleading: alpha_zero's background loop reports DECISION EVENTS
    # (~246 per universe-life), not universe runs. 743M/day is real
    # event throughput — but consumers must know it is not "simulations".
    unit: str = "mixed (alpha_zero counts decision events; other engines count scenario runs)"


class CoverageResponse(BaseModel):
    stage: str
    engines_online: int
    total_engines: int


class EngineResponse(BaseModel):
    code: str
    engines: list[str]
    engines_detail: list[dict[str, str]]


class CompanyResponse(BaseModel):
    name: str
    station: str
    simulations: int


class HealthResponse(BaseModel):
    status: str
    uptime: float
    engines: list[str]


@app.on_event("startup")
async def _startup() -> None:
    _load_events_24h()
    _load_alpha_zero()
    _load_kriegspiel()
    _load_cc()
    _load_remnants()
    _load_awareness()
    _load_platoon()
    _load_tdac()
    asyncio.create_task(_background_sim_loop())
    asyncio.create_task(_background_ks_loop())
    asyncio.create_task(_background_cc_loop())
    asyncio.create_task(_background_rem_loop())
    asyncio.create_task(_background_aw_loop())
    asyncio.create_task(_background_pl_loop())
    asyncio.create_task(_background_td_loop())
    asyncio.create_task(_event_trim_loop())


@app.get("/api/health")
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        uptime=round(time.time() - _started_at, 1),
        engines=_engines_online(),
    )


@app.get("/api/simulations/today")
async def simulations_today() -> SimTodayResponse:
    # Rolling 24h UTC window — the genuine count of decisions produced in the
    # last 24 hours. This is what index.html surfaces as the live tally.
    total_24h, by_engine_24h = _sum_24h()
    # Cumulative (all-time) totals are preserved for transparency.
    by_engine_cum: dict[str, int] = {}
    if _pl_available:
        by_engine_cum["platoon"] = _counts.get("platoon", 0)
    if _az_available:
        by_engine_cum["alpha_zero"] = _counts.get("alpha_zero", 0)
    if _td_available:
        by_engine_cum["tdac"] = _counts.get("tdac", 0)
    if _ks_available:
        by_engine_cum["kriegspiel"] = _counts.get("kriegspiel", 0)
    if _cc_available:
        by_engine_cum["cc"] = _counts.get("cc", 0)
    if _rem_available:
        by_engine_cum["remnants"] = _counts.get("remnants", 0)
    if _aw_available:
        by_engine_cum["awareness"] = _counts.get("awareness", 0)
    cumulative = sum(by_engine_cum.values())
    return SimTodayResponse(
        count=total_24h,
        runs=total_24h,
        last_24h=total_24h,
        by_engine=by_engine_24h,
        cumulative=cumulative,
        by_engine_cumulative=by_engine_cum,
        window_seconds=_WINDOW_S,
        as_of=time.time(),
        unit="mixed (alpha_zero counts decision events; other engines count scenario runs)",
    )


@app.get("/api/simulations/coverage")
async def simulations_coverage() -> CoverageResponse:
    online = _engines_online()
    return CoverageResponse(
        stage=_coverage_stage(len(online)),
        engines_online=len(online),
        total_engines=TOTAL_ENGINES,
    )


@app.get("/api/simulations/engine")
async def simulations_engine() -> EngineResponse:
    online = _engines_online()
    detail = [{"id": s, "name": ENGINE_DISPLAY_NAMES.get(s, s)} for s in online]
    return EngineResponse(code=_engine_code(online), engines=online, engines_detail=detail)


@app.get("/api/companies/{name}")
async def company_metrics(name: str) -> CompanyResponse:
    station = COMPANY_STATIONS.get(name.lower(), "unknown")
    simulations = _counts.get(station, 0) if station in (
        "platoon", "alpha_zero", "tdac", "kriegspiel", "cc", "remnants", "awareness"
    ) else 0
    return CompanyResponse(name=name, station=station, simulations=simulations)


# ---------------------------------------------------------------------------
# Kriegspiel endpoints
# ---------------------------------------------------------------------------

@app.get("/api/kriegspiel/battlefields")
async def ks_battlefields() -> list[dict[str, Any]]:
    if not _ks_available or not _ks_battlefields:
        return []
    out: list[dict[str, Any]] = [
        {
            "name": bf.name,
            "terrain": bf.terrain.value,
            "center": list(bf.center),
            "bounds": list(bf.bounds),
            "area_km2": bf.area_km2,
            "source": "canonical",
        }
        for bf in _ks_battlefields
    ]
    # Append LLM-synthesized battlefields if any have been registered.
    if _ks_battlefields_llm:
        for bf in _ks_battlefields_llm:
            out.append({
                "name": bf.name,
                "terrain": bf.terrain.value,
                "center": list(bf.center),
                "bounds": list(bf.bounds),
                "area_km2": bf.area_km2,
                "source": "llm",
            })
    return out


@app.post("/api/kriegspiel/run")
async def ks_run(body: dict[str, Any]) -> dict[str, Any]:
    if not _ks_available:
        return {"error": "Kriegspiel engine not available"}

    bf_name = body.get("battlefield", "random")
    n_scenarios = min(int(body.get("scenarios", 1000)), 50000)
    seed = body.get("seed", 42)

    battle = None
    if bf_name != "random" and _ks_battlefields:
        for bf in _ks_battlefields:
            if bf.name == bf_name:
                battle = _ks_create_battle(battlefield=bf, seed=seed)
                break

    def _run() -> dict[str, Any]:
        report = _ks_generate(battle=battle, n_scenarios=n_scenarios, seed=seed)
        d = _ks_report_to_dict(report)
        if battle:
            d["_battlefield"] = {
                "name": battle.battlefield.name,
                "terrain": battle.battlefield.terrain.value,
                "bounds": list(battle.battlefield.bounds),
            }
        global _ks_sim_count
        _ks_sim_count += report.scenarios_run
        _add_count("kriegspiel", report.scenarios_run)
        _ks_learn(report)
        return d

    result = await asyncio.to_thread(_run)
    return result


@app.post("/api/kriegspiel/campaign/simulate")
async def ks_campaign_simulate(body: dict[str, Any]) -> dict[str, Any]:
    """Run multi-engagement campaign simulations (operational level).

    Body: { battlefield?, red_doctrine?, blue_doctrine?, campaigns?,
            engagements?, engagement_hours?, red_reinforcement?,
            blue_reinforcement?, seed? }
    Returns aggregated campaign outcomes: win shares, front movement,
    remaining-force percentages, collapse counts.
    """
    if not _ks_available:
        return {"error": "Kriegspiel engine not available"}

    from engines.kriegspiel.campaign import run_campaign
    from engines.kriegspiel.models import BATTLEFIELDS, Doctrine

    bf_name = body.get("battlefield", "random")
    n_campaigns = max(1, min(int(body.get("campaigns", 50)), 500))
    n_engagements = max(1, min(int(body.get("engagements", 8)), 20))
    eng_hours = max(6, min(int(body.get("engagement_hours", 24)), 120))
    r_r = float(body.get("red_reinforcement", 0.30))
    b_r = float(body.get("blue_reinforcement", 0.30))
    seed = body.get("seed", None)
    try:
        red_doc = Doctrine(body.get("red_doctrine", "maneuver"))
    except ValueError:
        red_doc = Doctrine.MANEUVER
    try:
        blue_doc = Doctrine(body.get("blue_doctrine", "defensive"))
    except ValueError:
        blue_doc = Doctrine.DEFENSIVE

    bf = None
    if bf_name != "random":
        for cand in BATTLEFIELDS:
            if cand.name == bf_name:
                bf = cand
                break

    def _run() -> dict[str, Any]:
        import statistics
        from engines.kriegspiel.learning import get_campaign_tracker
        tracker = get_campaign_tracker()
        reports = [
            run_campaign(red_doctrine=red_doc, blue_doctrine=blue_doc,
                         battlefield=bf, n_engagements=n_engagements,
                         engagement_duration_hours=eng_hours,
                         red_reinforcement=r_r, blue_reinforcement=b_r,
                         seed=None if seed is None else int(seed) + i)
            for i in range(n_campaigns)
        ]
        dicts = [r.to_dict() for r in reports]
        wins = {"red": 0, "blue": 0, "stalemate": 0}
        for r in reports:
            wins[r.campaign_winner] += 1
            tracker.observe_report(r, r_r, b_r)
        global _ks_sim_count
        _ks_sim_count += sum(d["engagements_fought"] for d in dicts)
        _add_count("kriegspiel", sum(d["engagements_fought"] for d in dicts))
        return {
            "campaigns": n_campaigns,
            "matchup": f"{red_doc.value} vs {blue_doc.value}",
            "reinforcement": {"red": r_r, "blue": b_r},
            "campaign_wins": wins,
            "avg_engagements": round(statistics.mean(
                d["engagements_fought"] for d in dicts), 2),
            "avg_front_final_pct": round(statistics.mean(
                d["front_final_pct"] for d in dicts), 1),
            "avg_red_remaining_pct": round(statistics.mean(
                d["red_remaining_pct"] for d in dicts), 1),
            "avg_blue_remaining_pct": round(statistics.mean(
                d["blue_remaining_pct"] for d in dicts), 1),
            "collapses": {
                "red": sum(1 for d in dicts if d["collapsed"] == "red"),
                "blue": sum(1 for d in dicts if d["collapsed"] == "blue"),
            },
            "sample_campaign": dicts[0],
        }

    return await asyncio.to_thread(_run)


def _expand_timeline(report: dict[str, Any], eng_hours: float) -> dict[str, Any]:
    """Expand one campaign report into an engagement-by-engagement state
    timeline for playback: cumulative clock, front position and remaining
    force percentages, normalized to land exactly on the engine's finals."""
    engs = report.get("engagements") or []
    n = max(len(engs), 1)
    # Raw front deltas weighted by decisiveness, then rescaled so the series
    # terminates on the engine's actual front_final_pct.
    deltas = []
    for e in engs:
        w = e.get("winner")
        d = 2.0 if e.get("decisive") else 1.0
        deltas.append(d if w == "red" else (-d if w == "blue" else 0.0))
    s = sum(deltas)
    target_move = float(report.get("front_final_pct", 50.0)) - 50.0
    scale = (target_move / s) if abs(s) > 1e-9 else (target_move / n)
    front, red, blue = 50.0, 100.0, 100.0
    timeline = [{"i": 0, "t_hours": 0.0, "winner": None, "front_pct": round(front, 1),
                 "red_remaining": 100.0, "blue_remaining": 100.0,
                 "event": "Forces in contact — campaign begins"}]
    t = 0.0
    for e in engs:
        t += float(e.get("duration_hours") or eng_hours)
        front += deltas[e["index"]] * scale if abs(s) > 1e-9 else scale
        red *= (1.0 - min(float(e.get("red_casualties_pct") or 0), 95) / 100.0)
        blue *= (1.0 - min(float(e.get("blue_casualties_pct") or 0), 95) / 100.0)
        note = e.get("key_event") or ""
        if e.get("breakthrough_by"):
            note = f"BREAKTHROUGH ({e['breakthrough_by']}) — {note}"
        elif e.get("withdrawn_by"):
            note = f"Withdrawal ({e['withdrawn_by']}) — {note}"
        timeline.append({
            "i": e.get("index", len(timeline)),
            "t_hours": round(t, 1),
            "winner": e.get("winner"),
            "decisive": bool(e.get("decisive")),
            "front_pct": round(front, 1),
            "red_remaining": round(red, 1),
            "blue_remaining": round(blue, 1),
            "red_cas": float(e.get("red_casualties_pct") or 0),
            "blue_cas": float(e.get("blue_casualties_pct") or 0),
            "event": note or "Engagement resolved",
        })
    # Normalize drift so frame 0 sits exactly at 100% and the last frame lands
    # on the engine's reported finals (affine anchor, not multiplicative —
    # reinforcements make pure scaling push early frames above 100%).
    if len(timeline) > 1:
        last = timeline[-1]
        k = len(timeline) - 1

        def _anchor(series_key: str, final_val: float) -> None:
            d_end = last[series_key]
            denom = d_end - 100.0
            if abs(denom) < 1e-9:
                return
            gain = (float(final_val) - 100.0) / denom
            for st in timeline:
                st[series_key] = round(100.0 + (st[series_key] - 100.0) * gain, 1)

        _anchor("red_remaining", float(report.get("red_remaining_pct", 60)))
        _anchor("blue_remaining", float(report.get("blue_remaining_pct", 60)))
        fr_fix = float(report.get("front_final_pct", 50.0)) - last["front_pct"]
        if abs(fr_fix) > 0.05:
            for j, st in enumerate(timeline):
                st["front_pct"] = round(st["front_pct"] + fr_fix * ((j + 1) / k), 1)
    return {
        "matchup": f"{report.get('red_doctrine', 'red')} vs {report.get('blue_doctrine', 'blue')}",
        "campaign_winner": report.get("campaign_winner"),
        "collapsed": report.get("collapsed"),
        "front_final_pct": report.get("front_final_pct"),
        "red_remaining_pct": report.get("red_remaining_pct"),
        "blue_remaining_pct": report.get("blue_remaining_pct"),
        "engagements_fought": report.get("engagements_fought", len(engs)),
        "timeline": timeline,
    }


@app.post("/api/kriegspiel/animated_run")
async def ks_animated_run(body: dict[str, Any]) -> dict[str, Any]:
    """One deterministic campaign expanded into a playback timeline for the
    Battle Theater view (SIMS-local sandbox; no ontology writeback).

    Body: { battlefield?, red_doctrine?, blue_doctrine?, engagements?,
            engagement_hours?, red_reinforcement?, blue_reinforcement?, seed? }
    """
    if not _ks_available:
        return {"error": "Kriegspiel engine not available"}

    from engines.kriegspiel.campaign import run_campaign
    from engines.kriegspiel.models import BATTLEFIELDS, Doctrine

    bf_name = body.get("battlefield", "random")
    n_engagements = max(3, min(int(body.get("engagements", 10)), 20))
    eng_hours = max(6, min(int(body.get("engagement_hours", 24)), 120))
    r_r = float(body.get("red_reinforcement", 0.30))
    b_r = float(body.get("blue_reinforcement", 0.30))
    seed = body.get("seed", 42)
    try:
        red_doc = Doctrine(body.get("red_doctrine", "maneuver"))
    except ValueError:
        red_doc = Doctrine.MANEUVER
    try:
        blue_doc = Doctrine(body.get("blue_doctrine", "defensive"))
    except ValueError:
        blue_doc = Doctrine.DEFENSIVE

    bf = None
    if bf_name != "random":
        for cand in BATTLEFIELDS:
            if cand.name == bf_name:
                bf = cand
                break

    def _run() -> dict[str, Any]:
        report = run_campaign(red_doctrine=red_doc, blue_doctrine=blue_doc,
                              battlefield=bf, n_engagements=n_engagements,
                              engagement_duration_hours=eng_hours,
                              red_reinforcement=r_r, blue_reinforcement=b_r,
                              seed=int(seed)).to_dict()
        out = _expand_timeline(report, eng_hours)
        out.update({
            "battlefield": bf_name if bf is not None else (report.get("battlefield") or "random"),
            "seed": seed,
            "matchup": f"{red_doc.value} vs {blue_doc.value}",
            "red_doctrine": red_doc.value, "blue_doctrine": blue_doc.value,
            "reinforcement": {"red": r_r, "blue": b_r},
            "sandbox": True,
        })
        return out

    return await asyncio.to_thread(_run)


_GOD_ORDERS: dict[str, dict[str, Any]] = {
    # Branch modifiers applied to the REMAINING engagements of a running
    # campaign. Reinforcement deltas are absolute; doctrine may be overridden.
    "commit_reserves": {"side": "red", "reinforcement": +0.25, "doctrine": None},
    "strike_sector":   {"side": "red", "reinforcement": -0.10, "doctrine": "shock"},
    "withdraw":        {"side": "red", "reinforcement": +0.15, "doctrine": "defensive"},
}


@app.post("/api/kriegspiel/order")
async def ks_god_order(body: dict[str, Any]) -> dict[str, Any]:
    """God-mode branch re-simulation (SIMS-local sandbox).

    Body: animated_run params (same seed as the live run) plus
          { order: commit_reserves|strike_sector|withdraw,
            at_state: {t_hours, front_pct, red_remaining, blue_remaining} }
    Re-runs the remainder under modified conditions and returns a timeline
    whose first frame equals at_state — the animation continues seamlessly
    down the new branch.
    """
    if not _ks_available:
        return {"error": "Kriegspiel engine not available"}
    order = str(body.get("order", ""))
    mod = _GOD_ORDERS.get(order)
    if not mod:
        return {"error": f"unknown order '{order}' — expected one of {sorted(_GOD_ORDERS)}"}
    at = body.get("at_state") or {}
    for k in ("front_pct", "red_remaining", "blue_remaining"):
        if k not in at:
            return {"error": f"at_state.{k} required"}

    from engines.kriegspiel.campaign import run_campaign
    from engines.kriegspiel.models import BATTLEFIELDS, Doctrine

    bf_name = body.get("battlefield", "random")
    n_engagements = max(4, min(int(body.get("engagements", 10)), 20))
    eng_hours = max(6, min(int(body.get("engagement_hours", 18)), 120))
    r_r = float(body.get("red_reinforcement", 0.30))
    b_r = float(body.get("blue_reinforcement", 0.30))
    seed = int(body.get("seed", 42))
    try:
        red_doc = Doctrine(body.get("red_doctrine", "maneuver"))
    except ValueError:
        red_doc = Doctrine.MANEUVER
    try:
        blue_doc = Doctrine(body.get("blue_doctrine", "defensive"))
    except ValueError:
        blue_doc = Doctrine.DEFENSIVE

    if mod["side"] == "red":
        r_r = max(0.0, r_r + mod["reinforcement"])
        if mod["doctrine"]:
            try:
                red_doc = Doctrine(mod["doctrine"])
            except ValueError:
                pass

    bf = None
    if bf_name != "random":
        for cand in BATTLEFIELDS:
            if cand.name == bf_name:
                bf = cand
                break

    def _run() -> dict[str, Any]:
        report = run_campaign(red_doctrine=red_doc, blue_doctrine=blue_doc,
                              battlefield=bf, n_engagements=n_engagements,
                              engagement_duration_hours=eng_hours,
                              red_reinforcement=r_r, blue_reinforcement=b_r,
                              seed=seed).to_dict()
        out = _expand_timeline(report, eng_hours)
        tl = out["timeline"]
        # Splice: anchor the branch onto the live battlefield state. Forces
        # continue MULTIPLICATIVELY from the committed strength (a linear
        # shift could go negative when the branch declines faster); the front
        # continues additively and clamps to a sane band.
        t0 = tl[0]
        r_at = float(at.get("red_remaining", 100))
        b_at = float(at.get("blue_remaining", 100))
        f_at = float(at.get("front_pct", 50))
        t_at = float(at.get("t_hours", 0))
        r0, b0, f0 = max(t0["red_remaining"], 1e-9), max(t0["blue_remaining"], 1e-9), t0["front_pct"]
        for st in tl:
            st["red_remaining"] = round(min(100.0, max(0.0, r_at * st["red_remaining"] / r0)), 1)
            st["blue_remaining"] = round(min(100.0, max(0.0, b_at * st["blue_remaining"] / b0)), 1)
            st["front_pct"] = round(min(97.0, max(3.0, f_at + (st["front_pct"] - f0))), 1)
            st["t_hours"] = round(st["t_hours"] + t_at, 1)
        label = order.replace("_", " ").upper()
        tl[0]["event"] = f"[ORDER] {label} — branch re-simulated"
        if len(tl) > 1:
            tl[1]["event"] = f"[ORDER] {label} takes effect — {tl[1]['event']}"
        out.update({
            "order": order, "order_label": label,
            "modified": {"red_reinforcement": r_r, "red_doctrine": red_doc.value},
            "sandbox": True,
        })
        return out

    return await asyncio.to_thread(_run)


# --- MAVEN practice loop (SIMS-local gamification; JSON persistence) --------

_PRACTICE_DIR = _SUITE_ROOT / "data" / "practice"


def _practice_file(name: str) -> Path:
    _PRACTICE_DIR.mkdir(parents=True, exist_ok=True)
    return _PRACTICE_DIR / name


def _practice_load(name: str, default: Any) -> Any:
    try:
        return json.loads(_practice_file(name).read_text())
    except Exception:
        return default


def _practice_save(name: str, data: Any) -> None:
    try:
        _practice_file(name).write_text(json.dumps(data, indent=1))
    except Exception:
        pass


@app.get("/api/practice/maven/state")
async def practice_maven_state(battlefield: str = "Eastern Europe",
                               seed: int = 7) -> dict[str, Any]:
    """Simulated reconnaissance picture over a theater — deterministic per
    (battlefield, day-seed). Contacts are FAKE training targets for practicing
    MAVEN-style tasking; nothing here touches live feeds."""
    h = _battle_hash(f"{battlefield}:{seed}")
    n = 3 + h % 4
    tracks = []
    for i in range(n):
        hh = _battle_hash(f"{battlefield}:{seed}:{i}")
        tracks.append({
            "id": f"contact-{seed}-{i}",
            "kind": ("armor column", "supply convoy", "SAM site", "radar")[hh % 4],
            "lat": 48.6 + ((hh >> 3) % 900) / 9000.0,
            "lng": 30.0 + ((hh >> 6) % 1400) / 7000.0,
            "confidence": round(0.55 + ((hh >> 9) % 40) / 100.0, 2),
            "tasked": False,
        })
    book = _practice_load("practice.json", {})
    tasked = set((book.get("tasked_contacts") or {}).get(battlefield, []))
    for t in tracks:
        t["tasked"] = t["id"] in tasked
    bonus = float((book.get("bonus_pending") or {}).get(battlefield, 0.0))
    return {"battlefield": battlefield, "sandbox": True,
            "tracks": tracks, "bonus_pending": bonus,
            "note": "SIMULATED contacts for tool practice — not real-world data"}


@app.post("/api/practice/maven/task")
async def practice_maven_task(body: dict[str, Any]) -> dict[str, Any]:
    """Record a tasking against a simulated contact; grants a one-shot
    reinforcement bonus for the next FIGHT on that theater."""
    battlefield = str(body.get("battlefield", ""))
    contact_id = str(body.get("contact_id", ""))
    if not battlefield or not contact_id:
        return {"error": "battlefield and contact_id required"}
    book = _practice_load("practice.json", {})
    book.setdefault("tasked_contacts", {}).setdefault(battlefield, [])
    if contact_id in book["tasked_contacts"][battlefield]:
        return {"ok": True, "bonus_granted": 0.0, "note": "already tasked"}
    book["tasked_contacts"][battlefield].append(contact_id)
    book.setdefault("bonus_pending", {})
    book["bonus_pending"][battlefield] = round(
        float(book["bonus_pending"].get(battlefield, 0.0)) + 0.05, 3)
    book.setdefault("scoreboard", {})
    sb = book["scoreboard"]
    sb["taskings"] = sb.get("taskings", 0) + 1
    _practice_save("practice.json", book)
    return {"ok": True, "bonus_pending": book["bonus_pending"][battlefield],
            "scoreboard": sb}


@app.post("/api/practice/campaign_result")
async def practice_campaign_result(body: dict[str, Any]) -> dict[str, Any]:
    """Record a finished sandbox campaign in the practice scoreboard."""
    book = _practice_load("practice.json", {})
    sb = book.setdefault("scoreboard", {})
    sb["campaigns"] = sb.get("campaigns", 0) + 1
    winner = str(body.get("winner", "stalemate"))
    sb.setdefault("wins", {"red": 0, "blue": 0, "stalemate": 0})
    sb["wins"][winner] = sb["wins"].get(winner, 0) + 1
    if body.get("order_used"):
        sb["orders_issued"] = sb.get("orders_issued", 0) + 1
    # Consuming the fight burns the pending bonus.
    bf = str(body.get("battlefield", ""))
    if bf:
        book.setdefault("bonus_pending", {})
        used = float(book["bonus_pending"].get(bf, 0.0))
        book["bonus_pending"][bf] = 0.0
        if used:
            sb["bonuses_applied"] = sb.get("bonuses_applied", 0) + 1
    _practice_save("practice.json", book)
    return {"ok": True, "scoreboard": sb}


@app.get("/api/practice/scoreboard")
async def practice_scoreboard() -> dict[str, Any]:
    return {"sandbox": True, "scoreboard": _practice_load("practice.json", {}).get("scoreboard", {
        "campaigns": 0, "wins": {"red": 0, "blue": 0, "stalemate": 0},
        "taskings": 0, "orders_issued": 0, "bonuses_applied": 0})}


@app.post("/api/battle/simulate")
async def battle_simulate(body: dict[str, Any]) -> dict[str, Any]:
    """Physics-based engagement of the DEPLOYED historical forces (SIMS-local).

    Lanchester-family attrition on the real CDB90/curated figures: aimed-fire
    square law for tank-vs-tank, area fire against manpower, terrain cover and
    mobility from the battle's recorded terrain, quality multipliers from the
    recorded leadership/training/morale grades. NOTHING is scripted: the
    outcome emerges from the numbers. The recorded historical winner is
    returned ONLY as a reference for comparison — never fed into the model.

    Body: { battle_key, seed? }
    """
    return await asyncio.to_thread(
        _bt_run, str(body.get("battle_key", "")), body.get("seed", 42), None)


@app.post("/api/battle/order")
async def battle_order(body: dict[str, Any]) -> dict[str, Any]:
    """God-mode branch: resume the physics model from the live absolute state
    under new orders (SIMS-local sandbox).

    Body: { battle_key, seed?, order, at_state: {t_hours, front_pct,
              red:{men,tanks,guns}, blue:{men,tanks,guns}} }
    """
    order = str(body.get("order", ""))
    mod = _GOD_ORDERS.get(order)
    if not mod:
        return {"error": f"unknown order '{order}'"}
    at = body.get("at_state") or {}
    for side in ("red", "blue"):
        st = at.get(side) or {}
        for k in ("men", "tanks", "guns"):
            if not isinstance(st.get(k), (int, float)):
                return {"error": f"at_state.{side}.{k} required"}
        if not isinstance(at.get("front_pct"), (int, float)) \
                or not isinstance(at.get("t_hours"), (int, float)):
            return {"error": "at_state.front_pct and t_hours required"}
    return await asyncio.to_thread(
        _bt_run, str(body.get("battle_key", "")), body.get("seed", 42),
        {"order": order, "at": at})


# Terrain modifiers derived from the battle's recorded terrain string:
# cover shields defenders (area-fire dilution), mobility drives front motion.
def _bt_terrain_mods(terrain: str) -> dict[str, float]:
    t = str(terrain or "").lower()
    cover, mobility = 1.0, 1.0
    if any(k in t for k in ("urban", "city")):
        cover, mobility = 1.55, 0.55
    elif any(k in t for k in ("mountain", "alpine")):
        cover, mobility = 1.35, 0.55
    elif any(k in t for k in ("forest", "jungle", "wood")):
        cover, mobility = 1.28, 0.72
    elif any(k in t for k in ("desert", "flat", "open")):
        cover, mobility = 0.82, 1.35
    elif any(k in t for k in ("coast", "amphib", "beach")):
        cover, mobility = 0.95, 0.8
    elif any(k in t for k in ("marsh", "swamp", "river")):
        cover, mobility = 1.2, 0.6
    return {"cover": cover, "mobility": mobility}


def _bt_quality(q: dict) -> float:
    vals = [v for v in (q or {}).values() if isinstance(v, (int, float))]
    if not vals:
        return 1.0
    return round(0.72 + 0.145 * (sum(vals) / len(vals)), 3)


def _bt_run(battle_key: str, seed: Any, god: dict | None) -> dict[str, Any]:
    if not _load_chronos():
        return {"error": "Chronos not available"}
    rep = _forces_report(battle_key)
    if rep.get("error"):
        return rep
    if battle_key.startswith("curated-"):
        battle = _load_curated_battle(battle_key, _CHRONOS_DB)
    else:
        try:
            battle = _load_battle(int(battle_key.split("-", 1)[1]), _CHRONOS_DB)
        except (IndexError, ValueError):
            return {"error": "bad battle_key"}
    if not battle:
        return {"error": f"unknown battle {battle_key}"}
    d = battle.to_dict()

    def abs_start(side_key: str) -> dict[str, float]:
        s = rep["sides"][side_key]
        t = s.get("totals") or {}
        units = s.get("units") or []
        return {
            "men": float(t.get("men") or sum(u.get("men") or 0 for u in units)),
            "tanks": float(t.get("tanks") or sum(u.get("tanks") or 0 for u in units)),
            "guns": float(t.get("artillery") or sum(u.get("artillery") or 0 for u in units)),
            "air": float((units and max((u.get("aircraft_sorties") or 0) for u in units)) or 0),
            "q": _bt_quality(s.get("quality")),
        }

    R = abs_start("attacker")
    B = abs_start("defender")

    god_order = (god or {}).get("order")
    at = (god or {}).get("at") or {}
    if god_order:
        # Resume from the live absolute state instead of the deployment.
        R = {**R, "men": float(at["red"]["men"]), "tanks": float(at["red"]["tanks"]),
             "guns": float(at["red"]["guns"])}
        B = {**B, "men": float(at["blue"]["men"]), "tanks": float(at["blue"]["tanks"]),
             "guns": float(at["blue"]["guns"])}
        front = float(at["front_pct"])
        t_now = float(at["t_hours"])
    else:
        front = 50.0
        t_now = 0.0

    terr = _bt_terrain_mods(rep.get("terrain"))
    hist_dur = float(d.get("duration_hours") or 36)
    tick_h = 4.0
    max_t = t_now + max(hist_dur, tick_h * 6) * 1.6
    import math as _math
    import random as _random
    rng = _random.Random(int(seed) if isinstance(seed, (int, float)) else 42)

    S0R, S0B = R.copy(), B.copy()
    timeline: list[dict[str, Any]] = [{
        "i": 0, "t_hours": round(t_now, 1), "front_pct": round(front, 1),
        "rmen": round(R["men"]), "rtanks": round(R["tanks"]), "rguns": round(R["guns"]),
        "bmen": round(B["men"]), "btanks": round(B["tanks"]), "bguns": round(B["guns"]),
        "event": "Forces in contact",
    }]
    events: list[str] = []
    broke = None
    order_ticks_left = 0
    order_mod = {}
    if god_order == "commit_reserves":
        reserve_men = 0.08 * S0R["men"]
        R["men"] += reserve_men * 0.5
        order_ticks_left = 2
        order_mod = {"reserve_per_tick": reserve_men * 0.5, "morale": 0.06}
        events.append(f"[ORDER] Reserves committed: +{round(reserve_men):,} men streaming in")
    elif god_order == "strike_sector":
        order_ticks_left = 2
        order_mod = {"attack_coef": 1.4, "self_risk": 1.25}
        events.append("[ORDER] All-out strike: lethality up, exposure up")
    elif god_order == "withdraw":
        order_ticks_left = 999
        order_mod = {"own_loss_mult": 0.6, "cede_mult": 1.7}
        events.append("[ORDER] Breaking contact — defensive posture")

    def eff(s: dict) -> float:
        # Combat-effective power: men carry via soft coefficient, hardware heavy.
        return (s["men"] / 1000.0) * 1.0 + s["tanks"] * 14.0 + s["guns"] * 5.0

    def frac(s: dict, s0: dict) -> float:
        denom = max(eff(s0), 1e-6)
        return min(1.5, eff(s) / denom)

    i = 0
    while t_now < max_t:
        i += 1
        t_now += tick_h
        jitter_a = 0.92 + rng.random() * 0.16
        jitter_b = 0.92 + rng.random() * 0.16
        qr = R["q"] + order_mod.get("morale", 0.0)
        qb = B["q"]

        # --- Armor duel: Lanchester aimed fire (square-law class) ------------
        atk_coef = order_mod.get("attack_coef", 1.0) if order_ticks_left > 0 else 1.0
        k_armor = 0.010 * terr["mobility"]
        r_tank_kill = k_armor * B["tanks"] * qb * jitter_b
        b_tank_kill = k_armor * R["tanks"] * qr * jitter_a * (atk_coef if god_order == "strike_sector" else 1.0)
        # --- Guns: area fire dilutes into cover -----------------------------
        k_gun = 26.0 / terr["cover"]
        r_men_from_guns = k_gun * B["guns"] / 100.0 * jitter_b
        b_men_from_guns = k_gun * R["guns"] / 100.0 * jitter_a * atk_coef
        # --- Small arms / close action: proportional contact attrition ------
        k_inf = 0.0018 / terr["cover"]
        r_men_close = k_inf * B["men"] * jitter_b
        b_men_close = k_inf * R["men"] * jitter_a * atk_coef
        # --- Air strikes: pulse damage while sorties last --------------------
        air_r = 0.0
        if R["air"] > 0:
            air_r = min(R["air"], 400) * 0.9 * jitter_a
            R["air"] *= 0.985
        air_b = 0.0
        if B["air"] > 0:
            air_b = min(B["air"], 400) * 0.9 * jitter_b
            B["air"] *= 0.985

        self_risk = order_mod.get("self_risk", 1.0) if order_ticks_left > 0 else 1.0
        own_mult = order_mod.get("own_loss_mult", 1.0) if god_order == "withdraw" else 1.0

        dR_men = (r_men_from_guns + r_men_close + air_b * 0.35) * own_mult
        dB_men = (b_men_from_guns + b_men_close + air_r * 0.35)
        dR_tanks = r_tank_kill
        dB_tanks = b_tank_kill
        gun_duel = 0.004
        dR_guns = gun_duel * B["guns"] * qb * jitter_b
        dB_guns = gun_duel * R["guns"] * qr * jitter_a * atk_coef

        R["men"] = max(0.0, R["men"] - dR_men)
        B["men"] = max(0.0, B["men"] - dB_men)
        R["tanks"] = max(0.0, R["tanks"] - dR_tanks)
        B["tanks"] = max(0.0, B["tanks"] - dB_tanks)
        R["guns"] = max(0.0, R["guns"] - dR_guns)
        B["guns"] = max(0.0, B["guns"] - dB_guns)
        if order_ticks_left and order_ticks_left < 900:
            order_ticks_left -= 1
            if order_mod.get("reserve_per_tick") and order_ticks_left > 0:
                R["men"] += order_mod["reserve_per_tick"]
        elif order_ticks_left >= 900:
            pass

        # --- Front: pressure follows log force-ratio, scaled by mobility -----
        er, eb = max(eff(R), 1e-6), max(eff(B), 1e-6)
        pressure = _math.log(er / eb) * terr["mobility"] * 6.0 * jitter_a
        cede = order_mod.get("cede_mult", 1.0) if god_order == "withdraw" else 1.0
        front = min(96.0, max(4.0, front + pressure * cede))

        # --- Collapse checks (morale-weighted) --------------------------------
        fr_r, fr_b = frac(R, S0R), frac(B, S0B)
        brk_r = 0.30 - max(0.0, qr - 1.0) * 0.12
        brk_b = 0.30 - max(0.0, qb - 1.0) * 0.12
        note = None
        if fr_b <= brk_b and not broke:
            broke = "blue"
            events.append(f"T+{round(t_now)}h — BLUE FORCES ROUTED (combat effectiveness {round(fr_b*100)}%)")
            front = min(94.0, front + 18.0)
        elif fr_r <= brk_r and not broke:
            broke = "red"
            events.append(f"T+{round(t_now)}h — RED FORCES ROUTED (combat effectiveness {round(fr_r*100)}%)")
            front = max(6.0, front - 18.0)
        timeline.append({
            "i": i, "t_hours": round(t_now, 1), "front_pct": round(front, 1),
            "rmen": round(R["men"]), "rtanks": round(R["tanks"]), "rguns": round(R["guns"]),
            "bmen": round(B["men"]), "btanks": round(B["tanks"]), "bguns": round(B["guns"]),
            "event": note,
        })
        if broke:
            break

    if broke == "blue":
        verdict = {"winner": "red", "reason": "Blue collapsed below combat-effectiveness threshold"}
    elif broke == "red":
        verdict = {"winner": "blue", "reason": "Red collapsed below combat-effectiveness threshold"}
    else:
        drift = front - 50.0
        if abs(drift) < 6.0:
            verdict = {"winner": "stalemate", "reason": "Neither side broke; line essentially held"}
        elif drift > 0:
            verdict = {"winner": "red", "reason": "Attacker advanced but time expired before a rout"}
        else:
            verdict = {"winner": "blue", "reason": "Defender absorbed the offensive; ground held"}

    hist = {
        "recorded_winner": d.get("actual_winner"),
        "recorded_casualties": {
            "attacker": (d.get("attacker") or {}).get("casualties"),
            "defender": (d.get("defender") or {}).get("casualties"),
        },
        "source": rep["provenance"]["strength_source"],
    }
    out = {
        "battle_key": battle_key, "name": rep["name"], "year": rep["year"],
        "sandbox": True,
        "started": {
            "red": {"men": round(S0R["men"]), "tanks": round(S0R["tanks"]), "guns": round(S0R["guns"])},
            "blue": {"men": round(S0B["men"]), "tanks": round(S0B["tanks"]), "guns": round(S0B["guns"])},
        },
        "timeline": timeline,
        "events": events,
        "verdict": verdict,
        "history": hist,
        "model": {
            "family": "Lanchester hybrid — aimed-fire (armor) + area-fire (guns/manpower)",
            "terrain_mods": terr, "tick_hours": tick_h, "seed": seed,
            "god_order": god_order,
        },
    }
    return out


@app.get("/api/kriegspiel/research/campaign-table")
async def ks_campaign_table() -> dict[str, Any]:
    """Matchup x sustainment summary of accumulated campaign outcomes."""
    if not _ks_available:
        return {"error": "Kriegspiel engine not available"}
    from engines.kriegspiel.learning import get_campaign_tracker
    return get_campaign_tracker().table()


@app.get("/api/kriegspiel/research/campaign-findings")
async def ks_campaign_findings() -> dict[str, Any]:
    """Distilled operational-tempo lessons (matchup strength + tempo effects)."""
    if not _ks_available:
        return {"error": "Kriegspiel engine not available"}
    from engines.kriegspiel.learning import get_campaign_tracker
    tracker = get_campaign_tracker()
    return {
        "findings": tracker.findings(),
        "table": tracker.table(),
    }


# ---------------------------------------------------------------------------
# Kriegspiel LLM synthesis endpoints (Phase 5)
# ---------------------------------------------------------------------------

@app.get("/api/kriegspiel/llm/status")
async def ks_llm_status() -> dict[str, Any]:
    """Report whether the LLM synthesis layer is configured.

    Returns ``{available: bool, provider: str|None, model: str|None}``.
    ``available=False`` does NOT mean the engine is broken — it means
    procedural mode is in use. Callers should treat LLM mode as opt-in.
    """
    import os
    if not _ks_llm_available:
        return {
            "available": False,
            "provider": None,
            "model": None,
            "reason": "llm layer not loaded",
        }
    client = _ks_get_llm_client() if _ks_get_llm_client else None
    if client is None:
        return {
            "available": False,
            "provider": os.environ.get("KRIEGSPIEL_LLM_PROVIDER"),
            "model": os.environ.get("KRIEGSPIEL_LLM_MODEL"),
            "reason": "provider env not configured or invalid",
        }
    return {
        "available": True,
        "provider": client.provider,
        "model": client.model,
        "reason": None,
    }


@app.post("/api/kriegspiel/llm/seed")
async def ks_llm_seed(body: dict[str, Any] = None) -> dict[str, Any]:
    """Synthesize one LLM-enriched battle seed.

    Body (all optional):
        seed: int            — RNG seed for fallback positioning
        register: bool       — if true, add the LLM battlefield to the
                               runtime ``BATTLEFIELDS_LLM`` pool (default true)

    Returns the serialized battle plus its provenance dict. If the LLM is
    unavailable or its output fails validation, the response includes the
    fallback procedural battle and a ``provenance.source == "procedural"``
    marker so the caller knows what they got.
    """
    if not _ks_llm_available:
        return {"error": "LLM synthesis layer not loaded",
                "provenance": {"source": "unavailable"}}
    body = body or {}
    seed = body.get("seed")
    do_register = bool(body.get("register", True))

    def _run() -> dict[str, Any]:
        battle = _ks_synthesize_battle_seed(seed=seed)
        if do_register and battle.provenance and battle.provenance.get("source") == "llm":
            _ks_register_llm_battlefield(battle.battlefield)
        return {
            "battlefield": {
                "name": battle.battlefield.name,
                "terrain": battle.battlefield.terrain.value,
                "center": list(battle.battlefield.center),
                "bounds": list(battle.battlefield.bounds),
                "area_km2": battle.battlefield.area_km2,
            },
            "objective": battle.objective,
            "duration_hours": battle.duration_hours,
            "red_force": {
                "name": battle.red_force.name,
                "doctrine": battle.red_force.doctrine.value,
                "unit_count": len(battle.red_force.units),
                "unit_types": [u.unit_type.value for u in battle.red_force.units],
            },
            "blue_force": {
                "name": battle.blue_force.name,
                "doctrine": battle.blue_force.doctrine.value,
                "unit_count": len(battle.blue_force.units),
                "unit_types": [u.unit_type.value for u in battle.blue_force.units],
            },
            "provenance": battle.provenance,
        }

    return await asyncio.to_thread(_run)


@app.post("/api/kriegspiel/llm/run")
async def ks_llm_run(body: dict[str, Any] = None) -> dict[str, Any]:
    """Run Monte Carlo branching with an LLM-enriched seed.

    Body (all optional):
        scenarios: int       — branch count (capped at 50,000; default 1000)
        seed: int            — RNG seed
        register: bool       — add LLM battlefield to runtime pool (default true)

    Equivalent to ``POST /api/kriegspiel/run`` but with
    ``enrich_with_llm=True``. Falls back transparently to procedural if the
    LLM is unavailable — the response's ``provenance.source`` field tells
    the caller which path produced the seed.
    """
    if not _ks_available:
        return {"error": "Kriegspiel engine not available"}
    body = body or {}
    n_scenarios = min(int(body.get("scenarios", 1000)), 50000)
    seed = body.get("seed", 42)
    do_register = bool(body.get("register", True))

    def _run() -> dict[str, Any]:
        report = _ks_generate(
            battle=None,
            n_scenarios=n_scenarios,
            seed=seed,
            enrich_with_llm=True,
        )
        d = _ks_report_to_dict(report)
        if do_register and report.provenance and report.provenance.get("source") == "llm":
            # The battle object is internal to the report; we re-synthesize
            # is not needed — the synthesizer already registered it if it
            # produced a new battlefield. This branch is a no-op safety net.
            pass
        global _ks_sim_count
        _ks_sim_count += report.scenarios_run
        _add_count("kriegspiel", report.scenarios_run)
        _ks_learn(report)
        return d

    return await asyncio.to_thread(_run)


@app.post("/api/kriegspiel/llm/events")
async def ks_llm_events(body: dict[str, Any] = None) -> dict[str, Any]:
    """Ask the LLM for situational events tailored to a battle.

    Body:
        battlefield: str          — one of the predefined battlefield names
        red_doctrine: str         — optional, default random
        blue_doctrine: str        — optional, default random
        objective: str            — optional
        n: int                    — number of events (default 12, max 50)

    Falls back to the procedural event pool if the LLM is unavailable.
    """
    if not _ks_llm_available:
        return {"error": "LLM synthesis layer not loaded"}
    body = body or {}
    bf_name = body.get("battlefield", "random")
    n = min(int(body.get("n", 12)), 50)
    objective = body.get("objective", "Secure strategic corridor")

    # Build a minimal Battle to feed the synthesizer. We use a procedural
    # seed battle so the LLM has context, then ask it for events only.
    battle = None
    if _ks_battlefields:
        for bf in _ks_battlefields:
            if bf.name == bf_name:
                battle = _ks_create_battle(battlefield=bf, seed=body.get("seed", 42))
                break
    if battle is None:
        battle = _ks_create_battle(seed=body.get("seed", 42))

    # Override doctrines if the caller supplied them
    from engines.kriegspiel.models import Doctrine
    rd = body.get("red_doctrine")
    bd = body.get("blue_doctrine")
    if rd and rd in {d.value for d in Doctrine}:
        battle.red_force.doctrine = Doctrine(rd)
    if bd and bd in {d.value for d in Doctrine}:
        battle.blue_force.doctrine = Doctrine(bd)
    if objective:
        battle.objective = objective

    def _run() -> dict[str, Any]:
        events = _ks_synthesize_events(battle, n=n)
        return {
            "battlefield": battle.battlefield.name,
            "red_doctrine": battle.red_force.doctrine.value,
            "blue_doctrine": battle.blue_force.doctrine.value,
            "events": events,
            "n": len(events),
        }

    return await asyncio.to_thread(_run)


# ---------------------------------------------------------------------------
# Chronos — historical what-if engine (COW NMC country power + CDB90 corpus)
# ---------------------------------------------------------------------------
_CHRONOS_DB = _SUITE_ROOT.parent / "panteon" / "backend" / "panteon.db"
_chronos_available = False
_load_battle = None
_search_battles = None
_country_power = None
_top_powers = None
_simulate_historical = None
_what_if = None
_fidelity_report = None
_assert_gate = None
_get_oob = None
_load_curated_battle = None


def _load_chronos() -> bool:
    global _chronos_available, _load_battle, _search_battles, _country_power
    global _top_powers, _simulate_historical, _what_if, _fidelity_report, _assert_gate
    global _get_oob, _load_curated_battle
    if _chronos_available:
        return True
    if str(_SUITE_ROOT) not in sys.path:
        sys.path.insert(0, str(_SUITE_ROOT))
    else:
        sys.path.remove(str(_SUITE_ROOT))
        sys.path.insert(0, str(_SUITE_ROOT))
    try:
        from engines.chronos.loader import (
            load_battle as _lb,
            search_battles as _sb,
            country_power as _cp,
            top_powers as _tp,
            get_oob as _goob,
            load_curated_battle as _lcb,
        )
        from engines.chronos.engine import (
            simulate_historical as _sh,
            what_if as _wi,
        )
        from engines.chronos.fidelity import (
            fidelity_report as _fr,
            assert_gate as _ag,
        )
        _load_battle = _lb
        _search_battles = _sb
        _country_power = _cp
        _top_powers = _tp
        _simulate_historical = _sh
        _what_if = _wi
        _fidelity_report = _fr
        _assert_gate = _ag
        _get_oob = _goob
        _load_curated_battle = _lcb
        _chronos_available = True
    except Exception as exc:
        logger.debug("Chronos unavailable: %s", exc)
    return _chronos_available


@app.get("/api/chronos/battles")
async def chronos_battles(war: str = "WORLD WAR II", limit: int = 60) -> list[dict[str, Any]]:
    if not _load_chronos():
        return {"error": "Chronos not available"}
    rows = await asyncio.to_thread(_search_battles, _CHRONOS_DB, war, min(limit, 200))
    # Curated flagship battles (not in the corpus) appear at the top.
    for slug, label in (("curated-neptune-1944", "D-DAY NEPTUNE (NORMANDY 1944)"),):
        oob = await asyncio.to_thread(lambda s=slug: _get_oob(s, _CHRONOS_DB))
        if oob:
            rows.insert(0, {"isqno": slug, "name": label,
                            "war": "CURATED FLAGSHIP",
                            "location": "Normandy, France",
                            "source": "chronos_oob"})
    return rows


@app.get("/api/chronos/powers/{year}")
async def chronos_powers(year: int, limit: int = 12) -> dict[str, Any]:
    """Country national power (CINC + components) for a given year."""
    if not _load_chronos():
        return {"error": "Chronos not available"}
    return await asyncio.to_thread(
        lambda: {
            "year": year,
            "top": _top_powers(year, min(limit, 40), _CHRONOS_DB),
            "source": "Correlates of War NMC v7.0",
        }
    )


@app.get("/api/chronos/oob/{battle_key}")
async def chronos_oob(battle_key: str) -> dict[str, Any]:
    """Orders of battle for a battle (curated flagship entries when present)."""
    if not _load_chronos():
        return {"error": "Chronos not available"}
    return await asyncio.to_thread(
        lambda: {"battle_key": battle_key,
                 "entries": _get_oob(battle_key, _CHRONOS_DB)}
    )


# --- Battle Theater force deployment (SIMS-local sandbox; no ontology) ------

_BATTLE_LOCATIONS: dict[str, tuple[float, float]] = {
    "ITALY": (43.0, 12.5), "OKINAWA": (26.4, 127.9), "FRANCE": (47.4, 2.8),
    "USSR": (53.0, 39.5), "SOVIET UNION": (53.0, 39.5), "GERMANY": (50.8, 9.4),
    "TUNISIA": (36.2, 9.6), "EGYPT": (30.7, 28.9), "BELGIUM": (50.4, 5.2),
    "POLAND": (52.2, 20.0), "JAPAN": (33.6, 133.4), "NORTHWEST EUROPE": (51.8, 4.6),
    "LUXEMBOURG": (49.7, 6.1), "MALAYA": (3.6, 102.0), "MANCHURIA": (44.0, 125.0),
    "NORMANDY, FRANCE": (49.35, -0.6),
}

_CURATED_LOCATIONS: dict[str, tuple[float, float]] = {
    "curated-neptune-1944": (49.35, -0.6),
}


def _battle_hash(text: str) -> int:
    h = 0
    for ch in text:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return h


_ECHELON_LADDER = [  # (min men, echelon name, units at that tier)
    (120_000, "Army Group", 4), (60_000, "Army", 4), (30_000, "Corps", 4),
    (8_000, "Division", 5), (2_500, "Brigade", 4), (0, "Regiment", 3),
]
_UNIT_FRACTIONS = [0.34, 0.27, 0.21, 0.18]


def _decompose_side(side_key: str, side_dict: dict, seed: int,
                    oob_entries: list[dict]) -> list[dict]:
    """Curated OOB entries verbatim when present; else a deterministic
    decomposition of the side aggregate into echelon-sized formations."""
    if oob_entries:
        want = "attacker" if side_key == "attacker" else "defender"
        side_rows = [e for e in oob_entries if e.get("side") == want]

        def _is_top(e: dict) -> bool:
            # Same rule as engines.chronos.loader.build_side: only top-level
            # formations count, so children don't double their parents.
            parent = e.get("parent")
            if not parent:
                return True
            for other in side_rows:
                un, pn = other.get("unit_name"), parent
                if un == pn or (un and pn and (un.startswith(pn) or pn.startswith(un))):
                    return False
            return True

        rows = [e for e in side_rows if _is_top(e)]
        if rows:
            total = sum((e.get("strength") or 0) * (e.get("engagement_fraction") or 1.0)
                        for e in rows) or 1
            units = []
            for i, e in enumerate(rows):
                eq = e.get("equipment") or {}
                # engagement_fraction matches how the engine weights the side
                # aggregate — panel men must equal simulated committed men.
                eff = float(e.get("engagement_fraction") or 1.0)
                men = float(e.get("strength") or 0) * eff
                frac = men / total
                units.append({
                    "id": f"{side_key[0]}{i}", "name": e.get("unit_name") or f"{side_key} {i+1}",
                    "echelon": e.get("echelon") or "Formation",
                    "commander": None, "men": men, "fraction": round(frac, 3),
                    "tanks": float(eq.get("tanks") or eq.get("tanks_landed_d1") or 0),
                    "artillery": float(eq.get("artillery") or 0),
                    "aircraft_sorties": float(eq.get("aircraft") or eq.get("aircraft_sorties_d1") or 0),
                    "ships": float(eq.get("warships") or eq.get("ships") or 0),
                    "pos_frac": 0.16 + 0.26 * (i / max(len(rows) - 1, 1)),
                    "lateral": ((seed >> i) % 7 - 3) / 10.0,
                })
            return units
    men_total = float(side_dict.get("strength") or 0)
    tanks_total = float(side_dict.get("tanks") or 0)
    arty_total = float(side_dict.get("artillery") or 0)
    air_total = float(side_dict.get("aircraft") or 0)
    count, echelon = next(
        ((n, name) for floor, name, n in _ECHELON_LADDER if men_total >= floor),
        (3, "Regiment"))
    actors = side_dict.get("actors") or []
    fracs = (_UNIT_FRACTIONS * 3)[:count]
    scale = sum(fracs)
    units = []
    allocated = 0.0
    for i, fr in enumerate(fracs):
        ordinal = ["1st", "2nd", "3rd", "4th", "5th"][i % 5]
        base_name = actors[i % len(actors)] if actors else side_dict.get("unit_name") or side_key.title()
        is_last = i == len(fracs) - 1
        men_i = round(men_total - allocated) if is_last else round(men_total * fr / scale)
        allocated += men_i
        units.append({
            "id": f"{side_key[0]}{i}",
            "name": f"{ordinal} {base_name} {echelon}",
            "echelon": echelon,
            "commander": side_dict.get("commander") if i == 0 else None,
            "men": men_i, "fraction": round(fr / scale, 3),
            "tanks": round(tanks_total * fr / scale),
            "artillery": round(arty_total * fr / scale),
            "aircraft_sorties": round(air_total * fr / scale),
            "ships": 0.0,
            "pos_frac": 0.14 + 0.28 * (i / max(count - 1, 1)),
            "lateral": (((seed >> (i * 3)) % 7) - 3) / 10.0,
        })
    return units


def _forces_report(battle_key: str) -> dict[str, Any]:
    if battle_key.startswith("curated-"):
        battle = _load_curated_battle(battle_key, _CHRONOS_DB)
    else:
        try:
            isqno = int(battle_key.split("-", 1)[1])
        except (IndexError, ValueError):
            return {"error": "battle_key must look like 'cdb90-<isqno>' or 'curated-<slug>'"}
        battle = _load_battle(isqno, _CHRONOS_DB)
    if not battle:
        return {"error": f"unknown battle {battle_key}"}
    d = battle.to_dict()
    att, dfd = d.get("attacker") or {}, d.get("defender") or {}
    oob = _get_oob(battle_key, _CHRONOS_DB) or []
    seed = _battle_hash(battle_key)

    origin = _CURATED_LOCATIONS.get(battle_key)
    if origin is None:
        loc_raw = ""
        # location text lives on the list row, not the battle object; recover
        # via the same search used by /api/chronos/battles when possible.
        try:
            hits = _search_battles(_CHRONOS_DB, "", 2000)
            want_isq = str(d.get("battle_key", "")).split("-", 1)[-1]
            for row in hits:
                if str(row.get("isqno")) == want_isq or row.get("isqno") == battle_key:
                    loc_raw = row.get("location") or ""
                    break
        except Exception:
            loc_raw = ""
        origin = _BATTLE_LOCATIONS.get(loc_raw.upper().strip()) or _BATTLE_LOCATIONS.get(loc_raw.strip())
    origin = list(origin or (49.0, 8.0))
    bearing = 70 + (seed % 80)          # axis of advance, degrees true
    length_km = max(24.0, min(280.0, ((float(att.get("strength") or 0)) ** .5) * .55))

    def quality(sd: dict) -> dict:
        keys = ("leadership", "training", "morale", "logistics", "tech", "surprise")
        out = {}
        for k in keys:
            v = sd.get(k)
            if isinstance(v, (int, float)):
                out[k] = v
        return out

    report = {
        "battle_key": battle_key,
        "name": d.get("name"), "year": d.get("year"),
        "terrain": d.get("terrain"), "weather": d.get("weather"),
        "duration_hours": d.get("duration_hours"),
        "axis": {"origin": origin, "bearing_deg": bearing, "length_km": round(length_km)},
        "sides": {
            "attacker": {
                "label": ", ".join(att.get("actors") or []) or att.get("unit_name") or "Attacker",
                "commander": att.get("commander"), "actors": att.get("actors") or [],
                "totals": {"men": att.get("strength") or 0, "tanks": att.get("tanks") or 0,
                           "artillery": att.get("artillery") or 0,
                           "aircraft": att.get("aircraft") or 0},
                "quality": quality(att),
                "units": _decompose_side("attacker", att, seed, oob),
            },
            "defender": {
                "label": ", ".join(dfd.get("actors") or []) or dfd.get("unit_name") or "Defender",
                "commander": dfd.get("commander"), "actors": dfd.get("actors") or [],
                "totals": {"men": dfd.get("strength") or 0, "tanks": dfd.get("tanks") or 0,
                           "artillery": dfd.get("artillery") or 0,
                           "aircraft": dfd.get("aircraft") or 0},
                "quality": quality(dfd),
                "units": _decompose_side("defender", dfd, seed >> 8, oob),
            },
        },
        "provenance": {
            "unit_positions": "RECONSTRUCTED — no historical per-unit coordinates exist; "
                              "disposition generated deterministically from battlefield bounds+terrain",
            "oob_mode": bool([e for e in oob]) and "curated_oob" or "aggregate_decomposition",
            "strength_source": d.get("source") or "CDB90",
        },
    }
    return report


@app.get("/api/battle/forces/{battle_key}")
async def battle_forces(battle_key: str) -> dict[str, Any]:
    """Normalized force deployment for the Battle Theater view (SIMS-local).

    Units come from curated OOB trees when available, otherwise from a
    deterministic decomposition of CDB90 side aggregates. Positions are
    RECONSTRUCTED along a seeded axis of advance.
    """
    if not _load_chronos():
        return {"error": "Chronos not available"}
    return await asyncio.to_thread(_forces_report, battle_key)


@app.post("/api/chronos/replay")
async def chronos_replay(body: dict[str, Any]) -> dict[str, Any]:
    """Fidelity-gated historical replay: simulate a real battle with real data.

    Body: { battle_key: "cdb90-387" | "curated-neptune-1944", universes?: int, seed?: int }
    Returns the fidelity report — counterfactuals require passed=true.
    """
    if not _load_chronos():
        return {"error": "Chronos not available"}
    battle_key = str(body.get("battle_key", ""))
    universes = min(int(body.get("universes", 400)), 5000)
    seed = body.get("seed", 42)

    def _run() -> dict[str, Any]:
        if battle_key.startswith("curated-"):
            battle = _load_curated_battle(battle_key, _CHRONOS_DB)
        else:
            try:
                isqno = int(battle_key.split("-", 1)[1])
            except (IndexError, ValueError):
                return {"error": "battle_key must look like 'cdb90-<isqno>' or 'curated-<slug>'"}
            battle = _load_battle(isqno, _CHRONOS_DB)
        if not battle:
            return {"error": f"unknown battle {battle_key}"}
        report = _fidelity_report(battle, universes=universes, seed=seed)
        report["battle"] = battle.to_dict()
        oob = _get_oob(battle_key, _CHRONOS_DB)
        if oob:
            report["oob"] = oob
        return report

    return await asyncio.to_thread(_run)


@app.post("/api/chronos/what-if")
async def chronos_what_if(body: dict[str, Any]) -> dict[str, Any]:
    """Counterfactual branch set — sandbox mode: runs on ANY battle.

    The fidelity gate is advisory metadata, not a blocker (user intent:
    Chronos is a strength-comparison sandbox, not a history-fidelity tool).

    Body: {
      battle_key: str,
      override: {"attacker_strength_mult"|"defender_strength_mult"|
                 "attacker_quality_add"|"defender_quality_add"|"terrain"} ,
      universes?: int, seed?: int, force?: bool   # deprecated no-op
    }
    """
    if not _load_chronos():
        return {"error": "Chronos not available"}
    battle_key = str(body.get("battle_key", ""))
    universes = min(int(body.get("universes", 400)), 5000)
    seed = body.get("seed", 42)
    override = body.get("override") or {}
    if not isinstance(override, dict) or len(override) != 1:
        return {"error": "override must be a dict with exactly one variable"}

    def _run() -> dict[str, Any]:
        if battle_key.startswith("curated-"):
            battle = _load_curated_battle(battle_key, _CHRONOS_DB)
        else:
            try:
                isqno = int(battle_key.split("-", 1)[1])
            except (IndexError, ValueError):
                return {"error": "battle_key must look like 'cdb90-<isqno>' or 'curated-<slug>'"}
            battle = _load_battle(isqno, _CHRONOS_DB)
        if not battle:
            return {"error": f"unknown battle {battle_key}"}
        rep = _fidelity_report(battle, universes=min(universes, 800), seed=seed)
        result = _what_if(battle, override, universes=universes, seed=seed)
        result["gate"] = "passed" if rep.get("passed") else "advisory"
        result["fidelity"] = {
            "passed": rep.get("passed", False),
            "predicted_winner": rep.get("predicted_winner"),
            "actual_winner": rep.get("actual_winner"),
            "winner_fidelity": rep.get("checks", {}).get("winner_fidelity"),
        }
        return result

    return await asyncio.to_thread(_run)


# ---------------------------------------------------------------------------
# Research / self-learning endpoints (Kriegspiel doctrine evolution)
# ---------------------------------------------------------------------------
# These surface what the engine has *learned* from its own simulations:
#   - /api/research/strategy-table  : doctrine × terrain win-rate matrix
#   - /api/research/findings        : latest distilled research findings
#   - /api/research/parameters      : current evolved doctrine parameters
#   - /api/research/dossier         : full append-only research log
#   - /api/research/improve         : trigger a self-improvement step
#
# The tracker is a process-wide singleton in engines.kriegspiel.learning.
# All endpoints are read-only except /improve (manual self-improve trigger).

def _research_tracker():
    """Lazy-import the tracker. Returns None if Kriegspiel isn't loaded."""
    if not _ks_available:
        return None
    try:
        from engines.kriegspiel.learning import get_tracker
        return get_tracker()
    except Exception as exc:
        logger.debug("Research tracker unavailable: %s", exc)
        return None


@app.get("/api/research/strategy-table")
async def research_strategy_table() -> dict[str, Any]:
    tracker = _research_tracker()
    if tracker is None:
        return {"error": "research layer unavailable", "doctrines": [], "terrains": [], "matrix": []}
    return tracker.strategy_table()


@app.get("/api/research/findings")
async def research_findings(k: int = 10) -> dict[str, Any]:
    tracker = _research_tracker()
    if tracker is None:
        return {"error": "research layer unavailable", "findings": []}
    k = max(1, min(int(k), 50))
    return {"findings": tracker.findings(k), "k": k}


@app.get("/api/research/parameters")
async def research_parameters() -> dict[str, Any]:
    tracker = _research_tracker()
    if tracker is None:
        return {"error": "research layer unavailable", "current": {}, "total_adjustments": 0}
    return tracker.parameters()


@app.get("/api/research/dossier")
async def research_dossier(k: int = 50) -> dict[str, Any]:
    tracker = _research_tracker()
    if tracker is None:
        return {"error": "research layer unavailable"}
    k = max(1, min(int(k), 200))
    return tracker.dossier(k)


@app.post("/api/research/improve")
async def research_improve() -> dict[str, Any]:
    """Manually trigger a self-improvement step. The background loop also
    auto-triggers every 20 batches; this endpoint lets a human force one."""
    tracker = _research_tracker()
    if tracker is None:
        return {"error": "research layer unavailable", "changes": []}
    changes = tracker.self_improve()
    return {
        "changes_applied": len(changes),
        "changes": [
            {
                "doctrine": c.doctrine, "terrain": c.terrain, "field": c.field,
                "before": c.before, "after": c.after, "win_rate": c.win_rate,
                "rationale": c.rationale,
                "p_value": c.p_value, "fdr_gate": c.fdr_gate,
            } for c in changes
        ],
    }


@app.get("/api/research/bh-gate")
async def research_bh_gate(k: int = 20) -> dict[str, Any]:
    """Multiple-testing gate audit trail: how many hypotheses were tested and
    how many survived Benjamini-Hochberg at each self-improvement step."""
    tracker = _research_tracker()
    if tracker is None:
        return {"error": "research layer unavailable"}
    k = max(1, min(int(k), 100))
    return tracker.bh_gate_history(k)


@app.get("/api/research/adherence")
async def research_adherence(
    terrain: str = "open",
    n: int = 60,
    seed: int = 42,
) -> dict[str, Any]:
    """Run a controlled doctrine-adherence probe: does each doctrine's declared
    parameter profile actually produce the expected battle behavior? Runs in a
    worker thread — each battle is cheap but N×doctrines add up."""
    if not _ks_available:
        return {"error": "Kriegspiel engine not available"}

    from engines.kriegspiel.models import TerrainType
    from engines.kriegspiel.adherence import run_adherence_probe

    try:
        terrain_enum = TerrainType(terrain)
    except ValueError:
        terrain_enum = TerrainType.OPEN

    n_per_doctrine = max(10, min(int(n), 500))
    seed_i = int(seed)

    def _run() -> dict[str, Any]:
        return run_adherence_probe(
            terrain=terrain_enum,
            n_per_doctrine=n_per_doctrine,
            seed=seed_i,
        )

    return await asyncio.to_thread(_run)


# ---------------------------------------------------------------------------
# Persona endpoints (MatrAIx-inspired population layer)
# ---------------------------------------------------------------------------
# The persona core (sims_core/persona) is the shared population model for the
# whole stack: a correlated categorical schema, a dependency-aware DAG sampler,
# and cohort queries. These endpoints expose it and let callers run Alpha Zero
# branches where every universe is a *different person* instead of one generic
# archetype branched N times.

@app.get("/api/persona/schema")
async def persona_schema() -> dict[str, Any]:
    from sims_core.persona import render_schema_summary
    return render_schema_summary()


@app.post("/api/persona/sample")
async def persona_sample(body: dict[str, Any]) -> dict[str, Any]:
    """Sample one persona from the dependency DAG."""
    from sims_core.persona import sample_persona, parse_query

    seed = body.get("seed", 42)
    query = parse_query(body.get("query"))
    try:
        persona = sample_persona(seed=seed, query=query)
    except ValueError as exc:
        return {"error": str(exc)}
    return persona.to_dict()


@app.post("/api/persona/cohort")
async def persona_cohort(body: dict[str, Any]) -> dict[str, Any]:
    """Sample a reproducible cohort of personas matching a population query."""
    from sims_core.persona import sample_cohort, personas_to_dicts, parse_query

    n = max(1, min(int(body.get("n", 100)), 10000))
    seed = body.get("seed", 42)
    try:
        query = parse_query(body.get("query"))
        personas = sample_cohort(n, seed=seed, query=query)
    except ValueError as exc:
        return {"error": str(exc)}
    return {
        "n": len(personas),
        "seed": seed,
        "query": query.to_dict(),
        "personas": personas_to_dicts(personas),
    }


@app.post("/api/persona/alpha-zero/run")
async def persona_alpha_zero_run(body: dict[str, Any]) -> dict[str, Any]:
    """Run Alpha Zero branches where each universe is a sampled persona.

    Each persona in the cohort becomes one independent life simulation through
    the Alpha Zero FSM — the 'run this decision against millions of people'
    promise made concrete with coherent, correlated people instead of the same
    archetype shuffled N times."""
    if not _az_available:
        return {"error": "Alpha Zero engine not available"}

    from sims_core.persona import sample_cohort, personas_to_dicts, parse_query
    from sims_core.persona.bridges.alpha_zero import run_persona_cohort

    n = max(1, min(int(body.get("n", 50)), 1000))
    seed = body.get("seed", 42)
    max_age = max(20, min(int(body.get("max_age", 100)), 120))
    try:
        query = parse_query(body.get("query"))
        personas = sample_cohort(n, seed=seed, query=query)
    except ValueError as exc:
        return {"error": str(exc)}

    def _run() -> dict[str, Any]:
        result = run_persona_cohort(personas, base_seed=seed, max_age=max_age)
        if result is None:
            return {"error": "Alpha Zero engine unavailable at runtime"}
        result["query"] = query.to_dict()
        result["seed"] = seed
        result["cohort_preview"] = personas_to_dicts(personas[:5])
        _add_count("alpha_zero", result.get("personas_simulated", 0))
        return result

    return await asyncio.to_thread(_run)


# ---------------------------------------------------------------------------
# CC endpoints
# ---------------------------------------------------------------------------

@app.post("/api/cc/run")
async def cc_run(body: dict[str, Any]) -> dict[str, Any]:
    if not _cc_available:
        return {"error": "CC engine not available"}
    n_scenarios = min(int(body.get("scenarios", 5000)), 50000)
    seed = body.get("seed", 42)
    persona_query = body.get("persona_query")
    persona_n = max(1, min(int(body.get("persona_n", 100)), 5000))

    def _run() -> dict[str, Any]:
        defense_quality = 1.0
        if persona_query is not None:
            from sims_core.persona.bridges.population_context import (
                sample_population_context, digital_defense_quality,
            )
            try:
                ctx = sample_population_context(
                    persona_query, n=persona_n, seed=seed, cohort_label="cc-affected",
                )
                defense_quality = digital_defense_quality(ctx)
            except ValueError as exc:
                ctx = {"error": str(exc)}
        # Engine-internal population effect: a low-fluency population hardens
        # slower, so the attack simulation itself becomes easier.
        report = _cc_generate(n_scenarios=n_scenarios, seed=seed,
                              defense_quality=defense_quality)
        d = _cc_report_to_dict(report)
        _add_count("cc", report.scenarios_run)
        if persona_query is not None:
            d["population_context"] = ctx
            d["population_modifiers"] = {"defense_quality": defense_quality}
        return d

    return await asyncio.to_thread(_run)


# ---------------------------------------------------------------------------
# Remnants endpoints
# ---------------------------------------------------------------------------

@app.post("/api/remnants/run")
async def rem_run(body: dict[str, Any]) -> dict[str, Any]:
    if not _rem_available:
        return {"error": "Remnants engine not available"}
    n_scenarios = min(int(body.get("scenarios", 5000)), 50000)
    intensity = float(body.get("intensity", 50))
    duration = float(body.get("duration_months", 12))
    seed = body.get("seed", 42)
    persona_query = body.get("persona_query")
    persona_n = max(1, min(int(body.get("persona_n", 100)), 5000))

    condition = _rem_conflict(
        intensity=intensity,
        duration_months=duration,
        infrastructure_damage=min(intensity * 0.9, 100),
        population_displacement=min(intensity * 0.5, 100),
        supply_disruption=min(intensity * 0.8, 100),
        cultural_destruction=min(intensity * 0.3, 100),
    )

    def _run() -> dict[str, Any]:
        population_resilience = 1.0
        if persona_query is not None:
            from sims_core.persona.bridges.population_context import (
                sample_population_context, population_resilience as _pop_res,
            )
            try:
                ctx = sample_population_context(
                    persona_query, n=persona_n, seed=seed, cohort_label="remnants-affected",
                )
                population_resilience = _pop_res(ctx)
            except ValueError as exc:
                ctx = {"error": str(exc)}
        # Engine-internal population effect: a fragile population cannot sustain
        # institutions / supply chains through the crisis.
        report = _rem_generate(n_scenarios=n_scenarios, condition=condition,
                               seed=seed, population_resilience=population_resilience)
        d = _rem_report_to_dict(report)
        _add_count("remnants", report.scenarios_run)
        if persona_query is not None:
            d["population_context"] = ctx
            d["population_modifiers"] = {"population_resilience": population_resilience}
        return d

    return await asyncio.to_thread(_run)


# ---------------------------------------------------------------------------
# Awareness endpoints
# ---------------------------------------------------------------------------

@app.get("/api/awareness/threats")
async def aw_threats() -> list[dict[str, Any]]:
    if not _aw_available or not _aw_threats:
        return []
    return [
        {
            "name": t.name,
            "type": t.threat_type.value,
            "severity": t.severity.value,
            "affected_assets": t.affected_assets,
            "origin": t.origin,
            "urgency": round(t.urgency_score, 1),
        }
        for t in _aw_threats
    ]


@app.post("/api/awareness/run")
async def aw_run(body: dict[str, Any]) -> dict[str, Any]:
    if not _aw_available:
        return {"error": "Awareness engine not available"}
    threat_idx = int(body.get("threat_index", 0))
    n_scenarios = min(int(body.get("scenarios", 5000)), 50000)
    seed = body.get("seed", 42)
    persona_query = body.get("persona_query")
    persona_n = max(1, min(int(body.get("persona_n", 100)), 5000))

    threat = None
    if _aw_threats and 0 <= threat_idx < len(_aw_threats):
        threat = _aw_threats[threat_idx]

    def _run() -> dict[str, Any]:
        population_reach = 1.0
        if persona_query is not None:
            from sims_core.persona.bridges.population_context import (
                sample_population_context, population_reach as _pop_reach,
            )
            try:
                ctx = sample_population_context(
                    persona_query, n=persona_n, seed=seed, cohort_label="awareness-affected",
                )
                population_reach = _pop_reach(ctx)
            except ValueError as exc:
                ctx = {"error": str(exc)}
        # Engine-internal population effect: a hard-to-reach population makes
        # response actions land less often.
        report = _aw_generate(threat=threat, n_scenarios=n_scenarios, seed=seed,
                              population_reach=population_reach)
        d = _aw_report_to_dict(report)
        _add_count("awareness", report.scenarios_run)
        if persona_query is not None:
            d["population_context"] = ctx
            d["population_modifiers"] = {"population_reach": population_reach}
        return d

    return await asyncio.to_thread(_run)


# ---------------------------------------------------------------------------
# Platoon endpoints
# ---------------------------------------------------------------------------

@app.get("/api/platoon/objectives")
async def pl_objectives() -> list[dict[str, Any]]:
    if not _pl_available or not _pl_objectives:
        return []
    return [
        {
            "title": o.title,
            "domain": o.domain.value,
            "goal": o.goal,
            "constraints": o.constraints,
            "success_criteria": o.success_criteria,
            "risk_tolerance": o.risk_tolerance.value,
            "complexity": round(o.complexity, 1),
        }
        for o in _pl_objectives
    ]


@app.post("/api/platoon/run")
async def pl_run(body: dict[str, Any]) -> dict[str, Any]:
    if not _pl_available:
        return {"error": "Platoon engine not available"}
    obj_idx = int(body.get("objective_index", 0))
    n_scenarios = min(int(body.get("scenarios", 5000)), 50000)
    seed = body.get("seed", 42)

    objective = None
    if _pl_objectives and 0 <= obj_idx < len(_pl_objectives):
        objective = _pl_objectives[obj_idx]

    def _run() -> dict[str, Any]:
        d = _pl_generate(objective=objective, n_scenarios=n_scenarios, seed=seed)
        _add_count("platoon", d["scenarios_run"])
        return d

    return await asyncio.to_thread(_run)


@app.post("/api/platoon/extract")
async def pl_extract(body: dict[str, Any]) -> dict[str, Any]:
    """Treiver-style objective extraction: convert a free-text client brief
    into a structured Objective. Offline regex stage is always run; the LLM
    judge stage is opt-in via ``use_llm`` and falls back to the deterministic
    result on any provider/validation failure."""
    text = (body.get("text") or "").strip()
    if not text:
        return {"error": "no text provided", "code": 400}
    if len(text) > 8000:
        return {"error": "text too long (max 8000 chars)", "code": 400}
    use_llm = bool(body.get("use_llm", False))

    from engines.platoon.extraction import extract_objective

    def _run() -> dict[str, Any]:
        result = extract_objective(text, use_llm=use_llm)
        objective = result.to_objective()
        return {
            "extraction": result.to_dict(),
            "objective": {
                "title": objective.title,
                "domain": objective.domain.value,
                "goal": objective.goal,
                "constraints": objective.constraints,
                "success_criteria": objective.success_criteria,
                "risk_tolerance": objective.risk_tolerance.value,
                "time_horizon_years": objective.time_horizon_years,
                "population_scale": objective.population_scale,
                "confidence_required": objective.confidence_required,
                "complexity": round(objective.complexity, 1),
            },
        }

    return await asyncio.to_thread(_run)


# ---------------------------------------------------------------------------
# TDAC endpoints
# ---------------------------------------------------------------------------

@app.get("/api/tdac/sources")
async def td_sources() -> list[dict[str, Any]]:
    if not _td_available or not _td_sources:
        return []
    return [
        {
            "engine": s.engine,
            "title": s.title,
            "key_finding": s.key_finding,
            "stakes": s.stakes,
        }
        for s in _td_sources
    ]


@app.post("/api/tdac/run")
async def td_run(body: dict[str, Any]) -> dict[str, Any]:
    if not _td_available:
        return {"error": "TDAC engine not available"}
    src_idx = int(body.get("source_index", 0))
    n_scenarios = min(int(body.get("scenarios", 5000)), 50000)
    seed = body.get("seed", 42)

    source = None
    if _td_sources and 0 <= src_idx < len(_td_sources):
        source = _td_sources[src_idx]

    def _run() -> dict[str, Any]:
        d = _td_generate(source=source, n_scenarios=n_scenarios, seed=seed)
        _add_count("tdac", d["scenarios_run"])
        return d

    return await asyncio.to_thread(_run)


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("ALIEN_SIMS_PORT", "8090"))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
