"""JWT authentication and password hashing."""
import os
import time
from datetime import datetime, timedelta

import jwt
from passlib.context import CryptContext

SECRET_KEY = os.environ.get('HS_SECRET', 'panteon-engine-2026-alieninc-secret-key')
ALGORITHM = 'HS256'
TOKEN_EXPIRY_HOURS = 24

pwd_ctx = CryptContext(schemes=['bcrypt'], deprecated='auto')

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
