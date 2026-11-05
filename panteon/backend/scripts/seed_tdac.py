import asyncio
import uuid
from sqlalchemy import select
from panteon.core.database import async_session, init_db
from panteon.core.tenant import Tenant
from panteon.integrations.tdac_automation import TDACDailyReflectionAutomation


async def seed_tdac_tenant():
    await init_db()

    async with async_session() as db:
        result = await db.execute(select(Tenant).where(Tenant.slug == "thedailyartcult"))
        existing = result.scalar_one_or_none()

        if existing:
            print(f"TDAC tenant already exists: {existing.id}")
            return existing.id

        tenant = Tenant(
            id="00000000-0000-0000-0000-000000000001",
            name="The Daily Art Cult",
            display_name="The Daily Art Cult",
            description="Slow-luxury philosophical audio platform. Bespoke audiobooks, immersive listening experiences, and philosophical reflections.",
            slug="thedailyartcult",
            config={
                "website": "https://thedailyartcult.lol",
                "mission": "A world where death no longer extinguishes human consciousness",
                "subscription_price": 49,
                "currency": "USD",
                "trial_period_days": 180,
                "immortality_target": "2026-12-31",
                "publishers": [
                    {"name": "The Nocturnal School", "worldview": "Becoming"},
                    {"name": "Atelier Obsidian", "worldview": "Existentialism"},
                    {"name": "The Vellum Review", "worldview": "Stoicism"},
                    {"name": "Friction & Form", "worldview": "Absurdism"},
                    {"name": "Silent Spine", "worldview": "The Leap"},
                    {"name": "Anima Mundi Press", "worldview": "Mysticism"},
                    {"name": "Soma & Thread", "worldview": "Eastern Wisdom"},
                    {"name": "Marrow Archive", "worldview": "Politics"},
                    {"name": "Better Books & Garments", "worldview": "Witness"},
                ],
            },
            is_active=True,
        )
        db.add(tenant)
        await db.commit()
        print(f"Created TDAC tenant: {tenant.id}")

        automation_service = TDACDailyReflectionAutomation(db)
        automation = await automation_service.create_automation()
        await db.commit()
        print(f"Created TDAC daily reflection automation: {automation.id}")

        return tenant.id


if __name__ == "__main__":
    tenant_id = asyncio.run(seed_tdac_tenant())
    print(f"TDAC setup complete. Tenant ID: {tenant_id}")
