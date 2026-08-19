"""TDAC narrative engine — render simulation outputs as editorial/audio.

Takes a simulation result and branches it across different narrative angles
to find the most compelling way to communicate the insight. Each branch varies
the tone (analytical, dramatic, philosophical, instructional), the angle
(cause-focused, outcome-focused, human-focused), and the length — producing
different editorial treatments of the same underlying data.

This is the sense-making layer. The simulation engines produce numbers; TDAC
turns them into meaning.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from sims_core.monte_carlo import monte_carlo_branch, best_branch, convergence_rate


class NarrativeTone(str, Enum):
    ANALYTICAL = "analytical"        # data-driven, precise, objective
    DRAMATIC = "dramatic"            # high-stakes, tension, narrative arc
    PHILOSOPHICAL = "philosophical"  # reflective, meaning-making, slow
    INSTRUCTIONAL = "instructional"  # actionable, clear, directive
    LYRICAL = "lyrical"              # poetic, evocative, sensory


class NarrativeAngle(str, Enum):
    CAUSE_FOCUSED = "cause_focused"       # why this happened
    OUTCOME_FOCUSED = "outcome_focused"   # what the result means
    HUMAN_FOCUSED = "human_focused"       # who it affects
    SYSTEM_FOCUSED = "system_focused"     # how the pieces connect
    TEMPORAL = "temporal"                  # how it unfolds over time


class NarrativeLength(str, Enum):
    FLASH = "flash"          # 2 minutes (≈300 words)
    STANDARD = "standard"    # 5 minutes (≈750 words)
    LONG_FORM = "long_form"  # 15 minutes (≈2000 words)


@dataclass
class SimulationSource:
    """The simulation output to be rendered as narrative."""

    engine: str                           # which engine produced it
    title: str                            # what was simulated
    key_finding: str                      # the main insight
    supporting_data: dict[str, any] = field(default_factory=dict)
    stakes: str = ""                      # why it matters


@dataclass
class NarrativeBranch:
    """One branched narrative treatment of the simulation output."""

    tone: NarrativeTone
    angle: NarrativeAngle
    length: NarrativeLength
    headline: str                         # the editorial headline
    opening: str                          # the opening paragraph
    word_count: int
    emotional_resonance: float            # 0-100, how moving it is
    clarity: float                        # 0-100, how clear the insight becomes
    actionability: float                  # 0-100, how likely to drive action
    score: float = 0.0
    outcome: str = ""


# --- Narrative templates per tone ---

_TONE_OPENERS = {
    NarrativeTone.ANALYTICAL: [
        "The data reveals a pattern that demands attention.",
        "Across {n} simulated branches, a single signal emerges.",
        "The numbers converge on a conclusion that reshapes the question.",
    ],
    NarrativeTone.DRAMATIC: [
        "In {n} possible futures, one truth survived every branch.",
        "The simulation ran the scenario {n} times. The result was always the same.",
        "What happened next was not the most likely outcome — it was the inevitable one.",
    ],
    NarrativeTone.PHILOSOPHICAL: [
        "Consider what it means to simulate a decision {n} times and arrive at the same truth.",
        "The question is not whether the outcome was certain, but whether certainty itself is the illusion.",
        "In the space between {n} branches, something essential was preserved.",
    ],
    NarrativeTone.INSTRUCTIONAL: [
        "Here is what the simulation found, and what you should do about it.",
        "After {n} scenarios, three actions emerge as clearly necessary.",
        "The data points to a specific response. Here's the playbook.",
    ],
    NarrativeTone.LYRICAL: [
        "In the quiet after {n} simulations, the noise settles and the signal sings.",
        "Each of the {n} branches was a sentence; together they form a single breath.",
        "The simulation did not predict the future — it listened for it, {n} times.",
    ],
}

_ANGLE_QUESTIONS = {
    NarrativeAngle.CAUSE_FOCUSED: "Why did this happen?",
    NarrativeAngle.OUTCOME_FOCUSED: "What does this result mean?",
    NarrativeAngle.HUMAN_FOCUSED: "Who does this affect?",
    NarrativeAngle.SYSTEM_FOCUSED: "How do the pieces connect?",
    NarrativeAngle.TEMPORAL: "How does this unfold over time?",
}

_LENGTH_WORDS = {
    NarrativeLength.FLASH: 300,
    NarrativeLength.STANDARD: 750,
    NarrativeLength.LONG_FORM: 2000,
}


# --- Sample simulation sources (for standalone operation) ---

SAMPLE_SOURCES: list[SimulationSource] = [
    SimulationSource(
        engine="alpha_zero",
        title="Population-Scale Life Decision Branching",
        key_finding="Across 10,000 parallel life trajectories, education investment at age 22 produced the highest convergence on financial stability by age 45.",
        supporting_data={"universes": 10000, "convergence": 0.73, "best_strategy": "balanced_portfolio"},
        stakes="Every education policy decision is a bet on 10,000 possible futures.",
    ),
    SimulationSource(
        engine="kriegspiel",
        title="Taiwan Strait Combat Scenarios",
        key_finding="In 95% of branched scenarios, naval blockade was the decisive opening move, not direct engagement.",
        supporting_data={"scenarios": 10000, "convergence": 0.95, "key_event": "naval_blockade"},
        stakes="The first 48 hours determine the next 48 years.",
    ),
    SimulationSource(
        engine="cc",
        title="Infrastructure Attack Path Analysis",
        key_finding="The most common attack path reached the crown jewel database in 4 hops, exploiting SQL injection at the web API layer.",
        supporting_data={"scenarios": 5000, "breach_rate": 0.085, "depth": 4, "key_vuln": "sql_injection"},
        stakes="Your database is four steps from the internet. So is everyone else's.",
    ),
    SimulationSource(
        engine="remnants",
        title="Post-Conflict Continuity Analysis",
        key_finding="National language and religious institutions showed 95% survival probability across all conflict intensities, while currency and telecom showed below 20%.",
        supporting_data={"scenarios": 5000, "survival_rate": 0.54, "best_survivor": "National Language"},
        stakes="The things that outlast wars are not the things we build to fight them.",
    ),
    SimulationSource(
        engine="awareness",
        title="Ransomware Response Playbook Evaluation",
        key_finding="Rapid Isolation contained the threat in 44.6% of scenarios, but Threat Hunt & Eradicate achieved higher operational continuity despite slower containment.",
        supporting_data={"scenarios": 5000, "best_playbook": "Rapid Isolation", "success_rate": 0.446},
        stakes="The fastest response is not always the best response.",
    ),
]


def simulate_narrative(source: SimulationSource, seed: Optional[int] = None) -> dict:
    """Branch one narrative treatment of the simulation output. Per-branch function."""
    rng = random.Random(seed or 42)

    tone = rng.choice(list(NarrativeTone))
    angle = rng.choice(list(NarrativeAngle))
    length = rng.choice(list(NarrativeLength))

    # Generate headline
    n = source.supporting_data.get("scenarios", source.supporting_data.get("universes", 1000))
    headline_templates = {
        NarrativeTone.ANALYTICAL: f"Analysis: {source.title}",
        NarrativeTone.DRAMATIC: f"The {source.engine.replace('_', ' ').title()} Verdict: {source.key_finding[:60]}...",
        NarrativeTone.PHILOSOPHICAL: f"On {source.title}: A Reflection",
        NarrativeTone.INSTRUCTIONAL: f"What {source.title} Means for You",
        NarrativeTone.LYRICAL: f"{source.title}: A Meditation",
    }
    headline = headline_templates[tone]

    # Generate opening
    opener_template = rng.choice(_TONE_OPENERS[tone])
    opening = opener_template.format(n=f"{n:,}")

    word_count = _LENGTH_WORDS[length]

    # Score the narrative treatment
    # Emotional resonance: philosophical + lyrical score higher
    tone_resonance = {
        NarrativeTone.PHILOSOPHICAL: 85, NarrativeTone.LYRICAL: 80,
        NarrativeTone.DRAMATIC: 70, NarrativeTone.ANALYTICAL: 40,
        NarrativeTone.INSTRUCTIONAL: 30,
    }
    # Clarity: instructional + analytical score higher
    tone_clarity = {
        NarrativeTone.INSTRUCTIONAL: 90, NarrativeTone.ANALYTICAL: 85,
        NarrativeTone.DRAMATIC: 60, NarrativeTone.PHILOSOPHICAL: 55,
        NarrativeTone.LYRICAL: 45,
    }
    # Actionability: instructional scores highest
    tone_action = {
        NarrativeTone.INSTRUCTIONAL: 95, NarrativeTone.ANALYTICAL: 70,
        NarrativeTone.DRAMATIC: 50, NarrativeTone.PHILOSOPHICAL: 30,
        NarrativeTone.LYRICAL: 20,
    }

    resonance = min(100, tone_resonance[tone] + rng.uniform(-10, 10))
    clarity = min(100, tone_clarity[tone] + rng.uniform(-10, 10))
    actionability = min(100, tone_action[tone] + rng.uniform(-10, 10))

    # Length affects all three — longer = more resonance, shorter = more clarity
    length_mod = {NarrativeLength.FLASH: 0.9, NarrativeLength.STANDARD: 1.0, NarrativeLength.LONG_FORM: 1.1}
    resonance *= length_mod[length]
    clarity *= (2 - length_mod[length])
    actionability *= (2 - length_mod[length])

    score = resonance * 0.3 + clarity * 0.4 + actionability * 0.3
    outcome = "compelling" if score > 65 else ("adequate" if score > 45 else "weak")

    return {
        "tone": tone.value,
        "angle": angle.value,
        "length": length.value,
        "headline": headline,
        "opening": opening,
        "word_count": word_count,
        "emotional_resonance": round(resonance, 1),
        "clarity": round(clarity, 1),
        "actionability": round(actionability, 1),
        "score": round(score, 2),
        "outcome": outcome,
    }


def generate_narrative_scenarios(
    source: Optional[SimulationSource] = None,
    n_scenarios: int = 5000,
    seed: Optional[int] = None,
) -> dict:
    """Generate N branched narrative treatments and aggregate."""
    t0 = time.perf_counter()
    if source is None:
        source = SAMPLE_SOURCES[0]

    raw = monte_carlo_branch(
        lambda s: simulate_narrative(source, s),
        n_scenarios,
        seed=seed,
    )

    compelling = sum(1 for r in raw if r["outcome"] == "compelling")
    adequate = sum(1 for r in raw if r["outcome"] == "adequate")
    weak = sum(1 for r in raw if r["outcome"] == "weak")

    avg_resonance = sum(r["emotional_resonance"] for r in raw) / len(raw) if raw else 0
    avg_clarity = sum(r["clarity"] for r in raw) / len(raw) if raw else 0
    avg_action = sum(r["actionability"] for r in raw) / len(raw) if raw else 0

    convergence = convergence_rate(raw, outcome_key="outcome")
    best_raw = best_branch(raw, key="score")

    # Tone distribution
    tone_counts: dict[str, int] = {}
    for r in raw:
        tone_counts[r["tone"]] = tone_counts.get(r["tone"], 0) + 1
    tone_distribution = sorted(tone_counts.items(), key=lambda x: x[1], reverse=True)

    return {
        "source_engine": source.engine,
        "source_title": source.title,
        "key_finding": source.key_finding,
        "stakes": source.stakes,
        "scenarios_run": len(raw),
        "compelling": compelling,
        "adequate": adequate,
        "weak": weak,
        "avg_resonance": round(avg_resonance, 1),
        "avg_clarity": round(avg_clarity, 1),
        "avg_actionability": round(avg_action, 1),
        "convergence_rate": round(convergence, 4),
        "best_narrative": {
            "tone": best_raw["tone"],
            "angle": best_raw["angle"],
            "length": best_raw["length"],
            "headline": best_raw["headline"],
            "opening": best_raw["opening"],
            "word_count": best_raw["word_count"],
            "resonance": best_raw["emotional_resonance"],
            "clarity": best_raw["clarity"],
            "actionability": best_raw["actionability"],
            "score": best_raw["score"],
        } if best_raw else None,
        "tone_distribution": [{"tone": t, "count": c} for t, c in tone_distribution],
        "duration_ms": round((time.perf_counter() - t0) * 1000, 1),
    }
