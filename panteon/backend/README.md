# Panteon Backend

Enterprise Data & AI Operating System.

## Architecture

- **Spinal Craker** — Data platform (ontology engine, data integration, pipeline builder)
- **YONO** — AI platform (LLM orchestration, agent framework, automation)

## Quick Start

```bash
# Copy environment file
cp .env.example .env
# Edit .env with your API keys

# Start with Docker Compose
docker compose up -d

# API will be available at http://localhost:8000
# Docs at http://localhost:8000/docs
```

## Development

```bash
# Install dependencies
pip install -e ".[dev]"

# Run database
docker compose up postgres redis -d

# Run API
uvicorn panteon.main:app --reload
```

## API Endpoints

### Spinal Craker (Data Platform)

| Endpoint | Description |
|----------|-------------|
| `POST /api/v1/spinal-craker/object-types` | Create entity type |
| `GET /api/v1/spinal-craker/object-types` | List entity types |
| `POST /api/v1/spinal-craker/objects` | Create object instance |
| `GET /api/v1/spinal-craker/objects` | List objects |
| `PATCH /api/v1/spinal-craker/objects/{id}` | Update object |
| `DELETE /api/v1/spinal-craker/objects/{id}` | Delete object |
| `POST /api/v1/spinal-craker/link-types` | Create relationship type |
| `POST /api/v1/spinal-craker/links` | Create relationship |
| `POST /api/v1/spinal-craker/action-types` | Create action type |
| `POST /api/v1/spinal-craker/action-types/{id}/execute` | Execute action |

### YONO (AI Platform)

| Endpoint | Description |
|----------|-------------|
| `POST /api/v1/yono/providers` | Add LLM provider |
| `GET /api/v1/yono/providers` | List providers |
| `POST /api/v1/yono/models` | Add LLM model |
| `GET /api/v1/yono/models` | List models |
| `POST /api/v1/yono/execute` | Execute LLM call |
| `POST /api/v1/yono/agents` | Create AI agent |
| `POST /api/v1/yono/agents/chat` | Chat with agent |
| `POST /api/v1/yono/automations` | Create automation |
| `POST /api/v1/yono/automations/{id}/trigger` | Trigger automation |

## TDAC Integration

The Daily Art Cult is the founding tenant. See [TDAC_INTEGRATION.md](docs/TDAC_INTEGRATION.md) for full details.

### Quick Start

```bash
# Seed TDAC tenant
python scripts/seed_tdac.py

# Sync data from Supabase
curl -X POST http://localhost:8000/api/v1/tdac/sync/all \
  -H "Content-Type: application/json" \
  -d '{"supabase_url": "https://your-project.supabase.co", "supabase_key": "your-key"}'

# Check Resonance Index
curl http://localhost:8000/api/v1/tdac/resonance
```

### TDAC API Endpoints

| Endpoint | Description |
|----------|-------------|
| `POST /api/v1/tdac/sync/all` | Sync all data from Supabase |
| `GET /api/v1/tdac/resonance/{patron_id}` | Get patron Resonance Index |
| `GET /api/v1/tdac/resonance` | Get aggregate Resonance Index |
| `GET /api/v1/tdac/dashboard` | Get TDAC dashboard data |
| `POST /api/v1/webhooks/tdac/reflection-completed` | Webhook: reflection delivered |
| `POST /api/v1/webhooks/tdac/patron-updated` | Webhook: patron context updated |
| `POST /api/v1/webhooks/tdac/game-played` | Webhook: game played |
| `POST /api/v1/webhooks/tdac/giftcard-redeemed` | Webhook: gift card redeemed |

See `/impact/thedailyartcult.html` for the metric framework.
