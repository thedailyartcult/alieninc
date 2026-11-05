"""AI Advisor Panel - interview -> multiverse -> specialist advisors.

Runs the full advisor flow for one character (interview -> multiverse
simulation -> financial advisor + health coach + mentor) and persists a durable
per-character dossier through the MemorySystemAgent / CMB, so later sessions
recall prior advice for continuity. Identity and state live in memory, not code.

Used by the web platform (/api/ai/advisors) and available as a JSON CLI for
parity with the other agents.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, Optional

if __name__ == "__main__" and __package__ is None:
    _AI_DIR = os.path.dirname(os.path.abspath(__file__))
    _REPO_ROOT = os.path.dirname(_AI_DIR)
    sys.path.insert(0, _AI_DIR)
    if _REPO_ROOT not in sys.path:
        sys.path.insert(0, _REPO_ROOT)
    _ENGINE_DIR = os.path.join(_REPO_ROOT, "alpha-zero-engine")
    if _ENGINE_DIR not in sys.path:
        sys.path.insert(0, _ENGINE_DIR)

from engine.simulation import SimulationOrchestrator

from ai.interview_agent import InterviewAgent
from ai.memory_system import MemorySystemAgent
from ai.financial_advisor import FinancialAdvisorAgent
from ai.health_coach import HealthCoachAgent
from ai.mentor import MentorAgent
from ai.advisor_dossier import (
    recall_prior_advice,
    recall_advisor_dossier,
    merge_character_state,
)
from ai.pipeline import _persona_to_config


def run_advisor_panel(
    interview_text: str,
    workspace: str = "alphazero",
    overrides: Optional[Dict[str, Any]] = None,
    persist_memory: bool = True,
    max_universes: int = 100,
) -> Dict[str, Any]:
    """Run the Advisor Panel: interview -> multiverse -> all 3 specialists."""
    overrides = overrides or {}
    universes = max(10, min(max_universes, int(overrides.get("universes", 50))))

    # 1. Interview — build the persona
    interview = InterviewAgent()
    if os.environ.get("OLLAMA_DISABLE") == "1":
        persona = interview._extract_with_regex(interview_text)
    else:
        persona = interview.extract_persona_from_text(interview_text)
    for field in ("name", "age", "gender", "occupation", "birthplace", "current_city"):
        explicit = overrides.get(field)
        if explicit not in (None, ""):
            persona[field] = explicit
    character_name = persona.get("name", "Player")

    # 2. Simulate — persona seeds the multiverse
    config = _persona_to_config(persona, {**overrides, "universes": universes})
    orchestrator = SimulationOrchestrator(config)
    report = orchestrator.run_multiverse()

    simulation_results = [
        {
            "universe_id": u.universe_id,
            "final_net_worth": u.final_net_worth,
            "final_happiness": u.final_happiness,
            "final_health": u.final_health,
            "years_lived": u.years_lived,
        }
        for u in report.parallel_universes
    ]
    best = {
        "universe_id": report.best_net_worth.universe_id,
        "final_net_worth": report.best_net_worth.final_net_worth,
        "final_happiness": report.best_net_worth.final_happiness,
        "final_health": report.best_net_worth.final_health,
    }

    # 3. Character state — persona + best-universe outcomes for the advisors
    character_state = merge_character_state(persona, best)

    # 4. Recall prior advice for continuity (durable state lives in CMB)
    memory = MemorySystemAgent(workspace=workspace) if persist_memory else None
    prior_advice, prior_dossiers = recall_prior_advice(memory, character_name)

    # 5. Specialist advisors — each builds on prior advice for this character
    fa_input = dict(character_state)
    fa_input["prior_advice"] = prior_advice["financial_advisor"]
    financial_advice = FinancialAdvisorAgent().provide_advice(
        fa_input, overrides.get("financial_situation", "general")
    )

    hc_input = dict(character_state)
    hc_input["prior_advice"] = prior_advice["health_coach"]
    health_coach_advice = HealthCoachAgent().provide_advice(
        hc_input, overrides.get("health_situation", "general")
    )

    mn_input = dict(character_state)
    mn_input["prior_advice"] = prior_advice["mentor"]
    mentor = MentorAgent().provide_mentorship(
        mn_input, overrides.get("question", "") or ""
    )

    # 6. Persist the dossier so future sessions can recall it
    dossier_id = None
    if persist_memory:
        dossier_id = memory.store_learning({
            "type": "advisor_panel",
            "character_name": character_name,
            "persona": persona,
            "best": best,
            "advisor_outputs": {
                "financial_advisor": financial_advice,
                "health_coach": health_coach_advice,
                "mentor": mentor,
            },
        }, session_id=overrides.get("session_id"))

    return {
        "status": "success",
        "persona": persona,
        "simulation": {
            "total_simulations": report.total_simulations,
            "convergence_rate": report.convergence_rate,
            "sharpe_ratio": report.sharpe_ratio,
            "avg_years_lived": report.avg_years_lived,
            "best": best,
            "outcome_distribution": report.outcome_distribution,
        },
        "advisors": {
            "financial_advisor": financial_advice,
            "health_coach": health_coach_advice,
            "mentor": mentor,
        },
        "continuity": {
            "prior_dossiers": prior_dossiers,
            "prior_advice": prior_advice,
        },
        "dossier": {"learning_id": dossier_id, "stored": persist_memory},
    }


def main() -> None:
    """CLI entry point: read JSON on stdin, write JSON on stdout.

    Protocol:
      run:            {"interview_text": str, "workspace": str,
                       "universes": int, "persist_memory": bool,
                       "name"/"age"/... overrides, "question": str}
      recall_dossier: {"operation": "recall_dossier", "character_name": str,
                       "workspace": str, "limit": int}
    """
    try:
        raw = sys.stdin.buffer.read().decode("utf-8")
    except Exception:
        raw = ""

    request = {}
    if raw:
        try:
            request = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            request = {}

    workspace = request.get("workspace", "alphazero")

    if request.get("operation") == "recall_dossier":
        character_name = request.get("character_name") or request.get("name") or ""
        dossiers = recall_advisor_dossier(
            character_name, workspace=workspace, limit=int(request.get("limit", 10))
        )
        print(json.dumps({
            "status": "success",
            "character_name": character_name,
            "result": {"count": len(dossiers), "dossiers": dossiers},
        }, default=str))
        return

    text = request.get("interview_text") or request.get("initial_interview_text") or ""
    if not text:
        fields = [f"{k}: {v}" for k, v in request.items()
                  if k in ("name", "age", "gender", "occupation") and v not in (None, "")]
        text = ", ".join(fields)

    result = run_advisor_panel(
        text,
        workspace=workspace,
        overrides=request,
        persist_memory=request.get("persist_memory", True),
        max_universes=int(request.get("max_universes", 100)),
    )
    print(json.dumps(result, default=str))


if __name__ == "__main__":
    main()
