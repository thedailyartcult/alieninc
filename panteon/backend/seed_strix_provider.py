#!/usr/bin/env python3
"""Seed/refresh the YONO LLM provider + model used for strix scans.

Idempotent: creates the provider and model only if missing; otherwise
updates base_url and (if a new key is given) the encrypted key.
"""
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet

BACKEND = Path("/home/alieninc/panteon/backend")
DB = BACKEND / "panteon.db"
KEYFILE = BACKEND / ".yono_secret_key"

PROVIDER_NAME = os.environ.get("STRIX_PROVIDER", "Hetzner")
PROVIDER_TYPE = "openai"
BASE_URL = os.environ.get("LLM_API_BASE", "https://inference.hetzner.com/api/v1")
API_KEY = os.environ.get("LLM_API_KEY", "")
MODEL_ID = os.environ.get("STRIX_MODEL", "openai/Qwen/Qwen3.6-35B-A3B-FP8")
DISPLAY = os.environ.get("STRIX_MODEL_DISPLAY", "Qwen3.6-35B-A3B-FP8 (Strix)")


def main() -> None:
    if not KEYFILE.exists():
        KEYFILE.write_bytes(Fernet.generate_key())
        try:
            os.chmod(KEYFILE, 0o600)
        except OSError:
            pass
        print("generated key file", KEYFILE)
    env_key = os.environ.get("YONO_SECRET_KEY", "")
    key = env_key.encode("utf-8") if env_key else KEYFILE.read_bytes()
    f = Fernet(key)
    enc = f.encrypt(API_KEY.encode("utf-8")).decode("utf-8") if API_KEY else None

    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()

    row = cur.execute(
        "SELECT id FROM yono_llm_providers WHERE name = ?", (PROVIDER_NAME,)
    ).fetchone()
    if row:
        pid = row[0]
        cur.execute(
            "UPDATE yono_llm_providers SET base_url=?, "
            "api_key_encrypted=COALESCE(?, api_key_encrypted), is_enabled=1 WHERE id=?",
            (BASE_URL, enc, pid),
        )
        print("updated provider", PROVIDER_NAME, pid)
    else:
        pid = str(uuid.uuid4())
        cur.execute(
            "INSERT INTO yono_llm_providers "
            "(id,name,provider_type,api_key_encrypted,base_url,is_enabled,created_at) "
            "VALUES (?,?,?,?,?,1,?)",
            (pid, PROVIDER_NAME, PROVIDER_TYPE, enc, BASE_URL, now),
        )
        print("created provider", PROVIDER_NAME, pid)

    mrow = cur.execute(
        "SELECT id FROM yono_llm_models WHERE provider_id=? AND model_id=?",
        (pid, MODEL_ID),
    ).fetchone()
    if mrow:
        print("model exists", mrow[0])
    else:
        mid = str(uuid.uuid4())
        cur.execute(
            "INSERT INTO yono_llm_models "
            "(id,provider_id,model_id,display_name,capabilities,max_tokens,"
            "cost_per_1k_input,cost_per_1k_output,is_enabled,created_at) "
            "VALUES (?,?,?,?,?,?,0,0,1,?)",
            (mid, pid, MODEL_ID, DISPLAY, "[]", 8192, now),
        )
        print("created model", mid)

    conn.commit()
    conn.close()
    print("done")


if __name__ == "__main__":
    main()
