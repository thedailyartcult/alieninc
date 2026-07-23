import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from panteon.core.database import get_db
from panteon.core.tenant import Tenant, TenantMetric
from panteon.integrations.tdac import TDACConnector, ResonanceIndexCalculator
from pydantic import BaseModel

router = APIRouter(prefix="/tdac", tags=["TDAC"])


class SyncRequest(BaseModel):
    supabase_url: str
    supabase_key: str


class ResonanceResponse(BaseModel):
    patron_id: str
    resonance_index: float
    components: dict
    reflections_count: int
    period_days: int


@router.post("/sync/patrons")
async def sync_patrons(
    data: SyncRequest,
    db: AsyncSession = Depends(get_db),
):
    connector = TDACConnector(db)
    result = await connector.sync_patrons(data.supabase_url, data.supabase_key)
    return result


@router.post("/sync/reflections")
async def sync_reflections(
    data: SyncRequest,
    db: AsyncSession = Depends(get_db),
):
    connector = TDACConnector(db)
    result = await connector.sync_reflections(data.supabase_url, data.supabase_key)
    return result


@router.post("/sync/publishers")
async def sync_publishers(
    data: SyncRequest,
    db: AsyncSession = Depends(get_db),
):
    connector = TDACConnector(db)
    result = await connector.sync_publishers(data.supabase_url, data.supabase_key)
    return result


@router.post("/sync/all")
async def sync_all(
    data: SyncRequest,
    db: AsyncSession = Depends(get_db),
):
    connector = TDACConnector(db)
    patrons = await connector.sync_patrons(data.supabase_url, data.supabase_key)
    reflections = await connector.sync_reflections(data.supabase_url, data.supabase_key)
    publishers = await connector.sync_publishers(data.supabase_url, data.supabase_key)
    return {
        "patrons": patrons,
        "reflections": reflections,
        "publishers": publishers,
    }


@router.get("/resonance/{patron_id}", response_model=ResonanceResponse)
async def get_patron_resonance(
    patron_id: str,
    period_days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    calculator = ResonanceIndexCalculator(db)
    result = await calculator.calculate_for_patron(patron_id, period_days)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/resonance")
async def get_tenant_resonance(
    period_days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    calculator = ResonanceIndexCalculator(db)
    result = await calculator.calculate_tenant_aggregate(period_days)
    return result


@router.get("/metrics")
async def list_metrics(
    metric_type: Optional[str] = None,
    limit: int = Query(default=100, le=1000),
    db: AsyncSession = Depends(get_db),
):
    tenant = await db.execute(
        select(Tenant).where(Tenant.slug == "thedailyartcult")
    )
    tenant = tenant.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="TDAC tenant not found")

    query = select(TenantMetric).where(TenantMetric.tenant_id == tenant.id)
    if metric_type:
        query = query.where(TenantMetric.metric_type == metric_type)
    query = query.order_by(TenantMetric.computed_at.desc()).limit(limit)

    result = await db.execute(query)
    metrics = result.scalars().all()

    return [
        {
            "id": str(m.id),
            "metric_type": m.metric_type,
            "value": m.value,
            "computed_at": m.computed_at.isoformat(),
        }
        for m in metrics
    ]


@router.get("/dashboard")
async def get_dashboard(db: AsyncSession = Depends(get_db)):
    calculator = ResonanceIndexCalculator(db)
    aggregate = await calculator.calculate_tenant_aggregate(30)
    
    result = await db.execute(
        select(Tenant).where(Tenant.slug == "thedailyartcult")
    )
    tenant = result.scalar_one_or_none()
    
    recent_metrics = []
    if tenant:
        metrics_result = await db.execute(
            select(TenantMetric)
            .where(TenantMetric.tenant_id == tenant.id)
            .order_by(TenantMetric.computed_at.desc())
            .limit(20)
        )
        recent_metrics = [
            {
                "type": m.metric_type,
                "value": m.value,
                "at": m.computed_at.isoformat(),
            }
            for m in metrics_result.scalars().all()
        ]

    return {
        "tenant": "The Daily Art Cult",
        "resonance_index": aggregate,
        "recent_activity": recent_metrics,
    }
