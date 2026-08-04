"""Social variables module — 34 variables across 5 layers.

Based on parallel-life-sim's variable system, adapted for deterministic FSM simulation.
Each variable is a bounded integer 0-100 with causal chain tracking.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class VariableLayer(Enum):
    PERSONAL = "personal"
    INTERPERSONAL = "interpersonal"
    SOCIAL = "social"
    NATIONAL = "national"
    INTERNATIONAL = "international"


@dataclass
class SocialVariable:
    """A single social variable affecting character outcomes."""

    var_id: str
    name: str
    layer: VariableLayer
    description: str
    value: int = 50  # 0-100
    impact_weight: float = 1.0  # How strongly this variable affects outcomes

    def modify(self, delta: int) -> int:
        self.value = max(0, min(100, self.value + delta))
        return self.value


# ── 5-Layer Variable Definitions ──────────────────────────────────────

PERSONAL_VARIABLES: list[SocialVariable] = [
    SocialVariable("p1", "Self-Esteem", VariableLayer.PERSONAL, "Confidence in own abilities and worth", 50, 1.2),
    SocialVariable("p2", "Emotional Stability", VariableLayer.PERSONAL, "Ability to manage stress and emotional swings", 50, 1.1),
    SocialVariable("p3", "Ambition", VariableLayer.PERSONAL, "Drive to achieve goals and advance in life", 50, 1.3),
    SocialVariable("p4", "Creativity", VariableLayer.PERSONAL, "Ability to think originally and solve problems", 50, 1.0),
    SocialVariable("p5", "Resilience", VariableLayer.PERSONAL, "Capacity to recover from setbacks", 50, 1.2),
    SocialVariable("p6", "Empathy", VariableLayer.PERSONAL, "Ability to understand and share others' feelings", 50, 1.1),
    SocialVariable("p7", "Discipline", VariableLayer.PERSONAL, "Consistency in following through on commitments", 50, 1.2),
]

INTERPERSONAL_VARIABLES: list[SocialVariable] = [
    SocialVariable("i1", "Trust", VariableLayer.INTERPERSONAL, "Willingness to rely on others", 50, 1.0),
    SocialVariable("i2", "Communication Skill", VariableLayer.INTERPERSONAL, "Ability to express ideas clearly", 50, 1.1),
    SocialVariable("i3", "Conflict Resolution", VariableLayer.INTERPERSONAL, "Skill in resolving disagreements", 50, 1.0),
    SocialVariable("i4", "Social Magnetism", VariableLayer.INTERPERSONAL, "Natural ability to attract and retain connections", 50, 1.1),
    SocialVariable("i5", "Loyalty", VariableLayer.INTERPERSONAL, "Commitment to maintaining relationships", 50, 1.0),
    SocialVariable("i6", "Emotional Support", VariableLayer.INTERPERSONAL, "Capacity to provide comfort and encouragement", 50, 0.9),
]

SOCIAL_VARIABLES: list[SocialVariable] = [
    SocialVariable("s1", "Community Ties", VariableLayer.SOCIAL, "Strength of bonds within local community", 50, 1.0),
    SocialVariable("s2", "Social Mobility", VariableLayer.SOCIAL, "Perceived ability to move between social strata", 50, 1.1),
    SocialVariable("s3", "Cultural Capital", VariableLayer.SOCIAL, "Access to cultural knowledge and norms", 50, 0.9),
    SocialVariable("s4", "Network Density", VariableLayer.SOCIAL, "How interconnected one's social circles are", 50, 1.0),
    SocialVariable("s5", "Social Trust", VariableLayer.SOCIAL, "General trust in society and institutions", 50, 1.1),
    SocialVariable("s6", "Civic Engagement", VariableLayer.SOCIAL, "Participation in community and political life", 50, 0.8),
]

NATIONAL_VARIABLES: list[SocialVariable] = [
    SocialVariable("n1", "Economic Climate", VariableLayer.NATIONAL, "Overall state of the national economy", 50, 1.3),
    SocialVariable("n2", "Political Stability", VariableLayer.NATIONAL, "Steadiness and predictability of governance", 50, 1.2),
    SocialVariable("n3", "Education Quality", VariableLayer.NATIONAL, "Access to and quality of educational institutions", 50, 1.1),
    SocialVariable("n4", "Healthcare Access", VariableLayer.NATIONAL, "Availability and quality of healthcare", 50, 1.2),
    SocialVariable("n5", "Infrastructure", VariableLayer.NATIONAL, "Quality of transportation, utilities, and digital infrastructure", 50, 1.0),
    SocialVariable("n6", "Crime Rate", VariableLayer.NATIONAL, "Level of crime and personal safety in the nation", 50, 1.1),
]

INTERNATIONAL_VARIABLES: list[SocialVariable] = [
    SocialVariable("int1", "Global Trade", VariableLayer.INTERNATIONAL, "State of international trade and commerce", 50, 1.1),
    SocialVariable("int2", "Geopolitical Stability", VariableLayer.INTERNATIONAL, "Peace and stability in international relations", 50, 1.2),
    SocialVariable("int3", "Technology Access", VariableLayer.INTERNATIONAL, "Access to global technology and innovation", 50, 1.0),
    SocialVariable("int4", "Climate Conditions", VariableLayer.INTERNATIONAL, "Environmental factors affecting livelihoods", 50, 0.9),
    SocialVariable("int5", "Cultural Exchange", VariableLayer.INTERNATIONAL, "Flow of ideas and culture across borders", 50, 0.8),
]

ALL_VARIABLES: list[SocialVariable] = (
    PERSONAL_VARIABLES + INTERPERSONAL_VARIABLES + SOCIAL_VARIABLES + NATIONAL_VARIABLES + INTERNATIONAL_VARIABLES
)

LAYER_MAP: dict[str, list[SocialVariable]] = {
    "personal": PERSONAL_VARIABLES,
    "interpersonal": INTERPERSONAL_VARIABLES,
    "social": SOCIAL_VARIABLES,
    "national": NATIONAL_VARIABLES,
    "international": INTERNATIONAL_VARIABLES,
}


def get_variables_by_layer(layer: str) -> list[SocialVariable]:
    """Get all variables in a specific layer."""
    return LAYER_MAP.get(layer, [])


def get_all_variables() -> list[SocialVariable]:
    """Get all 34 social variables."""
    return ALL_VARIABLES


def get_variable(var_id: str) -> Optional[SocialVariable]:
    """Get a specific variable by ID."""
    for var in ALL_VARIABLES:
        if var.var_id == var_id:
            return var
    return None


def compute_layer_score(layer: str) -> float:
    """Compute the average score for a variable layer."""
    vars = get_variables_by_layer(layer)
    if not vars:
        return 50.0
    return sum(v.value for v in vars) / len(vars)


def compute_overall_score() -> float:
    """Compute the overall social score across all layers."""
    return sum(v.value for v in ALL_VARIABLES) / len(ALL_VARIABLES)