import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from panteon.yono.models import Automation, AutomationExecution
from panteon.core.config import settings
import structlog
import httpx

logger = structlog.get_logger()


class TDACDailyReflectionAutomation:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_automation(self) -> Automation:
        automation = Automation(
            name="tdac_daily_reflection",
            display_name="TDAC Daily Reflection",
            description="Generate and deliver daily philosophical reflection to active patrons via Supabase edge function",
            trigger_type="cron",
            trigger_config={
                "schedule": "0 6 * * *",
                "timezone": "UTC",
            },
            conditions=[
                {"type": "object_exists", "entity": "tdac_patron", "filter": {"subscription_tier": "active"}},
            ],
            effects=[
                {
                    "type": "edge_function_call",
                    "config": {
                        "function": "synthesize-issue",
                        "description": "Calls Supabase edge function which has Gemini + Azure TTS secrets",
                    },
                },
            ],
            is_enabled=True,
        )
        self.db.add(automation)
        await self.db.flush()
        return automation

    async def _call_edge_function(
        self,
        payload: dict,
        supabase_url: str,
        service_role_key: str,
        anon_key: str,
    ) -> dict:
        function_url = f"{supabase_url}/functions/v1/synthesize-issue"
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                function_url,
                headers={
                    "Authorization": f"Bearer {service_role_key}",
                    "apikey": anon_key,
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=120.0,
            )
            if resp.status_code != 200:
                raise Exception(f"Edge function returned {resp.status_code}: {resp.text[:300]}")
            return resp.json()

    async def execute_for_patron(
        self,
        patron_id: str,
        issue_id: Optional[str] = None,
    ) -> dict:
        if not settings.supabase_url or not settings.supabase_service_role_key:
            raise Exception("Supabase not configured")

        logger.info("triggering_daily_reflection", patron_id=patron_id, issue_id=issue_id)

        payload = {"test_user_id": patron_id}
        if issue_id:
            payload["issue_id"] = issue_id

        result = await self._call_edge_function(
            payload=payload,
            supabase_url=settings.supabase_url,
            service_role_key=settings.supabase_service_role_key,
            anon_key=settings.supabase_anon_key or "",
        )

        logger.info("daily_reflection_delivered", patron_id=patron_id, result=str(result)[:200])

        return {
            "patron_id": patron_id,
            "status": "delivered",
            "edge_function_result": result,
            "generated_at": datetime.utcnow().isoformat(),
        }

    async def execute_batch(
        self,
        issue_id: Optional[str] = None,
    ) -> dict:
        if not settings.supabase_url or not settings.supabase_service_role_key:
            raise Exception("Supabase not configured")

        logger.info("triggering_batch_reflections", issue_id=issue_id)

        payload = {}
        if issue_id:
            payload["issue_id"] = issue_id

        result = await self._call_edge_function(
            payload=payload,
            supabase_url=settings.supabase_url,
            service_role_key=settings.supabase_service_role_key,
            anon_key=settings.supabase_anon_key or "",
        )

        logger.info("batch_reflections_complete", result=str(result)[:200])

        return {
            "status": "completed",
            "edge_function_result": result,
            "generated_at": datetime.utcnow().isoformat(),
        }
