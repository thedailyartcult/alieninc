"""Persona adherence — controlled studies + multiple-testing discipline.

MatrAIx validates simulated users in two complementary ways that we adapt here:

1. **Controlled behavioral adherence.** The paper's 400-trial study assigns
   each agent a declared pole of a behavioral attribute (e.g. "verbose" vs
   "terse"), observes its behavior, and scores whether the assigned behavior
   was *expressed or correctly suppressed*. We mirror that design with
   ``run_controlled_study``: each persona declares a pole of one attribute, a
   behavior function observes the actual choice, and we report the hit rate.

2. **Multiple-testing correction.** With dozens of doctrine×terrain cells and
   per-field parameter adjustments, naive p-value thresholds produce false
   discoveries. ``benjamini_hochberg`` applies the BH procedure (FDR control)
   so only findings that survive the correction drive self-improvement — the
   discipline the MatrAIx team applies (Benjamini-Hochberg correction across
   declared primary outcomes).

Pure stdlib — no scipy/numpy — so the stack stays air-gapped.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from sims_core.persona.models import Persona
from sims_core.stats import two_proportion_z, benjamini_hochberg  # noqa: F401  (re-exported)


@dataclass
class AdherenceResult:
    """Outcome of one controlled adherence trial."""

    persona_id: str
    declared: str          # the assigned pole, e.g. "high"
    observed: str          # what the behavior actually expressed
    match: bool            # True if declared was expressed or correctly suppressed
    arm: str = ""          # "positive" or "negative" arm
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "persona_id": self.persona_id,
            "declared": self.declared,
            "observed": self.observed,
            "match": self.match,
            "arm": self.arm,
            "evidence": self.evidence,
        }


@dataclass
class AdherenceStudy:
    """Aggregate of a controlled adherence study (a MatrAIx-style report).

    ``overall_rate`` is the share of trials where the declared behavior was
    expressed or correctly suppressed. Per-arm and per-attribute cells break
    down where adherence holds and where it degrades.
    """

    n_trials: int
    overall_rate: float
    n_match: int
    per_attribute: dict[str, dict[str, Any]] = field(default_factory=dict)
    trials: list[AdherenceResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "n_trials": self.n_trials,
            "n_match": self.n_match,
            "overall_rate": round(self.overall_rate, 4),
            "per_attribute": self.per_attribute,
            "trials": [t.to_dict() for t in self.trials],
        }


def run_controlled_study(
    personas: list[Persona],
    attribute: str,
    behavior_fn: Callable[[Persona, int], tuple[str, dict]],
    arm_poles: Optional[dict[str, str]] = None,
    seed: Optional[int] = None,
) -> AdherenceStudy:
    """Controlled adherence study across personas (MatrAIx-style).

    ``behavior_fn(persona, seed)`` must return ``(observed_value, evidence)``
    where ``observed_value`` is the pole actually expressed (e.g. "high" or
    "low" for attribute ``attribute``). ``arm_poles`` maps arm name -> the
    declared pole for that arm; defaults to a two-arm design
    ``{"positive": <first value>, "negative": <second value>}`` inferred from
    the schema's value list.

    A trial matches if the persona's assigned value equals the observed value
    (the assigned pole was expressed), OR if the persona was assigned the
    opposite pole and did NOT express it (correctly suppressed).
    """
    from sims_core.persona.schema import DIMENSIONS

    dim = DIMENSIONS.get(attribute)
    if dim is None:
        raise ValueError(f"unknown attribute {attribute!r}")
    if arm_poles is None:
        if len(dim.values) < 2:
            raise ValueError(f"attribute {attribute!r} needs at least two values")
        arm_poles = {"positive": dim.values[0], "negative": dim.values[-1]}

    rng = random.Random(seed)
    trials: list[AdherenceResult] = []
    per_attribute: dict[str, dict[str, Any]] = {}

    for arm, declared in arm_poles.items():
        arm_personas = [p for p in personas if p.get(attribute) == declared]
        if not arm_personas:
            continue
        n_match = 0
        for persona in arm_personas:
            observed, evidence = behavior_fn(persona, rng.randint(0, 2**31 - 1))
            if observed == declared:
                match = True
            else:
                # Correct suppression: the opposite pole was declared, and the
                # behavior expressed a *different* (i.e. non-opposite) value.
                opposite = arm_poles["negative"] if arm == "positive" else arm_poles["positive"]
                match = observed != opposite
            if match:
                n_match += 1
            trials.append(AdherenceResult(
                persona_id=persona.summary(),
                declared=declared,
                observed=observed,
                match=match,
                arm=arm,
                evidence=evidence,
            ))
        per_attribute.setdefault(attribute, {})[arm] = {
            "declared": declared,
            "n": len(arm_personas),
            "n_match": n_match,
            "rate": round(n_match / len(arm_personas), 4) if arm_personas else 0.0,
        }

    n_match_total = sum(1 for t in trials if t.match)
    n_trials = len(trials)
    return AdherenceStudy(
        n_trials=n_trials,
        n_match=n_match_total,
        overall_rate=(n_match_total / n_trials) if n_trials else 0.0,
        per_attribute=per_attribute,
        trials=trials,
    )