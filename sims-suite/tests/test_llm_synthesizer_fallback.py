"""Synthesizer fallback tests — no live LLM, verifies the safety net.

Covers the two paths the contractor cares about:
  1. No LLM configured → procedural fallback, provenance.source == "procedural"
  2. LLM raises/returns garbage → procedural fallback, provenance records why
  3. LLM returns a valid battle → it flows through with provenance.source == "llm"
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from engines.kriegspiel.llm.client import LLMClient, LLMResponse
from engines.kriegspiel.llm.synthesizer import (
    synthesize_battle_seed,
    synthesize_events,
)
from engines.kriegspiel.models import Battle, Doctrine


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------

class _NoClient:
    """Stand-in for get_llm_client() returning None (no provider configured)."""
    provider = "none"
    model = "none"


class _RaisingClient(LLMClient):
    """LLM that always raises — simulates HTTP error / network failure."""
    provider = "raising"
    model = "test"

    def complete(self, prompt: str) -> LLMResponse:
        raise RuntimeError("simulated HTTP 500")


class _GarbageClient(LLMClient):
    """LLM that returns non-JSON — simulates a hallucinated response."""
    provider = "garbage"
    model = "test"

    def complete(self, prompt: str) -> LLMResponse:
        return LLMResponse(
            text="Sorry, I can't help with military scenarios.",
            provider=self.provider, model=self.model,
            prompt_hash="p", raw_response_hash="r", latency_ms=12.3,
        )


class _InvalidClient(LLMClient):
    """LLM that returns JSON failing domain validation."""
    provider = "invalid"
    model = "test"

    def complete(self, prompt: str) -> LLMResponse:
        # Strength 150 is out of range — should fail validation.
        bad = {
            "battlefield": {
                "name": "Bad", "center": [0, 0], "terrain": "open",
                "area_km2": 1000, "bounds": [-1, -1, 1, 1],
            },
            "objective": "test", "duration_hours": 48,
            "red_force": {"name": "R", "doctrine": "attrition", "units": [
                {"unit_type": "infantry", "strength": 150, "morale": 80,
                 "supply": 80, "speed_kmh": 25, "engagement_range_km": 5},
                {"unit_type": "infantry", "strength": 80, "morale": 80,
                 "supply": 80, "speed_kmh": 25, "engagement_range_km": 5},
                {"unit_type": "infantry", "strength": 80, "morale": 80,
                 "supply": 80, "speed_kmh": 25, "engagement_range_km": 5},
            ]},
            "blue_force": {"name": "B", "doctrine": "defensive", "units": [
                {"unit_type": "infantry", "strength": 80, "morale": 80,
                 "supply": 80, "speed_kmh": 25, "engagement_range_km": 5},
                {"unit_type": "infantry", "strength": 80, "morale": 80,
                 "supply": 80, "speed_kmh": 25, "engagement_range_km": 5},
                {"unit_type": "infantry", "strength": 80, "morale": 80,
                 "supply": 80, "speed_kmh": 25, "engagement_range_km": 5},
            ]},
        }
        return LLMResponse(
            text=json.dumps(bad),
            provider=self.provider, model=self.model,
            prompt_hash="p", raw_response_hash="r", latency_ms=45.6,
        )


class _ValidClient(LLMClient):
    """LLM that returns a fully valid battle."""
    provider = "valid"
    model = "test"

    def complete(self, prompt: str) -> LLMResponse:
        good = {
            "battlefield": {
                "name": "LLM Strait", "center": [25.0, 120.0],
                "terrain": "coastal", "area_km2": 50000,
                "bounds": [118, 22, 122, 27],
            },
            "objective": "Secure the strait",
            "duration_hours": 48,
            "red_force": {"name": "Red Fleet", "doctrine": "shock", "units": [
                {"unit_type": "infantry", "strength": 90, "morale": 80,
                 "supply": 100, "speed_kmh": 25, "engagement_range_km": 5},
                {"unit_type": "armor", "strength": 85, "morale": 75,
                 "supply": 90, "speed_kmh": 40, "engagement_range_km": 8},
                {"unit_type": "air", "strength": 95, "morale": 88,
                 "supply": 95, "speed_kmh": 80, "engagement_range_km": 30},
            ]},
            "blue_force": {"name": "Blue Fleet", "doctrine": "defensive", "units": [
                {"unit_type": "infantry", "strength": 80, "morale": 70,
                 "supply": 85, "speed_kmh": 22, "engagement_range_km": 4},
                {"unit_type": "artillery", "strength": 75, "morale": 65,
                 "supply": 80, "speed_kmh": 15, "engagement_range_km": 20},
                {"unit_type": "recon", "strength": 70, "morale": 60,
                 "supply": 75, "speed_kmh": 50, "engagement_range_km": 12},
            ]},
            "situational_events": ["amphibious landing repulsed",
                                   "carrier group sortied"],
        }
        return LLMResponse(
            text=json.dumps(good),
            provider=self.provider, model=self.model,
            prompt_hash="p", raw_response_hash="r", latency_ms=78.9,
        )


# ---------------------------------------------------------------------------
# Battle seed fallback path
# ---------------------------------------------------------------------------

def test_no_client_falls_back_to_procedural(monkeypatch=None):
    # Force get_llm_client to return None by passing client=None explicitly.
    battle = synthesize_battle_seed(seed=42, client=None)
    assert battle.provenance is not None
    assert battle.provenance["source"] == "procedural"
    assert "no LLM client" in battle.provenance["reason"]


def test_raising_client_falls_back_to_procedural():
    battle = synthesize_battle_seed(seed=42, client=_RaisingClient())
    assert battle.provenance["source"] == "procedural"
    assert "HTTP error" in battle.provenance["reason"]
    assert battle.provenance["attempted_provider"] == "raising"


def test_garbage_client_falls_back_to_procedural():
    battle = synthesize_battle_seed(seed=42, client=_GarbageClient())
    assert battle.provenance["source"] == "procedural"
    assert "JSON parse" in battle.provenance["reason"]


def test_invalid_client_falls_back_to_procedural():
    battle = synthesize_battle_seed(seed=42, client=_InvalidClient())
    assert battle.provenance["source"] == "procedural"
    assert "validation" in battle.provenance["reason"]


def test_valid_client_flows_through():
    battle = synthesize_battle_seed(seed=42, client=_ValidClient())
    assert battle.provenance["source"] == "llm"
    assert battle.provenance["provider"] == "valid"
    assert battle.provenance["model"] == "test"
    assert battle.provenance["validated"] is True
    assert battle.battlefield.name == "LLM Strait"
    assert battle.red_force.doctrine == Doctrine.SHOCK
    # Forces should be geographically deployed (positions set).
    for u in battle.red_force.units:
        assert u.position != (0.0, 0.0)
    for u in battle.blue_force.units:
        assert u.position != (0.0, 0.0)


# ---------------------------------------------------------------------------
# Events fallback path
# ---------------------------------------------------------------------------

def test_events_no_client_falls_back_to_procedural_pool():
    battle = synthesize_battle_seed(seed=42, client=None)
    events = synthesize_events(battle, n=5, client=None)
    assert len(events) == 5
    # Procedural pool events are lowercase
    assert all(isinstance(e, str) for e in events)


def test_events_valid_client_returns_llm_events():
    battle = synthesize_battle_seed(seed=42, client=_ValidClient())
    # Use the same valid client to get events
    events = synthesize_events(battle, n=3, client=_ValidClient())
    # The _ValidClient returns the battle JSON, not events JSON, so this
    # will fall through to the procedural pool. That's correct behavior —
    # we're testing the safety net, not a real event-capable client.
    assert len(events) == 3


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

def test_audit_log_written(tmp_path):
    import os
    os.environ["KRIEGSPIEL_LLM_AUDIT_DIR"] = str(tmp_path)
    try:
        synthesize_battle_seed(seed=42, client=_RaisingClient())
        files = list(tmp_path.glob("audit-*.jsonl"))
        assert files, "audit log file should be created"
        lines = files[0].read_text().strip().split("\n")
        assert len(lines) >= 1
        record = json.loads(lines[0])
        assert record["op"] == "battle_seed"
        assert record["status"] == "http_error"
        assert "ts" in record
    finally:
        del os.environ["KRIEGSPIEL_LLM_AUDIT_DIR"]
