"""
Ontology Tools — The bridge between YONO agents and the Spinal Craker ontology.

Following Palantir AIP architecture:
- Agents never access raw databases
- All data access goes through governed ontology interfaces
- Every operation is auditable and permission-checked
"""

import json
import uuid
from typing import Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from panteon.spinal_craker.service import OntologyService


# ── Tool Definitions (JSON Schema for LLM function calling) ──────────────

ONTOLOGY_TOOLS = [
    {
        "name": "list_object_types",
        "description": "List all object types defined in the ontology. Use this to discover what kinds of entities exist in the system (e.g. patrons, reflections, publishers).",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "query_objects",
        "description": "Query objects of a specific type from the ontology. Returns object instances with their properties. Use list_object_types first to find the correct type name.",
        "parameters": {
            "type": "object",
            "properties": {
                "type_name": {
                    "type": "string",
                    "description": "The name of the object type to query (e.g. 'tdac_patron', 'tdac_reflection')"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of objects to return (default 20, max 100)",
                    "default": 20
                },
                "property_filters": {
                    "type": "object",
                    "description": "Optional exact-match filters on object properties (e.g. {\"subscription_tier\": \"active\"})",
                    "default": {}
                }
            },
            "required": ["type_name"]
        }
    },
    {
        "name": "get_object",
        "description": "Get a single object by its ID. Returns the full object with all properties.",
        "parameters": {
            "type": "object",
            "properties": {
                "object_id": {
                    "type": "string",
                    "description": "The UUID of the object to retrieve"
                }
            },
            "required": ["object_id"]
        }
    },
    {
        "name": "get_object_links",
        "description": "Get relationships (links) for an object. Shows how this object is connected to other objects in the ontology.",
        "parameters": {
            "type": "object",
            "properties": {
                "object_id": {
                    "type": "string",
                    "description": "The UUID of the object"
                },
                "direction": {
                    "type": "string",
                    "enum": ["outgoing", "incoming"],
                    "description": "Direction of links to retrieve (default: outgoing)",
                    "default": "outgoing"
                }
            },
            "required": ["object_id"]
        }
    },
    {
        "name": "search_objects",
        "description": "Search for objects by property values. Useful for finding specific entities matching criteria.",
        "parameters": {
            "type": "object",
            "properties": {
                "type_name": {
                    "type": "string",
                    "description": "The object type name to search within"
                },
                "property_filters": {
                    "type": "object",
                    "description": "Property key-value pairs to filter by (exact match)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results (default 20)",
                    "default": 20
                }
            },
            "required": ["type_name", "property_filters"]
        }
    },
    {
        "name": "execute_action",
        "description": "Execute a governed action on an object. Actions are write operations that modify ontology state. Use list_action_types first to discover available actions.",
        "parameters": {
            "type": "object",
            "properties": {
                "action_name": {
                    "type": "string",
                    "description": "The name of the action type to execute"
                },
                "object_id": {
                    "type": "string",
                    "description": "The UUID of the target object (optional for some actions)"
                },
                "parameters": {
                    "type": "object",
                    "description": "Action parameters as defined by the action type's parameters_schema",
                    "default": {}
                }
            },
            "required": ["action_name"]
        }
    },
    {
        "name": "list_action_types",
        "description": "List all available action types in the ontology. Actions are governed write operations that can modify object state.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "recent_objects",
        "description": "Get the most recently updated objects across object types, newest first. This is the preferred tool for 'latest/latest activity/what changed' questions.",
        "parameters": {
            "type": "object",
            "properties": {
                "type_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional restriction to specific object type names (e.g. ['kriegspiel_assessment','maven_task']). Omit to cover all readable types.",
                    "default": []
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum objects to return (default 10, max 50)",
                    "default": 10
                }
            },
            "required": []
        }
    },
    {
        "name": "find_objects",
        "description": "Keyword search across object primary keys and properties when exact property filters do not apply (semantic-style fallback). Returns matches ranked by recency.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Keyword or phrase to look for (e.g. 'Taiwan Strait', 'S-400')"
                },
                "type_name": {
                    "type": "string",
                    "description": "Optional single object type name to restrict the search"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results (default 15, max 50)",
                    "default": 15
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_ontology_graph",
        "description": "Get ontology overview: object counts per type and link counts per link type. Use for 'what do we have / how much data' questions.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "set_map_view",
        "description": "Move the common operating picture (fusion map). Provide EITHER center+zoom OR bounds. Use whenever the operator asks to focus/show/fly somewhere geospatially.",
        "parameters": {
            "type": "object",
            "properties": {
                "center": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "[longitude, latitude]"
                },
                "zoom": {
                    "type": "number",
                    "description": "Map zoom level 1-18 (use >=7 for city-level focus)"
                },
                "bounds": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "number"}},
                    "description": "[[south, west], [north, east]]"
                }
            },
            "required": []
        }
    },
    {
        "name": "highlight_objects",
        "description": "Highlight specific ontology objects on the fusion map by their primary key values (e.g. theater or force names). Combine with set_map_view for focus.",
        "parameters": {
            "type": "object",
            "properties": {
                "primary_keys": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Primary key values of the objects to highlight (max 50)"
                },
                "type_name": {
                    "type": "string",
                    "description": "Optional object type name to scope highlighting"
                }
            },
            "required": ["primary_keys"]
        }
    },
    {
        "name": "toggle_layer",
        "description": "Show/hide a map layer on the common operating picture: threats, aviation, sims-ontology, or 3d buildings.",
        "parameters": {
            "type": "object",
            "properties": {
                "layer": {
                    "type": "string",
                    "enum": ["threats", "aviation", "sims-ontology", "3d"],
                    "description": "The layer to toggle"
                },
                "visible": {
                    "type": "boolean",
                    "description": "true=show, false=hide; omit to flip current state"
                }
            },
            "required": ["layer"]
        }
    },
]


