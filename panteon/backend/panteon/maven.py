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
import time
import uuid
from datetime import datetime, timezone

import httpx
from sqlalchemy import or_, select
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

LT_TASKED_IN = "mv_tasked_in"    # task -> theater
LT_ASSIGNED = "mv_assigned"      # asset -> task
LT_DETECTED = "mv_detected"      # detection -> task

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
    radius_km = max(1.0, min(float(body.get("aoi_radius_km") or 25.0), 300.0))
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
    task.properties = props
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
    orb_lat = 0.03 * math.cos(angle)
    orb_lng = 0.03 * math.sin(angle) / max(0.2, math.cos(math.radians(a["lat"])))
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


def _classify(track: dict, dist_km: float, radius_km: float) -> tuple[str, float]:
    """Deterministic classification of a REAL contact. Returns (class, confidence)."""
    mil = track.get("category") == "military" or str(track.get("squawk") or "").startswith(("0", "7"))
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
    tracks = _live_tracks()
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
        for tr in tracks:
            d_asset = _haversine_km(pos["lat"], pos["lng"], tr["lat"], tr["lng"])
            d_aoi = _haversine_km(aoi["lat"], aoi["lng"], tr["lat"], tr["lng"])
            if d_asset > cls["detect_radius_km"] or d_aoi > aoi["radius_km"] + 10.0:
                continue
            key = f"{asset['task_pk']}:{tr['track_id']}"
            if now - _LAST_DET.get(key, 0.0) < DET_COOLDOWN_S:
                continue
            _LAST_DET[key] = now
            det_class, conf = _classify(tr, d_asset, cls["detect_radius_km"])
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
                    task_obj.properties = tp
    await db.commit()
    return {"synced_assets": synced, "new_detections": len(new_dets),
            "detections": [{"id": str(d.id), "pk": d.primary_key_value,
                            **{k: v for k, v in (d.properties or {}).items()}}
                           for d in new_dets],
            "tracks_scanned": len(tracks)}


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
    det.properties = props
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
            try:
                resp = await client.post(
                    "http://localhost:8090/api/kriegspiel/campaign/simulate",
                    json=payload)
                resp.raise_for_status()
                camp = resp.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise RuntimeError(f"sims gateway failed for COA {code}: {exc}") from exc
            wins = camp.get("campaign_wins") or {}
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
            task_obj.properties = tp
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
    for name in (TASK_TYPE, DET_TYPE, COA_TYPE):
        t = await svc.get_object_type_by_name(name)
        if t is not None:
            type_ids[name] = t

    tasks = [{"id": str(o.id), "pk": o.primary_key_value,
              **(o.properties or {})} for o in await _objs(TASK_TYPE, 50)]
    dets = [{"id": str(o.id), "pk": o.primary_key_value,
             **(o.properties or {})} for o in await _objs(DET_TYPE, 80)]
    coas = [{"id": str(o.id), "pk": o.primary_key_value,
             **(o.properties or {})} for o in await _objs(COA_TYPE, 20)]
    return {"assets": assets_out, "tasks": tasks, "detections": dets,
            "coas": coas, "server_time": _now_iso()}
