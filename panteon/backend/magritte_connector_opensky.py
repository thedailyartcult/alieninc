"""
Module A: magritte_connector_opensky
The Aviation Domain Ingestion Sync Job — high-reliability pull mechanism
targeting the OpenSky Network API (states/all) with optional adsb.fi military
fallback.  Mirrors the GDELT DOC 2.0 connector architecture but for real-time
aircraft state vectors.

OpenSky Network (https://opensky-network.org) provides a free, open API for
real-time and historical flight tracking data.  Per the official API:

  * Endpoint:  https://opensky-network.org/api/states/all?extended=1
  * Auth:      Optional OAuth2 (client_credentials). Anonymous pool is
               per-IP limited to 400 credits/day.
  * extended=1:  appends the ADS-B emitter category as an 18th state-vector
                 field (s[17]).  Without it every category_os test is dead code.
  * Response:  {"time": <unix>, "states": [[icao24, callsign, country, ...], ...]}
  * State vector (18-element):
      0: icao24 (hex)           8: alt_geom
      1: callsign               9: speed (m/s, → knots)
      2: country                10: track (heading deg)
      3: on_ground              11: rad_alt
      4: last_contact           12: heading
      5: lon                    13: vertical_rate
      6: lat                    14: squawk
      7: alt_baro (ft or "ground")  17: category (extended=1)

Also pulls the adsb.fi military feed as a companion source:
  * Endpoint: https://opendata.adsb.fi/api/v2/mil
  * Auth:     NONE
  * Response: {"ac": [{hex, flight, lat, lon, alt_baro, gs, ...}, ...]}

Port of the osiris (https://github.com/simplifaisoul/osiris) OpenSky
flight-classification pipeline from TypeScript to Python.
"""

import asyncio
import logging
import random
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

import aiohttp

logger = logging.getLogger("magritte.connector.opensky")


# ──────────────────────────────────────────────────────────────────────────────
# Flight-Classification Lookup Tables
# (ported verbatim from osiris src/app/api/flights/route.ts)
# ──────────────────────────────────────────────────────────────────────────────

HELI_TYPES: set[str] = {
    'R22', 'R44', 'R66', 'B06', 'B06T', 'B204', 'B205', 'B206', 'B212', 'B222', 'B230',
    'B407', 'B412', 'B427', 'B429', 'B430', 'B505', 'B525',
    'AS32', 'AS35', 'AS50', 'AS55', 'AS65',
    'EC20', 'EC25', 'EC30', 'EC35', 'EC45', 'EC55', 'EC75',
    'H125', 'H130', 'H135', 'H145', 'H155', 'H160', 'H175', 'H215', 'H225',
    'S55', 'S58', 'S61', 'S64', 'S70', 'S76', 'S92',
    'A109', 'A119', 'A139', 'A169', 'A189', 'AW09',
    'MD52', 'MD60', 'MDHI', 'MD90', 'NOTR',
    'B47G', 'HUEY', 'GAMA', 'CABR', 'EXE',
}

PRIVATE_JET_TYPES: set[str] = {
    'G150', 'G200', 'G280', 'GLEX', 'G500', 'G550', 'G600', 'G650', 'G700',
    'GLF2', 'GLF3', 'GLF4', 'GLF5', 'GLF6', 'GL5T', 'GL7T', 'GV', 'GIV',
    'CL30', 'CL35', 'CL60', 'BD70', 'BD10',
    'C25A', 'C25B', 'C25C', 'C500', 'C510', 'C525', 'C550', 'C560', 'C56X', 'C680', 'C700', 'C750',
    'E35L', 'E50P', 'E55P', 'E545', 'E550',
    'FA50', 'FA7X', 'FA8X', 'F900', 'F2TH',
    'LJ35', 'LJ40', 'LJ45', 'LJ60', 'LJ70', 'LJ75',
    'PC12', 'PC24', 'TBM7', 'TBM8', 'TBM9',
    'PRM1', 'SF50', 'EA50', 'VLJ',
}

MILITARY_INDICATORS: set[str] = {
    'C17', 'C5M', 'C130', 'C30J', 'KC10', 'KC46', 'KC35', 'E3CF', 'E3TF', 'E8A',
    'B1B', 'B2', 'B52', 'F16', 'F15', 'F18', 'F22', 'F35', 'A10', 'F117',
    'RC135', 'E6B', 'P8A', 'P3', 'MQ9', 'RQ4', 'U2', 'EP3', 'RC12',
    'V22', 'CH47', 'UH60', 'AH64', 'AH1Z', 'MV22',
    'EUFI', 'RFAL', 'TORD', 'TYP', 'GR4',
}

