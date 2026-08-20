# Alien Inc Simulation Stack — `sims-suite/`

Seven independent companies, one continuous pipeline. This is the **commercial
simulation stack** of Alien Inc (not the internal tooling). Each station feeds
the next; Kriegspiel's scenario engine is the shared keystone that CC and
Remnants mirror.

```
Platoon ──objective──▶ Alpha Zero ──world-states──▶ Daily Art Cult (publish)
                            │
                            ▼
                       Kriegspiel ──10k scenarios──┐
                     (the keystone)                │
                     ┌──────┴──────┐               │
                     ▼             ▼               ▼
                Remnants       CC        Intellectual
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
| 6 | Defend       | Collective Consciousness | **Yes** ✓     | Yes (`/cc`) |
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
- **Phase 2** — CC + Remnants: two thin adapters over Kriegspiel.
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
   `enrich_with_llm=False` is the default. CC, Remnants, and the existing
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
- `engines.cc`, `engines.remnants` — adapters over `generate_scenarios`; the
  new flag defaults to `False`, so they keep working. They may opt in later by
  passing `enrich_with_llm=True` through their own thin shims.
- `engines.kriegspiel.combat.simulate_battle` — unchanged contract; richer
  `key_event` strings just flow through `BattleOutcome`.
- `api/gateway.py /api/kriegspiel/run` — unchanged. New endpoints added in a
  separate block. Existing background loop untouched.
- `requirements.txt` — no additions.

## Persona Population Layer (Phase 6 — MatrAIx-inspired refinement)

**Reference**: MatrAIx (arXiv 2608.04205) models human variation through a
1,290-dimension categorical schema and samples synthetic personas from a
*dependency DAG*: `p(x_i | x_Pa(i)) ∝ prior × adjustment × compatibility-mask`,
forward-sampled parent-first. Its validation protocol (controlled adherence
studies, Benjamini-Hochberg multiple-testing correction, cohort-vs-aggregate
subgroup analysis) is the discipline the whole stack now shares.

We adopt the *methodology*, not the 8.3B-scale infrastructure. A compact,
dependency-free adaptation now lives in the suite:

### New modules

```
sims_core/
  stats.py                    # stdlib-only stats: two_proportion_z, BH correction
  persona/
    schema.py                 # 25 correlated dimensions across 5 groups + priors,
                              #   adjustments, and compatibility masks
    sampler.py                # PersonaSampler: parent-first topological forward
                              #   sampling (deterministic per seed)
    models.py                 # Persona (values + NL descriptions -> readable profile),
                              #   PersonaCohortQuery (population filters)
    adherence.py              # run_controlled_study (MatrAIx 400-trial design),
                              #   re-exports the shared stats primitives
    bridges/alpha_zero.py     # persona -> engine.Character bridge + persona-cohort
                              #   life simulation runner (engine-optional)
engines/
  kriegspiel/
    adherence.py              # doctrine behavioral-signature probes (controlled
                              #   study vs a fixed reference force) + persona-risk
                              #   -> doctrine adherence bridge
    learning.py               # self_improve() now gates every parameter rewrite
                              #   behind a two-proportion z-test + Benjamini-Hochberg
                              #   FDR correction (audit trail via bh_gate_history)
  platoon/
    extraction.py             # Treiver-style objective extraction: offline regex
                              #   stage + optional provider-agnostic LLM judge with
                              #   validation + fallback
bridges/population_context.py # affected-population enrichment for Remnants/CC/
                              #   Awareness (readability + vulnerability profiles)
