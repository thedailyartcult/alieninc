"""AI Health Coach - Wellness, fitness, and lifestyle guidance.

This agent turns a character's health state (health, happiness, smarts,
karma, age) into concrete, actionable wellness advice: exercise and sleep
routines, stress management, diet habits, and a weekly plan. A deterministic
heuristic core always produces advice (OLLAMA_DISABLE=1 for tests); the local
Ollama LLM personalizes it on top when available.
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Any, Dict, List, Optional

if __name__ == "__main__" and __package__ is None:
    _AI_DIR = os.path.dirname(os.path.abspath(__file__))
    _REPO_ROOT = os.path.dirname(_AI_DIR)
    sys.path.insert(0, _AI_DIR)
    if _REPO_ROOT not in sys.path:
        sys.path.insert(0, _REPO_ROOT)

from ai.life_coach import character_from_dict


OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.environ.get("OLLAMA_HEALTH_MODEL", "llama3.2:latest")
OLLAMA_TIMEOUT = int(os.environ.get("OLLAMA_TIMEOUT", "60"))


def _ollama_generate(prompt: str, model: Optional[str] = None,
                     timeout: Optional[int] = None) -> Optional[str]:
    """Call the local Ollama server; return raw text or None on any failure.

    Honors OLLAMA_DISABLE=1 to skip the LLM (deterministic mode for tests).
    """
    if os.environ.get("OLLAMA_DISABLE") == "1":
        return None
    try:
        import requests
        resp = requests.post(
            OLLAMA_URL,
            json={"model": model or OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=timeout if timeout is not None else OLLAMA_TIMEOUT,
        )
        if resp.status_code == 200:
            return resp.json().get("response")
    except Exception:
        pass
    return None


def _parse_llm_json(raw: str) -> Any:
    """Best-effort parse of an LLM response into JSON."""
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        pass
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except (json.JSONDecodeError, TypeError):
            pass
    return None


class HealthCoachAgent:
    """Provides health, fitness, and lifestyle coaching."""

    def __init__(self):
        self.coaching_sessions: List[Dict[str, Any]] = []
        self.knowledge_base: Dict[str, Any] = {
            "exercise_minutes": 150,
            "sleep_hours": "7-9",
            "water_glasses": 8,
        }

    # ------------------------------------------------------------------
    # Deterministic analysis
    # ------------------------------------------------------------------

    def analyze_health_state(self, character: Any) -> Dict[str, Any]:
        """Assess overall health, risks, stress, and lifestyle habits."""
        health = int(character.health or 50)
        happiness = int(character.happiness or 50)
        age = int(character.age or 0)

        category = self._health_category(health)
        risks = self._risk_factors(character)
        stress = 100 - min(100, max(0, happiness + 10))

        return {
            "health_score": health,
            "happiness_score": happiness,
            "health_category": category,
            "stress_level": stress,
            "risk_factors": risks,
            "exercise_recommendation": self._exercise_recommendation(age, health),
            "sleep_recommendation": self.knowledge_base["sleep_hours"],
        }

    def _health_category(self, health: int) -> str:
        if health >= 80:
            return "excellent"
        if health >= 60:
            return "good"
        if health >= 40:
            return "fair"
        return "poor"

    def _risk_factors(self, character: Any) -> List[str]:
        risks = []
        health = int(character.health or 50)
        happiness = int(character.happiness or 50)
        age = int(character.age or 0)
        if health < 40:
            risks.append("Chronic health risk — professional medical check-up recommended")
        if happiness < 40:
            risks.append("Low mood — stress and burnout are likely contributing factors")
        if age > 50 and health < 60:
            risks.append("Age-related decline — prioritize screening and strength training")
        if happiness > 70 and health < 40:
            risks.append("Happiness masking physical strain — do not ignore physical symptoms")
        if not risks:
            risks.append("No major risk factors detected")
        return risks

    def _exercise_recommendation(self, age: int, health: int) -> str:
        if age > 60:
            return "30 min daily of low-impact activity (walking, swimming, tai chi)"
        if health < 40:
            return "15 min daily walk first; build up gradually toward 30 min"
        return "150+ minutes/week of moderate cardio plus two strength sessions"

    # ------------------------------------------------------------------
    # Advice generation
    # ------------------------------------------------------------------

    def provide_advice(self, character_data: Dict[str, Any],
                       situation: str = "general") -> Dict[str, Any]:
        """Health coaching from a plain dict (MCP JSON protocol)."""
        character = character_from_dict(character_data)
        state = self.analyze_health_state(character)
        basic = {
            "assessment": self._assessment(character, state),
            "recommendations": self._recommendations(character, state, situation),
            "weekly_plan": self._weekly_plan(character, state),
            "action_plan": self._action_plan(character, state),
            "encouragement": self._encouragement(character, state),
        }
        advice = self._enhance_with_llm(character, state, basic)
        if not advice:
            advice = basic

        self.coaching_sessions.append({
            "timestamp": "now",
            "character": character.name,
            "situation": situation,
            "recommendations": basic["recommendations"],
        })

        return {
            "character_name": character.name,
            "situation": situation,
            "analysis": state,
            "assessment": advice["assessment"],
            "recommendations": advice["recommendations"],
            "weekly_plan": advice["weekly_plan"],
            "action_plan": advice["action_plan"],
            "encouragement": advice["encouragement"],
        }

    def _assessment(self, character: Any, state: Dict[str, Any]) -> str:
        category = state["health_category"]
        if category == "excellent":
            return "You are in excellent condition — the goal is maintenance, consistency, and prevention."
        if category == "good":
            return "Health is solid with clear room to improve fitness, sleep, and stress resilience."
        if category == "fair":
            return "Health needs active attention — small daily habits will compound into real gains."
        return "Health is fragile right now. Rest, medical guidance, and gentle movement come first."

    def _recommendations(self, character: Any, state: Dict[str, Any],
                         situation: str) -> List[str]:
        recommendations: List[str] = []
        health = state["health_score"]
        happiness = state["happiness_score"]
        stress = state["stress_level"]

        if health < 40:
            recommendations.append("See a healthcare professional before starting any intense program.")
        recommendations.append(
            f"Aim for {self.knowledge_base['sleep_hours']} hours of sleep and {self.knowledge_base['water_glasses']} glasses of water daily."
        )
        recommendations.append(state["exercise_recommendation"])
        if stress > 60:
            recommendations.append("Incorporate a 10-minute daily mindfulness or breathing practice to lower stress.")
        if happiness < 50:
            recommendations.append("Schedule weekly social time — connection is a measurable health input.")

        situation_advice = {
            "general": ["Track sleep, steps, and mood for two weeks to find your baseline."],
            "weight_loss": ["Create a modest calorie deficit and add daily walking; avoid crash diets."],
            "fitness": ["Progressively overload workouts — add small weight or reps each week."],
            "stress": ["Set work boundaries, take real lunch breaks, and protect sleep as a non-negotiable."],
            "sleep": ["Keep a fixed wake time, no screens an hour before bed, and a cool dark room."],
            "recovery": ["Prioritize rest days and protein; sleep is where adaptation happens."],
        }
        recommendations.extend(situation_advice.get(situation, situation_advice["general"]))
        return recommendations

    def _weekly_plan(self, character: Any, state: Dict[str, Any]) -> Dict[str, str]:
        return {
            "monday": "30 min cardio + hydration focus",
            "tuesday": "Strength session (full body, light weights)",
            "wednesday": "Active rest: walk and stretch 20 min",
            "thursday": "30 min cardio + strength session",
            "friday": "Flexibility: yoga or mobility routine",
            "saturday": "Social activity or outdoor recreation",
            "sunday": "Rest, meal prep, and sleep schedule reset",
        }

    def _action_plan(self, character: Any, state: Dict[str, Any]) -> Dict[str, str]:
        return {
            "immediate": "Schedule 15 minutes of movement today; set a consistent wake time.",
            "30_days": "Hit 150 minutes of weekly exercise and a fixed sleep window.",
            "90_days": "Introduce two weekly strength sessions and a daily stress practice.",
            "6_months": "Reassess health metrics; adjust the plan based on progress.",
            "long_term": "Build a sustainable routine that survives busy weeks.",
        }

    def _encouragement(self, character: Any, state: Dict[str, Any]) -> str:
        if state["health_category"] == "poor":
            return "Every journey starts with one kind, small step. Rest is productive too."
        return "Health is built one ordinary day at a time — consistency quietly outperforms intensity."

    def _enhance_with_llm(self, character: Any, state: Dict[str, Any],
                          basic: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Use Ollama to personalize the advice; None keeps the heuristic core."""
        prompt = f"""
        You are a warm, evidence-based health coach. Given this character profile
        and the heuristic advice generated for them, enhance the advice to be
        deeply personalized and actionable.

        Character profile:
        - Name: {character.name}, Age: {character.age}
        - Health: {state['health_score']}/100, Happiness: {state['happiness_score']}/100
        - Stress level: {state['stress_level']}/100
        - Health category: {state['health_category']}
        - Risk factors: {state['risk_factors']}

        Basic advice: {json.dumps(basic, default=str)}

        Return ONLY valid JSON with keys:
        - assessment (string): personalized health assessment
        - recommendations (array of strings): specific advice
        - weekly_plan (object): monday..sunday activities
        - action_plan (object): immediate/30_days/90_days/6_months/long_term steps
        - encouragement (string): one motivating line

        Do not include markdown or explanation.
        """
        raw = _ollama_generate(prompt)
        if not raw:
            return None
        parsed = _parse_llm_json(raw)
        if not isinstance(parsed, dict):
            return None
        out = dict(basic)
        for key in ("assessment", "recommendations", "weekly_plan", "action_plan", "encouragement"):
            value = parsed.get(key)
            if key == "recommendations" and isinstance(value, list) and value:
                out[key] = [str(item) for item in value]
            elif isinstance(value, dict) and value:
                out[key] = value
            elif isinstance(value, str) and value.strip():
                out[key] = value.strip()
        return out

    def get_insights(self) -> Dict[str, Any]:
        """Overview of the agent's capabilities."""
        return {
            "capabilities": [
                "Health risk assessment",
                "Exercise and sleep programming",
                "Stress management",
                "Weekly wellness planning",
                "LLM-personalized guidance",
            ]
        }


def main() -> None:
    """CLI entry point: read JSON on stdin, write JSON on stdout.

    Protocol (used by the Rust MCP client and Go core integration):
      input:  {"character_json": str|object, "situation": str}
      output: {"status": "success", "result": {...advice...}}

    Env: OLLAMA_DISABLE=1 skips the LLM (pure deterministic mode).
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

    character_data = request.get("character_json") or request.get("character") or {}
    if isinstance(character_data, str):
        try:
            character_data = json.loads(character_data)
        except (json.JSONDecodeError, TypeError):
            character_data = {}

    situation = request.get("situation", "general")
    agent = HealthCoachAgent()
    advice = agent.provide_advice(character_data, situation)
    print(json.dumps({"status": "success", "result": advice}, default=str))


if __name__ == "__main__":
    main()
