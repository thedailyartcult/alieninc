"""
Module A: magritte_connector_gdelt
The Ingestion Sync Job — high-reliability pull mechanism targeting GDELT DOC 2.0 API.
Implements an aggressive, jittered exponential backoff retry, deterministic UUIDv5
identification via URL namespace, and raw append-only staging dataset persistence.
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
    SUMMARY = "summary"
    DOC = "doc"


@dataclass
class GDELTConfig:
    """Low-level config schema for GDELT DOC 2.0 API pull."""
    query: str
    mode: GDELTMode
    timespan: str
    maxrecords: int
    api_key: str
    base_url: str = "https://api.gdeltproject.org/api/gdeltv2"
    request_timeout: int = 30
    max_retries: int = 5
    base_backoff_ms: int = 1000
    max_backoff_ms: int = 60000
    jitter_factor: float = 0.3

    def __post_init__(self) -> None:
        if isinstance(self.mode, str):
            self.mode = GDELTMode(self.mode)


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

    async def _build_request(self, page: int) -> Dict[str, Any]:
        """Construct a paginated GDELT DOC 2.0 request payload."""
        payload: Dict[str, Any] = {
            "query": self.config.query,
            "mode": self.config.mode.value,
            "timespan": self.config.timespan,
            "maxRecords": self.config.maxrecords,
            "page": page,
        }
        return payload

    async def _request_with_retry(
        self, url: str, method: str = "GET", headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Aggressive jittered exponential backoff retry."""
        max_retries = self.config.max_retries
        base_backoff = self.config.base_backoff_ms
        max_backoff = self.config.max_backoff_ms
        jitter = self.config.jitter_factor

        last_exc: Optional[Exception] = None
        for attempt in range(max_retries + 1):
            try:
                if self._session:
                    async with self._session.request(
                        method, url, headers=headers, params=params,
                        timeout=aiohttp.ClientTimeout(total=self.config.request_timeout),
                    ) as resp:
                        if resp.status == 429:
                            await asyncio.sleep(self._compute_backoff(attempt, max_retries, base_backoff, max_backoff, jitter))
                            continue
                        if resp.status >= 500:
                            await asyncio.sleep(self._compute_backoff(attempt, max_retries, base_backoff, max_backoff, jitter))
                            continue
                        if resp.status >= 400:
                            body = await resp.text()
                            raise Exception(f"HTTP {resp.status}: {body}")
                        data = await resp.json()
                        return data
                raise Exception("No aiohttp session available")
            except Exception as exc:
                last_exc = exc
                await asyncio.sleep(self._compute_backoff(attempt, max_retries, base_backoff, max_backoff, jitter))

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
        """Pull GDELT DOC 2.0 data. Returns (records, total_count, page_count)."""
        url = f"{self.config.base_url}/doc2"
        headers = {"Authorization": f"Bearer {self.config.api_key}"}

        all_records: List[Dict[str, Any]] = []
        page_count = 0
        next_page = page

        while next_page is not None and len(all_records) < self.config.maxrecords:
            payload = await self._build_request(next_page)
            data = await self._request_with_retry(url, headers=headers, params=payload)

            results = data.get("result", []) or []
            page_count = len(results)
            all_records.extend(results)

            total = data.get("totalRecords", 0) or len(all_records)

            if total > 0 and len(all_records) >= total:
                break

            next_page = next_page + 1 if len(all_records) < self.config.maxrecords else None

        self._cache[str(page)] = all_records

        total_count = len(all_records)
        total_pages = int((total_count + self.config.maxrecords - 1) / self.config.maxrecords)

        return all_records, total_count, total_pages

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


class GDELTConnectorFactory:
    """Factory for creating GDELTConnector instances."""

    _session: Optional[aiohttp.ClientSession] = None

    @classmethod
    def create_session(cls) -> aiohttp.ClientSession:
        if cls._session is None:
            cls._session = aiohttp.ClientSession()
        return cls._session

    @classmethod
    def reset_session(cls) -> None:
        if cls._session:
            cls._session.close()
            cls._session = None
