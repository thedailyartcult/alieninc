"""Bridges between the persona core and the Alpha Zero engine.

Alpha Zero's ``Character`` is a thin BitLife-style archetype (age, gender,
happiness/health/smarts/karma, 34 social variables). This bridge makes the
"run this decision against 8.2 billion people" claim coherent by seeding a
Character from a sampled persona: instead of everyone starting at the same
defaults, each universe gets its own correlated person.

Nothing here patches the engine repo — we import its public objects and build a
``Character`` directly, then drive the existing orchestrator's FSM. If the
engine is not importable, all functions degrade to ``None``/empty results so
the rest of the stack keeps working.
"""

from __future__ import annotations

from typing import Optional

from sims_core.persona.models import Persona

_AGE_OFFSET = {
    "18-24": 0, "25-34": 2, "35-44": 4, "45-54": 6, "55-64": 8, "65+": 12,
}

_EDUCATION_MAP = {
    "none": "None", "primary": "Elementary", "secondary": "High School",
    "vocational": "Vocational", "bachelors": "Bachelor's", "postgrad": "Postgraduate",
}

_SECTOR_JOBS = {
    "agriculture": "Farmer", "industry": "Factory Operator", "services": "Service Worker",
    "technology": "Software Engineer", "finance": "Financial Analyst", "healthcare": "Nurse",
    "education": "Teacher", "government": "Civil Servant", "military": "Military Officer",
    "logistics": "Logistics Coordinator", "arts": "Artist", "not_in_workforce": "Unemployed",
}

_RISK_TO_PREFERENCE = {
    "very_low": "very_conservative", "low": "conservative", "moderate": "balanced",
    "high": "aggressive", "very_high": "very_aggressive",
}

_LOOKS_HINT = {
    "health_fitness": 4, "fitness_focused": 7, "active": 3, "moderate": 0, "inactive": -3,
}

# persona dimension -> (engine social var_id, multiplier) for the 34-var layer.
_SOCIAL_MAP: dict[str, tuple[str, float]] = {
    "ambition": ("p3", 0.9),          # Ambition
    "openness": ("p4", 0.8),          # Creativity
    "neuroticism": ("p2", -0.8),      # Emotional Stability (inverted)
    "trust_in_institutions": ("i1", 0.9),  # Trust
    "locus_of_control": ("p5", 0.8),  # Resilience
    "analytic_reasoning": ("p1", 0.8),  # Self-Esteem (loose proxy)
}

_VALUE_LEVEL = {"very_low": 15, "low": 30, "moderate": 50, "high": 70, "very_high": 85,
                "none": 10, "basic": 30, "intermediate": 55, "advanced": 75, "expert": 90,
                "low": 30, "medium": 55, "high": 80}


def _level_score(value: str) -> int:
    return _VALUE_LEVEL.get(value, 50)


def _looks_value(persona: Persona) -> int:
    score = 50
    lifestyle = persona.get("health_lifestyle")
    if lifestyle:
        score += _LOOKS_HINT.get(lifestyle, 0)
    return max(0, min(100, score))


