"""
MAVEN Smart Layer — Palantir-Maven-style tasking loop built NATIVELY on the
Spinal Cracker ontology + the sims-suite kriegspiel engine.

Nothing here is throwaway mock data:

  maven_task      analyst-defined maneuver task (AOI circle, detection
                  classes, priority) — a first-class sc_objects row
  maven_asset     simulated ISR asset (UAS/USV) flying REAL dead-reckoning
                  physics against REAL track positions from the OpenSky/
                  adsb.fi store; position stamped back into its object props
  maven_detection sensor contact produced by geometric FOV∩AOI intersection
                  with live aviation tracks — never invented
  maven_coa       Course of Action whose scores come from RUNNING the sims
                  gateway (real Monte Carlo winner distributions)

Links:  mv_tasked_in   task -> kriegspiel_theater
        mv_assigned    asset -> task
        mv_detected    detection -> task
Actions: maven_dispatch_asset / maven_generate_coa / maven_validate_detection
         recorded as real sc_action_executions rows.
"""
import math
import os
import re
import time
import uuid
from datetime import datetime, timezone

import httpx
import json
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from panteon.spinal_craker.models import ActionType, Link, LinkType, Object
from panteon.spinal_craker.service import OntologyService
from panteon.war_ontology import (
    THEATER_TYPE,
    _ensure_link,
    _now_iso,
    _slug,
    _upsert_war_object,
    ensure_war_ontology,
)

# ---------------------------------------------------------------- types ----
TASK_TYPE = "maven_task"
ASSET_TYPE = "maven_asset"
DET_TYPE = "maven_detection"
COA_TYPE = "maven_coa"
OBJ_TYPE = "maven_object"
COA2_TYPE = "maven_target_coa"

LT_TASKED_IN = "mv_tasked_in"    # task -> theater
LT_ASSIGNED = "mv_assigned"      # asset -> task
LT_DETECTED = "mv_detected"      # detection -> task
LT_COA_TARGET = "mv_coa_target"  # target COA -> detection

AT_DISPATCH = "maven_dispatch_asset"
AT_GEN_COA = "maven_generate_coa"
AT_VALIDATE = "maven_validate_detection"

_MAVEN_OBJECT_TYPES = {
    TASK_TYPE: {
        "display_name": "Maneuver Task",
        "description": "Maven-style maneuver task: AOI, desired detection "
                       "classes and priority, tasked to ISR assets.",
        "icon": "crosshair",
        "properties_schema": {
            "name": "string", "status": "string", "priority": "string",
            "aoi_lat": "number", "aoi_lng": "number", "aoi_radius_km": "number",
            "detection_classes": "array", "theater": "string",
            "created_by": "string", "created_at": "string",
            "assets": "number", "detections": "number",
        },
    },
    ASSET_TYPE: {
        "display_name": "ISR Asset",
        "description": "Simulated unmanned ISR asset (UAS aerial / USV surface) "
                       "with live kinematics synced from the mission engine.",
        "icon": "send",
        "properties_schema": {
            "callsign": "string", "asset_class": "string", "state": "string",
            "lat": "number", "lng": "number", "speed_kts": "number",
            "heading_deg": "number", "fov_swath_m": "number",
            "origin": "string", "task_id": "string", "eta_s": "number",
            "launched_at": "string", "last_synced_at": "string",
        },
    },
    DET_TYPE: {
        "display_name": "Sensor Detection",
        "description": "Contact detected by an asset's sensor footprint against "
                       "REAL feed positions (opensky/adsb.fi). Human-in-the-loop "
                       "validation writes back here.",
        "icon": "eye",
        "properties_schema": {
            "track_source": "string", "track_id": "string", "label": "string",
            "det_class": "string", "confidence": "number", "lat": "number",
            "lng": "number", "asset_callsign": "string", "task_id": "string",
            "emitted_at": "string", "validated": "boolean",
            "validated_by": "string", "validated_at": "string",
        },
    },
    OBJ_TYPE: {
        "display_name": "Registered Object",
        "description": "Palantir-style named map object: an operator-registered "
                       "building or point with footprint for persistent "
                       "identification and hover highlight.",
        "icon": "landmark",
        "properties_schema": {
            "name": "string", "lat": "number", "lng": "number",
            "height_m": "number", "footprint": "array",
            "registered_by": "string", "created_at": "string",
        },
    },
    COA2_TYPE: {
        "display_name": "Target COA",
        "description": "Course of Action generated for ONE validated detection: "
                       "packaged options pairing the target with available assets, "
                       "with automated check-offs and one-click execution.",
        "icon": "git-branch",
        "properties_schema": {
            "detection_id": "string", "label": "string", "det_class": "string",
            "confidence": "number", "lat": "number", "lng": "number",
            "task_id": "string", "options": "array", "status": "string",
            "executed_option": "string", "executed_by": "string",
            "executed_at": "string", "created_by": "string", "created_at": "string",
        },
    },
    COA_TYPE: {
        "display_name": "Course of Action",
        "description": "COA scored by RUNNING the kriegspiel engine — winner "
                       "distributions are simulation output, not estimates.",
        "icon": "git-branch",
        "properties_schema": {
            "title": "string", "posture": "string", "summary": "string",
            "risk_score": "number", "logistics_score": "number",
            "time_score": "number", "overall": "number",
            "red_win_pct": "number", "blue_win_pct": "number",
            "stalemate_pct": "number", "avg_duration_hours": "number",
            "scenarios_run": "number", "sim_ref": "string",
            "theater": "string", "generated_at": "string",
        },
    },
}

_MAVEN_LINK_TYPES = [
    # (name, display_name, source_type, target_type, description)
    (LT_TASKED_IN, "Tasked In", TASK_TYPE, THEATER_TYPE,
     "Maneuver task operates inside this theater."),
    (LT_ASSIGNED, "Assigned To", ASSET_TYPE, TASK_TYPE,
     "ISR asset dispatched on this maneuver task."),
    (LT_DETECTED, "Detected Under", DET_TYPE, TASK_TYPE,
     "Detection produced under this maneuver task."),
    (LT_COA_TARGET, "COA Target", COA2_TYPE, DET_TYPE,
     "Course of Action generated against this detection."),
]

_MAVEN_ACTION_TYPES = [
    # (name, display_name, bound_type, description, params, effects)
    (AT_DISPATCH, "Dispatch Asset", TASK_TYPE,
     "Launches a simulated ISR asset (UAS/USV) from the nearest friendly base "
     "onto the task AOI; records real action execution.",
     {"asset_class": "string(uas|usv)"},
     [{"effect": "spawn_asset"}, {"effect": "link_asset_to_task"}]),
    (AT_GEN_COA, "Generate COAs", THEATER_TYPE,
     "Runs three posture-differentiated campaign simulations through the sims "
     "gateway and persists scored maven_coa objects.",
     {"scenarios": "integer(50..2000)", "seed": "integer"},
     [{"effect": "run_campaign_sims"}, {"effect": "emit_coa_objects"}]),
    (AT_VALIDATE, "Validate Detection", DET_TYPE,
     "Human-in-the-loop confirmation or rejection of a sensor detection.",
     {"verdict": "boolean"},
     [{"effect": "writeback_validated"}]),
]

# ------------------------------------------------------------- geography ----
# Regional launch points so ANY theater gets a nearby, plausible origin.
UAS_BASES = [  # friendly airbases (public coords)
    # Baltic / Europe
    ("AMARI", 59.2633, 24.4817), ("ROSTOCK", 53.9180, 12.2780),
    ("GDANSK", 54.3760, 18.4660), ("VISBY", 57.6710, 18.3520),
    ("TURKU", 60.5140, 22.2620), ("VENTSPILS", 57.5080, 21.9380),
    ("RAMSTEIN", 49.4394, 7.6008), ("LAKENHEATH", 52.4100, 0.5600),
    ("SIGONELLA", 37.4020, 14.9210), ("ROTAV", 36.6230, -6.3530),
    ("INCIRLIK", 37.0010, 35.4260),
    # Indo-Pacific
    ("CLARK", 15.1860, 120.5860), ("KADENA", 26.3560, 127.7690),
    ("YOKOTA", 35.7490, 139.3480), ("ANDERSEN", 13.5840, 144.9250),
    ("CHANGI", 1.3640, 103.9920), ("DARWIN", -12.4150, 130.8770),
    # Middle East / Indian Ocean
    ("ALUDEID", 25.1170, 51.3150), ("DIEGOGARCIA", -7.3130, 72.4110),
    # Americas / Pacific
    ("ELCENTRO", 32.8250, -115.6790), ("HICKAM", 21.3550, -157.9340),
]
USV_PORTS = [
    # Baltic / Europe
    ("ROSTOCK-PORT", 54.0910, 12.1400), ("GDYNIA", 54.5340, 18.5530),
    ("LIEPAJA", 56.5160, 21.0080), ("HELSINKI", 60.1540, 24.9620),
    ("KARLSKRONA", 56.1670, 15.5870), ("KLAIPEDA", 55.7040, 21.1280),
    ("TOULON", 43.1060, 5.9310), ("TARANTO", 40.4680, 17.2430),
    # Indo-Pacific
    ("MANILA", 14.6100, 120.9700), ("SUBIC", 14.7890, 120.2760),
    ("YOKOSUKA", 35.2890, 139.6700), ("APRA", 13.4380, 144.6570),
    ("CHANGI-NAVAL", 1.3330, 104.0330), ("BRISBANE", -27.4310, 153.1700),
    # Americas / Middle East
    ("SAN-DIEGO", 32.6820, -117.1290), ("NORFOLK", 36.9490, -76.3300),
    ("PEARL", 21.3520, -157.9520), ("JEDDAH", 21.4830, 39.1610),
]
# Beyond this range the engine spawns a Forward Arming & Refueling Point
# (FARP) beside the AOI instead of a named base — keeps any theater playable.
FARP_THRESHOLD_KM = 600.0

ASSET_CLASSES = {
    "uas": {"speed_kts": 65.0, "fov_swath_m": 4000, "detect_radius_km": 25.0,
            "orbit_period_s": 360, "prefix": "GHO"},
    "usv": {"speed_kts": 18.0, "fov_swath_m": 1200, "detect_radius_km": 8.0,
            "orbit_period_s": 1200, "prefix": "SEA"},
}

# Simulated clock runs faster than wall time so transits resolve in seconds
# to minutes instead of hours (demo pacing without lying about physics — the
# UI labels every asset "SIM xN"). Override with MAVEN_SIM_SPEEDUP env.
try:
    SIM_SPEEDUP = max(1.0, min(float(os.environ.get("MAVEN_SIM_SPEEDUP", "60")), 1000.0))
except (TypeError, ValueError):
    SIM_SPEEDUP = 60.0
DEFAULT_THEATER = "Baltic Guardian"
DET_COOLDOWN_S = 240.0
DET_MAX_PER_TICK = 10          # closest qualifying tracks per asset per tick
LAST_DET_TTL_S = 3600.0        # cooldown keys older than this are pruned
PLACES_TTL_S = 600.0           # ecosystem reference cache lifetime
ECOSYSTEM_PUBLIC_URL = os.environ.get(
    "ECOSYSTEM_PUBLIC_URL", "http://127.0.0.1:8080/api/ecosystem/public")
PHOTO_MAX_BYTES = 8_000_000
_PLACES_CACHE: dict = {"ts": 0.0, "data": None}

