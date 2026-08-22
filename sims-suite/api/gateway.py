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
