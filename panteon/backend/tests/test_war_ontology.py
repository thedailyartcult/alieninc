import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from panteon.core.database import get_db, Base
from panteon.main import app
from panteon.api import routes_sims
from panteon.core.auth import SupabaseUser
from panteon.war_ontology import (
    ASSESSMENT_TYPE,
    AT_RUN_BATTLE,
    FORCE_TYPE,
    THEATER_TYPE,
    emit_battle_report,
    ensure_war_ontology,
    graph_snapshot,
)

BATTLE_REPORT = {
    "battlefield": "Taiwan Strait",
    "scenarios_run": 500,
    "red_wins": 81,
    "blue_wins": 419,
    "stalemates": 0,
    "decisive_battles": 480,
    "convergence_rate": 0.62,
    "avg_red_casualties": 50.8,
    "avg_blue_casualties": 24.3,
    "avg_duration_hours": 36.2,
    "duration_ms": 900,
    "seed": 42,
    "best_branch": {"winner": "blue", "score": 0.8, "key_event": "naval interdiction",
                    "duration_hours": 30.1, "red_casualties_pct": 48.0,
                    "blue_casualties_pct": 20.0,
                    "red_doctrine": "attrition", "blue_doctrine": "defensive"},
    "_battlefield": {"name": "Taiwan Strait", "terrain": "coastal",
                     "bounds": [118, 22, 124, 27]},
}


@pytest.fixture(autouse=True)
async def war_db():
    """Point get_db at a throwaway in-memory SQLite with the sc_* tables."""
    engine = create_async_engine("sqlite+aiosqlite://")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    state = {"tables": False}

    async def ensure_tables():
        if not state["tables"]:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            state["tables"] = True

    async def _fake_db():
        await ensure_tables()
        async with session_factory() as session:
            yield session
            await session.commit()

    app.dependency_overrides[get_db] = _fake_db
    session_factory.ensure_tables = ensure_tables
    yield session_factory
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
async def db_session(war_db):
    await war_db.ensure_tables()
    async with war_db() as session:
        yield session


@pytest.mark.asyncio
async def test_ensure_war_ontology_idempotent(db_session):
    first = await ensure_war_ontology(db_session)
    second = await ensure_war_ontology(db_session)
    assert set(first["object_types"]) == {THEATER_TYPE, FORCE_TYPE, ASSESSMENT_TYPE}
    assert second["created"] == []  # nothing new on second call


@pytest.mark.asyncio
async def test_emit_creates_linked_objects(db_session):
    summary = await emit_battle_report(db_session, BATTLE_REPORT)
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
async def test_emit_updates_theater_not_duplicate(db_session):
    await emit_battle_report(db_session, dict(BATTLE_REPORT))
    second = await emit_battle_report(db_session, dict(BATTLE_REPORT))
    # theater + forces updated (not created), only the assessment is new
    assert second["objects_created"] == 1
    assert second["objects_updated"] == 3
    snap = await graph_snapshot(db_session)
    assert snap["counts"]["by_type"][THEATER_TYPE] == 1
    assert snap["counts"]["by_type"][ASSESSMENT_TYPE] == 2


@pytest.mark.asyncio
async def test_emit_with_source_event_provenance(db_session):
    src = {"id": "gkg-123", "title": "Naval standoff reported", "country": "Taiwan"}
    summary = await emit_battle_report(
        db_session, dict(BATTLE_REPORT), mode="flashpoint", source_event=src)
    assert summary["emitted"]
    snap = await graph_snapshot(db_session)
    assessment = next(n for n in snap["nodes"] if n["type"] == ASSESSMENT_TYPE)
    assert assessment["properties"]["source_event_id"] == "gkg-123"
    assert assessment["properties"]["mode"] == "flashpoint"


@pytest.mark.asyncio
async def test_kriegspiel_run_route_emits(monkeypatch, war_db):
    from httpx import AsyncClient as HC

    async def fake_gateway(method, path, request=None, json_body=None):
        assert method == "POST" and path == "kriegspiel/run"
        return dict(BATTLE_REPORT)

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
