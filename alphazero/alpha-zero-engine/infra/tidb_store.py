"""TiDB persistence layer — durable simulation results and universe states.

Phase 4: Infrastructure. TiDB is MySQL wire-protocol compatible; this layer
uses pymysql against the standard `alpha_zero` database. It runs unchanged
against a real TiDB server (`tidb-server -store unistore`, port 4000) or any
MySQL-compatible server (MariaDB/MySQL) during development.

Connection settings:
    ALPHA_ZERO_SQL_DSN   e.g. mysql://root@127.0.0.1:4000/alpha_zero
                         (default: mysql://root@127.0.0.1:4000/alpha_zero)
    ALPHA_ZERO_SQL=0     disables persistence entirely (engine keeps running)

Schema is bootstrapped idempotently on first use (see bootstrap_schema()).
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Optional

SQL_DSN = os.environ.get(
    "ALPHA_ZERO_SQL_DSN", "mysql://root@127.0.0.1:4000/alpha_zero"
)
ENABLED = os.environ.get("ALPHA_ZERO_SQL", "1") != "0"

SCHEMA = """
CREATE TABLE IF NOT EXISTS simulation_reports (
    id           VARCHAR(64)  PRIMARY KEY,
    run_type     VARCHAR(32)  NOT NULL,
    config       JSON         NOT NULL,
    report       JSON         NOT NULL,
    backend      VARCHAR(16)  DEFAULT 'python',
    created_at   TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    KEY idx_reports_type (run_type),
    KEY idx_reports_created (created_at)
);

CREATE TABLE IF NOT EXISTS universe_states (
    universe_id  VARCHAR(64)  PRIMARY KEY,
    name         VARCHAR(64)  NOT NULL,
    age          INT          NOT NULL,
    state        JSON         NOT NULL,
    created_at   TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    KEY idx_universe_age (age)
);
"""

_conn: Optional[Any] = None


def _parse_dsn(dsn: str) -> dict:
    """Parse mysql://[user[:pass]@]host:port/db into pymysql kwargs."""
    rest = dsn.split("://", 1)[-1]
    creds, _, hostport = rest.rpartition("@")
    db = "alpha_zero"
    if "/" in hostport:
        hostport, _, db = hostport.partition("/")
    host, _, port = hostport.rpartition(":")
    port = int(port or "4000")
    user = "root"
    password = ""
    if creds:
        if ":" in creds:
            user, _, password = creds.partition(":")
        else:
            user = creds
    return {
        "host": host or "127.0.0.1",
        "port": port,
        "user": user or "root",
        "password": password,
        "database": db,
    }


def _connect():
    global _conn
    if _conn is not None:
        return _conn
    if not ENABLED:
        return None
    try:
        import pymysql
        params = _parse_dsn(SQL_DSN)
        _conn = pymysql.connect(
            host=params["host"], port=params["port"], user=params["user"],
            password=params["password"],
            connect_timeout=3, autocommit=True,
        )
        return _conn
    except Exception:
        _conn = None
        return None


def healthy() -> bool:
    if not ENABLED:
        return False
    conn = _connect()
    if conn is None:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return True
    except Exception:
        return False


def bootstrap_schema() -> bool:
    """Create tables if missing; returns True on success."""
    conn = _connect()
    if conn is None:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE DATABASE IF NOT EXISTS alpha_zero")
            cur.execute("USE alpha_zero")
            for statement in SCHEMA.split(";"):
                if statement.strip():
                    cur.execute(statement)
        return True
    except Exception:
        return False


def save_report(
    report_id: str,
    run_type: str,
    config: dict,
    report: dict,
    backend: str = "python",
) -> bool:
    """Persist a simulation report; upserts on collision."""
    conn = _connect()
    if conn is None:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("USE alpha_zero")
            cur.execute(
                """INSERT INTO simulation_reports
                   (id, run_type, config, report, backend)
                   VALUES (%s, %s, %s, %s, %s)
                   ON DUPLICATE KEY UPDATE
                     run_type = VALUES(run_type),
                     report = VALUES(report),
                     backend = VALUES(backend)""",
                (report_id, run_type, json.dumps(config, default=str),
                 json.dumps(report, default=str), backend),
            )
        return True
    except Exception:
        return False


def load_report(report_id: str) -> Optional[dict]:
    conn = _connect()
    if conn is None:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute("USE alpha_zero")
            cur.execute(
                "SELECT report FROM simulation_reports WHERE id = %s", (report_id,)
            )
            row = cur.fetchone()
            return json.loads(row[0]) if row else None
    except Exception:
        return None


def list_reports(run_type: Optional[str] = None, limit: int = 50) -> list[dict]:
    conn = _connect()
    if conn is None:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute("USE alpha_zero")
            if run_type:
                cur.execute(
                    """SELECT id, run_type, backend, created_at FROM simulation_reports
                       WHERE run_type = %s ORDER BY created_at DESC LIMIT %s""",
                    (run_type, int(limit)),
                )
            else:
                cur.execute(
                    """SELECT id, run_type, backend, created_at FROM simulation_reports
                       ORDER BY created_at DESC LIMIT %s""",
                    (int(limit),),
                )
            return [
                {"id": r[0], "run_type": r[1], "backend": r[2],
                 "created_at": r[3].isoformat() if r[3] else None}
                for r in cur.fetchall()
            ]
    except Exception:
        return []


def save_universe(universe_id: str, name: str, age: int, state: dict) -> bool:
    conn = _connect()
    if conn is None:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("USE alpha_zero")
            cur.execute(
                """INSERT INTO universe_states (universe_id, name, age, state)
                   VALUES (%s, %s, %s, %s)
                   ON DUPLICATE KEY UPDATE
                     name = VALUES(name), age = VALUES(age), state = VALUES(state)""",
                (universe_id, name, int(age), json.dumps(state, default=str)),
            )
        return True
    except Exception:
        return False


def load_universe(universe_id: str) -> Optional[dict]:
    conn = _connect()
    if conn is None:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute("USE alpha_zero")
            cur.execute(
                "SELECT state FROM universe_states WHERE universe_id = %s",
                (universe_id,),
            )
            row = cur.fetchone()
            return json.loads(row[0]) if row else None
    except Exception:
        return None


def recent_run_metrics(run_type: str, hours: int = 24) -> Optional[dict]:
    """Aggregate summary of recent runs of a type (for dashboards)."""
    conn = _connect()
    if conn is None:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute("USE alpha_zero")
            cur.execute(
                """SELECT COUNT(*), AVG(JSON_LENGTH(report)) FROM simulation_reports
                   WHERE run_type = %s AND created_at > NOW() - INTERVAL %s HOUR""",
                (run_type, int(hours)),
            )
            row = cur.fetchone()
            if row and row[0]:
                return {"count": row[0], "avg_report_size": round(row[1] or 0, 1)}
    except Exception:
        pass
    return None
