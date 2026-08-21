from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import httpx

from panteon.core.database import get_db
from panteon.core.auth import get_current_user
from panteon.yono.models import LLMProvider
from panteon.yono.secrets import decrypt_secret
from panteon.statham.models import SmmLink, SmmOrder

router = APIRouter(prefix="/smm", tags=["SMM Panel"], dependencies=[Depends(get_current_user)])

NAIZOP_BASE = "https://naizop.com/api/v2"


async def _get_naizop_key(db: AsyncSession) -> str:
    result = await db.execute(
        select(LLMProvider).where(LLMProvider.provider_type == "smm_panel", LLMProvider.is_enabled == True)
    )
    provider = result.scalar_one_or_none()
    if not provider or not provider.api_key_encrypted:
        raise HTTPException(status_code=400, detail="Naizop provider not configured in YONO")
    return decrypt_secret(provider.api_key_encrypted)


async def _naizop_call(action: str, api_key: str, extra: dict = None) -> dict:
    data = {"action": action, "key": api_key}
    if extra:
        data.update(extra)
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(NAIZOP_BASE, data=data)
        return resp.json()


async def _lookup_service_info(api_key: str, service_id: int) -> dict:
    resp = await _naizop_call("services", api_key)
    services = resp if isinstance(resp, list) else resp.get("services", [])
    for s in services:
        if str(s.get("service")) == str(service_id):
            return {"name": s.get("name", ""), "rate": float(s.get("rate", 0))}
    return {"name": "", "rate": 0}


class SMMOrderRequest(BaseModel):
    service: int
    link: str
    quantity: Optional[int] = None
    runs: Optional[int] = None
    interval: Optional[int] = None
    comments: Optional[list[str]] = None
    username: Optional[str] = None
    post: Optional[str] = None
    min: Optional[int] = None
    max: Optional[int] = None
    media_urls: Optional[list[str]] = None
    hashtag: Optional[str] = None
    hashtag_spacing: Optional[bool] = None
    user_pk: Optional[int] = None
    bulk: Optional[bool] = None
    drip_feed: Optional[bool] = None
    username_photo_url: Optional[str] = None
    expire_type: Optional[str] = None
    amount: Optional[int] = None


class SMMBulkOrderRequest(BaseModel):
    orders: list[SMMOrderRequest]


class SMMRefillRequest(BaseModel):
    order: int


class SMMRefillStatusRequest(BaseModel):
    order: int


class SMMCancelRequest(BaseModel):
    order: int


class SmmLinkCreate(BaseModel):
    platform: str
    url: str
    label: Optional[str] = None
    username: Optional[str] = None
    notes: Optional[str] = None


class SmmLinkUpdate(BaseModel):
    platform: Optional[str] = None
    url: Optional[str] = None
    label: Optional[str] = None
    username: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class SmmOrderCreate(BaseModel):
    link_id: str
    service: int
    quantity: Optional[int] = None
    runs: Optional[int] = None
    interval: Optional[int] = None
    comments: Optional[list[str]] = None


class SmmConfirmRequest(BaseModel):
    confirmed_by: str = "admin"
    notes: Optional[str] = None


@router.get("/balance")
async def get_balance(db: AsyncSession = Depends(get_db)):
    api_key = await _get_naizop_key(db)
    return await _naizop_call("balance", api_key)


@router.get("/services")
async def get_services(db: AsyncSession = Depends(get_db)):
    api_key = await _get_naizop_key(db)
    return await _naizop_call("services", api_key)


@router.post("/order")
async def create_order(data: SMMOrderRequest, db: AsyncSession = Depends(get_db)):
    api_key = await _get_naizop_key(db)
    params = {"service": data.service, "link": data.link}
    if data.quantity is not None:
        params["quantity"] = str(data.quantity)
    if data.runs is not None:
        params["runs"] = str(data.runs)
    if data.interval is not None:
        params["interval"] = str(data.interval)
    if data.comments is not None:
        params["comments"] = "\n".join(data.comments)
    if data.username is not None:
        params["username"] = data.username
    if data.post is not None:
        params["post"] = data.post
    if data.min is not None:
        params["min"] = str(data.min)
    if data.max is not None:
        params["max"] = str(data.max)
    if data.media_urls is not None:
        params["media_urls"] = "\n".join(data.media_urls)
    if data.hashtag is not None:
        params["hashtag"] = data.hashtag
    if data.hashtag_spacing is not None:
        params["hashtag_spacing"] = str(data.hashtag_spacing).lower()
    if data.user_pk is not None:
        params["user_pk"] = str(data.user_pk)
    if data.bulk is not None:
        params["bulk"] = str(data.bulk).lower()
    if data.drip_feed is not None:
        params["drip_feed"] = str(data.drip_feed).lower()
    if data.username_photo_url is not None:
        params["username_photo_url"] = data.username_photo_url
    if data.expire_type is not None:
        params["expire_type"] = data.expire_type
    if data.amount is not None:
        params["amount"] = str(data.amount)
    return await _naizop_call("add", api_key, params)


