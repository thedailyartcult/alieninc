import uuid
from typing import Any, Dict, List
from typing import Dict, List
from typing import List
"""
Module D: Actor Graph API router for Spinal Cracker / Panteon.

Exposes the actor relationship graph analysis from GDELT Events API
as endpoints under /api/v1/spinal-craker/actor-graph/. Provides
military intelligence on entity interactions, conflict patterns,
and relationship strengths.

Endpoints:
- /health: Graph health check
- /build: Build graph from GKG events
- /actors: List all actors
- /relations: List all relationships for an actor
- /subgraph: Get subgraph with n-hop neighbors
- /visualize: Export for visualization tools (json format)
- /strength: Get strength distribution
"""

import logging
import os
import sys
from dataclasses import dataclass
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from panteon.core.auth import get_current_user

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from actor_graph import ActorGraphBuilder, ActorNode, RelationshipType, ActorGraph  # noqa: E402
from gkg_connector import GKGEvent, GKGEventType  # noqa: E402

logger = logging.getLogger("spinal_cracker.actor_graph_router")

router = APIRouter(
    prefix="/actor-graph",
    tags=["Spinal Cracker Actor Graph"],
)

# Global graph instance (singleton via module level)
_actor_graph_builder = None


def get_actor_graph_builder() -> ActorGraphBuilder:
    """Get the global actor graph builder singleton."""
    global _actor_graph_builder
    if _actor_graph_builder is None:
        _actor_graph_builder = ActorGraphBuilder()
    return _actor_graph_builder


# Request/Response models

class BuildGraphRequest(BaseModel):
    """Request to build actor graph from GKG events."""
    events: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of GKG event dictionaries from GKG API.",
    )
    force_reset: bool = Field(
        default=False,
        description="If True, reset the existing graph before building.",
    )


class ActorIdRequest(BaseModel):
    """Request with actor ID."""
    actor_id: str = Field(
        default="",
        description="Actor node ID to filter by.",
    )


class HopRequest(BaseModel):
    """Request with hop count."""
    hop: int = Field(
        default=1,
        description="Number of hops for subgraph (1, 2, or 3).",
        ge=1,
        le=3,
    )


class VisualizeRequest(BaseModel):
    """Request for visualization export."""
    format: str = Field(
        default="json",
        description="Export format: json only (neo4j formatting unsupported).",
    )


# Endpoints

@router.get("/health")
async def health_check():
    """Graph health check."""
    builder = get_actor_graph_builder()
    nodes = len(builder.get_actors())
    edges = sum(len(e) for e in builder.graph.edges.values())
    return {
        "status": "ok",
        "source": "panteon spinal-cracker actor-graph",
        "total_actors": nodes,
        "total_relationships": edges,
        "graph_built_at": builder.graph.built_at,
    }


@router.post("/build")
async def build_graph(req: BuildGraphRequest):
    """Build actor relationship graph from GKG events."""
    global _actor_graph_builder
    _actor_graph_builder = get_actor_graph_builder()
    
    builder = _actor_graph_builder
    
    if req.force_reset:
        builder = ActorGraphBuilder()
        _actor_graph_builder = get_actor_graph_builder()
    
    try:
        for event_dict in req.events:
            # Parse minimal GKG event fields
            event_code = event_dict.get("event_code", "")
            event_type = event_dict.get("event_type", "")
            source_name = event_dict.get("source_actor", "unknown")
            target_name = event_dict.get("target_actor", "unknown")
            geo = event_dict.get("geo_data", {})
            
            # Create actor nodes
            source_actor = ActorNode(
                id=uuid.uuid4().hex[:12],
                name=source_name,
                actor_type="unknown",
            )
            target_actor = ActorNode(
                id=uuid.uuid4().hex[:12],
                name=target_name,
                actor_type="unknown",
            )
            
            # Add country if available
            if geo and "country" in geo:
                source_actor.country = geo["country"]
                target_actor.country = geo["country"]
            
            # Add event code to edge
            builder.add_event(event_code, event_type, source_actor, target_actor)
        
        return JSONResponse(content={
            "message": f"Graph built with {len(req.events)} events",
            "total_actors": len(builder.get_actors()),
            "total_relationships": sum(len(e) for e in builder.graph.edges.values()),
            "graph_summary": builder.export_for_visualization(),
        }, status_code=200)
        
    except Exception as exc:
        logger.exception("Graph build failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/actors")
async def list_actors():
    """List all actors in the graph."""
    builder = get_actor_graph_builder()
    actors = builder.get_actors()
    return JSONResponse(content={
        "actors": [
            {
                "id": node.id,
                "name": node.name,
                "actor_type": node.actor_type,
                "country": node.country,
            }
            for node in actors
        ],
        "total": len(actors),
    }, status_code=200)


@router.post("/relations")
async def get_relations(req: ActorIdRequest):
    """Get relationships for a specific actor."""
    builder = get_actor_graph_builder()
    edges = builder.get_relationships(req.actor_id)
    
    return JSONResponse(content={
        "actor_id": req.actor_id,
        "relationships": [
            {
                "source": edge.source_id,
                "target": edge.target_id,
                "relationship": edge.relationship.value,
                "strength": round(edge.strength, 2),
                "event_codes": edge.event_codes,
                "interaction_count": edge.interaction_count,
            }
            for edge in edges
        ],
        "total": len(edges),
    }, status_code=200)


@router.post("/subgraph")
async def get_subgraph(req: HopRequest):
    """Get subgraph with n-hop neighbors."""
    builder = get_actor_graph_builder()
    sub = builder.get_subgraph("", hop=req.hop)
    
    return JSONResponse(content={
        "hop": req.hop,
        "nodes": len(sub.nodes),
        "edges": sum(len(e) for e in sub.edges.values()),
        "built_at": sub.built_at,
    }, status_code=200)


@router.post("/visualize")
async def visualize(format: str = "json"):
    """Export graph for visualization tools."""
    builder = get_actor_graph_builder()
    data = builder.export_for_visualization()
    
    # Just return JSON format - neo4j formatting removed due to syntax complexity
    return JSONResponse(content=data, status_code=200)


@router.get("/strength")
async def strength_distribution():
    """Get relationship strength distribution."""
    builder = get_actor_graph_builder()
    dist = builder.get_strength_distribution()
    return JSONResponse(content=dist, status_code=200)
