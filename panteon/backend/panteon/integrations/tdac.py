import httpx
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
import structlog
from panteon.core.tenant import Tenant, TenantMetric
from panteon.spinal_craker.models import Object, ObjectType
from panteon.spinal_craker.service import OntologyService

logger = structlog.get_logger()


class TDACConnector:
    def __init__(self, db: AsyncSession, tenant_slug: str = "thedailyartcult"):
        self.db = db
        self.tenant_slug = tenant_slug
        self.ontology = OntologyService(db)

    async def get_tenant(self) -> Optional[Tenant]:
        result = await self.db.execute(
            select(Tenant).where(Tenant.slug == self.tenant_slug)
        )
        return result.scalar_one_or_none()

    async def sync_patrons(self, supabase_url: str, supabase_key: str) -> dict:
        logger.info("syncing_tdac_patrons", tenant=self.tenant_slug)
        
        patron_type = await self.ontology.get_object_type_by_name("tdac_patron")
        if not patron_type:
            patron_type = await self.ontology.create_object_type(
                name="tdac_patron",
                display_name="TDAC Patron",
                description="The Daily Art Cult subscriber",
                properties_schema={
                    "name": "string",
                    "email": "string",
                    "subscription_tier": "string",
                    "philosophical_context_md": "text",
                    "created_at": "datetime",
                },
            )

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{supabase_url}/rest/v1/patrons",
                headers={"apikey": supabase_key, "Authorization": f"Bearer {supabase_key}"},
            )
            response.raise_for_status()
            patrons = response.json()

        synced = 0
        for patron in patrons:
            existing = await self.ontology.get_object_by_pk(patron_type.id, patron["id"])
            if existing:
                await self.ontology.update_object(
                    existing.id,
                    {
                        "name": patron.get("name"),
                        "email": patron.get("email"),
                        "subscription_tier": patron.get("subscription_tier"),
                        "philosophical_context_md": patron.get("philosophical_context_md"),
                    },
                )
            else:
                await self.ontology.create_object(
                    object_type_id=patron_type.id,
                    primary_key_value=patron["id"],
                    properties={
                        "name": patron.get("name"),
                        "email": patron.get("email"),
                        "subscription_tier": patron.get("subscription_tier"),
                        "philosophical_context_md": patron.get("philosophical_context_md"),
                        "created_at": patron.get("created_at"),
                    },
                )
            synced += 1

        logger.info("synced_tdac_patrons", count=synced)
        return {"synced": synced}

    async def sync_reflections(self, supabase_url: str, supabase_key: str) -> dict:
        logger.info("syncing_tdac_reflections", tenant=self.tenant_slug)

        reflection_type = await self.ontology.get_object_type_by_name("tdac_reflection")
        if not reflection_type:
            reflection_type = await self.ontology.create_object_type(
                name="tdac_reflection",
                display_name="TDAC Reflection",
                description="Philosophical audio reflection",
                properties_schema={
                    "patron_id": "string",
                    "publisher_id": "string",
                    "script_text": "text",
                    "audio_url": "string",
                    "duration_seconds": "integer",
                    "topic": "string",
                    "listened_percentage": "float",
                    "created_at": "datetime",
                },
            )

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{supabase_url}/rest/v1/reflections",
                headers={"apikey": supabase_key, "Authorization": f"Bearer {supabase_key}"},
            )
            response.raise_for_status()
            reflections = response.json()

        synced = 0
        for reflection in reflections:
            existing = await self.ontology.get_object_by_pk(reflection_type.id, reflection["id"])
            if not existing:
                await self.ontology.create_object(
                    object_type_id=reflection_type.id,
                    primary_key_value=reflection["id"],
                    properties={
                        "patron_id": reflection.get("patron_id"),
                        "publisher_id": reflection.get("publisher_id"),
                        "script_text": reflection.get("script_text"),
                        "audio_url": reflection.get("audio_url"),
                        "duration_seconds": reflection.get("duration_seconds"),
                        "topic": reflection.get("topic"),
                        "listened_percentage": reflection.get("listened_percentage", 0),
                        "created_at": reflection.get("created_at"),
                    },
                )
                synced += 1

        logger.info("synced_tdac_reflections", count=synced)
        return {"synced": synced}

    async def sync_publishers(self, supabase_url: str, supabase_key: str) -> dict:
        logger.info("syncing_tdac_publishers", tenant=self.tenant_slug)

        publisher_type = await self.ontology.get_object_type_by_name("tdac_publisher")
        if not publisher_type:
            publisher_type = await self.ontology.create_object_type(
                name="tdac_publisher",
                display_name="TDAC Publisher",
                description="Philosophical worldview editorial house",
                properties_schema={
                    "name": "string",
                    "worldview": "string",
                    "description": "text",
                    "secular_or_spiritual": "string",
                },
            )

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{supabase_url}/rest/v1/publishers",
                headers={"apikey": supabase_key, "Authorization": f"Bearer {supabase_key}"},
            )
            response.raise_for_status()
            publishers = response.json()

        synced = 0
        for publisher in publishers:
            existing = await self.ontology.get_object_type_by_name(publisher["id"])
            if not existing:
                await self.ontology.create_object(
                    object_type_id=publisher_type.id,
                    primary_key_value=publisher["id"],
                    properties={
                        "name": publisher.get("name"),
                        "worldview": publisher.get("worldview"),
                        "description": publisher.get("description"),
                        "secular_or_spiritual": publisher.get("secular_or_spiritual"),
                    },
                )
                synced += 1

        logger.info("synced_tdac_publishers", count=synced)
        return {"synced": synced}


