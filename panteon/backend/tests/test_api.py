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
    response = await client.get("/api/v1/ono/providers")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_list_agents(client):
    response = await client.get("/api/v1/ono/agents")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
