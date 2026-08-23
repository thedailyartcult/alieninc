"""
Kriegspiel War Ontology — Palantir-style semantic bridge between sims-suite
battle runs and the Spinal Cracker object ontology (sc_* tables).

Every war simulation becomes a first-class digital-twin event:

  kriegspiel_theater  — real-world theater (Taiwan Strait, Levant, ...)
  kriegspiel_force    — red/blue operational group with a doctrine
  kriegspiel_assessment — one Monte Carlo battle/campaign run (an event object)
  ks_located_in       force -> theater
  ks_assessed_in      assessment -> theater
  ks_opposes          red force -> blue force
  kriegspeil_run_battle action type executes the sim and emits the above.

Objects carry lat/lng inside `properties` so the fusion map can render them.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from panteon.spinal_craker.models import ActionType, Link, LinkType, Object, ObjectType
from panteon.spinal_craker.service import OntologyService

THEATER_TYPE = "kriegspiel_theater"
FORCE_TYPE = "kriegspiel_force"
ASSESSMENT_TYPE = "kriegspiel_assessment"

LT_LOCATED_IN = "ks_located_in"    # force -> theater
LT_ASSESSED_IN = "ks_assessed_in"  # assessment -> theater
LT_OPPOSES = "ks_opposes"          # force(red) -> force(blue)

AT_RUN_BATTLE = "kriegspiel_run_battle"

_WAR_OBJECT_TYPES = {
    THEATER_TYPE: {
        "display_name": "War Theater",
        "description": "Real-world theater simulated by Kriegspiel (bounds, terrain, center).",
        "icon": "globe",
        "properties_schema": {
            "name": "string", "terrain": "string", "area_km2": "number",
            "lat": "number", "lng": "number", "bounds": "array",
            "assessments": "number", "last_assessed_at": "string",
        },
    },
    FORCE_TYPE: {
        "display_name": "War Force",
        "description": "Operational group (red/blue) with doctrine and reinforcement posture.",
        "icon": "shield",
        "properties_schema": {
            "side": "string", "doctrine": "string", "reinforcement": "number",
            "theater": "string", "lat": "number", "lng": "number",
            "avg_remaining_pct": "number", "collapses": "number",
        },
    },
    ASSESSMENT_TYPE: {
        "display_name": "Battle Assessment",
        "description": "One Monte Carlo simulation run over a theater with outcome distribution.",
        "icon": "activity",
        "properties_schema": {
            "mode": "string", "terrain": "string", "scenarios_run": "number",
            "red_wins": "number", "blue_wins": "number", "stalemates": "number",
            "decisive_battles": "number", "convergence_rate": "number",
            "red_win_pct": "number", "blue_win_pct": "number",
            "avg_red_casualties": "number", "avg_blue_casualties": "number",
            "avg_duration_hours": "number", "dominant_winner": "string",
            "seed": "number", "duration_ms": "number", "executed_at": "string",
            "lat": "number", "lng": "number",
            "source_event_id": "string", "source_event_title": "string",
            "source_country": "string",
        },
    },
}

_WAR_LINK_TYPES = [
    # (name, display_name, source_type, target_type, description)
    (LT_LOCATED_IN, "Located In", FORCE_TYPE, THEATER_TYPE,
     "Force is deployed in the theater."),
    (LT_ASSESSED_IN, "Assessed In", ASSESSMENT_TYPE, THEATER_TYPE,
     "Battle assessment was run against the theater."),
    (LT_OPPOSES, "Opposes", FORCE_TYPE, FORCE_TYPE,
     "Red/blue matchup evaluated by an assessment."),
]

_ACTION_TYPES = [
    # (name, display_name, bound_type, description, parameters_schema, effects)
    (AT_RUN_BATTLE, "Run Kriegspiel Battle", THEATER_TYPE,
     "Executes a Monte Carlo battle batch through the sims gateway and emits "
     "force/assessment objects linked to this theater.",
     {"scenarios": "integer(100..50000)", "seed": "integer"},
     [{"effect": "emit_assessment"}, {"effect": "upsert_forces"},
      {"effect": "link_to_theater"}]),
]


def _slug(name: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


async def ensure_war_ontology(db: AsyncSession) -> dict:
    """Idempotently create the war ontology types. Safe to call on every emit."""
    svc = OntologyService(db)
    created = []

    types: dict[str, ObjectType] = {}
    for name, spec in _WAR_OBJECT_TYPES.items():
        t = await svc.get_object_type_by_name(name)
        if t is None:
            t = await svc.create_object_type(
                name=name, display_name=spec["display_name"],
                description=spec["description"],
                properties_schema=spec["properties_schema"], icon=spec["icon"])
            created.append(name)
        types[name] = t

    existing_lts = (await db.execute(select(LinkType))).scalars().all()
    lt_index = {(lt.name, str(lt.source_type_id), str(lt.target_type_id)) for lt in existing_lts}
    link_types: dict[str, LinkType] = {}
    for name, display, src, tgt, desc in _WAR_LINK_TYPES:
        key = (name, str(types[src].id), str(types[tgt].id))
        if key not in lt_index:
            await svc.create_link_type(
                name=name, display_name=display,
                source_type_id=types[src].id, target_type_id=types[tgt].id,
                description=desc)
            created.append(name)
        else:
            for lt in existing_lts:
                if lt.name == name and str(lt.source_type_id) == str(types[src].id):
                    link_types[name] = lt
                    break

    existing_ats = (await db.execute(
        select(ActionType).where(ActionType.name == AT_RUN_BATTLE))).scalars().all()
    if not existing_ats:
        await svc.create_action_type(
            name=AT_RUN_BATTLE, display_name=_ACTION_TYPES[0][1],
            object_type_id=types[THEATER_TYPE].id,
            description=_ACTION_TYPES[0][3],
            parameters_schema=_ACTION_TYPES[0][4], effects=_ACTION_TYPES[0][5])
        created.append(AT_RUN_BATTLE)

    return {"ensured": True, "created": created,
            "object_types": {k: str(v.id) for k, v in types.items()}}


async def _ensure_link(db: AsyncSession, link_type_id, source_id, target_id,
                       properties: dict | None = None) -> bool:
    row = (await db.execute(
        select(Link).where(
            Link.link_type_id == str(link_type_id),
            Link.source_object_id == str(source_id),
            Link.target_object_id == str(target_id),
        ))).scalar_one_or_none()
    if row is not None:
        return False
    db.add(Link(link_type_id=str(link_type_id), source_object_id=str(source_id),
                target_object_id=str(target_id), properties=properties or {}))
    await db.flush()
    return True


async def _upsert_war_object(db: AsyncSession, type_id, pk: str,
                             properties: dict) -> tuple[Object, bool]:
    """Create-or-merge a war object keyed by its primary key."""
    obj = (await db.execute(
        select(Object).where(
            Object.object_type_id == str(type_id),
            Object.primary_key_value == pk))).scalar_one_or_none()
    if obj is None:
        obj = Object(object_type_id=str(type_id), primary_key_value=pk,
                     properties=properties, created_by="sims-suite")
        db.add(obj)
        await db.flush()
        return obj, True
    obj.properties = {**(obj.properties or {}), **properties}
    obj.updated_by = "sims-suite"
    await db.flush()
    return obj, False


async def emit_battle_report(db: AsyncSession, report: dict, mode: str = "battle",
                             source_event: dict | None = None) -> dict:
    """
    Persist a gateway battle/campaign report as ontology objects + links.
    Never raises into the sim path — callers wrap this best-effort.
    """
    await ensure_war_ontology(db)
    svc = OntologyService(db)

    bf_meta = report.get("_battlefield") or {}
    theater_name = report.get("battlefield") or bf_meta.get("name") or "unknown-theater"
    terrain = bf_meta.get("terrain", "open")
    bounds = bf_meta.get("bounds")
    if bounds and len(bounds) == 4:
        w, s, e, n = bounds
        lat = round((s + n) / 2.0, 5)
        lng = round((w + e) / 2.0, 5)
    else:
        lat = lng = None
    t_pk = f"ks-theater:{_slug(theater_name)}"

    created = updated = links_created = 0

    prev_assessments = 0
    theater_obj = (await db.execute(
        select(Object).where(Object.primary_key_value == t_pk))).scalar_one_or_none()
    if theater_obj is not None:
        prev_assessments = int((theater_obj.properties or {}).get("assessments") or 0)

    theater_props = {
        "name": theater_name, "terrain": terrain,
        "assessments": prev_assessments + 1, "last_assessed_at": _now_iso(),
    }
    if lat is not None:
        theater_props.update({"lat": lat, "lng": lng})
    if bounds:
        theater_props["bounds"] = list(bounds)

    theater, was_new = await _upsert_war_object(
        db, (await svc.get_object_type_by_name(THEATER_TYPE)).id, t_pk, theater_props)
    created += was_new
    updated += not was_new

    # ---- forces -------------------------------------------------------------
    best = report.get("best_branch") or {}
    camp = report.get("reinforcement") is not None
    red_doc = (best.get("red_doctrine")
               or report.get("_red_doctrine") or "maneuver")
    blue_doc = (best.get("blue_doctrine")
                or report.get("_blue_doctrine") or "defensive")
    reinf = report.get("reinforcement") or {}
    remaining = {
        "red": report.get("avg_red_remaining_pct"),
        "blue": report.get("avg_blue_remaining_pct"),
    }
    collapses = report.get("collapses") or {}

    ftype = (await svc.get_object_type_by_name(FORCE_TYPE)).id
    lts = {lt.name: lt for lt in (await db.execute(
        select(LinkType).where(LinkType.name.in_(
            [LT_LOCATED_IN, LT_ASSESSED_IN, LT_OPPOSES])))).scalars().all()}

    forces: dict[str, Object] = {}
    for side, doc in (("red", red_doc), ("blue", blue_doc)):
        props = {
            "side": side, "doctrine": doc, "theater": theater_name,
        }
        if reinf.get(side) is not None:
            props["reinforcement"] = reinf.get(side)
        if remaining.get(side) is not None:
            props["avg_remaining_pct"] = remaining[side]
        if collapses.get(side) is not None:
            props["collapses"] = collapses[side]
        if lat is not None:
            offset = -0.05 if side == "red" else 0.05
            props.update({"lat": round(lat + offset, 5), "lng": lng})
        force, was_new = await _upsert_war_object(
            db, ftype, f"ks-force:{_slug(theater_name)}:{side}", props)
        forces[side] = force
        created += was_new
        updated += not was_new
        links_created += await _ensure_link(
            db, lts[LT_LOCATED_IN].id, force.id, theater.id,
            {"doctrine": doc})

    links_created += await _ensure_link(
        db, lts[LT_OPPOSES].id, forces["red"].id, forces["blue"].id,
        {"matchup": f"{red_doc} vs {blue_doc}", "theater": theater_name})

    # ---- assessment (event object) ------------------------------------------
    decided = int(report.get("red_wins") or 0) + int(report.get("blue_wins") or 0)
    red_pct = round(100 * report.get("red_wins", 0) / decided, 1) if decided else 0.0
    blue_pct = round(100 * report.get("blue_wins", 0) / decided, 1) if decided else 0.0
    dominant = ("red" if red_pct >= blue_pct else "blue") if decided else "stalemate"

    assess_props = {
        "mode": mode,
        "terrain": terrain,
        "scenarios_run": report.get("scenarios_run") or report.get("campaigns"),
        "red_wins": report.get("red_wins"), "blue_wins": report.get("blue_wins"),
        "stalemates": report.get("stalemates"),
        "decisive_battles": report.get("decisive_battles"),
        "convergence_rate": report.get("convergence_rate"),
        "red_win_pct": red_pct, "blue_win_pct": blue_pct,
        "avg_red_casualties": report.get("avg_red_casualties"),
        "avg_blue_casualties": report.get("avg_blue_casualties"),
        "avg_duration_hours": report.get("avg_duration_hours"),
        "avg_engagements": report.get("avg_engagements"),
        "front_final_pct": report.get("avg_front_final_pct"),
        "dominant_winner": dominant,
        "seed": report.get("seed"), "duration_ms": report.get("duration_ms"),
        "executed_at": _now_iso(),
        "matchup": f"{red_doc} vs {blue_doc}",
    }
    if lat is not None:
        assess_props.update({"lat": lat, "lng": lng})
    if source_event:
        assess_props.update({
            "source_event_id": str(source_event.get("id") or ""),
            "source_event_title": str(source_event.get("title") or "")[:200],
            "source_country": str(source_event.get("country") or ""),
        })

    atype = (await svc.get_object_type_by_name(ASSESSMENT_TYPE)).id
    assessment, was_new = await _upsert_war_object(
        db, atype, f"ks-assessment:{uuid.uuid4()}", assess_props)
    created += was_new

    links_created += await _ensure_link(
        db, lts[LT_ASSESSED_IN].id, assessment.id, theater.id,
        {"mode": mode, "dominant_winner": dominant})

    return {
        "emitted": True,
        "objects_created": created,
        "objects_updated": updated,
        "links_created": links_created,
        "objects": {
            "theater": str(theater.id),
            "assessment": str(assessment.id),
            "red_force": str(forces["red"].id),
            "blue_force": str(forces["blue"].id),
        },
        "primary_keys": {
            "theater": t_pk,
            "assessment": assessment.primary_key_value,
        },
        "dominant_winner": dominant,
    }


async def record_action_execution(db: AsyncSession, theater_object_id: str | None,
                                  parameters: dict, result: dict,
                                  executed_by: str | None) -> None:
    """Record a COMPLETED kriegspiel_run_battle execution (real kinetics)."""
    at = (await db.execute(
        select(ActionType).where(ActionType.name == AT_RUN_BATTLE))).scalar_one_or_none()
    if at is None:
        return
    exec_row = await OntologyService(db).execute_action(
        at.id, object_id=theater_object_id, parameters=parameters,
        executed_by=executed_by or "sims-suite")
    exec_row.status = "succeeded"
    exec_row.result = result
    exec_row.completed_at = datetime.now(timezone.utc)


async def graph_snapshot(db: AsyncSession, limit: int = 400) -> dict:
    """Nodes + edges for map rendering of the war ontology subgraph."""
    type_names = (await db.execute(
        select(ObjectType).where(ObjectType.name.in_(list(_WAR_OBJECT_TYPES)))
    )).scalars().all()
    tid_map = {str(t.id): t.name for t in type_names}
    nodes = (await db.execute(
        select(Object).where(Object.object_type_id.in_(list(tid_map)))
        .order_by(Object.created_at.desc()).limit(limit))).scalars().all()

    node_ids = [n.id for n in nodes]
    edges = []
    if node_ids:
        all_links = (await db.execute(
            select(Link).where(Link.source_object_id.in_(
                [str(i) for i in node_ids])))).scalars().all()
        keep = {str(i) for i in node_ids}
        edges = [l for l in all_links if str(l.target_object_id) in keep]
        lt_rows = (await db.execute(
            select(LinkType).where(LinkType.id.in_(
                [str(l.link_type_id) for l in edges])))).scalars().all()
        lt_names = {str(lt.id): lt.name for lt in lt_rows}
        edges = [{
            "id": str(l.id), "link_type": lt_names.get(str(l.link_type_id)),
            "source": str(l.source_object_id), "target": str(l.target_object_id),
            "properties": l.properties or {},
        } for l in edges]

    return {
        "nodes": [{
            "id": str(n.id),
            "type": tid_map.get(str(n.object_type_id)),
            "pk": n.primary_key_value,
            "properties": n.properties or {},
            "created_at": n.created_at.isoformat() if n.created_at else None,
        } for n in nodes],
        "edges": edges,
        "counts": {
            "nodes": len(nodes), "edges": len(edges),
            "by_type": {name: sum(1 for n in nodes if tid_map.get(str(n.object_type_id)) == name)
                        for name in _WAR_OBJECT_TYPES},
        },
    }