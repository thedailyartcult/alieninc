"""AI Financial Advisor - Portfolio, savings, and debt guidance.

This agent turns a character's financial state (net worth, portfolio, debt,
income, age) into concrete, actionable advice: budget and savings rules,
debt payoff priorities, an age-appropriate allocation recommendation, and an
emergency-fund plan. A deterministic heuristic core always produces advice
(OLLAMA_DISABLE=1 for tests); the local Ollama LLM personalizes it on top
when available.
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
from ai.advisor_dossier import build_continuity

from finance.portfolio import STRATEGIES


OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.environ.get("OLLAMA_FINANCIAL_MODEL", "llama3.2:latest")
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


class FinancialAdvisorAgent:
    """Provides financial advice based on a character's financial state."""

    def __init__(self):
        self.advice_sessions: List[Dict[str, Any]] = []
        self.knowledge_base: Dict[str, Any] = {
            "strategies": STRATEGIES,
            "emergency_fund_months": 6,
            "savings_rate_target": 0.20,
            "debt_ratio_threshold": 0.35,
        }

    # ------------------------------------------------------------------
    # Deterministic analysis
    # ------------------------------------------------------------------

    def analyze_financial_state(self, character: Any) -> Dict[str, Any]:
        """Assess net worth, debt load, portfolio health, and risk profile."""
        net_worth = float(character.net_worth or 0.0)
        money = float(character.money or 0.0)
        debt = float(character.debt or 0.0)
        portfolio = float(character.portfolio_value or 0.0)
        income = self._estimate_income(character)
        age = int(character.age or 0)

        monthly_expenses = max(1.0, income / 12 * 0.6)
        emergency_fund = money if money > 0 else max(0.0, net_worth * 0.1)
        emergency_months = round(emergency_fund / monthly_expenses, 1)

        debt_ratio = round(debt / income, 2) if income > 0 else (1.0 if debt > 0 else 0.0)

        return {
            "net_worth": net_worth,
            "liquid_cash": money,
            "debt": debt,
            "debt_to_income_ratio": debt_ratio,
            "portfolio_value": portfolio,
            "estimated_monthly_income": round(income / 12, 2),
            "emergency_fund_months": emergency_months,
            "risk_profile": self._risk_profile(age, net_worth, debt_ratio),
            "recommended_strategy": self._recommended_strategy(age, net_worth),
        }

    def _estimate_income(self, character: Any) -> float:
        """Rough annual income proxy from education/occupation."""
        base = {
            "None": 25000, "Primary": 30000, "High School": 45000, "University": 70000,
        }.get(character.education_level, 45000)
        occupation = str(character.occupation or "").lower()
        multipliers = {
            "doctor": 5.0, "physician": 5.0, "surgeon": 6.0, "lawyer": 3.0,
            "engineer": 2.0, "nurse": 1.6, "teacher": 1.2, "manager": 2.2,
            "developer": 2.5, "financ": 2.5, "entrepreneur": 2.0, "executive": 4.0,
        }
        for key, mult in multipliers.items():
            if key in occupation:
                return base * mult
        return base

    def _risk_profile(self, age: int, net_worth: float, debt_ratio: float) -> str:
        if debt_ratio > 0.35:
            return "conservative"
        if age < 30 and net_worth >= 0:
            return "aggressive"
        if age < 50:
            return "moderate"
        return "conservative"

    def _recommended_strategy(self, age: int, net_worth: float) -> str:
        profile = self._risk_profile(age, net_worth, 0.0)
        if profile == "aggressive":
            return "hyper_growth"
        if profile == "conservative":
            return "recession_defense"
        if net_worth > 200000:
            return "dividend_income"
        return "balanced"

    # ------------------------------------------------------------------
    # Advice generation
    # ------------------------------------------------------------------

    def provide_advice(self, character_data: Dict[str, Any],
                       situation: str = "general") -> Dict[str, Any]:
        """Financial advice from a plain dict (MCP JSON protocol)."""
        character = character_from_dict(character_data)
        state = self.analyze_financial_state(character)
        basic = {
            "assessment": self._assessment(character, state),
            "recommendations": self._recommendations(character, state, situation),
            "action_plan": self._action_plan(character, state),
            "allocation": self._allocation_advice(character, state),
            "encouragement": self._encouragement(character, state),
        }
        advice = self._enhance_with_llm(character, state, basic)
        if not advice:
            advice = basic

        self.advice_sessions.append({
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
            "action_plan": advice["action_plan"],
            "allocation": advice["allocation"],
            "encouragement": advice["encouragement"],
            "continuity": build_continuity(character_data, character.name),
        }

    def _assessment(self, character: Any, state: Dict[str, Any]) -> str:
        nw = state["net_worth"]
        if nw < 0:
            return "Net worth is negative — the priority is eliminating debt and rebuilding a positive balance before investing."
        if state["emergency_fund_months"] < 3:
            return "Liquid savings cover less than 3 months of expenses — build the emergency fund before aggressive investing."
        if nw >= 100000:
            return "The financial foundation is solid; focus shifts to growth, tax efficiency, and long-term wealth preservation."
        return "A reasonable starting point — the next step is consistent saving and a diversified allocation."

    def _recommendations(self, character: Any, state: Dict[str, Any],
                         situation: str) -> List[str]:
        recommendations: List[str] = []
        debt = state["debt"]
        nw = state["net_worth"]
        months = state["emergency_fund_months"]
        profile = state["risk_profile"]

        if debt > 0:
            recommendations.append(
                f"Pay off the {debt:,.0f} debt aggressively (snowball or avalanche) — debt-to-income is {state['debt_to_income_ratio']:.2f}."
            )
        if months < 3:
            recommendations.append(
                f"Build an emergency fund covering 6 months of expenses (currently {months} month(s))."
            )
        if nw >= 0:
            recommendations.append(
                f"Automate saving at least 20% of income into the {state['recommended_strategy']} allocation."
            )
        if profile == "conservative" and nw > 0:
            recommendations.append("Prioritize capital preservation: bonds, dividend stocks, and gold over volatile assets.")

        situation_advice = {
            "general": ["Review your budget monthly and track every peso for 30 days."],
            "debt_reduction": ["Negotiate interest rates with creditors and consolidate high-interest debt."],
            "investment": ["Dollar-cost average monthly instead of timing the market; rebalance once a year."],
            "retirement": ["Maximize tax-advantaged retirement accounts and let compounding run."],
            "buying_home": ["Target a down payment of at least 20% to avoid mortgage insurance."],
            "emergency": ["Liquidate volatile positions first; keep only essential expenses funded."],
        }
        recommendations.extend(situation_advice.get(situation, situation_advice["general"]))
        return recommendations

    def _action_plan(self, character: Any, state: Dict[str, Any]) -> Dict[str, str]:
        return {
            "immediate": "Create a written budget; list all debts and expenses.",
            "30_days": "Cut discretionary spending to raise the savings rate above 20%.",
            "90_days": "Fund the emergency reserve to 3 months of expenses.",
            "6_months": "Fully fund the 6-month emergency fund and start automated investing.",
            "long_term": "Rebalance quarterly and review the allocation once a year.",
        }

    def _allocation_advice(self, character: Any, state: Dict[str, Any]) -> Dict[str, Any]:
        strategy_name = state["recommended_strategy"]
        info = STRATEGIES.get(strategy_name, STRATEGIES["balanced"])
        return {
            "strategy": strategy_name,
            "name": info["name"],
            "allocations": info["allocations"],
            "expected_return": info["expected_return"],
            "volatility": info["volatility"],
        }

    def _encouragement(self, character: Any, state: Dict[str, Any]) -> str:
        if state["net_worth"] < 0:
            return "Debt is a chapter, not the whole book. Every payment moves the story forward."
        if state["emergency_fund_months"] < 3:
            return "Building the reserve first is the disciplined move — the markets will still be there."
        return "Consistency beats brilliance. Keep the plan simple and show up every month."

    def _enhance_with_llm(self, character: Any, state: Dict[str, Any],
                          basic: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Use Ollama to personalize the advice; None keeps the heuristic core."""
        prompt = f"""
        You are a prudent financial advisor. Given this character profile and the
        heuristic advice generated for them, enhance the advice to be deeply
        personalized and actionable.

        Character profile:
        - Name: {character.name}, Age: {character.age}
        - Occupation: {character.occupation}, Education: {character.education_level}
        - Net worth: ${state['net_worth']:,.0f}, Debt: ${state['debt']:,.0f}
        - Emergency fund: {state['emergency_fund_months']} months
        - Risk profile: {state['risk_profile']}

        Basic advice: {json.dumps(basic, default=str)}

        Return ONLY valid JSON with keys:
        - assessment (string): personalized financial assessment
        - recommendations (array of strings): specific advice
        - action_plan (object): immediate/30_days/90_days/6_months/long_term steps
        - allocation (object): strategy, name, allocations
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
        for key in ("assessment", "recommendations", "action_plan", "allocation", "encouragement"):
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
                "Net worth and debt assessment",
                "Emergency fund planning",
                "Age-appropriate allocation advice",
                "Situation-specific recommendations",
                "LLM-personalized guidance",
            ],
            "strategies": list(STRATEGIES.keys()),
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
    agent = FinancialAdvisorAgent()
    advice = agent.provide_advice(character_data, situation)
    print(json.dumps({"status": "success", "result": advice}, default=str))


if __name__ == "__main__":
    main()
