"""
AISStream.io vessel tracking connector.

Manages a persistent WebSocket connection to AISStream.io for real-time
AIS vessel position data over the Philippines EEZ. Falls back to a
synthetic mock vessel generator when no API key is configured.

AISStream.io (https://aisstream.io) provides free global AIS data via
WebSocket. Position reports include MMSI, vessel name, type, position,
speed, course, heading, and navigational status.

Protocol:
  - Connect: wss://stream.aisstream.io/v0/stream
  - Subscribe within 3s: {"APIKey": "...", "BoundingBoxes": [[[lat,lng],[lat,lng]]], "FilterMessageTypes": ["PositionReport"]}
  - Receive: {"MetaData": {...}, "PositionReport": {...}}

Vessel classification follows IMO/AIS ship type codes:
  20-29:    HSC (high speed craft)
  30-39:    Fishing / Tugs / Dredger / Towing
  40-49:    HSC passenger
  50-59:    Passenger / Naval
  60-69:    Passenger
  70-79:    Cargo
  80-89:    Tanker
  90-99:    Other (often unknown/classified)
"""

import asyncio
import json
import logging
import math
import os
import random
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Optional

import aiohttp

logger = logging.getLogger("magritte.connector.vessels")


# ──────────────────────────────────────────────────────────────────────────────
# Vessel Classification
# ──────────────────────────────────────────────────────────────────────────────

class VesselCategory(str, Enum):
    NAVY = "navy"
    COAST_GUARD = "coast_guard"
    CARGO = "cargo"
    TANKER = "tanker"
    FISHING = "fishing"
    PASSENGER = "passenger"
    UNKNOWN = "unknown"


# AIS ship type code ranges (IMO 1373)
AIS_TYPE_RANGES = [
    (30, 39, VesselCategory.FISHING),
    (50, 59, VesselCategory.PASSENGER),
    (60, 69, VesselCategory.PASSENGER),
    (70, 79, VesselCategory.CARGO),
    (80, 89, VesselCategory.TANKER),
]

# Philippine Navy / Coast Guard vessel name patterns
PH_NAVAL_PATTERNS = [
    "BRP", "ACERO", "AGUINALDO", "BONIFACIO", "DELOS SANTOS",
    "JACINTO", "MAGBANUA", "MALAPAD", "EMILIO", "TALOS",
    "DEL PILAR", "GREGORIO", "ANTONIO", "RAJAH",
]
PH_CG_PATTERNS = [
    "PCG", "COSG", "SULTAN", "TAN", "BORJA", "DAVID",
    "FRANCISCO", "GAVINO", "HILARIA", "LEGRIS",
]

# Name heuristics for other categories (used when ShipType is missing from PositionReport)
CARGO_NAME_PATTERNS = [
    "MSC", "WAN HAI", "MAERSK", "CMA CGM", "EVERGREEN", "PIL",
    "OOCL", "APL", "SITC", "ONE", "HAPAG", "ZIM", "YANG MING",
    "CNC", "TS LINES", "RCL", "SWIRE", "COSCO",
    "KMTC", "HANJIN", "HYUNDAI", "HMM", "SM LINE",
    "TSK", "BAL", "PACIFIC BASIN", "BULK",
    "STAR BULK", "OLDENDORFF", "CARGILL", "COFCO",
    "X-PRESS", "SINOKOR", "HEUNG-A",
]

TANKER_NAME_PATTERNS = [
    "TANKER", "OIL TANKER", "CHEMICAL", "PETROCHEM", "GAS",
    "PETROBRAS", "SHELL", "EXXON", "BP ",
    "EAGLE", "FRONT", "NORDIC", "STENA", "TEEKAY",
    "DHT", "INTERNATIONAL SEAWAYS", "OSG", "SCORPIO",
]

PASSENGER_NAME_PATTERNS = [
    "2GO", "SUPERFERRY", "FASTCRAFT", "RO-RO", "RORO", "FERRY",
    "TRANS-ASIA", "NAVIOS", "STARLIGHT",
    "OCEANJET", "WEESAM", "LITE", "MONTENEGRO",
]

FISHING_NAME_PATTERNS = [
    "FV ", "FISHING", "LAPU-LAPU", "MINDANAO", "VISAYAS",
    "HARVEST", "HENG HUI", "HONGFA", "MC ZION", "SHENGPING",
    "SOUTHWARD FLYING", "STELLA MARIS", "DONA",
]

