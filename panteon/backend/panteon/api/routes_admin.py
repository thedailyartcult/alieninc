from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from panteon.core.database import get_db
from panteon.core.auth import SupabaseUser, require_role
from panteon.core.apikeys import APIKey, generate_api_key, hash_api_key

router = APIRouter(prefix="/admin", tags=["Platform Admin"])


class APIKeyCreate(BaseModel):
    name: str
    description: Optional[str] = None
    scopes: str = "read"
    expires_days: Optional[int] = None


class APIKeyResponse(BaseModel):
    id: str
    name: str
    key_prefix: str
    scopes: str
    is_active: bool
    created_at: str
    last_used_at: Optional[str]
    expires_at: Optional[str]


class APIKeyCreatedResponse(APIKeyResponse):
    raw_key: str


@router.post("/api-keys", response_model=APIKeyCreatedResponse)
async def create_api_key(
    data: APIKeyCreate,
    current_user: SupabaseUser = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    raw_key, key_hash, key_prefix = generate_api_key()
    expires_at = None
    if data.expires_days:
        from datetime import timedelta
        expires_at = datetime.utcnow() + timedelta(days=data.expires_days)

    key_record = APIKey(
        name=data.name,
        key_hash=key_hash,
        key_prefix=key_prefix,
        description=data.description,
        scopes=data.scopes,
        created_by=current_user.email,
        expires_at=expires_at,
    )
    db.add(key_record)
    await db.flush()

    return APIKeyCreatedResponse(
        id=str(key_record.id),
        name=key_record.name,
        key_prefix=key_record.key_prefix,
        scopes=key_record.scopes,
        is_active=key_record.is_active,
        created_at=key_record.created_at.isoformat(),
        last_used_at=key_record.last_used_at.isoformat() if key_record.last_used_at else None,
        expires_at=key_record.expires_at.isoformat() if key_record.expires_at else None,
        raw_key=raw_key,
    )


@router.get("/api-keys", response_model=list[APIKeyResponse])
async def list_api_keys(
    current_user: SupabaseUser = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(APIKey).order_by(desc(APIKey.created_at)))
    return [
        APIKeyResponse(
            id=str(k.id), name=k.name, key_prefix=k.key_prefix,
            scopes=k.scopes, is_active=k.is_active,
            created_at=k.created_at.isoformat(),
            last_used_at=k.last_used_at.isoformat() if k.last_used_at else None,
            expires_at=k.expires_at.isoformat() if k.expires_at else None,
        )
        for k in result.scalars().all()
    ]


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(
    key_id: str,
    current_user: SupabaseUser = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(APIKey).where(APIKey.id == key_id))
    key_record = result.scalar_one_or_none()
    if not key_record:
        raise HTTPException(status_code=404, detail="API key not found")
    key_record.is_active = False
    await db.flush()
    return {"revoked": True}
