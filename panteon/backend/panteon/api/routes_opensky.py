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

import aiohttp
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
# mirroring the GKG store pattern. Flight nodes are MERGED per icao24 (fresh
# positions overwrite stale ones) and dead tracks are pruned by last_seen age,
# so sparse OpenSky pulls no longer wipe coverage between refreshes.
# ---------------------------------------------------------------------------
_STORE_PATH = os.path.join(BACKEND_DIR, "panteon", "api", "opensky_osv2_store.json")

# Persisted rate gate — two independent cadences:
#   * adsb.fi (no auth, ~5s data age): safe to pull every ADSB_INTERVAL_S.
#   * OpenSky anonymous pool is IP-limited (~1 req/15min); authenticated drops
#     that to 90s. The gate enforces the OpenSky interval ACROSS runs/restarts.
_GATE_PATH = os.path.join(BACKEND_DIR, "panteon", "api", "opensky_rate_state.json")
_ANON_INTERVAL_S = float(os.environ.get("OPENSKY_ANON_INTERVAL_S", "900"))  # 15 min
_ADSB_INTERVAL_S = float(os.environ.get("OPENSKY_ADSB_INTERVAL_S", "30"))

# Track history — ring buffer of fixes per icao24, persisted so the frontend can
# draw Maven-style trails and the follow-camera without any extra pulls.
_HISTORY_PATH = os.path.join(BACKEND_DIR, "panteon", "api", "opensky_track_history.json")
TRACK_MAX_FIXES = int(os.environ.get("OPENSKY_TRACK_MAX_FIXES", "40"))
TRACK_FIX_TTL_S = float(os.environ.get("OPENSKY_TRACK_TTL_S", str(3 * 3600)))      # drop fixes older than 3h
TRACK_PRUNE_S = float(os.environ.get("OPENSKY_TRACK_PRUNE_S", str(6 * 3600)))      # prune aircraft unseen 6h
FLIGHT_STALE_REMOVE_S = float(os.environ.get("OPENSKY_FLIGHT_STALE_S", str(2700))) # dead track removal from OSv2 store

# adsbdb.com callsign -> route (origin/destination airport) cache. Routes are
# static, so positives cache for a week; negatives for half a day.
_ROUTE_CACHE_PATH = os.path.join(BACKEND_DIR, "panteon", "api", "opensky_route_cache.json")
_ROUTE_TTL_POS_S = 7 * 86400
_ROUTE_TTL_NEG_S = 12 * 3600
_ADSBDB_URL = "https://api.adsbdb.com/v0/callsign/"


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
        return {
            "last_pull_ts": 0.0,
            "last_adsb_pull_ts": 0.0,
            "cooldown_until": 0.0,
            "total_pulls": 0,
            "last_success_ts": None,
            "last_source": None,
            "last_providers": None,
        }


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
    """Snapshot of both feed gates + last-pull freshness for the admin UI."""
    now = time.time()
    adsb_left = max(0.0, _ADSB_INTERVAL_S - (now - _gate_state.get("last_adsb_pull_ts", 0.0)))
    opensky_left = max(0.0, _ANON_INTERVAL_S - (now - _gate_state["last_pull_ts"]))
    cool_left = max(0.0, _gate_state["cooldown_until"] - now)
    success_ts = _gate_state.get("last_success_ts")
    return {
        "total_pulls": _gate_state["total_pulls"],
        # adsb.fi fast lane
        "adsb_interval_s": _ADSB_INTERVAL_S,
        "adsb_seconds_left": adsb_left,
        "can_pull_adsb_now": adsb_left <= 0 and cool_left <= 0,
        # OpenSky enrichment lane
        "anon_interval_s": _ANON_INTERVAL_S,
        "anon_seconds_left": opensky_left,
        "opensky_seconds_left": opensky_left,
        "can_pull_now": opensky_left <= 0 and cool_left <= 0,
        "cooldown_until": _gate_state["cooldown_until"],
        "cooldown_active": _gate_state["cooldown_until"] > now,
        "cooldown_seconds_left": cool_left,
        # freshness of the served snapshot
        "last_success_ts": success_ts,
        "data_age_s": (now - success_ts) if success_ts else None,
        "last_source": _gate_state.get("last_source"),
        "last_providers": _gate_state.get("last_providers"),
    }