class ResonanceIndexCalculator:
    def __init__(self, db: AsyncSession, tenant_slug: str = "thedailyartcult"):
        self.db = db
        self.tenant_slug = tenant_slug
        self.ontology = OntologyService(db)

    async def calculate_for_patron(self, patron_id: str, period_days: int = 30) -> dict:
        patron_type = await self.ontology.get_object_type_by_name("tdac_patron")
        reflection_type = await self.ontology.get_object_type_by_name("tdac_reflection")

        if not patron_type or not reflection_type:
            return {"error": "Object types not found"}

        cutoff = datetime.utcnow() - timedelta(days=period_days)

        reflections = await self.ontology.search_objects(
            object_type_id=reflection_type.id,
            property_filters={"patron_id": patron_id},
            limit=1000,
        )

        recent_reflections = [r for r in reflections if r.properties.get("created_at") and datetime.fromisoformat(r.properties["created_at"].replace("Z", "+00:00")) >= cutoff]

        r1_return_rate = self._calc_return_rate(recent_reflections)
        r2_depth_score = await self._calc_depth_score(patron_id, patron_type)
        r3_discovery_rate = await self._calc_discovery_rate(patron_id, reflection_type, cutoff)
        r4_ritual_score = self._calc_ritual_score(recent_reflections)
        r5_gift_score = await self._calc_gift_score(patron_id)

        resonance = (
            r1_return_rate * 0.25
            + r2_depth_score * 0.25
            + r3_discovery_rate * 0.20
            + r4_ritual_score * 0.15
            + r5_gift_score * 0.15
        )

        return {
            "patron_id": patron_id,
            "period_days": period_days,
            "resonance_index": round(resonance, 3),
            "components": {
                "r1_return_rate": round(r1_return_rate, 3),
                "r2_depth_score": round(r2_depth_score, 3),
                "r3_discovery_rate": round(r3_discovery_rate, 3),
                "r4_ritual_score": round(r4_ritual_score, 3),
                "r5_gift_score": round(r5_gift_score, 3),
            },
            "reflections_count": len(recent_reflections),
        }

    def _calc_return_rate(self, reflections: list) -> float:
        if not reflections:
            return 0.0
        listened = sum(1 for r in reflections if r.properties.get("listened_percentage", 0) >= 50)
        return (listened / len(reflections)) * 10

    async def _calc_depth_score(self, patron_id: str, patron_type) -> float:
        patron = await self.ontology.get_object_by_pk(patron_type.id, patron_id)
        if not patron:
            return 0.0
        
        context_updates = patron.properties.get("context_update_count", 0)
        return min(context_updates * 2.5, 10.0)

    async def _calc_discovery_rate(self, patron_id: str, reflection_type, cutoff) -> float:
        reflections = await self.ontology.search_objects(
            object_type_id=reflection_type.id,
            property_filters={"patron_id": patron_id},
            limit=1000,
        )

        publishers = set()
        for r in reflections:
            if r.properties.get("publisher_id"):
                publishers.add(r.properties["publisher_id"])

        return min(len(publishers) * 2.0, 10.0)

    def _calc_ritual_score(self, reflections: list) -> float:
        if not reflections:
            return 0.0

        sorted_reflections = sorted(
            reflections,
            key=lambda r: r.properties.get("created_at", ""),
            reverse=True,
        )

        max_streak = 0
        current_streak = 0
        prev_date = None

        for r in sorted_reflections:
            created_at = r.properties.get("created_at")
            if not created_at:
                continue
            try:
                date = datetime.fromisoformat(created_at.replace("Z", "+00:00")).date()
            except ValueError:
                continue

            if prev_date and (prev_date - date).days == 1:
                current_streak += 1
            else:
                current_streak = 1

            max_streak = max(max_streak, current_streak)
            prev_date = date

        return min(max_streak * 1.5, 10.0)

    async def _calc_gift_score(self, patron_id: str) -> float:
        giftcard_type = await self.ontology.get_object_type_by_name("tdac_giftcard")
        if not giftcard_type:
            return 0.0

        giftcards = await self.ontology.search_objects(
            object_type_id=giftcard_type.id,
            property_filters={"redeemed_by": patron_id},
            limit=100,
        )

        return min(len(giftcards) * 3.0, 10.0)

    async def calculate_tenant_aggregate(self, period_days: int = 30) -> dict:
        patron_type = await self.ontology.get_object_type_by_name("tdac_patron")
        if not patron_type:
            return {"error": "Patron type not found"}

        patrons = await self.ontology.list_objects(object_type_id=patron_type.id, limit=1000)

        all_resonances = []
        for patron in patrons:
            result = await self.calculate_for_patron(patron.primary_key_value, period_days)
            if "resonance_index" in result:
                all_resonances.append(result["resonance_index"])

        if not all_resonances:
            return {"average_resonance": 0, "patron_count": 0}

        return {
            "average_resonance": round(sum(all_resonances) / len(all_resonances), 3),
            "min_resonance": round(min(all_resonances), 3),
            "max_resonance": round(max(all_resonances), 3),
            "patron_count": len(all_resonances),
            "period_days": period_days,
        }