@router.get("/status/{order_id}")
async def get_order_status(order_id: int, db: AsyncSession = Depends(get_db)):
    api_key = await _get_naizop_key(db)
    return await _naizop_call("status", api_key, {"order": str(order_id)})


@router.get("/status")
async def get_multiple_status(orders: str = Query(..., description="Comma-separated order IDs"), db: AsyncSession = Depends(get_db)):
    api_key = await _get_naizop_key(db)
    return await _naizop_call("status", api_key, {"orders": orders})


@router.post("/refill")
async def refill_order(data: SMMRefillRequest, db: AsyncSession = Depends(get_db)):
    api_key = await _get_naizop_key(db)
    return await _naizop_call("refill", api_key, {"order": str(data.order)})


@router.get("/refill-status/{order_id}")
async def get_refill_status(order_id: int, db: AsyncSession = Depends(get_db)):
    api_key = await _get_naizop_key(db)
    return await _naizop_call("refill_status", api_key, {"order": str(order_id)})


@router.post("/cancel")
async def cancel_order(data: SMMCancelRequest, db: AsyncSession = Depends(get_db)):
    api_key = await _get_naizop_key(db)
    return await _naizop_call("cancel", api_key, {"order": str(data.order)})


@router.post("/mass-order")
async def mass_order(data: SMMBulkOrderRequest, db: AsyncSession = Depends(get_db)):
    api_key = await _get_naizop_key(db)
    lines = []
    for o in data.orders:
        parts = [str(o.service), o.link]
        if o.quantity is not None:
            parts.append(str(o.quantity))
        lines.append(" ".join(parts))
    return await _naizop_call("massorders", api_key, {"orders": "\n".join(lines)})


@router.post("/links")
async def create_link(data: SmmLinkCreate, db: AsyncSession = Depends(get_db)):
    link = SmmLink(
        platform=data.platform, url=data.url,
        label=data.label, username=data.username, notes=data.notes,
    )
    db.add(link)
    await db.flush()
    return {"id": link.id, "platform": link.platform, "url": link.url, "label": link.label, "username": link.username, "status": link.status, "created_at": str(link.created_at)}


@router.get("/links")
async def list_links(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SmmLink).order_by(SmmLink.created_at.desc()))
    links = result.scalars().all()
    out = []
    for l in links:
        order_count = (await db.execute(select(SmmOrder).where(SmmOrder.link_id == l.id))).scalars().all()
        total_cost = sum(o.cost for o in order_count)
        confirmed_count = sum(1 for o in order_count if o.confirmed)
        out.append({
            "id": l.id, "platform": l.platform, "url": l.url, "label": l.label,
            "username": l.username, "status": l.status, "notes": l.notes,
            "created_at": str(l.created_at),
            "order_count": len(order_count), "total_cost": round(total_cost, 4),
            "confirmed_count": confirmed_count,
        })
    return out


@router.patch("/links/{link_id}")
async def update_link(link_id: str, data: SmmLinkUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SmmLink).where(SmmLink.id == link_id))
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    for field, val in data.model_dump(exclude_unset=True).items():
        setattr(link, field, val)
    await db.flush()
    return {"id": link.id, "platform": link.platform, "url": link.url, "label": link.label, "status": link.status}