def reset_opensky_cooldown() -> None:
    _gate_state["cooldown_until"] = 0.0
    _gate_state["last_pull_ts"] = 0.0
    _gate_state["last_adsb_pull_ts"] = 0.0
    _save_gate(_gate_state)


def _gate_acquire(block: bool = True) -> tuple[float, float]:
    """Return ``(adsb_wait_s, opensky_wait_s)``.

    An adsb.fi pull may proceed when ``adsb_wait_s == 0``; OpenSky enrichment
    is included in the same run only when ``opensky_wait_s == 0``.
    """
    now = time.time()
    adsb_wait = max(
        _ADSB_INTERVAL_S - (now - _gate_state.get("last_adsb_pull_ts", 0.0)),
        _gate_state["cooldown_until"] - now,
    )
    opensky_wait = max(0.0, _ANON_INTERVAL_S - (now - _gate_state["last_pull_ts"]))
    if block and adsb_wait > 0:
        return adsb_wait, opensky_wait
    return adsb_wait, opensky_wait


def _gate_mark_pull(include_opensky: bool = False) -> None:
    now = time.time()
    _gate_state["last_adsb_pull_ts"] = now
    if include_opensky:
        _gate_state["last_pull_ts"] = now
    _gate_state["total_pulls"] += 1
    _save_gate(_gate_state)


def _gate_mark_success(report_source: str, providers: dict | None) -> None:
    """Record snapshot freshness so /flights can prove the feed is live."""
    _gate_state["last_success_ts"] = time.time()
    _gate_state["last_source"] = report_source
    _gate_state["last_providers"] = providers or {}
    _save_gate(_gate_state)


# ---------------------------------------------------------------------------
# Track history (Maven-style trails) — ring buffer of fixes per icao24.
# ---------------------------------------------------------------------------

def _load_history() -> dict:
    if not os.path.exists(_HISTORY_PATH):
        return {}
    try:
        with open(_HISTORY_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        logger.warning("opensky_track_history.json unreadable; starting fresh")
        return {}


def _save_history(history: dict) -> None:
    try:
        os.makedirs(os.path.dirname(_HISTORY_PATH), exist_ok=True)
        tmp = _HISTORY_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(history, fh)
        os.replace(tmp, _HISTORY_PATH)
    except OSError as exc:
        logger.warning("Could not persist track history: %s", exc)


def merge_track_history(classified: dict, now: float | None = None) -> dict:
    """Append one fix per classified flight to its icao24 ring buffer.

    Fixes older than TRACK_FIX_TTL_S are dropped and aircraft unseen for
    TRACK_PRUNE_S are pruned entirely, keeping the file bounded. Returns
    ``{"aircraft": n_tracked, "fixes_appended": n}`` for the run report.
    """
    now = now or time.time()
    history = _load_history()
    appended = 0
    for key in ("commercial_flights", "private_flights", "private_jets", "military_flights"):
        for f in classified.get(key) or []:
            icao = (f.get("icao24") or "").strip().lower()
            lat, lng = f.get("lat"), f.get("lng")
            if not icao or lat is None or lng is None:
                continue
            entry = history.setdefault(icao, {"updated_at": 0.0, "fixes": []})
            entry["updated_at"] = now
            entry["fixes"].append({
                "t": round(now, 1),
                "lat": lat,
                "lng": lng,
                "alt": f.get("alt"),
                "gs": f.get("speed_knots"),
                "track": f.get("heading"),
                "on_ground": bool(f.get("grounded")),
            })
            appended += 1

    # TTL + cap + prune
    stale_icaos = []
    for icao, entry in history.items():
        fixes = [fx for fx in entry.get("fixes", []) if now - fx.get("t", 0) <= TRACK_FIX_TTL_S]
        entry["fixes"] = fixes[-TRACK_MAX_FIXES:]
        if now - entry.get("updated_at", 0.0) > TRACK_PRUNE_S:
            stale_icaos.append(icao)
    for icao in stale_icaos:
        history.pop(icao, None)

    _save_history(history)
    return {"aircraft": len(history), "fixes_appended": appended}


# ---------------------------------------------------------------------------
# adsbdb route enrichment — callsign -> origin/destination airports.
# ---------------------------------------------------------------------------

_route_session: aiohttp.ClientSession | None = None


async def _get_route_session() -> aiohttp.ClientSession:
    global _route_session
    if _route_session is None or _route_session.closed:
        _route_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8))
    return _route_session


