import json as _json

import pytest
from httpx import AsyncClient, ASGITransport

from panteon.main import app
from panteon.api import routes_sims
from panteon.core.auth import SupabaseUser


class FakeGatewayResponse:
    def __init__(self, content: bytes):
        self.status_code = 200
        self.content = content
        self.headers = {"content-type": "application/json"}


class FakeGatewayClient:
    last_url = None
    last_body = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, headers=None, params=None):
        type(self).last_url = url
        return FakeGatewayResponse(_json.dumps({"battlefields": [], "via": url}).encode())

    async def request(self, method, url, headers=None, params=None, content=None, json=None):
        type(self).last_url = url
        type(self).last_body = content if json is None else _json.dumps(json)
        return FakeGatewayResponse(_json.dumps({"changes_applied": 1}).encode())


@pytest.fixture(autouse=True)
def _reset_fake_gateway():
    FakeGatewayClient.last_url = None
    FakeGatewayClient.last_body = None
    yield
    FakeGatewayClient.last_url = None
    FakeGatewayClient.last_body = None


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _override_role(role):
    async def fake_user():
        return SupabaseUser(user_id="u1", email="member@alieninc.tech", role=role)

    app.dependency_overrides[routes_sims.get_current_user] = fake_user


@pytest.mark.asyncio
async def test_sims_requires_auth(client):
    response = await client.get("/api/v1/sims/health")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_sims_get_proxies_to_gateway(client, monkeypatch):
    monkeypatch.setattr(routes_sims.httpx, "AsyncClient", FakeGatewayClient)
    _override_role("viewer")
    try:
        response = await client.get("/api/v1/sims/kriegspiel/battlefields")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["changes_applied"] == 1
    assert FakeGatewayClient.last_url == "http://localhost:8090/api/kriegspiel/battlefields"


@pytest.mark.asyncio
async def test_sims_improve_forbidden_for_viewer(client, monkeypatch):
    monkeypatch.setattr(routes_sims.httpx, "AsyncClient", FakeGatewayClient)
    _override_role("viewer")
    try:
        response = await client.post("/api/v1/sims/research/improve")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 403
    assert FakeGatewayClient.last_url is None


@pytest.mark.asyncio
async def test_sims_improve_allowed_for_editor(client, monkeypatch):
    monkeypatch.setattr(routes_sims.httpx, "AsyncClient", FakeGatewayClient)
    _override_role("editor")
    try:
        response = await client.post("/api/v1/sims/research/improve", json={})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["changes_applied"] == 1
    assert FakeGatewayClient.last_url == "http://localhost:8090/api/research/improve"
