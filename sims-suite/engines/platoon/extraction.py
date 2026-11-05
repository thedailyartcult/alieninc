"""Platoon objective extraction — a Treiver-style two-stage extractor.

MatrAIx's Treiver turns free-text descriptions into structured attributes with
a two-stage pipeline: (1) an offline, deterministic regex/keyword pass that
produces high-precision candidates, then (2) an optional LLM judge that picks
final values with evidence and confidence. If the LLM is unavailable or its
output fails validation, the deterministic result stands.

Platoon's job is to *capture the objective* from the client. This module does
for an objective what Treiver does for a person: it converts a natural-language
brief ("We need to secure critical infrastructure within 18 months with zero
intrusions, no disruption to live services...") into a structured
:class:`ExtractionResult` that can become an ``Objective`` and flow down the
pipeline.

Design rules:
  - Stage 1 is fully offline and deterministic — air-gapped deployments never
    depend on a provider.
  - Stage 2 reuses the provider-agnostic LLM client from the Kriegspiel
    synthesis layer (DeepSeek / Ollama / OpenAI-compatible), so there are no
    new runtime deps and no duplicate provider code.
  - Every result carries provenance (method, prompt hash, validation status),
    mirroring the untrusted-content discipline used elsewhere in the stack.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from typing import Optional

from engines.platoon.objective import Objective, ObjectiveDomain, RiskTolerance

# ---------------------------------------------------------------------------
# Stage 1: offline keyword / regex extraction
# ---------------------------------------------------------------------------

_DOMAIN_KEYWORDS: list[tuple[str, list[str]]] = [
    ("national_security", ["conflict", "military", "defense", "warfare", "combat",
                           "adversary", "state-level", "regional conflict", "doctrine"]),
    ("cybersecurity", ["cyber", "intrusion", "breach", "ransomware", "network defense",
                       "crown-jewel", "red-team", "zero successful intrusions"]),
    ("economic_policy", ["economy", "gdp", "inflation", "trade", "tariff", "monetary",
                         "fiscal"]),
    ("corporate_strategy", ["portfolio", "capital allocation", "market share",
                            "shareholder", "revenue growth", "risk-adjusted returns"]),
    ("infrastructure", ["critical infrastructure", "power grid", "transportation",
                        "water system", "grid stability", "crown-jewel systems"]),
    ("public_health", ["public health", "pandemic", "vaccination", "patient outcomes",
                       "hospital", "health system"]),
    ("energy_transition", ["renewable", "energy transition", "carbon", "emissions",
                           "solar", "grid", "industrial operations"]),
    ("supply_chain", ["supply chain", "supplier", "logistics", "single-source",
                      "lead time", "critical path"]),
    ("diplomacy", ["diplomatic", "treaty", "negotiation", "alliance", "sanctions",
                   "embassy"]),
    ("market_entry", ["market entry", "expansion", "new market", "product launch",
                      "geographic expansion"]),
]

_RISK_CUES = {
    RiskTolerance.AGGRESSIVE: ["aggressive", "rapid", "fast", "high risk",
                               "risky", "ambitious timeline", "maximize", "rapidly"],
    RiskTolerance.CONSERVATIVE: ["conservative", "no risk", "safeguard", "protect",
                                 "stable", "prudent", "minimum risk", "zero disruption",
                                 "no disruption", "without compromising", "safely"],
}

_HORIZON_RE = re.compile(
    r"within\s+(\d+)\s*(years?|months?|days?|quarters?|decades?)"
    r"|(\d+)\s*-?\s*year\b"
    r"|by\s+(\d{4})",
    re.IGNORECASE,
)

_POPULATION_CUES = [
    ("population", "population"), ("people", "people"), ("citizens", "citizens"),
    ("8.2b", "8.2b"), ("8.2 billion", "8.2 billion"), ("millions", "millions"),
    ("customers", "customers"), ("workforce", "workforce"), ("users", "users"),
    ("consumers", "consumers"),
]

_CONSTRAINT_PATTERNS = [
    r"\bno\s+[a-z][^.,;]{3,60}",
    r"\bwithout\s+[a-z][^.,;]{3,60}",
    r"\bmust not\b[^.,;]{3,60}",
    r"\bcannot\b[^.,;]{3,60}",
    r"\bbudget capped at[^.,;]{3,60}",
    r"\bmust comply with[^.,;]{3,60}",
    r"\bmust maintain[^.,;]{3,60}",
    r"\bwhile\s+(?:maintaining|keeping|preserving)[^.,;]{3,60}",
    r"\bnot exceeding\b[^.,;]{3,60}",
    r"\bno cost increase\b[^.,;]{3,60}",
    r"\bno single position\b[^.,;]{3,60}",
]

_CRITERIA_PATTERNS = [
    r"\b(?:achieve|reduce|increase|lower|raise|cut|secure|ensure|deliver|reach)\b[^.,;]{3,80}",
    r"\bzero\s+successful[^.,;]{3,80}",
    r"\b\d+\s*%[^.,;]{3,80}",
    r"\bwithin\s+\d+\s*(?:minutes?|hours?|days?)[^.,;]{3,80}",
    r"\bsharpe ratio[^.,;]{3,60}",
    r"\bconvergence\s*(?:rate|>)[^.,;]{3,60}",
    r"\bsurvival score[^.,;]{3,60}",
    r"\bpass rate[^.,;]{3,60}",
    r"\bcoverage[^.,;]{3,60}",
    r"\b>\s*\d+[^.,;]{3,60}",
    r"\bmean time to (?:detect|resolve)\b[^.,;]{3,60}",
    r"\bbreach rate\b[^.,;]{3,60}",
    r"\breturn\s*>\s*\d+[^.,;]{3,60}",
    r"\bmax drawdown\b[^.,;]{3,60}",
]


def _detect_domain(text: str) -> tuple[str, float]:
    low = text.lower()
    scores: dict[str, int] = {}
    for domain, keywords in _DOMAIN_KEYWORDS:
        hits = sum(1 for k in keywords if k in low)
        if hits:
            scores[domain] = hits
    if not scores:
        return ("corporate_strategy", 0.2)
    best = max(scores, key=scores.get)
    total = sum(scores.values())
    return (best, round(scores[best] / total, 3))


def _detect_risk(text: str) -> tuple[str, float]:
    low = text.lower()
    hits = {RiskTolerance.AGGRESSIVE: 0, RiskTolerance.CONSERVATIVE: 0}
    for pole, cues in _RISK_CUES.items():
        hits[pole] = sum(1 for c in cues if c in low)
    if hits[RiskTolerance.AGGRESSIVE] == hits[RiskTolerance.CONSERVATIVE]:
        return (RiskTolerance.BALANCED.value, 0.5)
    best = max(hits, key=hits.get)
    total = hits[RiskTolerance.AGGRESSIVE] + hits[RiskTolerance.CONSERVATIVE]
    return (best.value, round(hits[best] / total, 3))


def _detect_horizon(text: str) -> tuple[Optional[float], float]:
    m = _HORIZON_RE.search(text)
    if not m:
        return (None, 0.0)
    if m.group(4):
        year = int(m.group(4))
        return (max(0.1, float(year - 2026)), 0.9)
    if m.group(3):
        return (float(int(m.group(3))), 0.9)
    amount = int(m.group(1))
    unit = m.group(2).lower()
    mult = {"year": 1.0, "years": 1.0, "month": 1 / 12, "months": 1 / 12,
            "day": 1 / 365, "days": 1 / 365, "quarter": 0.25, "quarters": 0.25,
            "decade": 10.0, "decades": 10.0}.get(unit, 1.0)
    return (round(amount * mult, 2), 0.9)


def _detect_population_scale(text: str) -> tuple[float, float]:
    low = text.lower()
    best_scale = 30.0
    best_confidence = 0.0
    for cue, label in _POPULATION_CUES:
        if cue in low:
            scale = {
                "8.2b": 100.0, "8.2 billion": 100.0, "millions": 80.0,
                "population": 75.0, "people": 70.0, "citizens": 70.0,
                "consumers": 70.0, "users": 60.0, "customers": 60.0,
                "workforce": 55.0,
            }.get(label, 50.0)
            if scale > best_scale or (scale == best_scale and best_confidence == 0.0):
                best_scale = scale
                best_confidence = 0.85
    return (round(best_scale, 1), best_confidence)


def _split_clauses(text: str) -> list[str]:
    """Split the brief into clause-ish units for constraint/criteria matching."""
    parts = re.split(r"[;.\n]", text)
    return [p.strip() for p in parts if p.strip()]


def _detect_constraints(text: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for pattern in _CONSTRAINT_PATTERNS:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            frag = m.group(0).strip()
            if frag and frag not in seen:
                out.append(frag)
                seen.add(frag)
    return out[:6]


def _detect_criteria(text: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for pattern in _CRITERIA_PATTERNS:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            frag = m.group(0).strip()
            if frag and frag not in seen:
                out.append(frag)
                seen.add(frag)
    return out[:6]


def _detect_goal(text: str) -> str:
    """Best-effort main clause: the sentence with the earliest action verb."""
    action_verbs = re.compile(
        r"\b(achieve|reduce|increase|secure|ensure|maximize|minimize|transition|"
        r"quantify|optimize|defend|protect|establish|build|model|diversify|deliver)\b",
        re.IGNORECASE,
    )
    best = None
    best_pos: Optional[int] = None
    for clause in _split_clauses(text):
        if len(clause) < 12:
            continue
        m = action_verbs.search(clause)
        if m and (best_pos is None or m.start() < best_pos):
            best, best_pos = clause, m.start()
    return best or text.strip()


def _detect_title(text: str) -> str:
    """A title from the brief: keep the first 8 words, title-cased."""
    words = re.findall(r"\S+", text.strip())
    if not words:
        return "Untitled Objective"
    title = " ".join(words[:8])
    return title[:1].upper() + title[1:] + ("..." if len(words) > 8 else "")


# ---------------------------------------------------------------------------
# Extraction result
# ---------------------------------------------------------------------------

@dataclass
class ExtractionResult:
    """The structured outcome of extracting an objective from free text."""

    text: str
    title: str
    domain: str
    domain_confidence: float
    goal: str
    constraints: list[str] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)
    risk_tolerance: str = "balanced"
    risk_confidence: float = 0.5
    time_horizon_years: Optional[float] = None
    time_confidence: float = 0.0
    population_scale: float = 30.0
    population_confidence: float = 0.0
    confidence_required: float = 70.0
    provenance: dict = field(default_factory=dict)

    def to_objective(self) -> Objective:
        domain = ObjectiveDomain(self.domain)
        risk = RiskTolerance(self.risk_tolerance)
        return Objective(
            title=self.title,
            domain=domain,
            goal=self.goal,
            constraints=self.constraints,
            success_criteria=self.success_criteria,
            risk_tolerance=risk,
            time_horizon_years=self.time_horizon_years or 5.0,
            population_scale=self.population_scale,
            confidence_required=self.confidence_required,
        )

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "domain": self.domain,
            "domain_confidence": self.domain_confidence,
            "goal": self.goal,
            "constraints": self.constraints,
            "success_criteria": self.success_criteria,
            "risk_tolerance": self.risk_tolerance,
            "risk_confidence": self.risk_confidence,
            "time_horizon_years": self.time_horizon_years,
            "time_confidence": self.time_confidence,
            "population_scale": self.population_scale,
            "population_confidence": self.population_confidence,
            "confidence_required": self.confidence_required,
            "provenance": self.provenance,
        }


# ---------------------------------------------------------------------------
# Stage 1: deterministic extraction
# ---------------------------------------------------------------------------

def extract_regex(text: str) -> ExtractionResult:
    """Offline, deterministic extraction (Treiver stage 1)."""
    domain, domain_conf = _detect_domain(text)
    risk, risk_conf = _detect_risk(text)
    horizon, horizon_conf = _detect_horizon(text)
    pop_scale, pop_conf = _detect_population_scale(text)
    return ExtractionResult(
        text=text,
        title=_detect_title(text),
        domain=domain,
        domain_confidence=domain_conf,
        goal=_detect_goal(text),
        constraints=_detect_constraints(text),
        success_criteria=_detect_criteria(text),
        risk_tolerance=risk,
        risk_confidence=risk_conf,
        time_horizon_years=horizon,
        time_confidence=horizon_conf,
        population_scale=pop_scale,
        population_confidence=pop_conf,
        provenance={
            "method": "regex",
            "stage": 1,
            "offline": True,
            "text_hash": hashlib.sha256(text.encode()).hexdigest()[:16],
        },
    )


# ---------------------------------------------------------------------------
# Stage 2: optional LLM judge (provider-agnostic, validated)
# ---------------------------------------------------------------------------

_LLM_PROMPT = """You are an objective-extraction judge. Parse the client brief below into strict JSON with exactly these keys:
{{
  "title": "short title",
  "domain": one of {domains},
  "goal": "one-sentence success definition",
  "constraints": ["array of constraint strings"],
  "success_criteria": ["array of measurable criteria"],
  "risk_tolerance": one of {risks},
  "time_horizon_years": number or null,
  "population_scale": number 0-100,
  "confidence_required": number 0-100
}}
Rules: only emit values directly supported by the text. If a field is unsupported use null or an empty array. Do not invent facts.

