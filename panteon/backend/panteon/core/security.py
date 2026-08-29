import time
import hashlib
import hmac
from collections import defaultdict
from typing import Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import structlog

from panteon.core.config import settings

logger = structlog.get_logger()

ALLOWED_ORIGINS = [
    "https://alieninc.tech",
    "https://thedailyartcult.lol",
    "https://accounts.thedailyartcult.lol",
    "https://support.thedailyartcult.lol",
    "https://policy.thedailyartcult.lol",
    "https://publications.thedailyartcult.lol",
]

if settings.debug:
    ALLOWED_ORIGINS.extend([
        "http://localhost:8000",
        "http://localhost:3000",
        "http://127.0.0.1:8000",
    ])


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(self), geolocation=()"
        if not settings.debug:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


class RateLimitState:
    def __init__(self, max_requests: int = 120, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.clients: dict[str, list[float]] = defaultdict(list)

    def is_limited(self, client_key: str) -> bool:
        now = time.time()
        cutoff = now - self.window_seconds
        self.clients[client_key] = [
            t for t in self.clients[client_key] if t > cutoff
        ]
        if len(self.clients[client_key]) >= self.max_requests:
            return True
        self.clients[client_key].append(now)
        return False

    def cleanup(self):
        now = time.time()
        cutoff = now - self.window_seconds * 2
        stale = [k for k, v in self.clients.items() if all(t < cutoff for t in v)]
        for k in stale:
            del self.clients[k]


api_rate_limit = RateLimitState(max_requests=300, window_seconds=60)
auth_rate_limit = RateLimitState(max_requests=10, window_seconds=300)


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        auth_header = request.headers.get("authorization", "")
        key = f"{client_ip}:{auth_header[:20]}" if auth_header else client_ip

        path = request.url.path
        if path.startswith("/api/v1/auth"):
            limiter = auth_rate_limit
        else:
            limiter = api_rate_limit

        if limiter.is_limited(key):
            logger.warning("rate_limit_exceeded", path=path, client=client_ip)
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Try again later."},
                headers={
                    "Retry-After": str(limiter.window_seconds),
                    "X-RateLimit-Limit": str(limiter.max_requests),
                },
            )

        response = await call_next(request)
        return response


AUDIT_EXCLUDED_PATHS = {
    "/health", "/docs", "/redoc", "/openapi.json", "/favicon.ico",
}
# High-frequency polling endpoints excluded to keep the audit table lean.
AUDIT_EXCLUDED_PREFIXES = ("/static", "/api/v1/maven/tick", "/api/v1/maven/state")
AUDIT_RETENTION_DAYS = 90
AUDIT_PRUNE_INTERVAL_S = 6 * 3600


class AuditMiddleware(BaseHTTPMiddleware):
    _last_prune: float = 0.0

    async def dispatch(self, request: Request, call_next):
        start = time.time()
        response: Response = await call_next(request)
        duration_ms = round((time.time() - start) * 1000, 1)

        path = request.url.path
        if path in AUDIT_EXCLUDED_PATHS or path.startswith(AUDIT_EXCLUDED_PREFIXES):
            return response

        method = request.method
        status_code = response.status_code
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "")[:500]

        auth_header = request.headers.get("authorization", "")
        user_email = None
        user_id = None
        role = None
        auth_state = "none"  # no Authorization header at all
        if auth_header.startswith("Bearer "):
            auth_state = "present"
            from panteon.core.auth import decode_supabase_claims, verify_supabase_token
            token = auth_header[7:]
            claims = decode_supabase_claims(token)
            exp = claims.get("exp") if claims else None
            if exp and time.time() >= float(exp):
                auth_state = "expired"  # header present but token past exp
            # Email is not in modern Supabase JWTs; resolve via the shared
            # verify cache (network fetch only on a cold token).
            try:
                user = await verify_supabase_token(token)
            except Exception:
                user = None
            if user:
                user_email = user.email
                user_id = user.id
                role = user.role

        log_level = "warning" if status_code >= 400 else "info"
        getattr(logger, log_level)(
            "audit",
            method=method,
            path=path,
            status=status_code,
            duration_ms=duration_ms,
            client=client_ip,
            user=user_email or "anonymous",
            role=role,
            auth=auth_state,
            ua=user_agent[:80],
        )

        try:
            await self._persist(
                user_email=user_email,
                user_id=user_id,
                method=method,
                path=path,
                status_code=status_code,
                client_ip=client_ip,
                user_agent=user_agent,
                duration_ms=duration_ms,
            )
        except Exception:
            pass  # audit must never break the request path

        await self._maybe_prune()

        return response

    @staticmethod
    async def _persist(**fields):
        from datetime import datetime
        from panteon.core.audit import AuditLog
        from panteon.core.database import async_session

        async with async_session() as session:
            session.add(AuditLog(timestamp=datetime.utcnow(), **fields))
            await session.commit()

    @classmethod
    async def _maybe_prune(cls):
        now = time.time()
        if now - cls._last_prune < AUDIT_PRUNE_INTERVAL_S:
            return
        cls._last_prune = now
        try:
            from datetime import datetime, timedelta
            from sqlalchemy import delete
            from panteon.core.audit import AuditLog
            from panteon.core.database import async_session

            cutoff = datetime.utcnow() - timedelta(days=AUDIT_RETENTION_DAYS)
            async with async_session() as session:
                await session.execute(delete(AuditLog).where(AuditLog.timestamp < cutoff))
                await session.commit()
        except Exception:
            pass
