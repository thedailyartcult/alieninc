from datetime import datetime, timezone
from datetime import datetime
"""
Module D: actor_graph
GDELT Actor Relationship Graph — military intelligence analysis of entity interactions.

Builds a directed graph of actor interactions from GDELT events:
- Nodes: Governments, militaries, organizations, individuals
- Edges: Interaction strength, event types, geospatial data
- Attributes: Conflict involvement, cooperation metrics, threat levels

Uses CAMEO event codes from GKG Events API to classify relationships:
- ACTS_IN: Country participates in event
- SUPPORTS: One actor supports another
- OPPOSes: One actor opposes another
- COLLABORates: One actor collaborates with another
- MONITORs: One actor monitors another
"""

import uuid
import hashlib
import json
import time
import logging
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict

logger = logging.getLogger("actor.graph")


class RelationshipType(Enum):
    """Types of actor relationships from GDELT events."""
    ACTS_IN = "acts_in"           # Country participates in event
    SUPPORTS = "supports"         # One actor supports another
    OPPOSes = "opposes"           # One actor opposes another  
    COLLABORates = "collaborates" # One actor collaborates with another
    MONITORs = "monitors"         # One actor monitors another
    TRIGGERs = "triggers"         # One actor triggers another


@dataclass
class ActorNode:
    """Node in the actor relationship graph."""
    id: str
    name: str
    actor_type: str  # government, military, organization, individual, country
    country: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    node_id: str = ""  # GDELT entity ID


@dataclass
class RelationshipEdge:
    """Edge connecting two actor nodes."""
    source_id: str
    target_id: str
    relationship: RelationshipType
    strength: float  # 0.0 to 1.0, based on event frequency
    event_codes: List[str] = field(default_factory=list)
    last_interaction: str = ""  # ISO date of last event
    interaction_count: int = 0


@dataclass
class ActorGraph:
    """Complete actor relationship graph."""
    nodes: Dict[str, ActorNode] = field(default_factory=dict)
    edges: Dict[str, List[RelationshipEdge]] = field(default_factory=lambda: defaultdict(list))
    built_at: str = ""  # ISO timestamp
    total_interactions: int = 0