CLIENT BRIEF:
{text}

Respond with ONLY the JSON object."""


def _validate_llm_payload(payload: dict, fallback: ExtractionResult) -> ExtractionResult:
    """Validate an LLM extraction against the Objective enums; fall back to the
    regex result on any failure."""
    def _valid_domain(d: str) -> bool:
        return d in {e.value for e in ObjectiveDomain}

    def _valid_risk(r: str) -> bool:
        return r in {e.value for e in RiskTolerance}

    valid = (isinstance(payload, dict)
             and isinstance(payload.get("title"), str)
             and isinstance(payload.get("goal"), str)
             and _valid_domain(payload.get("domain", ""))
             and _valid_risk(payload.get("risk_tolerance", "")))
    if not valid:
        return fallback

    return ExtractionResult(
        text=fallback.text,
        title=payload.get("title") or fallback.title,
        domain=payload["domain"],
        domain_confidence=0.9,
        goal=payload.get("goal") or fallback.goal,
        constraints=[c for c in payload.get("constraints", []) if isinstance(c, str)][:6]
                    or fallback.constraints,
        success_criteria=[c for c in payload.get("success_criteria", []) if isinstance(c, str)][:6]
                         or fallback.success_criteria,
        risk_tolerance=payload["risk_tolerance"],
        risk_confidence=0.9,
        time_horizon_years=payload.get("time_horizon_years") or fallback.time_horizon_years,
        time_confidence=0.9,
        population_scale=float(payload.get("population_scale") or fallback.population_scale),
        population_confidence=0.9,
        confidence_required=float(payload.get("confidence_required") or 70.0),
        provenance={
            "method": "llm",
            "stage": 2,
            "offline": False,
            "text_hash": fallback.provenance.get("text_hash"),
            "validated": True,
        },
    )


def extract_objective(
    text: str,
    use_llm: bool = False,
    timeout_s: int = 45,
) -> ExtractionResult:
    """Extract a structured Objective from a free-text brief.

    Stage 1 (regex) always runs and is authoritative when the LLM is disabled
    or fails validation. Stage 2 (optional) reuses the provider-agnostic LLM
    client from the Kriegspiel synthesis layer.
    """
    fallback = extract_regex(text)
    if not use_llm:
        return fallback

    try:
        from engines.kriegspiel.llm import get_llm_client
        client = get_llm_client()
        if client is None or not client.is_ready():
            return fallback
        prompt = _LLM_PROMPT.format(
            text=text,
            domains="|".join(sorted(e.value for e in ObjectiveDomain)),
            risks="|".join(sorted(e.value for e in RiskTolerance)),
        )
        response = client.complete(prompt)
        payload = json.loads(response.text.strip())
        result = _validate_llm_payload(payload, fallback)
        result.provenance["provider"] = response.provider
        result.provenance["model"] = response.model
        result.provenance["prompt_hash"] = response.prompt_hash
        result.provenance["latency_ms"] = response.latency_ms
        return result
    except Exception:
        # Any LLM failure falls back to the deterministic extraction.
        return fallback