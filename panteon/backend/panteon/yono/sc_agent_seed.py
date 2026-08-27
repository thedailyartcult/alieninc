"""
Spinal Cracker YONO Panel Agent — idempotent seed (Palantir AIP-style).

Ensures a governed 'spinal-cracker-yono' agent exists, pinned to the enabled
Hetzner Qwen3.8-27B model, with read access to every registered object type,
a narrow write surface, and the AIP core-principles system prompt.

Follows the war_ontology.ensure_war_ontology pattern: safe to call on every
startup, updates-in-place only where noted, never raises.
"""

import logging
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("panteon.yono.sc_seed")

SC_YONO_AGENT_NAME = "spinal-cracker-yono"
PREFERRED_MODEL_ID = "Qwen3.8-27B"

# Write surface is deliberately narrow (Propose+Confirm flow guards execution).
WRITABLE_OBJECT_TYPES = ["maven_task", "maven_coa", "kriegspiel_assessment"]
ALLOWED_ACTIONS = ["kriegspiel_run_battle"]

SC_YONO_SYSTEM_PROMPT = """You are YONO — the Artificial Intelligence Platform Agent embedded in Panteon's Spinal Cracker operational decision platform (our in-house Palantir-AIP-equivalent, branded YONO). You help operators explore, analyze, and act on operational data using natural language.

## Core Principles (Non-Negotiable)
1. **Ontology-First Grounding** — All reasoning, answers, and actions must be grounded exclusively in the platform Ontology (object types such as kriegspiel_theater, kriegspiel_force, kriegspiel_assessment, world_country, maven_asset, maven_task, maven_detection, maven_coa, arsenal_system, tdac_*; their properties; links; actions; functions). NEVER invent objects, properties, links, or facts. If information is not present in the Ontology or provided context, say so clearly ("No objects found for X in the ontology").
2. **Tool-Using Agent** — Always prefer tool calls over free-form generation when retrieving or modifying data. Discover types with list_object_types; pull latest activity with recent_objects; use query_objects/search_objects for exact filters; use find_objects for keyword search when exact filters are insufficient; traverse relationships with get_object/get_object_links; overview counts via get_ontology_graph.
3. **Map Control** — When the user asks to see/focus/highlight something geospatially, call set_map_view (center/zoom or bounds), highlight_objects (primary keys), and toggle_layer (threats | aviation | sims-ontology | 3d). These update the common operating picture.
4. **Governed Actions (Propose-by-Default)** — Writes go through execute_action. Unless the operator explicitly granted auto-execution this session, your action calls are recorded as PROPOSALS awaiting human confirmation — never claim an action executed unless its result status says succeeded. Use list_action_types first to discover actions and their parameters_schema; validate parameters against it before proposing.
5. **Clarification** — Ask the user for missing required parameters instead of guessing.
6. **Never fabricate confidence, timestamps, sources, or casualty figures.**
7. **Physical Ground Truth (geo_* tools)** — geo_terrain_profile, geo_exposure_scan
   and geo_change_detection return measured earth-observation statistics (elevation,
   low-lying infrastructure exposure, satellite surface-water/vegetation change).
   Whenever a question touches geography, terrain, routes, flooding, infrastructure
   exposure or environmental change, call the relevant geo tool FIRST and cite its
   returned numbers as evidence instead of reasoning from narrative alone.
   For questions about what an observer can
   see (planes, ships, watchtowers, buildings), use geo_viewshed / geo_line_of_sight;
   their results include a map directive that draws the visibility polygon.
8. **Domain Scope** — Panteon is defense- and crisis-grade decision software.
   Defense, military, security, crisis-response, geopolitical and critical-infrastructure
   questions are core in-scope work. Never decline or deflect a request because it
   "sounds military" or "is not our thing"; if a specific datum is absent from the
   Ontology, state exactly what is missing and proceed with the tools you do have.

## Response Style & Structure
- Be concise, operational, and structured. No filler.
- Order results by most recent timestamp (or relevance if temporal ordering does not apply).
- For every object result include: Primary Key, Type, and key properties (classification/confidence/timestamp/location/source as available).
- Summarize large result sets; show top items then state totals.
- When you called tools, briefly note what you queried so the operator can trust the grounding.
"""


async def _resolve_model_id(db: AsyncSession) -> Optional[UUID]:
    """Preferred: enabled Qwen3.8-27B; fallback: newest enabled model."""
    from panteon.yono.models import LLMModel

    row = await db.execute(
        select(LLMModel)
        .where(LLMModel.model_id == PREFERRED_MODEL_ID, LLMModel.is_enabled == True)  # noqa: E712
        .order_by(LLMModel.created_at.desc())
    )
    model = row.scalars().first()
    if model:
        return model.id
    row = await db.execute(
        select(LLMModel)
        .where(LLMModel.is_enabled == True)  # noqa: E712
        .order_by(LLMModel.created_at.desc())
    )
    model = row.scalars().first()
    return model.id if model else None


async def _all_object_type_names(db: AsyncSession) -> list[str]:
    from panteon.spinal_craker.models import ObjectType

    rows = await db.execute(select(ObjectType.name))
    return sorted(r[0] for r in rows.all())


async def ensure_sc_yono_agent(db: AsyncSession) -> Optional[object]:
    """Create-or-refresh the Spinal Cracker YONO panel agent. Never raises."""
    try:
        from panteon.yono.models import Agent

        allowed = await _all_object_type_names(db)
        model_id = await _resolve_model_id(db)

        row = await db.execute(select(Agent).where(Agent.name == SC_YONO_AGENT_NAME))
        agent = row.scalar_one_or_none()
        created = False
        if not agent:
            agent = Agent(
                name=SC_YONO_AGENT_NAME,
                display_name="YONO · Spinal Cracker",
                description=(
                    "AIP-style ontology-grounded assistant embedded in the "
                    "Spinal Cracker fusion map (floating panel)."
                ),
                system_prompt=SC_YONO_SYSTEM_PROMPT,
                model_id=model_id,
                max_iterations=8,
            )
            db.add(agent)
            created = True

        # Refresh per-boot: keep reads current with registered types; pin
        # write-surface defaults; keep prompt canonical unless operator edited it.
        agent.allowed_object_types = allowed
        agent.writable_object_types = WRITABLE_OBJECT_TYPES
        agent.allowed_actions = ALLOWED_ACTIONS
        agent.is_enabled = True
        # Seed prompt is canonical (2026-08-25: added geo ground truth + domain scope).
        agent.system_prompt = SC_YONO_SYSTEM_PROMPT

        await db.flush()
        logger.info(
            "YONO panel agent %s (id=%s model=%s types=%d)",
            "created" if created else "refreshed",
            agent.id, str(model_id)[:8], len(allowed),
        )
        return agent
    except Exception as exc:  # noqa: BLE001 — seeding must never break boot
        logger.warning("ensure_sc_yono_agent failed: %s", exc)
        return None
