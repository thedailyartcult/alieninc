"""
CENTRA Vulnerability Scanner Engine
========================================
Nessus-modeled vulnerability management engine for Alien Inc.
Multi-tenant, plugin-based, real-time WebSocket scanning.

Start: python main.py
"""
import os
import sys
import json
import asyncio
import logging
import secrets
from pathlib import Path
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from auth import create_token, decode_token, authenticate_user, get_password_hash, set_db
from database import Database
from engine import ScanEngine
from ws_manager import ConnectionManager
from plugins.plugin_loader import load_all_plugins
from strix_connector import StrixConnector

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger('centra')

app = FastAPI(title='Centra Engine', version='1.0.0')

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / 'data'
DATA_DIR.mkdir(exist_ok=True)

db = None
engine = None
strix = None
manager = ConnectionManager()
plugins = []


class LoginRequest(BaseModel):
    username: str
    password: str


class ScanRequest(BaseModel):
    targets: list[str]
    plugins: list[str] | None = None


class StrixScanRequest(BaseModel):
    targets: list[str]
    scan_mode: str = 'standard'
    instruction: str = ''


class RegisterRequest(BaseModel):
    username: str
    password: str
    display_name: str
    company_id: str


@app.on_event('startup')
async def startup():
    global db, engine, strix, plugins

    db = Database(DATA_DIR / 'centra.db')
    await db.init()
    set_db(db)

    plugins = load_all_plugins(BASE_DIR.parent / 'plugins')
    logger.info(f'Loaded {len(plugins)} plugins')

    engine = ScanEngine(db, manager, plugins)
    strix = StrixConnector(db, manager)
    strix_health = strix.health()
    logger.info(f'Red Team connector: {strix_health["message"]}')

    await seed_defaults()
    logger.info('Hawskight Engine started')


async def seed_defaults():
    companies = {
        'alieninc': 'Alien.Inc',
        'rousseau': 'Rousseau',
        'centra': 'Centra',
        'kmt': 'KMT Consulting Group',
        'tdac': 'The Daily Art Cult',
    }
    for cid, name in companies.items():
        await db.ensure_company(cid, name)

    default_users = [
        ('admin', 'alieninc', 'System Admin'),
        ('scan.ops', 'centra', 'Scan Operator'),
    ]
    for uname, cid, dname in default_users:
        existing = await db.get_user(uname)
        if not existing:
            pw = secrets.token_urlsafe(18)
            hashed = get_password_hash(pw)
            await db.create_user(uname, hashed, cid, dname, 'admin' if uname == 'admin' else 'operator')
            logger.info(f'Created user: {uname} ({cid}) — one-time password: {pw}')


# ── Auth Routes ──

@app.post('/api/auth/login')
async def login(req: LoginRequest):
    user = await authenticate_user(req.username, req.password)
    if not user:
        raise HTTPException(status_code=401, detail='Invalid credentials')
    token = create_token(user['id'], user['username'], user['company_id'], user['role'])
    return {
        'token': token,
        'user': {
            'id': user['id'],
            'username': user['username'],
            'company_id': user['company_id'],
            'display_name': user['display_name'],
            'role': user['role'],
        }
    }


@app.post('/api/auth/register')
async def register(req: RegisterRequest):
    existing = await db.get_user(req.username)
    if existing:
        raise HTTPException(status_code=409, detail='Username taken')
    hashed = get_password_hash(req.password)
    uid = await db.create_user(req.username, hashed, req.company_id, req.display_name, 'operator')
    token = create_token(uid, req.username, req.company_id, 'operator')
    return {'token': token, 'user': {'id': uid, 'username': req.username, 'company_id': req.company_id}}


@app.get('/api/auth/me')
async def get_me(request: Request):
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        raise HTTPException(status_code=401, detail='Missing token')
    payload = decode_token(auth[7:])
    if not payload:
        raise HTTPException(status_code=401, detail='Invalid token')
    user = await db.get_user_by_id(payload['user_id'])
    if not user:
        raise HTTPException(status_code=401, detail='User not found')
    return {'user': user}


# ── Company Routes ──

@app.get('/api/companies')
async def list_companies():
    return await db.get_companies()