# AIS vessel type code → human-readable name
_VESSEL_TYPE_NAMES = {
    20: "Wing in Ground", 21: "Wing in Ground", 22: "Wing in Ground",
    23: "Wing in Ground", 24: "Wing in Ground", 25: "Wing in Ground",
    26: "Wing in Ground", 27: "Wing in Ground", 28: "Wing in Ground",
    29: "Wing in Ground",
    30: "Fishing", 31: "Towing", 32: "Towing (large)", 33: "Dredger",
    34: "Diving Ops", 35: "Military Ops", 36: "Sailing", 37: "Pleasure",
    40: "HSC", 41: "HSC", 42: "HSC", 43: "HSC", 44: "HSC",
    45: "HSC", 46: "HSC", 47: "HSC", 48: "HSC", 49: "HSC",
    50: "Pilot Vessel", 51: "Search and Rescue", 52: "Tug",
    53: "Port Tender", 54: "Anti-Pollution", 55: "Law Enforcement",
    56: "Medical", 57: "RR HIS Resolution", 58: "Passenger",
    60: "Passenger", 61: "Passenger", 62: "Passenger", 63: "Passenger",
    64: "Passenger", 65: "Passenger", 66: "Passenger", 67: "Passenger",
    68: "Passenger", 69: "Passenger",
    70: "Cargo", 71: "Cargo", 72: "Cargo", 73: "Cargo",
    74: "Cargo", 75: "Cargo", 76: "Cargo", 77: "Cargo",
    78: "Cargo", 79: "Cargo",
    80: "Tanker", 81: "Tanker", 82: "Tanker", 83: "Tanker",
    84: "Tanker", 85: "Tanker", 86: "Tanker", 87: "Tanker",
    88: "Tanker", 89: "Tanker",
    90: "Other", 91: "Other", 92: "Other", 93: "Other",
    94: "Other", 95: "Other", 96: "Other", 97: "Other",
    98: "Other", 99: "Other",
}

# Navigational status labels
NAV_STATUS = {
    0: "underway_using_engine",
    1: "at_anchor",
    2: "not_under_command",
    3: "restricted_manoeuvrability",
    4: "constrained_by_draft",
    5: "moored",
    6: "aground",
    7: "engaged_in_fishing",
    8: "underway_sailing",
    15: "undefined",
}


# ──────────────────────────────────────────────────────────────────────────────
# MMSI MID Flag State Lookup
# ──────────────────────────────────────────────────────────────────────────────

