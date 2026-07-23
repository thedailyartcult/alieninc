from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, desc, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from panteon.core.database import get_db
from panteon.core.auth import SupabaseUser, get_current_user
from panteon.core.workspace import Workspace, WorkspaceMembership
from panteon.core.lineage import LineageNode, LineageEdge
from panteon.core.audit import AuditLog

router = APIRouter(prefix="/workspaces", tags=["Workspaces"])


class WorkspaceResponse(BaseModel):
    id: str
    name: str
    slug: str
    description: Optional[str]
    domain: Optional[str]
    workspace_type: str
    parent_workspace_id: Optional[str]
    is_active: bool
    created_at: str


class WorkspaceStats(BaseModel):
    workspace: WorkspaceResponse
    lineage_nodes: int
    lineage_edges: int
    audit_events_24h: int
    children_count: int


@router.get("", response_model=list[WorkspaceResponse])
async def list_workspaces(
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Workspace).order_by(Workspace.name))
    return [
        WorkspaceResponse(
            id=str(w.id), name=w.name, slug=w.slug, description=w.description,
            domain=w.domain, workspace_type=w.workspace_type,
            parent_workspace_id=str(w.parent_workspace_id) if w.parent_workspace_id else None,
            is_active=w.is_active, created_at=w.created_at.isoformat(),
        )
        for w in result.scalars().all()
    ]


@router.get("/{workspace_slug}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_slug: str,
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Workspace).where(Workspace.slug == workspace_slug))
    w = result.scalar_one_or_none()
    if not w:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return WorkspaceResponse(
        id=str(w.id), name=w.name, slug=w.slug, description=w.description,
        domain=w.domain, workspace_type=w.workspace_type,
        parent_workspace_id=str(w.parent_workspace_id) if w.parent_workspace_id else None,
        is_active=w.is_active, created_at=w.created_at.isoformat(),
    )


@router.get("/{workspace_slug}/stats", response_model=WorkspaceStats)
async def get_workspace_stats(
    workspace_slug: str,
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Workspace).where(Workspace.slug == workspace_slug))
    w = result.scalar_one_or_none()
    if not w:
        raise HTTPException(status_code=404, detail="Workspace not found")

    ws_info = WorkspaceResponse(
        id=str(w.id), name=w.name, slug=w.slug, description=w.description,
        domain=w.domain, workspace_type=w.workspace_type,
        parent_workspace_id=str(w.parent_workspace_id) if w.parent_workspace_id else None,
        is_active=w.is_active, created_at=w.created_at.isoformat(),
    )

    node_count = await db.execute(
        select(func.count(LineageNode.id)).where(LineageNode.workspace_id == str(w.id))
    )
    edge_count = await db.execute(
        select(func.count(LineageEdge.id)).where(
            LineageEdge.upstream_node_id.in_(
                select(LineageNode.id).where(LineageNode.workspace_id == str(w.id))
            )
        )
    )

    from datetime import datetime, timedelta
    since = datetime.utcnow() - timedelta(hours=24)
    audit_count = await db.execute(
        select(func.count(AuditLog.id)).where(AuditLog.timestamp >= since)
    )

    children = await db.execute(
        select(func.count(Workspace.id)).where(Workspace.parent_workspace_id == str(w.id))
    )

    return WorkspaceStats(
        workspace=ws_info,
        lineage_nodes=node_count.scalar() or 0,
        lineage_edges=edge_count.scalar() or 0,
        audit_events_24h=audit_count.scalar() or 0,
        children_count=children.scalar() or 0,
    )


@router.get("/{workspace_slug}/lineage")
async def get_workspace_lineage(
    workspace_slug: str,
    include_cross_workspace: bool = Query(default=True),
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Workspace).where(Workspace.slug == workspace_slug))
    w = result.scalar_one_or_none()
    if not w:
        raise HTTPException(status_code=404, detail="Workspace not found")

    if include_cross_workspace:
        nodes_result = await db.execute(
            select(LineageNode).where(
                (LineageNode.workspace_id == str(w.id)) | (LineageNode.node_type == "workspace")
            )
        )
    else:
        nodes_result = await db.execute(
            select(LineageNode).where(LineageNode.workspace_id == str(w.id))
        )
    nodes = nodes_result.scalars().all()
    node_ids = {str(n.id) for n in nodes}

    edges_result = await db.execute(select(LineageEdge))
    edges = [
        e for e in edges_result.scalars().all()
        if str(e.upstream_node_id) in node_ids or str(e.downstream_node_id) in node_ids
    ]

    return {
        "workspace": {"id": str(w.id), "name": w.name, "slug": w.slug},
        "nodes": [
            {
                "id": str(n.id), "node_type": n.node_type, "node_id": n.node_id,
                "name": n.name, "description": n.description,
                "workspace_id": n.workspace_id, "metadata": n.metadata_json,
            }
            for n in nodes
        ],
        "edges": [
            {
                "id": str(e.id),
                "upstream_node_id": str(e.upstream_node_id),
                "downstream_node_id": str(e.downstream_node_id),
                "edge_type": e.edge_type, "description": e.description,
            }
            for e in edges
        ],
    }
