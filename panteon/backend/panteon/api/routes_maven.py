"""
MAVEN Smart Layer routes — Palantir-Maven-style tasking over the Spinal
Cracker ontology + sims gateway. All writes are real ontology objects and
action executions; COA scores come from real kriegsimulation runs.

The AIS relay (WS /maven/ais/ws) keeps the AISStream.io key SERVER-SIDE:
browsers connect to us token-authenticated; we inject the key upstream.
"""
import asyncio
import json
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from panteon.core.auth import SupabaseUser, get_current_user, verify_supabase_token
from panteon.core.database import get_db
from panteon.maven import (
    ASSET_CLASSES,
    create_object,
    create_task,
    delete_object,
    delete_task,
    dispatch_asset,
    generate_coas,
    maven_state,
    prune_detections,
    recall_asset,
    rename_object,
    auto_task,
    maven_command,
    tick_and_collect,
    execute_target_coa,
    generate_target_coa,
    validate_detection,
)

router = APIRouter(prefix="/maven", tags=["MAVEN Smart Layer"])

ROLE_LEVELS = {"viewer": 0, "editor": 1, "admin": 2, "superadmin": 3}


def _require_editor(user: SupabaseUser) -> None:
    if ROLE_LEVELS.get(user.role, 0) < ROLE_LEVELS["editor"]:
        raise HTTPException(status_code=403,
                            detail="Editor role required for MAVEN tasking")


async def _body(request: Request) -> dict:
    try:
        data = await request.json()
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


