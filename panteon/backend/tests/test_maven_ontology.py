"""MAVEN Smart Layer tests — ontology types, tasking loop, detections from
REAL tracks (monkeypatched store), COA scoring through a faked sims gateway."""
import time
import uuid

import pytest

from panteon import maven as mv
from panteon.main import app
from panteon.core.auth import SupabaseUser
from panteon.war_ontology import THEATER_TYPE, graph_snapshot
from panteon.maven import (
    ASSET_TYPE,
    COA_TYPE,
    DET_TYPE,
    TASK_TYPE,
    create_task,
    delete_task,
    dispatch_asset,
    ensure_maven_ontology,
    generate_coas,
    prune_detections,
    recall_asset,
    tick_and_collect,
    validate_detection,
)


@pytest.fixture(autouse=True)
def _reset_engine_state():
    mv._ASSETS.clear()
    mv._LAST_DET.clear()
    yield
    mv._ASSETS.clear()
    mv._LAST_DET.clear()


@pytest.mark.asyncio
async def test_ensure_maven_ontology_idempotent(db_session):
    first = await ensure_maven_ontology(db_session)
    assert set(first["object_types"]) >= {TASK_TYPE, ASSET_TYPE, DET_TYPE, COA_TYPE}
    second = await ensure_maven_ontology(db_session)
    assert not any(str(c).startswith(("maven_", "mv_")) for c in second["created"])


@pytest.mark.asyncio
async def test_create_task_links_to_theater(db_session):
    res = await create_task(db_session, {
        "name": "BALTIC PICKET", "aoi_lat": 58.4, "aoi_lng": 20.1,
        "aoi_radius_km": 40, "priority": "high",
        "detection_classes": ["military-air"],
    }, "op@alieninc.tech")
    snap = await graph_snapshot(db_session)
    by_type = snap["counts"]["by_type"]
    assert by_type[TASK_TYPE] == 1
    assert by_type[THEATER_TYPE] >= 1
    edges = [e for e in snap["edges"] if e["link_type"] == "mv_tasked_in"]
    assert len(edges) == 1


@pytest.mark.asyncio
async def test_dispatch_spawns_asset_and_records_action(db_session):
    task = await create_task(db_session, {
        "name": "GULF WATCH", "aoi_lat": 59.6, "aoi_lng": 24.8,
    }, "op@alieninc.tech")
    out = await dispatch_asset(db_session, task["task_id"], "uas", "op@alieninc.tech")
    assert out["callsign"].startswith("GHO-")
    assert out["eta_s"] > 0
    # Baltic AOI -> nearest named base (AMARI), not a FARP.
    assert out["origin"] == "AMARI"
    snap = await graph_snapshot(db_session)
    assert snap["counts"]["by_type"][ASSET_TYPE] == 1
    links = [e for e in snap["edges"] if e["link_type"] == "mv_assigned"]
    assert len(links) == 1
    with pytest.raises(ValueError):
        await dispatch_asset(db_session, str(uuid.uuid4()), "uas", None)
    with pytest.raises(ValueError):
        await dispatch_asset(db_session, task["task_id"], "submarine", None)


@pytest.mark.asyncio
async def test_dispatch_philippines_uses_regional_base(db_session):
    """Regression: tasks outside the Baltics must launch from a NEARBY base,
    not fly 9,000 km from Estonia."""
    task = await create_task(db_session, {
        "name": "LUZON WATCH", "aoi_lat": 16.7, "aoi_lng": 121.4,
    }, None)
    out = await dispatch_asset(db_session, task["task_id"], "uas", None)
    assert out["origin"] == "CLARK"          # nearest base to northern Luzon
    assert out["distance_km"] < 400          # short hop, not trans-continental


@pytest.mark.asyncio
async def test_dispatch_mid_ocean_spawns_farp(db_session):
    """No base within 600 km -> FARP beside the AOI keeps any theater playable."""
    task = await create_task(db_session, {
        "name": "MIDATL", "aoi_lat": 0.0, "aoi_lng": -30.0,
    }, None)
    out = await dispatch_asset(db_session, task["task_id"], "usv", None)
    assert out["origin"].startswith("FARP-")
    assert out["distance_km"] <= 600


