# TDAC-Panteon Integration

The Daily Art Cult is the founding tenant of Panteon. This integration bridges TDAC's existing Supabase backend with Panteon's Spinal Craker ontology and YONO AI platform.

## Architecture

```
┌─────────────────┐         ┌──────────────────┐         ┌─────────────────┐
│   TDAC Website  │         │   Panteon API    │         │   Supabase DB   │
│  (thedailyart   │◄───────►│  (Spinal Craker  │◄───────►│  (TDAC Backend) │
│   cult.lol)     │ webhooks│   + YONO)         │  sync   │                 │
└─────────────────┘         └──────────────────┘         └─────────────────┘
```

## Components

### 1. Supabase Sync
Pulls TDAC data into Panteon's ontology:
- **Patrons** → `tdac_patron` entity type
- **Reflections** → `tdac_reflection` entity type
- **Publishers** → `tdac_publisher` entity type

```bash
POST /api/v1/tdac/sync/all
{
  "supabase_url": "https://your-project.supabase.co",
  "supabase_key": "your-anon-key"
}
```

### 2. Resonance Index
Composite metric measuring patron engagement depth:

```
Resonance = (R1 × 0.25) + (R2 × 0.25) + (R3 × 0.20) + (R4 × 0.15) + (R5 × 0.15)
```

- **R1 Return Rate**: % listening >50% of reflections
- **R2 Depth Score**: Context profile updates
- **R3 Discovery Rate**: Publishers explored
- **R4 Ritual Score**: Listening streaks
- **R5 Gift Score**: Gift cards redeemed

```bash
GET /api/v1/tdac/resonance/{patron_id}
GET /api/v1/tdac/resonance  # aggregate
```

### 3. Webhooks
TDAC reports real-time events to Panteon:

| Event | Endpoint |
|-------|----------|
| Reflection completed | `POST /api/v1/webhooks/tdac/reflection-completed` |
| Patron updated | `POST /api/v1/webhooks/tdac/patron-updated` |
| Game played | `POST /api/v1/webhooks/tdac/game-played` |
| Gift card redeemed | `POST /api/v1/webhooks/tdac/giftcard-redeemed` |

### 4. Daily Reflection Automation
YONO-powered pipeline for generating daily reflections:

1. **YONO Logic** → Compose reflection (Gemini)
2. **YONO Voice** → Synthesize audio (Azure TTS)
3. **Webhook** → Deliver to TDAC patron library

```python
from panteon.integrations.tdac_automation import TDACDailyReflectionAutomation

automation = TDACDailyReflectionAutomation(db)
result = await automation.execute_for_patron(
    patron_id="patron-123",
    patron_name="Marcus",
    philosophical_context="Stoic philosopher interested in impermanence",
    publisher_worldview="Stoicism",
    topic="endurance",
    gemini_api_key="...",
    azure_speech_key="...",
    azure_speech_region="eastus",
)
```

## Setup

```bash
# Seed TDAC tenant
python scripts/seed_tdac.py

# Sync data from Supabase
curl -X POST http://localhost:8000/api/v1/tdac/sync/all \
  -H "Content-Type: application/json" \
  -d '{"supabase_url": "...", "supabase_key": "..."}'

# Check resonance
curl http://localhost:8000/api/v1/tdac/resonance
```

## TDAC Dashboard

```bash
GET /api/v1/tdac/dashboard
```

Returns:
- Average Resonance Index
- Recent activity feed
- Patron engagement metrics

See `/impact/thedailyartcult.html` for the full metric framework.