@app.get('/api/companies/{company_id}/targets')
async def get_targets(company_id: str):
    targets = await db.get_targets(company_id)
    return targets


# ── Plugin Routes ──

@app.get('/api/plugins')
async def list_plugins():
    return [
        {
            'id': p.PLUGIN_ID, 'name': p.NAME, 'family': p.FAMILY,
            'cvss': p.CVSS_SCORE, 'cve': getattr(p, 'CVE', []),
            'description': p.DESCRIPTION
        }
        for p in plugins
    ]


# ── Scan Routes ──

@app.post('/api/scans')
async def start_scan(req: ScanRequest, request: Request):
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        raise HTTPException(status_code=401, detail='Missing token')
    payload = decode_token(auth[7:])
    if not payload:
        raise HTTPException(status_code=401, detail='Invalid token')

    company_id = payload['company_id']
    user_id = payload['user_id']
    username = payload['username']

    scan_id = await db.create_scan(company_id, user_id, req.targets)
    asyncio.create_task(engine.run_scan(scan_id, company_id, user_id, req.targets, req.plugins))

    return {'scan_id': scan_id, 'status': 'started'}


@app.get('/api/scans')
async def list_scans(request: Request):
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        raise HTTPException(status_code=401, detail='Missing token')
    payload = decode_token(auth[7:])
    if not payload:
        raise HTTPException(status_code=401, detail='Invalid token')
    return await db.get_scans(payload['company_id'])


@app.get('/api/scans/{scan_id}')
async def get_scan(scan_id: str, request: Request):
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        raise HTTPException(status_code=401, detail='Missing token')
    payload = decode_token(auth[7:])
    if not payload:
        raise HTTPException(status_code=401, detail='Invalid token')
    scan = await db.get_scan(scan_id, payload['company_id'])
    if not scan:
        raise HTTPException(status_code=404, detail='Scan not found')
    findings = await db.get_findings(scan_id)
    return {'scan': scan, 'findings': findings}


@app.delete('/api/scans/{scan_id}')
async def delete_scan(scan_id: str, request: Request):
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        raise HTTPException(status_code=401, detail='Missing token')
    payload = decode_token(auth[7:])
    if not payload:
        raise HTTPException(status_code=401, detail='Invalid token')
    await db.delete_scan(scan_id, payload['company_id'])
    return {'deleted': True}


@app.get('/api/stats/{company_id}')
async def get_stats(company_id: str):
    return await db.get_stats(company_id)


# ── Strix AI Pentest Routes ──

def _strix_auth(request: Request) -> tuple[str, int]:
    """Dual-path auth: Centra JWT first, then fall back to X-Company-Id header.

    The Centra portal login (login.html) stores a Supabase access_token in
    hs_session; the engine issues its own JWTs via /api/auth/login. This helper
    accepts either: a valid Centra Bearer token, or an X-Company-Id header so
    the existing portal session can drive red-team scans without a separate login.
    """
    auth = request.headers.get('Authorization', '')
    if auth.startswith('Bearer '):
        payload = decode_token(auth[7:])
        if payload:
            return payload['company_id'], payload['user_id']
    cid = request.headers.get('X-Company-Id', 'alieninc')
    return cid, 0


def _sanitize_health(h: dict) -> dict:
    """Strip tool-identifying details from the health response.
    Exposes only Centra-branded status — never the underlying engine name,
    version, or install path."""
    return {
        'engine_online': h['ready'],
        'docker_available': h['docker_available'],
        'llm_configured': h['llm_configured'],
        'reasoning_effort': h['reasoning_effort'],
        'free_ram_mb': h['free_ram_mb'],
        'ready': h['ready'],
        'message': 'Autonomous Red Team engine ready' if h['ready'] else 'Engine initializing — configuration pending',
    }


@app.get('/api/redteam/health')
async def redteam_health(request: Request):
    _strix_auth(request)
    return _sanitize_health(strix.health())


