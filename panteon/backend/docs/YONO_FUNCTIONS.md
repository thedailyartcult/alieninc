# YONO Functions — Spinal Craker → YONO Bridge

External-facing API that receives authenticated calls from Spinal Craker ontology
actions and executes AI agent tasks via YONO (the AI platform).

## Architecture

```
Spinal Craker Ontology Action
        │
        │  POST /api/v1/yono/functions/execute
        │  HMAC-signed request body
        ▼
YONO Function Endpoint (this service)
        │
        ├── HMAC verification (shared secret)
        ├── Per-principal rate limiting (20 req/hr)
        ├── Audit logging (JSONL)
        │
        ▼
  ┌─────────────┐     ┌──────────────┐
  │  Subprocess  │ or  │  Native YONO  │
  │  (opencode)  │     │  LLM Orch.    │
  └─────────────┘     └──────────────┘
```

**Key principle:** Spinal Craker Ontology enforces all permissioning upstream.
By the time a request reaches this endpoint, it has already been scoped to
only the data the calling principal is allowed to see. This service does NOT
re-implement permission checks.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ONO_FUNCTION_SHARED_SECRET` | *(required)* | HMAC shared secret with Spinal Craker |
| `ONO_FUNCTION_EXEC_MODE` | `subprocess` | `subprocess` (opencode CLI) or `native` (YONO orchestrator) |
| `ONO_FUNCTION_EXECUTABLE` | `opencode` | Path to CLI executable (subprocess mode) |
| `ONO_FUNCTION_MODEL` | *(empty)* | Model name passed to executable |
| `ONO_FUNCTION_TIMEOUT` | `120` | Max execution timeout in seconds (capped at 300) |
| `ONO_FUNCTION_RATE_LIMIT` | `20` | Max requests per principal per hour |
| `ONO_FUNCTION_AUDIT_DIR` | `audit-logs` | Directory for JSONL audit log files |

## API Endpoints

### POST /api/v1/yono/functions/execute

Execute an AI task with pre-scoped context from Spinal Craker.

**Authentication:** HMAC signature via `X-YONO-Signature` and `X-YONO-Timestamp` headers.

**Request body:**
```json
{
  "task_prompt": "Summarize the threat assessment for region X",
  "scoped_context": {"entities": [...], "region": "X"},
  "principal_id": "analyst-42",
  "request_id": "req-abc-123"
}
```

**Response (success):**
```json
{
  "request_id": "req-abc-123",
  "output": "The threat assessment for region X...",
  "status": "success",
  "execution_time_ms": 3420,
  "model": "gpt-4o"
}
```

**Response (error):**
```json
{
  "request_id": "req-abc-123",
  "status": "error",
  "error": "Execution timed out after 120s",
  "execution_time_ms": 120000
}
```

### GET /api/v1/yono/functions/health

Health check (no auth required).

## Testing with Signed curl

```bash
#!/bin/bash
SECRET="your-shared-secret"
TIMESTAMP=$(date +%s)
BODY='{"task_prompt":"Hello","principal_id":"test","request_id":"req-001","scoped_context":"test context"}'

SIGNATURE=$(echo -n "${TIMESTAMP}.${BODY}" | openssl dgst -sha256 -hmac "$SECRET" | awk '{print $2}')

curl -X POST http://localhost:8000/api/v1/yono/functions/execute \
  -H "Content-Type: application/json" \
  -H "X-YONO-Signature: ${SIGNATURE}" \
  -H "X-YONO-Timestamp: ${TIMESTAMP}" \
  -d "${BODY}"
```

## Viewing the Audit Log

```bash
# Tail the audit log
tail -f panteon/backend/audit-logs/yono-functions-audit.jsonl | jq .

# Search by request_id
grep "req-abc-123" panteon/backend/audit-logs/yono-functions-audit.jsonl | jq .

# Count requests per principal
cat panteon/backend/audit-logs/yono-functions-audit.jsonl | \
  jq -r 'select(.event=="function_request") | .principal_id' | sort | uniq -c
```

## Deployment

```bash
# Install systemd service
sudo cp panteon/backend/systemd/panteon.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable panteon
sudo systemctl start panteon

# Check status
sudo systemctl status panteon
journalctl -u panteon -f
```

## Rate Limiting

In-memory per-principal rate limiter: 20 requests/hour (configurable).
Returns `429 Too Many Requests` with `X-RateLimit-*` headers when exceeded.
Rejected requests are logged in the audit log.

## Process Safety

- Subprocess timeout: configurable, capped at 300s
- Hung processes are SIGKILL after timeout
- asyncio.wait_for enforces the deadline
- No zombie process accumulation