def test_sim_speedup_pacing():
    """Sim clock runs SIM_SPEEDUPx faster than wall time."""
    speedup = mv.SIM_SPEEDUP
    dist_km = 100.0
    real_s = dist_km / (65.0 * 1.852) * 3600.0     # true flight time
    wall_expected = max(2, int(real_s / speedup))
    asset = {
        "callsign": "T", "asset_class": "uas",
        "origin": {"lat": 59.26, "lng": 24.48, "name": "AMARI"},
        "aoi": {"lat": 58.5, "lng": 20.0, "radius_km": 25.0},
        "launched_at": time.time(), "eta_s": wall_expected, "speedup": speedup,
        "task_pk": "x", "task_id": "y",
    }
    p0 = mv.asset_position(asset)                  # just launched -> at origin
    assert p0["state"] == "transit"
    near = dict(asset, launched_at=time.time() - wall_expected / 2)
    pmid = mv.asset_position(near)
    assert pmid["state"] == "transit"
    done = dict(asset, launched_at=time.time() - (wall_expected + 60) * 4)
    pdone = mv.asset_position(done)
    assert pdone["state"] == "on-station"


def test_asset_position_transit_then_orbit():
    asset = {
        "callsign": "T", "asset_class": "uas",
        "origin": {"lat": 59.26, "lng": 24.48, "name": "AMARI"},
        "aoi": {"lat": 58.5, "lng": 20.0, "radius_km": 25.0},
        "launched_at": time.time() - 10, "eta_s": 3600, "task_pk": "x",
        "task_id": "y",
    }
    transit = mv.asset_position(asset)
    assert transit["state"] == "transit"
    near = dict(asset, launched_at=time.time() - 7200)
    orbit = mv.asset_position(near)
    assert orbit["state"] == "on-station"


def test_classify_deterministic():
    mil = {"category": "military", "speed_kts": 380, "squawk": "7000"}
    civ_fast = {"category": "jet", "speed_kts": 480, "squawk": "1000"}
    plain = {"category": "commercial", "speed_kts": 300, "squawk": "1234"}
    assert mv._classify(mil, 5, 25)[0] == "military-air"
    assert mv._classify(civ_fast, 5, 25)[0] == "fast-mover"
    assert mv._classify(plain, 5, 25)[0] == "air-contact"
    c_close = mv._classify(mil, 2, 25)[1]
    c_far = mv._classify(mil, 24, 25)[1]
    assert c_close > c_far


@pytest.mark.asyncio
async def test_tick_generates_detections_from_real_tracks(db_session, monkeypatch):
    task = await create_task(db_session, {
        "name": "DETECT TEST", "aoi_lat": 58.0, "aoi_lng": 20.0,
        "aoi_radius_km": 50,
    }, "op@alieninc.tech")
    out = await dispatch_asset(db_session, task["task_id"], "uas", None)
    # Force on-station at AOI center.
    callsign = out["callsign"]
    mv._ASSETS[callsign]["launched_at"] = time.time() - 999999
    mv._ASSETS[callsign]["eta_s"] = 60
    pos = mv.asset_position(mv._ASSETS[callsign])

    def fake_tracks():
        return [
            {"source": "opensky", "track_id": "abc123", "lat": pos["lat"] + 0.05,
             "lng": pos["lng"] + 0.05, "label": "RCH123", "category": "military",
             "speed_kts": 420, "squawk": "7000"},
            {"source": "opensky", "track_id": "faraway", "lat": 40.0,
             "lng": 5.0, "label": "DLH441", "category": "commercial",
             "speed_kts": 430, "squawk": "1000"},
        ]

    monkeypatch.setattr(mv, "_live_tracks", fake_tracks)
    first = await tick_and_collect(db_session)
    assert first["new_detections"] == 1
    det = first["detections"][0]
    assert det["det_class"] == "military-air"
    assert det["track_id"] == "abc123"

    # Cooldown: immediate re-tick must NOT duplicate.
    second = await tick_and_collect(db_session)
    assert second["new_detections"] == 0

    # Expire cooldown -> same track again still one detection per key (update).
    mv._LAST_DET.clear()
    third = await tick_and_collect(db_session)
    assert third["new_detections"] == 1


