"""
Aviation Domain router for the Spinal Cracker / Panteon admin panel.

Exposes the OpenSky Network aviation pull -> classification -> OSv2 writeback
pipeline as endpoints under `/api/v1/opensky/...`.  These reuse the connector
module (magritte_connector_opensky) and the OSv2 / WritebackService from
action_writeback_service, mirroring the GDELT router architecture but adapted
for real-time aircraft state vectors.

The pipeline runs in-process: the OSv2 manager / ontology graph are module-level
singletons so snapshots persist across requests in the same process.

OpenSky Network integration sourced from osiris
(https://github.com/simplifaisoul/osiris) — the flight classification engine
that splits 13K+ aircraft into commercial / private / jet / military / GPS-jamming
suspects based on callsign, ADS-B emitter category, and cruise profile.
"""

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from action_writeback_service import (  # noqa: E402
    AviationWritebackPipeline,
    OntologyGraph,
    OSv2Manager,
)
from magritte_connector_opensky import (  # noqa: E402
    OpenSkyConfig,
    OpenSkyConnector,
    OpenSkyConnectorFactory,
    StagingDataset,
)

logger = logging.getLogger("spinal_cracker.opensky_router")

router = APIRouter(
    prefix="/opensky",
    tags=["Spinal Cracker Aviation"],
)


class PipelineConfig(BaseModel):
    """User-overridable OpenSky Network query parameters."""
    client_id: str = Field(
        default="",
        description="OpenSky OAuth2 client ID (optional — anonymous pool is IP-limited).",
    )
    client_secret: str = Field(
        default="",
        description="OpenSky OAuth2 client secret (optional).",
    )
    fetch_military: bool = Field(
        default=True,
        description="Also pull the adsb.fi military aircraft feed.",
    )
    request_timeout: int = Field(default=30, ge=1, le=120)
    max_retries: int = Field(default=5, ge=0, le=10)
    # Optional bounding box to scope the OpenSky states/all pull.
    # None = global. When all four are set, only aircraft within the box are requested.
    lamin: float | None = Field(default=None, description="Min latitude of bbox scope.")
    lomin: float | None = Field(default=None, description="Min longitude of bbox scope.")
    lamax: float | None = Field(default=None, description="Max latitude of bbox scope.")
    lomax: float | None = Field(default=None, description="Max longitude of bbox scope.")


# ---------------------------------------------------------------------------
# Persistence — the OSv2 manager is in-memory, so aviation_flight nodes would
# be lost on every service restart (the map would start blank). We persist the
# object nodes to a JSON file after each successful run and reload on startup,
# mirroring the GKG store pattern. Flights are transient state vectors, so each
# run REPLACES the aviation_flight nodes (stale positions don't accumulate).
# ---------------------------------------------------------------------------
_STORE_PATH = os.path.join(BACKEND_DIR, "panteon", "api", "opensky_osv2_store.json")

# Persisted rate gate — OpenSky's anonymous pool is IP-limited (~1 req/15min).
# The connector enforces this per-instance, but a fresh connector is built every
# run, so the interval would reset each call. This module-level gate (persisted)
# enforces the anonymous interval ACROSS runs and restarts.
_GATE_PATH = os.path.join(BACKEND_DIR, "panteon", "api", "opensky_rate_state.json")
_ANON_INTERVAL_S = float(os.environ.get("OPENSKY_ANON_INTERVAL_S", "900"))  # 15 min