@app.post('/api/redteam/scans')
async def start_redteam_scan(req: StrixScanRequest, request: Request):
    company_id, user_id = _strix_auth(request)
    if not req.targets:
        raise HTTPException(status_code=400, detail='At least one target is required')

    h = strix.health()
    if not h['ready']:
        raise HTTPException(status_code=503, detail='Red Team engine not ready')

    scan_id = await db.create_strix_scan(
        company_id, user_id, req.targets, req.scan_mode, req.instruction
    )
    asyncio.create_task(strix.run_scan(
        scan_id, company_id, user_id, req.targets, req.scan_mode, req.instruction
    ))
    return {'scan_id': scan_id, 'status': 'started', 'targets': req.targets, 'scan_mode': req.scan_mode}


@app.get('/api/redteam/scans')
async def list_redteam_scans(request: Request):
    company_id, _ = _strix_auth(request)
    return await db.get_strix_scans(company_id)


@app.get('/api/redteam/stats')
async def get_redteam_stats(request: Request):
    company_id, _ = _strix_auth(request)
    return await db.get_strix_stats(company_id)


@app.get('/api/redteam/scans/{scan_id}')
async def get_redteam_scan(scan_id: str, request: Request):
    company_id, _ = _strix_auth(request)
    scan = await db.get_strix_scan(scan_id, company_id)
    if not scan:
        raise HTTPException(status_code=404, detail='Scan not found')
    findings = await db.get_strix_findings(scan_id)
    return {'scan': scan, 'findings': findings}


@app.delete('/api/redteam/scans/{scan_id}')
async def delete_redteam_scan(scan_id: str, request: Request):
    company_id, _ = _strix_auth(request)
    await strix.cancel_scan(scan_id, company_id)
    await db.delete_strix_scan(scan_id, company_id)
    return {'deleted': True}


# ── WebSocket ──

@app.websocket('/ws/scan')
async def ws_scan(websocket: WebSocket):
    await websocket.accept()

    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=10.0)
        msg = json.loads(raw)
        if msg.get('type') != 'auth' or not msg.get('token'):
            await websocket.close(code=4001, reason='Auth required')
            return

        payload = decode_token(msg['token'])
        if not payload:
            await websocket.close(code=4001, reason='Invalid token')
            return

        user_id = payload['user_id']
        company_id = payload['company_id']
        username = payload['username']

        await manager.connect(websocket, company_id, user_id)
        await websocket.send_text(json.dumps({
            'type': 'authenticated',
            'company_id': company_id,
            'username': username,
        }))

        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)

            if msg.get('type') == 'subscribe_scan':
                scan_id = msg.get('scan_id')
                if scan_id:
                    manager.subscribe(scan_id, company_id, user_id)
                    scan = await db.get_scan(scan_id, company_id)
                    if scan:
                        await websocket.send_text(json.dumps({
                            'type': 'scan_state',
                            'scan_id': scan_id,
                            'status': scan['status'],
                            'progress': scan['progress'],
                        }))

            elif msg.get('type') == 'cancel_scan':
                scan_id = msg.get('scan_id')
                if scan_id:
                    if scan_id.startswith('SX-'):
                        await strix.cancel_scan(scan_id, company_id)
                    else:
                        await engine.cancel_scan(scan_id, company_id)

    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    except Exception as e:
        logger.error(f'WebSocket error: {e}')
    finally:
        manager.disconnect(websocket)


# ── Static Files ──
# Serve the Centra frontend and parent site files

CENTRA_DIR = BASE_DIR.parent
SITE_DIR = CENTRA_DIR.parent

app.mount('/centra', StaticFiles(directory=str(CENTRA_DIR), html=True), name='centra')
app.mount('/data', StaticFiles(directory=str(SITE_DIR / 'data')), name='data')

# Catch-all: serve root site index
@app.get('/')
async def root():
    return FileResponse(str(SITE_DIR / 'index.html'))


@app.get('/scan')
async def scan_page():
    return FileResponse(str(CENTRA_DIR / 'scan.html'))


@app.get('/red-team')
async def redteam_page():
    return FileResponse(str(CENTRA_DIR / 'strix.html'))


@app.get('/login')
async def login_page():
    return FileResponse(str(CENTRA_DIR / 'login.html'))


if __name__ == '__main__':
    import uvicorn
    port = int(os.environ.get('PORT', 8721))
    logger.info(f'Starting Centra Engine on port {port}')
    uvicorn.run(app, host='127.0.0.1', port=port, log_level='info')
