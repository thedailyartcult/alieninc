import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from panteon.core.database import get_db, Base
from panteon.main import app
from panteon.api import routes_sims
from panteon.core.auth import SupabaseUser
from panteon.war_ontology import (
    ARSENAL_SYSTEM_TYPE,
    ASSESSMENT_TYPE,
    AT_RUN_BATTLE,
    FORCE_TYPE,
    THEATER_TYPE,
    WORLD_COUNTRY_TYPE,
    emit_battle_report,
    ensure_war_ontology,
    graph_snapshot,
)



@pytest.mark.asyncio
async def test_ensure_war_ontology_idempotent(db_session):
    first = await ensure_war_ontology(db_session)
    second = await ensure_war_ontology(db_session)
    assert set(first["object_types"]) >= {THEATER_TYPE, FORCE_TYPE, ASSESSMENT_TYPE,
                                           WORLD_COUNTRY_TYPE, ARSENAL_SYSTEM_TYPE}
    assert second["created"] == []  # nothing new on second call


@pytest.mark.asyncio
async def test_emit_creates_linked_objects(db_session, battle_report):
    summary = await emit_battle_report(db_session, battle_report)
    assert summary["emitted"] is True
    assert summary["objects_created"] == 4  # theater + red + blue + assessment
    assert summary["links_created"] == 4  # located x2 + assessed_in + opposes
    snap = await graph_snapshot(db_session)
    by_type = snap["counts"]["by_type"]
    assert by_type[THEATER_TYPE] == 1
    assert by_type[FORCE_TYPE] == 2
    assert by_type[ASSESSMENT_TYPE] == 1
    assert snap["counts"]["edges"] == 4

    theater = next(n for n in snap["nodes"] if n["type"] == THEATER_TYPE)
    # center of bounds [118, 22, 124, 27]
    assert theater["properties"]["lat"] == 24.5
    assert theater["properties"]["lng"] == 121.0
    assessment = next(n for n in snap["nodes"] if n["type"] == ASSESSMENT_TYPE)
    assert assessment["properties"]["dominant_winner"] == "blue"
    assert abs(assessment["properties"]["blue_win_pct"] - 83.8) < 0.2


@pytest.mark.asyncio
async def test_emit_updates_theater_not_duplicate(db_session, battle_report):
    await emit_battle_report(db_session, dict(battle_report))
    second = await emit_battle_report(db_session, dict(battle_report))
    # theater + forces updated (not created), only the assessment is new
    assert second["objects_created"] == 1
    assert second["objects_updated"] == 3
    snap = await graph_snapshot(db_session)
    assert snap["counts"]["by_type"][THEATER_TYPE] == 1
    assert snap["counts"]["by_type"][ASSESSMENT_TYPE] == 2


@pytest.mark.asyncio
async def test_emit_with_source_event_provenance(db_session, battle_report):
    src = {"id": "gkg-123", "title": "Naval standoff reported", "country": "Taiwan"}
    summary = await emit_battle_report(
        db_session, dict(battle_report), mode="flashpoint", source_event=src)
    assert summary["emitted"]
    snap = await graph_snapshot(db_session)
    assessment = next(n for n in snap["nodes"] if n["type"] == ASSESSMENT_TYPE)
    assert assessment["properties"]["source_event_id"] == "gkg-123"
    assert assessment["properties"]["mode"] == "flashpoint"


@pytest.mark.asyncio
async def test_kriegspiel_run_route_emits(monkeypatch, war_db, battle_report):
    from httpx import AsyncClient as HC

    async def fake_gateway(method, path, request=None, json_body=None):
        assert method == "POST" and path == "kriegspiel/run"
        return dict(battle_report)

    monkeypatch.setattr(routes_sims, "_gateway", fake_gateway)

    async def fake_user():
        return SupabaseUser(user_id="u1", email="war@alieninc.tech", role="editor")

    app.dependency_overrides[routes_sims.get_current_user] = fake_user
    transport = ASGITransport(app=app)
    try:
        async with HC(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/sims/kriegspiel/run",
                json={"battlefield": "Taiwan Strait", "scenarios": 500, "seed": 42})
    finally:
        app.dependency_overrides.pop(routes_sims.get_current_user, None)

    assert resp.status_code == 200
    body = resp.json()
    assert body["battlefield"] == "Taiwan Strait"
    assert body["ontology"]["emitted"] is True
    assert body["ontology"]["objects_created"] == 4
