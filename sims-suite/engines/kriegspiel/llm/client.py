"""Provider-agnostic LLM client interface.

One ABC, three concrete impls (DeepSeek API, local Ollama, OpenAI-compatible).
Selection is by env var ``KRIEGSPIEL_LLM_PROVIDER``. All HTTP is via stdlib
``urllib.request`` so air-gapped deployments stay air-gapped — no new deps.

Env:
    KRIEGSPIEL_LLM_PROVIDER  = deepseek | ollama | openai_compat | (unset)
    KRIEGSPIEL_LLM_API_KEY   = <key>            (deepseek, openai_compat)
    KRIEGSPIEL_LLM_BASE_URL  = http://localhost:11434   (ollama default)
    KRIEGSPIEL_LLM_MODEL     = deepseek-chat | qwen2.5:14b | gpt-4o-mini | ...
    KRIEGSPIEL_LLM_TIMEOUT_S = 60
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("kriegspiel.llm.client")


@dataclass
class LLMResponse:
    """One LLM completion result."""

    text: str
    provider: str
    model: str
    prompt_hash: str
    raw_response_hash: str
    latency_ms: float


class LLMClient(ABC):
    """Abstract LLM client — `complete(prompt) -> LLMResponse`."""

    provider: str = "abstract"
    model: str = "unknown"

    @abstractmethod
    def complete(self, prompt: str) -> LLMResponse:
        """Send `prompt`, return the completion plus provenance metadata."""
        raise NotImplementedError

    def is_ready(self) -> bool:
        """Whether this client is configured and callable."""
        return True


# ---------------------------------------------------------------------------
# Concrete implementations
# ---------------------------------------------------------------------------

class DeepSeekClient(LLMClient):
    """DeepSeek official API (chat completions, OpenAI-compatible schema)."""

    provider = "deepseek"
    base_url = "https://api.deepseek.com/v1/chat/completions"

    def __init__(self, api_key: str, model: str, timeout_s: int = 60):
        self.api_key = api_key
        self.model = model
        self.timeout_s = timeout_s

    def complete(self, prompt: str) -> LLMResponse:
        return _openai_compat_complete(
            url=self.base_url,
            api_key=self.api_key,
            model=self.model,
            prompt=prompt,
            provider=self.provider,
            timeout_s=self.timeout_s,
        )


class OpenAICompatClient(LLMClient):
    """Any OpenAI-compatible endpoint (vLLM, LM Studio, Together, Groq, ...)."""

    provider = "openai_compat"

    def __init__(self, base_url: str, api_key: str, model: str, timeout_s: int = 60):
        if not base_url.endswith("/chat/completions"):
            base_url = base_url.rstrip("/") + "/chat/completions"
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.timeout_s = timeout_s

    def complete(self, prompt: str) -> LLMResponse:
        return _openai_compat_complete(
            url=self.base_url,
            api_key=self.api_key,
            model=self.model,
            prompt=prompt,
            provider=self.provider,
            timeout_s=self.timeout_s,
        )


class OllamaClient(LLMClient):
    """Local Ollama daemon — air-gapped, no API key required."""

    provider = "ollama"

    def __init__(self, base_url: str, model: str, timeout_s: int = 60):
        if not base_url.endswith("/api/generate"):
            base_url = base_url.rstrip("/") + "/api/generate"
        self.base_url = base_url
        self.model = model
        self.timeout_s = timeout_s

    def complete(self, prompt: str) -> LLMResponse:
        import time
        import hashlib

        t0 = time.perf_counter()
        body = json.dumps({
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.7},
        }).encode("utf-8")
        req = urllib.request.Request(
            self.base_url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
            raw = resp.read().decode("utf-8")
        latency_ms = (time.perf_counter() - t0) * 1000
        try:
            data = json.loads(raw)
            text = data.get("response", "")
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Ollama returned non-JSON: {exc}") from exc
        return LLMResponse(
            text=text,
            provider=self.provider,
            model=self.model,
            prompt_hash=hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16],
            raw_response_hash=hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16],
            latency_ms=round(latency_ms, 1),
        )


# ---------------------------------------------------------------------------
# Shared OpenAI-compatible HTTP path (DeepSeek + OpenAICompat both use it)
# ---------------------------------------------------------------------------

def _openai_compat_complete(
    url: str,
    api_key: str,
    model: str,
    prompt: str,
    provider: str,
    timeout_s: int,
) -> LLMResponse:
    import time
    import hashlib

    t0 = time.perf_counter()
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system",
             "content": "You are a military scenario generator. "
                        "Output strictly valid JSON when asked."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
    }).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        raw = resp.read().decode("utf-8")
    latency_ms = (time.perf_counter() - t0) * 1000
    try:
        data = json.loads(raw)
        text = data["choices"][0]["message"]["content"]
    except (json.JSONDecodeError, KeyError, IndexError) as exc:
        raise RuntimeError(f"{provider} returned malformed response: {exc}") from exc
    return LLMResponse(
        text=text,
        provider=provider,
        model=model,
        prompt_hash=hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16],
        raw_response_hash=hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16],
        latency_ms=round(latency_ms, 1),
    )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_llm_client() -> Optional[LLMClient]:
    """Return a configured LLMClient, or None if no provider is set.

    This is the single entry point used by the synthesizer. If it returns
    None, the synthesizer falls back to the procedural seed — the pipeline
    never hard-fails on missing config.
    """
    provider = os.environ.get("KRIEGSPIEL_LLM_PROVIDER", "").strip().lower()
    if not provider:
        return None
    model = os.environ.get("KRIEGSPIEL_LLM_MODEL", "").strip()
    if not model:
        logger.warning("KRIEGSPIEL_LLM_PROVIDER set but KRIEGSPIEL_LLM_MODEL missing")
        return None
    timeout_s = int(os.environ.get("KRIEGSPIEL_LLM_TIMEOUT_S", "60"))

    try:
        if provider == "deepseek":
            key = os.environ.get("KRIEGSPIEL_LLM_API_KEY", "").strip()
            if not key:
                logger.warning("DeepSeek provider selected but API key missing")
                return None
            return DeepSeekClient(api_key=key, model=model, timeout_s=timeout_s)

        if provider == "ollama":
            base = os.environ.get("KRIEGSPIEL_LLM_BASE_URL",
                                  "http://localhost:11434").strip()
            return OllamaClient(base_url=base, model=model, timeout_s=timeout_s)

        if provider == "openai_compat":
            base = os.environ.get("KRIEGSPIEL_LLM_BASE_URL", "").strip()
            key = os.environ.get("KRIEGSPIEL_LLM_API_KEY", "").strip()
            if not base:
                logger.warning("openai_compat provider selected but base URL missing")
                return None
            return OpenAICompatClient(base_url=base, api_key=key,
                                      model=model, timeout_s=timeout_s)

        logger.warning("Unknown KRIEGSPIEL_LLM_PROVIDER=%r", provider)
        return None
    except Exception as exc:
        logger.warning("LLM client init failed: %s", exc)
        return None