def _load_route_cache() -> dict:
    if not os.path.exists(_ROUTE_CACHE_PATH):
        return {}
    try:
        with open(_ROUTE_CACHE_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}


def _save_route_cache(cache: dict) -> None:
    try:
        os.makedirs(os.path.dirname(_ROUTE_CACHE_PATH), exist_ok=True)
        tmp = _ROUTE_CACHE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(cache, fh)
        os.replace(tmp, _ROUTE_CACHE_PATH)
    except OSError as exc:
        logger.warning("Could not persist route cache: %s", exc)


async def lookup_flight_route(callsign: str) -> dict:
    """Resolve a callsign to its origin/destination route via adsbdb.com.

    Returns ``{"callsign", "found", "origin", "destination"}`` where the
    airports carry icao/iata codes, name, municipality, country and coords.
    Disk-cached: positives 7 days, negatives 12 hours.
    """
    cs = (callsign or "").strip().upper()
    if not cs:
        return {"callsign": cs, "found": False, "reason": "no callsign"}
    cache = _load_route_cache()
    hit = cache.get(cs)
    if hit:
        age = time.time() - hit.get("fetched_at", 0)
        ttl = _ROUTE_TTL_POS_S if hit.get("found") else _ROUTE_TTL_NEG_S
        if age <= ttl:
            return {k: v for k, v in hit.items() if k != "fetched_at"}

    data = None
    try:
        session = await _get_route_session()
        async with session.get(_ADSBDB_URL + cs) as resp:
            if resp.status == 200:
                data = await resp.json()
            elif resp.status in (404, 422):
                data = {}
            else:
                data = None  # transient — don't cache a failure
    except Exception as exc:  # noqa: BLE001
        logger.warning("adsbdb lookup failed for %s: %s", cs, exc)

    if data is None:
        return {"callsign": cs, "found": False, "reason": "lookup_unavailable"}

    # adsbdb envelopes successful payloads as {"response": {"flightroute": ...}}
    payload = (data or {}).get("response") if isinstance(data, dict) else None
    fr = ((payload if isinstance(payload, dict) else data) or {}).get("flightroute") or {}
    found = bool(fr.get("origin") or fr.get("destination"))

    def _apt(k: str) -> dict | None:
        a = fr.get(k) or None
        if not a:
            return None
        return {
            "icao": a.get("icao_code"), "iata": a.get("iata_code"),
            "name": a.get("name"), "municipality": a.get("municipality"),
            "country": a.get("country_name"), "lat": a.get("latitude"),
            "lng": a.get("longitude"),
        }

    result = {"callsign": cs, "found": found,
              "origin": _apt("origin"), "destination": _apt("destination")}
    cache[cs] = {"fetched_at": time.time(), **result}
    # Opportunistic prune of long-dead cache entries.
    dead = [k for k, v in cache.items()
            if time.time() - v.get("fetched_at", 0) > max(_ROUTE_TTL_POS_S, _ROUTE_TTL_NEG_S)]
    for k in dead:
        cache.pop(k, None)
    _save_route_cache(cache)
    return result


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