def build_character(persona: Persona, seed: int = 0) -> Optional[object]:
    """Build an Alpha Zero ``Character`` seeded from a persona.

    Returns ``None`` if the engine isn't importable. The returned character is
    a plain engine object; callers pass it to the orchestrator's FSM.
    """
    try:
        from engine.character import Character, Gender
    except Exception:
        return None

    gender_map = {"woman": Gender.FEMALE, "man": Gender.MALE, "non_binary": Gender.NON_BINARY}
    gender = gender_map.get(persona.get("gender_identity"), Gender.MALE)

    age_bracket = persona.get("age_bracket", "25-34")
    age = 18 + _AGE_OFFSET.get(age_bracket, 2) + (seed % 5)

    education = _EDUCATION_MAP.get(persona.get("education_level"), "High School")
    occupation = _SECTOR_JOBS.get(persona.get("occupation_sector"), "Unemployed")

    income_floor = {
        "low": 0.0, "lower_middle": 15000, "upper_middle": 45000,
        "high": 90000, "very_high": 250000,
    }
    money = income_floor.get(persona.get("income_bracket"), 0.0) * (0.8 + (seed % 5) / 10)

    smarts = 40
    smarts += _level_score(persona.get("analytic_reasoning")) * 0.35
    smarts += _level_score(persona.get("technical_proficiency")) * 0.3
    smarts += _level_score(persona.get("education_level")) * 0.35
    smarts = int(max(5, min(95, smarts)))

    happiness = 50
    happiness += 8 if persona.get("health_lifestyle") in ("active", "fitness_focused") else 0
    happiness += 6 if persona.get("openness") == "high" else 0
    happiness -= 6 if persona.get("neuroticism") == "high" else 0
    happiness = int(max(5, min(95, happiness)))

    health = 60
    health += {"inactive": -10, "moderate": 0, "active": 8, "fitness_focused": 12}.get(
        persona.get("health_lifestyle"), 0)
    health += {"low": -5, "very_high": 5}.get(persona.get("income_bracket"), 0)
    health = int(max(5, min(95, health)))

    try:
        char = Character(
            name=f"Persona-{seed}",
            age=age,
            gender=gender,
            money=money,
            happiness=happiness,
            health=health,
            smarts=smarts,
            looks=_looks_value(persona),
            karma=_level_score(persona.get("trust_in_institutions", "medium")),
            education_level=education,
            occupation=occupation,
            seed=seed,
            year=2026,
        )
    except Exception:
        return None

    # Seed the 34-variable social layer from the persona's psychology.
    for dim_id, (var_id, mult) in _SOCIAL_MAP.items():
        value = persona.get(dim_id)
        if value:
            char.set_social_variable(var_id, int(max(0, min(100, _level_score(value) * mult))))

    # Risk preference drives the finance strategy choice.
    risk = persona.get("risk_tolerance", "moderate")
    char.social_variables["risk_preference"] = _RISK_TO_PREFERENCE.get(risk, "balanced")

    # Tag the character with its persona for traceability.
    char.persona_profile = persona.profile_text()
    char.persona_values = dict(persona.values)
    return char


def run_persona_cohort(
    personas: list[Persona],
    base_seed: int = 42,
    max_age: int = 100,
) -> Optional[dict]:
    """Simulate each persona's life through the Alpha Zero FSM.

    Each persona becomes one independent universe (a different person, not a
    branch of the same person). Returns an aggregate report with per-persona
    outcomes plus cohort-level findings. ``None`` if the engine is unavailable.
    """
    try:
        from engine.simulation import SimulationOrchestrator, SimulationConfig
        from engine.relations import RelationGraph
        from engine.fsm import FSM
    except Exception:
        return None

    config = SimulationConfig(seed=base_seed)
    orchestrator = SimulationOrchestrator(config)

    results = []
    for i, persona in enumerate(personas):
        seed = base_seed + i
        char = build_character(persona, seed=seed)
        if char is None:
            continue
        relations = orchestrator.create_default_relations(char)
        fsm = FSM(seed=seed, strategy="balanced")
        try:
            steps = fsm.run_simulation(char, relations, max_age=max_age)
        except Exception:
            continue
        results.append({
            "persona": persona.summary(),
            "profile": persona.profile_text(),
            "risk_tolerance": persona.get("risk_tolerance"),
            "income_bracket": persona.get("income_bracket"),
            "age_bracket": persona.get("age_bracket"),
            "education_level": persona.get("education_level"),
            "final_net_worth": round(char.net_worth, 2),
            "final_happiness": char.happiness,
            "years_lived": len(steps),
            "occupation": char.occupation,
        })

    if not results:
        return None

    net_worths = [r["final_net_worth"] for r in results]
    happinesses = [r["final_happiness"] for r in results]

    return {
        "personas_simulated": len(results),
        "cohort_size": len(personas),
        "avg_net_worth": round(sum(net_worths) / len(net_worths), 2),
        "median_net_worth": _median(net_worths),
        "avg_happiness": round(sum(happinesses) / len(happinesses), 2),
        "convergence": _convergence(happinesses),
        "risk_groups": _group_by(net_worths, [r["risk_tolerance"] for r in results]),
        "outcomes": results,
    }


def _median(vals: list[float]) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2


def _convergence(vals: list[float]) -> float:
    if not vals:
        return 0.0
    avg = sum(vals) / len(vals)
    close = sum(1 for v in vals if abs(v - avg) < 10)
    return round(close / len(vals), 4)


def _group_by(net_worths: list[float], groups: list[str]) -> dict[str, dict]:
    buckets: dict[str, list[float]] = {}
    for nw, g in zip(net_worths, groups):
        buckets.setdefault(g, []).append(nw)
    out = {}
    for g, vals in buckets.items():
        out[g] = {
            "n": len(vals),
            "avg_net_worth": round(sum(vals) / len(vals), 2),
        }
    return out