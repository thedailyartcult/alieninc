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

import asyncio
import json
import logging
import os
import re
import time
import uuid
import aiohttp
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("gkg.connector.gdelt")


class GDELTError(Exception):
    """A classified GDELT request error.

    ``kind`` is one of: phrase_too_short, or_not_parenthesized, nested_or,
    rate_limited, server_error, network, timeout, generic.
    Structural kinds (phrase_too_short / or_not_parenthesized / nested_or) are
    never retried — retrying will not change GDELT's answer.
    """

    STRUCTURAL = {"phrase_too_short", "or_not_parenthesized", "nested_or"}

    def __init__(self, kind: str, message: str = "", wait_s: float = 0.0):
        super().__init__(message or kind)
        self.kind = kind
        self.message = message or kind
        self.wait_s = wait_s

    @property
    def is_structural(self) -> bool:
        return self.kind in self.STRUCTURAL


def validate_query_syntax(query: str) -> List[Dict[str, str]]:
    """Static, network-free GDELT DOC 2.0 query validation.

    Returns a list of issues, each {"kind", "severity", "message"}. severity is
    "error" (blocks Run) or "warning" (advisory; the live probe is authoritative).
    Mirrors the rules enforced by GDELT's DOC 2.0 API:
      * OR'd terms must be inside one flat (...) group.
      * Boolean OR blocks cannot be nested.
      * Short quoted single words are rejected ("The specified phrase is too short");
        the official convention is single words UNQUOTED, multi-word phrases quoted.
    """
    issues: List[Dict[str, str]] = []
    q = (query or "").strip()
    if not q:
        issues.append({"kind": "empty", "severity": "error", "message": "Query is empty."})
        return issues

    # Quote-stripped copy for OR/paren analysis (quotes preserved as "" markers).
    stripped = re.sub(r'"[^"]*"', '""', q)

    # Paren depth at each OR token (outside quotes).
    or_depths: List[int] = []
    depth = 0
    for m in re.finditer(r'\bOR\b', stripped):
        depth = stripped.count("(", 0, m.start()) - stripped.count(")", 0, m.start())
        or_depths.append(depth)

    if or_depths:
        if any(d <= 0 for d in or_depths):
            issues.append({
                "kind": "or_not_parenthesized",
                "severity": "error",
                "message": "OR'd terms must be surrounded by () — e.g. (a OR b OR c).",
            })
        elif len(set(or_depths)) > 1:
            issues.append({
                "kind": "nested_or",
                "severity": "error",
                "message": "Boolean OR blocks cannot be nested — use a single flat "
                           "(a OR b OR c) group.",
            })

    # Quoted single words: official convention is to leave single words unquoted.
    for m in re.finditer(r'"([^"]*)"', q):
        token = m.group(1)
        if token and " " not in token:
            issues.append({
                "kind": "quoted_single_word",
                "severity": "warning",
                "message": f'GDELT prefers single words unquoted — use {token} not "{token}" '
                           '(short quoted words are rejected as "too short").',
            })

    return issues


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
    title: str = ""
    domain: str = ""
    sourcecountry: str = ""
    language: str = ""
    translated_text: str = ""


@dataclass
class GKGConfig:
    """Configuration for GKG Events API pull."""
    query: str
    timespan: str = "1m"
    maxrecords: int = 250
    api_key: str = ""
    base_url: str = "https://api.gdeltproject.org/api/v2/doc"