@pytest.mark.asyncio
async def test_validate_writes_verdict(db_session):
    task = await create_task(db_session, {
        "aoi_lat": 58.0, "aoi_lng": 20.0}, "op@alieninc.tech")
    out = await dispatch_asset(db_session, task["task_id"], "usv", None)
    cs = out["callsign"]
    mv._ASSETS[cs]["launched_at"] = time.time() - 999999
    mv._ASSETS[cs]["eta_s"] = 1

    async def one_track():
        return [{"source": "opensky", "track_id": "zzz", "lat": 58.01,
                 "lng": 20.01, "label": "TEST1", "category": "jet",
                 "speed_kts": 450, "squawk": None}]
    import panteon.api.routes_opensky as ros  # noqa: F401 (import path sanity)
    orig = mv._live_tracks
    mv._live_tracks = lambda: [
        {"source": "opensky", "track_id": "zzz", "lat": 58.01, "lng": 20.01,
         "label": "TEST1", "category": "jet", "speed_kts": 450, "squawk": None}]
    try:
        await tick_and_collect(db_session)
    finally:
        mv._live_tracks = orig
    from sqlalchemy import select
    from panteon.spinal_craker.models import Object, ObjectType
    tid = (await db_session.execute(select(ObjectType).where(
        ObjectType.name == DET_TYPE))).scalars().one()
    obj = (await db_session.execute(select(Object).where(
        Object.object_type_id == str(tid.id)))).scalars().one()

    res = await validate_detection(db_session, str(obj.id), True, "qa@alieninc.tech")
    assert res["validated"] is True
    props = (await db_session.execute(
        select(Object).where(Object.id == obj.id))).scalars().one().properties
    assert props["validated"] is True and props["validated_by"] == "qa@alieninc.tech"


class FakeCoaClient:
    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json=None):
        class R:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "campaigns": json.get("campaigns"),
                    "campaign_wins": {"red": 120, "blue": 160, "stalemate": 20},
                    "avg_engagements": 1.5,
                    "avg_red_remaining_pct": 62.0,
                    "avg_blue_remaining_pct": 74.0,
                }
        return R()


@pytest.mark.asyncio
async def test_generate_coas_runs_real_simulations(db_session, monkeypatch):
    monkeypatch.setattr(mv.httpx, "AsyncClient", FakeCoaClient)
    res = await generate_coas(db_session, {"scenarios": 300, "seed": 7},
                              "op@alieninc.tech")
    codes = [c["code"] for c in res["coas"]]
    assert codes == ["BRAVO", "ALPHA", "CHARLIE"] or sorted(codes) == \
        ["ALPHA", "BRAVO", "CHARLIE"]
    ranks = [c["rank"] for c in res["coas"]]
    assert ranks == [1, 2, 3]
    overalls = [c["overall"] for c in res["coas"]]
    assert overalls == sorted(overalls, reverse=True)
    snap = await graph_snapshot(db_session)
    assert snap["counts"]["by_type"][COA_TYPE] == 3


@pytest.mark.asyncio
async def test_prune_honors_ttl(db_session):
    from datetime import datetime, timezone
    from sqlalchemy import select
    from panteon.spinal_craker.models import Object, ObjectType
    task = await create_task(db_session, {"aoi_lat": 58.0, "aoi_lng": 20.0}, None)
    out = await dispatch_asset(db_session, task["task_id"], "uas", None)
    cs = out["callsign"]
    mv._ASSETS[cs]["launched_at"] = time.time() - 999999
    mv._ASSETS[cs]["eta_s"] = 1
    old_iso = datetime.now(timezone.utc).fromtimestamp(
        time.time() - 30 * 86400).isoformat(timespec="seconds")

    def seeded():
        return [{"source": "opensky", "track_id": "old1", "lat": 58.02,
                 "lng": 20.02, "label": "OLD", "category": "military",
                 "speed_kts": 400, "squawk": "7000"}]
    orig = mv._live_tracks
    mv._live_tracks = seeded
    try:
        await tick_and_collect(db_session)
    finally:
        mv._live_tracks = orig

    tid = (await db_session.execute(select(ObjectType).where(
        ObjectType.name == DET_TYPE))).scalars().one()
    objs = (await db_session.execute(select(Object).where(
        Object.object_type_id == str(tid.id)))).scalars().all()
    assert len(objs) == 1
    objs[0].properties = {**(objs[0].properties or {}), "emitted_at": old_iso}
    from sqlalchemy.ext.asyncio import AsyncSession  # noqa: F401
    await db_session.commit()

    res = await prune_detections(db_session, ttl_days=14)
    assert res["pruned"] == 1
    remaining = (await db_session.execute(select(Object).where(
        Object.object_type_id == str(tid.id)))).scalars().all()
    assert remaining == []


# ------------------------------- API surface ------------------------------
class Unauth(Exception):
    pass


@pytest.fixture
async def api_client():
    from httpx import ASGITransport, AsyncClient
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        yield c


def _override_role(role):
    async def fake_user():
        if role is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=401, detail="unauthorized")
        return SupabaseUser(user_id="u1", email="m@alieninc.tech", role=role)
    app.dependency_overrides[mv_get_current_user()] = fake_user


def mv_get_current_user():
    from panteon.api.routes_maven import get_current_user
    return get_current_user