AIRLINER_TYPES: set[str] = {
    'A319', 'A320', 'A321', 'A332', 'A333', 'A339', 'A343', 'A359', 'A388',
    'B737', 'B738', 'B739', 'B38M', 'B39M', 'B752', 'B753', 'B763', 'B764',
    'B772', 'B77L', 'B77W', 'B788', 'B789', 'B78X',
    'E170', 'E175', 'E190', 'E195', 'CRJ7', 'CRJ9', 'AT43', 'AT72', 'DH8D',
}

BIZJET_OPERATORS: set[str] = {
    'EJA', 'EJM', 'NJE', 'LXJ', 'FJO', 'VJT', 'XOJ', 'JTL', 'WUP', 'GAJ', 'DPJ', 'CLY', 'TWY',
}

AIRLINE_CODE_RE = re.compile(r'^([A-Z]{3})\d')
CALLSIGN_RE = re.compile(r'^[A-Z0-9]{3,8}$')

JET_CRUISE_ALT_M = 8500
JET_CRUISE_KTS = 300

JAMMING_NACAP_THRESHOLD = 4
ADSB_MAX_DIST = 250
ADSB_FI_BASE = 'https://opendata.adsb.fi/api/v2'
ADSB_FI_GAP_MS = 1100

OPENSKY_STATES_URL = 'https://opensky-network.org/api/states/all?extended=1'
OPENSKY_TOKEN_URL = 'https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token'

# 30 regions covering every major aviation corridor at 250 nm radius (ported
# verbatim from osiris REGIONS constant).
REGIONS: list[dict[str, float]] = [
    # North America
    {'lat': 39.8,  'lon': -98.5},  # Central US
    {'lat': 41.0,  'lon': -74.0},  # Northeast (NYC/Boston/DC)
    {'lat': 33.0,  'lon': -84.0},  # Southeast (Atlanta)
    {'lat': 42.0,  'lon': -88.0},  # Midwest (Chicago)
    {'lat': 30.0,  'lon': -97.0},  # Texas (Dallas/Houston)
    {'lat': 47.0,  'lon': -122.0}, # Pacific Northwest (Seattle)
    {'lat': 34.0,  'lon': -118.0}, # SoCal (LA)
    {'lat': 45.0,  'lon': -73.0},  # Canada East (Montreal/Toronto)
    {'lat': 49.0,  'lon': -97.0},  # Canada Prairies
    # Europe
    {'lat': 50.0,  'lon':  15.0},  # Central Europe
    {'lat': 51.5,  'lon':  -1.0},  # UK / Ireland
    {'lat': 47.0,  'lon':   2.0},  # France / Alps
    {'lat': 40.0,  'lon':  -4.0},  # Iberia
    {'lat': 42.0,  'lon':  13.0},  # Italy / Adriatic
    {'lat': 60.0,  'lon':  15.0},  # Scandinavia
    {'lat': 52.0,  'lon':  22.0},  # Eastern Europe / Baltics
    {'lat': 39.0,  'lon':  35.0},  # Turkey / Aegean
    # Middle East & South Asia
    {'lat': 25.0,  'lon':  45.0},  # Arabian Gulf (Dubai/Riyadh)
    {'lat': 22.0,  'lon':  78.0},  # India
    # East Asia & Pacific
    {'lat': 35.0,  'lon': 105.0},  # China
    {'lat': 35.0,  'lon': 136.0},  # Japan
    {'lat': 37.0,  'lon': 127.0},  # Korea
    {'lat': 13.0,  'lon': 100.0},  # SE Asia (Bangkok)
    {'lat':  1.0,  'lon': 104.0},  # Singapore / Malacca Strait
    # Australia
    {'lat': -25.0, 'lon': 133.0},  # Central Australia
    {'lat': -33.0, 'lon': 151.0},  # Eastern Australia (Sydney)
    # Africa
    {'lat':  0.0,  'lon':  20.0},  # Central Africa
    {'lat': -26.0, 'lon':  28.0},  # South Africa
    # South America
    {'lat': -15.0, 'lon': -60.0},  # Brazil Central
    {'lat': -23.0, 'lon': -46.0},  # São Paulo / Rio
]

