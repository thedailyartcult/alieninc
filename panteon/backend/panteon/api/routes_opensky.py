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

import logging
import os
import sys

from fastapi import APIRouter, BackgroundTasks, HTTPException
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
        _build_pipeline._osv2 = osv2  # noqa: SLF001

    ontology = getattr(_build_pipeline, "_ontology", None)
    if ontology is None:
        ontology = OntologyGraph()
        _build_pipeline._ontology = ontology  # noqa: SLF001

    pipeline = AviationWritebackPipeline(osv2=osv2, object_storage={}, ontology_graph=ontology)
    return osv2, ontology, pipeline


async def _run_pipeline(config: PipelineConfig) -> dict:
    """Execute OpenSky pull -> classify -> writeback and return the report dict."""
    osv2, ontology, writeback_pipeline = _build_pipeline()

    osconfig = OpenSkyConfig(
        client_id=config.client_id,
        client_secret=config.client_secret,
        fetch_military=config.fetch_military,
        request_timeout=config.request_timeout,
        max_retries=config.max_retries,
    )
    staging = StagingDataset(path="/tmp/opensky_staging.jsonl")

    session = await OpenSkyConnectorFactory.create_session()
    connector = OpenSkyConnector(config=osconfig, staging=staging, aiohttp_session=session)

    report: dict = {"phase": "pending"}
    try:
        classified = await connector.execute()

        # Writeback classified flights to OSv2
        result = await writeback_pipeline.process_aviation_flights(classified)

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
        }
        logger.info("OpenSky pipeline run complete: %s", report)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Pipeline failed: %s", exc)
        report = {"phase": "failed", "error": str(exc)}
    finally:
        await OpenSkyConnectorFactory.reset_session()

    return report


@router.get("/health")
async def health_check():
    return {"status": "ok", "source": "panteon spinal-cracker opensky"}


@router.post("/pipeline/run")
async def run_pipeline(payload: PipelineConfig = None, _bg: BackgroundTasks = None):
    """Run the OpenSky Network -> classify -> writeback pipeline."""
    config = payload or PipelineConfig()
    report = await _run_pipeline(config)
    if report.get("phase") == "failed":
        raise HTTPException(status_code=502, detail=report.get("error", "pipeline failed"))
    return JSONResponse(content=report, status_code=200)


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
