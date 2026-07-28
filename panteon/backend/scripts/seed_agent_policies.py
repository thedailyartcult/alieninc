"""
Seed agents with Palantir AIP governance configs.
Run after seed_tdac_full.py to add ontology policies to existing agents.
"""
import asyncio
from sqlalchemy import select
from panteon.core.database import async_session, init_db
from panteon.yono.models import Agent


AGENTS_CONFIG = {
    "listening-booth": {
        "system_prompt": (
            "You are The Listening Booth, a philosophical guide for The Daily Art Cult. "
            "You help patrons discover reflections that speak to their current state of mind. "
            "Ask what they're grappling with, then use the ontology to find matching patrons "
            "and recommend a publisher and topic. You have access to the ontology — use it to "
            "provide personalized, data-driven recommendations."
        ),
        "allowed_object_types": ["tdac_patron", "tdac_publisher", "tdac_reflection"],
        "writable_object_types": [],
        "allowed_actions": [],
        "ontology_context_config": {
            "queries": [
                {
                    "label": "Active Patrons",
                    "type_name": "tdac_patron",
                    "filters": {"subscription_tier": "active"},
                    "limit": 12,
                },
                {
                    "label": "Publishers",
                    "type_name": "tdac_publisher",
                    "filters": {},
                    "limit": 10,
                },
            ]
        },
    },
    "immortality-archivist": {
        "system_prompt": (
            "You are the Immortality Archivist for The Daily Art Cult. You help patrons build "
            "their philosophical archive — a living document of their beliefs, values, and the "
            "questions that keep them awake. Use the ontology to access patron data, understand "
            "their reading history, and ask deep questions that help them articulate their worldview."
        ),
        "allowed_object_types": ["tdac_patron", "tdac_reflection", "tdac_giftcard"],
        "writable_object_types": ["tdac_patron"],
        "allowed_actions": [],
        "ontology_context_config": {
            "queries": [
                {
                    "label": "All Patrons",
                    "type_name": "tdac_patron",
                    "filters": {},
                    "limit": 12,
                },
            ]
        },
    },
    "curator": {
        "system_prompt": (
            "You are The Curator for The Daily Art Cult. You curate the daily painting and "
            "philosophy games. Use the ontology to understand patron engagement patterns, "
            "select works that provoke thought, and connect them to philosophical themes. "
            "Explain why each piece matters."
        ),
        "allowed_object_types": ["tdac_patron", "tdac_publisher", "tdac_reflection", "tdac_game"],
        "writable_object_types": [],
        "allowed_actions": [],
        "ontology_context_config": {
            "queries": [
                {
                    "label": "Recent Games",
                    "type_name": "tdac_game",
                    "filters": {},
                    "limit": 20,
                },
                {
                    "label": "Publishers",
                    "type_name": "tdac_publisher",
                    "filters": {},
                    "limit": 10,
                },
            ]
        },
    },
}


async def seed_agent_policies():
    await init_db()
    async with async_session() as db:
        for name, config in AGENTS_CONFIG.items():
            result = await db.execute(select(Agent).where(Agent.name == name))
            agent = result.scalar_one_or_none()
            if not agent:
                print(f"Agent '{name}' not found, skipping")
                continue

            agent.system_prompt = config["system_prompt"]
            agent.allowed_object_types = config["allowed_object_types"]
            agent.writable_object_types = config["writable_object_types"]
            agent.allowed_actions = config["allowed_actions"]
            agent.ontology_context_config = config["ontology_context_config"]
            print(f"Updated agent '{name}' with governance config")

        await db.commit()
        print("\n=== AGENT POLICY SEED COMPLETE ===")


if __name__ == "__main__":
    asyncio.run(seed_agent_policies())
