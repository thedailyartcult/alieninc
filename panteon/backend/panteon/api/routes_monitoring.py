from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, desc, and_, case
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from panteon.core.database import get_db
from panteon.core.auth import SupabaseUser, get_current_user
from panteon.core.audit import AuditLog
from panteon.core.lineage import LineageNode, LineageEdge, LineageEvent

router = APIRouter(prefix="/monitoring", tags=["Monitoring"])


@router.get("/summary")
async def get_summary(
    hours: int = Query(default=24, ge=1, le=720),
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    since = datetime.utcnow() - timedelta(hours=hours)

    total_reqs = await db.execute(
        select(func.count(AuditLog.id)).where(AuditLog.timestamp >= since)
    )
    total = total_reqs.scalar() or 0

    errors = await db.execute(
        select(func.count(AuditLog.id)).where(
            and_(AuditLog.timestamp >= since, AuditLog.status_code >= 400)
        )
    )
    error_count = errors.scalar() or 0

    auth_failures = await db.execute(
        select(func.count(AuditLog.id)).where(
            and_(AuditLog.timestamp >= since, AuditLog.status_code == 401)
        )
    )
    auth_fail_count = auth_failures.scalar() or 0

    avg_latency = await db.execute(
        select(func.avg(AuditLog.duration_ms)).where(AuditLog.timestamp >= since)
    )
    avg_ms = round(avg_latency.scalar() or 0, 1)

    p95_q = await db.execute(
        select(AuditLog.duration_ms)
        .where(and_(AuditLog.timestamp >= since, AuditLog.duration_ms.isnot(None)))
        .order_by(AuditLog.duration_ms.desc())
        .limit(1)
        .offset(max(0, int(total * 0.05)))
    )
    p95_ms = p95_q.scalar() or 0

    top_endpoints = await db.execute(
        select(AuditLog.path, func.count(AuditLog.id).label("count"))
        .where(and_(AuditLog.timestamp >= since, AuditLog.path.like("/api/%")))
        .group_by(AuditLog.path)
        .order_by(desc("count"))
        .limit(10)
    )
    endpoints = [{"path": r[0], "count": r[1]} for r in top_endpoints.all()]

    top_errors = await db.execute(
        select(AuditLog.path, AuditLog.status_code, func.count(AuditLog.id).label("count"))
        .where(and_(AuditLog.timestamp >= since, AuditLog.status_code >= 400))
        .group_by(AuditLog.path, AuditLog.status_code)
        .order_by(desc("count"))
        .limit(10)
    )
    error_endpoints = [{"path": r[0], "status": r[1], "count": r[2]} for r in top_errors.all()]

    active_users = await db.execute(
        select(AuditLog.user_email, func.count(AuditLog.id).label("count"))
        .where(and_(AuditLog.timestamp >= since, AuditLog.user_email.isnot(None)))
        .group_by(AuditLog.user_email)
        .order_by(desc("count"))
        .limit(20)
    )
    users = [{"email": r[0], "requests": r[1]} for r in active_users.all()]

    status_dist = await db.execute(
        select(AuditLog.status_code, func.count(AuditLog.id).label("count"))
        .where(AuditLog.timestamp >= since)
        .group_by(AuditLog.status_code)
        .order_by(AuditLog.status_code)
    )
    status_codes = {r[0]: r[1] for r in status_dist.all()}

    lineage_nodes = await db.execute(select(func.count(LineageNode.id)))
    lineage_edges = await db.execute(select(func.count(LineageEdge.id)))
    lineage_events = await db.execute(
        select(func.count(LineageEvent.id)).where(LineageEvent.created_at >= since)
    )

    return {
        "period_hours": hours,
        "total_requests": total,
        "error_count": error_count,
        "error_rate": round(error_count / max(total, 1) * 100, 2),
        "auth_failures": auth_fail_count,
        "avg_latency_ms": avg_ms,
        "p95_latency_ms": p95_ms,
        "top_endpoints": endpoints,
        "top_errors": error_endpoints,
        "active_users": users,
        "status_distribution": status_codes,
        "lineage": {
            "nodes": lineage_nodes.scalar() or 0,
            "edges": lineage_edges.scalar() or 0,
            "events_in_period": lineage_events.scalar() or 0,
        },
    }


@router.get("/health-history")
async def get_health_history(
    hours: int = Query(default=24, ge=1, le=720),
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    since = datetime.utcnow() - timedelta(hours=hours)
    bucket_size = max(1, hours // 24)

    result = await db.execute(
        select(
            func.strftime('%Y-%m-%d %H:00:00', AuditLog.timestamp).label("bucket"),
            func.count(AuditLog.id).label("total"),
            func.sum(case((AuditLog.status_code >= 500, 1), else_=0)).label("errors_5xx"),
            func.sum(case((AuditLog.status_code >= 400, 1), else_=0)).label("errors_4xx"),
            func.avg(AuditLog.duration_ms).label("avg_ms"),
        )
        .where(AuditLog.timestamp >= since)
        .group_by("bucket")
        .order_by("bucket")
    )
    return [
        {
            "timestamp": r[0],
            "total_requests": r[1],
            "errors_5xx": r[2] or 0,
            "errors_4xx": r[3] or 0,
            "avg_latency_ms": round(r[4] or 0, 1),
        }
        for r in result.all()
    ]
