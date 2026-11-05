import uuid
import secrets
import hashlib
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, String, Text, DateTime, Boolean
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends, HTTPException, status, Security
from fastapi.security import APIKeyHeader
from panteon.core.database import Base, get_db
from panteon.core.types import UUID_COL


class APIKey(Base):
    __tablename__ = "api_keys"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    key_hash = Column(String(128), nullable=False, unique=True, index=True)
    key_prefix = Column(String(12), nullable=False)
    description = Column(Text)
    scopes = Column(String(500), default="read")
    is_active = Column(Boolean, default=True)
    created_by = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)
    last_used_at = Column(DateTime)
    expires_at = Column(DateTime)


def generate_api_key() -> tuple[str, str, str]:
    raw_key = f"panteon_{secrets.token_urlsafe(48)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    key_prefix = raw_key[:12]
    return raw_key, key_hash, key_prefix


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def get_api_key_user(
    api_key: Optional[str] = Security(api_key_header),
    db: AsyncSession = Depends(get_db),
) -> Optional[dict]:
    if not api_key:
        return None
    key_hash = hash_api_key(api_key)
    result = await db.execute(
        select(APIKey).where(APIKey.key_hash == key_hash, APIKey.is_active == True)
    )
    key_record = result.scalar_one_or_none()
    if not key_record:
        return None
    if key_record.expires_at and key_record.expires_at < datetime.utcnow():
        return None
    key_record.last_used_at = datetime.utcnow()
    await db.flush()
    return {
        "type": "api_key",
        "key_id": key_record.id,
        "name": key_record.name,
        "scopes": key_record.scopes,
    }
