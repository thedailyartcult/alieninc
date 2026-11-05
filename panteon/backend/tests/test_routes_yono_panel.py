"""YONO Panel (Spinal Cracker floating AIP assistant) — backend tests.

Covers: panel status/chat endpoints, seeded agent, propose+confirm flow,
governance denials, recent_objects ordering, map-directive echo tools.
"""

import json as _json
from datetime import datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from panteon.main import app
from panteon.core.auth import SupabaseUser
from panteon.api import routes_yono


# ── Fixtures (reuses conftest.war_db in-memory DB + get_db override) ─────


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _override_role(role="operator"):
    async def fake_user():
        return SupabaseUser(user_id="u1", email="op@alieninc.tech", role=role)
    app.dependency_overrides[routes_yono.get_current_user] = fake_user


async def _seed_llm_and_agent(war_db):
    """Provider + enabled Qwen3.8-27B model + the seeded YONO agent."""
    from panteon.yono.models import LLMProvider, LLMModel
    from panteon.yono.sc_agent_seed import ensure_sc_yono_agent

    await war_db.ensure_tables()
    async with war_db() as db:
        provider = LLMProvider(
            name="Hetzner", provider_type="openai",
            base_url="https://inference.hetzner.com/api/v1", is_enabled=True,
        )
        db.add(provider)
        await db.flush()
        model = LLMModel(
            provider_id=provider.id, model_id="Qwen3.8-27B",
            display_name="Qwen3.8-27B", is_enabled=True,
        )
        db.add(model)
        await db.flush()
        agent = await ensure_sc_yono_agent(db)
        await db.commit()
        return str(agent.id), str(model.id)


async def _seed_action_type(factory):
    """A kriegspiel_run_battle action type bound to kriegspiel_theater."""
    from panteon.spinal_craker.models import ObjectType, ActionType

    await factory.ensure_tables()
    async with factory() as db:
        obj_type = ObjectType(
            name="kriegspiel_theater", display_name="Theater")
        db.add(obj_type)
        await db.flush()
        action = ActionType(
            name="kriegspiel_run_battle", display_name="Run Battle",
            object_type_id=obj_type.id,
            parameters_schema={"required": ["battlefield"]},
            is_enabled=True,
        )
        db.add(action)
        await db.commit()
        return str(action.id)


