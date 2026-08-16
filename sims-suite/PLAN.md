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
