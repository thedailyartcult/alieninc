from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
from panteon.core.database import get_db, get_routers
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

logger = structlog.get_logger()

router = APIRouter(prefix="/router", tags=["Router Monitoring"])


class RouterStatus(BaseModel):
    id: str
    callsign: str
    barangay: str
    municipality: str
    lat: float
    lng: float
    model: str
    firmware: str
    status: str  # "online" | "offline" | "warning"
    signal_strength: Optional[float] = None  # percentage 0-100
    connected_clients: Optional[int] = None
    last_heartbeat: Optional[str] = None
    error: Optional[str] = None


class RouterCreate(BaseModel):
    callsign: str
    barangay: str
    municipality: str
    lat: float
    lng: float
    model: str
    firmware: str


class RouterEnriched(BaseModel):
    id: str
    callsign: str
    barangay: str
    municipality: str
    lat: float
    lng: float
    model: str
    firmware: str
    status: str
    signal_strength: float = None
    connected_clients: int = None
    last_heartbeat: str = None
    error: str = None
    vendor_name: str = None
    device_type: str = None
    city: str = None
    country: str = None
    latitude: float = None
    longitude: float = None
    last_seen_ip: str = None
    first_seen: str = None


@router.get("/status", response_model=List[RouterStatus])
async def get_router_status(
    db: AsyncSession = Depends(get_db),
):
    """Get current status of all registered routers."""
    from panteon.core.database import get_routers
    routers = await get_routers(db)
    return routers


@router.post("/status", response_model=List[RouterStatus])
async def update_router_status(
    routers: List[RouterStatus],
    db: AsyncSession = Depends(get_db),
):
    """Update router status from external source (e.g., polling script)."""
    from panteon.core.database import upsert_router
    results = []
    for r in routers:
        await upsert_router(db, r)
        results.append(r)
    return results


@router.get("/{router_id}")
async def get_router_detail(
    router_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get detailed status for a specific router."""
    from panteon.core.database import get_router
    router = await get_router(db, router_id)
    if not router:
        raise HTTPException(status_code=404, detail="Router not found")
    return router


@router.get("/enriched", response_model=List[RouterEnriched])
async def get_router_enriched(
    db: AsyncSession = Depends(get_db),
):
    """Get all routers with enrichment data (vendor, location, device type)."""
    from panteon.core.database import get_routers
    routers = await get_routers(db)
    return routers