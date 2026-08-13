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
from datetime import datetime, timezone
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from panteon.core.auth import get_current_user

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from gkg_connector import GKGConnector, GKGConfig, GKGEvent, GKGEventType, GKGConnectorFactory  # noqa: E402
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
        gkg_events = await connector.pull()

        # Transform events into OSv2 writeback payloads
        writeback_records = []
        for event in gkg_events:
            writeback_records.append({
                "event_code": event.event_code,
                "event_type": event.event_type.name if event.event_type else event.event_code,
                "action_geo": json.dumps(event.action_geo),
                "avg_tone": event.avg_tone,
                "num_articles": event.num_articles,
                "event_date": event.event_date,
                "guid": event.guid,
                "type": "gkg_event",
            })

        result = await writeback_pipeline._writeback_batch(writeback_records, {})

        # Also extract actors from events and writeback
        # (simple extraction: event codes can imply actor types)
        actor_records = []
        for event in gkg_events:
            # Extract country from action_geo if available
            country = event.action_geo.get("country", "")
            if country:
                actor_records.append({
                    "name": event.event_type.name if event.event_type else event.event_code,
                    "actor_type": event.event_type.value if event.event_type else "unknown",
                    "country": country,
                    "type": "gkg_actor",
                })

        if actor_records:
            result2 = await writeback_pipeline._writeback_batch(actor_records, {})
        else:
            result2 = {"success_count": 0, "failure_count": 0, "transaction_id": ""}

        report = {
            "phase": "complete",
            "gkg": {
                "total_events": len(gkg_events),
                "events_written": _write_count(result),
                "actor_records": len(actor_records),
                "actors_written": _write_count(result2),
            },
            "ontology": {
                "object_type_count": len(ontology.object_types),
                "link_type_count": len(ontology.link_types),
            },
            "timestamp": __import__("datetime").datetime.now(timezone.utc).isoformat(),
        }
        logger.info("GKG pipeline run complete: %s", report)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Pipeline failed: %s", exc)
        report = {"phase": "failed", "error": str(exc)}
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


def _is_rate_limited(err: str) -> bool:
    return "429" in err or "rate limit" in err.lower()


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
        if phase != "complete" and _is_rate_limited(report.get("error", "")):
            _run_state["error"] = "rate limited by GDELT — retrying once in 60s"
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


@router.post("/pipeline/run")
async def run_pipeline(payload: PipelineConfig = None, background_tasks: BackgroundTasks = None):
    """Run the GKG pipeline as a background task; poll /pipeline/status for the result.

    GDELT pulls can take minutes (429 retry backoff), which exceeds the reverse-proxy
    read timeout and surfaced as HTTP 504 in the admin UI. Returning immediately with
    a job status avoids that — the frontend polls until complete/failed.
    """
    if _run_state.get("status") == "running":
        return JSONResponse(content={"status": "already_running", "state": _run_state}, status_code=200)
    config = payload or PipelineConfig()
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
    events = osv2.get_all_objects()  # simplified - would need proper query
    return JSONResponse(content={"events": events[-limit:], "count": len(events)}, status_code=200)


@router.get("/actors")
async def list_actors(limit: int = 100):
    """List stored GKG actors from OSv2."""
    osv2, _, _ = _build_pipeline()
    actors = osv2.get_all_objects()
    return JSONResponse(content={"actors": actors[-limit:], "count": len(actors)}, status_code=200)
