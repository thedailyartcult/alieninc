"""
Module B: GKG Events API router for Spinal Cracker / Panteon.

Exposes the GDELT Events API (GKG) pull -> parse -> ontology writeback pipeline
as endpoints under /api/v1/spinal-craker/ggk/. These complement the DOC 2.0
routes under /spinal-cracker/gdelt/.

The pipeline is intentionally lightweight and runs in-process (the OSv2 manager
/ ontology graph are module-level singletons so snapshots persist across requests
in the same process).
"""

import asyncio
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from panteon.core.auth import get_current_user

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from gkg_connector import (  # noqa: E402
    GKGConnector,
    GKGConfig,
    GKGEvent,
    GKGEventType,
    GKGConnectorFactory,
    GDELTError,
    validate_query_syntax,
    get_rate_state,
    reset_cooldown,
)
from gdelt_bigquery_connector import (  # noqa: E402
    GDELTBigQueryConnector,
    GDELTBigQueryConfig,
    is_bigquery_available,
)
from transform_gdelt_to_ontology import (  # noqa: E402
    GDELTTransformEngine,
    OntologyLayer,
    GDELTTransformPipeline,
)
from action_writeback_service import (  # noqa: E402
    OSv2Manager,
    GDELTWritebackPipeline,
    OntologyGraph,
)

logger = logging.getLogger("spinal_cracker.gkg_router")

router = APIRouter(
    prefix="/gkg",
    tags=["Spinal Cracker GKG"],
)


class PipelineConfig(BaseModel):
    """User-overridable GDELT Events API query parameters."""
    query: str = Field(
        default='("military" OR "defense" OR "security" OR "conflict")',
        description="GDELT Events API query string.",
    )
    timespan: str = Field(default="24h", description="GDELT timespan (e.g. 24h, 1h).")
    maxrecords: int = Field(default=250, ge=1, le=250)
    api_key: str = Field(default="", description="GDELT API key (empty: open/no-auth).")


def _build_pipeline() -> tuple[OSv2Manager, OntologyLayer, GDELTWritebackPipeline]:
    """Initialise the in-memory OSv2 store + ontology graph (module-level singletons)."""
    osv2 = getattr(_build_pipeline, "_osv2", None)
    if osv2 is None:
        osv2 = OSv2Manager()
        osv2.register_object_type("gkg_event", {
            "name": "gkg_event",
            "display_name": "GKG Event",
            "description": "GDELT GKG event object",
            "fields": ["event_code", "event_type", "action_geo", "avg_tone", "num_articles", "event_date"],
            "required_fields": ["event_code", "action_geo"],
            "relationships": ["HAS_EVENT_TYPE", "OCCURRED_IN"],
        })
        osv2.register_object_type("gkg_actor", {
            "name": "gkg_actor",
            "display_name": "GKG Actor",
            "description": "Extracted actor from GKG event",
            "fields": ["name", "actor_type", "country"],
            "required_fields": ["name"],
            "relationships": ["ACTS_IN"],
        })
        persisted = _load_osv2_store()
        if persisted:
            osv2._object_nodes.update(persisted)  # noqa: SLF001
        _build_pipeline._osv2 = osv2  # noqa: SLF001

    ontology = getattr(_build_pipeline, "_ontology", None)
    if ontology is None:
        ontology = OntologyLayer()
        _build_pipeline._ontology = ontology  # noqa: SLF001

    pipeline = GDELTWritebackPipeline(osv2=osv2, object_storage={}, ontology_graph=ontology)
    return osv2, ontology, pipeline


def _write_count(result) -> int:
    """Read success_count from a WritebackResult object or a plain dict."""
    return getattr(result, "success_count", None) or result.get("success_count", 0)


