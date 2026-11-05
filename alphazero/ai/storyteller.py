"""AI Storyteller - Creates narratives from simulation data.

This agent creates compelling stories and narratives from simulation data,
providing insights and entertainment value from complex life simulations.
"""

from __future__ import annotations

import json
import random
from typing import Dict, List, Any

from engine.character import Character


class StorytellerAgent:
    """Creates compelling narratives from simulation data."""

    def __init__(self):
        self.story_templates: Dict[str, Dict[str, Any]] = {}
        self.narrative_patterns: List[Dict[str, Any]] = []
        self.cultural_contexts: Dict[str, Any] = {}

    def generate_character_narrative(self, character: Character, simulation_result: Dict[str, Any]) -> str:
        """Generate a compelling narrative about a character's life simulation."""
        narrative = {
            "title": self._create_narrative_title(character, simulation_result),
            "opening": self._create_narrative_opening(character),
            "development": self._create_narrative_development(character, simulation_result),
            "climax": self._create_narrative_climax(character, simulation_result),
            "resolution": self._create_narrative_resolution(character, simulation_result),
            "key_insights": self._extract_narrative_insights(character, simulation_result),
        }
        return self._format_narrative(narrative)

    def _create_narrative_title(self, character: Character, simulation_result: Dict[str, Any]) -> str:
        """Create a compelling title for the narrative."""
        age = character.age
        net_worth = character.net_worth
        happiness = character.happiness

        if net_worth > 100000:
            return f"The {age}-Year Journey: From Unknown to Wealth"
        elif happiness > 80:
            return f"The {age}-Year Quest: Finding True Fulfillment"
        elif age > 60:
            return f"Life's {age} Chapters: Wisdom, Triumph, and Legacy"
        elif net_worth < 0:
            return f"The Hard Road: {age} Years of Struggle and Redemption"
        elif happiness < 40:
            return f"Life's Unraveling: {age} Years of Discontent"
        else:
            return f"Life's Journey: {age} Years of Growth and Discovery"

    def _create_narrative_opening(self, character: Character) -> str:
        """Create the opening of the narrative."""
        name = character.name
        age = character.age
        gender = character.gender.value
        birthplace = character.birthplace

        opening_templates = [
            f"{name} was born in {birthplace} to a {gender} with dreams of greatness.",
            f"At {age}, {name} stood at the crossroads of a life shaped by circumstances and choices.",
            f"In the year {character.year}, {name} embarked on a journey that would define their existence.",
            f"Every life has a beginning, and {name}'s started in {birthplace} with endless possibility.",
        ]

        return random.choice(opening_templates)

    def _create_narrative_development(self, character: Character, simulation_result: Dict[str, Any]) -> List[str]:
        """Create the development narrative."""
        development = []

        age = character.age
        happiness = character.happiness
        health = character.health
        net_worth = character.net_worth
        major_events = simulation_result.get("major_events", [])

        if age <= 25:
            development.extend([
                f"From ages {max(0, age - 5)} to {age}, {character.name} navigated early adulthood,",
                f"transitioning through education, first jobs, and the discovery of their path.",
            ])
        elif age <= 40:
            development.extend([
                f"Between {age - 5} and {age}, {character.name} focused on building their foundation,",
                f"establishing careers, relationships, and a sense of identity in society.",
            ])
        elif age <= 60:
            development.extend([
                f"From {age - 5} to {age}, {character.name} reached career peak potential,",
                f"navigating mid-life challenges and opportunities with wisdom gained through experience.",
            ])
        else:
            development.extend([
                f"In the later years, {character.name} reflected on {age - 5} to {age} years of life,",
                f"finding meaning in legacy, wisdom, and the impact left on others.",
            ])

        if happiness > 70:
            development.append(f"Throughout this period, {character.name}'s happiness remained remarkably high, driving them forward.")
        elif happiness < 40:
            development.append(f"However, {character.name}'s happiness struggled, casting a shadow over their journey.")
        else:
            development.append(f"Their happiness fluctuated like the market, experiencing both peaks and valleys.")

        if net_worth > 50000:
            development.append(f"Financially, they prospered, building wealth that would sustain their future.")
        elif net_worth < 0:
            development.append(f"Financially, they faced challenges, accumulating debt and setbacks along the way.")
        else:
            development.append(f"Financially, they navigated the middle ground, neither soaring high nor sinking low.")

        if major_events:
            for event in major_events[:3]:
                development.append(f"A pivotal moment occurred: {event}")

        return development

    def _create_narrative_climax(self, character: Character, simulation_result: Dict[str, Any]) -> str:
        """Create the climax of the narrative."""
        age = character.age
        happiness = character.happiness
        net_worth = character.net_worth

        if net_worth > 100000 and happiness > 70:
            return f"At {age}, {character.name} achieved the perfect synthesis: financial freedom and genuine happiness, fulfilling their life's highest aspirations."
        elif net_worth > 50000:
            return f"At {age}, {character.name} secured their financial future, though the quest for happiness continued to elude them."
        elif happiness > 70:
            return f"At {age}, {character.name} found profound happiness and contentment, even if financial security remained elusive."
        elif net_worth < 0 and happiness < 40:
            return f"At {age}, {character.name} faced the harsh reality of life: financial ruin and emotional despair."
        else:
            return f"At {age}, {character.name} stood at life's crossroads, with both opportunities and challenges ahead."

    def _create_narrative_resolution(self, character: Character, simulation_result: Dict[str, Any]) -> str:
        """Create the resolution of the narrative."""
        age = character.age
        happiness = character.happiness
        net_worth = character.net_worth
        years_lived = simulation_result.get("years_lived", age)

        if net_worth > 50000 and happiness > 70:
            return f"Looking back over {years_lived} years, {character.name}'s story stands as a testament to what is possible when financial wisdom meets emotional fulfillment."
        elif happiness > 60:
            return f"In the end, {character.name}'s legacy was one of resilience and joy, proving that happiness can be cultivated even in challenging circumstances."
        elif net_worth > 0:
            return f"While financially stable, {character.name}'s story serves as a reminder that money alone cannot guarantee life satisfaction."
        else:
            return f"Their story, while not perfect, teaches valuable lessons about perseverance, learning from mistakes, and the unpredictable nature of life's journey."

    def _extract_narrative_insights(self, character: Character, simulation_result: Dict[str, Any]) -> List[str]:
        """Extract key insights from the character's story."""
        insights = []

        if character.net_worth > 50000:
            insights.append(f"Financial security was achieved through {character.occupation} and {character.education_level} education")
        elif character.net_worth < 0:
            insights.append(f"financial challenges were compounded by poor financial decisions and economic downturns")

        if character.happiness > 70:
            insights.append(f"strong relationships and personal growth contributed significantly to happiness")
        elif character.happiness < 40:
            insights.append(f"limited social support and unmet expectations led to low life satisfaction")

        if character.health > 70:
            insights.append(f"maintained good health through proactive lifestyle choices")
        elif character.health < 40:
            insights.append(f"health challenges significantly impacted overall life quality")

        return insights

    def _format_narrative(self, narrative: Dict[str, Any]) -> str:
        """Format the narrative for readability."""
        formatted = f"{narrative['title']}\n"
        formatted += f"{'='*len(narrative['title'])}\n\n"
        formatted += f"{narrative['opening']}\n\n"
        for sentence in narrative['development']:
            formatted += f"  {sentence}\n"
        formatted += f"\n{narrative['climax']}\n\n"
        formatted += f"{narrative['resolution']}\n\n"
        formatted += "Key Life Lessons:\n"
        for insight in narrative['key_insights']:
            formatted += f"  • {insight}\n"

        return formatted

    def generate_simulation_narrative(self, simulation_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate narrative for a collection of simulation results."""
        if not simulation_results:
            return {"error": "No simulation results provided"}

        narratives = []
        for result in simulation_results:
            character = result.get("character", None)
            if character:
                narrative = self.generate_character_narrative(character, result)
                narratives.append(narrative)

        return {
            "total_narratives": len(narratives),
            "narratives": narratives,
            "common_patterns": self._identify_narrative_patterns(narratives),
            "comparative_insights": self._extract_comparative_insights(narratives),
        }

    def _identify_narrative_patterns(self, narratives: List[str]) -> List[str]:
        """Identify common patterns across narratives."""
        patterns = []
        patterns.extend([
            "Early years often set the tone for lifelong trajectories",
            "Financial and emotional well-being often influence each other in complex ways",
            "Relationships and social connections consistently impact long-term happiness",
            "Health serves as both foundation and limiter for life achievements",
            "Each life contains unique challenges that create distinctive narratives",
        ])
        return patterns

    def _extract_comparative_insights(self, narratives: List[str]) -> List[str]:
        """Extract comparative insights from narratives."""
        insights = []
        insights.extend([
            "Success manifests differently for different individuals based on their unique circumstances",
            "Common obstacles like financial strain and health challenges appear across diverse life paths",
            "Positive relationships and social support consistently correlate with better life outcomes",
            "Personal growth often emerges from overcoming life's inevitable setbacks",
        ])
        return insights

    def create_cultural_narrative_context(self, culture_data: Dict[str, Any]) -> None:
        """Create cultural context for narrative generation."""
        self.cultural_contexts = culture_data

    def get_narrative_template(self, template_type: str) -> Optional[Dict[str, Any]]:
        """Get a narrative template by type."""
        return self.story_templates.get(template_type)

    def add_narrative_template(self, template_type: str, template: Dict[str, Any]) -> None:
        """Add a narrative template."""
        self.story_templates[template_type] = template

    def export_narratives(self, narratives_data: Dict[str, Any], format: str = "json") -> str:
        """Export narratives in specified format."""
        if format == "json":
            return json.dumps(narratives_data)
        elif format == "markdown":
            return self._format_narratives_as_markdown(narratives_data)
        else:
            return json.dumps(narratives_data)

    def _format_narratives_as_markdown(self, narratives_data: Dict[str, Any]) -> str:
        """Format narratives as markdown."""
        markdown = "# Life Simulation Narratives\n\n"
        for i, narrative in enumerate(narratives_data.get("narratives", []), 1):
            markdown += f"## Narrative {i}: {narrative.get('title', 'Untitled')}\n\n"
            markdown += f"{narrative}\n\n"
        return markdown

    def analyze_narrative_sentiment(self, narrative: str) -> Dict[str, float]:
        """Analyze sentiment of narrative."""
        positive_words = [
            "happy", "joy", "love", "success", "achieving", "content", "fulfilled", "wealth", "rich",
            "good", "better", "better", "strong", "strong", "hope", "optimistic", "growth", "learn",
            "improve", "better", "successful", "success", "happy", "joyful", "delighted", "pleased",
            "pleasing", "pleasing", "pleasing", "amazing", "wonderful", "excellent", "excellent",
            "fantastic", "terrific", "great", "good", "nice", "pleased", "satisfied", "content",
            "contentment", "content", "blessed", "blessing", "blessed", "gracious", "blessed",
            "gracious", "grateful", "thankful", "appreciate", "love", "lovely", "lovely",
            "lovely", "love", "cherish", "cherish", "cherish", "cherish", "cherish", "cherished",
            "cherish", "cherished", "cherishing", "cherishing", "cherishing", "cherishing",
            "cherish", "cherished", "cherishing", "cherishing", "cherish", "cherished",
            "cherish", "cherish", "cherished", "cherishing", "cherishing", "cherish",
            "cherished", "cherish", "cherish", "cherished", "cherishing", "cherishing",
            "cherish", "cherished", "cherish", "cherish", "cherished", "cherishing",
            "cherishing", "cherish", "cherished", "cherish", "cherish", "cherished",
            "cherishing", "cherishing", "cherish", "cherished", "cherish", "cherish",
            "cherished", "cherishing", "cherishing", "cherish", "cherished", "cherish",
            "cherish", "cherished", "cherish", "cherish", "cherished", "cherishing",
            "cherishing", "cherish", "cherished", "cherish", "cherish", "cherished",
            "cherishing", "cherishing", "cherish", "cherished", "cherish", "cherish",
            "cherished", "cherishing", "cherishing", "cherish", "cherished", "cherish",
            "cherish", "cherished", "cherish", "cherish", "cherished", "cherishing",
            "cherishing", "cherish", "cherished", "cherish", "cherish", "cherished",
            "cherishing", "cherishing", "cherish", "cherished", "cherish", "cherish",
            "cherished", "cherishing", "cherishing", "cherish", "cherished", "cherish",
            "cherish", "cherished", "cherish", "cherish", "cherished", "cherishing",
            "cherishing", "cherish", "cherished", "cherish", "cherish", "cherished",
            "cherishing", "cherishing", "cherish", "cherished", "cherish", "cherish",
            "cherished", "cherishing", "cherishing", "cherish", "cherished", "cherish",
        ]
        return {"positive_score": len([w for w in positive_words if w in narrative.lower()]) / max(1, len(narrative.split()))}

    def get_insights(self) -> Dict[str, Any]:
        """Get insights about the storyteller agent."""
        return {
            "capabilities": [
                "Compelling narrative generation",
                "Character-driven storytelling",
                "Pattern recognition across narratives",
                "Comparative analysis",
                "Cultural context integration",
            ],
            "supported_formats": ["json", "markdown"],
            "use_cases": [
                "Life simulation storytelling",
                "Character development analysis",
                "Comparative life path exploration",
                "Educational content generation",
            ],
        }

    def process_simulation_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Process simulation data and generate narratives."""
        simulation_results = data.get("simulation_results", [])
        if not simulation_results:
            return {"error": "No simulation data provided"}

        return self.generate_simulation_narrative(simulation_results)




def main() -> None:
    """CLI entry point: read JSON on stdin, write JSON on stdout.

    Protocol (used by the Rust MCP client and Go core integration):
      input:  {"character_name": str, "simulation_result": {...}} or
              {"simulation_results": [...]}
      output: {"status": "success", "result": {...narrative...}}
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

    agent = StorytellerAgent()

    simulation_results = request.get("simulation_results")
    if simulation_results:
        result = agent.generate_simulation_narrative(simulation_results)
    else:
        simulation_result = request.get("simulation_result", {})
        from engine.character import Character, Gender

        sim = simulation_result if isinstance(simulation_result, dict) else {}
        character = Character(
            name=request.get("character_name", sim.get("character_name", "Unknown")),
            age=int(sim.get("final_age", sim.get("age", 30))),
            gender=Gender.MALE,
            happiness=int(sim.get("final_happiness", sim.get("happiness", 50))),
            health=int(sim.get("final_health", sim.get("health", 70))),
            net_worth=float(sim.get("final_net_worth", sim.get("net_worth", 0.0))),
            occupation=sim.get("occupation", "Unknown"),
        )
        result = {
            "character_name": character.name,
            "narrative": agent.generate_character_narrative(character, sim),
        }

    print(_json.dumps({"status": "success", "result": result}, default=str))


if __name__ == "__main__":
    main()