class GKGConnector:
    """High-reliability GDELT Events API sync job for military intelligence."""

    def __init__(self, config: GKGConfig):
        self.config = config

    async def _build_request(self) -> Dict[str, Any]:
        """Construct a GDELT DOC 2.0 API request payload."""
        payload: Dict[str, Any] = {
            "query": self.config.query,
            "timespan": self.config.timespan,
            "maxrecords": self.config.maxrecords,
            "format": "json",
            "mode": "artlist",
        }
        if self.config.api_key:
            payload["api_key"] = self.config.api_key
        return payload

    @staticmethod
    def _classify_html(body: str, ctype: str) -> "GDELTError":
        """Classify a 200/text-html GDELT response (rate-limit page or query error)."""
        low = body.lower()
        if "limit requests" in low or ("one every" in low and "second" in low):
            return GDELTError("rate_limited", "GDELT rate-limit landing page (~1 req/5s).")
        if "too short" in low:
            return GDELTError("phrase_too_short", "The specified phrase is too short.")
        if "must be surrounded" in low:
            return GDELTError("or_not_parenthesized", "OR'd terms must be surrounded by ().")
        if "cannot be nested" in low:
            return GDELTError("nested_or", "Boolean OR blocks cannot be nested.")
        return GDELTError(
            "generic", f"Non-JSON GDELT response (Content-Type={ctype}): {body[:200]}"
        )

    @staticmethod
    def _backoff_ms(attempt: int, max_retries: int) -> int:
        base = 5000
        jitter = 0.3
        return int(base * (2 ** attempt) * (1 + jitter * (attempt / max(1, max_retries))))

    async def _request_with_retry(
        self, *, max_retries: int = 2, max_backoff_ms: int = 20000, block: bool = True,
    ) -> Dict[str, Any]:
        """Make one GDELT DOC request with classified, tame retries.

        - ``max_retries``: extra attempts (probe=0, pull=2).
        - ``block``: if False, an active cooldown raises immediately instead of
          waiting (used by the Validate probe so the UI gets fast feedback).
        - Structural errors (phrase_too_short / or_not_parenthesized / nested_or)
          are never retried — retrying cannot change GDELT's answer.
        Every attempt acquires a rate-governance slot (spacing + budget + cooldown).
        """
        session = await GKGConnectorFactory.create_session()
        url = f"{self.config.base_url}/doc"
        headers: Dict[str, str] = {}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        params = await self._build_request()
        last_err: Optional[GDELTError] = None
        for attempt in range(max_retries + 1):
            await _gate_acquire(block=block)
            try:
                async with session.request(
                    "GET", url, headers=headers, params=params,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status == 429:
                        _enter_cooldown()
                        last_err = GDELTError("rate_limited", "HTTP 429 rate limited.")
                    elif resp.status >= 500:
                        last_err = GDELTError("server_error", f"HTTP {resp.status} server error.")
                    elif resp.status >= 400:
                        body = await resp.text()
                        last_err = self._classify_html(
                            body, resp.headers.get("Content-Type", "text/html")
                        )
                    else:
                        ctype = resp.headers.get("Content-Type", "")
                        if "json" not in ctype:
                            raw_body = await resp.text()
                            last_err = self._classify_html(raw_body, ctype)
                        else:
                            _clear_cooldown_on_success()
                            return await resp.json()
                    if last_err.is_structural:
                        raise last_err
                    if last_err.kind == "rate_limited":
                        _enter_cooldown()
                    if attempt < max_retries:
                        backoff = min(self._backoff_ms(attempt, max_retries), max_backoff_ms)
                        logger.warning("GDELT %s, retrying in %.1fs", last_err.kind, backoff / 1000)
                        await asyncio.sleep(backoff / 1000)
                        continue
                    raise last_err
            except asyncio.TimeoutError as exc:
                last_err = GDELTError("timeout", f"Request timeout: {exc}")
                if attempt < max_retries:
                    backoff = min(self._backoff_ms(attempt, max_retries), max_backoff_ms)
                    logger.warning("GDELT timeout, retrying in %.1fs", backoff / 1000)
                    await asyncio.sleep(backoff / 1000)
                    continue
                raise last_err
            except aiohttp.ClientError as exc:
                last_err = GDELTError("network", f"Connection error: {exc}")
                if attempt < max_retries:
                    backoff = min(self._backoff_ms(attempt, max_retries), max_backoff_ms)
                    logger.warning(
                        "GDELT connection error (%s), retrying in %.1fs", exc, backoff / 1000
                    )
                    await asyncio.sleep(backoff / 1000)
                    continue
                raise last_err
            except GDELTError:
                raise
        raise last_err or GDELTError("generic", "GDELT request failed")

    # Approximate country centroids (lat, lon) keyed by the full country name
    # GDELT DOC 2.0 returns in ``sourcecountry``. Used as a geocoding fallback
    # because DOC articles carry no per-article locations.
    _COUNTRY_CENTROIDS: Dict[str, tuple[float, float]] = {
        "United States": (39.8283, -98.5795), "USA": (39.8283, -98.5795),
        "China": (35.8617, 104.1954),
        "Vietnam": (14.0583, 108.2772),
        "Russia": (61.5240, 105.3188), "Russia Federation": (61.5240, 105.3188),
        "United Kingdom": (55.3781, -3.4360), "UK": (55.3781, -3.4360), "Great Britain": (55.3781, -3.4360),
        "Germany": (51.1657, 10.4515),
        "France": (46.2276, 2.2137),
        "Japan": (36.2048, 138.2529),
        "India": (20.5937, 78.9629),
        "Brazil": (-14.2350, -51.9253),
        "Canada": (56.1304, -106.3468),
        "Australia": (-25.2744, 133.7751),
        "South Korea": (35.9078, 127.7669), "Korea, South": (35.9078, 127.7669), "South Korea (Republic of Korea)": (35.9078, 127.7669),
        "North Korea": (40.3399, 127.5101), "Korea, North": (40.3399, 127.5101),
        "Italy": (41.8719, 12.5674),
        "Spain": (40.4637, -3.7492),
        "Ukraine": (48.3794, 31.1656),
        "Poland": (51.9194, 19.1451),
        "Turkey": (38.9637, 35.2433), "Turkiye": (38.9637, 35.2433),
        "Iran": (32.4279, 53.6880), "Iran, Islamic Republic of": (32.4279, 53.6880),
        "Iraq": (33.2232, 43.6793),
        "Israel": (31.0461, 34.8516),
        "Saudi Arabia": (23.8859, 45.0792),
        "Egypt": (26.8206, 30.8025),
        "Pakistan": (30.3753, 69.3451),
        "Afghanistan": (33.9391, 67.7100),
        "Indonesia": (-0.7893, 113.9213),
        "Philippines": (12.8797, 121.7740),
        "Thailand": (15.8700, 100.9925),
        "Taiwan": (23.6978, 120.9605), "Taiwan (Republic of China)": (23.6978, 120.9605),
        "Hong Kong": (22.3193, 114.1694),
        "Mexico": (23.6345, -102.5528),
        "Argentina": (-38.4161, -63.6167),
        "Chile": (-35.6751, -71.5430),
        "Colombia": (4.5709, -74.2973),
        "Peru": (-9.1900, -75.0152),
        "Venezuela": (6.4238, -66.5897),
        "South Africa": (-30.5595, 22.9375),
        "Nigeria": (9.0820, 8.6753),
        "Kenya": (-0.0236, 37.9062),
        "Ethiopia": (9.1450, 40.4897),
        "Morocco": (31.7917, -7.0926),
        "Algeria": (28.0339, 1.6596),
        "Libya": (26.3351, 17.2283),
        "Syria": (34.8021, 38.9968),
        "Lebanon": (33.8547, 35.8623),
        "Jordan": (30.5852, 36.2384),
        "Yemen": (15.5527, 48.5164),
        "United Arab Emirates": (23.4241, 53.8478), "UAE": (23.4241, 53.8478),
        "Qatar": (25.3548, 51.1839),
        "Kuwait": (29.3117, 47.4818),
        "Oman": (21.5126, 55.9233),
        "Kazakhstan": (48.0196, 66.9237),
        "Uzbekistan": (41.3775, 64.5853),
        "Mongolia": (46.8625, 103.8467),
        "Nepal": (28.3949, 84.1240),
        "Sri Lanka": (7.8731, 80.7718),
        "Bangladesh": (23.6850, 90.3563),
        "Malaysia": (4.2105, 101.9758),
        "Singapore": (1.3521, 103.8198),
        "Myanmar": (21.9162, 95.9560),
        "Cambodia": (12.5657, 104.9910),
        "Laos": (19.8563, 102.4955),
        "New Zealand": (-40.9006, 174.8860),
        "Fiji": (-17.7134, 178.0650),
        "Greece": (39.0742, 21.8243),
        "Netherlands": (52.1326, 5.2913),
        "Belgium": (50.5039, 4.4699),
        "Switzerland": (46.8182, 8.2275),
        "Austria": (47.5162, 14.5501),
        "Sweden": (60.1282, 18.6435),
        "Norway": (60.4720, 8.4689),
        "Finland": (61.9241, 25.7482),
        "Denmark": (56.2639, 9.5018),
        "Portugal": (39.3999, -8.2245),
        "Ireland": (53.4129, -8.2439),
        "Czech Republic": (49.8175, 15.4730),
        "Czechia": (49.8175, 15.4730),
        "Hungary": (47.1625, 19.5033),
        "Romania": (45.9432, 24.9668),
        "Bulgaria": (42.7339, 25.4858),
        "Serbia": (44.0165, 21.0059),
        "Croatia": (45.1000, 15.2000),
        "Belarus": (53.7098, 27.9534),
        "Georgia": (42.3154, 43.3569),
        "Armenia": (40.0691, 45.0382),
        "Azerbaijan": (40.1431, 47.5769),
        "Tajikistan": (38.8610, 71.2761),
        "Turkmenistan": (38.9697, 59.5563),
        "Kyrgyzstan": (41.2044, 74.7661),
        "Somalia": (5.1521, 46.1996),
        "Sudan": (12.8628, 30.2176),
        "Tunisia": (33.8869, 9.5375),
        "Ghana": (7.9465, -1.0232),
        "Ivory Coast": (7.5400, -5.5471), "Cote d'Ivoire": (7.5400, -5.5471),
        "Uganda": (1.3733, 32.2903),
        "Tanzania": (-6.3690, 34.8888),
        "Zimbabwe": (-19.0154, 29.1549),
        "Angola": (-11.2027, 17.8739),
        "Cuba": (21.5218, -77.7812),
        "Haiti": (18.9712, -72.2852),
        "Dominican Republic": (18.7357, -70.1627),
        "Panama": (8.5380, -80.7821),
        "Costa Rica": (9.7489, -83.7534),
        "Guatemala": (15.7835, -90.2308),
        "Ecuador": (-1.8312, -78.1834),
        "Bolivia": (-16.2902, -63.5887),
        "Paraguay": (-23.4425, -58.4438),
        "Uruguay": (-32.5228, -55.7658),
        "Greenland": (71.7069, -42.6043),
        "Iceland": (64.9631, -19.0208),
    }

    # Same fallback for the FIPS/ISO 2-letter codes GDELT sometimes emits.
    _COUNTRY_CENTROID_CODES: Dict[str, tuple[float, float]] = {
        "US": (39.8283, -98.5795), "CN": (35.8617, 104.1954), "VN": (14.0583, 108.2772),
        "RU": (61.5240, 105.3188), "UK": (55.3781, -3.4360), "GB": (55.3781, -3.4360),
        "DE": (51.1657, 10.4515), "FR": (46.2276, 2.2137), "JP": (36.2048, 138.2529),
        "IN": (20.5937, 78.9629), "BR": (-14.2350, -51.9253), "CA": (56.1304, -106.3468),
        "AU": (-25.2744, 133.7751), "KR": (35.9078, 127.7669), "KP": (40.3399, 127.5101),
        "IT": (41.8719, 12.5674), "ES": (40.4637, -3.7492), "UA": (48.3794, 31.1656),
        "PL": (51.9194, 19.1451), "TR": (38.9637, 35.2433), "IR": (32.4279, 53.6880),
        "IQ": (33.2232, 43.6793), "IL": (31.0461, 34.8516), "SA": (23.8859, 45.0792),
        "EG": (26.8206, 30.8025), "PK": (30.3753, 69.3451), "AF": (33.9391, 67.7100),
        "ID": (-0.7893, 113.9213), "PH": (12.8797, 121.7740), "TH": (15.8700, 100.9925),
        "TW": (23.6978, 120.9605), "HK": (22.3193, 114.1694), "MX": (23.6345, -102.5528),
        "AR": (-38.4161, -63.6167), "CL": (-35.6751, -71.5430), "CO": (4.5709, -74.2973),
        "PE": (-9.1900, -75.0152), "VE": (6.4238, -66.5897), "ZA": (-30.5595, 22.9375),
        "NG": (9.0820, 8.6753), "KE": (-0.0236, 37.9062), "ET": (9.1450, 40.4897),
        "MA": (31.7917, -7.0926), "DZ": (28.0339, 1.6596), "LY": (26.3351, 17.2283),
        "SY": (34.8021, 38.9968), "LB": (33.8547, 35.8623), "JO": (30.5852, 36.2384),
        "YE": (15.5527, 48.5164), "AE": (23.4241, 53.8478), "QA": (25.3548, 51.1839),
        "KW": (29.3117, 47.4818), "OM": (21.5126, 55.9233), "KZ": (48.0196, 66.9237),
        "UZ": (41.3775, 64.5853), "MN": (46.8625, 103.8467), "NP": (28.3949, 84.1240),
        "LK": (7.8731, 80.7718), "BD": (23.6850, 90.3563), "MY": (4.2105, 101.9758),
        "SG": (1.3521, 103.8198), "MM": (21.9162, 95.9560), "KH": (12.5657, 104.9910),
        "GR": (39.0742, 21.8243), "NL": (52.1326, 5.2913), "BE": (50.5039, 4.4699),
        "CH": (46.8182, 8.2275), "AT": (47.5162, 14.5501), "SE": (60.1282, 18.6435),
        "NO": (60.4720, 8.4689), "FI": (61.9241, 25.7482), "DK": (56.2639, 9.5018),
        "PT": (39.3999, -8.2245), "IE": (53.4129, -8.2439), "CZ": (49.8175, 15.4730),
        "HU": (47.1625, 19.5033), "RO": (45.9432, 24.9668), "BG": (42.7339, 25.4858),
        "RS": (44.0165, 21.0059), "BY": (53.7098, 27.9534), "GE": (42.3154, 43.3569),
        "AM": (40.0691, 45.0382), "AZ": (40.1431, 47.5769), "TJ": (38.8610, 71.2761),
        "TM": (38.9697, 59.5563), "KG": (41.2044, 74.7661), "SO": (5.1521, 46.1996),
        "SD": (12.8628, 30.2176), "TN": (33.8869, 9.5375), "GH": (7.9465, -1.0232),
        "UG": (1.3733, 32.2903), "TZ": (-6.3690, 34.8888), "ZW": (-19.0154, 29.1549),
        "AO": (-11.2027, 17.8739), "CU": (21.5218, -77.7812), "HT": (18.9712, -72.2852),
        "PA": (8.5380, -80.7821), "EC": (-1.8312, -78.1834), "BO": (-16.2902, -63.5887),
        "PY": (-23.4425, -58.4438), "UY": (-32.5228, -55.7658), "IS": (64.9631, -19.0208),
        "NZ": (-40.9006, 174.8860),
    }

    @classmethod
    def _country_centroid(cls, sourcecountry: str) -> Optional[Dict[str, Any]]:
        """Resolve a country name/code to an approximate centroid."""
        key = (sourcecountry or "").strip()
        if not key:
            return None
        coord = cls._COUNTRY_CENTROIDS.get(key) or cls._COUNTRY_CENTROID_CODES.get(key.upper())
        if not coord:
            return None
        return {"latitude": coord[0], "longitude": coord[1], "country": key}

    @staticmethod
    def _cameo_for_tone(tone_raw: Any, title: str = "") -> tuple[str, str]:
        """Coarse CAMEO bucket derived from article tone, with a title keyword
        fallback for the tone.

        The classic GDELT Events API (which supplied native CAMEO codes) is
        retired (404 since 2026); DOC 2.0 article JSON carries no tone value and
        no native CAMEO codes, so we bucket by tone when it is meaningful and
        otherwise classify the article headline into a conflict-relevant CAMEO
        family so the threat map can surface real security events.

        CAMEO buckets: 3010 = Attack, 2010 = Demonstrations, 3041 = Protest
        engagement, 3230 = Demonstrate force, 4010 = Propaganda/Neutral.
        """
        try:
            tone = float(tone_raw or 0)
        except (TypeError, ValueError):
            tone = 0.0
        if tone < -5:
            return "3010", "3010"  # Attack
        if tone < -1:
            return "2010", "2010"  # Demonstrate
        if tone > 1:
            return "5010", "5010"  # Neutral positive
        # No usable tone from DOC 2.0 -> classify the headline instead.
        code, _ = GKGConnector._classify_title(title)
        return code, code

    # Keyword families keyed to CAMEO event codes. Ordered most-threat first.
    _TITLE_KEYWORDS = {
        "3010": ["attack", "airstrike", "assault", "bomb", "explosion", "killed",
                  "kill", "dead", "death", "offensive", "raid", "shelling",
                  "strike", "battle", "war", "fighting", "clash", "combat",
                  "gunfire", "ambush", "terrorist", "terror", "insurgent",
                  "militant", "court", "hostage", "siege", "massacre"],
        "3041": ["protest", "protests", "demonstration", "demonstrations",
                  "rally", "march", "riot", "unrest", "uprising", "sit-in"],
        "3230": ["sanction", "embargo", "coerce", "coercion", "threat",
                  "ultimatum", "demand", "warn", "blackmail"],
        "3001": ["arrest", "detain", "deport", "deportation", "arrests",
                  "extradite", "exile"],
        "5010": ["peace", "agreement", "ceasefire", "negotiation", "treaty",
                  "dialogue", "summit", "diplomatic"],
    }

    @classmethod
    def _classify_title(cls, title: str) -> tuple[str, str]:
        """Classify an article headline into a CAMEO event code.

        Returns (code, code). Falls back to 4010 (Propaganda) when no keyword
        matches, or when the title is empty.
        """
        if not title:
            return "4010", "4010"
        lowered = title.lower()
        for code in cls._TITLE_KEYWORDS:
            for kw in cls._TITLE_KEYWORDS[code]:
                if kw in lowered:
                    return code, code
        return "4010", "4010"

    def _parse_gkg_event(self, raw: Dict[str, Any]) -> GKGEvent:
        """Parse raw GDELT DOC 2.0 article record into GKGEvent."""
        title = raw.get("title", "") or ""
        # DOC 2.0 provides no per-article tone; classify from the headline so
        # the threat map surfaces real conflict/security events instead of a
        # flat PROPAGANDA bucket for everything.
        event_root_code, event_code = self._cameo_for_tone(raw.get("tone", ""), title)

        # Map to CAMEO types
        try:
            event_type = GKGEventType(event_code)
        except ValueError:
            event_type = GKGEventType.UNKNOWN

        # Extract geospatial data from the article's first resolved location
        action_geo: Dict[str, Any] = {}
        locations = raw.get("locations") or []
        if locations:
            loc = locations[0]
            action_geo = {
                "latitude": loc.get("lat"),
                "longitude": loc.get("lon"),
                "country": loc.get("countrycode", ""),
                "city": loc.get("name", ""),
            }
        else:
            # DOC 2.0 JSON articles carry no locations; fall back to the
            # publishing country's centroid so events remain map-plottable.
            action_geo = self._country_centroid(raw.get("sourcecountry", "")) or {}

        # Extract tone (DOC JSON carries it as a string)
        try:
            avg_tone = float(raw.get("tone") or 0)
        except (TypeError, ValueError):
            avg_tone = 0.0

        # DOC records are single articles; treat each as one event
        num_articles = 1

        # Extract event date (YYYYMMDDHHMMSS)
        event_date = raw.get("seendate", "")

        # Build guid
        url = raw.get("url", "") or raw.get("url_mobile", "")
        guid = str(uuid.uuid5(uuid.NAMESPACE_URL, url or raw.get("title", "unknown")))

        return GKGEvent(
            guid=guid,
            event_root_code=event_root_code,
            event_code=event_code,
            event_type=event_type,
            action_geo=action_geo,
            source_event_id=raw.get("guid", ""),
            event_date=event_date,
            avg_tone=avg_tone,
            num_articles=num_articles,
            source_url=url,
            title=raw.get("title", "") or "",
            domain=raw.get("domain", "") or "",
            sourcecountry=raw.get("sourcecountry", "") or "",
            language=raw.get("language", "") or "",
            translated_text=raw.get("translated_text", "") or "",
        )

    async def pull(self) -> List[GKGEvent]:
        """Pull GDELT DOC 2.0 article data and return parsed GKGEvents."""
        raw_data = await self._request_with_retry(max_retries=2, block=True)

        events_raw = raw_data.get("articles", []) or []
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

    async def probe(self) -> Dict[str, Any]:
        """Single lightweight GDELT request (maxrecords=1) to validate the query.

        Uses no retries and non-blocking cooldown so the admin "Validate" button
        gets fast feedback. Returns {"valid": True, "sample_count": N}. Raises
        GDELTError (classified) on any failure.
        """
        saved = self.config.maxrecords
        self.config.maxrecords = 1
        try:
            data = await self._request_with_retry(max_retries=0, block=False)
            articles = data.get("articles", []) or []
            return {"valid": True, "sample_count": len(articles)}
        finally:
            self.config.maxrecords = saved

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


# ---------------------------------------------------------------------------
# Rate governance — every GDELT HTTP request (probe or pull) flows through
# _gate_acquire inside _request_with_retry. The free GDELT DOC 2.0 API has NO
# monthly cap — only a ~1 req/5s per-IP throttle — so we enforce client-side
# spacing and an escalating cooldown on rate-limit responses to avoid bursting
# and getting the IP throttled. (No monthly budget: we are on the free API,
# not GDELT Cloud's metered monthly allowance.)
# ---------------------------------------------------------------------------
_RATE_STATE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "gkg_gdelt_rate_state.json"
)
_MIN_SPACING_S = float(os.environ.get("GDELT_MIN_SPACING_S", "6"))

