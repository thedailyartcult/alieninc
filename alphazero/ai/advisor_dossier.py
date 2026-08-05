"""Shared dossier + continuity helpers for the AI Advisor Panel (Phase 9).

Per-character advisor state lives in durable memory (CMB) via the
MemorySystemAgent — identity/state live in memory, not code. These helpers
recall prior advice so the specialist advisors can build on earlier sessions.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

ADVISOR_KEYS: Tuple[str, ...] = ("financial_advisor", "health_coach", "mentor")


def build_continuity(character_data: Dict[str, Any],
                     character_name: str = "Unknown") -> Dict[str, Any]:
    """Deterministic continuity block from a character_data.prior_advice list."""
    prior = [str(p) for p in (character_data.get("prior_advice") or []) if p][:5]
    if prior:
        label = "entry" if len(prior) == 1 else "entries"
        summary = f"Building on {len(prior)} prior advice {label} for {character_name}."
    else:
        summary = f"No prior advice on file for {character_name} yet."
    return {
        "prior_advice_recalled": prior,
        "recalled_count": len(prior),
        "summary": summary,
    }


def merge_character_state(persona: Dict[str, Any],
                          best: Dict[str, Any]) -> Dict[str, Any]:
    """Persona + best-universe outcomes -> the advisors' character state."""
    state = dict(persona)
    state.setdefault("happiness", best.get("final_happiness", 50))
    state.setdefault("health", best.get("final_health", 70))
    state.setdefault("net_worth", best.get("final_net_worth", 0))
    state.setdefault("money", persona.get("money", 0))
    state.setdefault("debt", persona.get("debt", 0))
    state.setdefault("portfolio_value",
                     persona.get("portfolio_value", best.get("final_net_worth", 0) * 0.6))
    return state


def recall_prior_advice(memory, character_name: str) -> Tuple[Dict[str, List[str]], int]:
    """Recall prior advisor advice for a character.

    Returns (per-advisor recommendation lists, number of prior dossiers found).
    A memory agent is duck-typed: any object with retrieve_learnings(query=...)
    works. Pass None to skip recall.
    """
    prior: Dict[str, List[str]] = {key: [] for key in ADVISOR_KEYS}
    if memory is None or not character_name:
        return prior, 0

    learnings = memory.retrieve_learnings(query=character_name, limit=20)
    count = 0
    for learning in learnings:
        data = learning.get("data", {})
        if data.get("type") not in ("advisor_panel", "ai_pipeline"):
            continue
        if data.get("character_name") != character_name:
            continue
        count += 1
        outputs = data.get("advisor_outputs", {})
        for key in ADVISOR_KEYS:
            advisor = outputs.get(key) or {}
            recs = advisor.get("recommendations") or []
            if key == "mentor":
                recs = advisor.get("focus_areas") or []
            prior[key].extend(str(r) for r in recs if r)

    return prior, count


def recall_advisor_dossier(character_name: str, workspace: str = "alphazero",
                           limit: int = 10) -> List[Dict[str, Any]]:
    """Return stored advisor-panel dossiers for a character from CMB."""
    if not character_name:
        return []

    from ai.memory_system import MemorySystemAgent

    memory = MemorySystemAgent(workspace=workspace)
    learnings = memory.retrieve_learnings(query=character_name, limit=limit)
    results = []
    for learning in learnings:
        data = learning.get("data", {})
        inner = data.get("data", data)  # handle double-nested payload from web endpoint
        if inner.get("type") == "advisor_panel" and inner.get("character_name") == character_name:
            results.append(learning)
    return results
