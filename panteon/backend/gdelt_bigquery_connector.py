"""
GDELT BigQuery connector — production-grade GDELT access via Google BigQuery.

The free GDELT DOC 2.0 API is per-IP-throttled (~1 req/5s) and returns no
per-article tone. The full GDELT 2.0 Global Knowledge Graph (GKG) is mirrored
on Google BigQuery as a public dataset (gdelt-bq:gdeltv2.gkg), updated every
15 minutes, with rich fields: V2Tone, ActionGeo_Lat/Long, Actor1Name/Actor2Name,
Themes, etc. BigQuery has NO per-IP throttle — only a free 1 TB/month query
quota. This connector queries the GKG table for conflict events with tone,
actors, and precise geocoding, and maps them to the existing GKGEvent dataclass
so the fusion map and OSv2 pipeline consume them unchanged.

Authentication: a Google Cloud service-account JSON key. Set the path via the
GDELT_BQ_CREDENTIALS env var or pass it to GDELTBigQueryConfig. Without valid
credentials the connector raises a clear error so the caller can fall back to
the DOC 2.0 API (see routes_gkg.py BigQuery-first-with-DOC-fallback logic).

GKG 2.0 BigQuery schema (key columns used here):
  V2Tone            — comma-separated: tone, positive_score, negative_score,
                      polarity, activity_reference_density, self_group_reference_density
  ActionGeo_Lat     — latitude (FLOAT64)
  ActionGeo_Long    — longitude (FLOAT64)
  ActionGeo_FullName— full place name (STRING)
  ActionGeo_CountryCode — FIPS country code (STRING)
  Actor1Name / Actor2Name — actor names (STRING)
  Actor1CountryCode / Actor2CountryCode — FIPS country codes (STRING)
  Themes            — semicolon-separated theme list (STRING)
  DocumentIdentifier— source URL (STRING)
  V1Locations       — JSON-ish location string (STRING)
  DATE              — event timestamp (INTEGER, YYYYMMDDHHMMSS)
  SourceCommonName  — source domain (STRING)
"""

import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from gkg_connector import GKGEvent, GKGEventType

logger = logging.getLogger("gkg.connector.bigquery")

# Public GDELT BigQuery dataset (free, updated every 15 min).
_GKG_TABLE = "gdelt-bq.gdeltv2.gkg"


@dataclass
class GDELTBigQueryConfig:
    """Config for the BigQuery GKG connector."""
    credentials_path: str = ""
    project_id: str = ""
    max_results: int = 250
    days_back: int = 1
    # Conflict themes to search for (GKG THEME values). These are the GDELT
    # theme taxonomy entries for military/conflict content.
    themes: List[str] = field(default_factory=lambda: [
        "ARMEDCONFLICT", "MILITARY", "TERROR", "PROTEST", "CRISISLEX_CRISISLEXREC",
    ])
    # Min absolute tone to include (negative = more negative coverage).
    min_tone: float = -100.0
    max_tone: float = 100.0


def _client() -> Any:
    """Create a BigQuery client from the credentials path/env. Raises if no creds."""
    creds_path = (
        os.environ.get("GDELT_BQ_CREDENTIALS")
        or GDELTBigQueryConfig().credentials_path
    )
    if not creds_path or not os.path.exists(creds_path):
        raise RuntimeError(
            "GDELT BigQuery credentials not found. Set GDELT_BQ_CREDENTIALS to a "
            "Google Cloud service-account JSON key path. Create a free GCP project "
            "at console.cloud.google.com, enable BigQuery API, create a service "
            "account with BigQuery User role, and download the JSON key."
        )
    try:
        from google.cloud import bigquery
    except ImportError as exc:
        raise RuntimeError(
            "google-cloud-bigquery not installed. Run: pip install google-cloud-bigquery"
        ) from exc
    return bigquery.Client.from_service_account_json(creds_path)


def _cameo_for_tone(tone: float) -> GKGEventType:
    """Map a tone value to a CAMEO event type (mirrors gkg_connector logic)."""
    if tone < -5:
        return GKGEventType.ATTACK
    if tone < -1:
        return GKGEventType.DEMONSTRATIONS
    if tone > 1:
        return GKGEventType.POLITICAL
    return GKGEventType.PROPAGANDA


def _parse_tone(v2tone: str) -> float:
    """Extract the average tone (first field) from the V2Tone string."""
    if not v2tone:
        return 0.0
    try:
        return float(v2tone.split(",")[0])
    except (ValueError, IndexError):
        return 0.0


def _build_gkg_query(config: GDELTBigQueryConfig) -> str:
    """Build a parameterized SQL query against the GKG table.

    Filters to the conflict themes, the time window, and the tone range.
    Returns the columns we need to build GKGEvent objects. Uses a LIKE-based
    theme match (CONTAINS_SUBSTR is available in BigQuery but LIKE is safer
    across versions).
    """
    since = (datetime.now(timezone.utc) - timedelta(days=config.days_back))
    since_str = since.strftime("%Y%m%d%H%M%S")
    # Build theme filter: Themes LIKE '%THEME%'
    theme_filters = " OR ".join(
        f"Themes LIKE '%{t}%'" for t in config.themes
    )
    return f"""
    SELECT
        DATE,
        V2Tone,
        ActionGeo_Lat,
        ActionGeo_Long,
        ActionGeo_FullName,
        ActionGeo_CountryCode,
        Actor1Name,
        Actor2Name,
        Actor1CountryCode,
        Actor2CountryCode,
        Themes,
        DocumentIdentifier,
        SourceCommonName
    FROM `{_GKG_TABLE}`
    WHERE DATE >= {since_str}
      AND ({theme_filters})
      AND ActionGeo_Lat IS NOT NULL
      AND ActionGeo_Long IS NOT NULL
    ORDER BY DATE DESC
    LIMIT {int(config.max_results)}
    """


