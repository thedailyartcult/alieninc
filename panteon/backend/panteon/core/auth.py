import httpx
from typing import Optional
from jose import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from panteon.core.config import settings

security = HTTPBearer(auto_error=False)


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
    admins = [e.strip().lower() for e in (settings.admin_emails or "").split(",") if e.strip()]
    if email_lower in admins:
        return "admin"
    editors = [e.strip().lower() for e in (settings.editor_emails or "").split(",") if e.strip()]
    if email_lower in editors:
        return "editor"
    return "viewer"


async def verify_supabase_token(token: str) -> Optional[SupabaseUser]:
    api_key = settings.supabase_service_role_key or settings.supabase_anon_key
    if not settings.supabase_url or not api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Supabase not configured",
        )
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{settings.supabase_url}/auth/v1/user",
            headers={
                "apikey": api_key,
                "Authorization": f"Bearer {token}",
            },
            timeout=10,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        email = data.get("email", "")
        allowed_domains = [d.strip().lower() for d in (settings.allowed_email_domains or "").split(",") if d.strip()]
        if allowed_domains and email:
            domain = email.split("@", 1)[-1].lower() if "@" in email else ""
            if not any(domain == d or domain.endswith("." + d) for d in allowed_domains):
                return None
        return SupabaseUser(
            user_id=data["id"],
            email=email,
            role=resolve_role(email),
        )


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
    role_hierarchy = {"viewer": 0, "editor": 1, "admin": 2, "superadmin": 3}
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
