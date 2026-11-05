"""High-level synthesizer — wires LLM output through the validator gate.

The two public functions are the only thing ``scenarios.py`` and the gateway
need to call:

    synthesize_battle_seed(seed) -> Battle
        Tries the LLM. If the LLM is unavailable OR its output fails
        validation, falls back to the procedural ``create_default_battle``.
        Every attempt (success or fallback) is logged to the audit JSONL.

    synthesize_events(battle, n) -> list[str]
        Asks the LLM for `n` situational events tailored to the battle.
        Falls back to the fixed ``_KEY_EVENTS`` pool if the LLM is unavailable
        or all proposed events fail validation.

All file IO is opt-in via ``KRIEGSPIEL_LLM_AUDIT_DIR``; if unset, audit logs
are skipped (useful in tests).
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import random
from pathlib import Path
from typing import Optional

from engines.kriegspiel.llm.client import LLMClient, LLMResponse, get_llm_client
from engines.kriegspiel.llm.prompts import (
    render_battle_seed_prompt,
    render_events_prompt,
)
from engines.kriegspiel.llm.validator import (
    parse_and_validate_battle,
    parse_events_response,
    validate_battle,
    validate_event,
)
from engines.kriegspiel.models import Battle
from engines.kriegspiel.scenarios import create_default_battle

logger = logging.getLogger("kriegspiel.llm.synthesizer")


# ---------------------------------------------------------------------------
# Audit log (JSONL) — one record per LLM call
# ---------------------------------------------------------------------------

def _audit_dir() -> Optional[Path]:
    p = os.environ.get("KRIEGSPIEL_LLM_AUDIT_DIR", "").strip()
    if not p:
        return None
    path = Path(p)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _audit_log(record: dict) -> None:
    path = _audit_dir()
    if path is None:
        return
    record["ts"] = _dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    fname = f"audit-{_dt.datetime.utcnow().strftime('%Y%m%d')}.jsonl"
    with (path / fname).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Battle seed synthesis
# ---------------------------------------------------------------------------

def synthesize_battle_seed(
    seed: Optional[int] = None,
    client: Optional[LLMClient] = None,
) -> Battle:
    """Return a validated Battle seed.

    Tries the LLM; on any failure (no client, HTTP error, JSON parse error,
    validation rejection) falls back to ``create_default_battle(seed)``.

    The returned Battle always has a ``provenance`` dict on it. If the LLM
    produced it, provenance records the provider/model/prompt_hash/etc. If
    the procedural fallback produced it, provenance records that too.
    """
    if client is None:
        client = get_llm_client()

    if client is None:
        battle = create_default_battle(seed=seed)
        _set_provenance(battle, source="procedural",
                        reason="no LLM client configured")
        return battle

    prompt = render_battle_seed_prompt()
    try:
        resp = client.complete(prompt)
    except Exception as exc:
        logger.warning("LLM complete() failed: %s", exc)
        _audit_log({"op": "battle_seed", "status": "http_error",
                    "provider": client.provider, "model": client.model,
                    "error": str(exc)})
        battle = create_default_battle(seed=seed)
        _set_provenance(battle, source="procedural",
                        reason=f"LLM HTTP error: {exc}",
                        attempted_provider=client.provider)
        return battle

    # Try to extract JSON from the response (LLMs sometimes wrap in ```json)
    text = _strip_json_fence(resp.text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.warning("LLM returned non-JSON: %s", exc)
        _audit_log({"op": "battle_seed", "status": "json_parse_error",
                    "provider": resp.provider, "model": resp.model,
                    "prompt_hash": resp.prompt_hash,
                    "raw_response_hash": resp.raw_response_hash,
                    "error": str(exc),
                    "latency_ms": resp.latency_ms})
        battle = create_default_battle(seed=seed)
        _set_provenance(battle, source="procedural",
                        reason=f"LLM JSON parse error: {exc}",
                        attempted_provider=resp.provider,
                        attempted_model=resp.model)
        return battle

    result = parse_and_validate_battle(data)
    if not result.ok or result.battle is None:
        logger.warning("LLM battle failed validation: %s", result.reasons)
        _audit_log({"op": "battle_seed", "status": "validation_failed",
                    "provider": resp.provider, "model": resp.model,
                    "prompt_hash": resp.prompt_hash,
                    "raw_response_hash": resp.raw_response_hash,
                    "reasons": result.reasons,
                    "latency_ms": resp.latency_ms})
        battle = create_default_battle(seed=seed)
        _set_provenance(battle, source="procedural",
                        reason=f"LLM validation failed: {result.reasons}",
                        attempted_provider=resp.provider,
                        attempted_model=resp.model)
        return battle

    # Defense in depth — re-validate the constructed Battle object.
    ok, reasons = validate_battle(result.battle)
    if not ok:
        logger.warning("Constructed Battle failed re-validation: %s", reasons)
        _audit_log({"op": "battle_seed", "status": "post_build_validation_failed",
                    "provider": resp.provider, "model": resp.model,
                    "reasons": reasons, "latency_ms": resp.latency_ms})
        battle = create_default_battle(seed=seed)
        _set_provenance(battle, source="procedural",
                        reason=f"post-build validation failed: {reasons}",
                        attempted_provider=resp.provider,
                        attempted_model=resp.model)
        return battle

    # Deploy forces geographically (the LLM doesn't position units).
    from engines.kriegspiel.geography import deploy_force
    deploy_force(result.battle.red_force, result.battle.battlefield, "red", seed)
    deploy_force(result.battle.blue_force, result.battle.battlefield, "blue",
                 seed + 1 if seed else None)
    result.battle.seed = seed

    # Register any situational events the LLM proposed.
    events = data.get("situational_events", [])
    if isinstance(events, list):
        good_events: list[str] = []
        for e in events:
            if isinstance(e, str):
                ok, _ = validate_event(e)
                if ok:
                    good_events.append(e)
        if good_events:
            from engines.kriegspiel.combat import register_events
            register_events(good_events)

    _set_provenance(result.battle, source="llm",
                    provider=resp.provider, model=resp.model,
                    prompt_hash=resp.prompt_hash,
                    raw_response_hash=resp.raw_response_hash,
                    latency_ms=resp.latency_ms,
                    validated=True)
    _audit_log({"op": "battle_seed", "status": "ok",
                "provider": resp.provider, "model": resp.model,
                "prompt_hash": resp.prompt_hash,
                "raw_response_hash": resp.raw_response_hash,
                "battlefield": result.battle.battlefield.name,
                "red_doctrine": result.battle.red_force.doctrine.value,
                "blue_doctrine": result.battle.blue_force.doctrine.value,
                "n_events_registered": len(good_events) if isinstance(events, list) else 0,
                "latency_ms": resp.latency_ms})
    return result.battle


# ---------------------------------------------------------------------------
# Event synthesis
# ---------------------------------------------------------------------------

def synthesize_events(
    battle: Battle,
    n: int = 12,
    client: Optional[LLMClient] = None,
) -> list[str]:
    """Ask the LLM for `n` situational events tailored to the battle.

    Falls back to the fixed ``_KEY_EVENTS`` pool if the LLM is unavailable
    or every proposed event fails validation. Successfully validated events
    are also registered with the combat engine via ``register_events``.
    """
    if client is None:
        client = get_llm_client()

    if client is None:
        from engines.kriegspiel.combat import get_event_pool
        pool = get_event_pool()
        rng = random.Random(battle.seed or 42)
        return rng.sample(pool, min(n, len(pool)))

    prompt = render_events_prompt(
        n=n,
        battlefield_name=battle.battlefield.name,
        terrain=battle.battlefield.terrain.value,
        red_doctrine=battle.red_force.doctrine.value,
        blue_doctrine=battle.blue_force.doctrine.value,
        objective=battle.objective,
    )
    try:
        resp = client.complete(prompt)
    except Exception as exc:
        logger.warning("LLM events complete() failed: %s", exc)
        _audit_log({"op": "events", "status": "http_error",
                    "provider": client.provider, "error": str(exc)})
        from engines.kriegspiel.combat import get_event_pool
        return random.Random(battle.seed or 42).sample(
            get_event_pool(), min(n, len(get_event_pool())))

    events, errors = parse_events_response(_strip_json_fence(resp.text))
    if errors:
        _audit_log({"op": "events", "status": "partial_validation",
                    "provider": resp.provider, "model": resp.model,
                    "errors": errors, "latency_ms": resp.latency_ms})
    else:
        _audit_log({"op": "events", "status": "ok",
                    "provider": resp.provider, "model": resp.model,
                    "n_events": len(events), "latency_ms": resp.latency_ms})

    if not events:
        from engines.kriegspiel.combat import get_event_pool
        return random.Random(battle.seed or 42).sample(
            get_event_pool(), min(n, len(get_event_pool())))

    from engines.kriegspiel.combat import register_events
    register_events(events)
    return events


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_json_fence(text: str) -> str:
    """Strip ```json ... ``` fences if the LLM wrapped its output."""
    s = text.strip()
    if s.startswith("```"):
        # remove first fence line
        s = s.split("\n", 1)[1] if "\n" in s else s
        if s.endswith("```"):
            s = s.rsplit("```", 1)[0]
    return s.strip()


def _set_provenance(battle: Battle, **kwargs) -> None:
    """Attach a provenance dict to the battle."""
    battle.provenance = dict(kwargs)
