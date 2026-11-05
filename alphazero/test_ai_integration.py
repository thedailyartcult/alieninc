"""End-to-end AI agent integration tests (Phase 6 / LLM Implementation Guide).

Covers the five AI agents (interview, coach, analyze, narrate, memory), the
Go alphacore native commands added for them, the Rust MCP client bridge, and
the LLM (Ollama) fallback behavior.

Run:  python3 -m pytest test_ai_integration.py -v
"""

import json
import os
import subprocess
import sys
import time

import pytest

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(REPO_ROOT, "alpha-zero-engine"))


def _run_cli(script, payload, env_extra=None):
    """Run an AI agent via its JSON stdin/stdout CLI protocol."""
    env = {
        "PYTHONPATH": os.path.join(REPO_ROOT, "alpha-zero-engine"),
        "OLLAMA_DISABLE": "1",
        "PATH": os.environ.get("PATH", ""),
    }
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        [sys.executable, os.path.join(REPO_ROOT, "ai", script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


# ---------------------------------------------------------------------------
# Interview agent
# ---------------------------------------------------------------------------


def test_interview_regex_extraction():
    """Regex fallback produces a persona with full variable coverage."""
    out = _run_cli("interview_agent.py", {
        "interview_text": "My name is Maria Santos, I am 28 years old, a nurse from Cebu",
    })
    assert out["status"] == "success"
    persona = out["persona"]
    assert persona["name"] == "Maria Santos"
    assert persona["age"] == 28
    assert len(persona["social_variables"]) > 20


def test_interview_llm_merge():
    """With Ollama enabled, the LLM overrides while regex variables stay."""
    if os.environ.get("SKIP_LLM"):
        pytest.skip("OLLAMA disabled for this run")
    out = _run_cli("interview_agent.py", {
        "interview_text": "My name is Maria Santos, I am 28 years old, a nurse from Cebu",
    }, env_extra={"OLLAMA_DISABLE": "0"})
    persona = out["persona"]
    assert persona["name"]
    assert isinstance(persona.get("age"), int)
    assert len(persona["social_variables"]) > 20


# ---------------------------------------------------------------------------
# Life coach
# ---------------------------------------------------------------------------


def test_coach_recommendations():
    """Coaching returns situation-specific recommendations and an action plan."""
    character = {
        "name": "Maria",
        "age": 28,
        "happiness": 55,
        "health": 70,
        "smarts": 70,
        "net_worth": 15000,
        "occupation": "nurse",
    }
    out = _run_cli("life_coach.py", {
        "character_json": character,
        "situation": "career_change",
    })
    assert out["status"] == "success"
    result = out["result"]
    assert result["character_name"] == "Maria"
    assert len(result["recommendations"]) > 0
    assert result["action_plan"]


def test_coach_llm_advice_fallback():
    """Life advice always has the heuristic keys even without the LLM."""
    out = _run_cli("life_coach.py", {
        "character_json": {"name": "Juan", "age": 35, "happiness": 45},
        "situation": "general",
    })
    advice = out["result"]["life_advice"]
    for key in ("overall philosophy", "daily_habits", "medium_term_goals",
                "long_term_vision", "key_insight"):
        assert advice.get(key), f"missing life_advice key: {key}"


# ---------------------------------------------------------------------------
# Decision assistant
# ---------------------------------------------------------------------------


def test_analyze_simulation_outcomes():
    """Analysis summarizes results and returns recommendations."""
    out = _run_cli("decision_assistant.py", {
        "simulation_results": [
            {"final_net_worth": 50000, "final_happiness": 70},
            {"final_net_worth": 30000, "final_happiness": 80},
        ],
    })
    assert out["status"] == "success"
    result = out["result"]
    assert result["summary"]["total_simulations"] == 2
    assert result["summary"]["net_worth_range"]["mean"] == 40000
    assert isinstance(result["recommendations"], list)


# ---------------------------------------------------------------------------
# Storyteller
# ---------------------------------------------------------------------------


def test_narrate_from_simulation():
    """Narrative generation returns a story for a character result."""
    out = _run_cli("storyteller.py", {
        "character_name": "Maria",
        "simulation_result": {
            "final_age": 65,
            "final_net_worth": 120000,
            "final_happiness": 75,
        },
    })
    assert out["status"] == "success"
    narrative = out["result"]["narrative"]
    assert "Maria" in narrative
    assert "65" in narrative


# ---------------------------------------------------------------------------
# Financial advisor
# ---------------------------------------------------------------------------


def test_financial_advisor_advice():
    """Financial advice returns assessment, recommendations, and allocation."""
    character = {
        "name": "Maria",
        "age": 35,
        "net_worth": 45000,
        "debt": 5000,
        "money": 8000,
        "portfolio_value": 30000,
        "occupation": "nurse",
        "education": "University",
    }
    out = _run_cli("financial_advisor.py", {"character_json": character, "situation": "investment"})
    assert out["status"] == "success"
    result = out["result"]
    assert result["character_name"] == "Maria"
    assert len(result["recommendations"]) > 0
    assert result["analysis"]["net_worth"] == 38000
    assert result["allocation"]["strategy"] in ("hyper_growth", "balanced", "recession_defense", "dividend_income")
    assert result["encouragement"]


# ---------------------------------------------------------------------------
# Health coach
# ---------------------------------------------------------------------------


def test_health_coach_advice():
    """Health coaching returns assessment, recommendations, and a plan."""
    character = {
        "name": "Maria",
        "age": 35,
        "health": 55,
        "happiness": 45,
    }
    out = _run_cli("health_coach.py", {"character_json": character, "situation": "stress"})
    assert out["status"] == "success"
    result = out["result"]
    assert result["character_name"] == "Maria"
    assert len(result["recommendations"]) > 0
    assert result["weekly_plan"]["monday"]
    assert result["action_plan"]["30_days"]
    assert result["analysis"]["health_category"] in ("excellent", "good", "fair", "poor")


# ---------------------------------------------------------------------------
# Mentor
# ---------------------------------------------------------------------------


def test_mentor_synthesizes_advisors():
    """Mentor merges financial, health, and life coaching into one session."""
    character = {
        "name": "Maria",
        "age": 35,
        "happiness": 45,
        "health": 55,
        "smarts": 70,
        "net_worth": 15000,
        "occupation": "nurse",
    }
    out = _run_cli("mentor.py", {
        "character_json": character,
        "question": "Should I quit my job to start a clinic?",
    })
    assert out["status"] == "success"
    result = out["result"]
    assert result["character_name"] == "Maria"
    assert result["focus_areas"]
    assert len(result["principles"]) > 0
    assert result["financial_advisor"]["recommendations"]
    assert result["health_coach"]["recommendations"]
    assert result["life_coach"]["recommendations"]
    assert result["mentor_response"]


# ---------------------------------------------------------------------------
# Memory system
# ---------------------------------------------------------------------------


def test_memory_persistence(tmp_path):
    """Learnings persist across agent instances via the CMB file store."""
    ws = "test_ws_memory"
    payload = {
        "data": {"learning_id": "mem_persist_1", "data": {"insight": "persisted"},
                 "tags": ["test"], "importance": 8},
        "session_id": "s1",
    }
    out1 = _run_cli("memory_system.py", {
        "operation": "store", "workspace": ws, **payload,
    })
    assert out1["result"]["stored"] is True

    out2 = _run_cli("memory_system.py", {
        "operation": "retrieve", "query": "persisted", "workspace": ws,
    })
    assert out2["result"]["count"] >= 1

    out3 = _run_cli("memory_system.py", {
        "operation": "delete", "data": {"learning_id": "mem_persist_1"},
        "workspace": ws,
    })
    assert out3["result"]["deleted"] is True


def test_memory_session_lifecycle():
    """Sessions can be created and ended (durable across invocations)."""
    ws = "test_ws_memory"
    session_id = "lifecycle_{}_{}".format(os.getpid(), int(time.time() * 1000))
    out = _run_cli("memory_system.py", {
        "operation": "create_session", "workspace": ws,
        "session_id": session_id, "data": {"context": {"goal": "test"}},
    })
    assert out["result"]["created"] is True
    out2 = _run_cli("memory_system.py", {
        "operation": "end_session", "workspace": ws,
        "session_id": session_id, "data": {"insights": ["done"]},
    })
    assert out2["result"]["ended"] is True
    out3 = _run_cli("memory_system.py", {
        "operation": "end_session", "workspace": ws,
        "session_id": session_id, "data": {"insights": ["done"]},
    })
    assert out3["result"]["ended"] is True


# ---------------------------------------------------------------------------
# Advisor panel (Phase 9): interview -> multiverse -> 3 specialists + dossier
# ---------------------------------------------------------------------------


def _unique_ws(prefix):
    """Unique per-run workspace so repeated test runs don't see stale dossiers."""
    return f"{prefix}_{os.getpid()}_{int(time.time() * 1000)}"


def test_advisor_panel_cli():
    """Advisor panel runs interview -> multiverse -> 3 specialists + stores dossier."""
    out = _run_cli("advisor_panel.py", {
        "interview_text": "My name is Carlos Dizon, I am 32 years old, an engineer in Manila",
        "universes": 10, "max_universes": 10, "workspace": _unique_ws("test_ws_advisor"),
        "persist_memory": True,
    })
    assert out["status"] == "success"
    assert out["persona"]["name"] == "Carlos Dizon"
    assert out["simulation"]["total_simulations"] >= 10
    adv = out["advisors"]
    assert len(adv["financial_advisor"]["recommendations"]) > 0
    assert len(adv["health_coach"]["recommendations"]) > 0
    assert adv["mentor"]["focus_areas"]
    assert out["dossier"]["learning_id"] is not None
    assert out["dossier"]["stored"] is True
    assert out["continuity"]["prior_dossiers"] == 0
    assert adv["financial_advisor"]["continuity"]["recalled_count"] == 0
    assert adv["health_coach"]["continuity"]["recalled_count"] == 0
    assert adv["mentor"]["continuity"]["recalled_count"] == 0


def test_advisor_continuity_recall():
    """A second run for the same character recalls the prior dossier's advice."""
    ws = _unique_ws("test_ws_advisor_cont")
    payload = {
        "interview_text": "My name is Liza Cruz, I am 40 years old, a teacher in Manila",
        "universes": 10, "max_universes": 10, "workspace": ws, "persist_memory": True,
    }
    first = _run_cli("advisor_panel.py", payload)
    assert first["status"] == "success"
    assert first["continuity"]["prior_dossiers"] == 0

    second = _run_cli("advisor_panel.py", payload)
    assert second["status"] == "success"
    assert second["continuity"]["prior_dossiers"] >= 1
    assert len(second["continuity"]["prior_advice"]["financial_advisor"]) > 0
    assert len(second["continuity"]["prior_advice"]["health_coach"]) > 0
    assert len(second["continuity"]["prior_advice"]["mentor"]) > 0
    assert second["advisors"]["financial_advisor"]["continuity"]["recalled_count"] > 0


def test_advisor_dossier_recall():
    """Stored dossiers can be recalled per character via the CLI."""
    ws = _unique_ws("test_ws_advisor_dossier")
    _run_cli("advisor_panel.py", {
        "interview_text": "My name is Andres Bonifacio, I am 29, a businessman in Manila",
        "universes": 10, "max_universes": 10, "workspace": ws, "persist_memory": True,
    })
    out = _run_cli("advisor_panel.py", {
        "operation": "recall_dossier",
        "character_name": "Andres Bonifacio", "workspace": ws,
    })
    assert out["status"] == "success"
    assert out["result"]["count"] >= 1
    dossiers = out["result"]["dossiers"]
    assert dossiers[0]["data"]["type"] == "advisor_panel"
    assert "financial_advisor" in dossiers[0]["data"]["advisor_outputs"]


def test_pipeline_stores_advisor_outputs():
    """The pipeline memory stage stores each advisor's output, not just the insight."""
    ws = _unique_ws("test_ws_pipeline_adv")
    _run_cli("pipeline.py", {
        "interview_text": "My name is Rosa Alba, I am 26, a designer in Manila",
        "universes": 10, "max_universes": 10, "workspace": ws, "persist_memory": True,
    })
    out = _run_cli("memory_system.py", {
        "operation": "retrieve", "query": "Rosa Alba", "workspace": ws,
    })
    learnings = out["result"]["results"]
    assert learnings, "expected a stored pipeline learning"
    data = learnings[0]["data"]
    assert data["type"] == "ai_pipeline"
    assert "advisor_outputs" in data
    assert data["advisor_outputs"]["financial_advisor"]["recommendations"]
    assert data["advisor_outputs"]["health_coach"]["recommendations"]
    assert data["advisor_outputs"]["mentor"]["focus_areas"]


# ---------------------------------------------------------------------------
# Complete workflow
# ---------------------------------------------------------------------------


def test_complete_ai_workflow():
    """interview -> coach -> analyze -> narrate -> memory as one pipeline."""
    # 1. Interview
    interview = _run_cli("interview_agent.py", {
        "interview_text": "My name is Anna Reyes, I am 25, a fresh graduate in Manila",
    })
    profile = interview["persona"]
    assert profile["name"] == "Anna Reyes"

    # 2. Coach
    coaching = _run_cli("life_coach.py", {
        "character_json": profile,
        "situation": "career_starting_out",
    })
    assert coaching["status"] == "success"
    assert len(coaching["result"]["recommendations"]) > 0

    # 3. Analyze
    analysis = _run_cli("decision_assistant.py", {
        "simulation_results": [
            {"final_net_worth": 50000, "final_happiness": 70},
            {"final_net_worth": 30000, "final_happiness": 80},
        ],
    })
    assert analysis["status"] == "success"

    # 4. Narrate
    narrative = _run_cli("storyteller.py", {
        "character_name": profile["name"],
        "simulation_result": {"final_age": 65, "final_net_worth": 80000,
                              "final_happiness": 70},
    })
    assert narrative["status"] == "success"
    assert "Anna Reyes" in narrative["result"]["narrative"]

    # 5. Memory
    learning_id = "workflow_learning_1"
    memory = _run_cli("memory_system.py", {
        "operation": "store",
        "workspace": "test_ws_workflow",
        "data": {
            "learning_id": learning_id,
            "data": {"interview": profile, "coaching": coaching["result"]},
            "tags": ["integration_test", "ai_workflow"],
            "importance": 8,
        },
        "session_id": "workflow_session",
    })
    assert memory["result"]["stored"] is True
    assert memory["result"]["learning_id"] == learning_id


# ---------------------------------------------------------------------------
# Go native core AI commands
# ---------------------------------------------------------------------------

ALPHACORE = os.path.join(REPO_ROOT, "alpha-zero-engine", "core", "bin", "alphacore")

NEEDS_ALPHACORE = pytest.mark.skipif(
    not os.path.exists(ALPHACORE),
    reason="alphacore binary not built (run core/scripts/build_core.sh)",
)


def _alphacore(cmd, payload):
    proc = subprocess.run(
        [ALPHACORE, cmd],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


@NEEDS_ALPHACORE
def test_alphacore_interview():
    out = _alphacore("interview", {"name": "Maria", "age": 28, "gender": "female"})
    assert out["status"] == "success"
    assert out["backend"] == "go"
    assert out["profile"]["name"] == "Maria"


@NEEDS_ALPHACORE
def test_alphacore_coach():
    out = _alphacore("coach", {"character_json": '{"name": "Maria"}', "situation": "career_change"})
    assert out["status"] == "success"
    assert len(out["result"]["recommendations"]) > 0


@NEEDS_ALPHACORE
def test_alphacore_analyze():
    out = _alphacore("analyze", {
        "simulation_results": [{"final_net_worth": 50000, "final_happiness": 70}],
    })
    assert out["status"] == "success"
    assert out["result"]["summary"]["total"] == 1


@NEEDS_ALPHACORE
def test_alphacore_narrate():
    out = _alphacore("narrate", {
        "character_name": "Maria",
        "simulation_result": {"final_age": 65},
    })
    assert out["status"] == "success"
    assert "Maria" in out["result"]["title"]


@NEEDS_ALPHACORE
def test_alphacore_memory():
    out = _alphacore("memory", {"operation": "store", "data": {"learning_id": "l1"}})
    assert out["status"] == "success"
    assert out["result"]["stored"] is True


# ---------------------------------------------------------------------------
# Web platform (Flask) AI routes
# ---------------------------------------------------------------------------

def _import_ok(module):
    try:
        __import__(module)
        return True
    except ImportError:
        return False


NEEDS_FLASK = pytest.mark.skipif(
    not _import_ok("flask"),
    reason="flask not installed (pip install flask)",
)


def _web_app():
    sys.path.insert(0, os.path.join(REPO_ROOT, "alpha-zero-engine"))
    from api.routes import create_app
    return create_app().test_client()


@NEEDS_FLASK
def test_web_index_has_ai_tab():
    """Dashboard renders the AI Agents tab."""
    client = _web_app()
    html = client.get("/").get_data(as_text=True)
    assert "tab-ai-agents" in html
    assert "btn-ai-interview" in html


@NEEDS_FLASK
def test_web_ai_interview_route():
    """Interview route builds a persona with explicit field overlay."""
    client = _web_app()
    r = client.post("/api/ai/interview", json={
        "name": "Maria", "age": 28, "gender": "female",
        "initial_interview_text": "I work as a nurse in Cebu",
    })
    data = r.get_json()
    assert r.status_code == 200
    assert data["status"] == "success"
    assert data["persona"]["name"] == "Maria"
    assert data["persona"]["age"] == 28
    assert len(data["social_variables"]) > 20


@NEEDS_FLASK
def test_web_ai_coach_route():
    client = _web_app()
    r = client.post("/api/ai/coach", json={
        "character_json": {"name": "Maria", "age": 28, "happiness": 55},
        "situation": "career_change",
    })
    data = r.get_json()
    assert r.status_code == 200
    assert data["status"] == "success"
    assert len(data["result"]["recommendations"]) > 0


@NEEDS_FLASK
def test_web_ai_analyze_route():
    client = _web_app()
    r = client.post("/api/ai/analyze", json={
        "simulation_results": [{"final_net_worth": 50000, "final_happiness": 70}],
    })
    data = r.get_json()
    assert r.status_code == 200
    assert data["result"]["summary"]["total_simulations"] == 1


@NEEDS_FLASK
def test_web_ai_narrate_route():
    client = _web_app()
    r = client.post("/api/ai/narrate", json={
        "character_name": "Maria",
        "simulation_result": {"final_age": 65, "final_net_worth": 120000, "final_happiness": 75},
    })
    data = r.get_json()
    assert r.status_code == 200
    assert "Maria" in data["result"]["narrative"]


@NEEDS_FLASK
def test_web_ai_financial_advisor_route():
    client = _web_app()
    r = client.post("/api/ai/financial_advisor", json={
        "character_json": {"name": "Maria", "age": 35, "net_worth": 45000,
                           "debt": 5000, "money": 8000, "portfolio_value": 30000},
        "situation": "investment",
    })
    data = r.get_json()
    assert r.status_code == 200
    assert data["status"] == "success"
    assert len(data["result"]["recommendations"]) > 0
    assert data["result"]["allocation"]["strategy"]


@NEEDS_FLASK
def test_web_ai_health_coach_route():
    client = _web_app()
    r = client.post("/api/ai/health_coach", json={
        "character_json": {"name": "Maria", "age": 35, "health": 55, "happiness": 45},
        "situation": "stress",
    })
    data = r.get_json()
    assert r.status_code == 200
    assert data["status"] == "success"
    assert len(data["result"]["recommendations"]) > 0
    assert data["result"]["weekly_plan"]["monday"]


@NEEDS_FLASK
def test_web_ai_mentor_route():
    client = _web_app()
    r = client.post("/api/ai/mentor", json={
        "character_json": {"name": "Maria", "age": 35, "happiness": 45, "health": 55},
        "question": "What should I focus on this year?",
    })
    data = r.get_json()
    assert r.status_code == 200
    assert data["status"] == "success"
    assert data["result"]["focus_areas"]
    assert data["result"]["mentor_response"]
    assert data["result"]["financial_advisor"]["recommendations"]


@NEEDS_FLASK
def test_web_ai_memory_route():
    client = _web_app()
    r = client.post("/api/ai/memory", json={
        "operation": "store", "workspace": "test_ws_web",
        "data": {"learning_id": "web_route_1", "data": {"insight": "route works"},
                 "tags": ["web"], "importance": 5},
    })
    assert r.get_json()["result"]["stored"] is True
    r2 = client.post("/api/ai/memory", json={
        "operation": "retrieve", "workspace": "test_ws_web", "query": "route",
    })
    assert r2.get_json()["result"]["count"] >= 1


@NEEDS_FLASK
def test_web_ai_pipeline_route():
    """End-to-end pipeline: interview -> simulate -> analyze -> coach -> narrate -> memory."""
    client = _web_app()
    r = client.post("/api/ai/pipeline", json={
        "name": "Maria", "age": 28, "gender": "female",
        "interview_text": "My name is Maria Santos, I am 28 years old, a nurse from Cebu",
        "universes": 15, "max_universes": 15, "workspace": "test_ws_pipeline",
        "persist_memory": True,
    })
    data = r.get_json()
    assert r.status_code == 200
    assert data["status"] == "success"
    assert data["persona"]["name"] == "Maria"
    assert data["simulation"]["total_simulations"] >= 15
    assert data["simulation"]["convergence_rate"] >= 0
    assert len(data["analysis"]["recommendations"]) > 0
    assert len(data["coaching"]["recommendations"]) > 0
    assert len(data["narrative"]["story"]) > 50
    assert data["learning_id"] is not None


@NEEDS_FLASK
def test_web_ai_advisors_route():
    """Advisor panel route runs the full flow and persists a dossier."""
    old = os.environ.get("OLLAMA_DISABLE")
    os.environ["OLLAMA_DISABLE"] = "1"
    try:
        client = _web_app()
        r = client.post("/api/ai/advisors", json={
            "name": "Carlos", "age": 32, "gender": "male",
            "interview_text": "My name is Carlos Dizon, I am 32 years old, an engineer in Manila",
            "universes": 10, "max_universes": 10, "workspace": "test_ws_web_advisor",
            "persist_memory": True,
        })
        data = r.get_json()
        assert r.status_code == 200
        assert data["status"] == "success"
        assert data["persona"]["name"] == "Carlos"
        assert data["simulation"]["total_simulations"] >= 10
        assert data["advisors"]["financial_advisor"]["recommendations"]
        assert data["advisors"]["health_coach"]["recommendations"]
        assert data["advisors"]["mentor"]["focus_areas"]
        assert data["dossier"]["learning_id"] is not None
    finally:
        if old is None:
            os.environ.pop("OLLAMA_DISABLE", None)
        else:
            os.environ["OLLAMA_DISABLE"] = old


@NEEDS_FLASK
def test_web_ai_advisor_dossier_route():
    """Dossier route returns the stored advisor panel for a character."""
    client = _web_app()
    ws = "test_ws_web_dossier"
    name = "Dossier Tester"
    store = client.post("/api/ai/memory", json={
        "operation": "store", "workspace": ws,
        "data": {
            "learning_id": f"dossier_{os.getpid()}",
            "data": {
                "type": "advisor_panel",
                "character_name": name,
                "advisor_outputs": {
                    "financial_advisor": {"recommendations": ["save 20%"]},
                    "health_coach": {"recommendations": ["sleep 8h"]},
                    "mentor": {"focus_areas": ["Growth & Leverage"]},
                },
            },
            "tags": ["advisor_panel", "dossier"], "importance": 5,
        },
    })
    assert store.get_json()["result"]["stored"] is True

    r = client.post("/api/ai/advisor_dossier", json={
        "character_name": name, "workspace": ws,
    })
    data = r.get_json()
    assert r.status_code == 200
    assert data["status"] == "success"
    assert data["result"]["count"] >= 1
    dossier_data = data["result"]["dossiers"][0]["data"]
    inner = dossier_data.get("data", dossier_data)
    assert inner["type"] == "advisor_panel"