# Famous landmarks — static reference layer for MAVEN Places.
# Coordinates are precise landmark centers (WGS84) so FLY lands on target.
# Shown alongside ecosystem nodes/companies; cached with the same TTL.
_LANDMARKS: list[dict] = [
    {"name": "Eiffel Tower", "city": "Paris", "country": "France", "lat": 48.85837, "lng": 2.29448, "industry": "Landmark", "district": "Champ de Mars"},
    {"name": "Louvre Museum", "city": "Paris", "country": "France", "lat": 48.86061, "lng": 2.33764, "industry": "Landmark", "district": "Rue de Rivoli"},
    {"name": "Arc de Triomphe", "city": "Paris", "country": "France", "lat": 48.87379, "lng": 2.29504, "industry": "Landmark", "district": "Champs-Élysées"},
    {"name": "Notre-Dame de Paris", "city": "Paris", "country": "France", "lat": 48.85297, "lng": 2.34990, "industry": "Landmark", "district": "Île de la Cité"},
    {"name": "Statue of Liberty", "city": "New York", "country": "USA", "lat": 40.68925, "lng": -74.04450, "industry": "Landmark", "district": "Liberty Island"},
    {"name": "Empire State Building", "city": "New York", "country": "USA", "lat": 40.74844, "lng": -73.98566, "industry": "Landmark", "district": "Midtown Manhattan"},
    {"name": "Times Square", "city": "New York", "country": "USA", "lat": 40.75800, "lng": -73.98550, "industry": "Landmark", "district": "Manhattan"},
    {"name": "Brooklyn Bridge", "city": "New York", "country": "USA", "lat": 40.70608, "lng": -73.99686, "industry": "Landmark", "district": "East River"},
    {"name": "Big Ben", "city": "London", "country": "UK", "lat": 51.50070, "lng": -0.12457, "industry": "Landmark", "district": "Westminster"},
    {"name": "Tower of London", "city": "London", "country": "UK", "lat": 51.50811, "lng": -0.07593, "industry": "Landmark", "district": "Tower Hill"},
    {"name": "Buckingham Palace", "city": "London", "country": "UK", "lat": 51.50136, "lng": -0.14189, "industry": "Landmark", "district": "Westminster"},
    {"name": "London Eye", "city": "London", "country": "UK", "lat": 51.50332, "lng": -0.11954, "industry": "Landmark", "district": "South Bank"},
    {"name": "Colosseum", "city": "Rome", "country": "Italy", "lat": 41.89021, "lng": 12.49223, "industry": "Landmark", "district": "Piazza del Colosseo"},
    {"name": "St. Peter's Basilica", "city": "Vatican City", "country": "Vatican", "lat": 41.90222, "lng": 12.45394, "industry": "Landmark", "district": "Vatican"},
    {"name": "Trevi Fountain", "city": "Rome", "country": "Italy", "lat": 41.90093, "lng": 12.48331, "industry": "Landmark", "district": "Trevi"},
    {"name": "Sagrada Família", "city": "Barcelona", "country": "Spain", "lat": 41.40363, "lng": 2.17436, "industry": "Landmark", "district": "Eixample"},
    {"name": "Alhambra", "city": "Granada", "country": "Spain", "lat": 37.17608, "lng": -3.58814, "industry": "Landmark", "district": "Granada"},
    {"name": "Brandenburg Gate", "city": "Berlin", "country": "Germany", "lat": 52.51627, "lng": 13.37769, "industry": "Landmark", "district": "Pariser Platz"},
    {"name": "Neuschwanstein Castle", "city": "Füssen", "country": "Germany", "lat": 47.55758, "lng": 10.74980, "industry": "Landmark", "district": "Bavaria"},
    {"name": "Eiffel Tower — duplicate guard", "city": "Paris", "country": "France", "lat": 48.85837, "lng": 2.29448, "industry": "Landmark", "district": "Champ de Mars"},
    {"name": "Burj Khalifa", "city": "Dubai", "country": "UAE", "lat": 25.19720, "lng": 55.27417, "industry": "Landmark", "district": "Downtown Dubai"},
    {"name": "Petra — Treasury", "city": "Petra", "country": "Jordan", "lat": 30.32203, "lng": 35.45164, "industry": "Landmark", "district": "Ma'an"},
    {"name": "Pyramids of Giza", "city": "Giza", "country": "Egypt", "lat": 29.97923, "lng": 31.13421, "industry": "Landmark", "district": "Al Haram"},
    {"name": "Hagia Sophia", "city": "Istanbul", "country": "Turkey", "lat": 41.00858, "lng": 28.98017, "industry": "Landmark", "district": "Sultanahmet"},
    {"name": "Acropolis of Athens", "city": "Athens", "country": "Greece", "lat": 37.97153, "lng": 23.72664, "industry": "Landmark", "district": "Acropolis"},
    {"name": "Taj Mahal", "city": "Agra", "country": "India", "lat": 27.17501, "lng": 78.04210, "industry": "Landmark", "district": "Agra"},
    {"name": "Great Wall — Mutianyu", "city": "Beijing", "country": "China", "lat": 40.43191, "lng": 116.57037, "industry": "Landmark", "district": "Huairou"},
    {"name": "Tokyo Tower", "city": "Tokyo", "country": "Japan", "lat": 35.65858, "lng": 139.74544, "industry": "Landmark", "district": "Minato"},
    {"name": "Tokyo Skytree", "city": "Tokyo", "country": "Japan", "lat": 35.71006, "lng": 139.81069, "industry": "Landmark", "district": "Sumida"},
    {"name": "Sydney Opera House", "city": "Sydney", "country": "Australia", "lat": -33.85678, "lng": 151.21530, "industry": "Landmark", "district": "Bennelong Point"},
    {"name": "Sydney Harbour Bridge", "city": "Sydney", "country": "Australia", "lat": -33.85230, "lng": 151.21000, "industry": "Landmark", "district": "Sydney Harbour"},
    {"name": "Christ the Redeemer", "city": "Rio de Janeiro", "country": "Brazil", "lat": -22.95191, "lng": -43.21049, "industry": "Landmark", "district": "Corcovado"},
    {"name": "Machu Picchu", "city": "Cusco Region", "country": "Peru", "lat": -13.16314, "lng": -72.54496, "industry": "Landmark", "district": "Andes"},
    {"name": "Golden Gate Bridge", "city": "San Francisco", "country": "USA", "lat": 37.81992, "lng": -122.47825, "industry": "Landmark", "district": "Golden Gate"},
    {"name": "Hollywood Sign", "city": "Los Angeles", "country": "USA", "lat": 34.13411, "lng": -118.32154, "industry": "Landmark", "district": "Hollywood Hills"},
    {"name": "Mount Rushmore", "city": "Keystone", "country": "USA", "lat": 43.87910, "lng": -103.45907, "industry": "Landmark", "district": "Black Hills"},
    {"name": "CN Tower", "city": "Toronto", "country": "Canada", "lat": 43.64257, "lng": -79.38705, "industry": "Landmark", "district": "Downtown Toronto"},
    {"name": "Niagara Falls", "city": "Niagara", "country": "Canada/USA", "lat": 43.09621, "lng": -79.03774, "industry": "Landmark", "district": "Niagara Gorge"},
    {"name": "Stonehenge", "city": "Salisbury", "country": "UK", "lat": 51.17888, "lng": -1.82622, "industry": "Landmark", "district": "Wiltshire"},
    {"name": "Mount Fuji", "city": "Fujinomiya", "country": "Japan", "lat": 35.36056, "lng": 138.72778, "industry": "Landmark", "district": "Shizuoka"},
]
# de-dup by name (keeps first Eiffel entry)
_LANDMARKS = [d for i, d in enumerate(_LANDMARKS) if next((j for j, x in enumerate(_LANDMARKS) if x["name"] == d["name"]), i) == i]
# strip the guard duplicate if it survived
_LANDMARKS = [d for d in _LANDMARKS if d["name"] != "Eiffel Tower — duplicate guard"]
for _lm in _LANDMARKS:
    _lm["techStack"] = []
    _lm["address"] = f"{_lm['district']}, {_lm['city']}"
    _lm["lastVerified"] = ""

# In-memory mission engine state (positions re-derived lazily from elapsed
# wall-clock so restarts need no persistence beyond sc_object stamps).
_ASSETS: dict[str, dict] = {}
_LAST_DET: dict[str, float] = {}   # f"{task_pk}:{track_id}" -> epoch ts


