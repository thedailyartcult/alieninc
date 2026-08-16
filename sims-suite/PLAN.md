# Alien Inc Simulation Stack — `sims-suite/`

Seven independent companies, one continuous pipeline. This is the **commercial
simulation stack** of Alien Inc (not the internal tooling). Each station feeds
the next; Kriegspiel's scenario engine is the shared keystone that Citadel and
Remnants mirror.

```
Platoon ──objective──▶ Alpha Zero ──world-states──▶ Daily Art Cult (publish)
                            │
                            ▼
                       Kriegspiel ──10k scenarios──┐
                     (the keystone)                │
                     ┌──────┴──────┐               │
                     ▼             ▼               ▼
                Remnants       Citadel        Intellectual
              (outward:       (inward:         Awareness
               survives)       your walls)     (respond)
```

## Status

| # | Station      | Product               | Engine built? | Front-end built? |
|---|-------------|-----------------------|---------------|------------------|
| 1 | Define       | Platoon               | **Yes** ✓     | Yes (`/platoon-sim`) |
| 2 | Simulate     | Alpha Zero            | **Yes** ✓     | Yes (`/alphazero`) |
| 3 | Publish      | The Daily Art Cult    | **Yes** ✓     | Yes (`/tdac-sim`) |
| 4 | Survive      | Remnants              | **Yes** ✓     | Yes (`/remnants`) |
| 5 | Respond      | Intellectual Awareness| **Yes** ✓     | Yes (`/awareness`) |
| 6 | Defend       | Citadel               | **Yes** ✓     | Yes (`/citadel`) |
| 7 | Attack       | Kriegspiel            | **Yes** ✓     | Yes (`/kriegspiel`) |

**All 7 engines online. Coverage: Full-spectrum. Pipeline complete.**

## The `index.html` integration point

`/home/alieninc/index.html` already has a designed, documented hook (line ~3699):

```js
// To drive the counter from a real source, define before this script runs:
//   window.ALIEN_SIMS = { getValue: function () { return <number>; } };
```

The gateway (`api/gateway.py`) exposes `/api/simulations/today`. A ~15-line shim
in `index.html` defines `window.ALIEN_SIMS.getValue()` to poll it, replacing the
fake counter with real, live-growing numbers. The four metric cards
(`metricRevenue`, `metricExternal`, etc.) and the per-company revenue hooks
(`data-ecosystem="company-<name>-revenue"`) are all filled from the same poll.

## Design languages (codified — do NOT change)

Three skins live in `design/tokens.css`. New dashboards pick one by importing
the tokens and adding a skin class (`skin-platoon`, `skin-alphazero`,
`skin-tdac`).

| Skin        | Tokens          | Vibe                                    |
|-------------|-----------------|-----------------------------------------|
| Platoon     | `--platoon-*`   | Montserrat, purple `#25076B→#46178F`, yellow `#ffd400`, playful |
| Alpha Zero  | `--alphazero-*` | Google Sans Flex, white `#fff`, pill `#f1f3f4`, clean Google-product |
| Daily Art Cult | `--tdac-*`    | Cormorant/Playfair, dark `#070504`, slow-luxury editorial |

## File layout

```
sims-suite/
  design/
    tokens.css            # 3 skin token sets + --sims-* neutral
  engine/
    core/                 # shared Monte Carlo, branching, Scenario contract
      scenario.py         # the Scenario dataclass every station uses
      monte_carlo.py      # branching primitive (lifted from Alpha Zero)
  engines/                # one dir per station (built in later phases)
  bridges/                # cross-station bridges (narrative, etc.)
  api/
    gateway.py            # FastAPI: /api/simulations/* (feeds index.html)
  sites/                  # front-ends for unbuilt stations
  PLAN.md                 # this file
  README.md
  requirements.txt
```

## Phases

- **Phase 0** — Foundation: tokens, shared core, gateway, `index.html` shim.
  Real numbers flow to the site immediately from the existing Alpha Zero engine.
