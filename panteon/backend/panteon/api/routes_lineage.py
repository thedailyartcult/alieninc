import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from panteon.core.database import get_db
from panteon.core.auth import SupabaseUser, get_current_user
from panteon.core.lineage_service import LineageService

router = APIRouter(prefix="/lineage", tags=["Data Lineage"])


class NodeCreateRequest(BaseModel):
    node_type: str
    node_id: str
    name: str
    description: Optional[str] = None
    metadata: Optional[dict] = None


class EdgeCreateRequest(BaseModel):
    upstream_node_id: str
    downstream_node_id: str
    edge_type: str
    description: Optional[str] = None
    metadata: Optional[dict] = None


class EventCreateRequest(BaseModel):
    node_id: str
    event_type: str
    actor: Optional[str] = None
    details: Optional[dict] = None


@router.get("/graph")
async def get_full_graph(
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = LineageService(db)
    return await service.get_full_graph()


@router.get("/nodes/{node_id}/upstream")
async def get_upstream(
    node_id: str,
    depth: int = Query(default=3, ge=1, le=10),
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = LineageService(db)
    return await service.get_upstream(node_id, depth)


@router.get("/nodes/{node_id}/downstream")
async def get_downstream(
    node_id: str,
    depth: int = Query(default=3, ge=1, le=10),
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = LineageService(db)
    return await service.get_downstream(node_id, depth)


@router.get("/events")
async def get_recent_events(
    limit: int = Query(default=50, ge=1, le=500),
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = LineageService(db)
    return await service.get_recent_events(limit)


@router.post("/nodes")
async def create_node(
    data: NodeCreateRequest,
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = LineageService(db)
    node = await service.get_or_create_node(
        node_type=data.node_type,
        node_id=data.node_id,
        name=data.name,
        description=data.description,
        metadata=data.metadata,
    )
    return {
        "id": str(node.id),
        "node_type": node.node_type,
        "node_id": node.node_id,
        "name": node.name,
        "description": node.description,
        "metadata": node.metadata_json,
    }


@router.post("/edges")
async def create_edge(
    data: EdgeCreateRequest,
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = LineageService(db)
    edge = await service.create_edge(
        upstream_node_id=data.upstream_node_id,
        downstream_node_id=data.downstream_node_id,
        edge_type=data.edge_type,
        description=data.description,
        metadata=data.metadata,
    )
    return {
        "id": str(edge.id),
        "upstream_node_id": str(edge.upstream_node_id),
        "downstream_node_id": str(edge.downstream_node_id),
        "edge_type": edge.edge_type,
        "description": edge.description,
    }


@router.post("/events")
async def record_event(
    data: EventCreateRequest,
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = LineageService(db)
    event = await service.record_event(
        node_id=data.node_id,
        event_type=data.event_type,
        actor=data.actor or _user.email,
        details=data.details,
    )
    return {
        "id": str(event.id),
        "node_id": str(event.node_id),
        "event_type": event.event_type,
        "actor": event.actor,
        "created_at": event.created_at.isoformat(),
    }
