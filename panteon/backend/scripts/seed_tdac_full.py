import asyncio
import uuid
import random
from datetime import datetime, timedelta
from sqlalchemy import select
from panteon.core.database import async_session, init_db
from panteon.core.tenant import Tenant, TenantMetric
from panteon.spinal_craker.models import ObjectType, Object, LinkType, Link
from panteon.spinal_craker.service import OntologyService
from panteon.ono.models import LLMProvider, LLMModel, Agent, Automation
from panteon.integrations.tdac_automation import TDACDailyReflectionAutomation


PUBLISHERS = [
    {"id": "pub-nocturnal", "name": "The Nocturnal School", "worldview": "Becoming", "desc": "Will, self-overcoming, the eternal return of the same.", "type": "secular"},
    {"id": "pub-obsidian", "name": "Atelier Obsidian", "worldview": "Existentialism", "desc": "Freedom, authenticity, the weight of choice.", "type": "secular"},
    {"id": "pub-vellum", "name": "The Vellum Review", "worldview": "Stoicism", "desc": "Duty, composure, the citadel within.", "type": "secular"},
    {"id": "pub-friction", "name": "Friction & Form", "worldview": "Absurdism", "desc": "Rebellion, lucid courage, Sisyphus smiling.", "type": "secular"},
    {"id": "pub-silent", "name": "Silent Spine", "worldview": "The Leap", "desc": "Faith, commitment, the paradox of belief.", "type": "secular"},
    {"id": "pub-anima", "name": "Anima Mundi Press", "worldview": "Mysticism", "desc": "Love, longing, the soul of the world.", "type": "spiritual"},
    {"id": "pub-soma", "name": "Soma & Thread", "worldview": "Eastern Wisdom", "desc": "Wu wei, balance, the uncarved block.", "type": "secular"},
    {"id": "pub-marrow", "name": "Marrow Archive", "worldview": "Politics", "desc": "Plurality, public life, the space between.", "type": "secular"},
    {"id": "pub-better", "name": "Better Books & Garments", "worldview": "Witness", "desc": "Attention, being seen, the ethics of looking.", "type": "secular"},
    {"id": "pub-guidepost", "name": "Guidepost Ministries", "worldview": "Christian Contemplative", "desc": "The cloud of unknowing, divine darkness.", "type": "spiritual"},
]

PATRONS = [
    {"id": "patron-marcus", "name": "Marcus", "email": "marcus@example.com", "tier": "active", "context": "Stoic philosopher. Interested in impermanence, duty, and the dichotomy of control. Reads Aurelius daily."},
    {"id": "patron-elena", "name": "Elena", "email": "elena@example.com", "tier": "active", "context": "Existentialist thinker. Grapples with authenticity vs social performance. Kierkegaard and de Beauvoir are anchors."},
    {"id": "patron-kenji", "name": "Kenji", "email": "kenji@example.com", "tier": "active", "context": "Eastern philosophy practitioner. Zen Buddhism, Taoism. Seeks wu wei in a world of constant acceleration."},
    {"id": "patron-amara", "name": "Amara", "email": "amara@example.com", "tier": "active", "context": "Mystic and poet. Drawn to Rumi, Ibn Arabi, the via negativa. Language fails and that's the point."},
    {"id": "patron-thomas", "name": "Thomas", "email": "thomas@example.com", "tier": "premium", "context": "Political theorist. Hannah Arendt, pluralism, the public realm. Concerned with what survives collective action."},
    {"id": "patron-sophie", "name": "Sophie", "email": "sophie@example.com", "tier": "active", "context": "Absurdist. Camus is gospel. Finds meaning in the refusal to find meaning. Painter by weekend."},
    {"id": "patron-david", "name": "David", "email": "david@example.com", "tier": "active", "context": "Nietzschean. Will to power, eternal recurrence, self-overcoming. Training for a marathon while reading Zarathustra."},
    {"id": "patron-leila", "name": "Leila", "email": "leila@example.com", "tier": "premium", "context": "Christian contemplative. Centering prayer, the cloud of unknowing. Seeks God in silence and in the faces of strangers."},
    {"id": "patron-james", "name": "James", "email": "james@example.com", "tier": "active", "context": "Philosophy of mind. Consciousness, qualia, the hard problem. Reads Chalmers for fun and Dennett for frustration."},
    {"id": "patron-aria", "name": "Aria", "email": "aria@example.com", "tier": "active", "context": "Feminist philosopher. Butler, Irigaray, Kristeva. Interested in performativity and the materiality of the body."},
    {"id": "patron-omar", "name": "Omar", "email": "omar@example.com", "tier": "trial", "context": "New to philosophy. Curious about everything. Looking for a framework to understand why nothing makes sense and that's okay."},
    {"id": "patron-nina", "name": "Nina", "email": "nina@example.com", "tier": "active", "context": "Environmental philosopher. Timothy Morton, deep ecology, the hyperobject of climate change. Grieving and acting."},
]

