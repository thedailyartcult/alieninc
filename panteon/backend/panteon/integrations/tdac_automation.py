import uuid
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from panteon.ono.models import Automation, AutomationExecution
from panteon.ono.service import LLMOrchestrator
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
            description="Generate and deliver daily philosophical reflection to active patrons",
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
                    "type": "llm_call",
                    "config": {
                        "purpose": "compose_reflection",
                        "prompt_template": "Compose a 200-300 word philosophical reflection for {patron_name} based on their context: {philosophical_context}. Publisher worldview: {publisher_worldview}. Topic: {topic}.",
                    },
                },
                {
                    "type": "tts_synthesis",
                    "config": {
                        "voice": "en-US-BrianNeural",
                        "rate": "-8%",
                        "pitch": "-5%",
                    },
                },
                {
                    "type": "webhook",
                    "config": {
                        "url": "https://thedailyartcult.lol/api/reflection-delivered",
                        "method": "POST",
                    },
                },
            ],
            is_enabled=True,
        )
        self.db.add(automation)
        await self.db.flush()
        return automation

    async def execute_for_patron(
        self,
        patron_id: str,
        patron_name: str,
        philosophical_context: str,
        publisher_worldview: str,
        topic: str,
        gemini_api_key: str,
        azure_speech_key: str,
        azure_speech_region: str,
    ) -> dict:
        logger.info("generating_daily_reflection", patron_id=patron_id)

        gemini_prompt = f"""Compose a 200-300 word philosophical reflection for {patron_name} based on their context:
{philosophical_context}

Publisher worldview: {publisher_worldview}
Topic: {topic}

Write in a contemplative, literary style. Be personal and direct. Avoid clichés. Make it feel like a letter from a thoughtful friend."""

        async with httpx.AsyncClient() as client:
            gemini_response = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={gemini_api_key}",
                json={
                    "contents": [{"parts": [{"text": gemini_prompt}]}],
                    "generationConfig": {
                        "temperature": 0.8,
                        "maxOutputTokens": 500,
                    },
                },
                timeout=30.0,
            )
            gemini_response.raise_for_status()
            gemini_data = gemini_response.json()

        script_text = gemini_data["candidates"][0]["content"]["parts"][0]["text"]

        ssml = f"""
<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">
    <voice name="en-US-BrianNeural">
        <prosody rate="-8%" pitch="-5%">
            {script_text}
        </prosody>
    </voice>
</speak>
"""

        async with httpx.AsyncClient() as client:
            tts_response = await client.post(
                f"https://{azure_speech_region}.tts.speech.microsoft.com/cognitiveservices/v1",
                headers={
                    "Ocp-Apim-Subscription-Key": azure_speech_key,
                    "Content-Type": "application/ssml+xml",
                    "X-Microsoft-OutputFormat": "audio-24khz-160kbitrate-mono-mp3",
                },
                content=ssml,
                timeout=30.0,
            )
            tts_response.raise_for_status()

        audio_bytes = tts_response.content

        logger.info("daily_reflection_generated", patron_id=patron_id, script_length=len(script_text), audio_size=len(audio_bytes))

        return {
            "patron_id": patron_id,
            "script_text": script_text,
            "audio_bytes": audio_bytes,
            "generated_at": datetime.utcnow().isoformat(),
        }

    async def execute_batch(
        self,
        patrons: list[dict],
        gemini_api_key: str,
        azure_speech_key: str,
        azure_speech_region: str,
    ) -> dict:
        results = []
        errors = []

        for patron in patrons:
            try:
                result = await self.execute_for_patron(
                    patron_id=patron["id"],
                    patron_name=patron["name"],
                    philosophical_context=patron.get("philosophical_context", ""),
                    publisher_worldview=patron.get("publisher_worldview", "Stoicism"),
                    topic=patron.get("topic", "becoming"),
                    gemini_api_key=gemini_api_key,
                    azure_speech_key=azure_speech_key,
                    azure_speech_region=azure_speech_region,
                )
                results.append({"patron_id": patron["id"], "status": "success"})
            except Exception as e:
                logger.error("daily_reflection_failed", patron_id=patron["id"], error=str(e))
                errors.append({"patron_id": patron["id"], "error": str(e)})

        return {
            "total": len(patrons),
            "successful": len(results),
            "failed": len(errors),
            "errors": errors,
        }
