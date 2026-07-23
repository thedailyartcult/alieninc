from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from panteon.core.database import get_db
from panteon.core.auth import SupabaseUser, get_current_user
from panteon.contour.service import ContourService

router = APIRouter(prefix="/contour", tags=["Contour Analytics"])


class DashboardCreate(BaseModel):
    name: str
    description: Optional[str] = None
    workspace_id: Optional[str] = None
    layout: Optional[dict] = None
    is_public: bool = False


class DashboardUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    layout: Optional[dict] = None
    filters: Optional[list] = None
    is_public: Optional[bool] = None


class ChartCreate(BaseModel):
    dashboard_id: str
    title: str
    chart_type: str
    data_source: dict
    config: Optional[dict] = None
    position: Optional[dict] = None
    refresh_interval_seconds: int = 300


class ScheduleCreate(BaseModel):
    pipeline_id: str
    name: str
    cron_expression: str
    timezone: str = "UTC"
    workspace_id: Optional[str] = None
    retry_count: int = 3


class DQRuleCreate(BaseModel):
    name: str
    object_type_id: str
    rule_type: str
    config: dict
    severity: str = "warning"
    workspace_id: Optional[str] = None


# ================================================================
# DASHBOARDS
# ================================================================

@router.post("/dashboards")
async def create_dashboard(data: DashboardCreate, _user: SupabaseUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    svc = ContourService(db)
    d = await svc.create_dashboard(name=data.name, description=data.description, workspace_id=data.workspace_id, layout=data.layout, created_by=_user.email, is_public=data.is_public)
    return {"id": str(d.id), "name": d.name}


@router.get("/dashboards")
async def list_dashboards(workspace_id: Optional[str] = None, limit: int = Query(default=50, le=200), _user: SupabaseUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    svc = ContourService(db)
    return await svc.list_dashboards(workspace_id, limit)


@router.get("/dashboards/{dashboard_id}")
async def get_dashboard(dashboard_id: str, _user: SupabaseUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    svc = ContourService(db)
    result = await svc.get_dashboard(dashboard_id)
    if not result:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    return result


@router.patch("/dashboards/{dashboard_id}")
async def update_dashboard(dashboard_id: str, data: DashboardUpdate, _user: SupabaseUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    svc = ContourService(db)
    updates = {k: v for k, v in data.model_dump().items() if v is not None}
    result = await svc.update_dashboard(dashboard_id, updates)
    if not result:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    return {"id": str(result.id), "name": result.name}


@router.delete("/dashboards/{dashboard_id}")
async def delete_dashboard(dashboard_id: str, _user: SupabaseUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    svc = ContourService(db)
    ok = await svc.delete_dashboard(dashboard_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    return {"deleted": True}


# ================================================================
# CHARTS
# ================================================================

@router.post("/charts")
async def add_chart(data: ChartCreate, _user: SupabaseUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    svc = ContourService(db)
    try:
        chart = await svc.add_chart(dashboard_id=data.dashboard_id, title=data.title, chart_type=data.chart_type, data_source=data.data_source, config=data.config, position=data.position, refresh_interval_seconds=data.refresh_interval_seconds)
        return {"id": str(chart.id), "title": chart.title, "chart_type": chart.chart_type}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/charts/{chart_id}/query")
async def execute_chart_query(chart_id: str, _user: SupabaseUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    svc = ContourService(db)
    try:
        return await svc.execute_chart_query(chart_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ================================================================
# PIPELINE SCHEDULING
# ================================================================

@router.post("/schedules")
async def create_schedule(data: ScheduleCreate, _user: SupabaseUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    svc = ContourService(db)
    s = await svc.create_schedule(pipeline_id=data.pipeline_id, name=data.name, cron_expression=data.cron_expression, timezone=data.timezone, workspace_id=data.workspace_id, retry_count=data.retry_count, created_by=_user.email)
    return {"id": str(s.id), "name": s.name, "next_run_at": s.next_run_at.isoformat() if s.next_run_at else None}


@router.get("/schedules")
async def list_schedules(workspace_id: Optional[str] = None, _user: SupabaseUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    svc = ContourService(db)
    return await svc.list_schedules(workspace_id)


@router.post("/schedules/{schedule_id}/toggle")
async def toggle_schedule(schedule_id: str, enabled: bool = Query(...), _user: SupabaseUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    svc = ContourService(db)
    ok = await svc.toggle_schedule(schedule_id, enabled)
    if not ok:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {"toggled": True, "enabled": enabled}


@router.post("/schedules/{schedule_id}/run")
async def run_schedule(schedule_id: str, _user: SupabaseUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    svc = ContourService(db)
    try:
        return await svc.run_schedule(schedule_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/schedules/{schedule_id}/runs")
async def get_schedule_runs(schedule_id: str, limit: int = Query(default=20, le=100), _user: SupabaseUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    svc = ContourService(db)
    return await svc.get_schedule_runs(schedule_id, limit)


# ================================================================
# DATA QUALITY
# ================================================================

@router.post("/data-quality/rules")
async def create_dq_rule(data: DQRuleCreate, _user: SupabaseUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    svc = ContourService(db)
    try:
        rule = await svc.create_dq_rule(name=data.name, object_type_id=data.object_type_id, rule_type=data.rule_type, config=data.config, severity=data.severity, workspace_id=data.workspace_id)
        return {"id": str(rule.id), "name": rule.name, "rule_type": rule.rule_type}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/data-quality/check")
async def run_dq_checks(workspace_id: Optional[str] = None, _user: SupabaseUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    svc = ContourService(db)
    return await svc.run_dq_checks(workspace_id)


@router.get("/data-quality/violations")
async def get_dq_violations(limit: int = Query(default=50, le=200), status: str = "open", _user: SupabaseUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    svc = ContourService(db)
    return await svc.get_dq_violations(limit, status)


# ================================================================
# SEARCH
# ================================================================

@router.get("/search")
async def search(query: str = Query(..., min_length=2), workspace_id: Optional[str] = None, object_type: Optional[str] = None, limit: int = Query(default=50, le=200), _user: SupabaseUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    svc = ContourService(db)
    return await svc.search(query, workspace_id, object_type, limit)


@router.post("/search/rebuild-index")
async def rebuild_search_index(workspace_id: Optional[str] = None, _user: SupabaseUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    svc = ContourService(db)
    return await svc.rebuild_search_index(workspace_id)