MMSI_MID_FLAGS = {
    "201": "Albania", "202": "Andorra", "203": "Austria", "204": "Netherlands",
    "205": "Belgium", "206": "Belarus", "207": "Bulgaria", "208": "Vatican City",
    "209": "Cyprus", "210": "Cyprus", "211": "Germany", "212": "Cyprus",
    "213": "Georgia", "214": "Moldova", "215": "Malta", "216": "Armenia",
    "218": "Germany", "219": "Denmark", "220": "Denmark", "224": "Spain",
    "225": "Spain", "226": "France", "227": "France", "228": "France",
    "229": "Malta", "230": "Finland", "231": "Finland", "232": "United Kingdom",
    "233": "United Kingdom", "234": "United Kingdom", "235": "United Kingdom",
    "236": "Gibraltar", "237": "Greece", "238": "Greece", "239": "Greece",
    "240": "Greece", "241": "Greece", "242": "Morocco", "243": "Hungary",
    "244": "Netherlands", "245": "Netherlands", "246": "Netherlands",
    "247": "Netherlands", "248": "Malta", "249": "Malta", "250": "Ireland",
    "251": "Iceland", "252": "Liechtenstein", "253": "Luxembourg",
    "254": "Monaco", "255": "Portugal", "256": "Portugal", "257": "Portugal",
    "258": "Norway", "259": "Norway", "260": "Norway", "261": "Norway",
    "262": "Denmark", "263": "Denmark", "264": "Romania", "265": "Sweden",
    "266": "Sweden", "267": "Sweden", "268": "Sweden", "269": "Switzerland",
    "270": "Czech Republic", "271": "Turkey", "272": "Ukraine",
    "273": "Russia", "274": "North Macedonia", "275": "Russia",
    "276": "Russia", "277": "Russia", "278": "Russia", "279": "Russia",
    "280": "Luxembourg", "281": "Germany", "301": "Antigua and Barbuda",
    "303": "Antigua and Barbuda", "304": "Antigua and Barbuda",
    "305": "Antigua and Barbuda", "306": "Netherlands", "307": "Netherlands",
    "308": "Aruba", "309": "Bahamas", "310": "Bermuda", "311": "Bahamas",
    "312": "Belize", "314": "Barbados", "316": "Canada", "319": "Cayman Islands",
    "321": "Costa Rica", "325": "Cuba", "329": "Dominica",
    "331": "Dominican Republic", "334": "Honduras", "335": "Jamaica",
    "336": "Panama", "337": "Panama", "338": "United States",
    "339": "Mexico", "341": "Saint Kitts and Nevis", "345": "Mexico",
    "351": "Panama", "352": "Panama", "353": "Panama", "354": "Panama",
    "355": "Panama", "356": "Panama", "357": "Panama",
    "401": "Afghanistan", "403": "Saudi Arabia", "405": "Bangladesh",
    "406": "Myanmar", "407": "Vietnam", "408": "Bahrain",
    "410": "Bhutan", "412": "China", "413": "China", "414": "China",
    "416": "Taiwan", "417": "Sri Lanka", "419": "India", "422": "Iran",
    "425": "Iraq", "428": "Israel", "431": "Japan", "432": "Japan",
    "434": "Kazakhstan", "436": "Kyrgyzstan", "437": "Uzbekistan",
    "438": "Jordan", "440": "South Korea", "441": "South Korea",
    "445": "South Korea", "447": "Kuwait", "450": "Lebanon",
    "451": "Kyrgyzstan", "455": "Maldives", "457": "Mongolia",
    "458": "Oman", "459": "Nepal", "461": "Pakistan", "463": "Pakistan",
    "470": "United Arab Emirates", "471": "United Arab Emirates",
    "472": "Tajikistan", "473": "Yemen", "477": "Hong Kong",
    "501": "French Southern and Antarctic Lands", "503": "Australia",
    "510": "Micronesia", "511": "Marshall Islands", "512": "New Zealand",
    "514": "Cambodia", "515": "Myanmar", "516": "Christmas Island",
    "525": "Indonesia", "529": "Kiribati", "533": "Malaysia",
    "538": "Marshall Islands", "548": "Philippines", "553": "Papua New Guinea",
    "555": "Pitcairn Islands", "557": "Singapore", "559": "Singapore",
    "563": "Singapore", "564": "Singapore", "565": "Singapore",
    "566": "Singapore", "567": "Thailand", "572": "Tonga",
    "574": "Vietnam", "576": "Vanuatu", "577": "Samoa",
    "601": "South Africa", "603": "Angola", "605": "Algeria",
    "607": "Saint Pierre and Miquelon", "608": "Ascension Island",
    "609": "Democratic Republic of the Congo", "610": "Benin",
    "612": "Republic of the Congo", "613": "Cameroon",
    "614": "Comoros", "615": "Central African Republic",
    "616": "Cape Verde", "618": "Ivory Coast", "619": "Djibouti",
    "620": "Egypt", "621": "Eritrea", "622": "Ethiopia",
    "624": "Gabon", "625": "Djibouti", "626": "Equatorial Guinea",
    "627": "Ghana", "628": "Gambia", "629": "Guinea-Bissau",
    "630": "Guinea", "631": "Equatorial Guinea", "632": "Liberia",
    "633": "Burkina Faso", "634": "Kenya", "635": "Democratic Republic of the Congo",
    "636": "Liberia", "637": "Lesotho", "638": "Libya",
    "642": "Madagascar", "644": "Mauritius", "645": "Mauritius",
    "647": "Mozambique", "649": "Mauritius", "650": "Malawi",
    "654": "Madagascar", "655": "Malawi", "656": "Niger",
    "657": "Nigeria", "659": "Gabon", "660": "Senegal",
    "661": "Sierra Leone", "662": "Seychelles", "663": "Sao Tome and Principe",
    "664": "South Africa", "667": "Tunisia", "668": "Togo",
    "669": "Tanzania", "670": "Uganda", "674": "Tanzania",
    "675": "Nigeria", "676": "DR Congo", "677": "Tanzania",
    "701": "Argentina", "710": "Brazil", "720": "Bolivia",
    "725": "Chile", "730": "Colombia", "735": "Ecuador",
    "740": "Falkland Islands", "745": "Guiana",
    "750": "Guyana", "755": "Paraguay", "760": "Peru",
    "765": "Suriname", "770": "Uruguay", "775": "Venezuela",
}


def mmsi_flag(mmsi: str) -> str:
    """Derive flag country from MMSI MID (first 3 digits)."""
    mid = mmsi[:3] if mmsi and len(mmsi) >= 3 else ""
    return MMSI_MID_FLAGS.get(mid, "")


# ──────────────────────────────────────────────────────────────────────────────
# Naval Vessels Database Loader
# ──────────────────────────────────────────────────────────────────────────────

_NAVAL_DB: dict[str, dict] = {}  # name_upper -> entry
_NAVAL_DB_LOADED = False

def _load_naval_db():
    """Load naval-vessels.json from a-san/data/ into memory (once)."""
    global _NAVAL_DB, _NAVAL_DB_LOADED
    if _NAVAL_DB_LOADED:
        return
    _NAVAL_DB_LOADED = True
    paths = [
        "/home/alieninc/a-san/data/naval-vessels.json",
        os.path.join(os.path.dirname(__file__), "..", "..", "a-san", "data", "naval-vessels.json"),
    ]
    for p in paths:
        try:
            if not os.path.exists(p):
                continue
            with open(p) as f:
                raw = json.load(f)
            entries = raw.get("entries", []) if isinstance(raw, dict) else raw
            for e in entries:
                name = (e.get("designation") or "").upper().strip()
                if name:
                    _NAVAL_DB[name] = e
                for alt in (e.get("alt_names") or []):
                    alt_u = alt.upper().strip()
                    if alt_u and alt_u not in _NAVAL_DB:
                        _NAVAL_DB[alt_u] = e
            print(f"[vessels] Naval DB loaded: {len(_NAVAL_DB)} name entries from {p}", flush=True)
            return
        except Exception as ex:
            print(f"[vessels] Naval DB load failed ({p}): {ex}", flush=True)