@router.post("/orders")
async def create_tracked_order(data: SmmOrderCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SmmLink).where(SmmLink.id == data.link_id))
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    api_key = await _get_naizop_key(db)
    params = {"service": str(data.service), "link": link.url}
    if data.quantity is not None:
        params["quantity"] = str(data.quantity)
    if data.runs is not None:
        params["runs"] = str(data.runs)
    if data.interval is not None:
        params["interval"] = str(data.interval)
    if data.comments is not None:
        params["comments"] = "\n".join(data.comments)
    naizop_resp = await _naizop_call("add", api_key, params)
    naizop_order_id = naizop_resp.get("order")
    svc_info = await _lookup_service_info(api_key, data.service)
    qty = data.quantity or 0
    order = SmmOrder(
        link_id=data.link_id,
        naizop_order_id=naizop_order_id,
        service_id=data.service,
        service_name=svc_info["name"],
        quantity=qty,
        cost=round(svc_info["rate"] * qty / 1000, 4) if svc_info["rate"] and qty else 0,
        naizop_status="Processing",
    )
    db.add(order)
    await db.flush()
    return {"id": order.id, "naizop_order_id": naizop_order_id, "link_id": data.link_id, "status": "pending"}


@router.get("/orders")
async def list_orders(link_id: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    q = select(SmmOrder).order_by(SmmOrder.created_at.desc())
    if link_id:
        q = q.where(SmmOrder.link_id == link_id)
    result = await db.execute(q)
    orders = result.scalars().all()
    return [{
        "id": o.id, "link_id": o.link_id, "naizop_order_id": o.naizop_order_id,
        "service_id": o.service_id, "service_name": o.service_name, "quantity": o.quantity,
        "cost": o.cost, "naizop_status": o.naizop_status,
        "confirmed": o.confirmed, "confirmed_by": o.confirmed_by,
        "confirmed_at": str(o.confirmed_at) if o.confirmed_at else None,
        "notes": o.notes, "placed_at": str(o.placed_at),
    } for o in orders]


@router.post("/orders/{order_id}/sync")
async def sync_order_status(order_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SmmOrder).where(SmmOrder.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if not order.naizop_order_id:
        raise HTTPException(status_code=400, detail="No Naizop order ID")
    api_key = await _get_naizop_key(db)
    naizop_resp = await _naizop_call("status", api_key, {"order": str(order.naizop_order_id)})
    raw_status = naizop_resp.get("status") if isinstance(naizop_resp, dict) else str(naizop_resp)
    order.naizop_status = raw_status
    await db.flush()
    return {"id": order.id, "naizop_order_id": order.naizop_order_id, "naizop_status": raw_status}


@router.post("/orders/{order_id}/confirm")
async def confirm_order(order_id: str, data: SmmConfirmRequest, db: AsyncSession = Depends(get_db)):
    from datetime import datetime
    result = await db.execute(select(SmmOrder).where(SmmOrder.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    order.confirmed = True
    order.confirmed_by = data.confirmed_by
    order.confirmed_at = datetime.utcnow()
    if data.notes:
        order.notes = data.notes
    await db.flush()
    return {"id": order.id, "confirmed": True, "confirmed_by": order.confirmed_by, "confirmed_at": str(order.confirmed_at)}


@router.post("/orders/sync-all")
async def sync_all_orders(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SmmOrder).where(SmmOrder.naizop_status.notin_(["Completed", "Canceled"]))
    )
    orders = result.scalars().all()
    if not orders:
        return {"synced": 0}
    api_key = await _get_naizop_key(db)
    order_ids = [str(o.naizop_order_id) for o in orders if o.naizop_order_id]
    if not order_ids:
        return {"synced": 0}
    bulk_resp = await _naizop_call("status", api_key, {"orders": ",".join(order_ids)})
    status_map = {}
    if isinstance(bulk_resp, list):
        for item in bulk_resp:
            oid = str(item.get("order", ""))
            status_map[oid] = item.get("charge", 0), item.get("status", "")
    synced = 0
    for o in orders:
        oid = str(o.naizop_order_id)
        if oid in status_map:
            charge, status = status_map[oid]
            o.naizop_status = status
            if charge and charge > 0:
                o.cost = float(charge)
            synced += 1
    await db.flush()
    return {"synced": synced}


@router.delete("/links/{link_id}")
async def delete_link(link_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SmmLink).where(SmmLink.id == link_id))
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    order_count = (await db.execute(select(SmmOrder).where(SmmOrder.link_id == link_id))).scalars().all()
    for o in order_count:
        await db.delete(o)
    await db.delete(link)
    await db.flush()
    return {"deleted": True, "id": link_id, "orders_removed": len(order_count)}
