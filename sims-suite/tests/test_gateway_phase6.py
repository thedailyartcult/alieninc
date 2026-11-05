"""Gateway endpoint tests — Phase 6 new routes.

Tests the persona, research, and platoon extraction HTTP endpoints via
FastAPI's TestClient (starlette).
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from starlette.testclient import TestClient

from api.gateway import app

client = TestClient(app, raise_server_exceptions=False)


# ---- /api/persona/schema ----

def test_persona_schema_returns_fields():
    resp = client.get("/api/persona/schema")
    assert resp.status_code == 200
    data = resp.json()
    assert "categories" in data
    assert isinstance(data["categories"], list)
    assert len(data["categories"]) > 0
    first_cat = data["categories"][0]
    assert "category" in first_cat
    assert "dimensions" in first_cat


# ---- /api/persona/sample ----

def test_persona_sample_returns_persona():
    resp = client.post("/api/persona/sample", json={"seed": 42})
    assert resp.status_code == 200
    data = resp.json()
    assert "values" in data
    assert "profile" in data
    assert isinstance(data["values"], dict)


def test_persona_sample_with_query():
    resp = client.post("/api/persona/sample", json={"seed": 7, "query": {"education_level": "bachelors"}})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)


# ---- /api/persona/cohort ----

def test_persona_cohort_returns_multiple():
    resp = client.post("/api/persona/cohort", json={"n": 5, "seed": 42})
    assert resp.status_code == 200
    data = resp.json()
    assert data["n"] == 5
    assert len(data["personas"]) == 5
    assert data["seed"] == 42


def test_persona_cohort_caps_at_max():
    resp = client.post("/api/persona/cohort", json={"n": 99999, "seed": 1})
    assert resp.status_code == 200
    data = resp.json()
    assert data["n"] <= 10000


# ---- /api/research/bh-gate ----

def test_research_bh_gate_returns_dict():
    resp = client.get("/api/research/bh-gate")
    assert resp.status_code == 200
    data = resp.json()
    # Either returns gate history or an error if tracker unavailable
    assert isinstance(data, dict)


def test_research_bh_gate_respects_k():
    resp = client.get("/api/research/bh-gate?k=5")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)


# ---- /api/research/adherence ----

def test_research_adherence_returns_result():
    resp = client.get("/api/research/adherence?n=4&seed=42")
    assert resp.status_code == 200
    data = resp.json()
    # Either returns probe results or engine-unavailable error
    assert isinstance(data, dict)


# ---- /api/platoon/extract ----

def test_platoon_extract_returns_objective():
    resp = client.post("/api/platoon/extract", json={
        "text": "Secure critical infrastructure against state-level adversaries within 18 months. "
                "Zero successful intrusions. Budget capped at $50M."
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "extraction" in data
    assert "objective" in data
    obj = data["objective"]
    assert obj["domain"] == "cybersecurity"
    assert "Secure" in obj["title"]


def test_platoon_extract_empty_text():
    resp = client.post("/api/platoon/extract", json={"text": ""})
    assert resp.status_code == 200
    data = resp.json()
    assert "error" in data


def test_platoon_extract_too_long():
    resp = client.post("/api/platoon/extract", json={"text": "x" * 9000})
    assert resp.status_code == 200
    data = resp.json()
    assert "error" in data


def test_platoon_extract_no_text_field():
    resp = client.post("/api/platoon/extract", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert "error" in data