```

### Adherence probe — the risk/decisiveness finding (resolved)

The original probe used `decisive_rate` as the risk proxy and reported a
negative Spearman (-0.46). Investigation showed this was a **probe-design
artifact, not a doctrine flaw**: in this combat model (symmetric forces, 48-tick
grind) the `decisive` flag almost never fires, so `decisive_rate` was a
near-constant column and the correlation measured noise. The risk proxy is now
**casualty asymmetry** (how much the winning side pays to win) — a meaningful,
varying signal. With it, adherence reads 0.78–0.88 across all four attributes.

### Doctrine breakthrough mechanic + balance fix (shipped)

The adherence probe surfaced a **genuine doctrine balance bug**: Shock and
Maneuver won ~0% of engagements because high `aggression`/`risk` combined with
very low `supply_focus` / very high `morale_drain` made them self-destruct over
the 48-tick grind before aggression could pay off. Two changes fixed this:

1. **New `breakthrough` doctrine parameter** — a high-breakthrough attacker
   that holds a *local* unit superiority (more fighting units than the
   defender) can convert it into a decisive penetration and end the battle
   early, rather than grinding to stalemate. This makes Shock/Maneuver able to
   *win*, and makes the `decisive` flag meaningful. `BattleOutcome` now carries
   `breakthrough_by`.
2. **Evidence-based rebalance** — doctrine `supply_focus`/`morale_drain` are no
   longer so severe they guarantee defeat. Shock (still the most aggressive /
   risky / breakthrough) is now viable (win rate vs attrition ~0.39, up from
   ~0.0). The self-improve layer and the dashboard both understand the new
   `breakthrough` field.

### Combat engagement-rate rework — the root-cause fix (shipped 2026-08-19)

The rebalance helped but the deeper issue remained: **battlefields span
real-world theaters (thousands of km) but engagement ranges are tactical (km).**
`deploy_force` spread units across the whole theater, so opposing units started
~2000 km apart and never engaged — combat barely happened and per-tick
supply/morale attrition dominated every outcome (the 'supply_focus meta').

Three coordinated changes fixed the root cause:

1. **Tactical deployment** — `deploy_force` now places each side into a small
   engagement zone (~6 km) near the theater center, red west / blue east of the
   center line, so units actually make contact.
2. **Movement phase** — units advance toward the enemy each tick (terrain-speed
   modified), closing into engagement range over the battle.
3. **Higher engagement frequency** — a unit now engages multiple defenders in
   range per tick (capped at 3 for performance) instead of a single `break`.

Result: the combat model is now **aggression-coherent** — `aggression` predicts
win rate with Spearman ~1.0 (Shock 0.87 > Maneuver 0.63 > Attrition 0.36 >
others), decisive battles are common (~64% in a live run), and the supply_focus
meta is eliminated. The adherence probe's proxies were updated to match the new,
correct semantics (aggression → win_rate, risk → winner casualties inverted).
Adherence now reads 0.93.

### Deep population-vulnerability integration — engine-internal, all three stations

Beyond the post-hoc report modifiers, the affected population's profile is now
baked into **all three stress-station engines** (not just CC):

| Station | Engine-internal factor | Derived from | Effect (engine, not report) |
|---------|------------------------|--------------|------------------------------|
| CC | `digital_defense_quality` | digital fluency / trust / elderly | low-fluency pop → attack exploit chance rises → ~3.6× breach rate |
| Remnants | `population_resilience` | trust / income / age / urbanicity | fragile pop → survival score erodes → fewer survivors |
| Awareness | `population_reach` | digital fluency / urbanicity / trust | hard-to-reach pop → response actions land less → lower success |

Each factor is a 0.3–1.0 multiplier passed into the per-branch simulation
function (`simulate_attack`, `simulate_survival`, `simulate_response`), so the
vulnerability is a first-class input to the engine itself — not a post-hoc
gateway tweak. The gateway derives the factor from the sampled persona cohort
and records it under `population_modifiers`. Default 1.0 preserves existing
behavior (no regression). Verified live: vulnerable Remnants survival 0.0 (vs
0.55 baseline), hard-to-reach Awareness success 0.16 (vs ~0.4), low-fluency CC
breach 0.43.

### Population context (Remnants / CC / Awareness)

Remnants, CC, and Awareness accept an optional `persona_query` + `persona_n` on
their `/run` endpoints. When provided, a persona cohort is sampled and distilled
into an `affected_population` profile: distributions per schema group plus a
**readability index** and a **vulnerability index**.

**Population influences outcomes in the engine itself.** Each station derives a
0.3–1.0 factor from the cohort (see the table above) and passes it into the
per-branch simulation, so a vulnerable population genuinely changes the engine's
output — not just a report footnote. Each report carries the factor under
`population_modifiers`. (The earlier post-hoc `impact_modifiers` /
`apply_*_modifier` approach was fully superseded by this deeper integration and
removed.)

### Adherence probe — risk/aggression correlation transparency

The combat rework made `risk` and `aggression` correlated in effect (both scale
offensive success — Spearman ~0.96 on declared ordering, both ~0.93+ vs win
rate). There is no clean behavioral signal that separates them in this model
because they are designed to work together. The probe now reports
`parameter_correlations` (e.g. `aggression~risk: 0.96`) and a `note` so the
analyst knows the two adherence signals overlap and should be interpreted
together rather than as independent levers. Adherence reads 0.93–0.98.

### Research dashboard — Validation & rigor panel

The Kriegspiel research overlay (main index.html) now has a fourth panel that
polls `/api/research/bh-gate` and `/api/research/adherence` and renders the
multiple-testing gate (hypotheses tested vs survived) plus the per-attribute
adherence correlations — so the *validity* of the engine's learning is visible,
not just the outcomes.

### What each station gains

| Station | Refinement |
|---------|------------|
| Platoon | `extract_objective()` turns a client brief into a structured `Objective` |
| Alpha Zero | every universe is a *different person* (sampled cohort), not one archetype branched N times |
| Kriegspiel | parameter rewrites survive statistical significance; doctrine adherence measured, not assumed |
| Remnants / CC / Awareness | can sample a persona cohort and use it as their affected-population context |

### New endpoints

- `GET  /api/persona/schema` — schema overview (categories, dimensions, values)
- `POST /api/persona/sample` — sample one persona from the DAG (optional query)
- `POST /api/persona/cohort` — reproducible filtered cohort (N personas)
- `POST /api/persona/alpha-zero/run` — persona-cohort life simulation
- `GET  /api/research/adherence` — doctrine adherence probe (controlled study)
- `GET  /api/research/bh-gate` — multiple-testing audit trail for self-improvement
- `POST /api/platoon/extract` — Treiver-style objective extraction (LLM opt-in)

nginx: `/api/persona/` added to both sites-available and sites-enabled.

### Design rules (do NOT violate)

1. The persona core is **dependency-free** — stdlib only, air-gapped safe.
2. The Alpha Zero bridge is **engine-optional** — it returns `None` and degrades
   gracefully when the engine isn't importable; the rest of the stack never
   depends on it.
3. The LLM judge stage is **opt-in** and always falls back to the deterministic
   regex result on any provider/validation failure.
4. Every LLM/untrusted output carries a `provenance` record (`trusted=false` in
   CMB) — same discipline as the Kriegspiel LLM layer.
5. The compatibility mask is the *only* hard constraint; adjustments merely
   re-weight, so rare-but-valid profiles survive (MatrAIx Eq. 4).

### Test coverage (Phase 6 — 2026-08-19)

```
129 passed, 2 skipped — Phase 6 modules at 87% coverage

engines/kriegspiel/adherence.py     98%   (2 lines: unreachable defaults)
engines/kriegspiel/geography.py    100%
engines/kriegspiel/learning.py      92%   (27 lines: audit-trail detail formatting)
engines/platoon/extraction.py       87%   (20 lines: LLM stage-2 path)
sims_core/persona/adherence.py      98%   (1 line: unknown-attribute guard)
sims_core/persona/models.py         95%   (3 lines: edge-case defaults)
sims_core/persona/sampler.py        97%   (2 lines: parse_query edge cases)
sims_core/persona/schema.py         98%   (2 lines: edge-case validators)
```

Bugs fixed this session:
- `_HORIZON_RE` in extraction.py: `m.group(3)` was checking the "N-year" pattern
  instead of `m.group(4)` for "by YYYY" — year-based horizons returned `None`
  and crashed. Fixed to check group(4) for year, group(3) for "N-year" duration.