@router.get("/state")
async def get_maven_state(user: SupabaseUser = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    """Assets (dead-reckoned), tasks, recent detections, COAs."""
    try:
        return await maven_state(db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/task")
async def post_task(request: Request,
                    user: SupabaseUser = Depends(get_current_user),
                    db: AsyncSession = Depends(get_db)):
    _require_editor(user)
    body = await _body(request)
    try:
        return await create_task(db, body, user.email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/task/{task_id}/dispatch")
async def post_dispatch(task_id: str, request: Request,
                        user: SupabaseUser = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    _require_editor(user)
    body = await _body(request)
    try:
        return await dispatch_asset(db, task_id,
                                    asset_class=str(body.get("asset_class") or "uas"),
                                    executed_by=user.email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/task/{task_id}")
async def delete_task_route(task_id: str,
                            user: SupabaseUser = Depends(get_current_user),
                            db: AsyncSession = Depends(get_db)):
    """Delete a task with its live assets, detections and links."""
    _require_editor(user)
    try:
        return await delete_task(db, task_id, user.email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/asset/{callsign}/recall")
async def recall_asset_route(callsign: str,
                             user: SupabaseUser = Depends(get_current_user),
                             db: AsyncSession = Depends(get_db)):
    """Stand down one asset (removes it from the board and the ontology)."""
    _require_editor(user)
    try:
        return await recall_asset(db, callsign, user.email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/detection/{detection_id}/validate")
async def post_validate(detection_id: str, request: Request,
                        user: SupabaseUser = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    _require_editor(user)
    body = await _body(request)
    verdict = body.get("verdict")
    if not isinstance(verdict, bool):
        raise HTTPException(status_code=400, detail="verdict must be boolean")
    try:
        return await validate_detection(db, detection_id, verdict, user.email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/object")
async def post_object(request: Request,
                      user: SupabaseUser = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    """Register a named map object (building footprint or point)."""
    _require_editor(user)
    body = await _body(request)
    try:
        return await create_object(db, body, user.email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/object/{object_id}/rename")
async def post_object_rename(object_id: str, request: Request,
                             user: SupabaseUser = Depends(get_current_user),
                             db: AsyncSession = Depends(get_db)):
    _require_editor(user)
    body = await _body(request)
    try:
        return await rename_object(db, object_id, str(body.get("name") or ""))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/object/{object_id}")
async def delete_object_route(object_id: str,
                              user: SupabaseUser = Depends(get_current_user),
                              db: AsyncSession = Depends(get_db)):
    _require_editor(user)
    try:
        return await delete_object(db, object_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/command")
async def post_maven_command(request: Request,
                             user: SupabaseUser = Depends(get_current_user),
                             db: AsyncSession = Depends(get_db)):
    """Natural-language MAVEN bridge for YONO/chat: {\"text\": \"task on <object>\"}."""
    _require_editor(user)
    body = await _body(request)
    try:
        return await maven_command(db, body, user.email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/auto")
async def post_auto_task(request: Request,
                         user: SupabaseUser = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    """One-shot automated mission for YONO/chat automation.

    Body: {"object_id": "<mv-obj uuid>"} OR {"lat": .., "lng": ..},
    optional name, priority (low|medium|high), radius_km, asset_class (uas|usv).
    Creates the task AND dispatches an asset in one call.
    YONO example: curl -X POST .../api/v1/maven/auto -H 'auth' -d '{"object_id":"..."}'
    """
    _require_editor(user)
    body = await _body(request)
    try:
        return await auto_task(db, body, user.email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/coa/target/generate")
async def post_coa_target_generate(request: Request,
                                   user: SupabaseUser = Depends(get_current_user),
                                   db: AsyncSession = Depends(get_db)):
    """Phase-2: generate packaged COAs for one CONFIRMED detection."""
    _require_editor(user)
    body = await _body(request)
    try:
        return await generate_target_coa(db, body, user.email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/coa/target/{coa_id}/execute")
async def post_coa_target_execute(coa_id: str, request: Request,
                                  user: SupabaseUser = Depends(get_current_user),
                                  db: AsyncSession = Depends(get_db)):
    """Phase-3: execute the selected option and stamp the audit trail."""
    _require_editor(user)
    body = await _body(request)
    try:
        return await execute_target_coa(db, coa_id, str(body.get("option") or ""),
                                        user.email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/coa/generate")
async def post_coa_generate(request: Request,
                            user: SupabaseUser = Depends(get_current_user),
                            db: AsyncSession = Depends(get_db)):
    _require_editor(user)
    body = await _body(request)
    try:
        return await generate_coas(db, body, user.email)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/tick")
async def post_tick(user: SupabaseUser = Depends(get_current_user),
                    db: AsyncSession = Depends(get_db)):
    """Advance assets + collect detections against REAL feed tracks."""
    import time as _t, logging
    _log = logging.getLogger("panteon.maven")
    t0 = _t.monotonic()
    try:
        out = await tick_and_collect(db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    dt_ms = round((_t.monotonic() - t0) * 1000, 1)
    _log.info("tick duration_ms=%s assets=%s tracks_scanned=%s new_dets=%s",
              dt_ms, out.get("synced_assets"), out.get("tracks_scanned"),
              out.get("new_detections"))
    out["tick_ms"] = dt_ms
    return out


@router.post("/prune")
async def post_prune(request: Request,
                     user: SupabaseUser = Depends(get_current_user),
                     db: AsyncSession = Depends(get_db)):
    if ROLE_LEVELS.get(user.role, 0) < ROLE_LEVELS["admin"]:
        raise HTTPException(status_code=403, detail="Admin role required for pruning")
    body = await _body(request)
    return await prune_detections(db, ttl_days=int(body.get("ttl_days") or 14))


@router.get("/meta")
async def maven_meta(user: SupabaseUser = Depends(get_current_user)):
    """Static capability metadata for the UI (asset classes, radii, pacing)."""
    from panteon.maven import SIM_SPEEDUP
    return {"asset_classes": {
        k: {kk: vv for kk, vv in v.items()} for k, v in ASSET_CLASSES.items()
    }, "sim_speedup": SIM_SPEEDUP, "version": "m2"}


# --------------------------------------------------------------------------
# AIS relay — server-held AISStream.io key (never exposed to browsers)
# --------------------------------------------------------------------------

AIS_UPSTREAM = "wss://stream.aisstream.io/v0/stream"
logger = logging.getLogger("panteon.maven.ais")


@router.websocket("/ais/ws")
async def ais_relay(ws: WebSocket, token: str = ""):
    """Token-authenticated browser WS -> authenticated AISStream.io upstream.

    Client sends ONE subscribe message {BoundingBoxes:[[...]]} WITHOUT any
    key; the relay injects AISSTREAM_API_KEY from the server environment.
    """
    user = await verify_supabase_token(token) if token else None
    if user is None:
        await ws.close(code=4401)
        return
    await ws.accept()
    key = os.environ.get("AISSTREAM_API_KEY", "")
    if not key:
        try:
            await ws.send_text(json.dumps(
                {"error": "server has no AISSTREAM_API_KEY configured"}))
        except Exception:
            pass
        await ws.close(code=4400)
        return

    import websockets

    async def _fwd_in(up):
        # Client -> upstream: bbox re-subscribes; strip any client-sent key.
        while True:
            msg = await ws.receive_text()
            try:
                data = json.loads(msg)
                data.pop("APIKey", None)
                msg = json.dumps(data)
            except (json.JSONDecodeError, TypeError):
                pass
            await up.send(msg)

    try:
        subscribe = await ws.receive_text()
        sub_data = json.loads(subscribe) if subscribe else {}
    except WebSocketDisconnect:
        return
    sub_data.pop("APIKey", None)

    async def _fwd_out(up):
        async for message in up:
            await ws.send_text(message if isinstance(message, str)
                               else message.decode("utf-8", "replace"))

    async def _run(up):
        await up.send(json.dumps(sub_data))
        tasks = [asyncio.create_task(_fwd_in(up)),
                 asyncio.create_task(_fwd_out(up))]
        done, pending = await asyncio.wait(tasks,
                                           return_when=asyncio.FIRST_EXCEPTION)
        for t in pending:
            t.cancel()
        for t in done:
            exc = t.exception()
            if exc and not isinstance(exc, (WebSocketDisconnect,
                                            asyncio.CancelledError)):
                logger.info("ais relay ended: %s", exc)

    try:
        async with websockets.connect(AIS_UPSTREAM, open_timeout=15,
                                      ping_interval=20) as up:
            await _run(up)
    except (websockets.exceptions.WebSocketException, OSError, asyncio.TimeoutError) as exc:
        logger.warning("ais upstream unavailable: %s", exc)
        try:
            await ws.send_text(json.dumps({"error": f"ais upstream unreachable: {exc}"}))
            await ws.close(code=1011)
        except Exception:
            pass
    finally:
        try:
            await ws.close()
        except Exception:
            pass