def lookup_naval(name: str) -> Optional[dict]:
    """Look up a vessel name in the naval database. Returns entry or None."""
    _load_naval_db()
    name_upper = (name or "").upper().strip()
    if not name_upper:
        return None
    # Exact match
    if name_upper in _NAVAL_DB:
        return _NAVAL_DB[name_upper]
    # Substring match (for names like "BRP JOSE RIZAL" matching "Jose Rizal class")
    for key, entry in _NAVAL_DB.items():
        if key in name_upper or name_upper in key:
            return entry
    return None


def classify_vessel(mmsi: str, name: str, ship_type: int) -> VesselCategory:
    """Classify a vessel by AIS type code and name heuristics."""
    name_upper = (name or "").upper().strip()

    # Name-based overrides (military / coast guard — highest priority)
    for pat in PH_CG_PATTERNS:
        if pat in name_upper:
            return VesselCategory.COAST_GUARD
    for pat in PH_NAVAL_PATTERNS:
        if pat in name_upper:
            return VesselCategory.NAVY

    # AIS type code ranges (if available from ShipStaticData)
    if ship_type:
        for lo, hi, cat in AIS_TYPE_RANGES:
            if ship_type in range(lo, hi + 1):
                return cat

    # Name heuristics for when ship_type=0 (PositionReport-only)
    for pat in FISHING_NAME_PATTERNS:
        if pat in name_upper:
            return VesselCategory.FISHING
    for pat in PASSENGER_NAME_PATTERNS:
        if pat in name_upper:
            return VesselCategory.PASSENGER
    for pat in TANKER_NAME_PATTERNS:
        if pat in name_upper:
            return VesselCategory.TANKER
    for pat in CARGO_NAME_PATTERNS:
        if pat in name_upper:
            return VesselCategory.CARGO

    # MMSI prefix heuristics (Philippines: 548xxx)
    if mmsi and mmsi.startswith("548"):
        if ship_type in range(50, 60):
            return VesselCategory.NAVY

    return VesselCategory.UNKNOWN


def category_label(cat: VesselCategory) -> str:
    """Human-readable label for a vessel category."""
    return {
        VesselCategory.NAVY: "Philippine Navy",
        VesselCategory.COAST_GUARD: "Philippine Coast Guard",
        VesselCategory.CARGO: "Cargo",
        VesselCategory.TANKER: "Tanker",
        VesselCategory.FISHING: "Fishing",
        VesselCategory.PASSENGER: "Passenger",
        VesselCategory.UNKNOWN: "Unknown",
    }.get(cat, "Unknown")


def category_color(cat: VesselCategory) -> str:
    """CSS color for vessel category markers."""
    return {
        VesselCategory.NAVY: "#00d4ff",
        VesselCategory.COAST_GUARD: "#00ff88",
        VesselCategory.CARGO: "#ff8c00",
        VesselCategory.TANKER: "#ff4444",
        VesselCategory.FISHING: "#ffd700",
        VesselCategory.PASSENGER: "#a78bfa",
        VesselCategory.UNKNOWN: "#888888",
    }.get(cat, "#888888")


# ──────────────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class VesselConfig:
    """Connector configuration."""
    api_key: str = ""
    # Philippines EEZ bounding box: [[south,west],[north,east]]
    bounding_box: list = field(default_factory=lambda: [
        [4.0, 116.0], [22.0, 128.0]
    ])
    ws_url: str = "wss://stream.aisstream.io/v0/stream"
    mock_interval_s: float = 8.0
    mock_vessel_count: int = 18
    reconnect_base_s: float = 2.0
    reconnect_max_s: float = 60.0
    history_max: int = 2000
    feed_name: str = "aisstream"


# ──────────────────────────────────────────────────────────────────────────────
# Vessel Data Model
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class VesselAIS:
    """Single vessel state vector from AIS or mock."""
    mmsi: str
    name: str
    category: VesselCategory
    lat: float
    lng: float
    sog: float           # speed over ground (knots)
    cog: float           # course over ground (degrees)
    heading: float       # true heading (degrees)
    nav_status: int
    vessel_type_code: int
    timestamp: float     # unix epoch
    imo: int = 0
    call_sign: str = ""
    destination: str = ""
    draught: float = 0.0
    eta: str = ""
    source: str = "ais"
    flag_country: str = ""
    vessel_type_name: str = ""
    description: str = ""
    specs: list = field(default_factory=list)
    naval_db_entry: bool = False

    def to_dict(self) -> dict:
        d = {
            "mmsi": self.mmsi,
            "name": self.name,
            "category": self.category.value,
            "category_label": category_label(self.category),
            "color": category_color(self.category),
            "lat": self.lat,
            "lng": self.lng,
            "sog": round(self.sog, 1),
            "cog": round(self.cog, 1),
            "heading": round(self.heading, 1),
            "nav_status": self.nav_status,
            "nav_status_label": NAV_STATUS.get(self.nav_status, "unknown"),
            "vessel_type_code": self.vessel_type_code,
            "vessel_type_name": self.vessel_type_name,
            "flag_country": self.flag_country,
            "timestamp": self.timestamp,
            "imo": self.imo,
            "call_sign": self.call_sign,
            "destination": self.destination,
            "draught": self.draught,
            "eta": self.eta,
            "source": self.source,
            "age_s": round(time.time() - self.timestamp, 1),
        }
        if self.naval_db_entry:
            d["description"] = self.description
            d["specs"] = self.specs
        return d


