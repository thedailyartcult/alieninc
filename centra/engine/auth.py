"""JWT authentication and password hashing."""
import os
import time
from datetime import datetime, timedelta

import httpx

import jwt
from passlib.context import CryptContext

SECRET_KEY = os.environ.get('HS_SECRET', 'centra-engine-2026-alieninc-secret-key')
ALGORITHM = 'HS256'
TOKEN_EXPIRY_HOURS = 24

pwd_ctx = CryptContext(schemes=['pbkdf2_sha256'], deprecated='auto')

db_ref = None


def set_db(database):
    global db_ref
    db_ref = database


def create_token(user_id: int, username: str, company_id: str, role: str) -> str:
    exp = datetime.utcnow() + timedelta(hours=TOKEN_EXPIRY_HOURS)
    payload = {
        'user_id': user_id,
        'username': username,
        'company_id': company_id,
        'role': role,
        'exp': exp,
        'iat': datetime.utcnow(),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


def get_password_hash(password: str) -> str:
    return pwd_ctx.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_ctx.verify(plain, hashed)


async def authenticate_user(username: str, password: str) -> dict | None:
    if not db_ref:
        return None
    user = await db_ref.get_user(username)
    if not user:
        return None
    if not verify_password(password, user['password_hash']):
        return None
    return user


# ── Supabase portal-session verification ──
# The centra portal (hs_session) holds a Supabase access_token. Because this
# project uses legacy HS256 (anon key is public), signature checks alone are
# meaningless — so we ask Supabase itself whether the token is a live session.

_supabase_url = None
_supabase_anon_key = None
_supabase_cache: dict[str, tuple[float, str]] = {}
SUPABASE_CACHE_TTL = 300.0


def _load_supabase_env() -> None:
    """Load SUPABASE_URL/ANON_KEY from env, else the shared panteon .env
    (same ALIENINC Supabase project as the centra portal)."""
    global _supabase_url, _supabase_anon_key
    if _supabase_url is not None:
        return
    _supabase_url = os.environ.get('SUPABASE_URL', '')
    _supabase_anon_key = os.environ.get('SUPABASE_ANON_KEY', '')
    if _supabase_url and _supabase_anon_key:
        return
    p = os.environ.get('PANTEON_ENV', '/home/alieninc/panteon/backend/.env')
    try:
        with open(p) as f:
            for line in f:
                line = line.strip()
                if line.startswith('SUPABASE_URL='):
                    _supabase_url = line.split('=', 1)[1].strip().strip('"').strip("'")
                elif line.startswith('SUPABASE_ANON_KEY='):
                    _supabase_anon_key = line.split('=', 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass


def verify_supabase_token(token: str) -> str | None:
    """Return the user id if the Supabase session token is live, else None.
    Results are cached per token for SUPABASE_CACHE_TTL seconds."""
    _load_supabase_env()
    now = time.time()
    hit = _supabase_cache.get(token)
    if hit and now - hit[0] < SUPABASE_CACHE_TTL:
        return hit[1]
    if not _supabase_url:
        return None
    try:
        r = httpx.get(
            _supabase_url.rstrip('/') + '/auth/v1/user',
            headers={
                'Authorization': 'Bearer ' + token,
                'apikey': _supabase_anon_key or token,
            },
            timeout=5.0,
        )
        if r.status_code != 200:
            return None
        uid = r.json().get('id') or r.json().get('sub')
        if not uid:
            return None
        _supabase_cache[token] = (now, uid)
        return uid
    except Exception:
        return None