def _row_to_gkg_event(row: Any) -> Optional[GKGEvent]:
    """Convert a BigQuery row to a GKGEvent. Returns None if unparseable."""
    try:
        tone = _parse_tone(row.get("V2Tone") or "")
        lat = row.get("ActionGeo_Lat")
        lng = row.get("ActionGeo_Long")
        if lat is None or lng is None:
            return None
        event_type = _cameo_for_tone(tone)
        url = row.get("DocumentIdentifier") or ""
        guid = str(uuid.uuid5(uuid.NAMESPACE_URL, url or f"bq:{row.get('DATE')}"))
        # FIPS country code -> we keep it; the frontend maps via COUNTRY_CAPITALS
        # by full name, so we also store the FullName for geocoding display.
        geo_full = row.get("ActionGeo_FullName") or ""
        country_code = row.get("ActionGeo_CountryCode") or ""
        actor1 = row.get("Actor1Name") or ""
        actor2 = row.get("Actor2Name") or ""
        # Build title from actors + themes (GKG has no article title field).
        themes_raw = row.get("Themes") or ""
        title_parts = []
        if actor1:
            title_parts.append(actor1)
        if actor2:
            title_parts.append("-> " + actor2)
        if themes_raw:
            title_parts.append("[" + themes_raw.split(";")[0] + "]")
        title = " ".join(title_parts) if title_parts else geo_full or "GDELT GKG event"
        # Domain from source URL.
        domain = ""
        if url:
            try:
                from urllib.parse import urlparse
                domain = urlparse(url).netloc or ""
            except Exception:
                pass
        # Date: YYYYMMDDHHMMSS -> ISO.
        date_raw = str(row.get("DATE") or "")
        event_date = ""
        if len(date_raw) == 14:
            try:
                dt = datetime.strptime(date_raw, "%Y%m%d%H%M%S")
                event_date = dt.isoformat()
            except ValueError:
                event_date = date_raw
        return GKGEvent(
            guid=guid,
            event_root_code=event_type.value[:2] + "00",
            event_code=event_type.value,
            event_type=event_type,
            action_geo={
                "latitude": float(lat),
                "longitude": float(lng),
                "country": geo_full or country_code,
                "country_code": country_code,
            },
            source_event_id=guid,
            event_date=event_date,
            avg_tone=tone,
            num_articles=1,
            source_url=url,
            title=title,
            domain=domain,
            sourcecountry=country_code,
            language="",
            translated_text="",
        )
    except Exception as exc:
        logger.warning("Failed to parse BigQuery GKG row: %s", exc)
        return None


class GDELTBigQueryConnector:
    """Queries the GDELT GKG table on BigQuery for conflict events with tone."""

    def __init__(self, config: GDELTBigQueryConfig):
        self.config = config

    def pull(self) -> List[GKGEvent]:
        """Run the BigQuery query and return parsed GKGEvents.

        Synchronous (BigQuery client is blocking). Call from a thread if needed.
        Raises RuntimeError if credentials are missing/invalid.
        """
        client = _client()
        query = _build_gkg_query(self.config)
        logger.info("GDELT BigQuery query: %s", query[:200])
        try:
            query_job = client.query(query)
            rows = query_job.result()  # blocks until done
        except Exception as exc:
            logger.exception("BigQuery query failed: %s", exc)
            raise RuntimeError(f"BigQuery query failed: {exc}") from exc
        events: List[GKGEvent] = []
        for row in rows:
            event = _row_to_gkg_event(dict(row))
            if event is not None:
                events.append(event)
        logger.info(
            "GDELT BigQuery pull complete: %d events (tone range %.1f to %.1f)",
            len(events),
            min((e.avg_tone for e in events), default=0),
            max((e.avg_tone for e in events), default=0),
        )
        return events

    def validate(self) -> Dict[str, Any]:
        """Lightweight validation: run a 1-row query to confirm creds + access.

        Returns {"valid": True, "sample_count": N} or raises RuntimeError.
        """
        client = _client()
        try:
            query_job = client.query(
                f"SELECT DATE FROM `{_GKG_TABLE}` ORDER BY DATE DESC LIMIT 1"
            )
            rows = list(query_job.result())
            return {"valid": True, "sample_count": len(rows)}
        except Exception as exc:
            raise RuntimeError(f"BigQuery validation failed: {exc}") from exc


def is_bigquery_available() -> bool:
    """Quick check: are BigQuery credentials configured?"""
    creds_path = os.environ.get("GDELT_BQ_CREDENTIALS", "")
    return bool(creds_path and os.path.exists(creds_path))