async def _run_pipeline(config: PipelineConfig, include_opensky: bool | None = None) -> dict:
    """Execute feed pull -> classify -> writeback and return the report dict.

    Dual-cadence gate: adsb.fi refreshes may run every _ADSB_INTERVAL_S; the
    OpenSky states/all enrichment piggybacks on the same run only when its own
    (persisted) interval has elapsed. Flight nodes are MERGED by icao24 and dead
    tracks pruned by age, so coverage persists across sparse OpenSky pulls.
    """
    # Gate: enforce both intervals across runs/restarts.
    adsb_wait, opensky_wait_gate = _gate_acquire(block=False)
    if adsb_wait > 0:
        return {
            "phase": "failed",
            "error": f"adsb.fi interval not elapsed — wait {int(adsb_wait)}s.",
            "error_kind": "rate_limited",
            "wait_s": adsb_wait,
        }
    if include_opensky is None:
        include_opensky = opensky_wait_gate <= 0

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
        force_skip_open_sky=not include_opensky,
    )
    if not include_opensky:
        # Fast lane: don't let the connector's 90s response cache serve the
        # same adsb.fi frame twice — positions must advance every pull.
        osconfig.cache_ttl_ms = 30000
    staging = StagingDataset(path="/tmp/opensky_staging.jsonl")

    session = await OpenSkyConnectorFactory.create_session()
    connector = OpenSkyConnector(config=osconfig, staging=staging, aiohttp_session=session)

    report: dict = {"phase": "pending"}
    try:
        classified = await connector.execute()
        _gate_mark_pull(include_opensky=include_opensky)

        # Merge-by-icao24: keep flight nodes whose icao24 is in the fresh pull
        # (writeback updates them) or younger than FLIGHT_STALE_REMOVE_S; drop
        # genuinely dead tracks so the map doesn't accumulate ghosts.
        now_ts = time.time()
        incoming_icaos = set()
        for key in ("commercial_flights", "private_flights", "private_jets", "military_flights"):
            for f in classified.get(key) or []:
                icao = (f.get("icao24") or "").strip().lower()
                if icao:
                    incoming_icaos.add(icao)

        def _node_icao(node: dict) -> str:
            props = node.get("properties", node)
            return str(props.get("icao24") or "").strip().lower()

        def _node_age_s(node: dict) -> float:
            props = node.get("properties", node)
            ts = props.get("last_seen_ts")
            if not ts:
                ingested = props.get("ingested_at")
                try:
                    ts = datetime.fromisoformat(str(ingested)).timestamp() if ingested else now_ts
                except ValueError:
                    ts = now_ts
            return max(0.0, now_ts - float(ts))

        stale_guids = [
            g for g, n in osv2._object_nodes.items()  # noqa: SLF001
            if n.get("type") == "aviation_flight"
            and _node_icao(n) not in incoming_icaos
            and _node_age_s(n) > FLIGHT_STALE_REMOVE_S
        ]
        for g in stale_guids:
            osv2._object_nodes.pop(g, None)  # noqa: SLF001

        # Writeback classified flights to OSv2 (updates/adds this snapshot)
        result, _ = await writeback_pipeline.process_aviation_flights(classified)

        # Stamp freshness on every live track so future runs can age it out.
        for n in osv2._object_nodes.values():  # noqa: SLF001
            if n.get("type") != "aviation_flight":
                continue
            props = n.get("properties")
            if props is not None and isinstance(props, dict):
                props["last_seen_ts"] = now_ts

        # Maven-style trails: append this snapshot's fixes to the ring buffers.
        history_stats = merge_track_history(classified, now=now_ts)

        # Persist so the map is non-blank after restart.
        _save_store(osv2._object_nodes)  # noqa: SLF001

        # Record snapshot freshness for /flights meta + UI LIVE badge.
        _gate_mark_success(classified.get("source", "unknown"), classified.get("providers"))

        # Build final report
        report = {
            "phase": "complete",
            "opensky_included": include_opensky,
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
            "history": history_stats,
            "pruned_stale": len(stale_guids),
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
        logger.info("OpenSky pipeline run complete: %s", {k: report[k] for k in ("phase", "opensky_included", "history", "pruned_stale")})
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
    """Run the feed pipeline as a background task; poll /pipeline/status.

    Verification-first: the persisted gates are checked BEFORE scheduling the
    job. adsb.fi refreshes are allowed every _ADSB_INTERVAL_S (default 30s);
    OpenSky states/all enrichment piggybacks only when its own interval has
    elapsed. Rejected requests return the wait time so the admin UI can show a
    countdown instead of a hanging 504.
    """
    if _run_state.get("status") == "running":
        return JSONResponse(
            content={"status": "already_running", "state": _run_state}, status_code=200
        )
    config = payload or PipelineConfig()
    adsb_wait, opensky_wait = _gate_acquire(block=False)
    if adsb_wait > 0:
        return JSONResponse(
            content={
                "status": "rejected",
                "error_kind": "rate_limited",
                "message": f"adsb.fi interval not elapsed — wait {int(adsb_wait)}s.",
                "wait_s": adsb_wait,
                "rate": get_opensky_rate_state(),
            },
            status_code=200,
        )
    if background_tasks is not None:
        background_tasks.add_task(_run_pipeline_bg, config)
    else:
        await _run_pipeline_bg(config)
    return JSONResponse(
        content={
            "status": "started",
            "opensky_included": opensky_wait <= 0,
            "state": _run_state,
        },
        status_code=202,
    )


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
    The ``meta`` block proves feed liveness: data age, source, per-provider
    counts, and when the next adsb.fi / OpenSky pulls become due.
    """
    osv2, _, _ = _build_pipeline()
    objs = osv2.get_all_objects()
    flights = [o for o in objs if o.get("type") == "aviation_flight"]
    total_tracked = len(flights)
    if category:
        flights = [
            f for f in flights
            if f.get("properties", {}).get("category") == category
        ]
    return JSONResponse(
        content={
            "flights": flights[-limit:],
            "count": len(flights),
            "total_tracked": total_tracked,
            "meta": get_opensky_rate_state(),
        },
        status_code=200,
    )


@router.get("/flights/track/{icao24}")
async def flight_track(icao24: str, with_route: bool = True):
    """Full Maven-style dossier for one aircraft: live properties, position
    history (trail fixes) and — when adsbdb knows the callsign — the
    origin/destination route with airport coordinates.

    ``with_route=false`` skips the adsbdb round-trip so the UI can paint the
    trail immediately and enrich the route in parallel.
    """
    icao = (icao24 or "").strip().lower()
    osv2, _, _ = _build_pipeline()
    node = None
    for n in osv2.get_all_objects():
        if n.get("type") != "aviation_flight":
            continue
        props = n.get("properties", {})
        if str(props.get("icao24") or "").strip().lower() == icao:
            node = n
            break
    if node is None:
        return JSONResponse(content={"error": "unknown icao24", "icao24": icao}, status_code=404)

    history = _load_history().get(icao) or {"fixes": [], "updated_at": None}
    node_callsign = (node.get("properties", {}) or {}).get("callsign", "")
    route = await lookup_flight_route(node_callsign) if with_route else None
    return JSONResponse(
        content={
            "flight": node.get("properties", node),
            "track": {
                "icao24": icao,
                "fixes": history.get("fixes", []),
                "updated_at": history.get("updated_at"),
                "fix_count": len(history.get("fixes", [])),
            },
            "route": route,
            "meta": get_opensky_rate_state(),
        },
        status_code=200,
    )


@router.get("/flights/route/{callsign}")
async def flight_route(callsign: str):
    """adsbdb origin/destination lookup for a single callsign (disk-cached)."""
    result = await lookup_flight_route(callsign)
    return JSONResponse(content=result, status_code=200)
