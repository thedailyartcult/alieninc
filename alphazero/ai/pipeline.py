"""AI Pipeline — end-to-end agent workflow.

Orchestrates all five AI agents into a single pipeline:

    interview  ->  persona seeds a multiverse simulation
    ->  analyze  ->  narrate the best universe
    ->  memory   (learnings stored across sessions)

Used by the web platform (/api/ai/pipeline) and available as a CLI
for parity with the other agents.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Dict, Optional

from engine.character import Gender
from engine.simulation import SimulationOrchestrator, SimulationConfig

from ai.interview_agent import InterviewAgent
from ai.life_coach import LifeCoachAgent
from ai.decision_assistant import DecisionAssistantAgent
from ai.storyteller import StorytellerAgent
from ai.memory_system import MemorySystemAgent


def _clamp(value: Any, default: int = 50, lo: int = 0, hi: int = 100) -> int:
    """Coerce a persona attribute to a bounded int."""
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return default


def _persona_to_config(persona: Dict[str, Any],
                       overrides: Dict[str, Any]) -> SimulationConfig:
    """Map an interview persona onto a SimulationConfig."""
    gender_raw = persona.get("gender", "male")
    try:
        gender = Gender[gender_raw.upper()]
    except (KeyError, AttributeError):
        gender = Gender.MALE

    config = SimulationConfig(
        name=persona.get("name", "Player"),
        age=_clamp(persona.get("age", overrides.get("age", 20)), 20, 0, 100),
        gender=gender,
        birthplace=persona.get("birthplace", "Manila"),
        current_city=persona.get("current_city", "Manila"),
        happiness=_clamp(persona.get("happiness", 50)),
        health=_clamp(persona.get("health", 70)),
        smarts=_clamp(persona.get("smarts", 50)),
        looks=_clamp(persona.get("looks", 50)),
        karma=_clamp(persona.get("karma", 50)),
        seed=int(overrides.get("seed", 42)),
        num_universes=int(overrides.get("universes", 100)),
        max_workers=int(overrides.get("workers", 4)),
        portfolio_strategy=overrides.get("strategy", "balanced"),
        initial_portfolio=float(overrides.get("portfolio", 100000)),
    )
    return config


def run_ai_pipeline(
    interview_text: str,
    workspace: str = "default",
    overrides: Optional[Dict[str, Any]] = None,
    persist_memory: bool = True,
    max_universes: int = 100,
) -> Dict[str, Any]:
    """Run the full AI pipeline and return a combined result."""
    overrides = overrides or {}
    universes = max(10, min(max_universes, int(overrides.get("universes", 50))))

    # 1. Interview — build persona
    interview = InterviewAgent()
    persona = interview.extract_persona_from_text(interview_text)
    for field in ("name", "age", "gender", "occupation", "birthplace", "current_city"):
        explicit = overrides.get(field)
        if explicit not in (None, ""):
            persona[field] = explicit

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
    }

    # 3. Analyze — decision assistant interprets outcomes
    decision = DecisionAssistantAgent()
    analysis = decision.analyze_simulation_outcomes(simulation_results)

    # 4. Coach — life advice for the persona
    coach = LifeCoachAgent()
    coaching = coach.provide_advice(persona, overrides.get("situation", "general"))

    # 5. Narrate — story of the best universe
    storyteller = StorytellerAgent()
    from engine.character import Character

    character = Character(
        name=persona.get("name", "Player"),
        age=int(report.best_net_worth.steps[-1].age) if report.best_net_worth.steps else config.age,
        gender=config.gender,
        happiness=report.best_net_worth.final_happiness,
        health=report.best_net_worth.final_health,
        net_worth=report.best_net_worth.final_net_worth,
    )
    narrative = storyteller.generate_character_narrative(character, best)

    # 6. Memory — persist learnings across sessions
    learning_id = None
    if persist_memory:
        memory = MemorySystemAgent(workspace=workspace)
        learning_id = memory.store_learning({
            "type": "ai_pipeline",
            "persona": persona,
            "best": best,
            "convergence_rate": report.convergence_rate,
            "sharpe_ratio": report.sharpe_ratio,
            "insight": analysis.get("summary", {}),
            "recommendations": analysis.get("recommendations", []),
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
        "analysis": analysis,
        "coaching": coaching,
        "narrative": {"character_name": character.name,
                      "story": narrative},
        "learning_id": learning_id,
    }


def main() -> None:
    """CLI entry point: read JSON on stdin, write JSON on stdout.

    Protocol:
      input:  {"interview_text": str, "workspace": str,
               "universes": int, "persist_memory": bool, ...}
      output: {"status": "success", ...pipeline stages...}
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

    text = request.get("interview_text") or request.get("initial_interview_text") or ""
    if not text:
        fields = [f"{k}: {v}" for k, v in request.items()
                  if k in ("name", "age", "gender", "occupation") and v not in (None, "")]
        text = ", ".join(fields)

    result = run_ai_pipeline(
        text,
        workspace=request.get("workspace", "default"),
        overrides=request,
        persist_memory=request.get("persist_memory", True),
        max_universes=int(request.get("max_universes", 100)),
    )
    print(json.dumps(result, default=str))


if __name__ == "__main__":
    main()
