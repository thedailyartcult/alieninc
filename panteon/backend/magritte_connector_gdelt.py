"""
Module A: magritte_connector_gdelt
The Ingestion Sync Job — high-reliability pull mechanism targeting GDELT DOC 2.0 API.
Implements an aggressive, jittered exponential backoff retry, deterministic UUIDv5
identification via URL namespace, and raw append-only staging dataset persistence.

GDELT (Global Database of Events, Language, and Tone) is a free, open-source
global news database maintained by the GDELT Project (Georgetown University).
The DOC 2.0 API returns machine-translated global news coverage across 65+
languages. Per the official API:
  * Endpoint:  https://api.gdeltproject.org/api/v2/doc/doc
  * Auth:      NONE — the API is fully open, no API key required.
  * Params:    query, mode (ArtList), format, maxrecords (1-250), timespan
  * Response:  {"articles": [ {url, title, seendate, domain, sourcecountry, ...} ]}
  * seendate:  ISO-ish "YYYYMMDDTHHMMSSZ" (e.g. 20260714T030000Z)
  * Timespan:  "<n>min|h|hours|d|days|w|weeks|m|months" (e.g. 24h, 1m)
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

logger = logging.getLogger("magritte.connector.gdelt")


class GDELTMode(Enum):
    """Valid DOC 2.0 API modes."""
    ARTLIST = "artlist"
    ART = "art"
    IMAGECOLLAGE = "imagecollage"
    TIMELINEVOL = "timelinevol"
    TONECHART = "tonechart"
    WORDCLOUDENGLISH = "wordcloudenglish"
    WORDCLOUDIMAGETAGS = "wordcloudimagetags"
    IMAGECOLLAGESHARE = "imagecollageshare"


@dataclass
class GDELTConfig:
    """Low-level config schema for GDELT DOC 2.0 API pull."""
    query: str
    mode: GDELTMode = GDELTMode.ARTLIST
    timespan: str = "1m"
    maxrecords: int = 250
    api_key: str = ""
    base_url: str = "https://api.gdeltproject.org/api/v2/doc"
    request_timeout: int = 30
    max_retries: int = 5
    base_backoff_ms: int = 5000
    max_backoff_ms: int = 60000
    jitter_factor: float = 0.3

    def __post_init__(self) -> None:
        if isinstance(self.mode, str):
            self.mode = GDELTMode(self.mode.lower())
        if self.maxrecords > 250:
            self.maxrecords = 250


@dataclass
class RawStagingRecord:
    """Raw JSON body persisted into staging dataset before parsing."""
    guid: str
    url: str
    payload: Dict[str, Any]
    ingested_at: str
    source_mode: str
    record_type: str = "gdelt_article"


class StageRecord:
    """Internal staging record with parsed metadata."""

    def __init__(
        self,
        url: str,
        title: str,
        seendate: str,
        sourcecountry: str,
        domain: str,
        payload: Dict[str, Any],
    ):
        self.url = url
        self.title = title
        self.seendate = seendate
        self.sourcecountry = sourcecountry
        self.domain = domain
        self.payload = payload


@dataclass
class StagingDataset:
    """Simulated raw append-only staging dataset (Foundry Raw Dataset mimic)."""

    def __init__(self, path: str = "/tmp/gdelt_staging.parquet"):
        self.path = path
        self._records: List[Dict[str, Any]] = []

    def append(self, record: Dict[str, Any]) -> None:
        self._records.append(record)

    def snapshot(self) -> List[Dict[str, Any]]:
        return list(self._records)


class GDELTConnector:
    """High-reliability GDELT DOC 2.0 API sync job."""

    _cache: Dict[str, List[Dict[str, Any]]] = {}

    def __init__(
        self,
        config: GDELTConfig,
        staging: StagingDataset,
        aiohttp_session: Optional[aiohttp.ClientSession] = None,
    ):
        self.config = config
        self.staging = staging
        self._session = aiohttp_session

    async def _get_session(self) -> aiohttp.ClientSession:
        """Return the shared session or create one."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _build_request(self) -> Dict[str, Any]:
        """Construct a GDELT DOC 2.0 request payload."""
        payload: Dict[str, Any] = {
            "query": self.config.query,
            "mode": self.config.mode.value,
            "format": "json",
            "maxrecords": self.config.maxrecords,
            "timespan": self.config.timespan,
        }
        return payload

    def _parse_mode_response(self, data: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], int]:
        """Parse response based on the configured mode."""
        mode = self.config.mode
        if mode == GDELTMode.ARTLIST:
            articles = data.get("articles", []) or []
            return articles, len(articles)
        elif mode == GDELTMode.ART:
            # ART mode returns full article text articles
            articles = data.get("articles", []) or []
            return articles, len(articles)
        elif mode == GDELTMode.IMAGECOLLAGE:
            # IMAGECOLLAGE mode returns visual knowledge graph objects
            objects = data.get("objects", []) or []
            return objects, len(objects)
        elif mode == GDELTMode.TIMELINEVOL:
            # Already handled in pull()
            articles = data.get("timeline", {}).get("timelinevolraw", []) or []
            return articles, len(articles)
        elif mode == GDELTMode.TONECHART:
            # TONECHART returns tone analysis per article
            articles = data.get("articles", []) or []
            # Extract tone data if present, otherwise return empty
            for art in articles:
                art["tone"] = art.get("tone", {"sentiment": 0, "anger": 0, "fear": 0, "joy": 0, "sadness": 0})
            return articles, len(articles)
        elif mode == GDELTMode.WORDCLOUDENGLISH:
            # WORDCLOUDENGLISH returns word frequency counts
            words = data.get("words", []) or []
            return words, len(words)
        elif mode == GDELTMode.WORDCLOUDIMAGETAGS:
            # WORDCLOUDIMAGETAGS returns image tag frequencies
            tags = data.get("tags", []) or []
            return tags, len(tags)
        elif mode == GDELTMode.IMAGECOLLAGESHARE:
            # IMAGECOLLAGESHARE returns sharing metrics
            articles = data.get("articles", []) or []
            for art in articles:
                art["share_count"] = art.get("share_count", 0)
            return articles, len(articles)
        else:
            articles = data.get("articles", []) or []
            return articles, len(articles)

    async def _request_with_retry(
        self, url: str, method: str = "GET", headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Aggressive jittered exponential backoff retry (GDELT enforces ~1 req / 5s)."""
        max_retries = self.config.max_retries
        base_backoff = self.config.base_backoff_ms
        max_backoff = self.config.max_backoff_ms
        jitter = self.config.jitter_factor

        session = await self._get_session()
        last_exc: Optional[Exception] = None
        for attempt in range(max_retries + 1):
            try:
                async with session.request(
                    method, url, headers=headers, params=params,
                    timeout=aiohttp.ClientTimeout(total=self.config.request_timeout),
                ) as resp:
                    if resp.status == 429:
                        backoff = self._compute_backoff(attempt, max_retries, base_backoff, max_backoff, jitter)
                        logger.warning(f"GDELT rate limited (429), retrying in {backoff/1000:.1f}s (attempt {attempt+1}/{max_retries+1})")
                        await asyncio.sleep(backoff / 1000)
                        continue
                    if resp.status >= 500:
                        backoff = self._compute_backoff(attempt, max_retries, base_backoff, max_backoff, jitter)
                        logger.warning(f"GDELT server error ({resp.status}), retrying in {backoff/1000:.1f}s (attempt {attempt+1}/{max_retries+1})")
                        await asyncio.sleep(backoff / 1000)
                        continue
                    if resp.status >= 400:
                        body = await resp.text()
                        raise Exception(f"HTTP {resp.status}: {body}")
                    data = await resp.json()
                    return data
            except asyncio.TimeoutError as exc:
                last_exc = exc
                backoff = self._compute_backoff(attempt, max_retries, base_backoff, max_backoff, jitter)
                logger.warning(f"GDELT request timeout, retrying in {backoff/1000:.1f}s (attempt {attempt+1}/{max_retries+1})")
                await asyncio.sleep(backoff / 1000)
            except aiohttp.ClientError as exc:
                last_exc = exc
                backoff = self._compute_backoff(attempt, max_retries, base_backoff, max_backoff, jitter)
                logger.warning(f"GDELT connection error ({exc}), retrying in {backoff/1000:.1f}s (attempt {attempt+1}/{max_retries+1})")
                await asyncio.sleep(backoff / 1000)
            except Exception as exc:
                last_exc = exc
                backoff = self._compute_backoff(attempt, max_retries, base_backoff, max_backoff, jitter)
                logger.warning(f"GDELT request failed ({exc}), retrying in {backoff/1000:.1f}s (attempt {attempt+1}/{max_retries+1})")
                await asyncio.sleep(backoff / 1000)

        raise Exception(f"GDELT request failed after {max_retries + 1} attempts: {last_exc}")

    def _compute_backoff(
        self, attempt: int, max_retries: int, base_ms: int, max_ms: int, jitter: float
    ) -> float:
        """Jittered exponential backoff: base * 2^attempt * (1 + jitter)."""
        exponential = base_ms * (2 ** attempt)
        jittered = exponential * (1 + jitter * (attempt / max_retries))
        return min(jittered, max_ms)

    async def pull(
        self, page: int = 1
    ) -> Tuple[List[Dict[str, Any]], int, int]:
        """
        Pull GDELT DOC 2.0 data. Returns (records, total_count, page_count).

        GDELT returns up to `maxrecords` (max 250) articles in a single
        response and does NOT support server-side pagination, so this issues
        one request and returns the full result set.
        """
        url = f"{self.config.base_url}/doc"
        headers: Dict[str, str] = {}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        payload = await self._build_request()
        data = await self._request_with_retry(url, headers=headers, params=payload)

        articles, total_count = self._parse_mode_response(data)
        total_pages = 1
        return articles, total_count, total_pages

    async def persist_raw(
        self, records: List[Dict[str, Any]]
    ) -> List[RawStagingRecord]:
        """Persist raw JSON bodies into staging dataset. Returns staged records."""
        staged: List[RawStagingRecord] = []
        for i, payload in enumerate(records):
            raw_id = str(uuid.uuid5(uuid.NAMESPACE_URL, payload.get("url", "unknown")))
            record = RawStagingRecord(
                guid=raw_id,
                url=payload.get("url", "unknown"),
                payload=payload,
                ingested_at=datetime.now(timezone.utc).isoformat(),
                source_mode=self.config.mode.value,
            )
            self.staging.append(record.__dict__)
            staged.append(record)
        return staged

    async def execute(self, page: int = 1) -> List[RawStagingRecord]:
        """Execute full pull + staging pipeline. Returns list of staged records."""
        records, total_count, total_pages = await self.pull(page)
        staged = await self.persist_raw(records)
        logger.info(
            f"GDELT pull complete: {total_count} records fetched from page {page} "
            f"across {total_pages} pages. Staged {len(staged)} records."
        )
        return staged

    async def close(self) -> None:
        """Close the aiohttp session if we own it."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None


class GDELTConnectorFactory:
    """Factory for creating GDELTConnector instances."""

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