def _load_store() -> dict:
    if not os.path.exists(_STORE_PATH):
        return {}
    try:
        with open(_STORE_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        logger.warning("opensky_osv2_store.json unreadable; starting with empty store")
        return {}


def _save_store(nodes: dict) -> None:
    try:
        os.makedirs(os.path.dirname(_STORE_PATH), exist_ok=True)
        tmp = _STORE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(nodes, fh, default=str)
        os.replace(tmp, _STORE_PATH)
    except OSError as exc:
        logger.warning("Could not persist OpenSky OSv2 store: %s", exc)


def _load_gate() -> dict:
    try:
        with open(_GATE_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {"last_pull_ts": 0.0, "cooldown_until": 0.0, "total_pulls": 0}


def _save_gate(state: dict) -> None:
    try:
        os.makedirs(os.path.dirname(_GATE_PATH), exist_ok=True)
        tmp = _GATE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(state, fh)
        os.replace(tmp, _GATE_PATH)
    except OSError as exc:
        logger.warning("Could not persist OpenSky rate state: %s", exc)


_gate_state = _load_gate()


def get_opensky_rate_state() -> dict:
    """Snapshot of the OpenSky rate gate for the admin UI."""
    now = time.time()
    anon_left = max(0.0, _ANON_INTERVAL_S - (now - _gate_state["last_pull_ts"]))
    cool_left = max(0.0, _gate_state["cooldown_until"] - now)
    return {
        "total_pulls": _gate_state["total_pulls"],
        "anon_interval_s": _ANON_INTERVAL_S,
        "anon_seconds_left": anon_left,
        "can_pull_now": anon_left <= 0 and cool_left <= 0,
        "cooldown_until": _gate_state["cooldown_until"],
        "cooldown_active": _gate_state["cooldown_until"] > now,
        "cooldown_seconds_left": cool_left,
    }


def reset_opensky_cooldown() -> None:
    _gate_state["cooldown_until"] = 0.0
    _gate_state["last_pull_ts"] = 0.0
    _save_gate(_gate_state)


def _gate_acquire(block: bool = True) -> float:
    """Return wait seconds, or 0 if a pull may proceed. Raises if over-limit.

    Enforces the anonymous interval across runs (persisted). If ``block`` is
    False, returns the wait time instead of sleeping (used by validate/probe).
    """
    now = time.time()
    anon_left = _ANON_INTERVAL_S - (now - _gate_state["last_pull_ts"])
    cool_left = _gate_state["cooldown_until"] - now
    wait = max(anon_left, cool_left)
    if wait <= 0:
        return 0.0
    if not block:
        return wait
    return wait


def _gate_mark_pull() -> None:
    _gate_state["last_pull_ts"] = time.time()
    _gate_state["total_pulls"] += 1
    _save_gate(_gate_state)


def _gate_enter_cooldown(seconds: float = 900.0) -> None:
    _gate_state["cooldown_until"] = time.time() + seconds
    _save_gate(_gate_state)


def _build_pipeline() -> tuple[OSv2Manager, OntologyGraph, AviationWritebackPipeline]:
    """Initialise the in-memory OSv2 store + ontology graph (module-level singletons)."""
    osv2 = getattr(_build_pipeline, "_osv2", None)
    if osv2 is None:
        osv2 = OSv2Manager()
        osv2.register_object_type("aviation_flight", {
            "name": "aviation_flight",
            "display_name": "Aviation Flight",
            "description": "OpenSky Network tracked aircraft state vector",
            "fields": [
                "icao24", "callsign", "lat", "lng", "alt", "heading",
                "speed_knots", "model", "registration", "squawk",
                "airline_code", "aircraft_category", "category",
                "grounded", "nac_p",
            ],
            "required_fields": ["icao24"],
            "relationships": ["FLIGHT_TRACKED_IN_AIRSPACE"],
        })
        osv2.register_object_type("aviation_airport", {
            "name": "aviation_airport",
            "display_name": "Aviation Airport",
            "description": "Airport reference node",
            "fields": ["icao_code", "name", "lat", "lon", "country"],
            "required_fields": ["icao_code"],
            "relationships": [],
        })
        osv2.register_link_type("FLIGHT_TRACKED_IN_AIRSPACE", {
            "name": "FLIGHT_TRACKED_IN_AIRSPACE",
            "description": "Link from flight to airspace region via position",
            "target_type": "aviation_airspace",
        })
        persisted = _load_store()
        if persisted:
            osv2._object_nodes.update(persisted)  # noqa: SLF001
            logger.info("Loaded %d persisted aviation objects from store", len(persisted))
        _build_pipeline._osv2 = osv2  # noqa: SLF001

    ontology = getattr(_build_pipeline, "_ontology", None)
    if ontology is None:
        ontology = OntologyGraph()
        _build_pipeline._ontology = ontology  # noqa: SLF001

    pipeline = AviationWritebackPipeline(osv2=osv2, object_storage={}, ontology_graph=ontology)
    return osv2, ontology, pipeline


async def _run_pipeline(config: PipelineConfig) -> dict:
    """Execute OpenSky pull -> classify -> writeback and return the report dict.

    Enforces the persisted anonymous-interval gate (OpenSky anon ~1 req/15min),
    REPLACES stale aviation_flight nodes with the fresh snapshot (flights are
    transient state vectors, not historical records), and persists the store so
    the map is non-blank after a restart.
    """
    # Gate: enforce the anonymous interval across runs/restarts.
    wait = _gate_acquire(block=False)
    if wait > 0:
        return {
            "phase": "failed",
            "error": f"OpenSky anonymous interval not elapsed — wait {int(wait)}s.",
            "error_kind": "rate_limited",
            "wait_s": wait,
        }

    osv2, ontology, writeback_pipeline = _build_pipeline()

    osconfig = OpenSkyConfig(
        client_id=config.client_id,
        client_secret=config.client_secret,
        fetch_military=config.fetch_military,
        request_timeout=config.request_timeout,
        max_retries=config.max_retries,
        lamin=config.lamin,
        lomin=config.lomin,
        lamax=config.lamax,
        lomax=config.lomax,
    )
    staging = StagingDataset(path="/tmp/opensky_staging.jsonl")

    session = await OpenSkyConnectorFactory.create_session()
    connector = OpenSkyConnector(config=osconfig, staging=staging, aiohttp_session=session)

    report: dict = {"phase": "pending"}
    try:
        classified = await connector.execute()
        _gate_mark_pull()

        # Flights are transient state vectors: clear stale aviation_flight nodes
        # before writeback so the store reflects the LATEST snapshot (no unbounded
        # accumulation of dead aircraft). aviation_airport nodes are kept.
        stale_guids = [
            g for g, n in osv2._object_nodes.items()  # noqa: SLF001
            if n.get("type") == "aviation_flight"
        ]
        for g in stale_guids:
            osv2._object_nodes.pop(g, None)  # noqa: SLF001

        # Writeback classified flights to OSv2
        result, _ = await writeback_pipeline.process_aviation_flights(classified)

        # Persist the fresh snapshot so the map is non-blank after restart.
        _save_store(osv2._object_nodes)  # noqa: SLF001

        # Build final report
        report = {
            "phase": "complete",
            "opensky": {
                "total": classified.get("total", 0),
                "source": classified.get("source", "unknown"),
                "providers": classified.get("providers", {}),
                "gps_jamming": classified.get("gps_jamming", []),
            },
            "classification": {
                "commercial": len(classified.get("commercial_flights", [])),
                "private": len(classified.get("private_flights", [])),
                "private_jets": len(classified.get("private_jets", [])),
                "military": len(classified.get("military_flights", [])),
                "gps_jamming_count": len(classified.get("gps_jamming", [])),
            },
            "writeback": {
                "success_count": result.success_count,
                "failure_count": result.failure_count,
                "transaction_id": result.transaction_id,
            },
            "ontology": {
                "object_type_count": len(osv2._type_definitions),  # noqa: SLF001
                "link_type_count": len(osv2._link_definitions),  # noqa: SLF001
            },
            "timestamp": classified.get("timestamp"),
            "rate": get_opensky_rate_state(),
        }
        logger.info("OpenSky pipeline run complete: %s", report)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Pipeline failed: %s", exc)
        _gate_enter_cooldown()
        report = {
            "phase": "failed",
            "error": str(exc),
            "error_kind": "generic",
            "rate": get_opensky_rate_state(),
        }
    finally:
        await OpenSkyConnectorFactory.reset_session()

    return report


_run_state: dict = {
    "status": "idle",
    "started_at": None,
    "finished_at": None,
    "report": None,
    "error": None,
}


async def _run_pipeline_bg(config: PipelineConfig) -> dict:
    """Run the OpenSky pipeline in the background and publish state for polling.

    OpenSky pulls (especially the adsb.fi regional fallback sweep) can take well
    over a minute, which exceeds reverse-proxy read timeouts. Running in the
    background with a status endpoint avoids HTTP 504s — the admin UI polls.
    """
    global _run_state
    _run_state = {
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
        "report": None,
        "error": None,
    }
    try:
        report = await _run_pipeline(config)
        _run_state["report"] = report
        _run_state["status"] = "complete" if report.get("phase") == "complete" else "failed"
        if report.get("phase") != "complete":
            _run_state["error"] = report.get("error") or "pipeline failed"
    except Exception as exc:  # noqa: BLE001
        logger.exception("OpenSky background pipeline crashed: %s", exc)
        _run_state["status"] = "failed"
        _run_state["error"] = str(exc)
    _run_state["finished_at"] = datetime.now(timezone.utc).isoformat()
    return _run_state


@router.get("/health")
async def health_check():
    return {"status": "ok", "source": "panteon spinal-cracker opensky"}


@router.post("/pipeline/run")
async def run_pipeline(payload: PipelineConfig = None, background_tasks: BackgroundTasks = None):
    """Run the OpenSky pipeline as a background task; poll /pipeline/status.

    Verification-first: the persisted anonymous-interval gate is checked BEFORE
    scheduling the job. If OpenSky is not due for a pull yet, the request is
    rejected immediately (no job started) with the wait time, so the admin UI
    can show a countdown instead of a hanging 504.
    """
    if _run_state.get("status") == "running":
        return JSONResponse(
            content={"status": "already_running", "state": _run_state}, status_code=200
        )
    config = payload or PipelineConfig()
    wait = _gate_acquire(block=False)
    if wait > 0:
        return JSONResponse(
            content={
                "status": "rejected",
                "error_kind": "rate_limited",
                "message": f"OpenSky anonymous interval not elapsed — wait {int(wait)}s.",
                "wait_s": wait,
                "rate": get_opensky_rate_state(),
            },
            status_code=200,
        )
    if background_tasks is not None:
        background_tasks.add_task(_run_pipeline_bg, config)
    else:
        await _run_pipeline_bg(config)
    return JSONResponse(content={"status": "started", "state": _run_state}, status_code=202)


@router.get("/pipeline/status")
async def pipeline_status():
    """Return the current background pipeline run state (idle/running/complete/failed)."""
    return JSONResponse(content=_run_state, status_code=200)


@router.get("/pipeline/rate")
async def pipeline_rate():
    """OpenSky rate-gate snapshot: anonymous interval, cooldown, total pulls."""
    return JSONResponse(content=get_opensky_rate_state(), status_code=200)


@router.post("/pipeline/cooldown/reset")
async def pipeline_cooldown_reset():
    """Admin escape hatch: clear the OpenSky anonymous-interval gate + cooldown."""
    reset_opensky_cooldown()
    return JSONResponse(content=get_opensky_rate_state(), status_code=200)


@router.get("/ontology/snapshot")
async def ontology_snapshot():
    _, _, pipeline = _build_pipeline()
    return JSONResponse(content=pipeline.get_ontology_snapshot(), status_code=200)


@router.get("/objects")
async def list_objects(limit: int = 100):
    osv2, _, _ = _build_pipeline()
    objs = osv2.get_all_objects()
    flights = [o for o in objs if o.get("type") == "aviation_flight"]
    return JSONResponse(
        content={"flights": flights[-limit:], "count": len(flights)},
        status_code=200,
    )



@router.get("/flights")
async def list_flights(
    limit: int = 100, category: str = None
):
    """List classified flights, optionally filtered by category.

    Categories: commercial, private, jet, military.
    """
    osv2, _, _ = _build_pipeline()
    objs = osv2.get_all_objects()
    flights = [o for o in objs if o.get("type") == "aviation_flight"]
    if category:
        flights = [
            f for f in flights
            if f.get("properties", {}).get("category") == category
        ]
    return JSONResponse(
        content={"flights": flights[-limit:], "count": len(flights)},
        status_code=200,
    )
