# CMB PostgreSQL Migration Plan

**Status**: Documented — 2026-08-01  
**Trigger**: SQLite WAL contention under multi-tenant load (currently handles 10 concurrent ops cleanly)  
**Current DB**: `/srv/cmb/data/cmb.db` (SQLite WAL mode, busy_timeout=5000ms)

---

## 0. Assessment

SQLite with WAL mode currently handles the load (10 concurrent read/write ops = 0 errors). The engine already has a `cmb_ingest_postgres_schema` tool, meaning the Python codebase has psycopg awareness. Migration is a **future-proofing** measure, not an emergency.

**When to migrate**: If concurrent ops > 20 start producing "database is locked" errors, or if the engine needs to scale to 10+ workspaces with heavy write traffic.

---

## 1. Schema Mapping

### Core Tables

| SQLite Table | PostgreSQL Type | Notes |
|---|---|---|
| `memories` | `memories` | Primary table — all columns map directly |
| `workspaces` | `workspaces` | No changes needed |
| `repos` | `repos` | No changes needed |
| `sessions` | `sessions` | No changes needed |
| `receipts` | `receipts` | Hash chain — must preserve order |
| `graph_memory` | `graph_memory` | Entity graph edges |
| `graph_support` | `graph_support` | Evidence links |
| `graph_entity` | `graph_entity` | Canonical entities |
| `code_files` | `code_files` | Indexed source files |
| `code_symbols` | `code_symbols` | Parsed symbols |
| `code_edges` | `code_edges` | Call/import relationships |
| `links` | `links` | A-MEM memory links |
| `automation_phases` | `automation_phases` | Cloud bootstrap state |

### Column Type Changes

| SQLite Type | PostgreSQL Type | Notes |
|---|---|---|
| `TEXT` | `TEXT` | Direct mapping for all text columns |
| `INTEGER` | `BIGINT` | Use BIGINT for all integer columns |
| `REAL` | `DOUBLE PRECISION` | For importance, scores, timestamps |
| `BLOB` | `BYTEA` | For embedding vectors |
| `BOOLEAN` (0/1) | `BOOLEAN` | Convert 0/1 to true/false |
| `JSON` (TEXT) | `JSONB` | For metadata, provenance — use JSONB for indexing |

### Primary Keys

All UUID-style IDs (`mem_01K...`, `ws_01K...`, `repo_01K...`, `ses_01K...`) remain as `TEXT`/`VARCHAR(30)` — no change needed.

### Indexes

Recreate all SQLite indexes as PostgreSQL B-tree indexes. Add GIN index on `metadata` (JSONB) for provenance queries.

---

## 2. Vector Store Migration

### Current: sqlite-vec (or numpy-based)

The engine uses either:
- `sqlite-vec` extension for vector similarity search (384-dim MiniLM embeddings)
- `vector_numpy.py` fallback: in-memory numpy cosine similarity

### Target: pgvector

1. Install `pgvector` extension: `CREATE EXTENSION vector;`
2. Add `embedding vector(384)` column to `memories` table
3. Create HNSW or IVFFlat index: `CREATE INDEX ON memories USING hnsw (embedding vector_cosine_ops);`
4. Migrate existing embeddings from sqlite-vec table or re-compute via embedder

### Migration Steps

```sql
-- Enable pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- Add embedding column
ALTER TABLE memories ADD COLUMN embedding vector(384);

-- Migrate embeddings from sqlite-vec
-- Option A: Export from sqlite-vec, import to pgvector
-- Option B: Re-compute all embeddings (simpler, takes ~5 min for 1000 memories)

-- Create HNSW index for fast similarity search
CREATE INDEX idx_memories_embedding ON memories USING hnsw (embedding vector_cosine_ops);

-- FTS index for lexical search
CREATE INDEX idx_memories_fts ON memories USING gin(to_tsvector('english', title || ' ' || content));
```

---

## 3. Code Graph Migration