# ── Tool Execution ───────────────────────────────────────────────────────

class OntologyToolExecutor:
    """
    Executes ontology tools on behalf of an agent.
    
    In Palantir AIP terms, this is the "Ontology API" layer —
    the governed interface through which agents interact with the ontology.
    """

    def __init__(self, db: AsyncSession, agent_id: uuid.UUID):
        self.db = db
        self.agent_id = agent_id
        self.ontology = OntologyService(db)
        self._type_cache: dict[str, Any] = {}
        self._action_cache: dict[str, Any] = {}

    async def _resolve_type(self, type_name: str) -> Optional[Any]:
        """Resolve an object type by name, with caching."""
        if type_name not in self._type_cache:
            obj_type = await self.ontology.get_object_type_by_name(type_name)
            if obj_type:
                self._type_cache[type_name] = obj_type
        return self._type_cache.get(type_name)

    async def _resolve_action(self, action_name: str) -> Optional[Any]:
        """Resolve an action type by name, with caching."""
        if action_name not in self._action_cache:
            from panteon.spinal_craker.models import ActionType
            from sqlalchemy import select
            result = await self.db.execute(
                select(ActionType).where(ActionType.name == action_name)
            )
            action = result.scalar_one_or_none()
            if action:
                self._action_cache[action_name] = action
        return self._action_cache.get(action_name)

    async def execute(self, tool_name: str, arguments: dict) -> dict:
        """
        Execute a tool by name with given arguments.
        Returns a result dict suitable for inclusion in LLM context.
        """
        try:
            handler = getattr(self, f"_tool_{tool_name}", None)
            if not handler:
                return {"error": f"Unknown tool: {tool_name}"}
            return await handler(arguments)
        except Exception as e:
            return {"error": f"Tool execution failed: {str(e)}"}

    async def _tool_list_object_types(self, args: dict) -> dict:
        """List all object types in the ontology."""
        types = await self.ontology.list_object_types()
        return {
            "object_types": [
                {
                    "name": t.name,
                    "display_name": t.display_name,
                    "description": t.description,
                    "properties_schema": t.properties_schema,
                    "object_count": len(t.objects) if hasattr(t, 'objects') else "unknown"
                }
                for t in types
            ]
        }

    async def _tool_query_objects(self, args: dict) -> dict:
        """Query objects by type with optional filters."""
        type_name = args["type_name"]
        limit = min(args.get("limit", 20), 100)
        property_filters = args.get("property_filters", {})

        obj_type = await self._resolve_type(type_name)
        if not obj_type:
            return {"error": f"Object type '{type_name}' not found"}

        if property_filters:
            objects = await self.ontology.search_objects(
                object_type_id=obj_type.id,
                property_filters=property_filters,
                limit=limit,
            )
        else:
            objects = await self.ontology.list_objects(
                object_type_id=obj_type.id,
                limit=limit,
            )

        return {
            "type": type_name,
            "count": len(objects),
            "objects": [
                {
                    "id": str(obj.id),
                    "primary_key": obj.primary_key_value,
                    "properties": obj.properties,
                    "created_at": obj.created_at.isoformat() if obj.created_at else None,
                }
                for obj in objects
            ]
        }

    async def _tool_get_object(self, args: dict) -> dict:
        """Get a single object by ID."""
        object_id = args["object_id"]
        obj = await self.ontology.get_object(uuid.UUID(object_id))
        if not obj:
            return {"error": f"Object {object_id} not found"}

        # Also get its links
        outgoing = await self.ontology.get_object_links(obj.id, "outgoing")
        incoming = await self.ontology.get_object_links(obj.id, "incoming")

        return {
            "id": str(obj.id),
            "type": obj.object_type.name if obj.object_type else "unknown",
            "primary_key": obj.primary_key_value,
            "properties": obj.properties,
            "outgoing_links": [
                {
                    "link_type": link.link_type.name if link.link_type else "unknown",
                    "target_id": str(link.target_object_id),
                    "target_key": link.target_object.primary_key_value if link.target_object else "unknown",
                    "properties": link.properties,
                }
                for link in outgoing
            ],
            "incoming_links": [
                {
                    "link_type": link.link_type.name if link.link_type else "unknown",
                    "source_id": str(link.source_object_id),
                    "source_key": link.source_object.primary_key_value if link.source_object else "unknown",
                    "properties": link.properties,
                }
                for link in incoming
            ],
        }

    async def _tool_get_object_links(self, args: dict) -> dict:
        """Get relationships for an object."""
        object_id = args["object_id"]
        direction = args.get("direction", "outgoing")

        obj = await self.ontology.get_object(uuid.UUID(object_id))
        if not obj:
            return {"error": f"Object {object_id} not found"}

        links = await self.ontology.get_object_links(obj.id, direction)

        return {
            "object_id": object_id,
            "direction": direction,
            "links": [
                {
                    "link_type": link.link_type.name if link.link_type else "unknown",
                    "link_display": link.link_type.display_name if link.link_type else "unknown",
                    "source_id": str(link.source_object_id),
                    "source_key": link.source_object.primary_key_value if link.source_object else "unknown",
                    "target_id": str(link.target_object_id),
                    "target_key": link.target_object.primary_key_value if link.target_object else "unknown",
                    "properties": link.properties,
                }
                for link in links
            ]
        }

    async def _tool_search_objects(self, args: dict) -> dict:
        """Search objects by property values."""
        type_name = args["type_name"]
        property_filters = args["property_filters"]
        limit = min(args.get("limit", 20), 100)

        obj_type = await self._resolve_type(type_name)
        if not obj_type:
            return {"error": f"Object type '{type_name}' not found"}

        objects = await self.ontology.search_objects(
            object_type_id=obj_type.id,
            property_filters=property_filters,
            limit=limit,
        )

        return {
            "type": type_name,
            "filters": property_filters,
            "count": len(objects),
            "objects": [
                {
                    "id": str(obj.id),
                    "primary_key": obj.primary_key_value,
                    "properties": obj.properties,
                }
                for obj in objects
            ]
        }

    async def _tool_execute_action(self, args: dict) -> dict:
        """Execute a governed action on an object."""
        action_name = args["action_name"]
        object_id = args.get("object_id")
        parameters = args.get("parameters", {})

        action_type = await self._resolve_action(action_name)
        if not action_type:
            return {"error": f"Action type '{action_name}' not found"}

        if not action_type.is_enabled:
            return {"error": f"Action type '{action_name}' is disabled"}

        execution = await self.ontology.execute_action(
            action_type_id=action_type.id,
            object_id=uuid.UUID(object_id) if object_id else None,
            parameters=parameters,
            executed_by=f"agent:{self.agent_id}",
        )

        return {
            "execution_id": str(execution.id),
            "action_name": action_name,
            "status": execution.status,
            "executed_at": execution.executed_at.isoformat() if execution.executed_at else None,
        }

    async def _tool_list_action_types(self, args: dict) -> dict:
        """List all available action types."""
        from panteon.spinal_craker.models import ActionType
        from sqlalchemy import select

        result = await self.db.execute(select(ActionType))
        actions = result.scalars().all()

        return {
            "action_types": [
                {
                    "name": a.name,
                    "display_name": a.display_name,
                    "description": a.description,
                    "object_type": a.object_type.name if a.object_type else "unknown",
                    "parameters_schema": a.parameters_schema,
                    "effects": a.effects,
                    "is_enabled": a.is_enabled,
                }
                for a in actions
            ]
        }

    # ── Panel tools (recent / keyword / graph / map directives) ─────────

    async def _readable_types(self, requested: Optional[list[str]] = None) -> list[str]:
        """Intersect requested type names with the agent's allowed reads."""
        from sqlalchemy import select
        from panteon.yono.models import Agent

        row = await self.db.execute(
            select(Agent.allowed_object_types).where(Agent.id == self.agent_id)
        )
        allowed = row.scalar() or []
        if not requested:
            return list(allowed)
        return [t for t in requested if t in allowed]

    async def _tool_recent_objects(self, args: dict) -> dict:
        """Most recently updated objects across readable types, newest first."""
        from sqlalchemy import select
        from panteon.spinal_craker.models import Object, ObjectType

        limit = min(int(args.get("limit", 10)), 50)
        type_names = await self._readable_types(args.get("type_names") or [])
        if not type_names:
            return {"error": "No readable object types for this agent", "objects": []}

        rows = await self.db.execute(
            select(Object, ObjectType.name)
            .join(ObjectType, Object.object_type_id == ObjectType.id)
            .where(ObjectType.name.in_(type_names))
            .order_by(Object.updated_at.desc(), Object.created_at.desc())
            .limit(limit)
        )
        objects = []
        for obj, tname in rows.all():
            objects.append({
                "id": str(obj.id),
                "type": tname,
                "primary_key": obj.primary_key_value,
                "properties": obj.properties,
                "updated_at": obj.updated_at.isoformat() if obj.updated_at else None,
            })
        return {"count": len(objects), "ordered_by": "updated_at desc", "objects": objects}

    async def _tool_find_objects(self, args: dict) -> dict:
        """Keyword search over primary keys + properties (semantic fallback)."""
        from sqlalchemy import select, or_, cast, String
        from panteon.spinal_craker.models import Object, ObjectType

        query = str(args.get("query", "")).strip()
        if not query:
            return {"error": "query is required"}
        limit = min(int(args.get("limit", 15)), 50)
        type_name = args.get("type_name")
        requested = [type_name] if type_name else None
        type_names = await self._readable_types(requested)
        if not type_names:
            return {"error": f"Type '{type_name}' not readable for this agent" if type_name
                    else "No readable object types for this agent", "matches": []}

        like = f"%{query}%"
        stmt = (
            select(Object, ObjectType.name)
            .join(ObjectType, Object.object_type_id == ObjectType.id)
            .where(ObjectType.name.in_(type_names))
            .where(or_(
                cast(Object.primary_key_value, String).ilike(like),
                cast(Object.properties, String).ilike(like),
            ))
            .order_by(Object.updated_at.desc())
            .limit(limit)
        )
        rows = await self.db.execute(stmt)
        matches = [
            {
                "id": str(obj.id),
                "type": tname,
                "primary_key": obj.primary_key_value,
                "properties": obj.properties,
            }
            for obj, tname in rows.all()
        ]
        return {"query": query, "count": len(matches), "matches": matches}

    async def _tool_get_ontology_graph(self, args: dict) -> dict:
        """Overview counts: objects per type, links per link type."""
        from sqlalchemy import select, func
        from panteon.spinal_craker.models import (
            Object, ObjectType, Link, LinkType,
        )

        obj_rows = await self.db.execute(
            select(ObjectType.name, func.count(Object.id))
            .outerjoin(Object, Object.object_type_id == ObjectType.id)
            .group_by(ObjectType.name)
        )
        link_rows = await self.db.execute(
            select(LinkType.name, func.count(Link.id))
            .outerjoin(Link, Link.link_type_id == LinkType.id)
            .group_by(LinkType.name)
        )
        by_type = {name: count for name, count in obj_rows.all()}
        links_by_type = {name: count for name, count in link_rows.all()}
        return {
            "object_counts_by_type": by_type,
            "link_counts_by_type": links_by_type,
            "total_objects": sum(by_type.values()),
            "total_links": sum(links_by_type.values()),
        }

    async def _tool_set_map_view(self, args: dict) -> dict:
        """Validate and echo a map-view directive for the panel to apply."""
        center = args.get("center")
        zoom = args.get("zoom")
        bounds = args.get("bounds")
        if bounds:
            try:
                (s, w), (n, e) = bounds
                if not (-90 <= s < n <= 90 and -180 <= w < e <= 180):
                    raise ValueError
            except (TypeError, ValueError):
                return {"error": "bounds must be [[south, west], [north, east]]"}
            directive = {"op": "fit_bounds", "bounds": [[s, w], [n, e]]}
        elif center is not None and zoom is not None:
            try:
                lng, lat = float(center[0]), float(center[1])
                z = max(1.0, min(float(zoom), 18.0))
            except (TypeError, ValueError, IndexError):
                return {"error": "center must be [lng, lat] with numeric zoom"}
            if not (-180 <= lng <= 180 and -85 <= lat <= 85):
                return {"error": "center out of range"}
            directive = {"op": "fly_to", "center": [lng, lat], "zoom": z}
        else:
            return {"error": "provide center+zoom or bounds"}
        return {"directive": directive}

    async def _tool_highlight_objects(self, args: dict) -> dict:
        """Echo a highlight directive for the panel to apply."""
        pks = args.get("primary_keys") or []
        pks = [str(p) for p in pks][:50]
        if not pks:
            return {"error": "primary_keys must be a non-empty list"}
        directive = {
            "op": "highlight",
            "primary_keys": pks,
            "type_name": args.get("type_name"),
        }
        return {"directive": directive}

    async def _tool_toggle_layer(self, args: dict) -> dict:
        """Echo a layer-visibility directive for the panel to apply."""
        layer = args.get("layer")
        if layer not in ("threats", "aviation", "sims-ontology", "3d"):
            return {"error": "layer must be one of threats|aviation|sims-ontology|3d"}
        directive = {"op": "toggle_layer", "layer": layer}
        if isinstance(args.get("visible"), bool):
            directive["visible"] = args["visible"]
        return {"directive": directive}

    # ── Governed actions: propose vs execute ────────────────────────────

    async def propose_action(self, args: dict) -> dict:
        """Record an action as a PROPOSAL awaiting human confirmation.

        Mirrors OntologyService.execute_action's ledger write but marks the
        row 'proposed' so nothing runs until /yono/proposals/{id}/confirm.
        """
        from panteon.spinal_craker.models import ActionExecution

        action_name = args["action_name"]
        object_id = args.get("object_id")
        parameters = args.get("parameters", {})

        action_type = await self._resolve_action(action_name)
        if not action_type:
            return {"error": f"Action type '{action_name}' not found"}
        if not action_type.is_enabled:
            return {"error": f"Action type '{action_name}' is disabled"}

        execution = ActionExecution(
            action_type_id=action_type.id,
            object_id=uuid.UUID(object_id) if object_id else None,
            parameters={
                "arguments": parameters,
                "action_name": action_name,
            },
            executed_by=f"yono-proposal:{self.agent_id}",
            status="proposed",
        )
        self.db.add(execution)
        await self.db.flush()
        schema = action_type.parameters_schema or {}
        missing = [k for k in schema.get("required", []) if k not in parameters]
        return {
            "proposal_id": str(execution.id),
            "action_name": action_name,
            "status": "proposed",
            "missing_required_parameters": missing,
            "note": (
                "Awaiting operator confirmation in the YONO panel. Do NOT "
                "state this action has executed until status becomes succeeded."
            ),
        }


def get_tool_definitions() -> list[dict]:
    """Return tool definitions in OpenAI function-calling format."""
    return ONTOLOGY_TOOLS
