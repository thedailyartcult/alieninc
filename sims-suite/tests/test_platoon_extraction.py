"""Platoon extraction tests — Treiver-style objective extraction.

Stage 1 (regex/keyword) must be deterministic, offline, and produce a valid
Objective from a realistic client brief. The optional LLM stage falls back to
the deterministic result when no provider is configured.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from engines.platoon.extraction import extract_objective, extract_regex
from engines.platoon.objective import ObjectiveDomain, RiskTolerance


SAMPLE_BRIEF = (
    "We need to secure critical infrastructure against state-level cyber "
    "adversaries within 24 months. Achieve zero successful intrusions against "
    "crown-jewel systems. No disruption to live services. Budget capped at "
    "$50M. Must comply with NIST CSF 2.0. Mean time to detect under 15 "
    "minutes. Crown jewel breach rate below 2 percent. 100 percent asset "
    "coverage. Quarterly red-team pass rate above 90 percent."
)


def test_regex_extraction_detects_domain():
    result = extract_regex(SAMPLE_BRIEF)
    assert result.domain in {e.value for e in ObjectiveDomain}
    assert result.domain_confidence > 0.3
    # "cyber" + "intrusion" + "crown-jewel" + "red-team" strongly imply
    # cybersecurity in this brief.
    assert result.domain == "cybersecurity"


def test_regex_extraction_detects_risk_and_horizon():
    result = extract_regex(SAMPLE_BRIEF)
    assert result.risk_tolerance == RiskTolerance.CONSERVATIVE.value
    assert result.risk_confidence > 0.5
    assert result.time_horizon_years == 24 / 12  # "within 24 months"
    assert result.time_confidence > 0.5


def test_regex_extraction_finds_constraints_and_criteria():
    result = extract_regex(SAMPLE_BRIEF)
    assert len(result.constraints) >= 2
    assert any("No disruption to live services" in c for c in result.constraints)
    assert any("Budget capped at $50M" in c for c in result.constraints)
    assert len(result.success_criteria) >= 3


def test_extraction_builds_valid_objective():
    result = extract_objective(SAMPLE_BRIEF, use_llm=False)
    obj = result.to_objective()
    assert obj.domain == ObjectiveDomain.CYBERSECURITY
    assert obj.risk_tolerance == RiskTolerance.CONSERVATIVE
    assert obj.time_horizon_years == 2.0
    assert obj.constraints
    assert obj.success_criteria
    assert 0 <= obj.complexity <= 100


def test_extraction_is_deterministic():
    a = extract_regex(SAMPLE_BRIEF)
    b = extract_regex(SAMPLE_BRIEF)
    assert a.to_dict() == b.to_dict()


def test_llm_stage_falls_back_without_provider():
    import os
    # No LLM provider configured in the test env -> falls back to regex.
    result = extract_objective(SAMPLE_BRIEF, use_llm=True)
    assert result.provenance["method"] == "regex"
    assert result.provenance["offline"] is True
    assert result.domain == "cybersecurity"


def test_extraction_handles_short_brief():
    result = extract_regex("Model regional conflict impact on operations")
    assert result.domain == "national_security"
    assert result.goal  # non-empty goal clause
    assert result.to_objective() is not None


def test_unknown_domain_defaults_to_corporate():
    from engines.platoon.extraction import _detect_domain
    domain, conf = _detect_domain("nothing recognizable here at all")
    assert domain == "corporate_strategy"
    assert conf == 0.2


def test_year_based_horizon():
    from engines.platoon.extraction import _detect_horizon
    h, c = _detect_horizon("complete by 2030")
    assert c == 0.9
    assert h == 4.0  # 2030 - 2026


def test_nyear_pattern_horizon():
    from engines.platoon.extraction import _detect_horizon
    h, c = _detect_horizon("a 3-year transformation program")
    assert c == 0.9
    assert h == 3.0


def test_population_scale_detection():
    from engines.platoon.extraction import _detect_population_scale
    scale, conf = _detect_population_scale("affects 8.2 billion people")
    assert scale == 100.0
    assert conf == 0.85
    # Unspecified population -> low default with no confidence.
    scale2, conf2 = _detect_population_scale("general objective")
    assert scale2 == 30.0
    assert conf2 == 0.0


def test_balanced_risk_when_cues_equal():
    from engines.platoon.extraction import _detect_risk
    risk, conf = _detect_risk("no clear risk language at all")
    assert risk == RiskTolerance.BALANCED.value
    assert conf == 0.5


def test_goal_detection_uses_earliest_action_verb():
    from engines.platoon.extraction import _detect_goal
    g = _detect_goal("Maximize shareholder value. Diversify supply chains to reduce risk.")
    assert "Maximize shareholder value" in g


def test_extraction_detects_constraints_and_criteria():
    result = extract_regex("Secure systems. Must comply with GDPR. Reduce breach rate below 2 percent. Budget capped at 1M. No cost increase to customers.")
    assert any("Must comply with GDPR" in c for c in result.constraints)
    assert any("No cost increase" in c for c in result.constraints)
    assert any("below 2 percent" in c for c in result.success_criteria)


def test_extraction_handles_emptyish_brief():
    # A brief with no recognized domain keywords still yields a valid objective.
    result = extract_regex("Improve things.")
    assert result.domain == "corporate_strategy"
    assert result.to_objective() is not None
    assert result.time_horizon_years is None


def test_extraction_title_truncation():
    result = extract_regex("This is a very long objective title that should be truncated to eight words total for display purposes")
    assert len(result.title.split()) <= 9  # 8 words + "..." if truncated