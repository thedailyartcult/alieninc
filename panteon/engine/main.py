"""
PANTEON Vulnerability Scanner Engine
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

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger('panteon')

app = FastAPI(title='Panteon Engine', version='1.0.0')

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
manager = ConnectionManager()
plugins = []


class LoginRequest(BaseModel):
    username: str
    password: str


class ScanRequest(BaseModel):
    targets: list[str]
    plugins: list[str] | None = None


class RegisterRequest(BaseModel):
    username: str
    password: str
    display_name: str
    company_id: str


@app.on_event('startup')
async def startup():
    global db, engine, plugins

    db = Database(DATA_DIR / 'panteon.db')
    await db.init()
    set_db(db)

    plugins = load_all_plugins(BASE_DIR.parent / 'plugins')
    logger.info(f'Loaded {len(plugins)} plugins')

    engine = ScanEngine(db, manager, plugins)

    await seed_defaults()
    logger.info('Hawskight Engine started')


async def seed_defaults():
    companies = {
        'alieninc': 'Alien.Inc',
        'rousseau': 'Rousseau',
        'panteon': 'Panteon',
        'exosphere': 'Exosphere',
        'kmt': 'KMT Consulting Group',
        'statute': 'Statute & Precedent',
        'alcantara': 'St. Alcantara Foundation',
        'tdac': 'The Daily Art Cult',
    }
    for cid, name in companies.items():
        await db.ensure_company(cid, name)

    default_users = [
        ('admin', 'panteon2026', 'alieninc', 'System Admin'),
        ('scan.ops', 'scanops2026', 'panteon', 'Scan Operator'),
    ]
    for uname, pw, cid, dname in default_users:
        existing = await db.get_user(uname)
        if not existing:
            hashed = get_password_hash(pw)
            await db.create_user(uname, hashed, cid, dname, 'admin' if uname == 'admin' else 'operator')
            logger.info(f'Created user: {uname} ({cid})')


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
                    await engine.cancel_scan(scan_id, company_id)

    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    except Exception as e:
        logger.error(f'WebSocket error: {e}')
    finally:
        manager.disconnect(websocket)


# ── Static Files ──
# Serve the Panteon frontend and parent site files

PANTEON_DIR = BASE_DIR.parent
SITE_DIR = PANTEON_DIR.parent

app.mount('/panteon/engine', StaticFiles(directory=str(BASE_DIR)), name='engine_internal')
app.mount('/panteon', StaticFiles(directory=str(PANTEON_DIR), html=True), name='panteon')
app.mount('/data', StaticFiles(directory=str(SITE_DIR / 'data')), name='data')
app.mount('/kmt', StaticFiles(directory=str(SITE_DIR / 'kmt')), name='kmt')

# Catch-all: serve root site index
@app.get('/')
async def root():
    return FileResponse(str(SITE_DIR / 'index.html'))


@app.get('/scan')
async def scan_page():
    return FileResponse(str(PANTEON_DIR / 'scan.html'))


@app.get('/login')
async def login_page():
    return FileResponse(str(PANTEON_DIR / 'login.html'))


if __name__ == '__main__':
    import uvicorn
    port = int(os.environ.get('PORT', 8721))
    logger.info(f'Starting Panteon Engine on port {port}')
    uvicorn.run(app, host='0.0.0.0', port=port, log_level='info')
