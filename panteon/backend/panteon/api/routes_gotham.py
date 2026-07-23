import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from panteon.core.database import get_db
from panteon.core.auth import SupabaseUser, get_current_user
from panteon.gotham.service import GothamService

router = APIRouter(prefix="/gotham", tags=["Gotham Intelligence"])


class InvestigationCreate(BaseModel):
    title: str
    description: Optional[str] = None
    classification: str = "confidential"
    workspace_id: Optional[str] = None
    priority: str = "medium"
    tags: Optional[list[str]] = None


class InvestigationUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    tags: Optional[list[str]] = None


class FindingCreate(BaseModel):
    investigation_id: str
    title: str
    summary: Optional[str] = None
    analysis: Optional[str] = None
    confidence: float = 0.0
    finding_type: str = "observation"
    classification: str = "confidential"
    linked_entities: Optional[list] = None
    linked_objects: Optional[list] = None


class EvidenceCreate(BaseModel):
    finding_id: str
    evidence_type: str
    source: Optional[str] = None
    content: Optional[str] = None
    classification: str = "confidential"
    metadata: Optional[dict] = None


class ThreatEntityCreate(BaseModel):
    name: str
    entity_type: str = "person"
    aliases: Optional[list[str]] = None
    description: Optional[str] = None
    threat_level: str = "low"
    workspace_id: Optional[str] = None
    attributes: Optional[dict] = None
    classification: str = "confidential"


class EntityLink(BaseModel):
    source_id: str
    target_id: str
    connection_type: str = "related"
    weight: float = 1.0


class GeoEventCreate(BaseModel):
    title: str
    event_type: str
    occurred_at: datetime
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    country: Optional[str] = None
    region: Optional[str] = None
    severity: str = "moderate"
    description: Optional[str] = None
    threat_entity_id: Optional[str] = None
    workspace_id: Optional[str] = None
    investigation_id: Optional[str] = None


# ================================================================
# INVESTIGATIONS
# ================================================================