# ──────────────────────────────────────────────────────────────────────────────
# Mock Vessel Generator
# ──────────────────────────────────────────────────────────────────────────────

_MOCK_VESSELS = [
    # Navy
    {"mmsi": "548000101", "name": "BRP JOSE RIZAL", "type": 51, "cat": VesselCategory.NAVY,
     "lat": 14.5995, "lng": 120.9842, "sog": 12.0, "heading": 225},
    {"mmsi": "548000102", "name": "BRP ANTONIO LUNA", "type": 51, "cat": VesselCategory.NAVY,
     "lat": 10.3157, "lng": 123.8854, "sog": 8.5, "heading": 310},
    {"mmsi": "548000103", "name": "BRP CONRAD YAP", "type": 52, "cat": VesselCategory.NAVY,
     "lat": 7.0567, "lng": 125.6102, "sog": 14.2, "heading": 175},
    # Coast Guard
    {"mmsi": "548000201", "name": "BRP GABRIELA SILANG", "type": 52, "cat": VesselCategory.COAST_GUARD,
     "lat": 16.4023, "lng": 119.9912, "sog": 16.0, "heading": 135},
    {"mmsi": "548000202", "name": "PCG MALAPAD", "type": 52, "cat": VesselCategory.COAST_GUARD,
     "lat": 9.8500, "lng": 125.9833, "sog": 11.0, "heading": 270},
    {"mmsi": "548000203", "name": "BRP TAN GUARDIAN", "type": 52, "cat": VesselCategory.COAST_GUARD,
     "lat": 13.7563, "lng": 120.9822, "sog": 0.0, "heading": 0},
    # Cargo
    {"mmsi": "548000301", "name": "MSC ANNA", "type": 70, "cat": VesselCategory.CARGO,
     "lat": 12.8797, "lng": 121.7740, "sog": 11.5, "heading": 195},
    {"mmsi": "548000302", "name": "MAERSK SELETAR", "type": 71, "cat": VesselCategory.CARGO,
     "lat": 18.4500, "lng": 120.5667, "sog": 9.3, "heading": 245},
    {"mmsi": "548000303", "name": "WAN HAI 315", "type": 72, "cat": VesselCategory.CARGO,
     "lat": 11.2345, "lng": 124.0012, "sog": 13.8, "heading": 60},
    # Tanker
    {"mmsi": "548000401", "name": "PACIFIC EXPLORER", "type": 80, "cat": VesselCategory.TANKER,
     "lat": 15.1234, "lng": 119.5678, "sog": 7.2, "heading": 315},
    {"mmsi": "548000402", "name": "SEVERN TANKER", "type": 81, "cat": VesselCategory.TANKER,
     "lat": 6.8901, "lng": 126.1234, "sog": 10.5, "heading": 15},
    # Fishing
    {"mmsi": "548000501", "name": "FV LAPU-LAPU", "type": 30, "cat": VesselCategory.FISHING,
     "lat": 11.5833, "lng": 124.3667, "sog": 3.2, "heading": 80},
    {"mmsi": "548000502", "name": "FV VISAYAS", "type": 31, "cat": VesselCategory.FISHING,
     "lat": 9.1234, "lng": 126.5432, "sog": 2.8, "heading": 200},
    {"mmsi": "548000503", "name": "FV MINDANAO", "type": 32, "cat": VesselCategory.FISHING,
     "lat": 7.5678, "lng": 125.9012, "sog": 4.1, "heading": 340},
    # Passenger
    {"mmsi": "548000601", "name": "SUPERFERRY 9", "type": 60, "cat": VesselCategory.PASSENGER,
     "lat": 13.3300, "lng": 121.8300, "sog": 15.5, "heading": 165},
    {"mmsi": "548000602", "name": "2GO TRAVEL", "type": 61, "cat": VesselCategory.PASSENGER,
     "lat": 10.6667, "lng": 122.2333, "sog": 18.0, "heading": 350},
    # Unknown
    {"mmsi": "548000701", "name": "VIGOROUS STAR", "type": 90, "cat": VesselCategory.UNKNOWN,
     "lat": 17.5833, "lng": 122.0167, "sog": 6.7, "heading": 110},
    {"mmsi": "548000702", "name": "OCEAN BREEZE", "type": 99, "cat": VesselCategory.UNKNOWN,
     "lat": 8.1234, "lng": 123.4567, "sog": 5.0, "heading": 280},
]