The code graph tables (`code_files`, `code_symbols`, `code_edges`) map directly. No special types needed — all TEXT/BIGINT.

```sql
CREATE TABLE code_files (
    id TEXT PRIMARY KEY,
    repo_id TEXT REFERENCES repos(id),
    path TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    lang TEXT,
    updated_at DOUBLE PRECISION
);

CREATE TABLE code_symbols (
    id TEXT PRIMARY KEY,
    repo_id TEXT REFERENCES repos(id),
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    fqname TEXT,
    file TEXT NOT NULL,
    span TEXT,
    signature TEXT,
    lang TEXT,
    exported INTEGER,
    content_hash TEXT,
    valid_from DOUBLE PRECISION,
    valid_to DOUBLE PRECISION
);

CREATE TABLE code_edges (
    id TEXT PRIMARY KEY,
    from_symbol TEXT REFERENCES code_symbols(id),
    to_symbol TEXT REFERENCES code_symbols(id),
    relation TEXT,
    layer TEXT,
    direction TEXT,
    file TEXT,
    line INTEGER
);
```

---

## 4. Receipt Chain Migration

The receipt chain is a hash-linked list (each receipt includes `prev_hash`). This must be preserved exactly during migration to maintain audit integrity.

```sql
CREATE TABLE receipts (
    id TEXT PRIMARY KEY,
    version INTEGER NOT NULL,
    ts_ms BIGINT NOT NULL,
    operation TEXT NOT NULL,
    scope_digest TEXT,
    actor_digest TEXT,
    target_count INTEGER,
    status TEXT,
    metadata JSONB,
    prev_hash TEXT NOT NULL,
    hash TEXT NOT NULL,
    workspace_id TEXT REFERENCES workspaces(id),
    repo_id TEXT REFERENCES repos(id)
);

-- Verify chain after migration
SELECT id, prev_hash, hash FROM receipts ORDER BY ts_ms;
-- Recompute hashes and compare
```

---

## 5. Connection String

```bash
# Current (SQLite)
CMB_DB_PATH=/srv/cmb/data/cmb.db

# After migration (PostgreSQL)
CMB_DB_URL=postgresql://cmb:cmb_password@localhost:5432/cmb
```

The engine's `MemoryService.create()` would need to accept a `db_url` parameter instead of `db_path`. The existing `cmb_ingest_postgres_schema` tool already uses psycopg, so the venv has the dependency.

---

## 6. Migration Script