TOPICS = ["becoming", "endurance", "belonging", "creation", "faith", "loss", "longing", "love", "wonder", "loss", "introduction"]


async def seed():
    await init_db()
    async with async_session() as db:
        ontology = OntologyService(db)

        existing = await db.execute(select(Tenant).where(Tenant.slug == "thedailyartcult"))
        if existing.scalar_one_or_none():
            print("TDAC tenant exists, refreshing data...")
            await db.execute(TenantMetric.__table__.delete())
        else:
            tenant = Tenant(
                id="00000000-0000-0000-0000-000000000001",
                name="The Daily Art Cult",
                display_name="The Daily Art Cult",
                slug="thedailyartcult",
                description="Slow-luxury philosophical audio platform.",
                config={"publishers": PUBLISHERS, "subscription_price": 49, "immortality_target": "2026-12-31"},
                is_active=True,
            )
            db.add(tenant)
            await db.flush()
            print("Created TDAC tenant")

        publisher_type = await ontology.get_object_type_by_name("tdac_publisher")
        if not publisher_type:
            publisher_type = await ontology.create_object_type(
                name="tdac_publisher", display_name="TDAC Publisher",
                description="Philosophical worldview editorial house",
                properties_schema={"name": "string", "worldview": "string", "description": "text", "type": "string"},
            )
            print("Created publisher type")

        patron_type = await ontology.get_object_type_by_name("tdac_patron")
        if not patron_type:
            patron_type = await ontology.create_object_type(
                name="tdac_patron", display_name="TDAC Patron",
                description="Philosophical audio subscriber",
                properties_schema={"name": "string", "email": "string", "subscription_tier": "string", "philosophical_context_md": "text"},
            )
            print("Created patron type")

        reflection_type = await ontology.get_object_type_by_name("tdac_reflection")
        if not reflection_type:
            reflection_type = await ontology.create_object_type(
                name="tdac_reflection", display_name="TDAC Reflection",
                description="Philosophical audio reflection",
                properties_schema={"patron_id": "string", "publisher_id": "string", "script_text": "text", "audio_url": "string", "duration_seconds": "integer", "topic": "string", "listened_percentage": "float", "created_at": "datetime"},
            )
            print("Created reflection type")

        giftcard_type = await ontology.get_object_type_by_name("tdac_giftcard")
        if not giftcard_type:
            giftcard_type = await ontology.create_object_type(
                name="tdac_giftcard", display_name="TDAC Gift Card",
                description="Physical leather-bound gift card",
                properties_schema={"code": "string", "status": "string", "destination": "string", "redeemed_by": "string"},
            )
            print("Created giftcard type")

        game_type = await ontology.get_object_type_by_name("tdac_game")
        if not game_type:
            game_type = await ontology.create_object_type(
                name="tdac_game", display_name="TDAC Game Session",
                description="Daily painting or philosophy guessing game",
                properties_schema={"patron_id": "string", "game_type": "string", "streak": "integer", "score": "integer", "date": "string"},
            )
            print("Created game type")

        for p in PUBLISHERS:
            existing_pub = await ontology.get_object_by_pk(publisher_type.id, p["id"])
            if not existing_pub:
                await ontology.create_object(
                    object_type_id=publisher_type.id,
                    primary_key_value=p["id"],
                    properties={"name": p["name"], "worldview": p["worldview"], "description": p["desc"], "type": p["type"]},
                )
        print(f"Seeded {len(PUBLISHERS)} publishers")

        for p in PATRONS:
            existing_patron = await ontology.get_object_by_pk(patron_type.id, p["id"])
            if not existing_patron:
                await ontology.create_object(
                    object_type_id=patron_type.id,
                    primary_key_value=p["id"],
                    properties={"name": p["name"], "email": p["email"], "subscription_tier": p["tier"], "philosophical_context_md": p["context"], "context_update_count": random.randint(1, 8)},
                )
        print(f"Seeded {len(PATRONS)} patrons")

        now = datetime.utcnow()
        reflection_count = 0
        for patron in PATRONS:
            n_reflections = random.randint(8, 30)
            for i in range(n_reflections):
                days_ago = random.randint(0, 60)
                created = (now - timedelta(days=days_ago, hours=random.randint(0, 23))).isoformat()
                publisher = random.choice(PUBLISHERS)
                topic = random.choice(TOPICS)
                listened = round(random.uniform(10, 100), 1)
                rid = f"ref-{patron['id']}-{i}"
                existing_ref = await ontology.get_object_by_pk(reflection_type.id, rid)
                if not existing_ref:
                    await ontology.create_object(
                        object_type_id=reflection_type.id,
                        primary_key_value=rid,
                        properties={
                            "patron_id": patron["id"],
                            "publisher_id": publisher["id"],
                            "script_text": f"A reflection on {topic} from the perspective of {publisher['worldview']}...",
                            "audio_url": f"https://storage.thedailyartcult.lol/audio/{rid}.mp3",
                            "duration_seconds": random.randint(90, 240),
                            "topic": topic,
                            "listened_percentage": listened,
                            "created_at": created,
                        },
                    )
                    reflection_count += 1

        print(f"Seeded {reflection_count} reflections")

        giftcard_count = 0
        destinations = ["Paris", "Tokyo", "Hawaii", "London", "Cape Town", "Sydney", "New York", "Zurich"]
        for i in range(12):
            gid = f"gc-{i+1}"
            existing_gc = await ontology.get_object_by_pk(giftcard_type.id, gid)
            if not existing_gc:
                patron = random.choice(PATRONS)
                await ontology.create_object(
                    object_type_id=giftcard_type.id,
                    primary_key_value=gid,
                    properties={
                        "code": f"TDAC-{uuid.uuid4().hex[:8].upper()}",
                        "status": random.choice(["redeemed", "redeemed", "shipped", "in_transit"]),
                        "destination": random.choice(destinations),
                        "redeemed_by": patron["id"],
                    },
                )
                giftcard_count += 1
        print(f"Seeded {giftcard_count} gift cards")

        game_count = 0
        for patron in PATRONS:
            for gt in ["painter", "philosopher"]:
                for day in range(random.randint(3, 14)):
                    gid = f"game-{patron['id']}-{gt}-{day}"
                    existing_game = await ontology.get_object_by_pk(game_type.id, gid)
                    if not existing_game:
                        await ontology.create_object(
                            object_type_id=game_type.id,
                            primary_key_value=gid,
                            properties={
                                "patron_id": patron["id"],
                                "game_type": gt,
                                "streak": day + 1,
                                "score": random.randint(40, 100),
                                "date": (now - timedelta(days=day)).strftime("%Y-%m-%d"),
                            },
                        )
                        game_count += 1
        print(f"Seeded {game_count} game sessions")

        existing_provider = await db.execute(select(LLMProvider).where(LLMProvider.name == "Google"))
        if not existing_provider.scalar_one_or_none():
            google = LLMProvider(name="Google", provider_type="google", is_enabled=True)
            db.add(google)
            await db.flush()
            gemini = LLMModel(
                provider_id=google.id, model_id="gemini-2.5-pro",
                display_name="Gemini 2.5 Pro", capabilities=["text", "reasoning"],
                max_tokens=8192, cost_per_1k_input=0.00125, cost_per_1k_output=0.005,
            )
            db.add(gemini)
            await db.flush()

            openai = LLMProvider(name="OpenAI", provider_type="openai", is_enabled=True)
            db.add(openai)
            await db.flush()
            gpt = LLMModel(
                provider_id=openai.id, model_id="gpt-4o",
                display_name="GPT-4o", capabilities=["text", "vision", "audio"],
                max_tokens=4096, cost_per_1k_input=0.0025, cost_per_1k_output=0.01,
            )
            db.add(gpt)

            anthropic = LLMProvider(name="Anthropic", provider_type="anthropic", is_enabled=True)
            db.add(anthropic)
            await db.flush()
            claude = LLMModel(
                provider_id=anthropic.id, model_id="claude-sonnet-4-20250514",
                display_name="Claude Sonnet 4", capabilities=["text", "reasoning"],
                max_tokens=8192, cost_per_1k_input=0.003, cost_per_1k_output=0.015,
            )
            db.add(claude)
            print("Seeded LLM providers (Google, OpenAI, Anthropic)")

        existing_agent = await db.execute(select(Agent).where(Agent.name == "listening-booth"))
        if not existing_agent.scalar_one_or_none():
            agents = [
                Agent(name="listening-booth", display_name="The Listening Booth",
                      system_prompt="You are a philosophical guide. Help patrons discover reflections that speak to their current state of mind. Ask what they're grappling with, then recommend a publisher and topic.",
                      tools=["search_reflections", "recommend_publisher"]),
                Agent(name="immortality-archivist", display_name="Immortality Archivist",
                      system_prompt="You help patrons build their philosophical archive. Ask deep questions about their beliefs, values, and the questions that keep them awake. Distill their answers into a living document.",
                      tools=["update_context", "generate_archive"]),
                Agent(name="curator", display_name="The Curator",
                      system_prompt="You curate the daily painting and philosophy games. Select works that provoke thought and connect to philosophical themes. Explain why each piece matters.",
                      tools=["select_painting", "select_quote"]),
            ]
            for a in agents:
                db.add(a)
            print("Seeded 3 ONO agents")

        automation_service = TDACDailyReflectionAutomation(db)
        existing_auto = await db.execute(select(Automation).where(Automation.name == "tdac_daily_reflection"))
        if not existing_auto.scalar_one_or_none():
            await automation_service.create_automation()
            print("Seeded daily reflection automation")

        tenant = (await db.execute(select(Tenant).where(Tenant.slug == "thedailyartcult"))).scalar_one()

        metric_types = ["reflection_completed", "game_played", "giftcard_redeemed", "patron_context_updated"]
        metric_count = 0
        for i in range(50):
            mt = random.choice(metric_types)
            patron = random.choice(PATRONS)
            value = {}
            if mt == "reflection_completed":
                value = {"patron_id": patron["id"], "reflection_id": f"ref-metric-{i}", "publisher_id": random.choice(PUBLISHERS)["id"], "duration_seconds": random.randint(90, 240), "listened_percentage": round(random.uniform(30, 100), 1)}
            elif mt == "game_played":
                value = {"patron_id": patron["id"], "game_type": random.choice(["painter", "philosopher"]), "streak": random.randint(1, 14), "score": random.randint(40, 100)}
            elif mt == "giftcard_redeemed":
                value = {"patron_id": patron["id"], "giftcard_id": f"gc-{random.randint(1, 12)}", "destination": random.choice(destinations)}
            else:
                value = {"patron_id": patron["id"], "context_update_count": random.randint(1, 10)}

            m = TenantMetric(
                tenant_id=tenant.id, metric_type=mt, value=value,
                computed_at=now - timedelta(hours=random.randint(0, 720)),
            )
            db.add(m)
            metric_count += 1
        print(f"Seeded {metric_count} metric events")

        await db.commit()
        print("\n=== SEED COMPLETE ===")
        print(f"Publishers: {len(PUBLISHERS)}")
        print(f"Patrons: {len(PATRONS)}")
        print(f"Reflections: {reflection_count}")
        print(f"Gift Cards: {giftcard_count}")
        print(f"Game Sessions: {game_count}")
        print(f"LLM Providers: 3")
        print(f"ONO Agents: 3")
        print(f"Metric Events: {metric_count}")


if __name__ == "__main__":
    asyncio.run(seed())
