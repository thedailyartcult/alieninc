"""AI Interview Agent - Profiles personality and seeds Character objects for simulations.

This agent conducts interviews to collect personality data, which is then used to
seed Character objects for Alpha Zero multiverse simulations.
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Dict, List, Optional, Any

from engine.character import Character, Gender
from engine.social_variables import ALL_VARIABLES


OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:latest")
OLLAMA_TIMEOUT = int(os.environ.get("OLLAMA_TIMEOUT", "30"))


def _ollama_generate(prompt: str, model: Optional[str] = None,
                     timeout: Optional[int] = None) -> Optional[str]:
    """Call the local Ollama server; return raw text or None on any failure."""
    try:
        import requests
        resp = requests.post(
            OLLAMA_URL,
            json={"model": model or OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=timeout if timeout is not None else OLLAMA_TIMEOUT,
        )
        if resp.status_code != 200:
            return None
        return resp.json().get("response")
    except Exception:
        return None


class InterviewAgent:
    """Conducts personality interviews and profiles 34 social variables."""

    def __init__(self):
        self.interview_history: List[Dict[str, Any]] = []
        self.current_profile: Dict[str, Any] = {}

    def extract_persona_from_text(self, text: str) -> Dict[str, Any]:
        """Extract persona information from interview text using LLM-like processing.

        Strategy: the deterministic regex extraction is always the reliable base
        (guaranteed 34-variable coverage). When the local Ollama LLM is
        available, its higher-quality extractions are merged on top so the
        persona keeps full variable coverage while gaining LLM personalization.
        """
        persona = self._extract_with_regex(text)

        llm = self._extract_with_llm(text)
        if not isinstance(llm, dict) or not llm:
            return persona

        proper_name = re.compile(r"^[A-Z][a-z]+(?: [A-Z][a-z]+)*$")

        # Name: only overlay when the regex found nothing AND the LLM name
        # looks like a real capitalized proper name (small local models
        # frequently hallucinate tokens like "Interviewer").
        llm_name = llm.get("name")
        if (persona.get("name") in (None, "", "Unknown")
                and isinstance(llm_name, str)
                and proper_name.match(llm_name.strip())):
            persona["name"] = llm_name.strip()

        # Occupation / education / location: overlay when LLM answered.
        for field in ("occupation", "education", "birthplace", "current_city"):
            value = llm.get(field)
            if isinstance(value, str) and value.strip() and value.strip().lower() != "unknown":
                persona[field] = value.strip()

        # Desires and inferred traits: overlay when non-empty.
        for field in ("desires", "inferred_traits"):
            value = llm.get(field)
            if isinstance(value, (dict, list)) and value:
                persona[field] = value

        # Numeric stats: only trust the LLM when the regex stayed at its
        # default, otherwise the deterministic extraction wins.
        defaults = {"happiness": 50, "health": 70, "smarts": 50, "looks": 50, "karma": 50}
        for field, default in defaults.items():
            if persona.get(field) != default:
                continue
            value = llm.get(field)
            if isinstance(value, (int, float)) and 0 <= int(value) <= 100:
                persona[field] = int(value)

        age_value = llm.get("age")
        if persona.get("age") in (None, 0, 25) and isinstance(age_value, (int, float)) and 0 < int(age_value) <= 120:
            persona["age"] = int(age_value)

        # Social variables: overlay only when LLM returned broad coverage.
        if llm.get("social_variables") and len(llm["social_variables"]) > 5:
            merged = dict(persona.get("social_variables", {}))
            for var_id, value in llm["social_variables"].items():
                if var_id in merged and isinstance(value, (int, float)):
                    merged[var_id] = max(0, min(100, int(float(value))))
            persona["social_variables"] = merged

        return persona

    def _extract_with_llm(self, text: str) -> Dict[str, Any]:
        """Use Ollama to extract the full persona in a single JSON pass."""
        prompt = f"""
        Extract personality information from this interview text.

        Interview: {text}

        Return ONLY valid JSON with these keys:
        - name: person's name
        - age: age as integer
        - gender: male, female, or non_binary
        - birthplace: place of birth
        - current_city: current city
        - occupation: job or profession, or "Unemployed"
        - education: "None", "Primary", "High School", or "University"
        - happiness: 0-100 (default 50)
        - health: 0-100 (default 70)
        - smarts: 0-100 (default 50)
        - looks: 0-100 (default 50)
        - karma: 0-100 (default 50)
        - social_variables: object with numeric 0-100 values
        - desires: object with desire strengths as numbers 0.0-1.0
        - inferred_traits: array of strings

        Do not include any explanation or markdown.
        """
        raw = _ollama_generate(prompt)
        if not raw:
            return {"name": "Unknown"}
        return self._parse_llm_json(raw)

    def _infer_with_llm(self, text: str) -> Dict[str, int]:
        """Use Ollama for the 34 social variables, falling back to regex."""
        variables = self._infer_social_variables(text)
        prompt = (
            "Rate this person on each social/psychological dimension from 0-100 "
            "based on the interview text.\n\n"
            f"Interview: {text}\n\n"
            f"Variables: {json.dumps([v.var_id for v in ALL_VARIABLES])}\n\n"
            "Return ONLY a JSON object mapping each variable id to an integer 0-100."
        )
        raw = _ollama_generate(prompt)
        if not raw:
            return variables
        parsed = self._parse_llm_json(raw)
        if not isinstance(parsed, dict):
            return variables
        merged = dict(variables)
        for var_id, value in parsed.items():
            if var_id in merged and isinstance(value, (int, float)):
                merged[var_id] = max(0, min(100, int(float(value))))
        return merged

    @staticmethod
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

    def _extract_with_regex(self, text: str) -> Dict[str, Any]:
        """Rule-based persona extraction (deterministic fallback)."""
        persona = {
            "name": self._extract_name(text),
            "age": self._extract_age(text),
            "gender": self._extract_gender(text),
            "birthplace": self._extract_location(text, "birthplace"),
            "current_city": self._extract_location(text, "current city"),
            "occupation": self._extract_occupation(text),
            "education": self._extract_education(text),
            "happiness": self._extract_happiness(text),
            "health": self._extract_health(text),
            "smarts": self._extract_intelligence(text),
            "looks": self._extract_looks(text),
            "karma": self._extract_karma(text),
            "social_variables": self._infer_social_variables(text),
            "desires": self._extract_desires(text),
        }
        return persona

    def _extract_name(self, text: str) -> str:
        """Extract name from text."""
        patterns = [
            r"(?:my name is|I'm|I am|call me) ([A-Z][a-z]+(?: [A-Z][a-z]+)*)",
            r"^([A-Z][a-z]+ [A-Z][a-z]+)$",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                return match.group(1)
        return "Unknown"

    def _extract_age(self, text: str) -> int:
        """Extract age from text."""
        age_patterns = [
            r"(\d{1,2})\s*(?:years old|year old|y/o|\(age\))",
            r"age\s*(?:is|:)?\s*(\d{1,2})",
        ]
        for pattern in age_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return int(match.group(1))
        return 25

    def _extract_gender(self, text: str) -> str:
        """Extract gender from text."""
        if re.search(r"\b(man|male|boy|he|himself)\b", text, re.IGNORECASE):
            return Gender.MALE.value
        elif re.search(r"\b(woman|female|girl|she|herself)\b", text, re.IGNORECASE):
            return Gender.FEMALE.value
        elif re.search(r"\b(non.?binary|non.?bin|nonbinary)\b", text, re.IGNORECASE):
            return Gender.NON_BINARY.value
        return Gender.MALE.value

    def _extract_location(self, text: str, field: str) -> str:
        """Extract location information from text."""
        patterns = {
            "birthplace": r"(?:born in|birthplace|from) ([^.\\n]+)",
            "current city": r"(?:live in|current city|currently in|based in) ([^.\\n]+)",
        }
        if field in patterns:
            match = re.search(patterns[field], text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return "Unknown"

    def _extract_occupation(self, text: str) -> str:
        """Extract occupation from text."""
        patterns = [
            r"(?:I'm|am) (?:a|an) ([^.\n]+?)(?:\.|\n|\r|, and)",
            r"work(?:s|s)?\s+(?:as\s+)?([^.\n]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return "Unemployed"

    def _extract_education(self, text: str) -> str:
        """Extract education level from text."""
        if re.search(r"\b(university|college|uni|bac[kc]h(?:elor)?|master|ph\.?d\.?)\b", text, re.IGNORECASE):
            return "University"
        elif re.search(r"\b(high school|secondary|diploma|ged)\b", text, re.IGNORECASE):
            return "High School"
        elif re.search(r"\b(primary|elementary|middle school)\b", text, re.IGNORECASE):
            return "Primary"
        return "None"

    def _extract_happiness(self, text: str) -> int:
        """Extract happiness level (0-100) from text."""
        patterns = [
            r"(?:happiness|happy|joy|contentment)\s*(?:is|:)?\s*(\d{1,3})%?",
            r"(\d{1,3})\s*(?:%\s*happy|happy\s*%)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value = int(match.group(1))
                return max(0, min(100, value))
        return 50

    def _extract_health(self, text: str) -> int:
        """Extract health level (0-100) from text."""
        if re.search(r"\b(ill|sick|unhealthy|poor health|bad health)\b", text, re.IGNORECASE):
            return 30
        elif re.search(r"\b(healthy|fit|active|energetic)\b", text, re.IGNORECASE):
            return 80
        return 70

    def _extract_intelligence(self, text: str) -> int:
        """Extract smarts level (0-100) from text."""
        patterns = [
            r"(?:smart|intelligent|brainy|clever)\s*(?:is|:)?\s*(\d{1,3})?",
            r"I'?m (?:a |an )?(\d{1,3})? smart",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value = int(match.group(1) or 70)
                return max(0, min(100, value))
        return 50

    def _extract_looks(self, text: str) -> int:
        """Extract looks level (0-100) from text."""
        if re.search(r"\b(ugly|unattractive|plain|ugly|homely)\b", text, re.IGNORECASE):
            return 20
        elif re.search(r"\b(handsome|beautiful|attractive|pretty|stunning)\b", text, re.IGNORECASE):
            return 80
        return 50

    def _extract_karma(self, text: str) -> int:
        """Extract karma level (0-100) from text."""
        if re.search(r"\b(evil|bad|mean|nasty|selfish)\b", text, re.IGNORECASE):
            return 20
        elif re.search(r"\b(good|kind|nice|generous|altruistic)\b", text, re.IGNORECASE):
            return 80
        return 50

    def _infer_social_variables(self, text: str) -> Dict[str, int]:
        """Infer social variable values from text content."""
        variables = {}

        for var in ALL_VARIABLES:
            inferred = self._infer_single_variable(var, text)
            variables[var.var_id] = inferred

        return variables

    def _infer_single_variable(self, var: Any, text: str) -> int:
        """Infer a single social variable value from text."""
        value = 50  # baseline

        var_id = var.var_id
        var_name = var.name
        var_layer = var.layer

        content_lower = text.lower()

        if var_layer == "personal":
            if "ambition" in var_id.lower():
                if any(word in content_lower for word in ["driven", "goal", "ambitious"]):
                    value = 75
                elif any(word in content_lower for word in ["lazy", "indifferent", "give up"]):
                    value = 25
            elif "self-esteem" in var_id.lower():
                if any(word in content_lower for word in ["confident", "self-assured"]):
                    value = 80
                elif any(word in content_lower for word in ["insecure", "low self", "don't trust"]):
                    value = 20

        elif var_layer == "interpersonal":
            if "trust" in var_id.lower():
                if any(word in content_lower for word in ["trusting", "believe", "rely"]):
                    value = 75
                elif any(word in content_lower for word in ["skeptical", "distrust", "careful"]):
                    value = 25

        elif var_layer == "social":
            if "community ties" in var_name.lower():
                if any(word in content_lower for word in ["community", "neighbors", "neighbors"]):
                    value = 75
                elif any(word in content_lower for word in ["isolated", "alone", "lonely"]):
                    value = 25

        elif var_layer == "national":
            if "economic climate" in var_name.lower():
                if any(word in content_lower for word in ["economy", "financial", "money"]):
                    value = 60
                elif any(word in content_lower for word in ["poor", "struggle", "financial stress"]):
                    value = 30

        elif var_layer == "international":
            if "technology access" in var_name.lower():
                if any(word in content_lower for word in ["tech", "technology", "internet"]):
                    value = 70
                elif any(word in content_lower for word in ["behind", "no tech", "lacking"]):
                    value = 30

        return value

    def _extract_desires(self, text: str) -> Dict[str, float]:
        """Extract and score character desires based on text content."""
        desires = {
            "wealth": 0.5,
            "fame": 0.5,
            "security": 0.5,
            "knowledge": 0.5,
            "belonging": 0.5,
            "power": 0.5,
            "freedom": 0.5,
        }

        content_lower = text.lower()

        if any(word in content_lower for word in ["rich", "money", "wealth", "financial"]):
            desires["wealth"] = 0.8
        elif any(word in content_lower for word in ["poor", "broke", "debt"]):
            desires["wealth"] = 0.2

        if any(word in content_lower for word in ["famous", "fame", "celebrity"]):
            desires["fame"] = 0.7
        elif any(word in content_lower for word in ["private", "quiet", "alone"]):
            desires["fame"] = 0.2

        if any(word in content_lower for word in ["secure", "security", "safe"]):
            desires["security"] = 0.8
        elif any(word in content_lower for word in ["risk", "adventurous"]):
            desires["security"] = 0.2

        if any(word in content_lower for word in ["learn", "study", "knowledge", "educate"]):
            desires["knowledge"] = 0.8
        elif any(word in content_lower for word in ["ignorance", "simple"]):
            desires["knowledge"] = 0.2

        if any(word in content_lower for word in ["friends", "family", "social", "belong"]):
            desires["belonging"] = 0.7
        elif any(word in content_lower for word in ["alone", "lonely", "independent"]):
            desires["belonging"] = 0.3

        if any(word in content_lower for word in ["power", "control", "influence", "leader"]):
            desires["power"] = 0.7
        elif any(word in content_lower for word in ["follow", "subordinate", "helpless"]):
            desires["power"] = 0.2

        if any(word in content_lower for word in ["freedom", "independent", "autonomy"]):
            desires["freedom"] = 0.8
        elif any(word in content_lower for word in ["structure", "rules", "bound"]):
            desires["freedom"] = 0.2

        return desires

    def conduct_interview(self, initial_message: str) -> Dict[str, Any]:
        """Conduct an interview starting with an initial message."""
        self.interview_history.append({
            "role": "user",
            "content": initial_message,
        })

        response = self._generate_interview_response(initial_message)
        self.interview_history.append({
            "role": "assistant",
            "content": response,
        })

        persona = self.extract_persona_from_text(response)
        self.current_profile = persona

        return {
            "response": response,
            "persona_ready": "[PERSONA_READY]" in response,
            "persona": persona,
        }

    def _generate_interview_response(self, user_input: str) -> str:
        """Generate interview response based on user input."""
        interview_phase = len(self.interview_history)

        if interview_phase == 1:
            return (
                f"Hello! I'm here to understand your life story. Let me start with "
                f"yourself: what's your name, age, and where are you from? "
                f"Remember, be as honest and detailed as you'd like - this will help "
                f"create your parallel life simulations. [PERSONA_READY]"
                if self._has_basic_info(user_input)
                else ""
            )

        elif interview_phase == 2:
            return self._ask_follow_up_questions(user_input)

        else:
            return self._ask_deep_dive_questions(user_input)

    def _has_basic_info(self, text: str) -> bool:
        """Check if text contains basic profile information."""
        has_name = bool(re.search(r"(?:my name is|I'm|I am|call me)\s+[A-Z][a-z]+", text, re.IGNORECASE))
        has_age = bool(re.search(r"\b\d{1,2}\s*(?:years old|year old|y/o|\(age\))\b", text, re.IGNORECASE))
        has_gender = bool(re.search(r"\b(man|male|woman|female|non.?binary)\b", text, re.IGNORECASE))
        return has_name and has_age and has_gender

    def _ask_follow_up_questions(self, text: str) -> str:
        """Ask follow-up questions based on user's responses."""
        if not self._has_basic_info(text):
            return (
                "I need to know more about you. Could you please tell me your name, "
                "age, and gender? For example, 'My name is John, I'm 30 years old, "
                "and I'm male.'"
            )

        questions = [
            "What's your current occupation or what do you do for work?",
            "What level of education do you have?",
            "How would you rate your happiness on a scale of 1-100?",
            "How's your health these days?",
            "How smart would you say you are?",
            "How would you describe your appearance?",
            "What's your general sense of karma or life balance?",
            "What drives you most in life?",
            "What's your biggest fear?",
            "What's one thing you've always wanted to achieve?",
            "What's your favorite type of social environment?",
            "What do you trust most in people?",
            "What's your relationship with your community?",
            "How do you view your current economic situation?",
            "What technology do you rely on most?",
            "What role do you play in your family?",
            "What's your level of social engagement?",
            "What are your long-term goals?",
            "What's your biggest challenge right now?",
            "What's your version of success?",
        ]

        return questions[0]

    def _ask_deep_dive_questions(self, text: str) -> str:
        """Ask deep dive questions for further profiling."""
        questions = [
            "Can you tell me about your most significant life decision and why you made it?",
            "What's been the biggest turning point in your life so far?",
            "What environment helps you thrive the most?",
            "Describe a time when you felt most alive and engaged.",
            "What's something you're particularly good at that few people know about?",
            "How do you handle stress and difficult situations?",
            "What's your biggest source of joy in daily life?",
            "Describe your ideal day from morning to night.",
            "What values are most important to you?",
            "How do you balance work and personal life?",
            "What's your relationship with money like?",
            "How do you spend your free time?",
            "What's your perspective on success and failure?",
            "How do you maintain relationships?",
            "What's your approach to learning new things?",
        ]

        return questions[0]

    def create_character_from_profile(self, seed: int = 42) -> Character:
        """Create a Character object from the interview profile."""
        if not self.current_profile:
            raise ValueError("No profile available. Conduct interview first.")

        profile = self.current_profile

        character = Character(
            name=profile["name"],
            age=profile["age"],
            gender=Gender(profile["gender"]),
            birthplace=profile["birthplace"],
            current_city=profile["current_city"],
            happiness=profile["happiness"],
            health=profile["health"],
            smarts=profile["smarts"],
            looks=profile["looks"],
            karma=profile["karma"],
            money=profile.get("money", 0.0),
            occupation=profile["occupation"],
            education_level=profile["education"],
            relationship_status="Single",
            portfolio_value=profile.get("portfolio_value", 0.0),
            desires=profile.get("desires", {}),
            social_variables=profile.get("social_variables", {}),
            seed=seed,
        )

        return character

    def to_dict(self) -> Dict[str, Any]:
        """Convert interview session to dictionary."""
        return {
            "interview_history": self.interview_history,
            "current_profile": self.current_profile,
        }


