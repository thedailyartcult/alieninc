"""Persona schema — correlated categorical dimensions (MatrAIx-inspired).

MatrAIx (arXiv 2608.04205) models human variation through a 1,290-dimension
categorical schema and samples synthetic personas from a *dependency graph*:
each dimension is drawn conditionally on its parents via

    p(x_i | x_Pa(i))  ∝  prior_i(v) · adjustment_i(v; x_Pa(i)) · mask_i(v; x_Pa(i))

where the prior supplies the population marginal, the adjustment re-weights
values that are more/less common in this context, and the mask enforces hard
compatibility rules (a persona whose primary language is English cannot have
English proficiency "none").

This module is a compact, dependency-free adaptation of that idea for the Alien
Inc simulation stack: 25 dimensions spanning background / psychology /
capability / behavior / lifestyle, with explicit parent edges, sparse
contextual adjustments, and compatibility masks. It is honest about scope: the
priors are plausible population-shaped distributions, not a claim of empirical
calibration (MatrAIx calibrates its public coreset against UN/World Bank
marginals; we do not pretend to).

Every station can sample a persona (or a filtered cohort) and use it to seed a
simulation — Alpha Zero branches a persona's life, Kriegspiel pairs a persona's
risk appetite with a doctrine, Platoon captures the population an objective
affects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Set


def _norm(weights: dict[str, float]) -> dict[str, float]:
    """Normalize a raw weight dict to a probability distribution."""
    total = sum(weights.values())
    if total <= 0:
        return {}
    return {k: v / total for k, v in weights.items()}


def _adj(*rows: tuple[str, dict[str, float]]) -> dict[str, dict[str, float]]:
    """Compact builder for a parent_value -> {value: multiplier} adjustment table."""
    return dict(rows)


@dataclass(frozen=True)
class Dimension:
    """One categorical dimension of the persona schema.

    ``adjustments[parent_dim][parent_value][value]`` is a multiplier applied to
    the prior weight of ``value`` when ``parent_dim == parent_value``. Missing
    entries default to 1.0. ``masks`` entries are hard-forbidden values.
    """

    dim_id: str
    category: str
    values: tuple[str, ...]
    prior: dict[str, float]
    parents: tuple[str, ...] = ()
    adjustments: Dict[str, Dict[str, Dict[str, float]]] = field(default_factory=dict)
    masks: Dict[str, Dict[str, Set[str]]] = field(default_factory=dict)
    descriptions: Dict[str, str] = field(default_factory=dict)

    def description(self, value: str) -> str:
        return self.descriptions.get(value, f"{self.dim_id}={value}")


# ---------------------------------------------------------------------------
# Background
# ---------------------------------------------------------------------------

AGE_VALUES = ("18-24", "25-34", "35-44", "45-54", "55-64", "65+")
REGION_VALUES = (
    "north_america", "latin_america", "europe", "east_asia",
    "southeast_asia", "south_asia", "middle_east_north_africa",
    "sub_saharan_africa", "oceania",
)
EDUCATION_VALUES = ("none", "primary", "secondary", "vocational", "bachelors", "postgrad")
INCOME_VALUES = ("low", "lower_middle", "upper_middle", "high", "very_high")
OCCUPATION_VALUES = (
    "agriculture", "industry", "services", "technology", "finance",
    "healthcare", "education", "government", "military", "logistics",
    "arts", "not_in_workforce",
)

# Age prior — roughly adult population-shaped (not UN-calibrated).
AGE_PRIOR = _norm({
    "18-24": 16.0, "25-34": 20.0, "35-44": 18.0, "45-54": 15.0,
    "55-64": 14.0, "65+": 17.0,
})

# Region prior — rough global population share by region.
REGION_PRIOR = _norm({
    "north_america": 7.0, "latin_america": 8.0, "europe": 9.0,
    "east_asia": 19.0, "southeast_asia": 8.0, "south_asia": 25.0,
    "middle_east_north_africa": 7.0, "sub_saharan_africa": 14.0,
    "oceania": 1.0,
})

DIMENSIONS: dict[str, Dimension] = {}


def _register(dim: Dimension) -> Dimension:
    DIMENSIONS[dim.dim_id] = dim
    return dim


# ---- background ----
_register(Dimension(
    "age_bracket", "background", AGE_VALUES, AGE_PRIOR,
    descriptions={
        "18-24": "18-24 years old", "25-34": "25-34 years old",
        "35-44": "35-44 years old", "45-54": "45-54 years old",
        "55-64": "55-64 years old", "65+": "65 years or older",
    },
))

_register(Dimension(
    "region", "background", REGION_VALUES, REGION_PRIOR,
    descriptions={
        "north_america": "based in North America",
        "latin_america": "based in Latin America",
        "europe": "based in Europe", "east_asia": "based in East Asia",
        "southeast_asia": "based in Southeast Asia",
        "south_asia": "based in South Asia",
        "middle_east_north_africa": "based in the Middle East or North Africa",
        "sub_saharan_africa": "based in sub-Saharan Africa",
        "oceania": "based in Oceania",
    },
))

_register(Dimension(
    "gender_identity", "background", ("woman", "man", "non_binary"),
    _norm({"woman": 50.0, "man": 49.0, "non_binary": 1.0}),
    descriptions={
        "woman": "a woman", "man": "a man", "non_binary": "non-binary",
    },
))

_register(Dimension(
    "urbanicity", "background", ("urban", "suburban", "rural"),
    _norm({"urban": 46.0, "suburban": 24.0, "rural": 30.0}),
    parents=("region",),
    adjustments={
        "region": _adj(
            ("north_america", {"suburban": 2.6, "urban": 1.4, "rural": 0.7}),
            ("europe", {"urban": 1.5, "suburban": 1.6, "rural": 0.8}),
            ("south_asia", {"urban": 1.6, "suburban": 0.7, "rural": 0.9}),
            ("sub_saharan_africa", {"rural": 1.8, "urban": 0.9}),
            ("east_asia", {"urban": 1.7, "suburban": 1.2}),
            ("oceania", {"suburban": 2.0, "rural": 1.2}),
        ),
    },
    descriptions={
        "urban": "living in a city", "suburban": "living in the suburbs",
        "rural": "living in a rural area",
    },
))

_register(Dimension(
    "primary_language", "background",
    ("english", "mandarin", "hindi", "spanish", "arabic", "french",
     "portuguese", "russian", "bengali", "japanese", "german", "other"),
    _norm({
        "mandarin": 13.0, "hindi": 8.0, "spanish": 7.0, "english": 16.0,
        "arabic": 4.0, "french": 4.0, "portuguese": 4.0, "russian": 3.0,
        "bengali": 4.0, "japanese": 2.0, "german": 2.0, "other": 33.0,
    }),
    parents=("region",),
    adjustments={
        "region": _adj(
            ("north_america", {"english": 8.0, "spanish": 1.4}),
            ("latin_america", {"spanish": 8.0, "portuguese": 4.0}),
            ("europe", {"english": 2.2, "german": 1.6, "french": 1.6, "russian": 1.0}),
            ("east_asia", {"mandarin": 7.0, "japanese": 1.5}),
            ("southeast_asia", {"english": 1.6}),
            ("south_asia", {"hindi": 5.0, "bengali": 2.5}),
            ("middle_east_north_africa", {"arabic": 7.0, "english": 1.2}),
            ("sub_saharan_africa", {"english": 1.4, "french": 2.0, "portuguese": 1.2}),
            ("oceania", {"english": 9.0}),
        ),
    },
    descriptions={
        "english": "speaks English", "mandarin": "speaks Mandarin",
        "hindi": "speaks Hindi", "spanish": "speaks Spanish",
        "arabic": "speaks Arabic", "french": "speaks French",
        "portuguese": "speaks Portuguese", "russian": "speaks Russian",
        "bengali": "speaks Bengali", "japanese": "speaks Japanese",
        "german": "speaks German", "other": "speaks another first language",
    },
))

_register(Dimension(
    "education_level", "background", EDUCATION_VALUES,
    _norm({"none": 10.0, "primary": 16.0, "secondary": 32.0,
           "vocational": 14.0, "bachelors": 18.0, "postgrad": 10.0}),
    parents=("age_bracket",),
    adjustments={
        "age_bracket": _adj(
            ("18-24", {"secondary": 1.7, "bachelors": 1.3, "postgrad": 0.2, "none": 0.3}),
            ("25-34", {"bachelors": 1.6, "postgrad": 1.5, "none": 0.5}),
            ("35-44", {"postgrad": 1.3}),
            ("45-54", {"bachelors": 1.1}),
            ("55-64", {"secondary": 1.2, "postgrad": 0.9}),
            ("65+", {"none": 1.6, "primary": 1.3, "secondary": 1.2, "postgrad": 0.6}),
        ),
    },
    descriptions={
        "none": "no formal education", "primary": "primary education",
        "secondary": "secondary education", "vocational": "vocational training",
        "bachelors": "a bachelor's degree", "postgrad": "a postgraduate degree",
    },
))

_register(Dimension(
    "income_bracket", "background", INCOME_VALUES,
    _norm({"low": 22.0, "lower_middle": 26.0, "upper_middle": 26.0,
           "high": 18.0, "very_high": 8.0}),
    parents=("education_level", "region"),
    adjustments={
        "education_level": _adj(
            ("none", {"low": 2.4, "lower_middle": 1.4}),
            ("primary", {"low": 1.8}),
            ("secondary", {"lower_middle": 1.3}),
            ("vocational", {"upper_middle": 1.4}),
            ("bachelors", {"high": 1.9, "upper_middle": 1.3}),
            ("postgrad", {"very_high": 2.6, "high": 1.6}),
        ),
        "region": _adj(
            ("sub_saharan_africa", {"low": 1.9, "high": 0.5}),
            ("south_asia", {"low": 1.4}),
            ("north_america", {"very_high": 2.2, "high": 1.4}),
            ("europe", {"high": 1.2, "very_high": 1.5}),
            ("east_asia", {"upper_middle": 1.3}),
            ("oceania", {"high": 1.5, "very_high": 1.6}),
        ),
    },
    descriptions={
        "low": "with a low income", "lower_middle": "with a lower-middle income",
        "upper_middle": "with an upper-middle income", "high": "with a high income",
        "very_high": "with a very high income",
    },
))

_register(Dimension(
    "occupation_sector", "background", OCCUPATION_VALUES,
    _norm({
        "agriculture": 14.0, "industry": 15.0, "services": 18.0,
        "technology": 7.0, "finance": 5.0, "healthcare": 9.0,
        "education": 8.0, "government": 6.0, "military": 3.0,
        "logistics": 5.0, "arts": 3.0, "not_in_workforce": 7.0,
    }),
    parents=("education_level",),
    adjustments={
        "education_level": _adj(
            ("none", {"agriculture": 2.2, "not_in_workforce": 1.8}),
            ("primary", {"agriculture": 1.6, "industry": 1.2}),
            ("secondary", {"industry": 1.3, "services": 1.2}),
            ("vocational", {"industry": 1.6, "logistics": 1.4, "services": 1.1}),
            ("bachelors", {"technology": 2.0, "education": 1.6, "finance": 1.6}),
            ("postgrad", {"education": 1.8, "healthcare": 1.5, "government": 1.5}),
        ),
    },
    descriptions={
        "agriculture": "working in agriculture", "industry": "working in industry",
        "services": "working in services", "technology": "working in technology",
        "finance": "working in finance", "healthcare": "working in healthcare",
        "education": "working in education", "government": "working in government",
        "military": "serving in the military", "logistics": "working in logistics",
        "arts": "working in the arts", "not_in_workforce": "not currently in the workforce",
    },
))


# ---------------------------------------------------------------------------
# Psychology
# ---------------------------------------------------------------------------

RISK_VALUES = ("very_low", "low", "moderate", "high", "very_high")

_register(Dimension(
    "risk_tolerance", "psychology", RISK_VALUES,
    _norm({"very_low": 16.0, "low": 22.0, "moderate": 30.0, "high": 22.0, "very_high": 10.0}),
    parents=("age_bracket", "income_bracket"),
    adjustments={
        "age_bracket": _adj(
            ("18-24", {"very_high": 1.8, "high": 1.4, "very_low": 0.6}),
            ("25-34", {"high": 1.3}),
            ("45-54", {"very_low": 1.4}),
            ("55-64", {"very_low": 1.7, "low": 1.3}),
            ("65+", {"very_low": 2.2, "low": 1.3, "high": 0.5}),
        ),
        "income_bracket": _adj(
            ("low", {"very_low": 1.4}),
            ("very_high", {"very_high": 2.2, "high": 1.5, "very_low": 0.4}),
            ("high", {"high": 1.3}),
        ),
    },
    descriptions={
        "very_low": "highly risk-averse", "low": "risk-averse",
        "moderate": "moderately risk-tolerant", "high": "risk-tolerant",
        "very_high": "highly risk-seeking",
    },
))

_register(Dimension(
    "openness", "psychology", ("low", "medium", "high"),
    _norm({"low": 30.0, "medium": 45.0, "high": 25.0}),
    parents=("age_bracket",),
    adjustments={
        "age_bracket": _adj(
            ("18-24", {"high": 1.5}),
            ("25-34", {"high": 1.2}),
            ("65+", {"high": 0.5, "low": 1.5}),
        ),
    },
    descriptions={
        "low": "prefers familiar routines", "medium": "open to some new experiences",
        "high": "highly open to new experiences",
    },
))

_register(Dimension(
    "neuroticism", "psychology", ("low", "medium", "high"),
    _norm({"low": 30.0, "medium": 45.0, "high": 25.0}),
    descriptions={
        "low": "emotionally stable", "medium": "generally steady",
        "high": "prone to worry and stress",
    },
))

_register(Dimension(
    "trust_in_institutions", "psychology", ("low", "medium", "high"),
    _norm({"low": 30.0, "medium": 42.0, "high": 28.0}),
    parents=("region",),
    adjustments={
        "region": _adj(
            ("north_america", {"medium": 1.2, "low": 1.1}),
            ("europe", {"high": 1.4, "medium": 1.1}),
            ("sub_saharan_africa", {"low": 1.4}),
            ("middle_east_north_africa", {"low": 1.3}),
            ("south_asia", {"medium": 1.2}),
        ),
    },
    descriptions={
        "low": "distrustful of institutions", "medium": "cautiously trusting of institutions",
        "high": "trusting of institutions",
    },
))

_register(Dimension(
    "locus_of_control", "psychology", ("external", "mixed", "internal"),
    _norm({"external": 25.0, "mixed": 45.0, "internal": 30.0}),
    parents=("education_level",),
    adjustments={
        "education_level": _adj(
            ("none", {"external": 1.6}),
            ("primary", {"external": 1.3}),
            ("secondary", {"mixed": 1.2}),
            ("bachelors", {"internal": 1.5}),
            ("postgrad", {"internal": 1.8}),
        ),
    },
    descriptions={
        "external": "believes outcomes depend on external forces",
        "mixed": "sees outcomes as partly under their control",
        "internal": "believes outcomes are largely under their control",
    },
))

_register(Dimension(
    "ambition", "psychology", ("low", "medium", "high"),
    _norm({"low": 30.0, "medium": 42.0, "high": 28.0}),
    parents=("education_level", "income_bracket"),
    adjustments={
        "education_level": _adj(
            ("bachelors", {"high": 1.5}),
            ("postgrad", {"high": 1.7}),
            ("none", {"low": 1.5}),
        ),
        "income_bracket": _adj(
            ("very_high", {"high": 1.8}),
            ("low", {"low": 1.3}),
        ),
    },
    descriptions={
        "low": "content with their current position", "medium": "moderately ambitious",
        "high": "highly ambitious",
    },
))


# ---------------------------------------------------------------------------
# Capability
# ---------------------------------------------------------------------------

_register(Dimension(
    "technical_proficiency", "capability",
    ("none", "basic", "intermediate", "advanced", "expert"),
    _norm({"none": 30.0, "basic": 26.0, "intermediate": 22.0, "advanced": 14.0, "expert": 8.0}),
    parents=("education_level", "occupation_sector"),
    adjustments={
        "education_level": _adj(
            ("none", {"none": 2.2}),
            ("primary", {"none": 1.5}),
            ("secondary", {"basic": 1.3}),
            ("bachelors", {"advanced": 1.8, "expert": 1.4}),
            ("postgrad", {"advanced": 1.6, "expert": 1.9}),
        ),
        "occupation_sector": _adj(
            ("technology", {"expert": 3.5, "advanced": 2.2, "none": 0.2}),
            ("finance", {"intermediate": 1.5, "advanced": 1.3}),
            ("industry", {"basic": 1.3}),
            ("agriculture", {"none": 1.8}),
        ),
    },
    descriptions={
        "none": "no technical proficiency", "basic": "basic technical proficiency",
        "intermediate": "intermediate technical proficiency",
        "advanced": "advanced technical proficiency",
        "expert": "expert technical proficiency",
    },
))

_register(Dimension(
    "digital_fluency", "capability", ("low", "medium", "high"),
    _norm({"low": 28.0, "medium": 42.0, "high": 30.0}),
    parents=("age_bracket", "technical_proficiency"),
    adjustments={
        "age_bracket": _adj(
            ("18-24", {"high": 2.0, "low": 0.3}),
            ("25-34", {"high": 1.6, "low": 0.5}),
            ("55-64", {"low": 1.6}),
            ("65+", {"low": 2.6, "high": 0.3}),
        ),
        "technical_proficiency": _adj(
            ("expert", {"high": 3.0}),
            ("advanced", {"high": 2.2}),
            ("intermediate", {"high": 1.4}),
            ("none", {"low": 1.8}),
        ),
    },
    descriptions={
        "low": "low digital fluency", "medium": "moderate digital fluency",
        "high": "high digital fluency",
    },
))

_register(Dimension(
    "domain_expertise", "capability", ("none", "familiar", "proficient", "expert"),
    _norm({"none": 32.0, "familiar": 32.0, "proficient": 24.0, "expert": 12.0}),
    parents=("occupation_sector", "education_level"),
    adjustments={
        "occupation_sector": _adj(
            ("technology", {"proficient": 1.5, "expert": 1.8}),
            ("finance", {"proficient": 1.5, "expert": 1.3}),
            ("healthcare", {"proficient": 1.5, "expert": 1.3}),
            ("military", {"proficient": 1.4}),
            ("agriculture", {"familiar": 1.4}),
        ),
        "education_level": _adj(
            ("bachelors", {"proficient": 1.3}),
            ("postgrad", {"expert": 1.8, "proficient": 1.3}),
        ),
    },
    descriptions={
        "none": "no domain expertise", "familiar": "familiar with their domain",
        "proficient": "proficient in their domain", "expert": "an expert in their domain",
    },
))

_register(Dimension(
    "analytic_reasoning", "capability", ("low", "medium", "high"),
    _norm({"low": 30.0, "medium": 42.0, "high": 28.0}),
    parents=("education_level",),
    adjustments={
        "education_level": _adj(
            ("bachelors", {"high": 1.5}),
            ("postgrad", {"high": 1.9}),
            ("none", {"low": 1.7}),
            ("primary", {"low": 1.4}),
        ),
    },
    descriptions={
        "low": "prefers concrete, step-by-step reasoning",
        "medium": "comfortable with moderate abstraction",
        "high": "highly analytical thinker",
    },
))


# ---------------------------------------------------------------------------
# Behavior & interaction
# ---------------------------------------------------------------------------

ADOPTION_VALUES = ("laggard", "late_majority", "early_majority", "early_adopter", "innovator")

_register(Dimension(
    "technology_adoption", "behavior", ADOPTION_VALUES,
    _norm({"laggard": 16.0, "late_majority": 28.0, "early_majority": 32.0,
           "early_adopter": 17.0, "innovator": 7.0}),
    parents=("age_bracket", "digital_fluency"),
    adjustments={
        "age_bracket": _adj(
            ("18-24", {"early_adopter": 1.8, "innovator": 1.6, "laggard": 0.3}),
            ("25-34", {"early_adopter": 1.4}),
            ("55-64", {"laggard": 1.6}),
            ("65+", {"laggard": 2.4, "innovator": 0.2}),
        ),
        "digital_fluency": _adj(
            ("high", {"early_adopter": 1.8, "innovator": 2.0, "laggard": 0.2}),
            ("low", {"laggard": 2.0, "innovator": 0.2}),
        ),
    },
    descriptions={
        "laggard": "an avoider of new technology", "late_majority": "slow to adopt new technology",
        "early_majority": "adopts technology once proven",
        "early_adopter": "quick to adopt new technology", "innovator": "an early technology adopter",
    },
))

_register(Dimension(
    "consumption_style", "behavior", ("thrifty", "value_conscious", "balanced", "premium"),
    _norm({"thrifty": 24.0, "value_conscious": 32.0, "balanced": 30.0, "premium": 14.0}),
    parents=("income_bracket",),
    adjustments={
        "income_bracket": _adj(
            ("low", {"thrifty": 2.2, "premium": 0.2}),
            ("lower_middle", {"thrifty": 1.4, "value_conscious": 1.2}),
            ("upper_middle", {"balanced": 1.3}),
            ("high", {"premium": 1.8, "balanced": 1.2}),
            ("very_high", {"premium": 3.2}),
        ),
    },
    descriptions={
        "thrifty": "spends carefully", "value_conscious": "hunts for value",
        "balanced": "balanced spender", "premium": "prefers premium products",
    },
))

_register(Dimension(
    "work_style", "behavior", ("structured", "collaborative", "autonomous", "entrepreneurial"),
    _norm({"structured": 30.0, "collaborative": 30.0, "autonomous": 24.0, "entrepreneurial": 16.0}),
    parents=("occupation_sector", "locus_of_control"),
    adjustments={
        "occupation_sector": _adj(
            ("military", {"structured": 2.4}),
            ("government", {"structured": 1.6}),
            ("technology", {"autonomous": 1.5, "entrepreneurial": 1.5}),
            ("arts", {"autonomous": 1.7, "entrepreneurial": 1.4}),
            ("finance", {"structured": 1.3}),
        ),
        "locus_of_control": _adj(
            ("internal", {"entrepreneurial": 1.8, "autonomous": 1.4}),
            ("external", {"structured": 1.5}),
        ),
    },
    descriptions={
        "structured": "prefers clear structure and procedures",
        "collaborative": "prefers collaborative work", "autonomous": "prefers to work autonomously",
        "entrepreneurial": "prefers to operate entrepreneurially",
    },
))


# ---------------------------------------------------------------------------
# Lifestyle
# ---------------------------------------------------------------------------

_register(Dimension(
    "interests", "lifestyle",
    ("arts_culture", "science_technology", "health_fitness", "finance_business",
     "geopolitics_security", "food_cuisine", "sports", "travel"),
    _norm({
        "arts_culture": 14.0, "science_technology": 12.0, "health_fitness": 13.0,
        "finance_business": 10.0, "geopolitics_security": 10.0,
        "food_cuisine": 14.0, "sports": 15.0, "travel": 12.0,
    }),
    parents=("occupation_sector",),
    adjustments={
        "occupation_sector": _adj(
            ("technology", {"science_technology": 2.6}),
            ("finance", {"finance_business": 2.6}),
            ("military", {"geopolitics_security": 3.0}),
            ("government", {"geopolitics_security": 2.4}),
            ("healthcare", {"health_fitness": 2.0}),
            ("education", {"arts_culture": 1.5, "science_technology": 1.4}),
            ("arts", {"arts_culture": 2.8}),
            ("logistics", {"travel": 1.6}),
            ("agriculture", {"food_cuisine": 1.6}),
        ),
    },
    descriptions={
        "arts_culture": "interested in arts and culture",
        "science_technology": "interested in science and technology",
        "health_fitness": "interested in health and fitness",
        "finance_business": "interested in finance and business",
        "geopolitics_security": "interested in geopolitics and security",
        "food_cuisine": "interested in food and cuisine",
        "sports": "interested in sports", "travel": "interested in travel",
    },
))

_register(Dimension(
    "media_diet", "lifestyle", ("traditional", "mixed", "digital_native"),
    _norm({"traditional": 30.0, "mixed": 40.0, "digital_native": 30.0}),
    parents=("digital_fluency", "age_bracket"),
    adjustments={
        "digital_fluency": _adj(
            ("high", {"digital_native": 2.2, "traditional": 0.4}),
            ("low", {"traditional": 2.0, "digital_native": 0.2}),
        ),
        "age_bracket": _adj(
            ("18-24", {"digital_native": 2.4}),
            ("25-34", {"digital_native": 1.6}),
            ("55-64", {"traditional": 1.5}),
            ("65+", {"traditional": 2.2}),
        ),
    },
    descriptions={
        "traditional": "consumes traditional media", "mixed": "mixed media diet",
        "digital_native": "consumes mostly digital media",
    },
))

_register(Dimension(
    "health_lifestyle", "lifestyle", ("inactive", "moderate", "active", "fitness_focused"),
    _norm({"inactive": 26.0, "moderate": 40.0, "active": 24.0, "fitness_focused": 10.0}),
    parents=("income_bracket",),
    adjustments={
        "income_bracket": _adj(
            ("low", {"inactive": 1.5}),
            ("very_high", {"fitness_focused": 2.4, "active": 1.4}),
            ("high", {"active": 1.3, "fitness_focused": 1.5}),
        ),
    },
    descriptions={
        "inactive": "with an inactive lifestyle", "moderate": "with a moderately active lifestyle",
        "active": "with an active lifestyle", "fitness_focused": "fitness-focused",
    },
))


# ---------------------------------------------------------------------------
# Language proficiency (the paper's canonical dependency+mask example)
# ---------------------------------------------------------------------------

_register(Dimension(
    "english_proficiency", "background",
    ("native", "fluent", "intermediate", "basic", "none"),
    _norm({"native": 15.0, "fluent": 18.0, "intermediate": 22.0, "basic": 24.0, "none": 21.0}),
    parents=("primary_language", "region"),
    adjustments={
        "primary_language": _adj(
            ("english", {"native": 14.0, "none": 0.05}),
            ("other", {"none": 1.8}),
            ("mandarin", {"none": 1.3}),
        ),
        "region": _adj(
            ("north_america", {"native": 3.0, "fluent": 1.4, "none": 0.2}),
            ("europe", {"fluent": 1.6, "none": 0.6}),
            ("oceania", {"native": 3.0}),
            ("sub_saharan_africa", {"fluent": 1.3}),
            ("south_asia", {"fluent": 1.5}),
        ),
    },
    masks={
        "primary_language": {
            # The paper's compatibility rule, verbatim:
            # a persona whose primary language is English cannot have
            # English proficiency "none".
            "english": {"none"},
        },
    },
    descriptions={
        "native": "a native English speaker", "fluent": "fluent in English",
        "intermediate": "with intermediate English", "basic": "with basic English",
        "none": "with no English proficiency",
    },
))


# ---------------------------------------------------------------------------
# Topological order
# ---------------------------------------------------------------------------

def _topological_order() -> list[str]:
    """Parent-first topological order of all dimensions (deterministic)."""
    ordered: list[str] = []
    seen: set[str] = set()

    def visit(dim_id: str) -> None:
        if dim_id in seen:
            return
        seen.add(dim_id)
        dim = DIMENSIONS[dim_id]
        for parent in dim.parents:
            visit(parent)
        ordered.append(dim_id)

    for dim_id in DIMENSIONS:
        visit(dim_id)
    return ordered


TOPOLOGICAL_ORDER = _topological_order()


def categories() -> list[str]:
    """All schema categories in first-appearance order."""
    out: list[str] = []
    for dim_id in TOPOLOGICAL_ORDER:
        cat = DIMENSIONS[dim_id].category
        if cat not in out:
            out.append(cat)
    return out


def dimension(dim_id: str) -> Dimension:
    """Look up a dimension by id."""
    return DIMENSIONS[dim_id]


def validate_value(dim_id: str, value: str) -> bool:
    """Whether ``value`` is an allowed value for dimension ``dim_id``."""
    dim = DIMENSIONS.get(dim_id)
    return bool(dim and value in dim.values)