import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from panteon.core.database import get_db
from panteon.core.auth import get_current_user
from panteon.core.config import settings
from panteon.core.tenant import Tenant, TenantMetric
from panteon.spinal_craker.models import ObjectType, Object
from panteon.integrations.tdac import TDACConnector, ResonanceIndexCalculator
from pydantic import BaseModel
import structlog

logger = structlog.get_logger()

router = APIRouter(prefix="/tdac", tags=["TDAC"], dependencies=[Depends(get_current_user)])


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


@router.get("/patrons")
async def list_patrons(
    limit: int = Query(default=100, le=500),
    db: AsyncSession = Depends(get_db),
):
    tenant = await db.execute(select(Tenant).where(Tenant.slug == "thedailyartcult"))
    tenant = tenant.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="TDAC tenant not found")

    patron_type = await db.execute(
        select(ObjectType).where(ObjectType.name == "tdac_patron")
    )
    patron_type = patron_type.scalar_one_or_none()
    if not patron_type:
        return []

    result = await db.execute(
        select(Object)
        .where(Object.object_type_id == patron_type.id)
        .order_by(Object.created_at.desc())
        .limit(limit)
    )
    return [
        {"id": str(p.id), "primary_key": p.primary_key_value, "properties": p.properties, "created_at": p.created_at.isoformat()}
        for p in result.scalars().all()
    ]


@router.get("/patrons/{patron_id}/engagement")
async def get_patron_engagement(
    patron_id: str,
    db: AsyncSession = Depends(get_db),
):
    from panteon.integrations.tdac import ResonanceIndexCalculator
    calc = ResonanceIndexCalculator(db)
    resonance = await calc.calculate_for_patron(patron_id, 30)
    resonance_90 = await calc.calculate_for_patron(patron_id, 90)

    result = await db.execute(
        select(TenantMetric)
        .where(
            TenantMetric.tenant_id == (await db.execute(select(Tenant).where(Tenant.slug == "thedailyartcult"))).scalar_one_or_none().id,
            TenantMetric.metric_type == "reflection_completed",
        )
        .order_by(TenantMetric.computed_at.desc())
        .limit(500)
    )
    all_metrics = result.scalars().all()
    patron_metrics = [m for m in all_metrics if m.value.get("patron_id") == patron_id]

    listening_streak = 0
    reflections_heard = 0
    for m in patron_metrics:
        pct = m.value.get("listened_percentage", 0)
        if pct >= 50:
            reflections_heard += 1

    return {
        "patron_id": patron_id,
        "resonance_30d": resonance,
        "resonance_90d": resonance_90,
        "reflections_completed_30d": len(patron_metrics),
        "reflections_listened_30d": reflections_heard,
        "context_updates": resonance.get("components", {}).get("R2_depth_score", 0),
        "unique_publishers": resonance.get("components", {}).get("R3_discovery_rate", 0),
    }


class PublisherIssueCreate(BaseModel):
    publisher_id: str
    title: str
    base_prompt: str
    worldview: Optional[str] = None
    description: Optional[str] = None


class ReflectionTrigger(BaseModel):
    patron_id: str
    issue_id: Optional[str] = None


@router.post("/publisher-issues")
async def create_publisher_issue(
    data: PublisherIssueCreate,
    db: AsyncSession = Depends(get_db),
):
    issue_type = await db.execute(select(ObjectType).where(ObjectType.name == "tdac_publisher_issue"))
    issue_type = issue_type.scalar_one_or_none()
    if not issue_type:
        issue_type = await ObjectType(
            name="tdac_publisher_issue",
            display_name="TDAC Publisher Issue",
            description="Content issue for a publisher worldview",
            properties_schema={
                "publisher_id": "string",
                "title": "string",
                "base_prompt": "text",
                "worldview": "string",
                "is_published": "boolean",
            },
        )
        db.add(issue_type)
        await db.flush()

    from panteon.spinal_craker.service import OntologyService
    svc = OntologyService(db)
    obj = await svc.create_object(
        object_type_id=issue_type.id,
        primary_key_value=f"{data.publisher_id}:{data.title.lower().replace(' ', '-')[:40]}",
        properties={
            "publisher_id": data.publisher_id,
            "title": data.title,
            "base_prompt": data.base_prompt,
            "worldview": data.worldview,
            "description": data.description,
            "is_published": False,
        },
    )
    return {"id": str(obj.id), "primary_key": obj.primary_key_value, "properties": obj.properties}


@router.get("/publisher-issues")
async def list_publisher_issues(
    publisher_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    issue_type = await db.execute(select(ObjectType).where(ObjectType.name == "tdac_publisher_issue"))
    issue_type = issue_type.scalar_one_or_none()
    if not issue_type:
        return []

    query = select(Object).where(Object.object_type_id == issue_type.id)
    result = await db.execute(query.order_by(Object.created_at.desc()).limit(100))
    issues = []
    for obj in result.scalars().all():
        if publisher_id and obj.properties.get("publisher_id") != publisher_id:
            continue
        issues.append({"id": str(obj.id), "primary_key": obj.primary_key_value, "properties": obj.properties})
    return issues


@router.post("/trigger-reflection")
async def trigger_reflection(
    data: ReflectionTrigger,
    db: AsyncSession = Depends(get_db),
):
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise HTTPException(status_code=503, detail="Supabase not configured")

    from panteon.integrations.tdac_automation import TDACDailyReflectionAutomation
    automation = TDACDailyReflectionAutomation(db)

    try:
        result = await automation.execute_for_patron(
            patron_id=data.patron_id,
            issue_id=data.issue_id,
        )
        return result
    except Exception as e:
        logger.error("reflection_trigger_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


class BatchReflectionTrigger(BaseModel):
    issue_id: Optional[str] = None


@router.post("/trigger-reflections-batch")
async def trigger_reflections_batch(
    data: BatchReflectionTrigger = BatchReflectionTrigger(),
    db: AsyncSession = Depends(get_db),
):
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise HTTPException(status_code=503, detail="Supabase not configured")

    from panteon.integrations.tdac_automation import TDACDailyReflectionAutomation
    automation = TDACDailyReflectionAutomation(db)

    try:
        result = await automation.execute_batch(issue_id=data.issue_id)
        return result
    except Exception as e:
        logger.error("batch_reflection_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