def main() -> None:
    """CLI entry point: read JSON on stdin, write JSON on stdout.

    Protocol (used by the Rust MCP client and Go core integration):
      input:  {"name": str, "age": int, "gender": str, "interview_text": str}
      output: {"persona": {...persona dict...}, "profile": {...same...}}

    Env: OLLAMA_DISABLE=1 skips the LLM call (pure regex mode).
    """
    try:
        raw = sys.stdin.buffer.read().decode("utf-8")
    except Exception:
        raw = sys.stdin.read() if hasattr(sys.stdin, "read") else ""

    request = {}
    if raw:
        try:
            request = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            request = {}

    text = request.get("interview_text") or request.get("initial_interview_text") or ""
    if not text:
        fields = [
            f"{k}: {v}" for k, v in request.items()
            if k in ("name", "age", "gender", "occupation") and v not in (None, "")
        ]
        text = ", ".join(fields)

    agent = InterviewAgent()
    if os.environ.get("OLLAMA_DISABLE") == "1":
        persona = agent._extract_with_regex(text)
    else:
        persona = agent.extract_persona_from_text(text)
    agent.current_profile = persona

    output = {
        "persona": persona,
        "profile": persona,
        "social_variables": persona.get("social_variables", {}),
        "status": "success",
    }
    print(json.dumps(output, default=str))


if __name__ == "__main__":
    main()