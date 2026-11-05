"""
FastAPI router for vessel tracking endpoints.

Exposes /api/v1/vessels/* for the GAIA vessel layer.
Pattern: mirrors routes_opensky.py structure.
"""

import logging
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from magritte_connector_vessels import vessel_connector, _reload_api_key

logger = logging.getLogger("panteon.api.routes_vessels")
router = APIRouter(tags=["vessels"])


@router.on_event("startup")
async def _start_vessel_connector():
    """Start the vessel connector background task on app startup."""
    try:
        _reload_api_key()
        await vessel_connector.start()
        print(f"[vessels] VesselConnector started: mode={vessel_connector.mode}", flush=True)
    except Exception as e:
        print(f"[vessels] Failed to start VesselConnector: {e}", flush=True)


@router.on_event("shutdown")
async def _stop_vessel_connector():
    """Stop the vessel connector on app shutdown."""
    try:
        await vessel_connector.stop()
    except Exception:
        pass


@router.get("/vessels")
async def list_vessels(
    category: str = Query(None, description="Filter by category: navy,coast_guard,cargo,tanker,fishing,passenger,unknown"),
    limit: int = Query(200, ge=1, le=2000),
):
    """List all tracked vessels, optionally filtered by category."""
    vessels = vessel_connector.get_vessels(category=category)
    return JSONResponse(content={
        "vessels": vessels[:limit],
        "count": len(vessels),
        "total_tracked": len(vessel_connector._vessels),
        "meta": vessel_connector.get_status(),
    }, status_code=200)


@router.get("/vessels/status")
async def vessel_status():
    """Connector health and diagnostics."""
    return JSONResponse(content=vessel_connector.get_status(), status_code=200)


@router.get("/vessels/{mmsi}")
async def get_vessel(mmsi: str):
    """Single vessel detail by MMSI."""
    vessel = vessel_connector.get_vessel(mmsi)
    if not vessel:
        return JSONResponse(
            content={"error": "unknown mmsi", "mmsi": mmsi},
            status_code=404,
        )
    return JSONResponse(content={"vessel": vessel}, status_code=200)
