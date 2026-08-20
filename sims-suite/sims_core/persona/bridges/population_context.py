"""Population-context enrichment — shared across the station engines.

Remnants, CC, and Awareness each model a system under stress (what survives a
conflict, where your walls give, how to respond). But none of them currently
account for *who is affected* — the human population caught in the blast radius.
This module closes that gap using the persona core:

  - ``population_context(personas)`` distills a sampled cohort into an
    "affected population" profile: demographic / psychographic / capability
    distributions plus readability metrics (digital fluency, trust, risk,
    connectivity) that a station can use to make its scenario more human-aware.

  - ``enrich_report(report, context)`` attaches the context to a station report
    dict so the API response carries both the technical outcome and the human
    dimension — MatrAIx's cohort-vs-aggregate insight made concrete: a response
    that works for a digitally-fluent urban cohort may fail a low-fluency rural
    one.

This module is intentionally additive and engine-agnostic: it does not touch
the existing engine internals (no regression risk), it only augments the report
that the gateway already serializes.
"""

from __future__ import annotations

from collections import Counter
from typing import Optional

from sims_core.persona.models import Persona


def _pct(counts: Counter, total: int) -> dict[str, float]:
    return {k: round(v / total, 3) for k, v in counts.most_common()} if total else {}


def population_context(personas: list[Persona], cohort_label: str = "") -> dict:
    """Distill a sampled persona cohort into an affected-population profile.

    Returns a dict with distribution summaries per schema group plus a set of
    human-readability metrics a station can reason over.
    """
    n = len(personas)
    if n == 0:
        return {
            "cohort_size": 0, "cohort_label": cohort_label,
            "distributions": {}, "readability": {}, "notes": "empty cohort",
        }

    age = Counter(p.get("age_bracket") for p in personas)
    region = Counter(p.get("region") for p in personas)
    education = Counter(p.get("education_level") for p in personas)
    income = Counter(p.get("income_bracket") for p in personas)
    risk = Counter(p.get("risk_tolerance") for p in personas)
    digital = Counter(p.get("digital_fluency") for p in personas)
    trust = Counter(p.get("trust_in_institutions") for p in personas)
    adoption = Counter(p.get("technology_adoption") for p in personas)
    language = Counter(p.get("primary_language") for p in personas)

    def _share(counter: Counter, value: str) -> float:
        return round(counter.get(value, 0) / n, 3) if n else 0.0

    # Readability: how easy is it to reach / assist this population remotely?
    digital_fluent_share = _share(digital, "high")
    low_fluency_share = _share(digital, "low")
    high_trust_share = _share(trust, "high")
    low_trust_share = _share(trust, "low")
    high_risk_share = _share(risk, "high") + _share(risk, "very_high")
    conservative_share = _share(risk, "very_low") + _share(risk, "low")
    rural_share = _share(Counter(p.get("urbanicity") for p in personas), "rural")
    english_share = _share(language, "english")

    # A single composite readability index 0-100: higher = easier to reach and
    # assist this population through digital / institutional channels.
    readability_score = max(0.0, min(1.0, (
        digital_fluent_share * 0.35      # can be reached digitally
        + high_trust_share * 0.25        # will trust official channels
        - low_fluency_share * 0.15
        - low_trust_share * 0.15
        - rural_share * 0.10
        + english_share * 0.05
        + 0.20                           # baseline floor
    )))

    # Vulnerability: how much harm this population absorbs in a crisis.
    # High in low-income, low-fluency, low-trust, elderly cohorts.
    elderly_share = _share(age, "65+")
    low_income_share = _share(income, "low") + _share(income, "lower_middle")
    vulnerability_score = max(0.0, min(1.0, (
        low_income_share * 0.35
        + low_fluency_share * 0.20
        + elderly_share * 0.20
        + rural_share * 0.15
        + low_trust_share * 0.10
    )))

    return {
        "cohort_size": n,
        "cohort_label": cohort_label,
        "distributions": {
            "age_bracket": _pct(age, n),
            "region": _pct(region, n),
            "education_level": _pct(education, n),
            "income_bracket": _pct(income, n),
            "risk_tolerance": _pct(risk, n),
            "digital_fluency": _pct(digital, n),
            "trust_in_institutions": _pct(trust, n),
            "technology_adoption": _pct(adoption, n),
            "primary_language": _pct(language, n),
        },
        "readability": {
            "digital_fluent_share": digital_fluent_share,
            "low_fluency_share": low_fluency_share,
            "high_trust_share": high_trust_share,
            "low_trust_share": low_trust_share,
            "high_risk_share": high_risk_share,
            "conservative_share": conservative_share,
            "rural_share": rural_share,
            "english_share": english_share,
            "readability_index": round(readability_score * 100, 1),
            "vulnerability_index": round(vulnerability_score * 100, 1),
        },
        "notes": (
            "sampled population context attached to the scenario outcome; "
            "interpret technical results within this human dimension"
        ),
    }


