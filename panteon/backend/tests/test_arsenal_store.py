import json
import os

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from panteon import arsenal_sync
from panteon.arsenal_sync import run_sync, link_ontology
from panteon.core.auth import SupabaseUser
from panteon.main import app


CATALOG = {
    "schema_version": 1,
    "generated": "2026-08-24T00:00:00+00:00",
    "categories": ["Aircraft", "UAVs"],
    "category_keys": ["aircraft", "uavs"],
    "total_entries": 3,
    "entry_counts": {"aircraft": 2, "uavs": 1},
    "entries": {
        "aircraft": [
            {"designation": "F-16 Fighting Falcon", "alt_names": ["F-16"],
             "country": "United States", "manufacturer": "Lockheed Martin",
             "category": "Aircraft", "description": "Multirole fighter.",
             "specs": ["Role: Multirole Fighter"],
             "sources": [{"label": "Test", "url": "https://example.com/a"}],
             "fetched_at": "2026-08-20T00:00:00+00:00"},
            {"designation": "Rafale", "alt_names": [],
             "country": "France", "manufacturer": "Dassault",
             "category": "Aircraft", "description": "Omnirole fighter.",
             "specs": [], "sources": [], "fetched_at": None},
        ],
        "uavs": [
            {"designation": "Bayraktar TB2", "alt_names": ["TB2"],
             "country": "Turkey", "manufacturer": "Baykar",
             "category": "UAVs", "description": "MALE UCAV.",
             "specs": [], "sources": [],
             "fetched_at": "2026-08-21T00:00:00+00:00"},
        ],
    },
}


@pytest.fixture
def catalog_file(tmp_path):
    """Small synthetic a-san catalog + sync wired to a throwaway DB."""
    path = tmp_path / "catalog-data.json"
    path.write_text(json.dumps(CATALOG))
    orig_path = arsenal_sync.arsenal_mod.CATALOG_PATH
    arsenal_sync.arsenal_mod.CATALOG_PATH = str(path)
    engine = create_async_engine("sqlite+aiosqlite://")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    orig_engine, orig_session = arsenal_sync.engine, arsenal_sync.async_session
    arsenal_sync.engine = engine
    arsenal_sync.async_session = factory
    yield path
    arsenal_sync.engine, arsenal_sync.async_session = orig_engine, orig_session
    arsenal_sync.arsenal_mod.CATALOG_PATH = orig_path


@pytest.mark.asyncio
async def test_sync_idempotent(catalog_file):
    first = await run_sync()
    assert first["ok"] and first["added"] == 3 and first["updated"] == 0
    second = await run_sync()
    assert second["ok"] and second["unchanged"] == 3
    assert second["added"] == 0 and second["updated"] == 0


@pytest.mark.asyncio
async def test_sync_retires_without_deleting(catalog_file):
    await run_sync()
    data = json.loads(catalog_file.read_text())
    data["entries"]["aircraft"] = [
        e for e in data["entries"]["aircraft"] if e["designation"] != "Rafale"]
    catalog_file.write_text(json.dumps(data))
    out = await run_sync()
    assert out["retired"] == 1
    from panteon.arsenal_store import ArsItem
    async with arsenal_sync.async_session() as db:
        total = (await db.execute(
            select(func.count()).select_from(ArsItem))).scalar_one()
        active = (await db.execute(
            select(func.count()).select_from(ArsItem)
            .where(ArsItem.active.is_(True)))).scalar_one()
    assert total == 3 and active == 2   # row kept, flag flipped


@pytest.mark.asyncio
async def test_link_ontology_matches_flagship_pks(catalog_file):
    from panteon.spinal_craker.models import Object, ObjectType
    from panteon.arsenal_store import ArsOntologyLink, ontology_pk
    await run_sync()
    async with arsenal_sync.async_session() as db:
        ot = ObjectType(name="arsenal_system", display_name="ARSENAL")
        pk = ontology_pk("aircraft", "F-16 Fighting Falcon")
        obj = Object(object_type=ot, primary_key_value=pk, properties={})
        db.add(obj)
        await db.commit()
        out = await link_ontology(db)
        assert out["linked"] == 1
        again = await link_ontology(db)
        assert again["linked"] == 0
        links = (await db.execute(
            select(ArsOntologyLink))).scalars().all()
        assert len(links) == 1


@pytest.fixture
async def api_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport,
                           base_url="http://test") as c:
        yield c


def _override_auth():
    from panteon.api import routes_arsenal

    async def fake_user():
        return SupabaseUser(user_id="u1", email="m@alieninc.tech", role="viewer")
    app.dependency_overrides[routes_arsenal.get_current_user] = fake_user


@pytest.mark.asyncio
async def test_arsenal_api_requires_auth(api_client):
    response = await api_client.get("/api/v1/arsenal/categories")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_arsenal_api_categories_and_compare(api_client, tmp_path):
    """API + sync share ONE throwaway engine so the endpoints see the import."""
    from panteon.core.database import get_db

    path = tmp_path / "catalog-data.json"
    path.write_text(json.dumps(CATALOG))
    orig_path = arsenal_sync.arsenal_mod.CATALOG_PATH
    orig_engine, orig_session = arsenal_sync.engine, arsenal_sync.async_session
    engine = create_async_engine("sqlite+aiosqlite://")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    arsenal_sync.arsenal_mod.CATALOG_PATH = str(path)
    arsenal_sync.engine = engine
    arsenal_sync.async_session = factory

    async def _fake_db():
        async with factory() as session:
            yield session
            await session.commit()

    app.dependency_overrides[get_db] = _fake_db
    _override_auth()
    try:
        assert (await run_sync())["added"] == 3
        r = await api_client.get("/api/v1/arsenal/categories")
        body = r.json()
        assert r.status_code == 200
        assert body["total_active"] == 3
        icons = {c["key"]: c["icon_path"] for c in body["categories"]}
        assert icons["aircraft"].endswith("aircraft.png")

        r = await api_client.get("/api/v1/arsenal/items?q=falcon")
        entries = r.json()["entries"]
        assert len(entries) == 1 and entries[0]["designation"].startswith("F-16")
        assert entries[0]["specs_parsed"], "specs must be parsed for admin UI"

        r = await api_client.get(
            "/api/v1/arsenal/capabilities/compare?countries=USA,France,Turkey")
        comp = r.json()["comparison"]
        by_c = {c["country"]: c["counts"] for c in comp}
        assert by_c["United States"]["aircraft"] == 1
        assert by_c["France"]["aircraft"] == 1
        leaders = r.json()["leader_per_category"]
        assert leaders["aircraft"] == "United States"   # first max wins ties
        assert leaders["uavs"] == "Turkey"
    finally:
        from panteon.api import routes_arsenal
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(routes_arsenal.get_current_user, None)
        arsenal_sync.arsenal_mod.CATALOG_PATH = orig_path
        arsenal_sync.engine, arsenal_sync.async_session = orig_engine, orig_session
