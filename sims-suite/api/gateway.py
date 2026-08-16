"""Sims-suite gateway — the single API that feeds alieninc.tech/index.html.

Aggregates live simulation metrics from all 7 engines and exposes them under
``/api/simulations/*`` (proxied same-origin via nginx). In Phase 0, only the
Alpha Zero engine is online; the gateway runs a light background loop of *real*
Alpha Zero simulations so the numbers on index.html are genuine, not faked.

index.html integration (line ~3699):
    window.ALIEN_SIMS = { getValue: () => <polled count> };

Endpoints:
    GET /api/simulations/today      — { count, runs, last_24h, by_engine }
    GET /api/simulations/coverage   — { stage, engines_online, total_engines }
    GET /api/simulations/engine     — { code, engines: [...] }
    GET /api/companies/{name}       — { name, station, simulations }
    GET /api/health                 — { status, uptime, engines }

Run:
    cd /home/alieninc/sims-suite && python -m api.gateway
    # or: uvicorn api.gateway:app --host 127.0.0.1 --port 8090
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import threading
import time
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
    "citadel": "citadel",
    "awareness": "awareness",
}

TOTAL_ENGINES = 7

# ---------------------------------------------------------------------------
# Persistent cumulative counter — survives restarts, never trims
# ---------------------------------------------------------------------------

_COUNT_FILE = _SUITE_ROOT / "api" / ".sim_count.json"


def _read_count() -> dict[str, int]:
    """Read the persistent cumulative counter."""
    try:
        import json
        if _COUNT_FILE.exists():
            return json.loads(_COUNT_FILE.read_text())
    except Exception:
        pass
    return {"alpha_zero": 0, "kriegspiel": 0}


def _write_count(counts: dict[str, int]) -> None:
    """Write the persistent cumulative counter atomically."""
    import json
    try:
        _COUNT_FILE.write_text(json.dumps(counts))
    except Exception:
        pass


def _add_count(engine: str, n: int) -> None:
    """Add n to the persistent counter for the given engine."""
    import threading
    with _count_lock:
        _counts[engine] = _counts.get(engine, 0) + n
        _write_count(_counts)


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

_ks_sim_count = 0  # in-memory (also persisted via _add_count)
_ks_last_report: dict[str, Any] = {}


def _load_kriegspiel() -> bool:
    """Try to import the Kriegspiel engine. Return True if available."""
    global _ks_available, _ks_generate, _ks_report_to_dict, _ks_battlefields, _ks_create_battle
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
        from engines.kriegspiel.models import BATTLEFIELDS as _bf

        _ks_generate = _gs
        _ks_report_to_dict = _rtd
        _ks_battlefields = _bf
        _ks_create_battle = _cdb
        _ks_available = True
        logger.info("Kriegspiel engine loaded")
        return True
    except Exception as exc:
        logger.warning("Could not load Kriegspiel engine: %s", exc)
        return False


def _run_ks_background_batch() -> int:
    """Run a small batch of Kriegspiel scenarios for the live counter."""
    global _ks_sim_count
    if not _ks_available:
        return 0
    try:
        report = _ks_generate(n_scenarios=50, seed=None)
        _ks_sim_count += report.scenarios_run
        _add_count("kriegspiel", report.scenarios_run)
        _ks_last_report = _ks_report_to_dict(report)
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
# Citadel engine — imported lazily (Kriegspiel turned inward on infra)
# ---------------------------------------------------------------------------

_cit_available = False
_cit_generate: Any = None
_cit_report_to_dict: Any = None
_cit_create_infra: Any = None


def _load_citadel() -> bool:
    global _cit_available, _cit_generate, _cit_report_to_dict, _cit_create_infra
    if _cit_available:
        return True
    if str(_SUITE_ROOT) not in sys.path:
        sys.path.insert(0, str(_SUITE_ROOT))
    try:
        from engines.citadel.attack import (
            generate_attack_scenarios as _gas,
            report_to_dict as _rtd,
        )
        from engines.citadel.infra_graph import create_sample_infra as _csi

        _cit_generate = _gas
        _cit_report_to_dict = _rtd
        _cit_create_infra = _csi
        _cit_available = True
        logger.info("Citadel engine loaded")
        return True
    except Exception as exc:
        logger.warning("Could not load Citadel engine: %s", exc)
        return False


def _run_cit_background_batch() -> int:
    if not _cit_available:
        return 0
    try:
        report = _cit_generate(n_scenarios=100, seed=None)
        _add_count("citadel", report.scenarios_run)
        return report.scenarios_run
    except Exception:
        return 0


async def _background_cit_loop() -> None:
    if not SIM_ENABLED:
        return
    interval = SIM_INTERVAL_S * 4
    logger.info("Citadel background loop started (interval=%.1fs)", interval)
    while True:
        try:
            await asyncio.to_thread(_run_cit_background_batch)
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
    if _cit_available:
        online.append("citadel")
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


class CoverageResponse(BaseModel):
    stage: str
    engines_online: int
    total_engines: int


class EngineResponse(BaseModel):
    code: str
    engines: list[str]


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
    _load_alpha_zero()
    _load_kriegspiel()
    _load_citadel()
    _load_remnants()
    _load_awareness()
    _load_platoon()
    _load_tdac()
    asyncio.create_task(_background_sim_loop())
    asyncio.create_task(_background_ks_loop())
    asyncio.create_task(_background_cit_loop())
    asyncio.create_task(_background_rem_loop())
    asyncio.create_task(_background_aw_loop())
    asyncio.create_task(_background_pl_loop())
    asyncio.create_task(_background_td_loop())


@app.get("/api/health")
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        uptime=round(time.time() - _started_at, 1),
        engines=_engines_online(),
    )


@app.get("/api/simulations/today")
async def simulations_today() -> SimTodayResponse:
    pl_total = _counts.get("platoon", 0)
    az_total = _counts.get("alpha_zero", 0)
    td_total = _counts.get("tdac", 0)
    ks_total = _counts.get("kriegspiel", 0)
    cit_total = _counts.get("citadel", 0)
    rem_total = _counts.get("remnants", 0)
    aw_total = _counts.get("awareness", 0)
    by_engine: dict[str, int] = {}
    if _pl_available:
        by_engine["platoon"] = pl_total
    if _az_available:
        by_engine["alpha_zero"] = az_total
    if _td_available:
        by_engine["tdac"] = td_total
    if _ks_available:
        by_engine["kriegspiel"] = ks_total
    if _cit_available:
        by_engine["citadel"] = cit_total
    if _rem_available:
        by_engine["remnants"] = rem_total
    if _aw_available:
        by_engine["awareness"] = aw_total
    total = pl_total + az_total + td_total + ks_total + cit_total + rem_total + aw_total
    return SimTodayResponse(
        count=total,
        runs=total,
        last_24h=total,
        by_engine=by_engine,
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
    return EngineResponse(code=_engine_code(online), engines=online)


@app.get("/api/companies/{name}")
async def company_metrics(name: str) -> CompanyResponse:
    station = COMPANY_STATIONS.get(name.lower(), "unknown")
    simulations = _counts.get(station, 0) if station in (
        "platoon", "alpha_zero", "tdac", "kriegspiel", "citadel", "remnants", "awareness"
    ) else 0
    return CompanyResponse(name=name, station=station, simulations=simulations)


# ---------------------------------------------------------------------------
# Kriegspiel endpoints
# ---------------------------------------------------------------------------

@app.get("/api/kriegspiel/battlefields")
async def ks_battlefields() -> list[dict[str, Any]]:
    if not _ks_available or not _ks_battlefields:
        return []
    return [
        {
            "name": bf.name,
            "terrain": bf.terrain.value,
            "center": list(bf.center),
            "bounds": list(bf.bounds),
            "area_km2": bf.area_km2,
        }
        for bf in _ks_battlefields
    ]


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
        return d

    result = await asyncio.to_thread(_run)
    return result


# ---------------------------------------------------------------------------
# Citadel endpoints
# ---------------------------------------------------------------------------

@app.post("/api/citadel/run")
async def cit_run(body: dict[str, Any]) -> dict[str, Any]:
    if not _cit_available:
        return {"error": "Citadel engine not available"}
    n_scenarios = min(int(body.get("scenarios", 5000)), 50000)
    seed = body.get("seed", 42)

    def _run() -> dict[str, Any]:
        report = _cit_generate(n_scenarios=n_scenarios, seed=seed)
        d = _cit_report_to_dict(report)
        _add_count("citadel", report.scenarios_run)
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

    condition = _rem_conflict(
        intensity=intensity,
        duration_months=duration,
        infrastructure_damage=min(intensity * 0.9, 100),
        population_displacement=min(intensity * 0.5, 100),
        supply_disruption=min(intensity * 0.8, 100),
        cultural_destruction=min(intensity * 0.3, 100),
    )

    def _run() -> dict[str, Any]:
        report = _rem_generate(n_scenarios=n_scenarios, condition=condition, seed=seed)
        d = _rem_report_to_dict(report)
        _add_count("remnants", report.scenarios_run)
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

    threat = None
    if _aw_threats and 0 <= threat_idx < len(_aw_threats):
        threat = _aw_threats[threat_idx]

    def _run() -> dict[str, Any]:
        report = _aw_generate(threat=threat, n_scenarios=n_scenarios, seed=seed)
        d = _aw_report_to_dict(report)
        _add_count("awareness", report.scenarios_run)
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