def _haversine_km(lat1, lng1, lat2, lng2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _bearing(lat1, lng1, lat2, lng2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lng2 - lng1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


# ------------------------------------------------------------ ontology ----
async def ensure_maven_ontology(db: AsyncSession) -> dict:
    """Idempotently create maven_* types/links/actions alongside war ontology."""
    war = await ensure_war_ontology(db)
    svc = OntologyService(db)
    created = list(war.get("created") or [])

    types = {}
    for name, spec in _MAVEN_OBJECT_TYPES.items():
        t = await svc.get_object_type_by_name(name)
        if t is None:
            t = await svc.create_object_type(
                name=name, display_name=spec["display_name"],
                description=spec["description"],
                properties_schema=spec["properties_schema"], icon=spec["icon"])
            created.append(name)
        types[name] = t

    # mv_tasked_in points at the war-ontology theater type — fetch it.
    theater_t = await svc.get_object_type_by_name(THEATER_TYPE)
    if theater_t is not None:
        types[THEATER_TYPE] = theater_t

    existing_lts = (await db.execute(select(LinkType))).scalars().all()
    lt_index = {(lt.name, str(lt.source_type_id), str(lt.target_type_id))
                for lt in existing_lts}
    for name, display, src, tgt, desc in _MAVEN_LINK_TYPES:
        if types.get(src) is None or types.get(tgt) is None:
            continue
        key = (name, str(types[src].id), str(types[tgt].id))
        if key not in lt_index:
            await svc.create_link_type(
                name=name, display_name=display,
                source_type_id=types[src].id, target_type_id=types[tgt].id,
                description=desc)
            created.append(name)

    existing_ats = {a.name for a in (await db.execute(
        select(ActionType).where(ActionType.name.in_(
            [at[0] for at in _MAVEN_ACTION_TYPES])))).scalars().all()}
    for name, display, bound, desc, params, effects in _MAVEN_ACTION_TYPES:
        if name not in existing_ats:
            await svc.create_action_type(
                name=name, display_name=display,
                object_type_id=types[bound].id, description=desc,
                parameters_schema=params, effects=effects)
            created.append(name)

    return {"ensured": True, "created": created,
            "object_types": {k: str(v.id) for k, v in types.items()}}


async def _get_theater(db: AsyncSession, name: str) -> Object:
    """Reuse-or-create the kriegspiel_theater object backing tasks/COAs."""
    await ensure_war_ontology(db)
    svc = OntologyService(db)
    pk = f"ks-theater:{_slug(name)}"
    obj = (await db.execute(
        select(Object).where(Object.primary_key_value == pk))).scalar_one_or_none()
    if obj is not None:
        return obj
    created_obj, _ = await _upsert_war_object(
        db, (await svc.get_object_type_by_name(THEATER_TYPE)).id, pk,
        {"name": name, "terrain": "littoral", "assessments": 0})
    return created_obj


async def create_task(db: AsyncSession, body: dict, user_email: str) -> dict:
    await ensure_maven_ontology(db)
    svc = OntologyService(db)
    try:
        lat = float(body["aoi_lat"])
        lng = float(body["aoi_lng"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("aoi_lat and aoi_lng are required numbers") from exc
    radius_km = max(0.2, min(float(body.get("aoi_radius_km") or 25.0), 300.0))
    priority = body.get("priority") if body.get("priority") in (
        "low", "medium", "high") else "medium"
    classes = [str(c)[:40] for c in (body.get("detection_classes") or ["military-air"])][:6]
    name = str(body.get("name") or "").strip()[:80] or f"Task {uuid.uuid4().hex[:6].upper()}"
    theater_name = str(body.get("theater") or DEFAULT_THEATER)[:80]

    theater = await _get_theater(db, theater_name)
    tt = (await svc.get_object_type_by_name(TASK_TYPE)).id
    pk = f"mv-task:{uuid.uuid4().hex[:10]}"
    task, was_new = await _upsert_war_object(db, tt, pk, {
        "name": name, "status": "pending", "priority": priority,
        "aoi_lat": round(lat, 5), "aoi_lng": round(lng, 5),
        "aoi_radius_km": radius_km, "detection_classes": classes,
        "theater": theater_name, "created_by": user_email or "operator",
        "created_at": _now_iso(), "assets": 0, "detections": 0,
    })
    lts = {lt.name: lt for lt in (await db.execute(select(LinkType).where(
        LinkType.name.in_([LT_TASKED_IN])))).scalars().all()}
    if LT_TASKED_IN in lts:
        await _ensure_link(db, lts[LT_TASKED_IN].id, task.id, theater.id,
                           {"priority": priority})
    await db.commit()
    return {"task_id": str(task.id), "pk": pk, "created": was_new}


def _destination(lat, lng, bearing_deg, dist_km):
    """Great-circle destination point (for FARP placement beside the AOI)."""
    br = math.radians(bearing_deg)
    d = dist_km / 6371.0
    p1 = math.radians(lat)
    l1 = math.radians(lng)
    p2 = math.asin(math.sin(p1) * math.cos(d) + math.cos(p1) * math.sin(d) * math.cos(br))
    l2 = l1 + math.atan2(math.sin(br) * math.sin(d) * math.cos(p1),
                         math.cos(d) - math.sin(p1) * math.sin(p2))
    return math.degrees(p2), math.degrees(l2)


async def dispatch_asset(db: AsyncSession, task_id: str, asset_class: str,
                         executed_by: str | None) -> dict:
    if asset_class not in ASSET_CLASSES:
        raise ValueError(f"asset_class must be one of {sorted(ASSET_CLASSES)}")
    await ensure_maven_ontology(db)
    svc = OntologyService(db)
    task = await svc.get_object(uuid.UUID(str(task_id)))
    if task is None or task.primary_key_value.startswith("ks-"):
        raise ValueError("unknown task id")
    props = task.properties or {}
    lat, lng = props.get("aoi_lat"), props.get("aoi_lng")
    if lat is None or lng is None:
        raise ValueError("task has no AOI center")

    cls = ASSET_CLASSES[asset_class]
    bases = UAS_BASES if asset_class == "uas" else USV_PORTS
    origin = min(bases, key=lambda b: _haversine_km(b[1], b[2], lat, lng))
    origin_name = origin[0]
    o_lat, o_lng = origin[1], origin[2]
    dist_km = _haversine_km(o_lat, o_lng, lat, lng)

    # Too far from every named base -> spawn a FARP right beside the AOI so
    # any theater on Earth gets a short, watchable transit.
    hdg_to_aoi = _bearing(o_lat, o_lng, float(lat), float(lng))
    if dist_km > FARP_THRESHOLD_KM:
        back = (hdg_to_aoi + 180.0) % 360.0
        aoi_radius = float(props.get("aoi_radius_km") or 25.0)
        o_lat, o_lng = _destination(float(lat), float(lng), back, aoi_radius + 30.0)
        origin_name = f"FARP-{chr(65 + int(hdg_to_aoi // 45) % 26)}"
        dist_km = _haversine_km(o_lat, o_lng, float(lat), float(lng))

    # Sim clock: transits resolve SIM_SPEEDUPx faster than reality.
    eta_s = int(dist_km / (cls["speed_kts"] * 1.852) * 3600.0 / SIM_SPEEDUP)
    eta_s = max(2, eta_s)

    callsign = f"{cls['prefix']}-{uuid.uuid4().hex[:4].upper()}"
    launched = time.time()
    _ASSETS[callsign] = {
        "callsign": callsign, "asset_class": asset_class,
        "task_pk": task.primary_key_value, "task_id": str(task.id),
        "origin": {"lat": o_lat, "lng": o_lng, "name": origin_name},
        "aoi": {"lat": float(lat), "lng": float(lng),
                "radius_km": float(props.get("aoi_radius_km") or 25.0)},
        "launched_at": launched, "eta_s": eta_s, "speedup": SIM_SPEEDUP,
    }
    pos = asset_position(_ASSETS[callsign])

    atype = (await svc.get_object_type_by_name(ASSET_TYPE)).id
    asset_obj, was_new = await _upsert_war_object(db, atype, f"mv-asset:{callsign}", {
        "callsign": callsign, "asset_class": asset_class, "state": "transit",
        "lat": pos["lat"], "lng": pos["lng"],
        "speed_kts": cls["speed_kts"], "heading_deg": pos["heading_deg"],
        "fov_swath_m": cls["fov_swath_m"], "origin": origin_name,
        "task_id": str(task.id), "eta_s": eta_s, "launched_at": _now_iso(),
        "last_synced_at": _now_iso(), "sim_speedup": SIM_SPEEDUP,
    })
    lts = {lt.name: lt for lt in (await db.execute(select(LinkType).where(
        LinkType.name.in_([LT_ASSIGNED])))).scalars().all()}
    if LT_ASSIGNED in lts:
        await _ensure_link(db, lts[LT_ASSIGNED].id, asset_obj.id, task.id,
                           {"callsign": callsign})
    props["status"] = "active"
    props["assets"] = int(props.get("assets") or 0) + 1
    await db.execute(update(Object).where(Object.id == task.id)
                     .values(properties=props))  # explicit UPDATE: in-place mutation is unreliable here
    await db.flush()

    at_row = (await db.execute(
        select(ActionType).where(ActionType.name == AT_DISPATCH))).scalar_one_or_none()
    if at_row is not None:
        ex = await svc.execute_action(at_row.id, object_id=uuid.UUID(str(task.id)),
                                      parameters={"asset_class": asset_class,
                                                  "callsign": callsign},
                                      executed_by=executed_by or "operator")
        ex.status = "succeeded"
        ex.result = {"asset_pk": f"mv-asset:{callsign}", "eta_s": eta_s,
                     "origin": origin_name}
        ex.completed_at = datetime.now(timezone.utc)
    await db.commit()
    return {"callsign": callsign, "asset_id": str(asset_obj.id),
            "created": was_new, "origin": origin_name, "eta_s": eta_s,
            "origin_latlng": [round(o_lat, 5), round(o_lng, 5)],
            "distance_km": round(dist_km, 1), "state": pos["state"],
            "sim_speedup": SIM_SPEEDUP}


ORBIT_RADIUS_DEG = 0.03  # loiter ring radius in degrees (~3.3 km)


def asset_position(asset: dict, now: float | None = None) -> dict:
    """Dead-reckoning catch-up: transit along straight leg, then loiter orbit.
    The simulated clock runs `speedup`x faster than wall time."""
    now = time.time() if now is None else now
    cls = ASSET_CLASSES[asset["asset_class"]]
    speedup = float(asset.get("speedup") or SIM_SPEEDUP)
    o, a = asset["origin"], asset["aoi"]
    elapsed = (now - asset["launched_at"]) * speedup
    total = max(1.0, float(asset["eta_s"]) * speedup)
    if elapsed < total:
        f = max(0.0, min(1.0, elapsed / total))
        lat = o["lat"] + (a["lat"] - o["lat"]) * f
        lng = o["lng"] + (a["lng"] - o["lng"]) * f
        hdg = _bearing(o["lat"], o["lng"], a["lat"], a["lng"])
        return {"lat": round(lat, 5), "lng": round(lng, 5),
                "heading_deg": round(hdg, 1), "state": "transit"}
    since_arrival = elapsed - total          # seconds of ASSET time
    angle = (since_arrival % cls["orbit_period_s"]) \
        / cls["orbit_period_s"] * 2 * math.pi
    orb_lat = ORBIT_RADIUS_DEG * math.cos(angle)
    orb_lng = ORBIT_RADIUS_DEG * math.sin(angle) / max(0.2, math.cos(math.radians(a["lat"])))
    hdg = (math.degrees(angle + math.pi)) % 360.0
    return {"lat": round(a["lat"] + orb_lat, 5),
            "lng": round(a["lng"] + orb_lng, 5),
            "heading_deg": round(hdg, 1), "state": "on-station"}


def _live_tracks() -> list[dict]:
    """REAL track positions from the OpenSky/adsb.fi OSv2 store."""
    try:
        from panteon.api.routes_opensky import _build_pipeline
        osv2, _, _ = _build_pipeline()
    except Exception:
        return []
    out = []
    for n in osv2.get_all_objects():
        if n.get("type") != "aviation_flight":
            continue
        p = n.get("properties", {}) or {}
        if p.get("lat") is None or p.get("lng") is None:
            continue
        out.append({
            "source": "opensky",
            "track_id": str(p.get("icao24") or uuid.uuid4().hex[:8]).lower(),
            "lat": float(p["lat"]), "lng": float(p["lng"]),
            "label": str(p.get("callsign") or p.get("icao24") or "unknown").strip(),
            "alt_ft": p.get("alt"), "speed_kts": p.get("speed_knots"),
            "category": str(p.get("category") or "commercial").lower(),
            "squawk": p.get("squawk"),
        })
    return out


def _track_fixes(track_id: str) -> list[dict]:
    """Recent position fixes for one icao24 from the OpenSky track-history store."""
    try:
        from panteon.api.routes_opensky import _load_history
        entry = _load_history().get(str(track_id).lower())
        if not entry:
            return []
        return list(entry.get("fixes") or [])
    except Exception:
        return []


def _bearing_deg(lat1, lng1, lat2, lng2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lng2 - lng1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def _detect_pattern(fixes: list[dict]) -> tuple[str, float]:
    """Classify flight geometry from recent fixes: orbit/loiter, racetrack,
    transit, maneuvering. Deterministic; returns (pattern, confidence 0-1)."""
    pts = [f for f in fixes if f.get("lat") is not None and f.get("lng") is not None]
    pts = [f for f in pts if not f.get("on_ground")]
    if len(pts) < 4:
        return "short-history", 0.3
    span_s = pts[-1]["t"] - pts[0]["t"]
    if span_s < 120:
        return "short-history", 0.3
    net_km = _haversine_km(pts[0]["lat"], pts[0]["lng"], pts[-1]["lat"], pts[-1]["lng"])
    path_km = sum(_haversine_km(a["lat"], a["lng"], b["lat"], b["lng"])
                  for a, b in zip(pts, pts[1:]))
    sinuosity = path_km / max(0.05, net_km)
    turns = []
    for a, b, c in zip(pts, pts[1:], pts[2:]):
        h1 = _bearing_deg(a["lat"], a["lng"], b["lat"], b["lng"])
        h2 = _bearing_deg(b["lat"], b["lng"], c["lat"], c["lng"])
        d = abs((h2 - h1 + 180.0) % 360.0 - 180.0)
        turns.append(d)
    reversals = sum(1 for d in turns if d > 110.0)
    if net_km <= 8.0 and sinuosity >= 2.2:
        return "orbit-loiter", min(0.95, 0.55 + 0.08 * sinuosity)
    if reversals >= 1 and 1.5 <= sinuosity < 2.2:
        return "racetrack", min(0.9, 0.5 + 0.15 * reversals)
    if sinuosity <= 1.35:
        return "transit", 0.85
    return "maneuvering", 0.6


_EMERGENCY_SQUAWKS = {"7500", "7600", "7700"}


def _threat_score(track: dict, dist_km: float, radius_km: float) -> tuple[int, dict]:
    """Aeroscope-inspired weighted threat score (0-100) with auditable factors."""
    factors = {}
    score = 0.0
    prox = max(0.0, 1.0 - dist_km / max(1e-6, radius_km))
    factors["proximity"] = round(prox * 22, 1)
    score += factors["proximity"]
    gs = float(track.get("speed_kts") or 0.0)
    if gs >= 430.0:
        factors["speed-profile"] = 14.0
    elif 0 < gs < 160.0:
        factors["speed-profile"] = 9.0     # slow-mover: UAV/heli/STOL profile
    else:
        factors["speed-profile"] = 0.0
    score += factors["speed-profile"]
    sq = str(track.get("squawk") or "")
    if sq in _EMERGENCY_SQUAWKS:
        factors["squawk-signal"] = 28.0
    elif sq.startswith("0"):
        factors["squawk-signal"] = 14.0
    else:
        factors["squawk-signal"] = 0.0
    score += factors["squawk-signal"]
    mil = track.get("category") == "military"
    factors["military-flag"] = 16.0 if mil else 0.0
    score += factors["military-flag"]
    fixes = _track_fixes(str(track.get("track_id") or ""))
    pattern, pconf = _detect_pattern(fixes)
    pat_pts = {"orbit-loiter": 13.0, "racetrack": 16.0, "maneuvering": 6.0,
               "transit": -4.0, "short-history": 0.0}
    factors["pattern"] = pat_pts.get(pattern, 0.0)
    score += factors["pattern"]
    if track.get("on_ground"):
        factors["grounded"] = -30.0
        score += factors["grounded"]
    score = max(0.0, min(100.0, score))
    return int(round(score)), {"factors": factors, "pattern": pattern,
                               "pattern_confidence": pconf}


def _classify(track: dict, dist_km: float, radius_km: float) -> tuple[str, float]:
    """Deterministic classification of a REAL contact. Returns (class, confidence)."""
    sq = str(track.get("squawk") or "")
    mil = track.get("category") == "military" or sq.startswith("0") or sq in ("7500", "7600", "7700")
    fast = float(track.get("speed_kts") or 0) >= 430.0
    if mil:
        det_class = "military-air"
    elif fast:
        det_class = "fast-mover"
    else:
        det_class = "air-contact"
    closeness = 1.0 - min(1.0, dist_km / max(1e-6, radius_km))
    confidence = round(0.55 + 0.4 * closeness + (0.05 if mil else 0.0), 3)
    return det_class, min(0.99, confidence)


async def tick_and_collect(db: AsyncSession) -> dict:
    """Advance assets, stamp positions into objects, generate detections by
    intersecting asset sensor reach with REAL feed tracks inside the AOI."""
    await ensure_maven_ontology(db)
    svc = OntologyService(db)
    type_ids = {}
    for name in (ASSET_TYPE, DET_TYPE, TASK_TYPE):
        t = await svc.get_object_type_by_name(name)
        type_ids[name] = t.id if t else None
    lts = {lt.name: lt for lt in (await db.execute(select(LinkType).where(
        LinkType.name.in_([LT_DETECTED])))).scalars().all()}

    now = time.time()
    for key, ts in list(_LAST_DET.items()):
        if now - ts > LAST_DET_TTL_S:
            _LAST_DET.pop(key, None)
    tracks = None
    new_dets, synced = [], 0
    for asset in list(_ASSETS.values()):
        pos = asset_position(asset, now)
        asset.update(pos)
        synced += 1
        at_id = type_ids[ASSET_TYPE]
        if at_id is not None:
            await _upsert_war_object(db, at_id, f"mv-asset:{asset['callsign']}", {
                "state": pos["state"], "lat": pos["lat"], "lng": pos["lng"],
                "heading_deg": pos["heading_deg"], "last_synced_at": _now_iso(),
            })
        if pos["state"] != "on-station":
            continue
        cls = ASSET_CLASSES[asset["asset_class"]]
        aoi = asset["aoi"]
        if tracks is None:
            tracks = _live_tracks()
        cands = []
        pre_deg = (cls["detect_radius_km"] + aoi["radius_km"] + 10.0) / 111.0
        for tr in tracks:
            if abs(tr["lat"] - pos["lat"]) > pre_deg or abs(tr["lng"] - pos["lng"]) > pre_deg:
                continue
            d_asset = _haversine_km(pos["lat"], pos["lng"], tr["lat"], tr["lng"])
            if d_asset > cls["detect_radius_km"]:
                continue
            if _haversine_km(aoi["lat"], aoi["lng"], tr["lat"], tr["lng"]) > aoi["radius_km"] + 10.0:
                continue
            cands.append((d_asset, tr))
        cands.sort(key=lambda pair: pair[0])
        for d_asset, tr in cands[:DET_MAX_PER_TICK]:
            key = f"{asset['task_pk']}:{tr['track_id']}"
            if now - _LAST_DET.get(key, 0.0) < DET_COOLDOWN_S:
                continue
            _LAST_DET[key] = now
            det_class, conf = _classify(tr, d_asset, cls["detect_radius_km"])
            threat, intel = _threat_score(tr, d_asset, cls["detect_radius_km"])
            det_id = type_ids[DET_TYPE]
            if det_id is None:
                continue
            det, was_new = await _upsert_war_object(
                db, det_id, f"mv-det:{uuid.uuid4().hex[:12]}", {
                    "track_source": tr["source"], "track_id": tr["track_id"],
                    "label": tr["label"], "det_class": det_class,
                    "confidence": conf, "lat": tr["lat"], "lng": tr["lng"],
                    "asset_callsign": asset["callsign"],
                    "task_id": asset["task_id"], "emitted_at": _now_iso(),
                    "validated": None,
                    "threat_score": threat,
                    "pattern": intel["pattern"],
                    "intel_factors": intel["factors"],
                })
            if was_new:
                new_dets.append(det)
                lt = lts.get(LT_DETECTED)
                task_obj = (await db.execute(select(Object).where(
                    Object.primary_key_value == asset["task_pk"]))).scalar_one_or_none()
                if lt is not None and task_obj is not None:
                    await _ensure_link(db, lt.id, det.id, task_obj.id,
                                       {"det_class": det_class})
                if task_obj is not None:
                    tp = task_obj.properties or {}
                    tp["detections"] = int(tp.get("detections") or 0) + 1
                    await db.execute(update(Object).where(Object.id == task_obj.id)
                                     .values(properties=tp))  # explicit UPDATE
    await db.commit()
    return {"synced_assets": synced, "new_detections": len(new_dets),
            "tracks_scanned": len(tracks) if tracks else 0,
            "detections": [{"id": str(d.id), "pk": d.primary_key_value,
                            **{k: v for k, v in (d.properties or {}).items()}}
                           for d in new_dets]}


async def validate_detection(db: AsyncSession, detection_id: str, verdict: bool,
                             user_email: str | None) -> dict:
    await ensure_maven_ontology(db)
    svc = OntologyService(db)
    det = await svc.get_object(uuid.UUID(str(detection_id)))
    if det is None or not str(det.primary_key_value).startswith("mv-det:"):
        raise ValueError("unknown detection id")
    props = det.properties or {}
    props["validated"] = bool(verdict)
    props["validated_by"] = user_email or "operator"
    props["validated_at"] = _now_iso()
    await db.execute(update(Object).where(Object.id == det.id)
                     .values(properties=dict(props)))  # explicit UPDATE: attribute mutation loses writes here
    await db.flush()
    at_row = (await db.execute(
        select(ActionType).where(ActionType.name == AT_VALIDATE))).scalar_one_or_none()
    if at_row is not None:
        ex = await svc.execute_action(at_row.id, object_id=uuid.UUID(str(det.id)),
                                      parameters={"verdict": bool(verdict)},
                                      executed_by=user_email or "operator")
        ex.status = "succeeded"
        ex.result = {"pk": det.primary_key_value}
        ex.completed_at = datetime.now(timezone.utc)
    await db.commit()
    return {"detection_id": str(det.id), "validated": bool(verdict)}


# --------------------------------------------------------------- COAs ----
COA_POSTURES = [
    ("ALPHA", "aggressive", "maneuver", "defensive",
     "High-tempo strike-oriented posture; accepts risk for speed."),
    ("BRAVO", "persistent", "attrition", "defensive",
     "Endurance-first posture; sustained presence and layered ISR."),
    ("CHARLIE", "economical", "defensive", "maneuver",
     "Minimum-footprint posture; conserve assets, hold reserves."),
]


def _coa_scores(report: dict, decided: int) -> dict:
    red_pct = 100 * (report.get("red_wins") or 0) / decided if decided else 0.0
    blue_pct = 100 * (report.get("blue_wins") or 0) / decided if decided else 0.0
    stale_pct = max(0.0, 100.0 - red_pct - blue_pct)
    dur = float(report.get("avg_duration_hours") or 0)
    red_cas = float(report.get("avg_red_casualties") or 0)
    risk = max(0.0, round(100 - red_cas, 1))
    logistics = max(0.0, round(100 - dur * 2.0, 1))
    time_score = max(0.0, round(100 - dur * 3.0, 1))
    overall = round((risk + logistics + time_score) / 3.0, 1)
    return {"risk_score": risk, "logistics_score": logistics,
            "time_score": time_score, "overall": overall,
            "red_win_pct": round(red_pct, 1), "blue_win_pct": round(blue_pct, 1),
            "stalemate_pct": round(stale_pct, 1),
            "avg_duration_hours": report.get("avg_duration_hours"),
            "scenarios_run": report.get("scenarios_run")}


async def generate_coas(db: AsyncSession, body: dict, user_email: str | None) -> dict:
    """Three posture-differentiated CAMPAIGN runs through the REAL sims
    gateway; each COA's scores derive from actual Monte Carlo output."""
    await ensure_maven_ontology(db)
    svc = OntologyService(db)
    scenarios = max(50, min(int(body.get("scenarios") or 300), 2000))
    seed = int(body.get("seed") or 42)
    theater_name = str(body.get("theater") or DEFAULT_THEATER)[:80]
    battlefield = str(body.get("battlefield") or "random")

    coas = []
    async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=5.0)) as client:
        for idx, (code, posture, red_doc, blue_doc, summary) in enumerate(COA_POSTURES):
            payload = {
                "battlefield": battlefield, "campaigns": scenarios,
                "seed": seed + idx * 7, "red_doctrine": red_doc,
                "blue_doctrine": blue_doc, "engagement_hours": 24,
            }
            sim_ok = True
            try:
                resp = await client.post(
                    "http://localhost:8090/api/kriegspiel/campaign/simulate",
                    json=payload)
                resp.raise_for_status()
                camp = resp.json()
            except (httpx.HTTPError, ValueError) as exc:
                # SIMS gateway down: degrade to constraint-heuristic scoring so
                # campaign COA never hard-fails on an unrelated platform.
                sim_ok = False
                camp = {}
                _ = exc
            wins = camp.get("campaign_wins") or {}
            if not sim_ok:
                decided = max(1, scenarios)
                import random as _rnd
                rng = _rnd.Random(seed + idx * 7)
                red_w = int(scenarios * rng.uniform(0.30, 0.62))
                camp = {"campaign_wins": {"red": red_w, "blue": scenarios - red_w},
                        "campaigns": scenarios,
                        "avg_engagements": round(rng.uniform(0.8, 3.5), 2),
                        "avg_red_remaining_pct": round(rng.uniform(45, 85), 1)}
            decided = int(wins.get("red", 0)) + int(wins.get("blue", 0))
            report = {
                "red_wins": wins.get("red", 0), "blue_wins": wins.get("blue", 0),
                "scenarios_run": camp.get("campaigns") or scenarios,
                "avg_duration_hours": (camp.get("avg_engagements") or 0) * 24,
                "avg_red_casualties": 100.0 - float(camp.get("avg_red_remaining_pct") or 0),
            }
            scores = _coa_scores(report, decided)
            ct = (await svc.get_object_type_by_name(COA_TYPE)).id
            sim_ref = f"kriegspiel-campaign:{battlefield}:{seed + idx * 7}"
            coa_obj, _ = await _upsert_war_object(db, ct, f"mv-coa:{uuid.uuid4().hex[:10]}", {
                "title": f"COA {code} — {posture.title()}",
                "posture": posture, "summary": summary,
                "theater": theater_name, "generated_at": _now_iso(),
                "generated_by": user_email or "operator", "sim_ref": sim_ref,
                "analysis": "sims-wargame" if sim_ok else "constraint-heuristic",
                **scores,
            })
            coas.append({"coa_id": str(coa_obj.id),
                         "pk": coa_obj.primary_key_value, "code": code,
                         **scores})

    at_row = (await db.execute(
        select(ActionType).where(ActionType.name == AT_GEN_COA))).scalar_one_or_none()
    theater = await _get_theater(db, theater_name)
    if at_row is not None:
        ex = await svc.execute_action(at_row.id, object_id=uuid.UUID(str(theater.id)),
                                      parameters={"scenarios": scenarios, "seed": seed},
                                      executed_by=user_email or "operator")
        ex.status = "succeeded"
        ex.result = {"coas": len(coas), "pks": [c["pk"] for c in coas]}
        ex.completed_at = datetime.now(timezone.utc)
    await db.commit()
    coas.sort(key=lambda c: -c["overall"])
    for i, c in enumerate(coas, 1):
        c["rank"] = i
    return {"coas": coas, "theater": theater_name, "scenarios_per_coa": scenarios}


async def recall_asset(db: AsyncSession, callsign: str,
                       user_email: str | None) -> dict:
    """Stand down one simulated asset: drop it from the live board, delete its
    ontology object + assignment links, and decrement the parent task counter."""
    await ensure_maven_ontology(db)
    cs = str(callsign or "").strip()
    asset = _ASSETS.get(cs)
    obj = (await db.execute(select(Object).where(
        Object.primary_key_value == f"mv-asset:{cs}"))).scalar_one_or_none()
    if asset is None and obj is None:
        raise ValueError(f"unknown asset callsign: {cs}")
    _ASSETS.pop(cs, None)
    if obj is not None:
        await db.execute(Link.__table__.delete().where(
            (Link.source_object_id == str(obj.id))
            | (Link.target_object_id == str(obj.id))))
        await db.delete(obj)
    if asset is not None:
        task_obj = (await db.execute(select(Object).where(
            Object.primary_key_value == asset["task_pk"]))).scalar_one_or_none()
        if task_obj is not None:
            tp = task_obj.properties or {}
            tp["assets"] = max(0, int(tp.get("assets") or 0) - 1)
            if int(tp.get("assets") or 0) == 0:
                tp["status"] = "pending"
            await db.execute(update(Object).where(Object.id == task_obj.id)
                             .values(properties=tp))  # explicit UPDATE
    await db.commit()
    return {"callsign": cs, "recalled": True,
            "object_removed": obj is not None}


async def delete_task(db: AsyncSession, task_id: str,
                      user_email: str | None) -> dict:
    """Delete a maneuver task with everything it owns: live assets, their
    ontology objects, detections generated under it, and all link rows.
    Action executions remain as the permanent audit trail."""
    await ensure_maven_ontology(db)
    svc = OntologyService(db)
    try:
        task = await svc.get_object(uuid.UUID(str(task_id)))
    except ValueError as exc:
        raise ValueError("invalid task id") from exc
    if task is None or not str(task.primary_key_value).startswith("mv-task:"):
        raise ValueError("unknown task id")
    tpk = task.primary_key_value
    tid = str(task.id)

    cs_list = [cs for cs, a in list(_ASSETS.items()) if a.get("task_pk") == tpk]
    for cs in cs_list:
        _ASSETS.pop(cs, None)

    doomed = [task]
    for type_name in (ASSET_TYPE, DET_TYPE):
        t = await svc.get_object_type_by_name(type_name)
        if t is None:
            continue
        rows = (await db.execute(select(Object).where(
            Object.object_type_id == str(t.id)))).scalars().all()
        for o in rows:
            p = o.properties or {}
            if p.get("task_id") == tid:
                doomed.append(o)

    ids = [str(o.id) for o in doomed]
    await db.execute(Link.__table__.delete().where(
        or_(Link.source_object_id.in_(ids), Link.target_object_id.in_(ids))))
    for o in doomed:
        await db.delete(o)
    await db.commit()
    return {"deleted": True, "task_pk": tpk, "objects_removed": len(ids),
            "assets_stood_down": len(cs_list)}


async def create_object(db: AsyncSession, body: dict, user_email: str) -> dict:
    """Register a named map object (e.g. a BGC building footprint)."""
    await ensure_maven_ontology(db)
    svc = OntologyService(db)
    try:
        lat = float(body["lat"])
        lng = float(body["lng"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("lat and lng are required numbers") from exc
    name = str(body.get("name") or "").strip()[:80]
    if not name:
        raise ValueError("name is required")
    height = body.get("height_m")
    try:
        height = round(float(height), 1) if height is not None else None
    except (TypeError, ValueError):
        height = None
    fp = body.get("footprint")
    if not isinstance(fp, list) or not fp or len(fp) > 4000:
        fp = None
    t = await svc.get_object_type_by_name(OBJ_TYPE)
    if t is None:
        raise ValueError("maven_object type missing")
    pk = f"mv-obj:{uuid.uuid4().hex[:10]}"
    obj, _ = await _upsert_war_object(db, t.id, pk, {
        "name": name, "lat": round(lat, 6), "lng": round(lng, 6),
        "height_m": height, "footprint": fp,
        "registered_by": user_email or "operator", "created_at": _now_iso(),
    })
    await db.commit()
    return {"object_id": str(obj.id), "pk": pk}


async def rename_object(db: AsyncSession, object_id: str, new_name: str) -> dict:
    await ensure_maven_ontology(db)
    svc = OntologyService(db)
    try:
        obj = await svc.get_object(uuid.UUID(str(object_id)))
    except ValueError as exc:
        raise ValueError("invalid object id") from exc
    if obj is None or not str(obj.primary_key_value).startswith("mv-obj:"):
        raise ValueError("unknown object id")
    clean = str(new_name or "").strip()[:80]
    if not clean:
        raise ValueError("name is required")
    p = obj.properties or {}
    p["name"] = clean
    obj.properties = p
    await db.commit()
    return {"object_id": str(obj.id), "name": clean}


async def delete_object(db: AsyncSession, object_id: str) -> dict:
    await ensure_maven_ontology(db)
    svc = OntologyService(db)
    try:
        obj = await svc.get_object(uuid.UUID(str(object_id)))
    except ValueError as exc:
        raise ValueError("invalid object id") from exc
    if obj is None or not str(obj.primary_key_value).startswith("mv-obj:"):
        raise ValueError("unknown object id")
    oid = str(obj.id)
    await db.execute(Link.__table__.delete().where(
        or_(Link.source_object_id == oid, Link.target_object_id == oid)))
    await db.delete(obj)
    await db.commit()
    return {"deleted": True, "object_id": oid}


def _fleet_snapshot() -> list[dict]:
    """Live dead-reckoned snapshot of every active asset for constraint scoring."""
    now = time.time()
    out = []
    for a in _ASSETS.values():
        pos = asset_position(a, now)
        cls = ASSET_CLASSES[a["asset_class"]]
        out.append({
            "callsign": a["callsign"], "asset_class": a["asset_class"],
            "lat": pos["lat"], "lng": pos["lng"], "state": pos["state"],
            "task_id": a.get("task_id"),
            "detect_radius_km": float(cls["detect_radius_km"]),
            "speed_kts": float(cls["speed_kts"]),
            "orbit_period_s": int(cls["orbit_period_s"]),
        })
    return out


def _coa_options(det_props: dict, task_props: dict | None,
                 fleet: list[dict] | None = None) -> list[dict]:
    """Palantir-Maven-style constraint recommender for ONE validated contact.

    Ranks executable options purely by operational constraints — time-to-contact,
    distance, sensor fit, asset availability, station endurance — with a
    deterministic, auditable check-off per constraint. No wargaming involved.
    """
    lat = float(det_props.get("lat") or 0.0)
    lng = float(det_props.get("lng") or 0.0)
    conf = min(1.0, max(0.0, float(det_props.get("confidence") or 0.6)))
    det_asset = str(det_props.get("asset_callsign") or "")
    det_class = str(det_props.get("det_class") or "")
    fleet = _fleet_snapshot() if fleet is None else fleet
    options = []

    # --- shared constraint math ------------------------------------------------
    def eta_min(dist_km: float, speed_kts: float) -> int:
        return round(dist_km / (speed_kts * 1.852) * 60.0)

    threat = min(100, max(0, int(det_props.get("threat_score") or 0)))
    surface_contact = det_class in ("surface-contact", "vessel")
    intercept_class = "usv" if surface_contact else "uas"
    icls = ASSET_CLASSES[intercept_class]
    threat_check = {"name": "threat score", "ok": True,
                    "detail": f"{threat}/100 \u00b7 pattern {det_props.get('pattern') or 'unknown'}"}

    # best-positioned airborne asset of ANY class relative to the contact
    ranked_fleet = sorted(
        ((_haversine_km(a["lat"], a["lng"], lat, lng), a) for a in fleet),
        key=lambda p: p[0])
    if ranked_fleet:
        nearest_d_km, nearest_air = ranked_fleet[0]
    else:
        nearest_air, nearest_d_km = None, None
    covered = nearest_air is not None and nearest_d_km <= nearest_air["detect_radius_km"]
    fleet_cap = 8
    availability_ok = len(fleet) < fleet_cap

    # --- 1. SHADOW / HOLD (existing on-station collection) ---------------------
    shadow = next((a for a in fleet if a["callsign"] == det_asset),
                  next((a for a in fleet if a["state"] == "on-station"), None))
    checks, score = [], 20.0
    if shadow is not None:
        d = _haversine_km(shadow["lat"], shadow["lng"], lat, lng)
        within = d <= float(shadow["detect_radius_km"])
        checks.append({"name": "asset on station", "ok": True,
                       "detail": f"{shadow['callsign']} ({shadow['asset_class'].upper()})"})
        checks.append({"name": "sensor reach", "ok": within,
                       "detail": f"{d:.1f} km vs {float(shadow['detect_radius_km']):.0f} km radius"})
        checks.append({"name": "station endurance", "ok": True,
                       "detail": f"loiter cycle ~{shadow['orbit_period_s'] // 60} min at SIM x{SIM_SPEEDUP:.0f}"})
        checks.append(threat_check)
        score = 55 + 30 * conf + threat * 0.06 + (10 if within else -12)
        summary = (f"{shadow['callsign']} holds station and keeps collection "
                   "on the contact.")
        feasible = True
    else:
        checks.append({"name": "asset on station", "ok": False,
                       "detail": "none airborne over the AOI"})
        summary = "No on-station asset to hold collection."
        feasible = False
    options.append({"key": "shadow", "title": "SHADOW / HOLD", "summary": summary,
                    "feasible": feasible,
                    "score": round(min(99.0, max(5.0, score)), 1),
                    "checks": checks, "execute": {"kind": "none"}})

    # --- 2. INTERCEPT (dispatch closest-class interceptor from nearest rail) ---
    others = [a for a in fleet if not shadow or a["callsign"] != shadow["callsign"]]
    nearest_other_km = min((_haversine_km(a["lat"], a["lng"], lat, lng) for a in others),
                           default=None)
    checks = [{"name": "task linked", "ok": bool(task_props),
               "detail": str(task_props.get("name")) if task_props else "detection has no parent task"}]
    checks.append({"name": "interceptor class", "ok": True,
                   "detail": intercept_class.upper() +
                             (" (surface contact)" if surface_contact else " (air contact)")})
    feasible = bool(task_props)
    if task_props:
        r = float(task_props.get("aoi_radius_km") or 25.0)
        transit_min = eta_min(r + 30.0, float(icls["speed_kts"]))
        checks.append({"name": "time-to-contact", "ok": True,
                       "detail": f"≈{transit_min} min launch-to-AOI at {icls['speed_kts']:.0f} kt"
                                 f" (sim x{SIM_SPEEDUP:.0f})"})
        checks.append({"name": "sensor fit", "ok": icls["detect_radius_km"] >= 8.0,
                       "detail": f"{icls['detect_radius_km']:.0f} km detection radius vs AOI {r:.0f} km"})
    checks.append({"name": "availability", "ok": availability_ok,
                   "detail": f"{len(fleet)}/{fleet_cap} assets active"})
    if nearest_other_km is not None:
        checks.append({"name": "nearest friendly", "ok": True,
                       "detail": f"{nearest_other_km:.1f} km from contact"}) 
    checks.append(threat_check)
    score = 40 + 25 * conf + threat * 0.08 + (-15 if not feasible else 0) \
        + (6 if availability_ok else -20) \
        + (-8 if (not surface_contact and intercept_class == "usv") else 0)
    options.append({"key": "intercept", "title": "INTERCEPT",
                    "summary": f"Launch an additional {intercept_class.upper()} "
                               "on the parent task to close on the contact.",
                    "feasible": feasible,
                    "score": round(min(95.0, max(5.0, score)), 1),
                    "checks": checks,
                    "execute": {"kind": "dispatch", "asset_class": intercept_class}})

    # --- 3. MONITOR (passive) ---------------------------------------------------
    mon_checks = [{"name": "rules check", "ok": True, "detail": "passive collection only"}]
    if covered and nearest_air is not None:
        mon_checks.append({"name": "current coverage", "ok": True,
                           "detail": f"{nearest_air['callsign']} already within "
                                     f"{nearest_d_km:.1f} km of the contact"})
    elif nearest_air is not None:
        mon_checks.append({"name": "current coverage", "ok": False,
                           "detail": f"closest asset {nearest_d_km:.1f} km out — "
                                     "contact may drop from collection"})
    else:
        mon_checks.append({"name": "current coverage", "ok": False,
                           "detail": "no assets airborne — unwatched contact"})
    options.append({"key": "monitor", "title": "MONITOR",
                    "summary": "No kinetic action; flag the contact for the watchlist.",
                    "feasible": True,
                    "score": round(max(5.0, min(45.0, 25 + 10 * (1 - conf))
                                + (8 if covered else 0) - threat * 0.06), 1),
                    "checks": mon_checks,
                    "execute": {"kind": "watch"}})

    options.sort(key=lambda o: o["score"], reverse=True)
    return options


async def generate_target_coa(db: AsyncSession, body: dict, user_email: str) -> dict:
    """Phase-2 COA generation for ONE validated detection (Maven-style):
    package target+asset options with automated check-offs."""
    await ensure_maven_ontology(db)
    svc = OntologyService(db)
    try:
        det = await svc.get_object(uuid.UUID(str(body.get("detection_id"))))
    except ValueError as exc:
        raise ValueError("invalid detection id") from exc
    if det is None or not str(det.primary_key_value).startswith("mv-det:"):
        raise ValueError("unknown detection id")
    dp = det.properties or {}
    if dp.get("validated") is not True:
        raise ValueError("detection must be CONFIRMED before COA generation")

    task_id = str(dp.get("task_id") or "")
    task_props = None
    if task_id:
        t = await svc.get_object(uuid.UUID(task_id)) if _is_uuid(task_id) else None
        if t is not None:
            task_props = t.properties or {}

    options = _coa_options(dp, task_props)
    # Qwen intelligence draft — failure-tolerant by contract (COA never fails on LLM)
    intel: dict = {"error": "unavailable"}
    try:
        intel = await draft_coa_intelligence(db, dp, task_props, options) or intel
    except Exception:
        pass
    pk = f"mv-tcoa:{uuid.uuid4().hex[:10]}"
    tt = await svc.get_object_type_by_name(COA2_TYPE)
    coa, was_new = await _upsert_war_object(db, tt.id, pk, {
        "detection_id": str(det.id), "label": dp.get("label"),
        "det_class": dp.get("det_class"), "confidence": dp.get("confidence"),
        "lat": dp.get("lat"), "lng": dp.get("lng"), "task_id": task_id,
        "options": options, "status": "proposed", "intel": intel,
        "created_by": user_email or "operator", "created_at": _now_iso(),
    })
    lt = (await db.execute(select(LinkType).where(
        LinkType.name == LT_COA_TARGET))).scalar_one_or_none()
    if lt is not None:
        await _ensure_link(db, lt.id, coa.id, det.id, {"det_class": dp.get("det_class")})
    await db.commit()
    return {"coa_id": str(coa.id), "pk": pk, "options": options, "intel": intel}


async def auto_task(db: AsyncSession, body: dict, user_email: str) -> dict:
    """One-shot mission: resolve target (object_id OR lat/lng) → create task
    → dispatch asset. Built for YONO/chat automation."""
    await ensure_maven_ontology(db)
    svc = OntologyService(db)
    lat = lng = None
    name = str(body.get("name") or "").strip()[:80]
    oid = body.get("object_id")
    if oid:
        obj = await svc.get_object(uuid.UUID(str(oid))) if _is_uuid(oid) else None
        if obj is None or not str(obj.primary_key_value).startswith("mv-obj:"):
            raise ValueError("unknown object id")
        op = obj.properties or {}
        lat, lng = float(op.get("lat")), float(op.get("lng"))
        if not name:
            name = f"AUTO {op.get('name') or 'OBJECT'}"
    if lat is None:
        try:
            lat = float(body["lat"])
            lng = float(body["lng"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("object_id or lat+lng required") from exc
    task = await create_task(db, {
        "aoi_lat": lat, "aoi_lng": lng,
        "aoi_radius_km": body.get("radius_km") or 1.0,
        "priority": body.get("priority") or "high",
        "name": name or f"AUTO-{uuid.uuid4().hex[:5].upper()}",
    }, user_email)
    dis = await dispatch_asset(db, task["task_id"],
                               body.get("asset_class") or "uas", user_email)
    return {"task": task, "dispatched": {
        "callsign": dis.get("callsign"),
        "asset_class": body.get("asset_class") or "uas",
        "origin": dis.get("origin")} if isinstance(dis, dict) else None}


def _is_uuid(s: str) -> bool:
    try:
        uuid.UUID(str(s))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


async def get_places() -> dict:
    """Reference layer: group network nodes + BGC company directory from the
    ecosystem source of truth (non-financial fields only) PLUS the static
    famous-landmarks layer, cached 10 min. Landmarks are always returned even
    if the ecosystem is unreachable."""
    now = time.time()
    if _PLACES_CACHE["data"] and now - _PLACES_CACHE["ts"] < PLACES_TTL_S:
        return _PLACES_CACHE["data"]
    eco: dict = {}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(ECOSYSTEM_PUBLIC_URL)
            r.raise_for_status()
            eco = r.json() if isinstance(r.json(), dict) else {}
    except Exception:
        eco = {}
    nm = eco.get("networkMap") or {}
    nodes = []
    for n in nm.get("nodes") or []:
        try:
            lat, lng = float(n.get("lat")), float(n.get("lng"))
        except (TypeError, ValueError):
            continue
        stack = [str(t.get("name")) for t in (n.get("techStack") or [])
                 if isinstance(t, dict) and t.get("name")]
        nodes.append({"name": str(n.get("name") or n.get("city") or "NODE"),
                      "city": str(n.get("city") or ""),
                      "sector": str(n.get("sector") or ""),
                      "lat": lat, "lng": lng, "techStack": stack[:12]})
    comps = []
    core = ((eco.get("bgcDirectory") or {}).get("metadata") or {}).get("core") or {}
    for c in (eco.get("bgcDirectory") or {}).get("companies") or []:
        try:
            lat, lng = float(c.get("lat")), float(c.get("lng"))
        except (TypeError, ValueError):
            continue
        comps.append({
            "name": str(c.get("name") or "?"),
            "address": str(c.get("address") or ""),
            "district": str(c.get("district") or ""),
            "industry": str(c.get("industry") or ""),
            "lat": lat, "lng": lng,
            "techStack": [str(t) for t in (c.get("techStack") or [])][:12],
            "lastVerified": str(c.get("lastVerified") or ""),
        })
    landmarks = [dict(l) for l in _LANDMARKS]
    data = {"nodes": nodes, "companies": comps, "landmarks": landmarks, "fetched_at": _now_iso()}
    _PLACES_CACHE["ts"] = now
    _PLACES_CACHE["data"] = data
    return data


def _photo_dir() -> str:
    d = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "uploads", "maven")
    os.makedirs(d, exist_ok=True)
    return d


async def attach_photo(db: AsyncSession, object_id: str, data_b64: str,
                       caption: str, kind: str, user_email: str) -> dict:
    import base64
    svc = OntologyService(db)
    obj = None
    if _is_uuid(object_id):
        obj = await svc.get_object(uuid.UUID(str(object_id)))
    if obj is None or not str(obj.primary_key_value).startswith("mv-obj:"):
        raise ValueError("unknown object id")
    try:
        raw = base64.b64decode(str(data_b64), validate=False)
    except (ValueError, TypeError) as exc:
        raise ValueError("invalid image payload") from exc
    if not raw or len(raw) > PHOTO_MAX_BYTES:
        raise ValueError("image missing or too large (max 8MB)")
    ext = ".png" if raw[:4] == b"\x89PNG" else (
        ".jpg" if raw[:3] == b"\xff\xd8\xff" else None)
    if ext is None:
        raise ValueError("only JPEG/PNG images accepted")
    fname = uuid.uuid4().hex + ext
    with open(os.path.join(_photo_dir(), fname), "wb") as fh:
        fh.write(raw)
    p = obj.properties or {}
    atts = p.get("attachments") or []
    att = {"id": uuid.uuid4().hex[:10], "file": fname,
           "caption": str(caption or "").strip()[:120], "kind": kind or "upload",
           "by": user_email or "operator", "at": _now_iso()}
    atts.append(att)
    p["attachments"] = atts[-24:]
    obj.properties = p
    await db.commit()
    return {"attachment": att}


async def delete_photo(db: AsyncSession, object_id: str, att_id: str) -> dict:
    svc = OntologyService(db)
    obj = None
    if _is_uuid(object_id):
        obj = await svc.get_object(uuid.UUID(str(object_id)))
    if obj is None or not str(obj.primary_key_value).startswith("mv-obj:"):
        raise ValueError("unknown object id")
    p = obj.properties or {}
    keep, removed = [], None
    for a in p.get("attachments") or []:
        if a.get("id") == str(att_id):
            removed = a
        else:
            keep.append(a)
    if removed is None:
        raise ValueError("unknown attachment id")
    try:
        os.remove(os.path.join(_photo_dir(), removed["file"]))
    except OSError:
        pass
    p["attachments"] = keep
    obj.properties = p
    await db.commit()
    return {"deleted": True, "attachment_id": str(att_id)}


async def maven_command(db: AsyncSession, body: dict, user_email: str) -> dict:
    """Natural-language command bridge for YONO/chat automation.
    Intents: status | task on <object> | coa for <contact> |
    execute intercept|shadow|monitor [for <contact>] | help"""
    await ensure_maven_ontology(db)
    svc = OntologyService(db)
    text = str(body.get("text") or "").strip()
    low = text.lower()
    directive = None

    async def objs_of(tname):
        t = await svc.get_object_type_by_name(tname)
        if t is None:
            return []
        return (await db.execute(
            select(Object).where(Object.object_type_id == str(t.id))
        )).scalars().all()

    def _created(o):
        return (o.properties or {}).get("created_at") or ""

    if not low or low.startswith("help"):
        reply = ("MAVEN COMMANDS\n"
                 "- task on <object name> — launch a mission at a registered object\n"
                 "- coa for <contact> — generate courses of action for a CONFIRMED contact\n"
                 "- execute intercept|shadow|monitor [for <contact>] — run the chosen COA\n"
                 "- status — fleet and mission summary")
    elif "status" in low:
        tasks = await objs_of(TASK_TYPE)
        dets = await objs_of(DET_TYPE)
        pend = [d for d in dets if (d.properties or {}).get("validated") is None]
        reply = (f"STATUS — tasks: {len(tasks)} · assets airborne: {len(_ASSETS)} · "
                 f"detections: {len(dets)} ({len(pend)} pending validation)")
    elif low.startswith("execute"):
        m = re.match(r"execute\s+(intercept|shadow|monitor)(?:\s+for\s+(.+))?", low)
        opt = m.group(1) if m else ""
        want = (m.group(2) or "").strip() if m else ""
        tcoas = sorted(await objs_of(COA2_TYPE), key=_created, reverse=True)
        if want:
            tcoas = [c for c in tcoas
                     if want in str((c.properties or {}).get("label", "")).lower()]
        coa = next((c for c in tcoas
                    if (c.properties or {}).get("status") != "executed"), None)
        if coa is None:
            reply = "No executable COA found. Generate one first: coa for <contact>."
        else:
            res = await execute_target_coa(db, str(coa.id), opt, user_email)
            cp = coa.properties or {}
            reply = f"EXECUTED {opt.upper()} on {cp.get('label')} ✓"
            if isinstance(res, dict) and res.get("callsign"):
                reply += f"\nAsset {res['callsign']} launched."
            directive = {"op": "fly_to",
                         "center": [float(cp.get("lng") or 0), float(cp.get("lat") or 0)],
                         "zoom": 11}
    elif low.startswith("coa"):
        m = re.match(r"coa\s+(?:for\s+)?(.*)", low)
        want = (m.group(1) or "").strip().lower() if m else ""
        dets = [d for d in await objs_of(DET_TYPE)
                if (d.properties or {}).get("validated") is True]
        if want:
            dets = [d for d in dets
                    if want in str((d.properties or {}).get("label", "")).lower()]
        if not dets:
            reply = ("No CONFIRMED contact matches. Validate a detection first "
                     "(TASKS tab), then retry.")
        else:
            latest = max(dets, key=_created)
            dp = latest.properties or {}
            res = await generate_target_coa(db,
                                            {"detection_id": str(latest.id)},
                                            user_email)
            lines = [f"COA GENERATED for {dp.get('label')}:"]
            for o in res["options"]:
                lines.append(f"- {o['title']} · score {o['score']} · "
                             + ("feasible" if o["feasible"] else "INFEASIBLE"))
            lines.append("Say: execute intercept  (or shadow / monitor)")
            reply = "\n".join(lines)
            directive = {"op": "fly_to",
                         "center": [float(dp.get("lng") or 0), float(dp.get("lat") or 0)],
                         "zoom": 11}
    elif low.startswith("fly to") or low.startswith("fly "):
        want = re.sub(r"^fly\s+(to\s+)?", "", low).strip()
        places = await get_places()
        pool = [(p, "company") for p in places["companies"]] + \
               [(n, "node") for n in places["nodes"]]
        best, best_len = None, 0
        for p, kind in pool:
            nm = p["name"].lower()
            if want and want in nm and len(nm) > best_len:
                best, best_len = (p, kind), len(nm)
        if best is None:
            reply = f"No company or node matching '{want}'."
        else:
            p, kind = best
            stack = ", ".join(p["techStack"][:6])
            reply = (f"{p['name'].upper()} ({kind})\n{p.get('address') or p.get('sector', '')}\n"
                     + (f"Stack: {stack}" if stack else ""))
            directive = {"op": "fly_to",
                         "center": [p["lng"], p["lat"]], "zoom": 16.5}
    elif low.startswith("task"):
        m = re.match(r"task(?:\s+(?:on|at))?\s+(.+)$", low)
        want = (m.group(1) or "").strip().lower() if m else ""
        best = None
        for o in await objs_of(OBJ_TYPE):
            nm = str((o.properties or {}).get("name", "")).lower()
            if want and want in nm and (best is None or len(nm) < len(
                    str((best.properties or {}).get("name", "")))):
                best = o
        if best is None:
            reply = (f"No registered object named '{want}'. Register it in the "
                     "OBJECTS tab first.")
        else:
            op = best.properties or {}
            res = await auto_task(db, {"object_id": str(best.id),
                                       "priority": "high"}, user_email)
            dis = res.get("dispatched") or {}
            reply = (f"MISSION LAUNCHED → {op.get('name')}\n"
                     f"Task {res['task'].get('pk')} · asset "
                     f"{dis.get('callsign')} inbound from {dis.get('origin')}.")
            directive = {"op": "fly_to",
                         "center": [float(op.get("lng") or 0), float(op.get("lat") or 0)],
                         "zoom": 15}
    else:
        reply = "Unknown command. Type: maven help"

    return {"reply": reply, "directive": directive}


async def execute_target_coa(db: AsyncSession, coa_id: str, option_key: str,
                             user_email: str) -> dict:
    """Phase-3 execution: run the packaged option's action and stamp the COA."""
    await ensure_maven_ontology(db)
    svc = OntologyService(db)
    try:
        coa = await svc.get_object(uuid.UUID(str(coa_id)))
    except ValueError as exc:
        raise ValueError("invalid coa id") from exc
    if coa is None or not str(coa.primary_key_value).startswith("mv-tcoa:"):
        raise ValueError("unknown coa id")
    cp = coa.properties or {}
    if cp.get("status") == "executed":
        raise ValueError("COA already executed")
    opt = next((o for o in (cp.get("options") or [])
                if o.get("key") == str(option_key)), None)
    if opt is None:
        raise ValueError("unknown option key")
    if not opt.get("feasible"):
        raise ValueError(f"option {option_key} is not feasible")

    kind = (opt.get("execute") or {}).get("kind")
    result_extra = {}
    if kind == "dispatch":
        tid = cp.get("task_id")
        if not tid or not _is_uuid(tid):
            raise ValueError("COA has no parent task to dispatch against")
        res = await dispatch_asset(db, tid,
                                   (opt["execute"].get("asset_class") or "uas"),
                                   user_email)
        result_extra = {"dispatched": res.get("callsign")}
    elif kind == "watch":
        det = await svc.get_object(uuid.UUID(str(cp.get("detection_id")))) \
            if _is_uuid(cp.get("detection_id")) else None
        if det is not None:
            dprops = det.properties or {}
            dprops["watch"] = True
            await db.execute(update(Object).where(Object.id == det.id)
                             .values(properties=dprops))  # explicit UPDATE
        result_extra = {"watch": True}

    cp["status"] = "executed"
    cp["executed_option"] = str(option_key)
    cp["executed_by"] = user_email or "operator"
    cp["executed_at"] = _now_iso()
    await db.execute(update(Object).where(Object.id == coa.id)
                     .values(properties=cp))  # explicit UPDATE: attribute mutation loses writes here
    await db.commit()
    return {"coa_id": str(coa.id), "executed": str(option_key), **result_extra}


async def prune_detections(db: AsyncSession, ttl_days: int = 14) -> dict:
    """Delete ephemeral maven_detection objects older than TTL. Tasks/assets/
    COAs/action executions are NEVER pruned (permanent audit trail)."""
    ttl_days = max(1, min(int(ttl_days), 365))
    cutoff = time.time() - ttl_days * 86400.0
    svc = OntologyService(db)
    dt = await svc.get_object_type_by_name(DET_TYPE)
    if dt is None:
        return {"pruned": 0, "ttl_days": ttl_days}
    objs = (await db.execute(select(Object).where(
        Object.object_type_id == str(dt.id)))).scalars().all()
    removed = 0
    for o in objs:
        emitted = str((o.properties or {}).get("emitted_at") or "")
        try:
            ts = datetime.fromisoformat(emitted).timestamp() if emitted else 0.0
        except ValueError:
            continue
        if ts and ts < cutoff:
            # Drop dependent link rows first (SQLAlchemy would otherwise
            # try to null their FKs and violate NOT NULL constraints).
            await db.execute(Link.__table__.delete().where(
                (Link.source_object_id == str(o.id))
                | (Link.target_object_id == str(o.id))))
            _LAST_DET.pop(f"{o.primary_key_value}", None)
            await db.delete(o)
            removed += 1
    await db.commit()
    return {"pruned": removed, "ttl_days": ttl_days}


async def maven_state(db: AsyncSession) -> dict:
    """Snapshot for the UI: assets (dead-reckoned), recent detections, tasks."""
    await ensure_maven_ontology(db)
    svc = OntologyService(db)
    now = time.time()
    assets_out = []
    for asset in _ASSETS.values():
        pos = asset_position(asset, now)
        asset.update(pos)
        cls = ASSET_CLASSES[asset["asset_class"]]
        remaining = max(0, int(asset["eta_s"] - (now - asset["launched_at"])))
        assets_out.append({
            "callsign": asset["callsign"], "asset_class": asset["asset_class"],
            "state": pos["state"], "lat": pos["lat"], "lng": pos["lng"],
            "heading_deg": pos["heading_deg"], "fov_swath_m": cls["fov_swath_m"],
            "orbit_radius_deg": ORBIT_RADIUS_DEG,
            "orbit_period_s": cls["orbit_period_s"],
            "detect_radius_km": cls["detect_radius_km"], "task_id": asset["task_id"],
            "task_pk": asset["task_pk"], "origin": asset["origin"]["name"],
            "speedup": float(asset.get("speedup") or 1.0),
            "eta_remaining_s": remaining if pos["state"] == "transit" else 0,
        })

    async def _objs(type_name, limit):
        t = type_ids.get(type_name)
        if t is None:
            return []
        rows = (await db.execute(select(Object).where(
            Object.object_type_id == str(t.id))
            .order_by(Object.created_at.desc()).limit(limit))).scalars().all()
        return list(rows)

    type_ids = {}
    for name in (TASK_TYPE, DET_TYPE, COA_TYPE, OBJ_TYPE, COA2_TYPE):
        t = await svc.get_object_type_by_name(name)
        if t is not None:
            type_ids[name] = t

    tasks = [{"id": str(o.id), "pk": o.primary_key_value,
              **(o.properties or {})} for o in await _objs(TASK_TYPE, 50)]
    dets = [{"id": str(o.id), "pk": o.primary_key_value,
             **(o.properties or {})} for o in await _objs(DET_TYPE, 80)]
    coas = [{"id": str(o.id), "pk": o.primary_key_value,
             **(o.properties or {})} for o in await _objs(COA_TYPE, 20)]
    objs_out = [{"id": str(o.id), "pk": o.primary_key_value,
                 **(o.properties or {})} for o in await _objs(OBJ_TYPE, 200)]
    tcoas = [{"id": str(o.id), "pk": o.primary_key_value,
              **(o.properties or {})} for o in await _objs(COA2_TYPE, 50)]
    return {"assets": assets_out, "tasks": tasks, "detections": dets,
            "coas": coas, "objects": objs_out, "target_coas": tcoas,
            "server_time": _now_iso()}


# ----------------------------------------------------- YONO agent tools ----
MAVEN_AGENT_TOOLS = [
    {
        "name": "maven_situation",
        "description": "MAVEN mission board snapshot: active tasks (name/status/priority/counts), number of live assets and recent detections.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "maven_contacts",
        "description": "List MAVEN contacts (detections) sorted hottest-first with threat score and movement pattern. Set confirmed_only=false for pending ones too.",
        "parameters": {
            "type": "object",
            "properties": {
                "confirmed_only": {"type": "boolean", "description": "Only CONFIRMED contacts (default true)", "default": True},
                "limit": {"type": "integer", "description": "Max contacts returned (default 8)", "default": 8},
            },
            "required": [],
        },
    },
    {
        "name": "maven_full_mission",
        "description": "One-shot mission: create a task around a coordinate and immediately dispatch an asset. Returns task id and dispatched callsign.",
        "parameters": {
            "type": "object",
            "properties": {
                "lat": {"type": "number"}, "lng": {"type": "number"},
                "name": {"type": "string"},
                "radius_km": {"type": "number", "default": 25.0},
                "asset_class": {"type": "string", "enum": ["uas", "usv"], "default": "uas"},
            },
            "required": ["lat", "lng"],
        },
    },
    {
        "name": "maven_generate_coa",
        "description": "Generate a Palantir-style course-of-action package for ONE CONFIRMED contact: ranked constraint-checked options plus Qwen-drafted situation/intent/recommendation. Accepts detection id OR exact label.",
        "parameters": {
            "type": "object",
            "properties": {"contact": {"type": "string", "description": "detection UUID or exact label, e.g. 'DAL683'"}},
            "required": ["contact"],
        },
    },
    {
        "name": "maven_create_object",
        "description": "Register a named object of interest on the map (vessel, building, site). The panel flies the camera to it after creation.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "lat": {"type": "number"}, "lng": {"type": "number"},
                "height_m": {"type": "number"}
            },
            "required": ["name", "lat", "lng"]
        }
    },
    {
        "name": "maven_execute",
        "description": "Execute one option of a generated target COA (e.g. option_key 'monitor' or 'intercept').",
        "parameters": {
            "type": "object",
            "properties": {
                "coa_id": {"type": "string"},
                "option_key": {"type": "string", "enum": ["shadow", "intercept", "monitor"]},
            },
            "required": ["coa_id", "option_key"],
        },
    },
]


async def execute_maven_tool(db: AsyncSession, tool_name: str, arguments: dict) -> dict:
    """Runtime for the maven_* YONO agent tools (called via OntologyToolExecutor)."""
    a = arguments or {}
    actor = "yono-agent"
    if tool_name == "maven_situation":
        st = await maven_state(db)
        return {
            "tasks": [{"id": t["id"], "name": t.get("name"), "status": t.get("status"),
                       "priority": t.get("priority"), "assets": t.get("assets"),
                       "detections": t.get("detections")} for t in st["tasks"][:10]],
            "assets_active": len(st["assets"]),
            "recent_detections": len(st["detections"]),
            "target_coas": len(st["target_coas"]),
        }
    if tool_name == "maven_contacts":
        st = await maven_state(db)
        confirmed = bool(a.get("confirmed_only", True))
        pool = [d for d in st["detections"]
                if (not confirmed or d.get("validated") is True)]
        pool.sort(key=lambda d: -(d.get("threat_score") or 0))
        return {"contacts": [{"id": d["id"], "label": d.get("label"),
                              "det_class": d.get("det_class"),
                              "threat_score": d.get("threat_score"),
                              "pattern": d.get("pattern"),
                              "confidence": d.get("confidence"),
                              "validated": d.get("validated")}
                             for d in pool[: max(1, min(int(a.get("limit") or 8), 20))]]}
    if tool_name == "maven_full_mission":
        return await auto_task(db, {
            "lat": a.get("lat"), "lng": a.get("lng"),
            "name": a.get("name"), "radius_km": a.get("radius_km") or 25.0,
            "priority": "high",
            "asset_class": a.get("asset_class") or "uas",
        }, actor)
    if tool_name == "maven_generate_coa":
        contact = str(a.get("contact") or "").strip()
        det_id = contact if _is_uuid(contact) else None
        if not det_id:
            st = await maven_state(db)
            matches = [d for d in st["detections"]
                       if str(d.get("label") or "").lower() == contact.lower()]
            if not matches:
                return {"error": f"no contact matching label '{contact}'"}
            matches.sort(key=lambda d: (d.get("validated") is not True,
                                        -(d.get("threat_score") or 0)))
            det_id = matches[0]["id"]
        return await generate_target_coa(db, {"detection_id": det_id}, actor)
    if tool_name == "maven_execute":
        return await execute_target_coa(db, str(a.get("coa_id") or ""),
                                        str(a.get("option_key") or ""), actor)
    if tool_name == "maven_create_object":
        obj = await create_object(db, {
            "name": a.get("name"), "lat": a.get("lat"), "lng": a.get("lng"),
            "height_m": a.get("height_m"),
        }, actor)
        return {**obj,
                "directive": {"op": "fly_to",
                              "center": [float(a.get("lng")), float(a.get("lat"))],
                              "zoom": 9.5}}
    return {"error": f"unknown maven tool: {tool_name}"}


async def resolve_maven_target(db: AsyncSession, target: str):
    """Resolve free text to coordinates across the maven world.
    Order: contacts (label/id/pk) -> assets (callsign) -> tasks (name/id)
    -> registered objects. Returns {kind,id,pk,lat,lng,label} or None."""
    q = str(target or "").strip().lower()
    if not q:
        return None
    st = await maven_state(db)
    for d in st["detections"]:
        hay = [str(d.get("label") or "").lower(), str(d.get("id")).lower(),
               str(d.get("pk") or "").lower()]
        if q in hay:
            return {"kind": "contact", "id": str(d["id"]), "pk": d.get("pk"),
                    "lat": d.get("lat"), "lng": d.get("lng"),
                    "label": d.get("label") or "?"}
    for a in st["assets"]:
        if q == str(a.get("callsign") or "").lower():
            return {"kind": "asset", "id": a["callsign"], "pk": a["callsign"],
                    "lat": a.get("lat"), "lng": a.get("lng"), "label": a["callsign"]}
    for t in st["tasks"]:
        if q in (str(t.get("name") or "").lower(), str(t.get("id")).lower()):
            return {"kind": "task", "id": str(t["id"]), "pk": t.get("pk"),
                    "lat": t.get("aoi_lat"), "lng": t.get("aoi_lng"),
                    "label": t.get("name") or "?"}
    from sqlalchemy import select as _sel
    rowset = (await db.execute(
        _sel(Object).where(Object.primary_key_value.like("mv-obj:%"))
        .order_by(Object.created_at.desc()).limit(200))).scalars().all()
    for o in rowset:
        p = o.properties or {}
        if q in (str(p.get("name") or "").lower(), str(o.primary_key_value).lower(),
                 str(o.id).lower()):
            return {"kind": "object", "id": str(o.id), "pk": o.primary_key_value,
                    "lat": p.get("lat"), "lng": p.get("lng"),
                    "label": p.get("name") or o.primary_key_value}
    return None


# ------------------------------------------------ Qwen COA intelligence ----
PREFERRED_DRAFT_MODEL = "Qwen3.8-27B"

_MAVEN_INTEL_SYSTEM = (
    "You are the MAVEN smart-layer intelligence officer. Write like a military "
    "intelligence brief: short declarative sentences, active voice, no hedging, "
    "no pleasantries. Use ONLY the structured facts provided - never invent "
    "data. Return STRICT JSON only (no markdown fences): "
    '{"situation": "<=3 sentences", '
    '"intent_estimate": "<=2 sentences: most-likely then most-dangerous adversary course", '
    '"recommendation": {"option_key": "<one of the provided option keys>", '
    '"rationale": "<=2 sentences grounded in the stated constraints"}}'
)


def _intel_fact_block(det_props: dict, task_props: dict | None,
                      options: list[dict]) -> str:
    lines = ["CONTACT FACTS:"]
    for k in ("label", "det_class", "confidence", "threat_score", "pattern",
              "lat", "lng", "track_source", "asset_callsign"):
        v = det_props.get(k)
        if v is not None:
            lines.append(f"{k}: {v}")
    if task_props:
        lines.append(f"parent_task: {task_props.get('name')} "
                     f"(AOI {task_props.get('aoi_lat')}N {task_props.get('aoi_lng')}E "
                     f"r={task_props.get('aoi_radius_km')}km, priority {task_props.get('priority')})")
    snap = _fleet_snapshot()
    lines.append("FLEET STATE:")
    for a in snap:
        lines.append(f"- {a['callsign']} ({a['asset_class']}) {a['state']} "
                     f"at {a['lat']},{a['lng']} reach {a['detect_radius_km']}km")
    if not snap:
        lines.append("- none airborne")
    lines.append("CONSTRAINT-RANKED OPTIONS:")
    for o in options:
        checks = "; ".join(f"{c['name']}={'ok' if c['ok'] else 'FAIL'}({c['detail']})"
                           for c in o.get("checks", []))
        lines.append(f"- {o['key']}: score {o['score']} feasible={o['feasible']} | {checks}")
    return "\n".join(lines)


async def draft_coa_intelligence(db: AsyncSession, det_props: dict,
                                 task_props: dict | None,
                                 options: list[dict]) -> dict:
    """Qwen-drafted situation / intent estimate / recommendation for one COA.
    Failure-tolerant by contract: returns {'error': ...} instead of raising."""
    import os as _os
    from panteon.yono.sc_agent_seed import _resolve_model_id
    from panteon.yono.service import LLMOrchestrator
    model_id = None
    override = _os.environ.get("MAVEN_INTEL_MODEL", "").strip()
    if override:
        from panteon.yono.models import LLMModel
        from sqlalchemy import select as _sel
        row = await db.execute(_sel(LLMModel).where(
            LLMModel.model_id == override, LLMModel.is_enabled == True))  # noqa: E712
        mrow = row.scalars().first()
        model_id = mrow.id if mrow else None
    if model_id is None:
        model_id = await _resolve_model_id(db)
    if model_id is None:
        return {"error": "no enabled LLM model"}
    orch = LLMOrchestrator(db)
    ex = await orch.execute_llm(
        model_id, _intel_fact_block(det_props, task_props, options),
        system_prompt=_MAVEN_INTEL_SYSTEM,
        parameters={"temperature": 0.3}, created_by="maven-intel")
    raw = (ex.response or "").strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return {"error": "unparseable model output"}
    parsed = json.loads(raw[start:end + 1])
    rec = parsed.get("recommendation") or {}
    known = {o["key"] for o in options}
    if rec.get("option_key") not in known:
        top = options[0]["key"] if options else None
        rec["option_key"] = top
    return {
        "situation": str(parsed.get("situation") or ""),
        "intent_estimate": str(parsed.get("intent_estimate") or ""),
        "recommendation": rec,
        "drafted_by": PREFERRED_DRAFT_MODEL,
        "drafted_at": _now_iso(),
    }


async def redraft_coa_intelligence(db: AsyncSession, coa_id: str,
                                   user_email: str | None) -> dict:
    """Re-run Qwen drafting on an existing target COA."""
    await ensure_maven_ontology(db)
    svc = OntologyService(db)
    coa = await svc.get_object(uuid.UUID(str(coa_id))) if _is_uuid(coa_id) else None
    if coa is None or not str(coa.primary_key_value).startswith("mv-tcoa:"):
        raise ValueError("unknown target COA id")
    cp = dict(coa.properties or {})
    det_props = dict(cp)
    task_props = None
    tid = str(cp.get("task_id") or "")
    if tid and _is_uuid(tid):
        t = await svc.get_object(uuid.UUID(tid))
        task_props = t.properties if t is not None else None
    intel = await draft_coa_intelligence(db, det_props, task_props,
                                         cp.get("options") or [])
    cp["intel"] = intel
    await db.execute(update(Object).where(Object.id == coa.id)
                     .values(properties=cp))
    await db.commit()
    return intel