# Spoofed-headers pools (ported from osiris stealthFetch.ts)
IP_POOLS: list[tuple[list[int], list[int]]] = [
    # US Comcast, Cablevision, Verizon
    ([47, 0], [127, 255]),
    ([73, 0], [1, 127]),
    ([73, 131], [0, 255]),
    ([73, 182], [0, 255]),
    ([75, 100], [0, 255]),
    ([104, 128], [0, 255]),
    ([107, 150], [0, 255]),
    ([172, 220], [0, 255]),
    ([174, 0], [0, 255]),
    ([184, 0], [0, 255]),
    # UK BT
    ([86, 128], [127, 255]),
    ([81, 132], [63, 255]),
    # DE Telekom
    ([91, 64], [63, 255]),
    ([80, 128], [63, 255]),
    # FR Orange
    ([90, 0], [63, 255]),
    ([86, 192], [63, 255]),
    # IT Telecom Italia
    ([79, 0], [63, 255]),
    ([87, 0], [31, 255]),
    # BR Vivo
    ([177, 0], [127, 255]),
    # AU Telstra
    ([101, 160], [31, 255]),
    # IN Jio
    ([49, 32], [31, 255]),
    # CA Rogers
    ([99, 224], [31, 255]),
]

USER_AGENTS: list[str] = [
    (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
    ),
    (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
    ),
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0',
    (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Safari/605.1.15'
    ),
    (
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
    ),
    (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 '
        'Safari/537.36 Edg/130.0.0.0'
    ),
    (
        'Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) '
        'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 '
        'Mobile/15E148 Safari/604.1'
    ),
    (
        'Mozilla/5.0 (iPad; CPU OS 18_1 like Mac OS X) '
        'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 '
        'Mobile/15E148 Safari/604.1'
    ),
    (
        'Mozilla/5.0 (Linux; Android 14; Pixel 8) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 '
        'Mobile Safari/537.36'
    ),
    (
        'Mozilla/5.0 (Linux; Android 14; SM-S918B) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 '
        'Mobile Safari/537.36'
    ),
]


def _generate_residential_ip() -> str:
    """Pick a random residential IP from the spoofed pool."""
    base, rng = random.choice(IP_POOLS)
    oct3 = base[1] + random.randint(rng[0], rng[1])
    octet4 = (random.randint(0, 254) + 1) if rng[1] else 1
    return f"{base[0]}.{oct3}.{octet4}.{random.randint(1, 254)}"


def _random_ua() -> str:
    return random.choice(USER_AGENTS)