_rate_state: Dict[str, Any] = {
    "last_request_ts": 0.0,
    "cooldown_until": 0.0,
    "cooldown_level": 0,
    "total_requests": 0,
}


def _load_rate_state() -> None:
    global _rate_state
    try:
        with open(_RATE_STATE_PATH, encoding="utf-8") as fh:
            saved = json.load(fh)
        _rate_state.update({k: saved.get(k, _rate_state[k]) for k in _rate_state})
    except (OSError, json.JSONDecodeError):
        pass


def _persist_rate_state() -> None:
    try:
        os.makedirs(os.path.dirname(_RATE_STATE_PATH), exist_ok=True)
        tmp = _RATE_STATE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(_rate_state, fh)
        os.replace(tmp, _RATE_STATE_PATH)
    except OSError as exc:
        logger.warning("Could not persist GDELT rate state: %s", exc)


def get_rate_state() -> Dict[str, Any]:
    """Snapshot of the rate-governance state for the admin UI / rate endpoint."""
    now = time.time()
    return {
        "total_requests": _rate_state["total_requests"],
        "cooldown_until": _rate_state["cooldown_until"],
        "cooldown_active": _rate_state["cooldown_until"] > now,
        "cooldown_seconds_left": max(0.0, _rate_state["cooldown_until"] - now),
        "min_spacing_s": _MIN_SPACING_S,
    }


