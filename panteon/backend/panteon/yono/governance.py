"""
Governance Layer — Palantir AIP-style permission enforcement for YONO agents.

Every agent operation is checked against the agent's policy:
- What object types can it READ?
- What object types can it WRITE?
- What actions can it EXECUTE?
- What ontology context is auto-injected?

The agent inherits the user's permissions — it cannot escalate beyond them.
"""

import uuid
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from panteon.yono.models import Agent
from panteon.spinal_craker.service import OntologyService


class GovernanceVerdict:
    """Result of a governance check."""
    
    def __init__(self, allowed: bool, reason: str = "", context: dict = None):
        self.allowed = allowed
        self.reason = reason
        self.context = context or {}

    def __repr__(self):
        return f"GovernanceVerdict(allowed={self.allowed}, reason='{self.reason}')"


class GovernanceLayer:
    """
    Enforces agent permissions against the ontology.
    
    In Palantir AIP terms:
    - Context Layer: auto-injects relevant ontology data the agent is allowed to see
    - Query Layer: restricts which object types/properties the agent can query
    - Action Layer: restricts which actions the agent can execute
    - Every decision is logged for audit
    """

    def __init__(self, db: AsyncSession, agent: Agent):
        self.db = db
        self.agent = agent
        self.ontology = OntologyService(db)

    def check_read(self, type_name: str) -> GovernanceVerdict:
        """Check if agent can read objects of this type."""
        allowed = self.agent.allowed_object_types or []
        if not allowed:
            return GovernanceVerdict(
                allowed=False,
                reason=f"Agent '{self.agent.name}' has no read permissions. Configure allowed_object_types."
            )
        if type_name not in allowed:
            return GovernanceVerdict(
                allowed=False,
                reason=f"Agent '{self.agent.name}' is not authorized to read '{type_name}'. Allowed: {allowed}"
            )
        return GovernanceVerdict(allowed=True)

    def check_write(self, type_name: str) -> GovernanceVerdict:
        """Check if agent can write/modify objects of this type."""
        writable = self.agent.writable_object_types or []
        if not writable:
            return GovernanceVerdict(
                allowed=False,
                reason=f"Agent '{self.agent.name}' has no write permissions. Configure writable_object_types."
            )
        if type_name not in writable:
            return GovernanceVerdict(
                allowed=False,
                reason=f"Agent '{self.agent.name}' is not authorized to write '{type_name}'. Allowed: {writable}"
            )
        return GovernanceVerdict(allowed=True)

    def check_action(self, action_name: str) -> GovernanceVerdict:
        """Check if agent can execute this action type."""
        allowed_actions = self.agent.allowed_actions or []
        if not allowed_actions:
            return GovernanceVerdict(
                allowed=False,
                reason=f"Agent '{self.agent.name}' has no action permissions. Configure allowed_actions."
            )
        if action_name not in allowed_actions:
            return GovernanceVerdict(
                allowed=False,
                reason=f"Agent '{self.agent.name}' is not authorized to execute action '{action_name}'. Allowed: {allowed_actions}"
            )
        return GovernanceVerdict(allowed=True)

    async def build_context(self) -> str:
        """
        Auto-inject ontology context into the agent's prompt.
        
        This is the "Context Layer" from Palantir AIP —
        deterministic data injection before the LLM reasons.
        
        Returns a formatted string to prepend to the system prompt.
        """
        config = self.agent.ontology_context_config or {}
        if not config:
            return ""

        context_parts = ["## Ontology Context\n"]
        context_parts.append("The following data has been pre-loaded from the enterprise ontology:\n")

        for ctx in config.get("queries", []):
            type_name = ctx.get("type_name")
            filters = ctx.get("filters", {})
            label = ctx.get("label", type_name)

            if not type_name:
                continue

            # Governance check
            verdict = self.check_read(type_name)
            if not verdict.allowed:
                context_parts.append(f"### {label}: ACCESS DENIED — {verdict.reason}\n")
                continue

            obj_type = await self.ontology.get_object_type_by_name(type_name)
            if not obj_type:
                context_parts.append(f"### {label}: Type '{type_name}' not found\n")
                continue

            limit = ctx.get("limit", self.agent.max_context_objects or 20)

            if filters:
                objects = await self.ontology.search_objects(
                    object_type_id=obj_type.id,
                    property_filters=filters,
                    limit=limit,
                )
            else:
                objects = await self.ontology.list_objects(
                    object_type_id=obj_type.id,
                    limit=limit,
                )

            context_parts.append(f"### {label} ({len(objects)} records)\n")
            for obj in objects:
                props_str = ", ".join(f"{k}: {v}" for k, v in (obj.properties or {}).items())
                context_parts.append(f"- **{obj.primary_key_value}**: {props_str}\n")
            context_parts.append("\n")

        if len(context_parts) <= 2:
            return ""

        return "".join(context_parts)

    def filter_tool_list(self, tools: list[dict]) -> list[dict]:
        """
        Filter the ontology tool list based on agent permissions.
        
        Only expose tools the agent is authorized to use.
        """
        filtered = []
        for tool in tools:
            name = tool.get("name", "")
            
            # Read tools — check if agent has ANY read permissions
            if name in ("query_objects", "get_object", "get_object_links", "search_objects"):
                if self.agent.allowed_object_types:
                    filtered.append(tool)
                continue

            # List types — always allowed (discovery)
            if name in ("list_object_types",):
                filtered.append(tool)
                continue

            # Action tools — check if agent has action permissions
            if name in ("execute_action", "list_action_types"):
                if self.agent.allowed_actions:
                    filtered.append(tool)
                continue

            # Unknown tools — deny by default
            continue

        return filtered
