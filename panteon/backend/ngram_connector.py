"""
Module C: ngram_connector
GDELT Context Ngrams and Web Ngrams analysis — keyword co-occurrence and trend analysis.

Context Ngrams API: https://api.gdeltproject.org/api/v2/ngrams
  * Analyzes co-occurrence of keywords across the monitored news population
  * Returns frequency counts, date-partitioned trends, and correlation data
  * Parameters: keyword, start_date, end_date, timespan, maxrecords

Web Ngrams API: https://api.gdeltproject.org/api/v2/ webngrams
  * Analyzes web content co-occurrence trends
  * Returns web search volume index data by keyword and date part

Both APIs support 65-language translingual search — keywords are translated
to 65 languages and results are aggregated across all monitored coverage.

Rate limit: ~1 req / 5s (same as DOC 2.0 API).
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

logger = logging.getLogger("ngram.connector")


class NgramType(Enum):
    """Supported ngram analysis types."""
    CONTEXT = "context"     # Keyword co-occurrence in news
    WEB = "web"           # Web content co-occurrence trends


@dataclass
class NgramResult:
    """Result from ngram analysis."""
    keyword: str
    start_date: str
    end_date: str
    timespan: str
    frequency: int
    date_partitioned: Dict[str, int]  # e.g. {"20260714": 5, "20260715": 3}
    correlation_keywords: List[str] = field(default_factory=list)
    confidence: float = 0.0


@dataclass
class NgramConfig:
    """Configuration for ngram analysis."""
    keyword: str
    ngram_type: NgramType = NgramType.CONTEXT
    start_date: str = ""  # e.g. "20260101"
    end_date: str = ""    # e.g. "20261231"
    timespan: str = "1m"
    maxrecords: int = 250
    api_key: str = ""


# Shared session factory (same pattern as Module A & B)
_shared_ngram_session: Optional[aiohttp.ClientSession] = None


async def _get_ngram_shared_session() -> aiohttp.ClientSession:
    """Return shared aiohttp session for ngram connector."""
    global _shared_ngram_session
    if _shared_ngram_session is None or _shared_ngram_session.closed:
        _shared_ngram_session = aiohttp.ClientSession()
    return _shared_ngram_session


class NgramConnector:
    """High-reliability GDELT ngram analysis connector."""

    def __init__(self, config: NgramConfig):
        self.config = config

    async def _build_request(self) -> Dict[str, Any]:
        """Construct ngram API request payload."""
        payload: Dict[str, Any] = {
            "keyword": self.config.keyword,
            "timespan": self.config.timespan,
            "maxrecords": self.config.maxrecords,
        }
        if self.config.start_date:
            payload["start_date"] = self.config.start_date
        if self.config.end_date:
            payload["end_date"] = self.config.end_date
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

        session = await _get_ngram_shared_session()
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

        raise Exception(f"GDELT ngram request failed after {max_retries + 1} attempts: {last_exc}")

    async def analyze(self) -> NgramResult:
        """Run ngram analysis and return structured result."""
        # Construct URL based on ngram type
        if self.config.ngram_type == NgramType.CONTEXT:
            url = "https://api.gdeltproject.org/api/v2/ngrams"
        else:
            url = "https://api.gdeltproject.org/api/v2/webngrams"

        headers: Dict[str, str] = {}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        payload = await self._build_request()
        raw_data = await self._request_with_retry(url, headers=headers, params=payload)

        # Parse response based on type
        keyword = self.config.keyword
        frequency = raw_data.get("frequency", 0)
        date_partitioned = raw_data.get("date_partitioned", {})

        # Correlation keywords from GDELT analysis
        correlation = raw_data.get("correlation_keywords", [])
        if not correlation:
            # Simple heuristic: return top related terms
            correlation = self._compute_correlations(keyword)

        confidence = raw_data.get("confidence", 0.5)

        return NgramResult(
            keyword=keyword,
            start_date=self.config.start_date or "",
            end_date=self.config.end_date or "",
            timespan=self.config.timespan,
            frequency=frequency,
            date_partitioned=date_partitioned,
            correlation_keywords=correlation,
            confidence=confidence
        )

    def _compute_correlations(self, keyword: str) -> List[str]:
        """Compute simple correlation keywords based on the main keyword."""
        # Heuristic mapping of related terms
        keyword_lower = keyword.lower()
        correlations = []

        # Build correlation dictionary
        corr_map = {
            "military": ["defense", "security", "conflict", "war"],
            "defense": ["military", "security", "deterrence"],
            "security": ["military", "defense", "cyber"],
            "conflict": ["military", "war", "conflict"],
            "terror": ["attack", "bombing", "violence"],
        }

        # Find matching correlations
        for key, vals in corr_map.items():
            if key in keyword_lower:
                correlations.extend(vals)

        # Deduplicate while preserving order
        seen = set()
        result = []
        for c in correlations:
            if c not in seen:
                seen.add(c)
                result.append(c)

        return result if result else ["related", "analysis"]
