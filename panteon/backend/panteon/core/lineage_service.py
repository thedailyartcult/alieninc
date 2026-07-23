import uuid
from typing import Optional
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from panteon.core.lineage import LineageNode, LineageEdge, LineageEvent
from panteon.core.database import is_sqlite


def _uid(val) -> str:
    if is_sqlite and val is not None:
        return str(val)
    return val


class LineageService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_or_create_node(
        self,
        node_type: str,
        node_id: str,
        name: str,
        description: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> LineageNode:
        result = await self.db.execute(
            select(LineageNode).where(
                and_(LineageNode.node_type == node_type, LineageNode.node_id == node_id)
            )
        )
        node = result.scalar_one_or_none()
        if node:
            if name != node.name or (description and description != node.description):
                node.name = name
                if description:
                    node.description = description
                if metadata:
                    node.metadata_json = {**(node.metadata_json or {}), **metadata}
                await self.db.flush()
            return node

        node = LineageNode(
            node_type=node_type,
            node_id=node_id,
            name=name,
            description=description,
            metadata_json=metadata or {},
        )
        self.db.add(node)
        await self.db.flush()
        return node

    async def create_edge(
        self,
        upstream_node_id: str,
        downstream_node_id: str,
        edge_type: str,
        description: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> LineageEdge:
        existing = await self.db.execute(
            select(LineageEdge).where(
                and_(
                    LineageEdge.upstream_node_id == _uid(upstream_node_id),
                    LineageEdge.downstream_node_id == _uid(downstream_node_id),
                    LineageEdge.edge_type == edge_type,
                )
            )
        )
        edge = existing.scalar_one_or_none()
        if edge:
            return edge

        edge = LineageEdge(
            upstream_node_id=_uid(upstream_node_id),
            downstream_node_id=_uid(downstream_node_id),
            edge_type=edge_type,
            description=description,
            metadata_json=metadata or {},
        )
        self.db.add(edge)
        await self.db.flush()
        return edge

    async def record_event(
        self,
        node_id: str,
        event_type: str,
        actor: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> LineageEvent:
        event = LineageEvent(
            node_id=_uid(node_id),
            event_type=event_type,
            actor=actor,
            details=details or {},
        )
        self.db.add(event)
        await self.db.flush()
        return event

    async def get_upstream(self, node_id: str, depth: int = 3) -> list[dict]:
        return await self._traverse(node_id, direction="upstream", depth=depth)

    async def get_downstream(self, node_id: str, depth: int = 3) -> list[dict]:
        return await self._traverse(node_id, direction="downstream", depth=depth)

    async def _traverse(self, node_id: str, direction: str, depth: int) -> list[dict]:
        result = await self.db.execute(
            select(LineageNode).where(LineageNode.id == _uid(node_id))
        )
        root = result.scalar_one_or_none()
        if not root:
            return []

        visited = set()
        graph = []
        await self._walk(root, direction, depth, visited, graph)
        return graph

    async def _walk(
        self, node: LineageNode, direction: str, depth: int, visited: set, graph: list
    ):
        if node.id in visited or depth < 0:
            return
        visited.add(node.id)

        node_data = {
            "id": str(node.id),
            "node_type": node.node_type,
            "node_id": node.node_id,
            "name": node.name,
            "description": node.description,
            "metadata": node.metadata_json,
            "edges": [],
        }

        if direction == "upstream":
            result = await self.db.execute(
                select(LineageEdge)
                .where(LineageEdge.downstream_node_id == _uid(node.id))
            )
            edges = result.scalars().all()
            for edge in edges:
                node_data["edges"].append({
                    "id": str(edge.id),
                    "edge_type": edge.edge_type,
                    "direction": "upstream",
                    "connected_node_id": str(edge.upstream_node_id),
                })
                upstream_result = await self.db.execute(
                    select(LineageNode).where(LineageNode.id == _uid(edge.upstream_node_id))
                )
                upstream = upstream_result.scalar_one_or_none()
                if upstream:
                    await self._walk(upstream, direction, depth - 1, visited, graph)
        else:
            result = await self.db.execute(
                select(LineageEdge)
                .where(LineageEdge.upstream_node_id == _uid(node.id))
            )
            edges = result.scalars().all()
            for edge in edges:
                node_data["edges"].append({
                    "id": str(edge.id),
                    "edge_type": edge.edge_type,
                    "direction": "downstream",
                    "connected_node_id": str(edge.downstream_node_id),
                })
                downstream_result = await self.db.execute(
                    select(LineageNode).where(LineageNode.id == _uid(edge.downstream_node_id))
                )
                downstream = downstream_result.scalar_one_or_none()
                if downstream:
                    await self._walk(downstream, direction, depth - 1, visited, graph)

        graph.append(node_data)

    async def get_full_graph(self) -> dict:
        nodes_result = await self.db.execute(select(LineageNode))
        nodes = nodes_result.scalars().all()

        edges_result = await self.db.execute(select(LineageEdge))
        edges = edges_result.scalars().all()

        return {
            "nodes": [
                {
                    "id": str(n.id),
                    "node_type": n.node_type,
                    "node_id": n.node_id,
                    "name": n.name,
                    "description": n.description,
                    "metadata": n.metadata_json,
                }
                for n in nodes
            ],
            "edges": [
                {
                    "id": str(e.id),
                    "upstream_node_id": str(e.upstream_node_id),
                    "downstream_node_id": str(e.downstream_node_id),
                    "edge_type": e.edge_type,
                    "description": e.description,
                    "metadata": e.metadata_json,
                }
                for e in edges
            ],
        }

    async def get_recent_events(self, limit: int = 50) -> list[dict]:
        result = await self.db.execute(
            select(LineageEvent)
            .order_by(LineageEvent.created_at.desc())
            .limit(limit)
        )
        events = result.scalars().all()
        return [
            {
                "id": str(e.id),
                "node_id": str(e.node_id),
                "event_type": e.event_type,
                "actor": e.actor,
                "details": e.details,
                "created_at": e.created_at.isoformat(),
            }
            for e in events
        ]
