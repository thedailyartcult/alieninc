"""AI Mentor - Synthesizes life guidance across finance, health, and growth.

This agent orchestrates the FinancialAdvisor, HealthCoach, and LifeCoach into a
single mentoring session, then layers career, relationship, education, and
personal-growth guidance on top. A deterministic heuristic core always
produces a mentoring plan (OLLAMA_DISABLE=1 for tests); the local Ollama LLM
answers open-ended questions when available.
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

from ai.life_coach import LifeCoachAgent, character_from_dict
from ai.advisor_dossier import build_continuity
from ai.financial_advisor import FinancialAdvisorAgent
from ai.health_coach import HealthCoachAgent


OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.environ.get("OLLAMA_MENTOR_MODEL", "llama3.2:latest")
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


class MentorAgent:
    """Synthesizes the specialist agents into one mentoring voice."""

    def __init__(self):
        self.financial = FinancialAdvisorAgent()
        self.health = HealthCoachAgent()
        self.life = LifeCoachAgent()
        self.mentoring_sessions: List[Dict[str, Any]] = []

    def provide_mentorship(self, character_data: Dict[str, Any],
                           question: str = "") -> Dict[str, Any]:
        """Full mentoring session: specialist advice + synthesis + answers."""
        character = character_from_dict(character_data)

        financial = self.financial.provide_advice(character_data, "general")
        health = self.health.provide_advice(character_data, "general")
        life = self.life.provide_advice(character_data, "general")

        focus = self._focus_areas(character)
        basic = {
            "assessment": self._assessment(character),
            "focus_areas": focus,
            "principles": self._principles(character),
            "action_plan": self._action_plan(character, focus),
            "weekly_routine": self._weekly_routine(character, focus),
            "mentor_response": self._default_response(character, question),
        }

        if question.strip():
            llm_answer = self._answer_with_llm(character, question)
            if llm_answer:
                basic["mentor_response"] = llm_answer

        self.mentoring_sessions.append({
            "timestamp": "now",
            "character": character.name,
            "question": question,
            "focus_areas": focus,
        })

        return {
            "character_name": character.name,
            "question": question,
            "assessment": basic["assessment"],
            "focus_areas": basic["focus_areas"],
            "principles": basic["principles"],
            "action_plan": basic["action_plan"],
            "weekly_routine": basic["weekly_routine"],
            "mentor_response": basic["mentor_response"],
            "financial_advisor": financial,
            "health_coach": health,
            "life_coach": life,
            "continuity": build_continuity(character_data, character.name),
        }

    # ------------------------------------------------------------------
    # Deterministic mentoring logic
    # ------------------------------------------------------------------

    def _focus_areas(self, character: Any) -> List[str]:
        focus = []
        if int(character.smarts or 50) < 60:
            focus.append("Skills & Education")
        if int(character.happiness or 50) < 55:
            focus.append("Relationships & Fulfillment")
        if int(character.health or 70) < 60:
            focus.append("Health & Energy")
        if float(character.net_worth or 0.0) < 20000:
            focus.append("Financial Foundation")
        if int(character.karma or 50) < 50:
            focus.append("Integrity & Community")
        if not focus:
            focus.append("Growth & Leverage")
        return focus

    def _assessment(self, character: Any) -> str:
        age = int(character.age or 0)
        if age < 25:
            return "A defining window — choices about skills, habits, and people now compound for decades."
        if age < 40:
            return "The compounding years — career and relationships are being built while you still have energy to redirect."
        if age < 60:
            return "The leverage years — experience is your edge; delegate, mentor others, and protect your health."
        return "The legacy years — focus on impact, mentorship, and financial security for the future."

    def _principles(self, character: Any) -> List[str]:
        return [
            "Energy follows health: protect sleep and movement before everything else.",
            "Money is a tool, not a score — a quiet emergency fund buys more freedom than a loud splurge.",
            "Skills compound like investments: study the craft that pays your rent and opens doors.",
            "Relationships are the real net worth — invest in people who grow when you grow.",
            "Make the important small and the small important — daily habits beat heroic effort.",
        ]

    def _action_plan(self, character: Any, focus: List[str]) -> Dict[str, str]:
        plan = {
            "immediate": "Choose one focus area and define a single concrete win for the week.",
            "30_days": "Establish one new daily habit tied to that focus area.",
            "90_days": "Finish one project or course that builds proof of skill.",
            "6_months": "Revisit the focus areas; rebalance effort toward the weakest.",
            "long_term": "Define the person you are becoming and let goals serve that person.",
        }
        if "Financial Foundation" in focus:
            plan["immediate"] = "Write a budget today; auto-save 20% before spending anything else."
        if "Health & Energy" in focus:
            plan["immediate"] = "Protect tonight's sleep and move for 15 minutes today."
        return plan

    def _weekly_routine(self, character: Any, focus: List[str]) -> Dict[str, str]:
        routine = {
            "monday": "Deep work on the top skill or project",
            "tuesday": "Network: one conversation with someone ahead of you",
            "wednesday": "Health: strength or cardio session",
            "thursday": "Financial review: track spending, save first",
            "friday": "Reflect and plan the next week",
            "saturday": "Relationships: quality time with key people",
            "sunday": "Rest, read, and reset",
        }
        return routine

    def _default_response(self, character: Any, question: str) -> str:
        focus = ", ".join(self._focus_areas(character))
        if not question.strip():
            return (
                f"{character.name}, the highest-leverage moves right now are {focus}. "
                "Start with the smallest daily habit, then let momentum carry the rest."
            )
        return (
            f"On '{question}': start with the honest version of your situation, "
            "choose one concrete step you can take this week, and treat the outcome as data, not verdict."
        )

    def _answer_with_llm(self, character: Any, question: str) -> Optional[str]:
        """Use Ollama for an open-ended mentoring answer; None keeps the default."""
        prompt = f"""
        You are a wise, direct mentor. The mentee is:
        - Name: {character.name}, Age: {character.age}
        - Occupation: {character.occupation}, Education: {character.education_level}
        - Happiness: {character.happiness}/100, Health: {character.health}/100
        - Smarts: {character.smarts}/100, Net worth: ${float(character.net_worth or 0.0):,.0f}

        Their question: {question}

        Answer in a warm, practical, specific way (2-4 sentences). Give one
        concrete action they can take this week. No markdown, no preamble.
        """
        raw = _ollama_generate(prompt)
        if not raw:
            return None
        return raw.strip()

    def get_insights(self) -> Dict[str, Any]:
        """Overview of the agent's capabilities."""
        return {
            "capabilities": [
                "Synthesizes financial, health, and life coaching",
                "Prioritizes growth focus areas",
                "Open-ended question answering",
                "Weekly mentoring routine",
                "LLM-personalized responses",
            ]
        }


def main() -> None:
    """CLI entry point: read JSON on stdin, write JSON on stdout.

    Protocol (used by the Rust MCP client and Go core integration):
      input:  {"character_json": str|object, "question": str}
      output: {"status": "success", "result": {...mentoring...}}

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

    question = request.get("question", "") or ""
    agent = MentorAgent()
    result = agent.provide_mentorship(character_data, question)
    print(json.dumps({"status": "success", "result": result}, default=str))


if __name__ == "__main__":
    main()
