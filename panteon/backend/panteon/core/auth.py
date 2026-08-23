from __future__ import annotations

import hashlib
import httpx
import time
from typing import Optional
from collections import OrderedDict
from jose import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from panteon.core.config import settings

security = HTTPBearer(auto_error=False)

_VERIFY_CACHE_TTL = 300
_VERIFY_CACHE_MAX = 256


class _VerifyCache:
    """In-process LRU cache for Supabase token verification.

    Every authenticated API call used to trigger a live HTTPS round-trip to
    Supabase /auth/v1/user. With ~13 parallel calls per admin Overview refresh
    that made the dashboard look like it was constantly reconnecting whenever
    Supabase was slow or flaky. Verified tokens (or verified-negative results)
    are cached for a short TTL so only the first request per token hits the
    network.
    """

    def __init__(self, ttl: int = _VERIFY_CACHE_TTL, max_size: int = _VERIFY_CACHE_MAX):
        self.ttl = ttl
        self.max_size = max_size
        self._store: OrderedDict[str, tuple[float, Optional[SupabaseUser]]] = OrderedDict()

    def get(self, token: str) -> tuple[bool, Optional[SupabaseUser]]:
        key = self._key(token)
        now = time.time()
        item = self._store.get(key)
        if item is None:
            return False, None
        (expires, user) = item
        if now > expires:
            del self._store[key]
            return False, None
        self._store.move_to_end(key)
        return True, user

    def set(self, token: str, user: Optional[SupabaseUser]):
        key = self._key(token)
        self._store[key] = (time.time() + self.ttl, user)
        self._store.move_to_end(key)
        while len(self._store) > self.max_size:
            self._store.popitem(last=False)

    @staticmethod
    def _key(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()


_verify_cache = _VerifyCache()


class SupabaseUser:
    def __init__(self, user_id: str, email: str, role: str = "viewer"):
        self.id = user_id
        self.email = email
        self.role = role


def decode_supabase_claims(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, options={"verify_signature": False})
        return payload
    except Exception:
        return None


def resolve_role(email: str) -> str:
    if not email:
        return "viewer"
    email_lower = email.lower()
    superadmins = [e.strip().lower() for e in (settings.superadmin_emails or "").split(",") if e.strip()]
    if email_lower in superadmins:
        return "superadmin"
    mimi_only = [e.strip().lower() for e in (settings.mimi_only_emails or "").split(",") if e.strip()]
    if email_lower in mimi_only:
        return "mimi"
    admins = [e.strip().lower() for e in (settings.admin_emails or "").split(",") if e.strip()]
    if email_lower in admins:
        return "admin"
    editors = [e.strip().lower() for e in (settings.editor_emails or "").split(",") if e.strip()]
    if email_lower in editors:
        return "editor"
    return "viewer"


async def verify_supabase_token(token: str) -> Optional[SupabaseUser]:
    cached, user = _verify_cache.get(token)
    if cached:
        return user
    api_key = settings.supabase_service_role_key or settings.supabase_anon_key
    if not settings.supabase_url or not api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Supabase not configured",
        )
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{settings.supabase_url}/auth/v1/user",
                headers={
                    "apikey": api_key,
                    "Authorization": f"Bearer {token}",
                },
                timeout=10,
            )
    except httpx.HTTPError:
        _verify_cache.set(token, None)
        return None
    if resp.status_code != 200:
        _verify_cache.set(token, None)
        return None
    data = resp.json()
    email = data.get("email", "")
    allowed_domains = [d.strip().lower() for d in (settings.allowed_email_domains or "").split(",") if d.strip()]
    if allowed_domains and email:
        domain = email.split("@", 1)[-1].lower() if "@" in email else ""
        if not any(domain == d or domain.endswith("." + d) for d in allowed_domains):
            _verify_cache.set(token, None)
            return None
    user = SupabaseUser(
        user_id=data["id"],
        email=email,
        role=resolve_role(email),
    )
    _verify_cache.set(token, user)
    return user


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> SupabaseUser:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = await verify_supabase_token(credentials.credentials)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired Supabase session",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_role(minimum_role: str):
    role_hierarchy = {"viewer": 0, "mimi": 0, "editor": 1, "admin": 2, "superadmin": 3}
    async def role_checker(current_user: SupabaseUser = Depends(get_current_user)):
        user_level = role_hierarchy.get(current_user.role, 0)
        required_level = role_hierarchy.get(minimum_role, 0)
        if user_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires {minimum_role} role or higher",
            )
        return current_user
    return role_checker


def require_smm_access():
    """MiMi Panel access: superadmins always; dedicated MiMi-only operators."""
    async def smm_checker(current_user: SupabaseUser = Depends(get_current_user)):
        if current_user.role not in ("superadmin", "mimi"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Requires MiMi panel access",
            )
        return current_user
    return smm_checker