# ---------------------------------------------------------------------------
# OSv2 store persistence: the OSv2 manager is in-memory, so GKG events/actors
# would be lost on every service restart. We persist the object nodes to a
# JSON file after each successful run and reload them on startup.
# ---------------------------------------------------------------------------
_STORE_PATH = os.path.join(BACKEND_DIR, "panteon", "api", "gkg_osv2_store.json")


def _load_osv2_store() -> dict:
    if not os.path.exists(_STORE_PATH):
        return {}
    try:
        with open(_STORE_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        # Prune the legacy actor node created when actor records carried neither
        # guid nor url (every actor collapsed onto uuid5("unknown")). Those
        # guids are meaningless; drop them so the store reflects real actors.
        legacy_actor_guid = str(uuid.uuid5(uuid.NAMESPACE_URL, "unknown"))
        pruned = {
            k: v for k, v in data.items()
            if not (v.get("type") == "gkg_actor" and k == legacy_actor_guid)
        }
        if len(pruned) != len(data):
            logger.info("Pruned %s legacy collapsed actor node(s) from store", len(data) - len(pruned))
        return pruned
    except (OSError, json.JSONDecodeError):
        logger.warning("gkg_osv2_store.json unreadable; starting with empty store")
        return {}


def _save_osv2_store(nodes: dict) -> None:
    try:
        os.makedirs(os.path.dirname(_STORE_PATH), exist_ok=True)
        tmp = _STORE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(nodes, fh, default=str)
        os.replace(tmp, _STORE_PATH)
    except OSError as exc:
        logger.warning("Could not persist GKG OSv2 store: %s", exc)


async def _run_pipeline(config: PipelineConfig) -> dict:
    """Execute pull -> parse -> writeback and return the report dict."""
    osv2, ontology, writeback_pipeline = _build_pipeline()

    gdconfig = GKGConfig(
        query=config.query,
        timespan=config.timespan,
        maxrecords=config.maxrecords,
        api_key=config.api_key,
    )

    staging = []  # staging dataset not needed for GKG, events written directly

    connector = GKGConnector(config=gdconfig)

    report: dict = {"phase": "pending"}
    try:
        # BigQuery-first: try the production-grade GDELT GKG table (rich tone +
        # actors + precise geocoding, no per-IP throttle). Fall back to the DOC
        # 2.0 API if BigQuery is unavailable (no creds / quota / error).
        gkg_events = []
        source_used = "unknown"
        bq_error = None
        if is_bigquery_available():
            try:
                import asyncio as _asyncio
                bq_config = GDELTBigQueryConfig(max_results=config.maxrecords)
                bq_connector = GDELTBigQueryConnector(config=bq_config)
                # BigQuery client is blocking — run in a thread.
                gkg_events = await _asyncio.to_thread(bq_connector.pull)
                source_used = "bigquery"
                logger.info("GDELT BigQuery pull succeeded: %d events", len(gkg_events))
            except Exception as bq_exc:
                bq_error = str(bq_exc)
                logger.warning("GDELT BigQuery failed, falling back to DOC 2.0: %s", bq_exc)

        if not gkg_events:
            # DOC 2.0 fallback (or BigQuery unavailable).
            gkg_events = await connector.pull()
            source_used = "doc2_fallback" if bq_error else "doc2"

        # Transform events into OSv2 writeback payloads
        writeback_records = []
        for event in gkg_events:
            writeback_records.append({
                "event_code": event.event_code,
                "event_root_code": event.event_root_code,
                "event_type": event.event_type.name if event.event_type else event.event_code,
                "action_geo": json.dumps(event.action_geo),
                "avg_tone": event.avg_tone,
                "num_articles": event.num_articles,
                "event_date": event.event_date,
                "guid": event.guid,
                "url": event.source_url,
                "title": event.title,
                "sourcecountry": event.sourcecountry,
                "domain": event.domain,
                "language": event.language,
                "seendate": event.event_date,
                "type": "gkg_event",
            })

        result = await writeback_pipeline._writeback_batch(writeback_records, {})

        # Also extract actors from events and writeback.
        # Actor identity is derived deterministically from (name, country, type)
        # so the same actor merges across runs while distinct actors map to
        # distinct OSv2 nodes. The writeback service falls back to
        # uuid5(NAMESPACE_URL, url-or-"unknown") when a record carries neither
        # guid nor url — which made every actor collapse into ONE node; an
        # explicit guid here fixes that.
        actor_records = []
        for event in gkg_events:
            # Extract country from action_geo if available
            country = event.action_geo.get("country", "")
            etype = event.event_type if event.event_type else GKGEventType.UNKNOWN
            name = f"{country} {etype.name}".strip() if country else etype.name
            actor_guid = str(uuid.uuid5(
                uuid.NAMESPACE_URL, f"gkg_actor:{name}:{etype.value}:{country}"
            ))
            actor_records.append({
                "guid": actor_guid,
                "name": name,
                "actor_type": etype.value,
                "country": country,
                "type": "gkg_actor",
            })

        if actor_records:
            result2 = await writeback_pipeline._writeback_batch(actor_records, {})
        else:
            result2 = {"success_count": 0, "failure_count": 0, "transaction_id": ""}

        # Report the number of DISTINCT actor nodes actually stored, not the raw
        # record count (records are deduped onto shared actor nodes).
        unique_actors = len({r["guid"] for r in actor_records}) if actor_records else 0

        report = {
            "phase": "complete",
            "gkg": {
                "total_events": len(gkg_events),
                "events_written": _write_count(result),
                "actor_records": len(actor_records),
                "actors_written": min(_write_count(result2), unique_actors),
                "source": source_used,
            },
            "ontology": {
                "object_type_count": len(ontology.object_types),
                "link_type_count": len(ontology.link_types),
            },
            "bigquery": {
                "available": is_bigquery_available(),
                "used": source_used == "bigquery",
                "error": bq_error,
            },
            "timestamp": __import__("datetime").datetime.now(timezone.utc).isoformat(),
        }
        _save_osv2_store(osv2._object_nodes)  # noqa: SLF001
        logger.info("GKG pipeline run complete: %s", report)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Pipeline failed: %s", exc)
        report = {"phase": "failed", "error": str(exc)}
        if isinstance(exc, GDELTError):
            report["error_kind"] = exc.kind
    finally:
        await GKGConnectorFactory.reset_session()

    return report


_run_state: dict = {
    "status": "idle",
    "started_at": None,
    "finished_at": None,
    "report": None,
    "error": None,
}

# Transient GDELT failures worth one background retry (structural errors are
# never retried — retrying cannot change the outcome).
_TRANSIENT_KINDS = {"rate_limited", "server_error", "network", "timeout"}


def _is_rate_limited(err: str) -> bool:
    return "429" in err or "rate limit" in err.lower()


# Validation cache: {query: {"ts": float, "result": dict}}. A successfully
# probed query is reused for VALID_CACHE_TTL_S so re-clicking Run doesn't burn
# another GDELT request against the per-IP throttle.
_validation_cache: dict = {}
_VALID_CACHE_TTL_S = 120.0


async def _validate_query(config: PipelineConfig, force_live: bool = False) -> dict:
    """Verify a query structurally, then with a single live GDELT probe.

    Returns {valid, errors, warnings, live, sample_count?, error_kind?, message?,
    rate}. ``live`` is "skipped" (structural failure), "cached" or "probed".
    Never raises — callers get a JSON-serialisable result.
    """
    issues = validate_query_syntax(config.query)
    errors = [i for i in issues if i["severity"] == "error"]
    warnings = [i for i in issues if i["severity"] == "warning"]
    rate = get_rate_state()

    if errors:
        return {
            "valid": False, "errors": errors, "warnings": warnings,
            "live": "skipped", "rate": rate,
        }

    now = datetime.now(timezone.utc).timestamp()
    cached = _validation_cache.get(config.query)
    if cached and not force_live and (now - cached["ts"]) < _VALID_CACHE_TTL_S:
        return {
            "valid": cached["result"]["valid"], "errors": errors, "warnings": warnings,
            "live": "cached", "sample_count": cached["result"].get("sample_count"),
            "rate": rate,
        }

    # BigQuery-first validation: if BigQuery is configured, validate via a
    # lightweight BQ probe (no per-IP throttle). Only fall back to the DOC 2.0
    # probe when BigQuery is unavailable.
    if is_bigquery_available():
        try:
            import asyncio as _asyncio
            bq_conn = GDELTBigQueryConnector(config=GDELTBigQueryConfig(max_results=1))
            bq_result = await _asyncio.to_thread(bq_conn.validate)
            _validation_cache[config.query] = {"ts": now, "result": bq_result}
            return {
                "valid": True, "errors": errors, "warnings": warnings,
                "live": "bigquery", "sample_count": bq_result.get("sample_count"),
                "rate": rate, "backend": "bigquery",
            }
        except Exception as bq_exc:  # noqa: BLE001
            logger.warning("BigQuery validate failed, falling back to DOC 2.0: %s", bq_exc)
            # Fall through to DOC 2.0 probe below.

    gdconfig = GKGConfig(
        query=config.query, timespan=config.timespan,
        maxrecords=config.maxrecords, api_key=config.api_key,
    )
    connector = GKGConnector(config=gdconfig)
    try:
        result = await connector.probe()
        _validation_cache[config.query] = {"ts": now, "result": result}
        return {
            "valid": True, "errors": errors, "warnings": warnings,
            "live": "probed", "sample_count": result["sample_count"], "rate": get_rate_state(),
        }
    except GDELTError as exc:
        return {
            "valid": False, "errors": errors, "warnings": warnings,
            "live": "probed", "error_kind": exc.kind, "message": exc.message,
            "wait_s": exc.wait_s, "rate": get_rate_state(),
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("GKG validate probe crashed: %s", exc)
        return {
            "valid": False, "errors": errors, "warnings": warnings,
            "live": "probed", "error_kind": "generic", "message": str(exc),
            "rate": get_rate_state(),
        }
    finally:
        await GKGConnectorFactory.reset_session()


async def _run_pipeline_bg(config: PipelineConfig) -> dict:
    """Run the GKG pipeline in the background and publish state for polling.

    GDELT rate-limits request bursts from an IP; on a rate-limit failure we wait
    once for the throttle window and retry, so a single "Run" click usually lands.
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
        phase = report.get("phase")
        # One background retry, but ONLY for transient failures. Structural
        # errors (phrase_too_short / or_not_parenthesized / nested_or) never
        # change on retry, so we surface them immediately instead of burning
        # another request against the per-IP throttle.
        if phase != "complete":
            kind = report.get("error_kind", "")
            if kind in _TRANSIENT_KINDS or (not kind and _is_rate_limited(report.get("error", ""))):
                _run_state["error"] = "transient GDELT failure — retrying once in 60s"
                await asyncio.sleep(60)
                report = await _run_pipeline(config)
                phase = report.get("phase")
        _run_state["report"] = report
        _run_state["status"] = "complete" if phase == "complete" else "failed"
        if phase != "complete":
            _run_state["error"] = report.get("error") or "pipeline failed"
    except Exception as exc:  # noqa: BLE001
        logger.exception("GKG background pipeline crashed: %s", exc)
        _run_state["status"] = "failed"
        _run_state["error"] = str(exc)
    _run_state["finished_at"] = datetime.now(timezone.utc).isoformat()
    return _run_state


@router.get("/health")
async def health_check():
    return {"status": "ok", "source": "panteon spinal-cracker gkg"}


@router.post("/pipeline/validate")
async def validate_pipeline(payload: PipelineConfig = None):
    """Verify a query before running: structural rules + a single live GDELT probe.

    This is the verification-first gate. The admin UI calls this from the
    "Validate" button and (optionally) before "Run" so a bad query never reaches
    the background pipeline and never triggers a retry storm / IP throttle.
    """
    config = payload or PipelineConfig()
    result = await _validate_query(config, force_live=True)
    # Always 200: the verdict (valid true/false) lives in the body so the admin
    # UI's shared api() helper (which drops non-2xx bodies) receives it intact.
    return JSONResponse(content=result, status_code=200)


@router.get("/bigquery/status")
async def bigquery_status():
    """Report whether the GDELT BigQuery backend is configured and available.

    BigQuery is the production-grade GDELT path (no per-IP throttle, rich tone
    + actors + precise geocoding). This endpoint tells the admin UI whether
    the BigQuery-first path is active or whether the system will use the DOC
    2.0 API fallback.
    """
    available = is_bigquery_available()
    return JSONResponse(content={
        "available": available,
        "credentials_path": os.environ.get("GDELT_BQ_CREDENTIALS", ""),
        "mode": "bigquery-first" if available else "doc2-only",
        "note": (
            "GDELT BigQuery is configured — the pipeline will query the GKG "
            "table (tone + actors + geocoding) and fall back to DOC 2.0 on error."
            if available else
            "GDELT BigQuery is NOT configured — set GDELT_BQ_CREDENTIALS to a "
            "Google Cloud service-account JSON key to enable the production "
            "backend (no per-IP throttle). Currently using DOC 2.0 only."
        ),
    }, status_code=200)


@router.get("/pipeline/rate")
async def pipeline_rate():
    """GDELT rate-governance snapshot: cooldown state, spacing, total requests.

    The free GDELT DOC 2.0 API has no monthly cap — only a ~1 req/5s per-IP
    throttle — so this reports throttle/cooldown status, not a budget.
    """
    return JSONResponse(content=get_rate_state(), status_code=200)


@router.post("/pipeline/cooldown/reset")
async def pipeline_cooldown_reset():
    """Admin escape hatch: clear an active GDELT cooldown immediately."""
    reset_cooldown()
    return JSONResponse(content=get_rate_state(), status_code=200)


@router.post("/pipeline/run")
async def run_pipeline(payload: PipelineConfig = None, background_tasks: BackgroundTasks = None):
    """Run the GKG pipeline as a background task; poll /pipeline/status for the result.

    Verification-first: the EXACT query is validated (structural + live probe,
    cached for _VALID_CACHE_TTL_S) before any background pull is scheduled. A bad
    query is rejected here with 422 and never starts a job, so it cannot trigger a
    retry storm or IP throttle. GDELT pulls can still take minutes (rate-limit
    backoff), so we return immediately with a job status and the frontend polls.
    """
    if _run_state.get("status") == "running":
        return JSONResponse(content={"status": "already_running", "state": _run_state}, status_code=200)
    config = payload or PipelineConfig()
    verification = await _validate_query(config, force_live=False)
    if not verification["valid"]:
        # 200 with status:"rejected" — the body carries the verification detail
        # so the admin UI (shared api() drops non-2xx bodies) can render it.
        return JSONResponse(
            content={"status": "rejected", "verification": verification},
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


@router.get("/events")
async def list_events(limit: int = 100):
    """List stored GKG events from OSv2."""
    osv2, _, _ = _build_pipeline()
    events = [n for n in osv2.get_all_objects() if n.get("type") == "gkg_event"]
    return JSONResponse(content={"events": events[-limit:], "count": len(events)}, status_code=200)


@router.get("/actors")
async def list_actors(limit: int = 100):
    """List stored GKG actors from OSv2."""
    osv2, _, _ = _build_pipeline()
    actors = [n for n in osv2.get_all_objects() if n.get("type") == "gkg_actor"]
    return JSONResponse(content={"actors": actors[-limit:], "count": len(actors)}, status_code=200)