class MockVesselEngine:
    """Synthetic vessel generator for development without AISStream API key."""

    def __init__(self, config: VesselConfig):
        self.config = config
        self._vessels: dict[str, dict] = {}
        self._seed_vessels()

    def _seed_vessels(self):
        """Seed initial mock vessels with some position jitter."""
        for v in _MOCK_VESSELS:
            jitter_lat = random.uniform(-0.05, 0.05)
            jitter_lng = random.uniform(-0.05, 0.05)
            self._vessels[v["mmsi"]] = {
                "mmsi": v["mmsi"],
                "name": v["name"],
                "type": v["type"],
                "category": v["cat"],
                "lat": v["lat"] + jitter_lat,
                "lng": v["lng"] + jitter_lng,
                "base_lat": v["lat"],
                "base_lng": v["lng"],
                "sog": v["sog"],
                "heading": v["heading"],
                "cog": v["heading"],
                "nav_status": 0 if v["sog"] > 1 else 5,
                "phase": random.uniform(0, 2 * math.pi),
                "speed_var": random.uniform(0.8, 1.2),
                "heading_var": random.uniform(-5, 5),
                "last_update": time.time(),
            }

    def tick(self) -> list[VesselAIS]:
        """Advance all mock vessels and return current state."""
        now = time.time()
        result = []
        for mmsi, v in self._vessels.items():
            dt = now - v["last_update"]
            if dt > 0:
                # Slow random drift for realism
                v["phase"] += random.uniform(0.01, 0.05) * dt
                v["heading"] = (v["heading"] + v["heading_var"] * random.uniform(-0.1, 0.1)) % 360
                speed_factor = v["speed_var"] * (1 + 0.05 * math.sin(v["phase"]))

                # Dead-reckon position
                eff_sog = v["sog"] * speed_factor
                km = eff_sog * 1.852 * dt / 3600
                rad = v["heading"] * math.pi / 180
                v["lat"] += (km * math.cos(rad)) / 110.574
                v["lng"] += (km * math.sin(rad)) / (111.320 * max(0.2, math.cos(v["lat"] * math.pi / 180)))

                # Soft boundary: if drift goes too far from base, nudge back
                dist_lat = v["lat"] - v["base_lat"]
                dist_lng = v["lng"] - v["base_lng"]
                dist_deg = math.sqrt(dist_lat**2 + dist_lng**2)
                if dist_deg > 2.0:
                    pull = 0.01 * (dist_deg - 2.0)
                    v["lat"] -= dist_lat * pull
                    v["lng"] -= dist_lng * pull

                # Keep within EEZ
                v["lat"] = max(4.0, min(22.0, v["lat"]))
                v["lng"] = max(116.0, min(128.0, v["lng"]))

                v["cog"] = v["heading"]
                v["nav_status"] = 0 if eff_sog > 1 else 5
                v["sog"] = eff_sog
                v["last_update"] = now

            result.append(VesselAIS(
                mmsi=mmsi,
                name=v["name"],
                category=v["category"],
                lat=v["lat"],
                lng=v["lng"],
                sog=v["sog"],
                cog=v["cog"],
                heading=v["heading"],
                nav_status=v["nav_status"],
                vessel_type_code=v["type"],
                timestamp=now,
                source="mock",
            ))
        return result

    def get_vessel(self, mmsi: str) -> Optional[VesselAIS]:
        """Get a single mock vessel by MMSI."""
        v = self._vessels.get(mmsi)
        if not v:
            return None
        return VesselAIS(
            mmsi=mmsi,
            name=v["name"],
            category=v["category"],
            lat=v["lat"],
            lng=v["lng"],
            sog=v["sog"],
            cog=v["cog"],
            heading=v["heading"],
            nav_status=v["nav_status"],
            vessel_type_code=v["type"],
            timestamp=v["last_update"],
            source="mock",
        )


# ──────────────────────────────────────────────────────────────────────────────
# AISStream WebSocket Connector
# ──────────────────────────────────────────────────────────────────────────────