class FakeLLM:
    """Scripted LLMOrchestrator.execute_llm_with_tools replacement."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    async def execute_llm_with_tools(self, **kwargs):
        self.calls.append(kwargs)
        step = self.script.pop(0) if self.script else {
            "content": "done", "tokens_input": 1, "tokens_output": 1}
        return {"content": step.get("content", ""),
                "tool_calls": step.get("tool_calls", []),
                "tokens_input": step.get("tokens_input", 1),
                "tokens_output": step.get("tokens_output", 1)}

    @staticmethod
    def tool_call(name, arguments):
        return [{
            "id": f"call_{name}",
            "type": "function",
            "function": {"name": name, "arguments": _json.dumps(arguments)},
        }]


@pytest.fixture
def patch_llm(monkeypatch):
    """Replace LLMOrchestrator.execute_llm_with_tools with a scripted fake."""
    def _install(script):
        fake = FakeLLM(script)

        async def scripted(self, **kwargs):
            fake.calls.append(kwargs)
            step = fake.script.pop(0) if fake.script else {
                "content": "done", "tokens_input": 1, "tokens_output": 1}
            return {"content": step.get("content", ""),
                    "tool_calls": step.get("tool_calls", []),
                    "tokens_input": step.get("tokens_input", 1),
                    "tokens_output": step.get("tokens_output", 1)}

        monkeypatch.setattr(
            "panteon.yono.service.LLMOrchestrator.execute_llm_with_tools",
            scripted)
        return fake
    return _install


# ── Tests ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_panel_requires_auth(client):
    response = await client.get("/api/v1/yono/panel/status")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_panel_status_unseeded(client):
    _override_role()
    try:
        response = await client.get("/api/v1/yono/panel/status")
    finally:
        app.dependency_overrides.pop(routes_yono.get_current_user, None)
    assert response.status_code == 200
    body = response.json()
    assert body["seeded"] is False


@pytest.mark.asyncio
async def test_seed_is_idempotent(war_db):
    from panteon.yono.sc_agent_seed import ensure_sc_yono_agent

    id1, _ = await _seed_llm_and_agent(war_db)
    async with war_db() as db:
        agent2 = await ensure_sc_yono_agent(db)
        await db.commit()
    assert str(agent2.id) == id1


@pytest.mark.asyncio
async def test_panel_status_seeded(client, war_db):
    agent_id, _ = await _seed_llm_and_agent(war_db)
    _override_role()
    try:
        response = await client.get("/api/v1/yono/panel/status")
    finally:
        app.dependency_overrides.pop(routes_yono.get_current_user, None)
    assert response.status_code == 200
    body = response.json()
    assert body["seeded"] is True
    assert body["agent"]["id"] == agent_id
    assert body["model"]["model_id"] == "Qwen3.8-27B"
    assert "kriegspiel_assessment" in body["agent"]["writable_object_types"]
    assert "kriegspiel_run_battle" in body["agent"]["allowed_actions"]


@pytest.mark.asyncio
async def test_panel_chat_proposes_action(client, war_db, patch_llm):
    await _seed_llm_and_agent(war_db)
    await _seed_action_type(war_db)
    fake = patch_llm([
        {"content": "", "tool_calls": FakeLLM.tool_call(
            "execute_action",
            {"action_name": "kriegspiel_run_battle",
             "parameters": {"battlefield": "Taiwan Strait", "scenarios": 800}})},
        {"content": "Proposed a battle run on Taiwan Strait."},
    ])
    _override_role()
    try:
        response = await client.post("/api/v1/yono/panel/chat", json={
            "message": "Run a battle sim on Taiwan Strait"})
    finally:
        app.dependency_overrides.pop(routes_yono.get_current_user, None)
    assert response.status_code == 200
    body = response.json()
    assert body["response"] == "Proposed a battle run on Taiwan Strait."
    entry = next(t for t in body["tool_calls"] if t["tool"] == "execute_action")
    assert entry.get("proposed") is True
    proposal_id = entry["proposal_id"]
    # Ledger row exists and nothing executed
    from panteon.spinal_craker.models import ActionExecution
    async with war_db() as db:
        row = await db.get(ActionExecution, __import__("uuid").UUID(proposal_id))
    assert row.status == "proposed"
    assert fake.calls[0]["tools"] is not None  # tools were offered to the LLM


@pytest.mark.asyncio
async def test_panel_chat_governance_denial(client, war_db, patch_llm):
    await _seed_action_type(war_db)
    await _seed_llm_and_agent(war_db)
    patch_llm([
        {"content": "", "tool_calls": FakeLLM.tool_call(
            "query_objects", {"type_name": "not_registered_type"})},
        {"content": "That type does not exist or is not readable."},
    ])
    _override_role()
    try:
        response = await client.post("/api/v1/yono/panel/chat", json={
            "message": "show me not_registered_type"})
    finally:
        app.dependency_overrides.pop(routes_yono.get_current_user, None)
    assert response.status_code == 200
    entry = response.json()["tool_calls"][0]
    assert entry["denied"] is True
    assert "not authorized" in entry["reason"].lower()


@pytest.mark.asyncio
async def test_recent_objects_newest_first(client, war_db, patch_llm):
    from panteon.spinal_craker.models import Object, ObjectType

    await war_db.ensure_tables()
    async with war_db() as db:
        t = ObjectType(name="kriegspiel_theater", display_name="Theater")
        db.add(t)
        await db.flush()
        now = datetime.utcnow()
        for i, age in enumerate((3, 1, 2)):  # insertion order vs updated_at
            db.add(Object(
                object_type_id=t.id, primary_key_value=f"T{i}",
                properties={"name": f"Theater {i}"},
                updated_at=now - timedelta(hours=age),
                created_at=now,
            ))
        await db.commit()

    await _seed_llm_and_agent(war_db)
    patch_llm([
        {"content": "", "tool_calls": FakeLLM.tool_call("recent_objects", {})},
        {"content": "Latest objects listed."},
    ])
    _override_role()
    try:
        response = await client.post("/api/v1/yono/panel/chat", json={
            "message": "latest activity"})
    finally:
        app.dependency_overrides.pop(routes_yono.get_current_user, None)
    assert response.status_code == 200
    entry = response.json()["tool_calls"][0]
    result = entry.get("result") or {}
    pks = [o["primary_key"] for o in result.get("objects", [])]
    assert pks == ["T1", "T2", "T0"]  # newest (age=1h) first
    assert entry.get("denied") is None


@pytest.mark.asyncio
async def test_map_directive_tools_echo(client, war_db, patch_llm):
    await _seed_llm_and_agent(war_db)
    patch_llm([
        {"content": "", "tool_calls":
            FakeLLM.tool_call("set_map_view", {"center": [121.0, 24.0], "zoom": 7})
            + FakeLLM.tool_call("toggle_layer", {"layer": "sims-ontology", "visible": True})
            + FakeLLM.tool_call("set_map_view", {"center": [999, 0], "zoom": 5})},
        {"content": "Focused the map."},
    ])
    _override_role()
    try:
        response = await client.post("/api/v1/yono/panel/chat", json={
            "message": "show Taiwan on the map"})
    finally:
        app.dependency_overrides.pop(routes_yono.get_current_user, None)
    assert response.status_code == 200
    entries = [t for t in response.json()["tool_calls"]]
    d0 = entries[0]["result"]["directive"]
    assert d0 == {"op": "fly_to", "center": [121.0, 24.0], "zoom": 7.0}
    d1 = entries[1]["result"]["directive"]
    assert d1 == {"op": "toggle_layer", "layer": "sims-ontology", "visible": True}
    assert "error" in entries[2]["result"]


@pytest.mark.asyncio
async def test_confirm_then_reject_lifecycle(client, war_db, monkeypatch):
    from uuid import UUID

    from panteon.yono.ontology_tools import OntologyToolExecutor
    from panteon.yono.models import Agent

    agent_id, _ = await _seed_llm_and_agent(war_db)
    await _seed_action_type(war_db)

    async with war_db() as db:
        agent = await db.get(Agent, UUID(agent_id))
        executor = OntologyToolExecutor(db, agent.id)
        proposal = await executor.propose_action({
            "action_name": "kriegspiel_run_battle",
            "parameters": {"battlefield": "Baltic Coast"},
        })
        await db.commit()
    pid = proposal["proposal_id"]

    # Gateway + ontology emission are faked: confirm must flip to succeeded once
    async def fake_gateway(method, path, request=None, json_body=None):
        return {"battlefield": "Baltic Coast", "scenarios_run": 500,
                "red_wins": 10, "blue_wins": 490}

    async def fake_emit(db, report, mode="battle", **kwargs):
        return {"emitted": True, "mode": mode}

    monkeypatch.setattr("panteon.api.routes_sims._gateway", fake_gateway)

    class _EmitMod:
        @staticmethod
        async def emit_battle_report(*a, **kw):
            return await fake_emit(*a, **kw)

    import sys
    monkeypatch.setitem(sys.modules, "panteon.war_ontology", _EmitMod)

    _override_role()
    try:
        first = await client.post(f"/api/v1/yono/proposals/{pid}/confirm")
        again = await client.post(f"/api/v1/yono/proposals/{pid}/confirm")

        # Second proposal → reject path
        async with war_db() as db:
            agent = await db.get(Agent, UUID(agent_id))
            ex = OntologyToolExecutor(db, agent.id)
            p2 = await ex.propose_action({
                "action_name": "kriegspiel_run_battle",
                "parameters": {"battlefield": "Donbas"}})
            await db.commit()
        rej = await client.post(f"/api/v1/yono/proposals/{p2['proposal_id']}/reject")
    finally:
        app.dependency_overrides.pop(routes_yono.get_current_user, None)

    assert first.status_code == 200
    assert first.json()["status"] == "succeeded"
    assert first.json()["result"]["report"]["battlefield"] == "Baltic Coast"
    assert again.status_code == 409
    assert rej.status_code == 200
    assert rej.json()["status"] == "rejected"


# ── /panel/chat/stream (SSE) ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_panel_stream_requires_auth(client):
    response = await client.post("/api/v1/yono/panel/chat/stream",
                                 json={"message": "hi"})
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_panel_chat_stream_events(client, war_db, monkeypatch):
    await _seed_llm_and_agent(war_db)

    async def fake_stream(self, **kwargs):
        yield ("delta", "Hel")
        yield ("delta", "lo world")
        yield ("done", {"content": "Hello world", "tool_calls": [],
                        "tokens_input": 3, "tokens_output": 2})

    monkeypatch.setattr(
        "panteon.yono.service.LLMOrchestrator.stream_llm_with_tools", fake_stream)

    _override_role()
    try:
        response = await client.post("/api/v1/yono/panel/chat/stream",
                                     json={"message": "say hi"})
    finally:
        app.dependency_overrides.pop(routes_yono.get_current_user, None)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = [_json.loads(line[len("data: "):])
              for line in response.text.split("\n") if line.startswith("data: ")]
    types = [e["type"] for e in events]
    assert "delta" in types and "status" in types
    done = [e for e in events if e["type"] == "done"]
    assert len(done) == 1
    assert done[0]["payload"]["response"] == "Hello world"
    deltas = "".join(e["text"] for e in events if e["type"] == "delta")
    assert deltas == "Hello world"


# ── /panel/history (refresh replay) ──────────────────────────────────────


@pytest.mark.asyncio
async def test_panel_history_requires_auth(client):
    response = await client.get("/api/v1/yono/panel/history",
                                params={"session_id": "00000000-0000-0000-0000-000000000000"})
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_panel_history_replay(client, war_db, patch_llm):
    agent_id, _ = await _seed_llm_and_agent(war_db)
    patch_llm([{"content": "answer one", "tokens_input": 1, "tokens_output": 1}])
    _override_role()
    try:
        chat = await client.post("/api/v1/yono/panel/chat", json={"message": "question one"})
        sid = chat.json()["session_id"]
        hist = await client.get("/api/v1/yono/panel/history", params={"session_id": sid})
        missing = await client.get("/api/v1/yono/panel/history",
                                   params={"session_id": "00000000-0000-0000-0000-000000000000"})
    finally:
        app.dependency_overrides.pop(routes_yono.get_current_user, None)

    assert hist.status_code == 200
    assert hist.json()["session_id"] == sid
    msgs = hist.json()["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[0]["content"] == "question one"
    assert msgs[1]["content"] == "answer one"
    assert missing.status_code == 404