def _stealth_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Generate spoofed headers — mirrors osiris stealthHeaders()."""
    ip = _generate_residential_ip()
    headers = {
        'User-Agent': _random_ua(),
        'Accept-Language': 'en-US,en;q=0.9',
        'X-Forwarded-For': ip,
        'X-Real-IP': ip,
    }
    if extra:
        headers.update(extra)
    return headers


# ──────────────────────────────────────────────────────────────────────────────
# Data Classes
# ──────────────────────────────────────────────────────────────────────────────

class OpenSkySource(Enum):
    """Flight data source."""
    OPENSKY = "opensky"
    ADSBFI = "adsbfi"


@dataclass
class OpenSkyConfig:
    """Low-level config schema for the OpenSky Network API pull."""
    client_id: str = ""
    client_secret: str = ""
    fetch_military: bool = True
    open_sky_url: str = OPENSKY_STATES_URL
    token_url: str = OPENSKY_TOKEN_URL
    adsb_fi_mil_url: str = f"{ADSB_FI_BASE}/mil"
    adsb_fi_regions_url: str = f"{ADSB_FI_BASE}/lat/{{lat}}/lon/{{lon}}/dist/{{dist}}"
    request_timeout: int = 30
    max_retries: int = 5
    base_backoff_ms: int = 5000
    max_backoff_ms: int = 60000
    jitter_factor: float = 0.3
    cache_ttl_ms: int = 90000
    anonymous_interval_ms: int = 900000
    cooldown_ms: int = 15 * 60 * 1000
    # Optional bounding box to scope the OpenSky states/all pull (lamin/lomin/lamax/lomax).
    # None = global pull. When set, only aircraft within the box are requested.
    lamin: float | None = None
    lomin: float | None = None
    lamax: float | None = None
    lomax: float | None = None
    # Router-level cadence control: when True the OpenSky states/all pull is
    # skipped entirely (adsb.fi-only refresh). The persisted router gate decides
    # when OpenSky is due; the connector must not second-guess it per-instance.
    force_skip_open_sky: bool = False


@dataclass
class FlightRecord:
    """A classified flight record after processing."""
    callsign: str
    lat: float
    lng: float
    alt: int
    heading: int
    speed_knots: float | None
    model: str
    icao24: str
    registration: str
    squawk: str
    airline_code: str
    aircraft_category: str
    category: str  # commercial | private | jet | military
    grounded: bool
    nac_p: float | None
    raw_payload: dict[str, Any]
    source: str
    ingested_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "callsign": self.callsign,
            "lat": self.lat,
            "lng": self.lng,
            "alt": self.alt,
            "heading": self.heading,
            "speed_knots": self.speed_knots,
            "model": self.model,
            "icao24": self.icao24,
            "registration": self.registration,
            "squawk": self.squawk,
            "airline_code": self.airline_code,
            "aircraft_category": self.aircraft_category,
            "category": self.category,
            "grounded": self.grounded,
            "nac_p": self.nac_p,
            "source": self.source,
            "ingested_at": self.ingested_at,
        }


@dataclass
class StagingDataset:
    """Raw append-only staging dataset (Foundry Raw Dataset mimic)."""

    def __init__(self, path: str = "/tmp/opensky_staging.jsonl"):
        self.path = path
        self._records: list[dict[str, Any]] = []

    def append(self, record: dict[str, Any]) -> None:
        self._records.append(record)

    def snapshot(self) -> list[dict[str, Any]]:
        return list(self._records)


# ──────────────────────────────────────────────────────────────────────────────
# Flight Classification Logic
# (ported from osiris classifyFlight())
# ──────────────────────────────────────────────────────────────────────────────

def classify_flight(f: dict[str, Any]) -> FlightRecord | None:
    """
    Classify a raw aircraft state into commercial / private / jet / military.

    Mirrors the osiris classifyFlight() logic: OpenSky supplies no aircraft
    type, and its ADS-B emitter category is "no information" for ~96% of
    aircraft even with extended=1.  The callsign (airline designator vs
    registration) is the primary discriminator for the bulk of traffic.
    """
    model_upper = (f.get('t', '') or '').upper()
    flight_str = (f.get('flight', '') or '').strip().upper()
    db_flags = f.get('dbFlags', 0)

    if model_upper == 'TWR':
        return None

    lat = f.get('lat')
    lon = f.get('lon')
    if lat is None or lon is None:
        return None

    callsign = flight_str or f.get('hex', '') or 'UNKNOWN'

    alt_raw = f.get('alt_baro')
    alt_meters = (alt_raw * 0.3048) if isinstance(alt_raw, (int, float)) else 0
    gs_val = f.get('gs')
    speed_knots = round(gs_val * 1.94384, 1) if isinstance(gs_val, (int, float)) else None
    heading = f.get('track', 0)
    is_heli = model_upper in HELI_TYPES or f.get('category_os') == 8
    is_grounded = isinstance(alt_raw, (int, float)) and alt_raw < 100

    is_os_military = f.get('category_os') == 14
    is_os_high_perf = f.get('category_os') == 7
    is_os_light = f.get('category_os') == 2
    is_os_heavy = f.get('category_os') in (4, 5, 6)

    airline_match = AIRLINE_CODE_RE.match(callsign)
    airline_code = airline_match.group(1) if airline_match else ''

    is_ga_callsign = not airline_code and bool(CALLSIGN_RE.match(flight_str))
    cruises_like_a_jet = alt_meters > JET_CRUISE_ALT_M and (speed_knots or 0) > JET_CRUISE_KTS

    category = 'commercial'
    if (is_os_military or (db_flags & 1) or model_upper in MILITARY_INDICATORS or
            re.match(r'^(RCH|KING|DUKE|EVAC|JAKE|REACH|CONVOY)\d', flight_str)):
        category = 'military'
    elif model_upper in AIRLINER_TYPES or is_os_heavy:
        category = 'commercial'
    elif (airline_code in BIZJET_OPERATORS or model_upper in PRIVATE_JET_TYPES or
          is_os_high_perf or (is_ga_callsign and cruises_like_a_jet)):
        category = 'jet'
    elif is_ga_callsign or is_os_light:
        category = 'private'

    return FlightRecord(
        callsign=callsign,
        lat=round(lat * 100000) / 100000,
        lng=round(lon * 100000) / 100000,
        alt=round(alt_meters) if alt_meters else 0,
        heading=round(heading),
        speed_knots=speed_knots,
        model=f.get('t', 'Unknown'),
        icao24=f.get('hex', ''),
        registration=f.get('r', 'N/A'),
        squawk=f.get('squawk', ''),
        airline_code=airline_code,
        aircraft_category='heli' if is_heli else 'plane',
        category=category,
        grounded=is_grounded,
        nac_p=f.get('nac_p'),
        raw_payload=f,
        source=f.get('_source', 'unknown'),
    )


def aggregate_jamming(points: list[dict[str, Any]], threshold: int) -> list[dict[str, Any]]:
    """Aggregate GPS-jamming suspect aircraft into a 2-degree grid (ported from osiris)."""
    if not points:
        return []
    grid: dict[str, dict[str, Any]] = {}
    grid_size = 2

    for p in points:
        g_lat = (int(p['lat']) // grid_size) * grid_size
        g_lng = (int(p['lng']) // grid_size) * grid_size
        key = f"{g_lat},{g_lng}"
        if key not in grid:
            grid[key] = {
                'lat': g_lat + grid_size / 2,
                'lng': g_lng + grid_size / 2,
                'count': 0,
                'total_nac_p': 0,
            }
        cell = grid[key]
        cell['count'] += 1
        cell['total_nac_p'] += p['nac_p']

    result = []
    for cell in grid.values():
        if cell['count'] >= 3:
            severity = round((1 - (cell['total_nac_p'] / cell['count']) / threshold) * 100)
            result.append({
                'lat': cell['lat'],
                'lng': cell['lng'],
                'severity': severity,
                'count': cell['count'],
            })
    return result


# ──────────────────────────────────────────────────────────────────────────────
# OpenSky Connector
# ──────────────────────────────────────────────────────────────────────────────

class OpenSkyConnector:
    """High-reliability OpenSky Network + adsb.fi sync job with OAuth2."""

    _cache: dict[str, list[dict[str, Any]]] = {}

    def __init__(
        self,
        config: OpenSkyConfig,
        staging: StagingDataset,
        aiohttp_session: aiohttp.ClientSession | None = None,
    ):
        self.config = config
        self.staging = staging
        self._session = aiohttp_session

        # Cached state (mirrors osiris module-level caches)
        self._cached_data: dict[str, Any] | None = None
        self._last_fetch_time: float = 0
        self._os_snapshot: list[dict[str, Any]] = []
        self._os_snapshot_time: float = 0
        self._fetch_promise: asyncio.Future | None = None
        self._opensky_cooldown_until: float = 0

        # OAuth2 token state
        self._os_token: str | None = None
        self._os_token_expiry: float = 0

    # ── Session management ──────────────────────────────────────────────────

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        """Close the aiohttp session if we own it."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    # ── OAuth2 token ────────────────────────────────────────────────────────

    def has_open_sky_creds(self) -> bool:
        return bool(self.config.client_id and self.config.client_secret)

    def _open_sky_interval(self) -> int:
        if self.has_open_sky_creds():
            return self.config.cache_ttl_ms
        return self.config.anonymous_interval_ms

    async def _get_open_sky_token(self, session: aiohttp.ClientSession) -> str | None:
        """Fetch an OpenSky OAuth2 client_credentials token."""
        if not self.has_open_sky_creds():
            return None
        if self._os_token and time.time() * 1000 < self._os_token_expiry:
            return self._os_token

        data = {
            'grant_type': 'client_credentials',
            'client_id': self.config.client_id,
            'client_secret': self.config.client_secret,
        }
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        try:
            async with session.post(
                self.config.token_url,
                data=data,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if not resp.ok:
                    logger.warning("OpenSky token failed: %s", resp.status)
                    return None
                token_data = await resp.json()
                if not token_data.get('access_token'):
                    logger.warning("OpenSky token response missing access_token")
                    return None
                self._os_token = token_data['access_token']
                self._os_token_expiry = time.time() * 1000 + (
                    (token_data.get('expires_in', 1800) - 60) * 1000
                )
                return self._os_token
        except Exception as e:
            logger.warning("OpenSky token error: %s", e)
            return None

    # ── Raw HTTP helpers ────────────────────────────────────────────────────

    def _compute_backoff(
        self, attempt: int, max_retries: int, base_ms: int, max_ms: int, jitter: float
    ) -> float:
        """Jittered exponential backoff: base * 2^attempt * (1 + jitter)."""
        exponential = base_ms * (2 ** attempt)
        jittered = exponential * (1 + jitter * (attempt / max(1, max_retries)))
        return min(jittered, max_ms)

    async def _stealth_fetch(
        self, session: aiohttp.ClientSession, url: str, **kwargs
    ) -> dict[str, Any] | None:
        """Fetch JSON with stealth headers (mirrors osiris stealthFetch)."""
        headers = _stealth_headers(kwargs.pop('headers', None))
        timeout = aiohttp.ClientTimeout(total=kwargs.pop('timeout', self.config.request_timeout))
        max_retries = self.config.max_retries
        base_backoff = self.config.base_backoff_ms
        max_backoff = self.config.max_backoff_ms
        jitter = self.config.jitter_factor

        for attempt in range(max_retries + 1):
            try:
                async with session.get(url, headers=headers, timeout=timeout, **kwargs) as resp:
                    if resp.status == 429:
                        backoff = self._compute_backoff(attempt, max_retries, base_backoff, max_backoff, jitter)  # noqa: E501
                        logger.warning("OpenSky rate limited (429), backing off %.1fs (attempt %d/%d)",  # noqa: E501
                                       backoff / 1000, attempt + 1, max_retries + 1)
                        await asyncio.sleep(backoff / 1000)
                        continue
                    if resp.status >= 500:
                        backoff = self._compute_backoff(attempt, max_retries, base_backoff, max_backoff, jitter)  # noqa: E501
                        logger.warning("OpenSky server error (%d), backing off %.1fs", resp.status, backoff / 1000)  # noqa: E501
                        await asyncio.sleep(backoff / 1000)
                        continue
                    if resp.status >= 400:
                        body = await resp.text()
                        logger.error("OpenSky HTTP %d: %s", resp.status, body)
                        return None
                    return await resp.json()
            except TimeoutError:
                if attempt < max_retries:
                    backoff = self._compute_backoff(attempt, max_retries, base_backoff, max_backoff, jitter)  # noqa: E501
                    logger.warning("OpenSky timeout, retrying in %.1fs", backoff / 1000)
                    await asyncio.sleep(backoff / 1000)
                    continue
                logger.error("OpenSky request timed out after %d attempts", max_retries + 1)
                return None
            except aiohttp.ClientError as exc:
                if attempt < max_retries:
                    backoff = self._compute_backoff(attempt, max_retries, base_backoff, max_backoff, jitter)  # noqa: E501
                    logger.warning("OpenSky connection error (%s), retrying in %.1fs", exc, backoff / 1000)  # noqa: E501
                    await asyncio.sleep(backoff / 1000)
                    continue
                logger.error("OpenSky connection failed: %s", exc)
                return None
            except Exception as exc:
                if attempt < max_retries:
                    backoff = self._compute_backoff(attempt, max_retries, base_backoff, max_backoff, jitter)  # noqa: E501
                    logger.warning("OpenSky request failed (%s), retrying in %.1fs", exc, backoff / 1000)  # noqa: E501
                    await asyncio.sleep(backoff / 1000)
                    continue
                logger.error("OpenSky request failed after %d attempts: %s", max_retries + 1, exc)
                return None

        return None

    # ── OpenSky states/all ─────────────────────────────────────────────────

    def _bbox_query(self) -> str:
        """Build the lamin/lomin/lamax/lomax query string if a bbox is configured."""
        c = self.config
        if c.lamin is not None and c.lomin is not None and c.lamax is not None and c.lomax is not None:
            return f"lamin={c.lamin}&lomin={c.lomin}&lamax={c.lamax}&lomax={c.lomax}"
        return ""

    async def _fetch_open_sky_snapshot(self, session: aiohttp.ClientSession, token: str | None) -> list[dict[str, Any]]:  # noqa: E501
        """Fetch the global aircraft state vector from OpenSky /states/all?extended=1."""
        headers = {}
        if token:
            headers['Authorization'] = f'Bearer {token}'

        url = self.config.open_sky_url
        bbox = self._bbox_query()
        if bbox:
            url = f"{url}&{bbox}"

        data = await self._stealth_fetch(session, url, headers=headers)
        if data is None:
            return []

        states = data.get('states', [])
        if len(states) > 100:
            snapshot = []
            for s in states:
                if len(s) >= 18:
                    snapshot.append({
                        'hex': s[0],
                        'flight': (s[1] or '').strip() if s[1] else '',
                        'lon': s[5],
                        'lat': s[6],
                        'alt_baro': s[7] if isinstance(s[7], (int, float)) else None,
                        'gs': s[9] if isinstance(s[9], (int, float)) else None,
                        'track': s[10],
                        'squawk': s[14],
                        'category_os': s[17] if len(s) > 17 else None,
                    })
            return snapshot
        return []

    # ── adsb.fi military feed ───────────────────────────────────────────────

    async def _fetch_adsb_fi_mil(self, session: aiohttp.ClientSession) -> list[dict[str, Any]]:
        """Fetch the adsb.fi military aircraft feed."""
        data = await self._stealth_fetch(session, self.config.adsb_fi_mil_url)
        if data is None:
            return []
        return data.get('ac', [])

    async def _fetch_adsb_fi_region(self, session: aiohttp.ClientSession, lat: float, lon: float) -> list[dict[str, Any]]:  # noqa: E501
        """Fetch aircraft from a single adsb.fi regional endpoint (paced ~1 req/s)."""
        url = self.config.adsb_fi_regions_url.format(
            lat=lat, lon=lon, dist=ADSB_MAX_DIST
        )
        data = await self._stealth_fetch(session, url, timeout=12)
        if data is None:
            return []
        return data.get('ac', [])

    def _ingest_ac(self, raw: list[dict[str, Any]], into: list[dict[str, Any]], seen: set[str]) -> int:  # noqa: E501
        """Deduplicate and ingest raw aircraft by icao24 hex."""
        added = 0
        for ac in raw:
            hex_val = (ac.get('hex', '') or '').lower().strip()
            if hex_val and hex_val not in seen:
                seen.add(hex_val)
                into.append(ac)
                added += 1
        return added

    # ── Main pull ──────────────────────────────────────────────────────────

    async def pull(self) -> dict[str, Any]:
        """
        Pull aviation data from OpenSky Network (with adsb.fi military fallback)
        and classify all aircraft.

        Returns a report dict mirroring the osiris response format:
        {
            commercial_flights, private_flights, private_jets,
            military_flights, gps_jamming,
            total, source, providers, timestamp
        }
        """
        session = await self._get_session()

        # Check response cache (osiris 90s TTL)
        now = time.time() * 1000
        if self._cached_data and (now - self._last_fetch_time) < self.config.cache_ttl_ms:
            return self._cached_data

        # Determine if OpenSky is due for a fetch
        skip_open_sky = (
            self.config.force_skip_open_sky or
            now < self._opensky_cooldown_until or
            (now - self._os_snapshot_time) < self._open_sky_interval()
        )

        all_raw: list[dict[str, Any]] = []
        seen_hex: set[str] = set()

        token = None if skip_open_sky else await self._get_open_sky_token(session)

        # Phase 1+2: adsb.fi military AND OpenSky in parallel (OpenSky skipped
        # cleanly when the router gate says it is not due).
        mil_task = self._fetch_adsb_fi_mil(session)
        os_task = self._fetch_open_sky_snapshot(session, token) if not skip_open_sky else None

        if os_task is not None:
            mil_results, os_results = await asyncio.gather(
                mil_task, os_task, return_exceptions=True
            )
        else:
            mil_results = await mil_task
            os_results = 'skipped'  # sentinel: gate said not due (NOT a failure)

        # Process military feed results
        if isinstance(mil_results, list):
            self._ingest_ac(mil_results, all_raw, seen_hex)
        mil_count = len(all_raw)

        # Process OpenSky snapshot
        if os_results is not None and not isinstance(os_results, Exception):
            if isinstance(os_results, list) and len(os_results) > 0:
                self._os_snapshot = os_results
                self._os_snapshot_time = now
        open_sky_worked = len(self._os_snapshot) > 0

        # Re-check for 429 handling (mirrors osiris cooldown).
        # 'skipped' = gate deferral, must not enter the failure cooldown.
        if os_results is None:
            self._opensky_cooldown_until = now + self.config.cooldown_ms
            logger.warning("OpenSky 429 — cooling down %d min", self.config.cooldown_ms // 60000)

        # Merge OpenSky snapshot into all_raw
        self._ingest_ac(self._os_snapshot, all_raw, seen_hex)

        # Phase 3: Regional sweep — last resort only
        if not open_sky_worked:
            logger.warning("No OpenSky snapshot — falling back to adsb.fi regional sweep")
            for r in REGIONS:
                region_ac = await self._fetch_adsb_fi_region(session, r['lat'], r['lon'])
                self._ingest_ac(region_ac, all_raw, seen_hex)
                await asyncio.sleep(ADSB_FI_GAP_MS / 1000)

            if len(all_raw) == 0:
                logger.error(
                    "Every flight provider returned zero aircraft — "
                    "set OPENSKY_CLIENT_ID/OPENSKY_CLIENT_SECRET (free at opensky-network.org)"
                )

        # Classify all aircraft
        commercial: list[dict[str, Any]] = []
        private_flights: list[dict[str, Any]] = []
        jets: list[dict[str, Any]] = []
        military: list[dict[str, Any]] = []
        gps_jamming: list[dict[str, Any]] = []

        for raw in all_raw:
            # Tag source for classification
            if 'hex' in raw and raw.get('_source') is None:
                raw['_source'] = ('opensky' if open_sky_worked else 'adsbfi')
            record = classify_flight(raw)
            if record is None:
                continue

            if (isinstance(record.nac_p, (int, float)) and
                    record.nac_p <= JAMMING_NACAP_THRESHOLD and
                    not record.grounded):
                gps_jamming.append({
                    'lat': record.lat,
                    'lng': record.lng,
                    'nac_p': record.nac_p,
                    'callsign': record.callsign,
                })

            if record.category == 'military':
                military.append(record.to_dict())
            elif record.category == 'jet':
                jets.append(record.to_dict())
            elif record.category == 'private':
                private_flights.append(record.to_dict())
            else:
                commercial.append(record.to_dict())

        if open_sky_worked:
            source = 'opensky-auth' if self.has_open_sky_creds() else 'opensky-anon'
        elif mil_count > 0:
            source = 'adsbfi-mil'
        else:
            source = 'regional'

        report = {
            "commercial_flights": commercial,
            "private_flights": private_flights,
            "private_jets": jets,
            "military_flights": military,
            "gps_jamming": aggregate_jamming(gps_jamming, JAMMING_NACAP_THRESHOLD),
            "total": len(all_raw),
            "source": source,
            "providers": {
                "adsbfi_mil": mil_count,
                "adsbfi_regional": 0 if open_sky_worked else (len(all_raw) - mil_count),
                "opensky": len(self._os_snapshot),
                "opensky_auth": self.has_open_sky_creds(),
                "opensky_age_s": round((now - self._os_snapshot_time) / 1000) if self._os_snapshot_time else None,  # noqa: E501
            },
            "timestamp": datetime.now(UTC).isoformat(),
        }

        self._cached_data = report
        self._last_fetch_time = now
        return report

    async def persist_raw(self, records: list[dict[str, Any]]) -> int:
        """Persist raw flight records to the staging dataset."""
        for payload in records:
            guid = str(uuid.uuid5(uuid.NAMESPACE_URL, payload.get("icao24", "unknown")))
            self.staging.append({
                "guid": guid,
                "icao24": payload.get("icao24", ""),
                "payload": payload,
                "ingested_at": datetime.now(UTC).isoformat(),
                "record_type": "aviation_flight",
            })
        return len(records)

    async def execute(self) -> dict[str, Any]:
        """Execute full pull + staging pipeline."""
        report = await self.pull()
        for category_key in ("commercial_flights", "private_flights", "private_jets", "military_flights"):  # noqa: E501
            await self.persist_raw(report[category_key])
        logger.info(
            "OpenSky pull complete: %d total flights (%d commercial, %d private, %d jets, %d military)",  # noqa: E501
            report["total"],
            len(report["commercial_flights"]),
            len(report["private_flights"]),
            len(report["private_jets"]),
            len(report["military_flights"]),
        )
        return report


class OpenSkyConnectorFactory:
    """Factory for creating OpenSkyConnector instances."""

    _shared_session: aiohttp.ClientSession | None = None

    @classmethod
    async def create_session(cls) -> aiohttp.ClientSession:
        if cls._shared_session is None or cls._shared_session.closed:
            headers = _stealth_headers()
            cls._shared_session = aiohttp.ClientSession(headers=headers)
        return cls._shared_session

    @classmethod
    async def reset_session(cls) -> None:
        if cls._shared_session and not cls._shared_session.closed:
            await cls._shared_session.close()
        cls._shared_session = None

    @classmethod
    async def close_session(cls) -> None:
        await cls.reset_session()
