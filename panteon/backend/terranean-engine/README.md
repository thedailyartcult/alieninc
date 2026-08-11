# Terranean Engine

Dual-mode intelligence service combining **Etiology** (causal reconstruction) and **Teleology** (purpose & trajectory modeling).

## What It Does

- **Etiology**: Ingests events, builds causal graphs (NetworkX), finds root causes, runs counterfactual analysis
- **Teleology**: Infers actor purposes from behavior patterns, projects future trajectories, identifies leverage points

## Install & Run (Debian)

```bash
cd /home/tablet/alieninc/panteon/backend/terranean-engine

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

uvicorn main:app --reload --port 8100
```

API docs at `http://localhost:8100/docs`

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/ingest` | Feed events into the engine |
| POST | `/reconstruct` | Build causal graph from ingested events |
| GET | `/graph` | Return current causal graph (nodes + edges) |
| POST | `/root-cause` | Find ranked root causes for a target event |
| POST | `/counterfactual` | Simulate removing/intervening on events |
| POST | `/infer-purposes` | Infer purpose objects from actor behavior |
| GET | `/purposes` | Return all inferred purposes |
| POST | `/project-trajectory` | Project future states from purposes |
| POST | `/leverage-points` | Find high-impact intervention points |
| GET | `/health` | Service health check |
| POST | `/reset` | Clear all in-memory state |

## Example curl Commands

### Ingest events
```bash
curl -X POST http://localhost:8100/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "events": [
      {"id": "e1", "timestamp": "2026-01-01T10:00:00", "actor": "alpha", "action": "deploy", "target": "system-a"},
      {"id": "e2", "timestamp": "2026-01-01T10:05:00", "actor": "alpha", "action": "configure", "target": "system-a"},
      {"id": "e3", "timestamp": "2026-01-01T10:10:00", "actor": "system-a", "action": "fail", "target": null, "goal_hint": null},
      {"id": "e4", "timestamp": "2026-01-01T10:15:00", "actor": "beta", "action": "investigate", "target": "system-a"},
      {"id": "e5", "timestamp": "2026-01-01T10:20:00", "actor": "beta", "action": "patch", "target": "system-a", "goal_hint": "restore_service"}
    ]
  }'
```

### Reconstruct causal graph
```bash
curl -X POST http://localhost:8100/reconstruct \
  -H "Content-Type: application/json" \
  -d '{"scope": null}'
```

### Get graph
```bash
curl http://localhost:8100/graph
```

### Find root causes
```bash
curl -X POST http://localhost:8100/root-cause \
  -H "Content-Type: application/json" \
  -d '{"target_id": "e3", "depth": 10}'
```

### Counterfactual analysis
```bash
curl -X POST http://localhost:8100/counterfactual \
  -H "Content-Type: application/json" \
  -d '{"event_ids": ["e1"], "intervention": "remove"}'
```

### Infer purposes
```bash
curl -X POST http://localhost:8100/infer-purposes \
  -H "Content-Type: application/json" \
  -d '{"actor_scope": null}'
```

### Get purposes
```bash
curl http://localhost:8100/purposes
```

### Project trajectory
```bash
curl -X POST http://localhost:8100/project-trajectory \
  -H "Content-Type: application/json" \
  -d '{"purpose_ids": null, "horizon": 5}'
```

### Find leverage points
```bash
curl -X POST http://localhost:8100/leverage-points \
  -H "Content-Type: application/json" \
  -d '{"trajectory_id": null, "objective": "disrupt_failure_chain"}'
```

### Health check
```bash
curl http://localhost:8100/health
```

### Reset state
```bash
curl -X POST http://localhost:8100/reset
```

## Integration from dashboard.html

```javascript
const ENGINE = 'http://localhost:8100';

async function ingestEvents(events) {
  const res = await fetch(`${ENGINE}/ingest`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ events })
  });
  return res.json();
}

async function reconstruct() {
  const res = await fetch(`${ENGINE}/reconstruct`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ scope: null })
  });
  return res.json();
}

async function getGraph() {
  const res = await fetch(`${ENGINE}/graph`);
  return res.json();
}

async function findRootCause(targetId) {
  const res = await fetch(`${ENGINE}/root-cause`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ target_id: targetId, depth: 10 })
  });
  return res.json();
}

async function counterfactual(eventIds) {
  const res = await fetch(`${ENGINE}/counterfactual`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ event_ids: eventIds, intervention: 'remove' })
  });
  return res.json();
}

async function inferPurposes() {
  const res = await fetch(`${ENGINE}/infer-purposes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ actor_scope: null })
  });
  return res.json();
}

async function projectTrajectory(horizon = 10) {
  const res = await fetch(`${ENGINE}/project-trajectory`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ purpose_ids: null, horizon })
  });
  return res.json();
}

async function leveragePoints(objective) {
  const res = await fetch(`${ENGINE}/leverage-points`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ trajectory_id: null, objective })
  });
  return res.json();
}
```

## Typical Workflow

```
1. POST /ingest          — feed your events
2. POST /reconstruct     — build the causal graph
3. POST /root-cause      — find what caused a specific event
4. POST /counterfactual  — what if we remove an event?
5. POST /infer-purposes  — what are actors trying to achieve?
6. POST /project-trajectory — where is this heading?
7. POST /leverage-points — where should we intervene?
```