def reset_cooldown() -> None:
    """Admin escape hatch: clear an active cooldown."""
    _rate_state["cooldown_until"] = 0.0
    _rate_state["cooldown_level"] = 0
    _persist_rate_state()


async def _gate_acquire(block: bool = True) -> None:
    """Acquire one GDELT request slot. Raises GDELTError if unavailable.

    - In cooldown -> if block, wait it out; else raise rate_limited immediately
      (so the Validate probe reports throttle instead of hanging the UI).
    - Spacing (< MIN_SPACING_S since last request) -> sleep the small remainder.
    Increments the total request counter exactly once per dispatched request.
    """
    now = time.time()
    cooldown_left = _rate_state["cooldown_until"] - now
    if cooldown_left > 0:
        if block:
            logger.info("GDELT cooldown active: waiting %.1fs", cooldown_left)
            await asyncio.sleep(cooldown_left)
        else:
            raise GDELTError(
                "rate_limited",
                f"GDELT is throttling this IP — try again in {int(cooldown_left)}s.",
                wait_s=cooldown_left,
            )
    spacing = _MIN_SPACING_S - (time.time() - _rate_state["last_request_ts"])
    if spacing > 0:
        await asyncio.sleep(spacing)
    _rate_state["last_request_ts"] = time.time()
    _rate_state["total_requests"] += 1
    _persist_rate_state()


def _enter_cooldown() -> None:
    """Escalating cooldown after a rate-limit response: 30, 60, 120, 240, 300 cap."""
    lvl = _rate_state["cooldown_level"]
    secs = min(30 * (2 ** lvl), 300)
    _rate_state["cooldown_until"] = time.time() + secs
    _rate_state["cooldown_level"] = lvl + 1
    _persist_rate_state()
    logger.warning("GDELT rate limit detected — entering %ss cooldown", secs)


def _clear_cooldown_on_success() -> None:
    if _rate_state["cooldown_level"] != 0:
        _rate_state["cooldown_level"] = 0
        _persist_rate_state()


# Load persisted rate state on import so cooldowns survive restarts.
_load_rate_state()
