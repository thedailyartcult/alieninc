import pytest
from httpx import AsyncClient, ASGITransport
from panteon.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_root(client):
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Panteon"
    assert "spinal_craker" in data["platforms"]
    assert "ono" in data["platforms"]


@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_list_object_types(client):
    response = await client.get("/api/v1/spinal-craker/object-types")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_list_providers(client):
    response = await client.get("/api/v1/yono/providers")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_list_agents(client):
    response = await client.get("/api/v1/yono/agents")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_research_requires_auth(client):
    response = await client.get("/api/v1/research/the-founding-charter")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_research_bad_slug(client):
    response = await client.get("/api/v1/research/../../etc/passwd")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_research_missing_article(client, monkeypatch):
    from panteon.api import routes_research
    from panteon.core.auth import SupabaseUser

    async def fake_user():
        return SupabaseUser(user_id="u1", email="member@alieninc.tech", role="viewer")

    app.dependency_overrides[routes_research.get_current_user] = fake_user
    try:
        response = await client.get("/api/v1/research/does-not-exist")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_research_returns_article(client, monkeypatch, tmp_path):
    from panteon.api import routes_research
    from panteon.core.auth import SupabaseUser

    (tmp_path / "the-founding-charter.json").write_text(
        '{"slug":"the-founding-charter","title":"The Founding","date":"2016-12-22",'
        '"author":"Patrick Neil A.","html":"<h2>Charter</h2><p>Body.</p>"}',
        encoding="utf-8",
    )

    async def fake_user():
        return SupabaseUser(user_id="u1", email="member@alieninc.tech", role="viewer")

    monkeypatch.setattr(routes_research, "_locked_dir", lambda: tmp_path)
    app.dependency_overrides[routes_research.get_current_user] = fake_user
    try:
        response = await client.get("/api/v1/research/the-founding-charter")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    data = response.json()
    assert data["slug"] == "the-founding-charter"
    assert data["title"] == "The Founding"
    assert "<p>Body.</p>" in data["html"]
