# sims-suite

The commercial simulation stack of Alien Inc — seven independent companies that
form one continuous pipeline: **define → simulate → publish → attack → survive →
defend → respond**.

See [PLAN.md](./PLAN.md) for the full architecture and phased build.

## Quick start

```bash
cd /home/alieninc/sims-suite
pip install -r requirements.txt
python -m api.gateway          # starts on 127.0.0.1:8090
```

The gateway runs a light background loop of real Alpha Zero simulations and
exposes `/api/simulations/today` which `index.html` polls via a one-line shim.

## What's real right now (Phase 0)

- The **Alpha Zero** engine (`/home/alieninc/alphazero/alpha-zero-engine`) runs
  genuine Monte Carlo life-branch simulations in the background.
- `index.html` metric cards show live counts from those real runs.
- The shared `Scenario` contract (`engine/core/scenario.py`) is defined for all
  seven stations; only `alpha_zero` is populated yet.

## What's placeholder

Kriegspiel, Citadel, Remnants, and Intellectual Awareness have no engine yet —
they ship in Phases 1–3.