class ActorGraphBuilder:
    """Builds and maintains actor relationship graphs from GDELT events."""

    def __init__(self):
        self.graph: ActorGraph = ActorGraph()
        self.event_counter: Dict[str, int] = defaultdict(int)

    def add_event(self, event_code: str, event_type: str, 
                  source_actor: ActorNode, target_actor: ActorNode,
                  geo_data: Dict[str, Any] = None) -> None:
        """Add a GDELT event to the actor relationship graph."""
        # Classify relationship based on event code
        rel_type = self._classify_relationship(event_code)
        
        # Create or update nodes
        if source_actor.id not in self.graph.nodes:
            self.graph.nodes[source_actor.id] = source_actor
        if target_actor.id not in self.graph.nodes:
            self.graph.nodes[target_actor.id] = target_actor
        
        # Create or update edge
        edge_key = f"{source_actor.id}_{target_actor.id}"
        
        # Find existing edge
        existing_edges = self.graph.edges.get(edge_key, [])
        
        # Check if relationship type matches
        matching = [e for e in existing_edges if e.relationship == rel_type]
        
        if matching:
            # Update existing edge
            edge = matching[0]
            edge.strength = min(1.0, edge.strength + 0.1)
            edge.event_codes.append(event_code)
            edge.interaction_count += 1
            # Update last interaction date
            from datetime import datetime, timezone
            edge.last_interaction = datetime.now(timezone.utc).isoformat()[:10]
        else:
            # Create new edge
            new_edge = RelationshipEdge(
                source_id=source_actor.id,
                target_id=target_actor.id,
                relationship=rel_type,
                strength=0.1,
                event_codes=[event_code],
                last_interaction=datetime.now(timezone.utc).isoformat()[:10],
                interaction_count=1,
            )
            existing_edges.append(new_edge)
        
        self.graph.edges[edge_key] = existing_edges
        self.event_counter[event_code] = self.event_counter.get(event_code, 0) + 1
        self.graph.total_interactions += 1

    def _classify_relationship(self, event_code: str) -> RelationshipType:
        """Classify GDELT CAMEO event code into relationship type."""
        code = event_code[:4] if len(event_code) >= 4 else event_code
        
        classification = {
            "1010": RelationshipType.ACTS_IN,      # Riots - country acts in event
            "2010": RelationshipType.ACTS_IN,      # Demonstrations - country acts
            "3010": RelationshipType.OPPOSes,      # Attack - opposes
            "3110": RelationshipType.SUPPORts,     # Defense - supports
            "4010": RelationshipType.COLLABORates, # Propaganda - collaborates
            "5010": RelationshipType.MONITORs,     # Political - monitors
            "6010": RelationshipType.TRIGGERs,     # Military movement - triggers
            "7010": RelationshipType.ACTS_IN,      # Treaty - countries act
            "8010": RelationshipType.OPPOSes,      # Sanctions - opposes
        }
        
        return classification.get(code, RelationshipType.ACTS_IN)

    def get_actors(self) -> List[ActorNode]:
        """Return all actor nodes in the graph."""
        return list(self.graph.nodes.values())

    def get_relationships(self, actor_id: str = None) -> List[RelationshipEdge]:
        """Return all edges, optionally filtered by actor."""
        if actor_id:
            edges = []
            for edge_list in self.graph.edges.values():
                edges.extend([e for e in edge_list if e.source_id == actor_id or e.target_id == actor_id])
            return edges
        return [e for edge_list in self.graph.edges.values() for e in edge_list]

    def get_subgraph(self, actor_id: str, hop: int = 1) -> ActorGraph:
        """Get subgraph starting from actor with given hops."""
        sub = ActorGraph()
        sub.nodes = {actor_id: self.graph.nodes.get(actor_id)} if actor_id in self.graph.nodes else {}
        
        # Add 1-hop neighbors
        if hop >= 1 and actor_id in self.graph.edges:
            for edge in self.graph.edges.get(actor_id, []):
                neighbor_id = edge.target_id if edge.source_id == actor_id else edge.source_id
                if neighbor_id in self.graph.nodes:
                    sub.nodes[neighbor_id] = self.graph.nodes[neighbor_id]
                    sub.edges.setdefault(actor_id, []).append(edge)
        
        sub.built_at = datetime.now(timezone.utc).isoformat()
        sub.total_interactions = self.graph.total_interactions
        return sub

    def get_strength_distribution(self) -> Dict[str, int]:
        """Get distribution of relationship strengths."""
        dist = {"high": 0, "medium": 0, "low": 0}
        for edge_list in self.graph.edges.values():
            for edge in edge_list:
                if edge.strength >= 0.7:
                    dist["high"] += 1
                elif edge.strength >= 0.4:
                    dist["medium"] += 1
                else:
                    dist["low"] += 1
        return dist

    def export_for_visualization(self) -> Dict[str, Any]:
        """Export graph data for Neo4j, Cytoscape, or other visualization tools."""
        nodes_data = []
        for node_id, node in self.graph.nodes.items():
            nodes_data.append({
                "id": node.id,
                "label": node.name,
                "type": node.actor_type,
                "country": node.country,
                "metadata": node.metadata,
            })
        
        edges_data = []
        edge_ids = set()
        for edge_list in self.graph.edges.values():
            for edge in edge_list:
                edge_key = f"{edge.source_id}_{edge.target_id}_{edge.relationship.value}"
                if edge_key not in edge_ids:
                    edge_ids.add(edge_key)
                    edges_data.append({
                        "source": edge.source_id,
                        "target": edge.target_id,
                        "relationship": edge.relationship.value,
                        "strength": edge.strength,
                        "event_codes": edge.event_codes,
                        "interaction_count": edge.interaction_count,
                    })
        
        return {
            "nodes": nodes_data,
            "edges": edges_data,
            "total_nodes": len(self.graph.nodes),
            "total_edges": len(edges_data),
            "built_at": self.graph.built_at,
            "total_interactions": self.graph.total_interactions,
        }


# Global actor graph instance (singleton pattern)
_actor_graph_instance: ActorGraphBuilder = None


def get_actor_graph() -> ActorGraphBuilder:
    """Get the global actor graph builder singleton."""
    global _actor_graph_instance
    if _actor_graph_instance is None:
        _actor_graph_instance = ActorGraphBuilder()
    return _actor_graph_instance
