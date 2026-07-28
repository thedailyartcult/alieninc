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


def get_tool_definitions() -> list[dict]:
    """Return tool definitions in OpenAI function-calling format."""
    return ONTOLOGY_TOOLS