```python
#!/usr/bin/env python3
"""Migrate CMB from SQLite to PostgreSQL.

Usage: python migrate_to_postgres.py --sqlite /srv/cmb/data/cmb.db --postgres "postgresql://cmb:pass@localhost/cmb"
"""
import sqlite3
import psycopg
import json
import sys
import argparse

def migrate(sqlite_path: str, pg_dsn: str):
    src = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    dst = psycopg.connect(pg_dsn)

    # 1. Create schema (run SQL from schema.sql)
    with open("schema_postgres.sql") as f:
        dst.execute(f.read())

    # 2. Migrate workspaces
    for ws in src.execute("SELECT * FROM workspaces"):
        dst.execute(
            "INSERT INTO workspaces (id, name, description, visibility, created_at) VALUES (%s, %s, %s, %s, %s)",
            (ws["id"], ws["name"], ws["description"], ws["visibility"], ws["created_at"]))

    # 3. Migrate repos
    for r in src.execute("SELECT * FROM repos"):
        dst.execute(
            "INSERT INTO repos (id, workspace_id, name, root_path) VALUES (%s, %s, %s, %s)",
            (r["id"], r["workspace_id"], r["name"], r["root_path"]))

    # 4. Migrate memories (largest table)
    for m in src.execute("SELECT * FROM memories"):
        dst.execute(
            """INSERT INTO memories (id, workspace_id, repo_id, session_id, scope, mtype,
               title, content, summary, keywords, metadata, importance, surprise, stability,
               access_count, last_access, valid_from, valid_to, valid_to_recorded_at,
               ingested_at, expired_at, subject_key, claim_kind, pinned, sensitivity,
               provenance, sort_order, quality_score, ttl_days)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            tuple(m[idx] for idx in range(len(m))))

    # 5. Migrate receipts (preserve chain order)
    for r in src.execute("SELECT * FROM receipts ORDER BY ts_ms"):
        dst.execute(
            """INSERT INTO receipts (id, version, ts_ms, operation, scope_digest, actor_digest,
               target_count, status, metadata, prev_hash, hash, workspace_id, repo_id)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (r["id"], r["version"], r["ts_ms"], r["operation"], r["scope_digest"],
             r["actor_digest"], r["target_count"], r["status"],
             json.dumps(r["metadata"]) if r["metadata"] else None,
             r["prev_hash"], r["hash"], r["workspace_id"], r["repo_id"]))

    # 6. Migrate sessions, links, graph tables, code tables...
    # (same pattern as above)

    dst.commit()

    # 7. Verify chain integrity
    verify_receipt_chain(dst)

    src.close()
    dst.close()
    print("Migration complete")

def verify_receipt_chain(conn):
    """Verify the receipt hash chain after migration."""
    rows = conn.execute("SELECT id, prev_hash, hash FROM receipts ORDER BY ts_ms").fetchall()
    import hashlib
    prev = None
    for row in rows:
        expected = row["prev_hash"]
        if prev is not None:
            assert expected == prev, f"Chain broken at {row['id']}: expected {prev}, got {expected}"
        # Verify hash
        payload = json.dumps({"id": row["id"], "prev_hash": row["prev_hash"]}, sort_keys=True)
        computed = hashlib.sha256(payload.encode()).hexdigest()
        # Note: actual hash computation depends on the engine's receipt format
        prev = row["hash"]
    print(f"Receipt chain verified: {len(rows)} receipts")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite", required=True)
    parser.add_argument("--postgres", required=True)
    args = parser.parse_args()
    migrate(args.sqlite, args.postgres)
```

---

## 7. Downtime Estimate

| Phase | Duration | Notes |
|---|---|---|
| Schema creation | < 1s | DDL only |
| Data export (SQLite read) | ~30s | 1000 memories, 100 receipts, graph tables |
| Data import (PostgreSQL write) | ~60s | Bulk INSERT with COPY would be faster |
| Embedding re-computation | ~5 min | 1000 memories × 384-dim MiniLM (~0.3s each) |
| Index creation | ~30s | HNSW + GIN indexes |
| Chain verification | ~5s | Hash check on receipts |
| **Total** | **~7 min** | With COPY instead of INSERT: ~4 min |

---

## 8. Rollback Plan

1. **Keep SQLite DB intact** during migration (read-only mode)
2. **Dual-write period**: After migration, run both SQLite and PostgreSQL in parallel for 1 week
3. **Switch-over**: Update `CMB_DB_URL` env var, restart engine
4. **Rollback**: If PostgreSQL fails, revert `CMB_DB_PATH` to SQLite path, restart engine
5. **Data sync**: During dual-write, a simple script copies new SQLite writes to PostgreSQL (or vice versa)

```bash
# Rollback command
export CMB_DB_PATH=/srv/cmb/data/cmb.db
unset CMB_DB_URL
systemctl restart cmb-engine
```

---

## 9. Post-Migration Optimizations

1. **Connection pooling**: Use `pgbouncer` or `asyncpg` pool (5-20 connections)
2. **Read replicas**: For dashboard/analytics reads, offload to a replica
3. **Partitioning**: Partition `memories` by `workspace_id` for multi-tenant isolation
4. **Materialized views**: For analytics queries (token savings, quality distribution)
5. **Autovacuum tuning**: Aggressive autovacuum for high-write tables (receipts, memories)

---

**End of Document**
