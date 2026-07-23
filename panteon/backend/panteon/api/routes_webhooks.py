import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from typing import Optional
from panteon.core.database import get_db
from panteon.core.tenant import Tenant, TenantMetric
import structlog

logger = structlog.get_logger()

router = APIRouter(prefix="/webhooks/tdac", tags=["TDAC Webhooks"])


class ReflectionCompleted(BaseModel):
    patron_id: str
    reflection_id: str
    publisher_id: str
    duration_seconds: int
    listened_percentage: float = 0
    topic: Optional[str] = None


class PatronUpdated(BaseModel):
    patron_id: str
    context_update_count: Optional[int] = None
    subscription_tier: Optional[str] = None


class GamePlayed(BaseModel):
    patron_id: str
    game_type: str
    streak: int
    score: int


class GiftCardRedeemed(BaseModel):
    giftcard_id: str
    patron_id: str
    destination: Optional[str] = None


def verify_webhook_secret(secret: str = Header(None, alias="X-Webhook-Secret")):
    if not secret:
        raise HTTPException(status_code=401, detail="Missing webhook secret")
    return secret


@router.post("/reflection-completed")
async def on_reflection_completed(
    data: ReflectionCompleted,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    logger.info("tdac_reflection_completed", patron_id=data.patron_id, reflection_id=data.reflection_id)

    tenant = await db.get(Tenant, "00000000-0000-0000-0000-000000000001")
    if not tenant:
        raise HTTPException(status_code=404, detail="TDAC tenant not found")

    metric = TenantMetric(
        tenant_id=tenant.id,
        metric_type="reflection_completed",
        value={
            "patron_id": data.patron_id,
            "reflection_id": data.reflection_id,
            "publisher_id": data.publisher_id,
            "duration_seconds": data.duration_seconds,
            "listened_percentage": data.listened_percentage,
            "topic": data.topic,
        },
        computed_at=datetime.utcnow(),
    )
    db.add(metric)
    await db.flush()

    return {"status": "recorded", "metric_id": str(metric.id)}


@router.post("/patron-updated")
async def on_patron_updated(
    data: PatronUpdated,
    db: AsyncSession = Depends(get_db),
):
    logger.info("tdac_patron_updated", patron_id=data.patron_id)

    tenant = await db.get(Tenant, "00000000-0000-0000-0000-000000000001")
    if not tenant:
        raise HTTPException(status_code=404, detail="TDAC tenant not found")

    metric = TenantMetric(
        tenant_id=tenant.id,
        metric_type="patron_context_updated",
        value={
            "patron_id": data.patron_id,
            "context_update_count": data.context_update_count,
            "subscription_tier": data.subscription_tier,
        },
        computed_at=datetime.utcnow(),
    )
    db.add(metric)
    await db.flush()

    return {"status": "recorded", "metric_id": str(metric.id)}


@router.post("/game-played")
async def on_game_played(
    data: GamePlayed,
    db: AsyncSession = Depends(get_db),
):
    logger.info("tdac_game_played", patron_id=data.patron_id, game_type=data.game_type)

    tenant = await db.get(Tenant, "00000000-0000-0000-0000-000000000001")
    if not tenant:
        raise HTTPException(status_code=404, detail="TDAC tenant not found")

    metric = TenantMetric(
        tenant_id=tenant.id,
        metric_type="game_played",
        value={
            "patron_id": data.patron_id,
            "game_type": data.game_type,
            "streak": data.streak,
            "score": data.score,
        },
        computed_at=datetime.utcnow(),
    )
    db.add(metric)
    await db.flush()

    return {"status": "recorded", "metric_id": str(metric.id)}


@router.post("/giftcard-redeemed")
async def on_giftcard_redeemed(
    data: GiftCardRedeemed,
    db: AsyncSession = Depends(get_db),
):
    logger.info("tdac_giftcard_redeemed", giftcard_id=data.giftcard_id, patron_id=data.patron_id)

    tenant = await db.get(Tenant, "00000000-0000-0000-0000-000000000001")
    if not tenant:
        raise HTTPException(status_code=404, detail="TDAC tenant not found")

    metric = TenantMetric(
        tenant_id=tenant.id,
        metric_type="giftcard_redeemed",
        value={
            "giftcard_id": data.giftcard_id,
            "patron_id": data.patron_id,
            "destination": data.destination,
        },
        computed_at=datetime.utcnow(),
    )
    db.add(metric)
    await db.flush()

    return {"status": "recorded", "metric_id": str(metric.id)}