- **Phase 1** — Kriegspiel: combat scenario generator (the keystone).
- **Phase 2** — Citadel + Remnants: two thin adapters over Kriegspiel.
- **Phase 3** — Intellectual Awareness: SOAR/IR layer (reuses GDELT from Spinal Craker).
- **Phase 4** — Close the loop: Platoon objective-capture + Daily Art Cult narrative bridge.
- **Phase 5** — LLM-driven scenario synthesis layer (mirrors Xi'an Technological Univ. /
  Fu Yanfang team's DeepSeek approach, provider-agnostic). See "LLM Synthesis Layer"
  below.

## LLM Synthesis Layer (Phase 5)

**Reference**: Xi'an Technological University team (Fu Yanfang) used DeepSeek LLM to
generate 10,000 military scenarios in 48 seconds, where the AI directly produces
geographic environments, force deployments, event logic, and operational strategies.
We mirror the *capability* (AI-generated scenario seeds), not the speed target —
verifiability wins over latency for a defense contractor.

### Goal

Add an LLM-driven scenario synthesizer as an **opt-in layer** on top of Kriegspiel.
The existing procedural engine stays as the air-gapped fallback. When LLM enrichment
is enabled, the LLM proposes; a deterministic validator disposes; only validated
battles enter the Monte Carlo pool. Every LLM-synthesized battle carries a
`provenance` record (provider, model, prompt hash, validation status).

### Design principles

1. **Provider-agnostic**: a single `LLMClient` interface; concrete impls for
   DeepSeek API, local Ollama, and any OpenAI-compatible endpoint. Selected via env.
2. **Backward compatible**: `generate_scenarios(...)` keeps its current signature;
   `enrich_with_llm=False` is the default. Citadel, Remnants, and the existing
   `/api/kriegspiel/run` endpoint keep working unchanged.
3. **No new runtime deps**: LLM HTTP calls use stdlib `urllib.request`. Air-gapped
   deployments stay air-gapped. If no provider is configured, the LLM layer is a
   no-op and the procedural engine answers every call.
4. **Verification gate** (this is what the contractor learns from):
   - JSON schema validation (parse-or-reject)
   - Domain sanity checks: lat/lng within ±90/±180, force size 3–15 units,
     doctrine/terrain/unit_type must be valid enum values, strengths/morale/supply
     in 0–100, bounds box must contain the center
   - Every rejection is logged with a reason; failed synthesis falls back to
     procedural seed so the pipeline never hard-fails on LLM noise
5. **Provenance + audit**: every LLM-synthesized battle gets
   `battle.provenance = {source: "llm", provider, model, prompt_hash,
   validated_at, raw_response_hash}`. Stored in CMB with `trusted=false` per
   untrusted-content policy. Rejected outputs are kept in a JSONL audit log under
   `engines/kriegspiel/llm/audit/`.

### File layout (additions)

```
engines/kriegspiel/
  llm/
    __init__.py          # public surface: get_llm_client, synthesize_battle_seed
    client.py            # LLMClient ABC + DeepSeekClient/OllamaClient/OpenAICompatClient
    prompts.py           # structured prompts for battlefield/force/event/strategy
    synthesizer.py       # synthesize_battle_seed(), synthesize_events()
    validator.py         # validate_battle(), validate_event(), rejection reasons
    audit/               # JSONL audit log of every LLM call (gitignored)
  models.py              # +Battle.provenance, +BATTLEFIELDS_LLM (mutable pool)
  combat.py              # _KEY_EVENTS → EVENTS_POOL + register_events()
  scenarios.py           # +enrich_with_llm flag on create_default_battle & generate_scenarios
api/
  gateway.py             # +/api/kriegspiel/llm/{status,seed,run,events}
sites/kriegspiel/
  index.html             # +LLM-mode toggle, provenance panel, validation-failures view
tests/
  test_llm_validator.py
  test_llm_synthesizer_fallback.py
  test_kriegspiel_no_regression.py
```

### Env config

```
KRIEGSPIEL_LLM_PROVIDER     = deepseek | ollama | openai_compat | (unset)
KRIEGSPIEL_LLM_API_KEY      = <key>           # deepseek, openai_compat
KRIEGSPIEL_LLM_BASE_URL     = http://localhost:11434  # ollama default
KRIEGSPIEL_LLM_MODEL        = deepseek-chat | qwen2.5:14b | gpt-4o-mini | ...
KRIEGSPIEL_LLM_TIMEOUT_S    = 60
KRIEGSPIEL_LLM_AUDIT_DIR    = engines/kriegspiel/llm/audit
```

### Phases

- **5a** — LLM client interface + DeepSeek/Ollama/OpenAI-compat impls + validator
  (no engine integration yet, fully unit-testable).
- **5b** — Synthesizer wires LLM output → validated `Battle`. `enrich_with_llm`
  flag on `create_default_battle` / `generate_scenarios`.
- **5c** — Gateway endpoints (`/api/kriegspiel/llm/*`) + dashboard toggle.
- **5d** — Audit log + CMB provenance storage with `trusted=false`.

### Dependency impact (verified safe)

- `sims_core.monte_carlo` — untouched (LLM layer sits above it, not inside).
- `engines.citadel`, `engines.remnants` — adapters over `generate_scenarios`; the
  new flag defaults to `False`, so they keep working. They may opt in later by
  passing `enrich_with_llm=True` through their own thin shims.
- `engines.kriegspiel.combat.simulate_battle` — unchanged contract; richer
  `key_event` strings just flow through `BattleOutcome`.
- `api/gateway.py /api/kriegspiel/run` — unchanged. New endpoints added in a
  separate block. Existing background loop untouched.
- `requirements.txt` — no additions.
