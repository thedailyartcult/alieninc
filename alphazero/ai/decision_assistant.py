"""AI Decision Assistant - Interprets simulation results and suggests life paths.

This agent analyzes simulation outcomes and provides strategic decision guidance,
helping users understand implications and make informed choices about their life paths.
"""

from __future__ import annotations

from typing import Dict, List, Any


class DecisionAssistantAgent:
    """Interprets simulation results and suggests life paths and decisions."""

    def __init__(self):
        self.decision_history: List[Dict[str, Any]] = []
        self.scenario_templates: Dict[str, Dict[str, Any]] = {}

    def analyze_simulation_outcomes(self, simulation_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze simulation outcomes and provide decision insights."""
        analysis = {
            "summary": self._create_outcome_summary(simulation_results),
            "path_analysis": self._analyze_potential_paths(simulation_results),
            "risk_assessment": self._assess_risks_and_opportunities(simulation_results),
            "recommendations": self._generate_path_recommendations(simulation_results),
            "decision_points": self._identify_key_decision_points(simulation_results),
            "scenario_projections": self._project_scenarios(simulation_results),
        }
        return analysis

    def _create_outcome_summary(self, simulation_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create a summary of simulation outcomes."""
        if not simulation_results:
            return {"error": "No simulation results provided"}

        net_worths = [result.get("final_net_worth", 0) for result in simulation_results]
        happiness_levels = [result.get("final_happiness", 0) for result in simulation_results]
        life_expectancies = [result.get("years_lived", 0) for result in simulation_results]

        return {
            "total_simulations": len(simulation_results),
            "net_worth_range": {
                "min": min(net_worths) if net_worths else 0,
                "max": max(net_worths) if net_worths else 0,
                "mean": sum(net_worths) / len(net_worths) if net_worths else 0,
                "median": sorted(net_worths)[len(net_worths) // 2] if net_worths else 0,
            },
            "happiness_range": {
                "min": min(happiness_levels) if happiness_levels else 0,
                "max": max(happiness_levels) if happiness_levels else 0,
                "mean": sum(happiness_levels) / len(happiness_levels) if happiness_levels else 0,
                "median": sorted(happiness_levels)[len(happiness_levels) // 2] if happiness_levels else 0,
            },
            "life_expectancy_range": {
                "min": min(life_expectancies) if life_expectancies else 0,
                "max": max(life_expectancies) if life_expectancies else 0,
                "mean": sum(life_expectancies) / len(life_expectancies) if life_expectancies else 0,
            },
        }

    def _analyze_potential_paths(self, simulation_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze potential paths from simulation results."""
        if not simulation_results:
            return {}

        paths = {
            "wealth_focused": [],
            "happiness_focused": [],
            "balanced": [],
            "struggling": [],
        }

        for result in simulation_results:
            net_worth = result.get("final_net_worth", 0)
            happiness = result.get("final_happiness", 0)

            if net_worth > 50000 and happiness > 70:
                paths["balanced"].append(result)
            elif net_worth > 50000 and happiness <= 70:
                paths["wealth_focused"].append(result)
            elif net_worth <= 50000 and happiness > 70:
                paths["happiness_focused"].append(result)
            else:
                paths["struggling"].append(result)

        return paths

    def _assess_risks_and_opportunities(self, simulation_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Assess risks and opportunities."""
        if not simulation_results:
            return {}

        net_worths = [result.get("final_net_worth", 0) for result in simulation_results]
        happiness_levels = [result.get("final_happiness", 0) for result in simulation_results]

        risk_factors = []
        opportunities = []

        if max(net_worths) > 100000:
            opportunities.append("High wealth accumulation potential (> $100K)")

        if max(happiness_levels) > 80:
            opportunities.append("High happiness achievement possible (>80)")

        if min(net_worths) < 0:
            risk_factors.append("Financial ruin risk")

        if min(happiness_levels) < 30:
            risk_factors.append("Severe life dissatisfaction")

        return {
            "risk_factors": risk_factors,
            "opportunities": opportunities,
            "convergence_analysis": self._analyze_convergence(simulation_results),
        }

    def _analyze_convergence(self, simulation_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze convergence patterns in simulation results."""
        if not simulation_results:
            return {}

        net_worths = [result.get("final_net_worth", 0) for result in simulation_results]
        happiness_levels = [result.get("final_happiness", 0) for result in simulation_results]

        similar_count = self._count_similar_outcomes(simulation_results)
        similarity_rate = similar_count / len(simulation_results) if simulation_results else 0

        return {
            "similar_outcomes_count": similar_count,
            "similarity_rate": similarity_rate,
            "outcome_diversity": 1.0 - similarity_rate,
            "dominant_path": self._identify_dominant_path(simulation_results),
        }

    def _count_similar_outcomes(self, simulation_results: List[Dict[str, Any]]) -> int:
        """Count similar outcomes based on clustering."""
        if len(simulation_results) < 3:
            return len(simulation_results)

        net_worths = [result.get("final_net_worth", 0) for result in simulation_results]
        happiness_levels = [result.get("final_happiness", 0) for result in simulation_results]

        similar = 0
        for i, result in enumerate(simulation_results):
            nw = result.get("final_net_worth", 0)
            hap = result.get("final_happiness", 0)

            for j, other_result in enumerate(simulation_results):
                if i == j:
                    continue

                other_nw = other_result.get("final_net_worth", 0)
                other_hap = other_result.get("final_happiness", 0)

                if abs(nw - other_nw) < 10000 and abs(hap - other_hap) < 10:
                    similar += 1
                    break

        return similar

    def _identify_dominant_path(self, simulation_results: List[Dict[str, Any]]) -> str:
        """Identify the dominant life path from simulation results."""
        if not simulation_results:
            return "undefined"

        paths = self._analyze_potential_paths(simulation_results)

        path_counts = {
            "wealth_focused": len(paths["wealth_focused"]),
            "happiness_focused": len(paths["happiness_focused"]),
            "balanced": len(paths["balanced"]),
            "struggling": len(paths["struggling"]),
        }

        return max(path_counts, key=path_counts.get)

    def _generate_path_recommendations(self, simulation_results: List[Dict[str, Any]]) -> List[str]:
        """Generate recommendations based on simulation outcomes."""
        recommendations = []

        if not simulation_results:
            return recommendations

        net_worths = [result.get("final_net_worth", 0) for result in simulation_results]
        happiness_levels = [result.get("final_happiness", 0) for result in simulation_results]

        risk_assessment = self._assess_risks_and_opportunities(simulation_results)
        path_analysis = self._analyze_potential_paths(simulation_results)

        if risk_assessment.get("risk_factors"):
            recommendations.extend(risk_assessment.get("risk_factors"))

        if risk_assessment.get("opportunities"):
            recommendations.extend(risk_assessment.get("opportunities"))

        if path_analysis.get("balanced"):
            recommendations.append("Balanced paths (wealth + happiness) are most achievable")

        if path_analysis.get("wealth_focused"):
            recommendations.append("Wealth-focused paths demonstrate strong financial strategies")

        if path_analysis.get("happiness_focused"):
            recommendations.append("Happiness-focused paths show the value of non-material success")

        return recommendations

    def _identify_key_decision_points(self, simulation_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Identify key decision points from simulation outcomes."""
        decision_points = []

        if not simulation_results:
            return decision_points

        net_worths = [result.get("final_net_worth", 0) for result in simulation_results]
        happiness_levels = [result.get("final_happiness", 0) for result in simulation_results]

        critical_thresholds = {
            "financial_security": 50000,
            "high_happiness": 80,
            "moderate_wellbeing": 30000,
        }

        for result in simulation_results:
            nw = result.get("final_net_worth", 0)
            hap = result.get("final_happiness", 0)

            decisions = []

            if nw < critical_thresholds["moderate_wellbeing"]:
                decisions.append("financial_stability")

            if nw > critical_thresholds["financial_security"]:
                decisions.append("financial_freedom")

            if hap < 40:
                decisions.append("life_satisfaction")

            if hap > critical_thresholds["high_happiness"]:
                decisions.append("optimizing_wellbeing")

            if decisions:
                decision_points.append({
                    "outcome": result,
                    "key_decisions": decisions,
                    "priority": self._prioritize_decisions(decisions),
                })

        return decision_points

    def _prioritize_decisions(self, decisions: List[str]) -> str:
        """Prioritize decisions based on their impact."""
        priority_map = {
            "financial_stability": "high",
            "financial_freedom": "medium",
            "life_satisfaction": "high",
            "optimizing_wellbeing": "medium",
        }

        if not decisions:
            return "low"

        max_priority = max(priority_map.get(d, "low") for d in decisions)
        return max_priority

    def _project_scenarios(self, simulation_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Project future scenarios based on simulation patterns."""
        if not simulation_results:
            return {}

        return {
            "current_trends": self._analyze_trends(simulation_results),
            "best_case_scenario": self._create_best_case_scenario(simulation_results),
            "worst_case_scenario": self._create_worst_case_scenario(simulation_results),
            "most_likely_scenario": self._identify_most_likely_scenario(simulation_results),
        }

    def _analyze_trends(self, simulation_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze trends in simulation results."""
        if not simulation_results:
            return {}

        net_worths = [result.get("final_net_worth", 0) for result in simulation_results]
        happiness_levels = [result.get("final_happiness", 0) for result in simulation_results]

        return {
            "net_worth_trend": self._calculate_trend(net_worths),
            "happiness_trend": self._calculate_trend(happiness_levels),
            "stability_score": self._calculate_stability(net_worths, happiness_levels),
        }

    def _calculate_trend(self, values: List[float]) -> str:
        """Calculate trend direction."""
        if len(values) < 3:
            return "insufficient_data"

        first_half = values[:len(values) // 2]
        second_half = values[len(values) // 2:]

        first_avg = sum(first_half) / len(first_half)
        second_avg = sum(second_half) / len(second_half)

        change_percent = ((second_avg - first_avg) / first_avg) * 100 if first_avg != 0 else 0

        if change_percent > 10:
            return "improving"
        elif change_percent < -10:
            return "declining"
        else:
            return "stable"

    def _calculate_stability(self, net_worths: List[float], happiness_levels: List[float]) -> float:
        """Calculate stability score."""
        if len(net_worths) < 2:
            return 0

        nw_stability = 1.0 - (max(net_worths) - min(net_worths)) / max(net_worths) if max(net_worths) > 0 else 0
        hap_stability = 1.0 - (max(happiness_levels) - min(happiness_levels)) / 100

        return (nw_stability + hap_stability) / 2

    def _create_best_case_scenario(self, simulation_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create best case scenario."""
        if not simulation_results:
            return {}

        best_by_net_worth = max(simulation_results, key=lambda x: x.get("final_net_worth", 0))
        best_by_happiness = max(simulation_results, key=lambda x: x.get("final_happiness", 0))

        return {
            "best_wealth": best_by_net_worth,
            "best_happiness": best_by_happiness,
            "balanced_best": self._find_most_balanced(simulation_results),
        }

    def _create_worst_case_scenario(self, simulation_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create worst case scenario."""
        if not simulation_results:
            return {}

        worst_by_net_worth = min(simulation_results, key=lambda x: x.get("final_net_worth", 0))
        worst_by_happiness = min(simulation_results, key=lambda x: x.get("final_happiness", 0))

        return {
            "worst_wealth": worst_by_net_worth,
            "worst_happiness": worst_by_happiness,
        }

    def _identify_most_likely_scenario(self, simulation_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Identify the most likely scenario."""
        if not simulation_results:
            return {}

        paths = self._analyze_potential_paths(simulation_results)
        path_counts = {
            "wealth_focused": len(paths["wealth_focused"]),
            "happiness_focused": len(paths["happiness_focused"]),
            "balanced": len(paths["balanced"]),
            "struggling": len(paths["struggling"]),
        }

        most_likely_path = max(path_counts, key=path_counts.get)
        sample_result = paths[most_likely_path][0] if paths[most_likely_path] else simulation_results[0]

        return {
            "path_type": most_likely_path,
            "probability": path_counts[most_likely_path] / len(simulation_results),
            "sample_outcome": sample_result,
            "character_recommendations": self._get_path_recommendations(most_likely_path),
        }

    def _get_path_recommendations(self, path_type: str) -> List[str]:
        """Get recommendations for a specific path type."""
        recommendations = {
            "wealth_focused": [
                "Invest in diversified assets",
                "Develop high-income skills",
                "Practice disciplined saving and budgeting",
                "Minimize lifestyle inflation",
            ],
            "happiness_focused": [
                "Cultivate gratitude and mindfulness",
                "Invest in relationships and community",
                "Pursue meaningful hobbies and passions",
                "Maintain work-life balance",
            ],
            "balanced": [
                "Build emergency funds and savings",
                "Develop multiple income streams",
                "Practice regular reflection and adjustment",
                "Maintain flexible lifestyle choices",
            ],
            "struggling": [
                "Seek professional help and guidance",
                "Develop concrete action plans",
                "Build supportive networks",
                "Set realistic, achievable goals",
            ],
        }

        return recommendations.get(path_type, [])

    def _find_most_balanced(self, simulation_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Find the most balanced outcome."""
        if not simulation_results:
            return {}

        balanced_results = [
            result for result in simulation_results
            if 30000 <= result.get("final_net_worth", 0) <= 100000
            and 60 <= result.get("final_happiness", 0) <= 85
        ]

        if not balanced_results:
            return simulation_results[0]

        return max(
            balanced_results,
            key=lambda x: (x.get("final_net_worth", 0) + x.get("final_happiness", 0)) / 2
        )

    def get_decision_insights(self, simulation_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Get comprehensive decision insights."""
        analysis = self.analyze_simulation_outcomes(simulation_results)

        insights = {
            "key_findings": self._extract_key_findings(simulation_results),
            "strategic_recommendations": analysis["recommendations"],
            "risk_management": self._develop_risk_management_plan(simulation_results),
            "success_factors": self._identify_success_factors(simulation_results),
            "avoidance_recommendations": self._identify_avoidance_recommendations(simulation_results),
        }

        return insights

    def _extract_key_findings(self, simulation_results: List[Dict[str, Any]]) -> List[str]:
        """Extract key findings from simulation results."""
        findings = []

        if not simulation_results:
            return findings

        net_worths = [result.get("final_net_worth", 0) for result in simulation_results]
        happiness_levels = [result.get("final_happiness", 0) for result in simulation_results]

        analysis = self.analyze_simulation_outcomes(simulation_results)

        if analysis["path_analysis"]["balanced"]:
            findings.append(f"Balanced outcomes (wealth + happiness) account for {len(analysis['path_analysis']['balanced'])}/{len(simulation_results)} scenarios")

        if analysis["path_analysis"]["wealth_focused"]:
            findings.append(f"Wealth-focused paths demonstrate significant financial success for some individuals")

        if analysis["path_analysis"]["happiness_focused"]:
            findings.append(f"Happiness-focused paths show that non-material success is achievable")

        if analysis["risk_assessment"]["risk_factors"]:
            findings.append(f"Key risks to avoid: {', '.join(analysis['risk_assessment']['risk_factors'])}")

        if analysis["risk_assessment"]["opportunities"]:
            findings.append(f"Major opportunities exist: {', '.join(analysis['risk_assessment']['opportunities'])}")

        return findings

    def _develop_risk_management_plan(self, simulation_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Develop a risk management plan."""
        if not simulation_results:
            return {}

        return {
            "primary_risks": ["financial_instability", "health_issues", "relationship_strain"],
            "mitigation_strategies": [
                "Build emergency funds and insurance",
                "Maintain healthy lifestyle habits",
                "Cultivate strong social connections",
                "Develop diverse skill sets",
            ],
            "early_warning_signs": self._identify_early_warning_signs(simulation_results),
        }

    def _identify_early_warning_signs(self, simulation_results: List[Dict[str, Any]]) -> List[str]:
        """Identify early warning signs from simulation results."""
        signs = []

        if not simulation_results:
            return signs

        net_worths = [result.get("final_net_worth", 0) for result in simulation_results]
        happiness_levels = [result.get("final_happiness", 0) for result in simulation_results]

        if any(nw < 0 for nw in net_worths):
            signs.append("Negative net worth indicates financial problems")

        if any(hap < 30 for hap in happiness_levels):
            signs.append("Low happiness signals life dissatisfaction")

        if any(nw < 10000 and hap < 50 for nw, hap in zip(net_worths, happiness_levels)):
            signs.append("Combined financial and emotional distress")

        return signs

    def _identify_success_factors(self, simulation_results: List[Dict[str, Any]]) -> List[str]:
        """Identify success factors from simulation results."""
        return [
            "Financial discipline and planning",
            "Strong social support networks",
            "Continuous learning and adaptation",
            "Balanced priorities (wealth + happiness)",
            "Resilience in facing challenges",
        ]

    def _identify_avoidance_recommendations(self, simulation_results: List[Dict[str, Any]]) -> List[str]:
        """Identify what to avoid based on simulation results."""
        return [
            "Excessive debt and financial leverage",
            "Neglecting health for wealth",
            "Isolating from social connections",
            "Chasing wealth at the expense of happiness",
            "Procrastinating on important decisions",
        ]

    def save_decision(self, simulation_result: Dict[str, Any], recommendations: List[str]) -> None:
        """Save a decision to history."""
        decision = {
            "timestamp": "now",
            "simulation_result": simulation_result,
            "recommendations": recommendations,
        }
        self.decision_history.append(decision)


def main() -> None:
    """CLI entry point: read JSON on stdin, write JSON on stdout.

    Protocol (used by the Rust MCP client and Go core integration):
      input:  {"simulation_results": [...]}
      output: {"status": "success", "result": {...analysis...}}
    """
    import sys
    import json as _json

    try:
        raw = sys.stdin.buffer.read().decode("utf-8")
    except Exception:
        raw = ""

    request = {}
    if raw:
        try:
            request = _json.loads(raw)
        except (_json.JSONDecodeError, TypeError):
            request = {}

    results = request.get("simulation_results", [])
    agent = DecisionAssistantAgent()
    analysis = agent.analyze_simulation_outcomes(results)
    print(_json.dumps({"status": "success", "result": analysis}, default=str))


if __name__ == "__main__":
    main()
