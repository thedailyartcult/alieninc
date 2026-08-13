"""
Module B: gkg_connector_gdelt
GDELT Global Knowledge Graph Events API integration — military-grade intelligence.
Parses CAMEO event codes, extracts actor entities, geospatial data, and conflict metrics.
Complements the DOC 2.0 pipeline (Module A) with event-level intelligence.

GDELT Events API: https://api.gdeltproject.org/api/v2/events
  * Auth: NONE — fully open
  * Params: query, format, maxrecords (1-250), timespan, tone, V2 format
  * Response: {"events": [ {EventCode, EventRootCode, ActionGeo, ...] }
  * CAMEO codes: 1010=Riots, 2010=Demonstrations, 3010=Attack etc.
  * ActionGeo: {GLOBE: {latitude, longitude, country}, ...}
"""

import uuid
import hashlib
import json
import time
import logging
import asyncio
import aiohttp
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone

logger = logging.getLogger("gkg.connector.gdelt")


class GKGEventType(Enum):
    """CAMEO event type codes for military intelligence."""
    RIOTS = "1010"
    DEMONSTRATIONS = "2010"
    ATTACK = "3010"
    DEFENSE = "3110"
    PROPAGANDA = "4010"
    POLITICAL = "5010"
    MILITARY_MOVEMENT = "6010"
    TREATY = "7010"
    SANCTIONS = "8010"
    UNKNOWN = "9999"


@dataclass
class GKGEvent:
    """Parsed GKG event with military intelligence fields."""
    guid: str
    event_root_code: str
    event_code: str
    event_type: GKGEventType
    action_geo: Dict[str, Any]
    source_event_id: str
    event_date: str
    avg_tone: float
    num_articles: int
    average_color: Optional[str] = None
    feelings: Optional[Dict[str, Any]] = None
    num_media_files: int = 0
    num_sources: int = 0
    source_url: str = ""
    translated_text: str = ""


@dataclass
class GKGConfig:
    """Configuration for GKG Events API pull."""
    query: str
    timespan: str = "1m"
    maxrecords: int = 250
    api_key: str = ""
    base_url: str = "https://api.gdeltproject.org/api/v2/events"