def enrich_report(report: dict, personas: list[Persona], cohort_label: str = "") -> dict:
    """Attach an affected-population context to a station report dict.

    Additive and safe: it never mutates the input report in place (returns a
    shallow-copied dict with ``population_context`` added), so existing callers
    and dashboard contracts are unaffected.
    """
    out = dict(report)
    out["population_context"] = population_context(personas, cohort_label)
    return out


def sample_population_context(
    query: Optional[dict],
    n: int = 100,
    seed: int = 42,
    cohort_label: str = "",
) -> dict:
    """Sample a persona cohort from a raw query dict and return its context.

    Convenience for the gateway: takes the API's raw ``query`` body, samples
    the cohort, and returns the population profile ready to attach to a report.
    Raises ``ValueError`` on an invalid query (unknown dimension / bad value).
    """
    from sims_core.persona import sample_cohort, parse_query

    parsed = parse_query(query)
    personas = sample_cohort(n, seed=seed, query=parsed)
    return population_context(personas, cohort_label)


def digital_defense_quality(context: dict) -> float:
    """Engine-internal defense multiplier derived from a population's digital
    fluency and trust.

    Returns 0.0-1.0 where 1.0 = no population penalty (highly fluent, high
    trust). A low-fluency / low-trust population hardens and patches slower,
    so the *attack simulation itself* becomes easier — this is the factor to
    pass into ``cc.simulate_attack(..., defense_quality=...)`` so vulnerability
    is baked into the engine, not just the report.
    """
    readability = context.get("readability", {})
    fluent = readability.get("digital_fluent_share", 0.3)
    low_fluency = readability.get("low_fluency_share", 0.3)
    high_trust = readability.get("high_trust_share", 0.3)
    low_trust = readability.get("low_trust_share", 0.3)
    elderly = 0.0
    dist = context.get("distributions", {}).get("age_bracket", {})
    elderly = dist.get("65+", 0.0)

    # Defense quality rises with fluency + trust, falls with low fluency,
    # low trust, and an elderly (harder-to-patch) cohort. Bounded to a sane
    # range so a single cohort can't zero the defense.
    quality = 0.45 + 0.55 * fluent + 0.20 * high_trust - 0.25 * low_fluency \
        - 0.15 * low_trust - 0.20 * elderly
    return round(max(0.30, min(1.0, quality)), 3)


def population_resilience(context: dict) -> float:
    """Engine-internal survival multiplier derived from a population's
    resilience profile (trust, income, age, locality).

    Returns 0.0-1.0 where 1.0 = no penalty (high-trust, high-income, young,
    urban). A vulnerable population (low trust, low income, elderly, rural)
    cannot sustain institutions / supply chains / cultural artifacts through a
    crisis, so the Remnants engine itself produces fewer survivors. This is
    the factor to pass into ``remnants.simulate_survival(..., population_
    resilience=...)``.
    """
    readability = context.get("readability", {})
    high_trust = readability.get("high_trust_share", 0.3)
    low_trust = readability.get("low_trust_share", 0.3)
    dist = context.get("distributions", {})
    age = dist.get("age_bracket", {})
    elderly = age.get("65+", 0.0)
    income = dist.get("income_bracket", {})
    low_income = income.get("low", 0.0) + income.get("lower_middle", 0.0)
    urban = 1.0 - readability.get("rural_share", 0.3)

    # Resilience rises with trust and urbanicity, falls with low trust, an
    # elderly cohort, and low income. Bounded to a sane range.
    resilience = 0.40 + 0.35 * high_trust + 0.20 * urban \
        - 0.15 * low_trust - 0.20 * elderly - 0.20 * low_income
    return round(max(0.30, min(1.0, resilience)), 3)


def population_reach(context: dict) -> float:
    """Engine-internal response multiplier derived from a population's
    reachability (digital fluency, connectivity, trust).

    Returns 0.0-1.0 where 1.0 = no penalty (highly fluent, urban, trusting).
    A low-fluency / rural / low-trust population is hard to reach with response
    actions, so the Awareness engine itself produces lower response success.
    This is the factor to pass into ``awareness.simulate_response(..., 
    population_reach=...)``.
    """
    readability = context.get("readability", {})
    fluent = readability.get("digital_fluent_share", 0.3)
    low_fluency = readability.get("low_fluency_share", 0.3)
    high_trust = readability.get("high_trust_share", 0.3)
    low_trust = readability.get("low_trust_share", 0.3)
    rural = readability.get("rural_share", 0.3)
    elderly = context.get("distributions", {}).get("age_bracket", {}).get("65+", 0.0)

    # Reachability rises with fluency and trust, falls with low fluency, rural
    # locality, low trust, and an elderly cohort. Bounded to a sane range.
    reach = 0.40 + 0.55 * fluent + 0.20 * high_trust \
        - 0.25 * low_fluency - 0.15 * rural - 0.15 * low_trust - 0.20 * elderly
    return round(max(0.30, min(1.0, reach)), 3)