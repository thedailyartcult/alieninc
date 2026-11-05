import json
import os
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from panteon.core.auth import SupabaseUser, get_current_user

router = APIRouter(prefix="/auth", tags=["Auth"])

# Unified login audit — same file as legacy server.py (secure.alieninc.tech)
# so the secure dashboard at /api/audit/access sees Panteon logins too.
# server.py default: ROOT/data/compliance/login_audit.jsonl where ROOT=/home/alieninc
_LOGIN_AUDIT_PATH = Path(os.environ.get("SECURE_LOGIN_AUDIT_FILE", "/home/alieninc/data/compliance/login_audit.jsonl"))


def _append_login_audit(email: str, ok: bool, ip: str, ua: str, source: str = "panteon") -> None:
    try:
        _LOGIN_AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        rec = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "email": (email or "").strip()[:254],
            "ip": ip or "",
            "user_agent": (ua or "")[:500],
            "result": "success" if ok else "failure",
            "source": source,
        }
        with open(_LOGIN_AUDIT_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, sort_keys=True) + "\n")
    except Exception:
        pass


class LoginAuditIn(BaseModel):
    email: str
    success: bool
    error_code: Optional[str] = None
    source: Optional[str] = None


@router.get("/me")
async def whoami(current_user: SupabaseUser = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "role": current_user.role,
    }


@router.post("/login-audit")
async def login_audit(payload: LoginAuditIn, request: Request):
    """Append-only login event to the shared compliance JSONL.

    Unauthenticated on purpose — must log failures before a token exists.
    Rate-limited by RateLimitMiddleware (10/300s for /api/v1/auth/*).
    """
    ip = request.client.host if request.client else "unknown"
    # Honor CF real IP if nginx forwarded it
    xf = request.headers.get("x-forwarded-for") or request.headers.get("cf-connecting-ip")
    if xf:
        ip = xf.split(",")[0].strip() or ip
    ua = request.headers.get("user-agent", "")
    src = (payload.source or "panteon").strip()[:32] or "panteon"
    _append_login_audit(payload.email, bool(payload.success), ip, ua, source=src)
    return {"ok": True}