class VesselConnector:
    """
    Background vessel tracking connector.

    Mode 1 (real): WebSocket connection to AISStream.io, subscribes to
    Philippines EEZ bounding box, receives PositionReport messages.
    Mode 2 (mock): Synthetic vessel generator with dead-reckon motion.

    Thread-safe vessel snapshot access via get_vessels() / get_vessel().
    """

    def __init__(self, config: Optional[VesselConfig] = None):
        self.config = config or VesselConfig(
            api_key=os.environ.get("AISSTREAM_API_KEY", ""),
        )
        self._vessels: dict[str, VesselAIS] = {}
        self._lock = asyncio.Lock() if hasattr(asyncio, 'Lock') else None
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._mode = "mock" if not self.config.api_key else "real"
        self._connected = False
        self._started_at: Optional[float] = None
        self._messages_received = 0
        self._reconnect_attempts = 0
        self._mock_engine: Optional[MockVesselEngine] = None

        if self._mode == "mock":
            self._mock_engine = MockVesselEngine(self.config)
            logger.info("VesselConnector: MOCK mode (no AISStream API key)")
        else:
            logger.info("VesselConnector: REAL mode (AISStream.io)")

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def messages_received(self) -> int:
        return self._messages_received

    def get_status(self) -> dict:
        """Return connector health status."""
        return {
            "mode": self._mode,
            "running": self._running,
            "connected": self._connected,
            "vessels_tracked": len(self._vessels),
            "messages_received": self._messages_received,
            "reconnect_attempts": self._reconnect_attempts,
            "started_at": self._started_at,
            "uptime_s": round(time.time() - self._started_at, 1) if self._started_at else 0,
            "api_key_configured": bool(self.config.api_key),
        }

    def get_vessels(self, category: Optional[str] = None) -> list[dict]:
        """Return all tracked vessels as dicts, optionally filtered by category."""
        vessels = list(self._vessels.values())
        if category:
            vessels = [v for v in vessels if v.category.value == category]
        return [v.to_dict() for v in sorted(vessels, key=lambda x: x.name)]

    def get_vessel(self, mmsi: str) -> Optional[dict]:
        """Return a single vessel by MMSI."""
        v = self._vessels.get(mmsi)
        return v.to_dict() if v else None

    async def start(self):
        """Start the background vessel tracking task."""
        if self._running:
            return
        self._running = True
        self._started_at = time.time()
        self._task = asyncio.create_task(self._run_loop())
        logger.info("VesselConnector started")

    async def stop(self):
        """Stop the background vessel tracking task."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        if self._session:
            try:
                await self._session.close()
            except Exception:
                pass
            self._session = None
        logger.info("VesselConnector stopped")

    # ── Background loop ──────────────────────────────────────────────────

    async def _run_loop(self):
        """Main background loop: runs WebSocket or mock tick cycle."""
        if self._mode == "mock":
            await self._mock_loop()
        else:
            await self._ws_loop()

    async def _mock_loop(self):
        """Mock mode: tick synthetic vessels at fixed interval."""
        while self._running:
            try:
                vessels = self._mock_engine.tick()
                for v in vessels:
                    self._vessels[v.mmsi] = v
                self._messages_received += 1
            except Exception as e:
                logger.error(f"Mock tick error: {e}")
            await asyncio.sleep(self.config.mock_interval_s)

    async def _ws_loop(self):
        """Real mode: connect to AISStream, subscribe, receive messages."""
        backoff = self.config.reconnect_base_s

        while self._running:
            try:
                self._connected = False
                await self._connect_and_receive()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._reconnect_attempts += 1
                print(f"[vessels] AISStream WS disconnected ({e}), reconnecting in {backoff:.1f}s "
                    f"(attempt #{self._reconnect_attempts})", flush=True)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, self.config.reconnect_max_s)

        self._connected = False

    async def _connect_and_receive(self):
        """Single WebSocket session: connect, subscribe, process messages."""
        timeout = aiohttp.ClientTimeout(total=None, connect=15)
        self._session = aiohttp.ClientSession(timeout=timeout)
        try:
            self._ws = await self._session.ws_connect(
                self.config.ws_url,
                heartbeat=30,
            )
            self._connected = True
            self._reconnect_attempts = 0
            print("[vessels] AISStream WS connected", flush=True)

            # Subscribe to Philippines EEZ — multiple tight bboxes
            subscription = {
                "APIKey": self.config.api_key,
                "BoundingBoxes": [
                    [[14.0, 120.0], [15.5, 122.0]],   # Manila Bay / Subic / Clark
                    [[10.0, 119.0], [12.5, 123.5]],    # Visayas / Palawan
                    [[6.0, 121.0], [10.0, 127.0]],     # Mindanao Sea / Davao
                ],
            }
            await self._ws.send_json(subscription)
            print(f"[vessels] AISStream subscribed: {len(subscription['BoundingBoxes'])} bboxes", flush=True)

            msg_count = 0
            last_print = time.time()
            while True:
                try:
                    msg = await self._ws.receive()
                except Exception as e:
                    print(f"[vessels] WS receive error: {type(e).__name__}: {e}", flush=True)
                    break
                if msg.type in (aiohttp.WSMsgType.TEXT, aiohttp.WSMsgType.BINARY):
                    try:
                        raw = msg.data
                        if isinstance(raw, bytes):
                            raw = raw.decode("utf-8", errors="replace")
                        data = json.loads(raw)
                        mt = data.get("MessageType", "?")
                        if mt == "PositionReport":
                            self._process_ais_message(data)
                        elif mt == "ShipStaticData":
                            self._process_ship_static(data)
                    except Exception as e:
                        pass
                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    print(f"[vessels] WS closed/error: {msg.type}", flush=True)
                    break

        finally:
            self._connected = False
            if self._session:
                await self._session.close()
                self._session = None

    def _process_ais_message(self, data: dict):
        """Parse an AISStream PositionReport and update vessel state."""
        meta = data.get("MetaData", {})
        pos = data.get("Message", {}).get("PositionReport", {})
        if not meta or not pos:
            return

        mmsi = str(meta.get("MMSI", "")).strip()
        if not mmsi:
            return

        name = (meta.get("ShipName", "") or "").strip()
        ship_type = int(pos.get("ShipType", 0) or pos.get("VesselType", 0) or 0)
        category = classify_vessel(mmsi, name, ship_type)
        flag = mmsi_flag(mmsi)

        # Cross-reference naval database
        naval_entry = lookup_naval(name) if name else None
        description = ""
        specs = []
        naval_db_hit = False
        if naval_entry:
            description = naval_entry.get("description", "")
            specs = naval_entry.get("specs", [])
            naval_db_hit = True
            # Override category if naval DB says it's military
            entry_cat = (naval_entry.get("category") or "").lower()
            if "naval" in entry_cat or "navy" in entry_cat:
                category = VesselCategory.NAVY
            elif "coast guard" in entry_cat:
                category = VesselCategory.COAST_GUARD

        # Vessel type name from code
        type_name = _VESSEL_TYPE_NAMES.get(ship_type, "") if ship_type else ""

        vessel = VesselAIS(
            mmsi=mmsi,
            name=name or f"VESSEL-{mmsi[-4:]}",
            category=category,
            lat=float(pos.get("Latitude", 0) or 0),
            lng=float(pos.get("Longitude", 0) or 0),
            sog=float(pos.get("Sog", 0) or 0),
            cog=float(pos.get("Cog", 0) or 0),
            heading=float(pos.get("Heading", 0) or 0),
            nav_status=int(pos.get("NavigationalStatus", 15) or 15),
            vessel_type_code=ship_type,
            timestamp=time.time(),
            imo=int(meta.get("IMO", 0) or 0),
            call_sign=str(meta.get("CallSign", "") or ""),
            destination=str(pos.get("Destination", "") or ""),
            draught=float(pos.get("Draught", 0) or 0),
            eta=str(pos.get("ETA", "") or ""),
            source="ais",
            flag_country=flag,
            vessel_type_name=type_name,
            description=description,
            specs=specs,
            naval_db_entry=naval_db_hit,
        )

        self._vessels[mmsi] = vessel
        self._messages_received += 1

        # Prune stale vessels (>10 min without update)
        now = time.time()
        stale = [k for k, v in self._vessels.items() if now - v.timestamp > 600]
        for k in stale:
            del self._vessels[k]

    def _process_ship_static(self, data: dict):
        """Parse AISShipStaticData — enriches existing vessel records with name/type/dimensions."""
        meta = data.get("MetaData", {})
        msg = data.get("Message", {}).get("ShipStaticData", {})
        if not meta:
            return
        mmsi = str(meta.get("MMSI", "")).strip()
        if not mmsi:
            return
        self._messages_received += 1
        vessel = self._vessels.get(mmsi)
        if not vessel:
            return
        name = (meta.get("ShipName", "") or "").strip()
        if name and name != f"VESSEL-{mmsi[-4:]}":
            vessel.name = name
        ship_type = int(msg.get("VesselType", 0) or 0)
        if ship_type:
            vessel.vessel_type_code = ship_type
            vessel.vessel_type_name = _VESSEL_TYPE_NAMES.get(ship_type, "")
            vessel.category = classify_vessel(mmsi, vessel.name, ship_type)
        vessel.imo = int(msg.get("IMO", 0) or 0) or vessel.imo
        vessel.call_sign = str(msg.get("CallSign", "") or "") or vessel.call_sign
        vessel.destination = str(msg.get("Destination", "") or "") or vessel.destination
        vessel.draught = float(msg.get("Draught", 0) or 0) or vessel.draught
        vessel.eta = str(msg.get("ETA", "") or "") or vessel.eta
        # Enrich flag from MMSI if not already set
        if not vessel.flag_country:
            vessel.flag_country = mmsi_flag(mmsi)
        # Cross-reference naval DB if not already done
        if not vessel.naval_db_entry and vessel.name:
            naval_entry = lookup_naval(vessel.name)
            if naval_entry:
                vessel.description = naval_entry.get("description", "")
                vessel.specs = naval_entry.get("specs", [])
                vessel.naval_db_entry = True
                entry_cat = (naval_entry.get("category") or "").lower()
                if "naval" in entry_cat or "navy" in entry_cat:
                    vessel.category = VesselCategory.NAVY
                elif "coast guard" in entry_cat:
                    vessel.category = VesselCategory.COAST_GUARD


# ──────────────────────────────────────────────────────────────────────────────
# Singleton (created on import, started by routes_vessels on app startup)
# ──────────────────────────────────────────────────────────────────────────────

vessel_connector = VesselConnector()

# Lazy env reload: in case the env var was set after import (e.g. systemd EnvironmentFile)
def _reload_api_key():
    key = os.environ.get("AISSTREAM_API_KEY", "")
    if key and not vessel_connector.config.api_key:
        vessel_connector.config.api_key = key
        vessel_connector._mode = "real"
        vessel_connector._mock_engine = None
        print(f"[vessels] API key loaded from env (len={len(key)})", flush=True)
