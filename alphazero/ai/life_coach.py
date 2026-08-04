"""AI Life Coach - Advises based on simulation outcomes and character development.

This agent provides coaching advice, suggestions, and recommendations based on
character attributes, simulation results, and life coaching principles.
"""

from __future__ import annotations

import json
from typing import Dict, List, Any, Optional

from engine.character import Character


class LifeCoachAgent:
    """Provides life coaching advice based on simulation outcomes and character state."""

    def __init__(self):
        self.coaching_sessions: List[Dict[str, Any]] = []
        self.knowledge_base: Dict[str, Any] = {
            "health_advice": {
                "improve": "Regular exercise (30 min daily), balanced diet, sleep 7-9 hours",
                "maintain": "Stay active, avoid excessive alcohol, regular check-ups",
            },
            "finance_advice": {
                "save": "Save 20% of income, build emergency fund, invest in diversified portfolio",
                "budget": "Track spending, eliminate debt, create monthly budget",
            },
            "career_advice": {
                "grow": "Develop new skills, seek mentorship, take on challenging projects",
                "transition": "Assess market demand, update resume, consider networking",
            },
            "relationship_advice": {
                "build": "Communicate openly, spend quality time, show appreciation",
                "maintain": "Resolve conflicts constructively, support each other",
            },
        }

    def analyze_character_state(self, character: Character) -> Dict[str, Any]:
        """Analyze character state and provide coaching recommendations."""
        analysis = {
            "overall_health": self._assess_overall_health(character),
            "growth_areas": self._identify_growth_areas(character),
            "strengths": self._identify_strengths(character),
            "immediate_focus": self._prioritize_focus_areas(character),
            "life_advice": self._generate_life_advice(character),
        }
        return analysis

    def _assess_overall_health(self, character: Character) -> Dict[str, Any]:
        """Assess character's overall health and well-being."""
        health_score = (character.happiness + character.health + character.smarts + character.looks) / 4

        return {
            "health_level": self._health_level_category(health_score),
            "risk_factors": self._identify_risk_factors(character),
            "area_of_concern": self._identify_concern_areas(character),
            "health_action_needed": self._get_health_action_needed(health_score),
        }

    def _health_level_category(self, score: float) -> str:
        """Categorize health level based on score."""
        if score >= 80:
            return "excellent"
        elif score >= 65:
            return "good"
        elif score >= 50:
            return "moderate"
        elif score >= 35:
            return "concerning"
        else:
            return "critical"

    def _identify_risk_factors(self, character: Character) -> List[str]:
        """Identify potential risk factors based on character attributes."""
        risk_factors = []

        if character.health < 50:
            risk_factors.append("Poor health may impact longevity and quality of life")

        if character.happiness < 40:
            risk_factors.append("Low happiness could lead to depression or poor motivation")

        if character.net_worth < 0:
            risk_factors.append("Negative net worth creates financial stress")

        if not character.is_employed and character.money < 1000:
            risk_factors.append("Unemployment with low savings creates financial insecurity")

        return risk_factors

    def _identify_concern_areas(self, character: Character) -> List[str]:
        """Identify areas of concern that need immediate attention."""
        concerns = []

        if character.health < 40:
            concerns.append("health")

        if character.happiness < 30:
            concerns.append("mental well-being")

        if character.net_worth < -5000:
            concerns.append("financial stability")

        return concerns

    def _get_health_action_needed(self, health_score: float) -> Dict[str, str]:
        """Get specific health actions based on health score."""
        if health_score < 40:
            return {
                "immediate": "Seek medical attention",
                "short_term": "Establish healthy routines",
                "long_term": "Rebuild health foundation",
            }
        elif health_score < 55:
            return {
                "immediate": "Schedule wellness check-up",
                "short_term": "Improve diet and exercise",
                "long_term": "Establish sustainable habits",
            }
        elif health_score < 70:
            return {
                "immediate": "Review lifestyle habits",
                "short_term": "Set health goals",
                "long_term": "Maintain current improvements",
            }
        else:
            return {
                "immediate": "Continue healthy habits",
                "short_term": "Set new health goals",
                "long_term": "Optimize health and performance",
            }

    def _identify_growth_areas(self, character: Character) -> List[Dict[str, Any]]:
        """Identify areas where character can grow and improve."""
        growth_areas = []

        if character.health < 60:
            growth_areas.append({
                "area": "Health",
                "current_state": f"Health: {character.health}/100",
                "priority": "high" if character.health < 40 else "medium",
                "suggested_actions": self.knowledge_base["health_advice"]["improve"],
                "expected_impact": "Better longevity, more energy, improved quality of life",
            })

        if character.net_worth < 10000:
            growth_areas.append({
                "area": "Financial Stability",
                "current_state": f"Net Worth: ${character.net_worth:,.2f}",
                "priority": "high" if character.net_worth < 0 else "medium",
                "suggested_actions": self.knowledge_base["finance_advice"]["save"],
                "expected_impact": "Reduced stress, greater security, more opportunities",
            })

        if character.smarts < 60:
            growth_areas.append({
                "area": "Knowledge & Skills",
                "current_state": f"Smarts: {character.smarts}/100",
                "priority": "medium",
                "suggested_actions": "Learn new skills, read more, seek challenges",
                "expected_impact": "Better career prospects, increased problem-solving ability",
            })

        return growth_areas

    def _identify_strengths(self, character: Character) -> List[Dict[str, Any]]:
        """Identify character's strengths and advantages."""
        strengths = []

        if character.happiness >= 70:
            strengths.append({
                "area": "Emotional Well-being",
                "current_state": f"Happiness: {character.happiness}/100",
                "value": "Positive outlook enables better decision-making and resilience",
            })

        if character.net_worth > 50000:
            strengths.append({
                "area": "Financial Security",
                "current_state": f"Net Worth: ${character.net_worth:,.2f}",
                "value": "Provides security and opportunities for investment and growth",
            })

        if character.health >= 80:
            strengths.append({
                "area": "Physical Health",
                "current_state": f"Health: {character.health}/100",
                "value": "Foundation for pursuing goals and enjoying life",
            })

        return strengths

    def _prioritize_focus_areas(self, character: Character) -> List[str]:
        """Prioritize areas where character should focus attention."""
        focus_areas = []

        if character.health < 50:
            focus_areas.append("Health is the foundation for all other life goals")

        if character.net_worth < 0:
            focus_areas.append("Financial stability is critical for peace of mind")

        if character.smarts < 40:
            focus_areas.append("Education and skills unlock future opportunities")

        if character.happiness < 35:
            focus_areas.append("Mental well-being affects all life decisions")

        return focus_areas

    def _generate_life_advice(self, character: Character) -> Dict[str, Any]:
        """Generate holistic life advice based on character's situation."""
        advice = {
            "overall philosophy": self._get_philosophical_advice(character),
            "daily_habits": self._suggest_daily_habits(character),
            "medium_term_goals": self._suggest_medium_term_goals(character),
            "long_term_vision": self._suggest_long_term_vision(character),
            "key_insight": self._derive_key_insight(character),
        }
        return advice

    def _get_philosophical_advice(self, character: Character) -> str:
        """Get philosophical advice based on character's attributes."""
        if character.net_worth > 100000:
            return (
                "Wealth is a tool, not a goal. Focus on using it to create meaningful "
                "experiences and help others. Balance security with growth."
            )
        elif character.health < 50:
            return (
                "Health is your most valuable asset. Every decision should consider its "
                "impact on your well-being. Quality over quantity in all things."
            )
        elif character.happiness < 50:
            return (
                "Happiness comes from within, but external circumstances can help or hinder. "
                "Focus on building habits that nurture joy and meaning."
            )
        else:
            return (
                "You're in a good position to pursue your authentic path. Use your strengths "
                "to create value for yourself and others. Stay curious and grow." 
            )

    def _suggest_daily_habits(self, character: Character) -> List[str]:
        """Suggest daily habits based on character's needs."""
        habits = []

        if character.health < 60:
            habits.append("Start with 10-minute morning stretching and meditation")

        if character.net_worth < 10000:
            habits.append("Track all expenses and save at least $100 daily if possible")

        if character.smarts < 60:
            habits.append("Dedicate 30 minutes daily to learning something new")

        if character.happiness < 60:
            habits.append("Practice gratitude by noting 3 things you're grateful for each evening")

        habits.extend([
            "Get 7-9 hours of quality sleep",
            "Maintain social connections with friends and family",
            "Exercise for at least 30 minutes",
            "Set aside time for hobbies and activities you enjoy",
        ])

        return habits

    def _suggest_medium_term_goals(self, character: Character) -> List[str]:
        """Suggest 6-12 month goals based on character's situation."""
        goals = []

        if character.health < 60:
            goals.append(f"Improve health score by {70 - character.health} points through exercise and diet")

        if character.net_worth < 20000:
            goals.append(f"Build emergency fund to ${20000 - abs(character.net_worth):,.0f}")

        if not character.is_employed:
            goals.append("Develop skills for employment in your field of interest")

        goals.extend([
            "Develop a new skill or hobby",
            "Strengthen important relationships",
            "Complete a personal development project",
        ])

        return goals

    def _suggest_long_term_vision(self, character: Character) -> str:
        """Suggest long-term vision based on character's attributes."""
        if character.happiness > 70 and character.health > 70:
            return (
                "Pursue your passions and create lasting impact. Consider mentorship, "
                "community involvement, or creative pursuits that align with your values."
            )
        elif character.health < 50:
            return (
                "Focus on recovery and building a sustainable foundation. Health is the "
                "platform from which all other goals can be achieved."
            )
        elif character.net_worth > 50000:
            return (
                "Use your financial resources to create opportunities for yourself and others. "
                "Consider investments, philanthropy, or entrepreneurial ventures."
            )
        else:
            return (
                "Build a balanced life where health, relationships, and purpose all thrive. "
                "Take calculated risks and stay adaptable to change."
            )

    def _derive_key_insight(self, character: Character) -> str:
        """Derive a key insight about the character based on their state."""
        if character.happiness > character.health:
            return (
                "Your emotional resilience is stronger than your physical condition. "
                "Channel this mental strength into improving your health habits."
            )
        elif character.net_worth > 0 and character.happiness > 60:
            return (
                "You have both financial stability and emotional well-being. "
                "This is a strong foundation for pursuing meaningful goals and helping others."
            )
        elif character.health < 50 and character.net_worth < 0:
            return (
                "You face significant challenges in both health and finances. "
                "Prioritize immediate stability - health first, then financial security. "
                "Small, consistent steps will lead to meaningful change."
            )
        else:
            return (
                "You have a good balance of attributes. Focus on leveraging your strengths "
                "to overcome areas of weakness and continue growing toward your full potential."
            )

    def provide_coaching(self, character: Character, situation: str) -> Dict[str, Any]:
        """Provide specific coaching based on a situation or challenge."""
        coaching = {
            "situation": situation,
            "analysis": self.analyze_character_state(character),
            "specific_recommendations": self._generate_specific_recommendations(character, situation),
            "action_plan": self._create_action_plan(character, situation),
            "encouragement": self._provide_encouragement(character),
        }

        self.coaching_sessions.append({
            "timestamp": "now",
            "situation": situation,
            "character": character.name,
            "recommendations": coaching["specific_recommendations"],
        })

        return coaching

    def _generate_specific_recommendations(
        self, character: Character, situation: str
    ) -> List[str]:
        """Generate specific recommendations based on situation."""
        recommendations = []

        if situation == "career_change":
            recommendations.extend([
                "Research your alternative career path thoroughly",
                "Update your skills or education if needed",
                "Network with people in that field",
                "Create a financial plan for the transition",
            ])

        elif situation == "relationship_issues":
            recommendations.extend([
                "Schedule a honest conversation about concerns",
                "Consider couples therapy or counseling",
                "Identify what you value most in the relationship",
                "Practice active listening and empathy",
            ])

        elif situation == "health_concerns":
            recommendations.extend([
                "Consult with a healthcare professional",
                "Start with small, manageable lifestyle changes",
                "Set realistic health goals",
                "Build a support system for accountability",
            ])

        elif situation == "financial_problems":
            recommendations.extend([
                "Create a detailed budget and stick to it",
                "Look for ways to increase income",
                "Negotiate with creditors if needed",
                "Seek financial counseling if overwhelmed",
            ])

        else:
            recommendations.extend([
                "Break down your challenge into smaller, manageable steps",
                "Focus on what you can control, not what you can't",
                "Seek support from trusted friends, family, or professionals",
                "Practice patience and self-compassion",
            ])

        return recommendations

    def _create_action_plan(self, character: Character, situation: str) -> Dict[str, Any]:
        """Create a structured action plan."""
        return {
            "immediate_steps": self._get_immediate_steps(character, situation),
            "short_term_goals": self._get_short_term_goals(character, situation),
            "long_term_vision": self._get_long_term_vision(character, situation),
            "success_metrics": self._define_success_metrics(character, situation),
        }

    def _get_immediate_steps(self, character: Character, situation: str) -> List[str]:
        """Get immediate steps to take."""
        steps = []

        if situation == "health_concerns":
            steps.extend([
                "Schedule doctor appointment this week",
                "Start walking 15 minutes daily",
                "Prepare healthy meals for the week",
            ])

        elif situation == "financial_problems":
            steps.extend([
                "Create a 30-day spending freeze",
                "List all income and expenses",
                "Contact creditors if bills are overdue",
            ])

        else:
            steps.extend([
                "Write down what exactly needs to be done",
                "Pick one small step to take today",
                "Set a deadline for completion",
            ])

        return steps

    def _get_short_term_goals(
        self, character: Character, situation: str
    ) -> List[str]:
        """Get short-term goals."""
        goals = []

        if situation == "health_concerns":
            goals.append(f"Improve health score by 10 points in one month")
            goals.append(f"Establish consistent exercise routine")

        elif situation == "financial_problems":
            goals.append(f"Reduce expenses by 20%")
            goals.append(f"Build emergency fund of $1,000")

        else:
            goals.append(f"Complete specific task related to {situation}")
            goals.append(f"Track progress and adjust as needed")

        return goals

    def _get_long_term_vision(
        self, character: Character, situation: str
    ) -> str:
        """Get long-term vision."""
        if situation == "health_concerns":
            return (
                "Achieve optimal health that supports all other life goals and dreams. "
                "Become the best version of yourself physically and mentally."
            )
        elif situation == "financial_problems":
            return (
                "Achieve financial security and freedom. "
                "Have the resources to pursue your passions and support your loved ones."
            )
        else:
            return (
                "Overcome this challenge and grow stronger from the experience. "
                "Use this as an opportunity to develop new skills and resilience."
            )

    def _define_success_metrics(
        self, character: Character, situation: str
    ) -> List[str]:
        """Define success metrics."""
        metrics = []

        if situation == "health_concerns":
            metrics.extend([
                "Doctor reports improvement in health markers",
                "Can complete daily exercise without excessive fatigue",
                "Sleep quality improves",
            ])

        elif situation == "financial_problems":
            metrics.extend([
                "Debt reduces by 10%",
                "Monthly budget is consistently followed",
                "Emergency fund reaches minimum goal",
            ])

        else:
            metrics.extend([
                "Problem is resolved or significantly improved",
                "Develop new skills or habits",
                "Feel more confident in handling similar situations",
            ])

        return metrics

    def _provide_encouragement(self, character: Character) -> str:
        """Provide encouraging message."""
        if character.happiness > 60:
            return (
                "Your positive outlook is a powerful asset. Keep nurturing it while "
                "addressing areas that need attention. You have the capacity to succeed."
            )
        elif character.net_worth > 0:
            return (
                "You have financial resources to work with. Use them wisely to support "
                "your journey. Every step forward, no matter how small, counts."
            )
        elif character.health > 60:
            return (
                "Your health is your greatest foundation. You have the resilience to "
                "overcome challenges. Trust in your ability to adapt and grow."
            )
        else:
            return (
                "Even when times are tough, remember that change is possible. "
                "You have survived challenges before, and you can do it again. "
                "Every small step forward is progress."
            )

    def get_coaching_history(self) -> List[Dict[str, Any]]:
        """Get coaching session history."""
        return self.coaching_sessions

    def get_insights(self, character: Character) -> Dict[str, Any]:
        """Generate insights about the character based on their life state."""
        insights = {
            "personality_profile": self._create_personality_profile(character),
            "life_situation": self._analyze_life_situation(character),
            "key_strengths": self._identify_strengths(character),
            "growth_opportunities": self._identify_growth_areas(character),
            "recommended_focus": self._prioritize_focus_areas(character),
        }
        return insights

    def _create_personality_profile(self, character: Character) -> Dict[str, Any]:
        """Create a personality profile based on character attributes."""
        profile = {
            "type": self._determine_personality_type(character),
            "core_values": self._identify_core_values(character),
            "motivational_factors": self._identify_motivational_factors(character),
            "stress_responses": self._identify_stress_responses(character),
            "growth_style": self._identify_growth_style(character),
        }
        return profile

    def _determine_personality_type(self, character: Character) -> str:
        """Determine personality type based on attributes."""
        traits = []

        if character.happiness > 70:
            traits.append("optimistic")
        elif character.happiness < 40:
            traits.append("pessimistic")

        if character.health > 70:
            traits.append("healthy-conscious")
        elif character.health < 40:
            traits.append("health-challenged")

        if character.net_worth > 50000:
            traits.append("financially-secure")
        elif character.net_worth < 0:
            traits.append("financially-stressed")

        if character.smarts > 70:
            traits.append("intellectual")
        elif character.smarts < 40:
            traits.append("learning-challenged")

        if len(traits) == 0:
            return "balanced"

        return "-" .join(traits)

    def _identify_core_values(self, character: Character) -> List[str]:
        """Identify core values based on character's situation."""
        values = []

        if character.health < 50:
            values.append("health")

        if character.net_worth < 0:
            values.append("financial-security")

        if character.happiness > 60:
            values.append("joy")

        if character.smarts > 60:
            values.append("growth")

        if len(values) == 0:
            values.append("balance")

        return values

    def _identify_motivational_factors(self, character: Character) -> Dict[str, float]:
        """Identify what motivates the character."""
        factors = {
            "achievement": 0.5,
            "security": 0.5,
            "recognition": 0.5,
            "relationships": 0.5,
            "growth": 0.5,
        }

        if character.net_worth < 0:
            factors["security"] = 0.9

        if character.happiness < 40:
            factors["relationships"] = 0.8

        if character.health < 50:
            factors["security"] = 0.8

        if character.smarts > 70:
            factors["achievement"] = 0.8

        if character.desires:
            for desire, strength in character.desires.items():
                if desire in factors:
                    factors[desire] = max(factors[desire], strength)

        return factors

    def _identify_stress_responses(self, character: Character) -> Dict[str, str]:
        """Identify how the character responds to stress."""
        responses = {}

        if character.health < 50:
            responses["health_stress"] = "withdrawal"

        if character.net_worth < 0:
            responses["financial_stress"] = "overwhelms"

        if character.happiness < 40:
            responses["emotional_stress"] = "irrational-decision-making"

        return responses

    def _identify_growth_style(self, character: Character) -> str:
        """Identify character's growth style."""
        if character.health < 50 and character.net_worth < 0:
            return "structured"
        elif character.happiness > 60 and character.smarts > 60:
            return "exploratory"
        elif character.health > 60 and character.happiness > 60:
            return "balanced"
        else:
            return "incremental"

    def _analyze_life_situation(self, character: Character) -> Dict[str, Any]:
        """Analyze overall life situation."""
        life_score = (
            character.happiness
            + character.health
            + character.smarts
            + min(100, max(0, character.net_worth / 1000))
        ) / 4

        return {
            "overall_score": life_score,
            "life_stage": self._determine_life_stage(character.age),
            "situational_consciousness": self._assess_situational_consciousness(character),
            "resilience_indicators": self._assess_resilience(character),
            "support_needs": self._assess_support_needs(character),
        }

    def _determine_life_stage(self, age: int) -> str:
        """Determine life stage based on age."""
        if age < 25:
            return "early-career"
        elif age < 40:
            return "mid-career"
        elif age < 60:
            return "peak-years"
        else:
            return "later-years"

    def _assess_situational_consciousness(self, character: Character) -> Dict[str, Any]:
        """Assess character's situational consciousness."""
        awareness = {
            "financial_awareness": self._assess_financial_awareness(character),
            "health_awareness": self._assess_health_awareness(character),
            "career_awareness": self._assess_career_awareness(character),
        }

        return {
            "level": self._calculate_consciousness_level(awareness),
            "blind_spots": self._identify_consciousness_blind_spots(character),
            "growth_opportunities": self._identify_consciousness_growth(character),
        }

    def _assess_financial_awareness(self, character: Character) -> float:
        """Assess financial awareness."""
        if character.net_worth > 50000:
            return 0.9
        elif character.net_worth > 10000:
            return 0.7
        elif character.net_worth > 0:
            return 0.5
        elif character.net_worth > -5000:
            return 0.3
        else:
            return 0.1

    def _assess_health_awareness(self, character: Character) -> float:
        """Assess health awareness."""
        if character.health > 70:
            return 0.8
        elif character.health > 50:
            return 0.6
        elif character.health > 30:
            return 0.4
        else:
            return 0.2

    def _assess_career_awareness(self, character: Character) -> float:
        """Assess career awareness."""
        if character.occupation != "Unemployed":
            return 0.7
        elif character.education_level != "None":
            return 0.5
        else:
            return 0.3

    def _calculate_consciousness_level(self, awareness: Dict[str, float]) -> float:
        """Calculate overall consciousness level."""
        return (awareness["financial_awareness"] + awareness["health_awareness"] + awareness["career_awareness"]) / 3

    def _identify_consciousness_blind_spots(self, character: Character) -> List[str]:
        """Identify areas of limited awareness."""
        blind_spots = []

        if character.net_worth < 0 and character.occupation != "Unemployed":
            blind_spots.append("underestimating financial impact of current lifestyle")

        if character.health < 50 and character.occupation != "Unemployed":
            blind_spots.append("overestimating physical capacity in high-stress roles")

        if character.happiness < 50 and character.relationship_status != "Single":
            blind_spots.append("not recognizing relationship needs and boundaries")

        return blind_spots

    def _identify_consciousness_growth(self, character: Character) -> List[str]:
        """Identify areas for consciousness growth."""
        growth = []

        if character.net_worth < 0:
            growth.append("develop financial literacy and planning skills")

        if character.health < 50:
            growth.append("improve health literacy and self-care practices")

        if character.happiness < 50:
            growth.append("increase emotional intelligence and self-awareness")

        return growth

    def _assess_resilience(self, character: Character) -> Dict[str, float]:
        """Assess resilience indicators."""
        resilience = {
            "financial_resilience": self._calculate_financial_resilience(character),
            "health_resilience": self._calculate_health_resilience(character),
            "emotional_resilience": self._calculate_emotional_resilience(character),
        }

        return {
            "overall": (resilience["financial_resilience"] + resilience["health_resilience"] + resilience["emotional_resilience"]) / 3,
            "strongest": max(resilience, key=resilience.get),
            "weakest": min(resilience, key=resilience.get),
        }

    def _calculate_financial_resilience(self, character: Character) -> float:
        """Calculate financial resilience."""
        if character.net_worth > 50000:
            return 0.9
        elif character.net_worth > 10000:
            return 0.7
        elif character.net_worth > 0:
            return 0.5
        elif character.net_worth > -5000:
            return 0.3
        else:
            return 0.1

    def _calculate_health_resilience(self, character: Character) -> float:
        """Calculate health resilience."""
        return min(1.0, character.health / 100)

    def _calculate_emotional_resilience(self, character: Character) -> float:
        """Calculate emotional resilience."""
        if character.happiness > 70:
            return 0.9
        elif character.happiness > 50:
            return 0.7
        elif character.happiness > 30:
            return 0.5
        else:
            return 0.3

    def _assess_support_needs(self, character: Character) -> Dict[str, str]:
        """Assess support needs."""
        needs = {}

        if character.health < 50:
            needs["health"] = "professional medical support and possibly therapy"

        if character.net_worth < 0:
            needs["financial"] = "financial counseling and possibly assistance programs"

        if character.happiness < 40:
            needs["emotional"] = "emotional support from friends, family, or professionals"

        if character.smarts < 50:
            needs["education"] = "educational support or tutoring"

        return needs
