"""Structured prompts for the LLM synthesis layer.

Each prompt asks the model to output strict JSON matching a schema the
validator can verify. We ask for the four output categories the Xi'an team
identified: geographic environment, force deployments, event logic, and
operational strategies.
"""

from __future__ import annotations

BATTLE_SEED_SYSTEM = (
    "You are a military scenario generator for a Monte Carlo battle simulator. "
    "You output STRICTLY valid JSON — no markdown, no prose, no commentary. "
    "The JSON must match the schema in the user prompt exactly."
)

BATTLE_SEED_PROMPT = """Generate one realistic modern military battle scenario as JSON.

Output schema (every field required unless marked optional):
{
  "battlefield": {
    "name": string,                       // real-world region name
    "center": [lat, lng],                 // lat in [-90, 90], lng in [-180, 180]
    "terrain": "open|urban|mountain|forest|desert|coastal|wetland",
    "area_km2": number,                   // 100 to 5_000_000
    "bounds": [west, south, east, north]  // lng,lat,lng,lat; must contain center
  },
  "objective": string,                    // one-sentence strategic objective
  "duration_hours": integer,              // 6 to 168
  "red_force": {
    "name": string,
    "doctrine": "attrition|maneuver|shock|defensive|guerrilla|logistical|information",
    "units": [
      {
        "unit_type": "infantry|armor|artillery|air|naval|logistics|recon|cyber",
        "strength": number,               // 0-100
        "morale": number,                 // 0-100
        "supply": number,                 // 0-100
        "speed_kmh": number,              // 5-100
        "engagement_range_km": number     // 1-50
      }
    ]
  },
  "blue_force": { /* same shape as red_force */ },
  "situational_events": [string, ...]     // 5-15 short event labels
}

Constraints:
  - Each force must have between 3 and 15 units.
  - Use realistic modern force compositions (mixed arms).
  - Situational events should be specific tactical turning points.
  - Bounds box must enclose the center point.

Return ONLY the JSON object."""


EVENTS_PROMPT = """You are augmenting a battle scenario with situational event labels.

Given the battle context below, generate {n} short (3-8 word) tactical event
labels that could occur during the engagement. Each event should be a specific
turning point or notable moment.

Battle context:
  Battlefield: {battlefield_name} ({terrain})
  Red doctrine: {red_doctrine}
  Blue doctrine: {blue_doctrine}
  Objective: {objective}

Output schema:
{{
  "events": ["event 1", "event 2", ...]
}}

Return ONLY the JSON object."""


def render_battle_seed_prompt() -> str:
    return BATTLE_SEED_PROMPT


def render_events_prompt(
    n: int,
    battlefield_name: str,
    terrain: str,
    red_doctrine: str,
    blue_doctrine: str,
    objective: str,
) -> str:
    return EVENTS_PROMPT.format(
        n=n,
        battlefield_name=battlefield_name,
        terrain=terrain,
        red_doctrine=red_doctrine,
        blue_doctrine=blue_doctrine,
        objective=objective or "secure strategic corridor",
    )