@router.get("/dashboard")
async def gotham_dashboard(
    workspace_id: Optional[str] = None,
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = GothamService(db)
    return await svc.get_dashboard_stats(workspace_id)


@router.post("/investigations")
async def create_investigation(
    data: InvestigationCreate,
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = GothamService(db)
    inv = await svc.create_investigation(
        title=data.title,
        description=data.description,
        classification=data.classification,
        workspace_id=data.workspace_id,
        created_by=_user.email,
        priority=data.priority,
        tags=data.tags,
    )
    return {"id": str(inv.id), "case_number": inv.case_number, "status": inv.status}


@router.get("/investigations")
async def list_investigations(
    workspace_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = GothamService(db)
    return await svc.list_investigations(workspace_id, status, limit)


@router.get("/investigations/{investigation_id}")
async def get_investigation(
    investigation_id: str,
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = GothamService(db)
    result = await svc.get_investigation(investigation_id)
    if not result:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return result


@router.patch("/investigations/{investigation_id}")
async def update_investigation(
    investigation_id: str,
    data: InvestigationUpdate,
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = GothamService(db)
    updates = {k: v for k, v in data.model_dump().items() if v is not None}
    result = await svc.update_investigation(investigation_id, updates, _user.email)
    if not result:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return {"id": str(result.id), "status": result.status, "case_number": result.case_number}


@router.post("/investigations/{investigation_id}/assign")
async def assign_analyst(
    investigation_id: str,
    analyst_email: str = Query(...),
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = GothamService(db)
    ok = await svc.assign_analyst(investigation_id, analyst_email)
    if not ok:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return {"assigned": True, "analyst": analyst_email}


# ================================================================
# FINDINGS & EVIDENCE
# ================================================================

@router.post("/findings")
async def create_finding(
    data: FindingCreate,
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = GothamService(db)
    finding = await svc.create_finding(
        investigation_id=data.investigation_id,
        title=data.title,
        summary=data.summary,
        analysis=data.analysis,
        confidence=data.confidence,
        finding_type=data.finding_type,
        classification=data.classification,
        linked_entities=data.linked_entities,
        linked_objects=data.linked_objects,
        created_by=_user.email,
    )
    return {"id": str(finding.id), "title": finding.title}


@router.post("/evidence")
async def add_evidence(
    data: EvidenceCreate,
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = GothamService(db)
    evidence = await svc.add_evidence(
        finding_id=data.finding_id,
        evidence_type=data.evidence_type,
        source=data.source,
        content=data.content,
        classification=data.classification,
        metadata=data.metadata,
    )
    return {"id": str(evidence.id), "evidence_type": evidence.evidence_type}


# ================================================================
# GRAPH ANALYSIS
# ================================================================

@router.get("/graph/analyze")
async def analyze_graph(
    entity_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
    depth: int = Query(default=2, ge=1, le=5),
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = GothamService(db)
    return await svc.analyze_entity_graph(entity_id, workspace_id, depth)


# ================================================================
# THREAT ENTITIES
# ================================================================

@router.post("/entities")
async def create_threat_entity(
    data: ThreatEntityCreate,
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = GothamService(db)
    entity = await svc.create_threat_entity(
        name=data.name,
        entity_type=data.entity_type,
        aliases=data.aliases,
        description=data.description,
        threat_level=data.threat_level,
        workspace_id=data.workspace_id,
        attributes=data.attributes,
        classification=data.classification,
    )
    return {"id": str(entity.id), "name": entity.name, "risk_score": entity.risk_score}


@router.get("/entities")
async def list_threat_entities(
    workspace_id: Optional[str] = None,
    threat_level: Optional[str] = None,
    entity_type: Optional[str] = None,
    min_risk_score: Optional[float] = None,
    limit: int = Query(default=100, le=500),
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = GothamService(db)
    return await svc.list_threat_entities(workspace_id, threat_level, entity_type, min_risk_score, limit)


@router.post("/entities/link")
async def link_entities(
    data: EntityLink,
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = GothamService(db)
    ok = await svc.link_entities(data.source_id, data.target_id, data.connection_type, data.weight)
    if not ok:
        raise HTTPException(status_code=404, detail="Source entity not found")
    return {"linked": True}


# ================================================================
# GEOSPATIAL
# ================================================================

@router.post("/geo-events")
async def create_geo_event(
    data: GeoEventCreate,
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = GothamService(db)
    event = await svc.create_geo_event(
        title=data.title,
        event_type=data.event_type,
        occurred_at=data.occurred_at,
        latitude=data.latitude,
        longitude=data.longitude,
        country=data.country,
        region=data.region,
        severity=data.severity,
        description=data.description,
        threat_entity_id=data.threat_entity_id,
        workspace_id=data.workspace_id,
        investigation_id=data.investigation_id,
    )
    return {"id": str(event.id), "title": event.title}


@router.get("/geo-events")
async def get_geo_events(
    workspace_id: Optional[str] = None,
    country: Optional[str] = None,
    event_type: Optional[str] = None,
    severity: Optional[str] = None,
    days_back: int = Query(default=30, le=365),
    limit: int = Query(default=200, le=1000),
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = GothamService(db)
    return await svc.get_geo_events(workspace_id, country, event_type, severity, days_back, limit)


@router.get("/country-risk")
async def get_country_risk(
    country: Optional[str] = None,
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = GothamService(db)
    return await svc.get_country_risk(country)


@router.post("/country-risk/compute")
async def compute_country_risk(
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = GothamService(db)
    return await svc.compute_country_risk_from_events()


# ================================================================
# PATTERN DETECTION / ALERTS
# ================================================================

@router.post("/detect-anomalies")
async def detect_anomalies(
    workspace_id: Optional[str] = None,
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = GothamService(db)
    alerts = await svc.detect_anomalies(workspace_id)
    return {"alerts_generated": len(alerts), "alerts": alerts}


@router.get("/alerts")
async def get_alerts(
    workspace_id: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = GothamService(db)
    return await svc.get_active_alerts(workspace_id, severity, limit)


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: str,
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = GothamService(db)
    ok = await svc.acknowledge_alert(alert_id, _user.email)
    if not ok:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"acknowledged": True}