class GKGConnector:
    """High-reliability GDELT Events API sync job for military intelligence."""

    def __init__(self, config: GKGConfig):
        self.config = config

    async def _build_request(self) -> Dict[str, Any]:
        """Construct a GDELT Events API request payload."""
        payload: Dict[str, Any] = {
            "query": self.config.query,
            "timespan": self.config.timespan,
            "maxrecords": self.config.maxrecords,
            "format": "V2",
        }
        if self.config.api_key:
            payload["api_key"] = self.config.api_key
        return payload

    async def _request_with_retry(
        self, url: str, method: str = "GET", headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Retry with jittered backoff (GDELT ~1 req/5s)."""
        max_retries = 5
        base_backoff = 5000
        max_backoff = 60000
        jitter = 0.3

        session = await self._get_shared_session()
        last_exc: Optional[Exception] = None
        for attempt in range(max_retries + 1):
            try:
                async with session.request(
                    method, url, headers=headers, params=params,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status == 429:
                        backoff = base_backoff * (2 ** attempt) * (1 + jitter * (attempt / max_retries))
                        logger.warning(f"GDELT rate limited (429), retrying in {backoff/1000:.1f}s")
                        await asyncio.sleep(backoff / 1000)
                        continue
                    if resp.status >= 500:
                        backoff = base_backoff * (2 ** attempt) * (1 + jitter * (attempt / max_retries))
                        logger.warning(f"GDELT server error ({resp.status}), retrying in {backoff/1000:.1f}s")
                        await asyncio.sleep(backoff / 1000)
                        continue
                    if resp.status >= 400:
                        body = await resp.text()
                        raise Exception(f"HTTP {resp.status}: {body}")
                    data = await resp.json()
                    return data
            except asyncio.TimeoutError as exc:
                last_exc = exc
                backoff = base_backoff * (2 ** attempt) * (1 + jitter * (attempt / max_retries))
                logger.warning(f"GDELT request timeout, retrying in {backoff/1000:.1f}s")
                await asyncio.sleep(backoff / 1000)
            except aiohttp.ClientError as exc:
                last_exc = exc
                backoff = base_backoff * (2 ** attempt) * (1 + jitter * (attempt / max_retries))
                logger.warning(f"GDELT connection error ({exc}), retrying in {backoff/1000:.1f}s")
                await asyncio.sleep(backoff / 1000)
            except Exception as exc:
                last_exc = exc
                backoff = base_backoff * (2 ** attempt) * (1 + jitter * (attempt / max_retries))
                logger.warning(f"GDELT request failed ({exc}), retrying in {backoff/1000:.1f}s")
                await asyncio.sleep(backoff / 1000)

        raise Exception(f"GDELT Events request failed after {max_retries + 1} attempts: {last_exc}")

    def _parse_gkg_event(self, raw: Dict[str, Any]) -> GKGEvent:
        """Parse raw GDELT Events API response into GKGEvent."""
        # Extract event codes
        event_root_code = raw.get("EventRootCode", "9999")
        event_code = raw.get("EventCode", "9999")

        # Map to CAMEO types
        try:
            event_type = GKGEventType(event_code)
        except ValueError:
            event_type = GKGEventType.UNKNOWN

        # Extract geospatial data
        action_geo = raw.get("ActionGeo", {})
        globe = action_geo.get("GLOBE", {})
        location = {
            "latitude": globe.get("latitude"),
            "longitude": globe.get("longitude"),
            "country": globe.get("country"),
            "city": globe.get("city"),
        }

        # Extract tone
        avg_tone = raw.get("AvgTone", 0)

        # Extract article count
        num_articles = raw.get("NumArticles", 0)

        # Extract event date
        event_date = raw.get("EventDate", "")

        # Build guid
        guid = str(uuid.uuid5(uuid.NAMESPACE_URL, raw.get("EventID", "unknown")))

        return GKGEvent(
            guid=guid,
            event_root_code=event_root_code,
            event_code=event_code,
            event_type=event_type,
            action_geo=location,
            source_event_id=raw.get("EventID", ""),
            event_date=event_date,
            avg_tone=avg_tone,
            num_articles=num_articles,
        )

    async def pull(self) -> List[GKGEvent]:
        """Pull GDELT Events API data and return parsed GKGEvents."""
        url = f"{self.config.base_url}/events"
        headers: Dict[str, str] = {}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        payload = await self._build_request()
        raw_data = await self._request_with_retry(url, headers=headers, params=payload)

        events_raw = raw_data.get("events", []) or []
        gkg_events: List[GKGEvent] = []

        for raw in events_raw:
            try:
                gkg_event = self._parse_gkg_event(raw)
                gkg_events.append(gkg_event)
            except Exception as e:
                logger.warning(f"Failed to parse GKG event: {e}")
                continue

        logger.info(f"GKG pull complete: {len(gkg_events)} events parsed from {len(events_raw)} raw events")
        return gkg_events

    async def execute(self) -> List[GKGEvent]:
        """Execute full GKG pull pipeline. Returns list of staged GKGEvents."""
        events = await self.pull()
        logger.info(f"GKG execution complete: {len(events)} events staged")
        return events


# Shared session factory (same pattern as Module A)
class GKGConnectorFactory:
    """Factory for creating GKGConnector instances."""

    _shared_session: Optional[aiohttp.ClientSession] = None

    @classmethod
    async def create_session(cls) -> aiohttp.ClientSession:
        if cls._shared_session is None or cls._shared_session.closed:
            cls._shared_session = aiohttp.ClientSession()
        return cls._shared_session

    @classmethod
    async def reset_session(cls) -> None:
        if cls._shared_session and not cls._shared_session.closed:
            await cls._shared_session.close()
        cls._shared_session = None

    @classmethod
    async def close_session(cls) -> None:
        await cls.reset_session()
