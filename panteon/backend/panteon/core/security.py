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
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
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


api_rate_limit = RateLimitState(max_requests=120, window_seconds=60)
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


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.time()
        response: Response = await call_next(request)
        duration_ms = round((time.time() - start) * 1000, 1)

        path = request.url.path
        if path in ("/health",) or path.startswith("/static"):
            return response

        method = request.method
        status_code = response.status_code
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "")[:200]

        auth_header = request.headers.get("authorization", "")
        user_email = None
        if auth_header.startswith("Bearer "):
            from panteon.core.auth import decode_supabase_claims
            claims = decode_supabase_claims(auth_header[7:])
            if claims:
                user_email = claims.get("email")

        log_level = "warning" if status_code >= 400 else "info"
        getattr(logger, log_level)(
            "audit",
            method=method,
            path=path,
            status=status_code,
            duration_ms=duration_ms,
            client=client_ip,
            user=user_email or "anonymous",
            ua=user_agent[:80],
        )

        return response