@pytest.mark.asyncio
async def test_api_requires_auth(api_client):
    resp = await api_client.get("/api/v1/maven/state")
    assert resp.status_code == 401


# --------------------------- operator control -----------------------------
@pytest.mark.asyncio
async def test_recall_asset_stands_down(db_session):
    task = await create_task(db_session, {
        "name": "RECALL ME", "aoi_lat": 58.0, "aoi_lng": 20.0}, "op@alieninc.tech")
    out = await dispatch_asset(db_session, task["task_id"], "uas", None)
    cs = out["callsign"]
    res = await recall_asset(db_session, cs, "op@alieninc.tech")
    assert res["recalled"] is True and res["object_removed"] is True
    assert cs not in mv._ASSETS
    with pytest.raises(ValueError):
        await recall_asset(db_session, "UAS-NOPE", None)


@pytest.mark.asyncio
async def test_delete_task_removes_assets_and_detections(db_session, monkeypatch):
    task = await create_task(db_session, {
        "name": "DEL TASK", "aoi_lat": 55.5, "aoi_lng": 19.4}, "op@alieninc.tech")
    a1 = await dispatch_asset(db_session, task["task_id"], "uas", None)
    a2 = await dispatch_asset(db_session, task["task_id"], "usv", None)

    # Seed two detections bound to this task + one foreign detection.
    from panteon.spinal_craker.models import Object as Obj, Link as LinkModel
    async def mk_det(pk, tid):
        svc = mv.OntologyService(db_session)
        dt = await svc.get_object_type_by_name(DET_TYPE)
        obj, _ = await mv._upsert_war_object(
            db_session, dt.id, pk,
            {"task_id": tid, "validated": None, "lat": 1.0, "lng": 2.0})
        return obj
    d_mine = await mk_det("mv-det:del-a", task["task_id"])
    d_mine2 = await mk_det("mv-det:del-b", task["task_id"])
    other = await create_task(db_session, {
        "name": "KEEP ME", "aoi_lat": 10.0, "aoi_lng": 10.0}, "op@alieninc.tech")
    d_other = await mk_det("mv-det:keep", other["task_id"])
    await db_session.commit()

    res = await delete_task(db_session, task["task_id"], "op@alieninc.tech")
    assert res["deleted"] is True and res["assets_stood_down"] == 2

    pks = {o.primary_key_value for o in (await db_session.execute(
        __import__("sqlalchemy").select(Obj))).scalars().all()}
    assert f"mv-asset:{a1['callsign']}" not in pks
    assert f"mv-asset:{a2['callsign']}" not in pks
    assert "mv-det:del-a" not in pks and "mv-det:del-b" not in pks
    assert "mv-det:keep" in pks
    assert other["pk"] in pks

    with pytest.raises(ValueError):
        await delete_task(db_session, str(uuid.uuid4()), None)


@pytest.mark.asyncio
async def test_delete_and_recall_routes_role_gated(api_client):
    _override_role("viewer")
    try:
        r = await api_client.delete("/api/v1/maven/task/" + str(uuid.uuid4()))
        assert r.status_code == 403
        c = await api_client.post("/api/v1/maven/asset/UAS-XXXX/recall", json={})
        assert c.status_code == 403
    finally:
        app.dependency_overrides.pop(mv_get_current_user(), None)


@pytest.mark.asyncio
async def test_api_role_gating(api_client):
    _override_role("viewer")
    try:
        r = await api_client.post("/api/v1/maven/task", json={})
        assert r.status_code == 403
    finally:
        app.dependency_overrides.pop(mv_get_current_user(), None)

    _override_role("editor")
    try:
        r = await api_client.post("/api/v1/maven/task", json={
            "name": "API TASK", "aoi_lat": 58.2, "aoi_lng": 19.9})
        assert r.status_code == 200
        body = r.json()
        assert body["pk"].startswith("mv-task:")
        s = await api_client.get("/api/v1/maven/state")
        assert s.status_code == 200
        names = [t["name"] for t in s.json()["tasks"]]
        assert "API TASK" in names
    finally:
        app.dependency_overrides.pop(mv_get_current_user(), None)


# ------------------------------- AIS relay --------------------------------
@pytest.mark.asyncio
async def test_ais_relay_rejects_unauthenticated():
    from fastapi.testclient import TestClient
    with TestClient(app) as tc:  # runs lifespan (init_db) on real engine config
        with pytest.raises(Exception):
            with tc.websocket_connect("/api/v1/maven/ais/ws?token=garbage"):
                pass
