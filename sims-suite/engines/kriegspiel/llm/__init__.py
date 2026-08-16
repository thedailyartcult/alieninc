"""Kriegspiel LLM synthesis layer — provider-agnostic scenario generator.

Mirrors the capability described by Fu Yanfang's Xi'an Technological University
team (DeepSeek-driven battle-scenario synthesis): the LLM directly produces
geographic environments, force deployments, event logic, and operational
strategies. We mirror the *capability*, not the speed target — verifiability
wins over latency for a defense contractor.

Public surface:
    get_llm_client()       -> LLMClient | None   (None if not configured)
    synthesize_battle_seed(seed) -> Battle        (validated or fallback)
    synthesize_events(battle, n) -> list[str]
    register_events(events)                      (extends combat event pool)
    validate_battle(battle) -> (ok, reasons)

Design:
    - Provider-agnostic via LLMClient ABC; concrete impls for DeepSeek, Ollama,
      and any OpenAI-compatible endpoint. Selected by env vars.
    - No new runtime deps (stdlib urllib.request only).
    - Validator gate: JSON schema + domain sanity checks. Rejected LLM output
      falls back to the procedural seed — pipeline never hard-fails.
    - Every LLM-synthesized Battle carries a `provenance` dict.
"""

from engines.kriegspiel.llm.client import (
    LLMClient,
    LLMResponse,
    DeepSeekClient,
    OllamaClient,
    OpenAICompatClient,
    get_llm_client,
)
from engines.kriegspiel.llm.synthesizer import (
    synthesize_battle_seed,
    synthesize_events,
)
from engines.kriegspiel.llm.validator import (
    validate_battle,
    validate_event,
    ValidationError,
)

__all__ = [
    "LLMClient",
    "LLMResponse",
    "DeepSeekClient",
    "OllamaClient",
    "OpenAICompatClient",
    "get_llm_client",
    "synthesize_battle_seed",
    "synthesize_events",
    "validate_battle",
    "validate_event",
    "ValidationError",
]
