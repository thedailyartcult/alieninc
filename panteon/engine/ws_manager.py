"""WebSocket connection manager with multi-tenant isolation."""
import json
import logging
from fastapi import WebSocket

logger = logging.getLogger('panteon.ws')


class ConnectionManager:
    def __init__(self):
        self._connections: dict[str, dict[int, list[WebSocket]]] = {}
        self._subscriptions: dict[str, set[tuple[str, int]]] = {}

    async def connect(self, ws: WebSocket, company_id: str, user_id: int):
        if company_id not in self._connections:
            self._connections[company_id] = {}
        if user_id not in self._connections[company_id]:
            self._connections[company_id][user_id] = []
        self._connections[company_id][user_id].append(ws)
        logger.info(f'WS connected: company={company_id} user={user_id}')

    def disconnect(self, ws: WebSocket):
        for cid in list(self._connections.keys()):
            for uid in list(self._connections[cid].keys()):
                if ws in self._connections[cid][uid]:
                    self._connections[cid][uid].remove(ws)
                    if not self._connections[cid][uid]:
                        del self._connections[cid][uid]
                    if not self._connections[cid]:
                        del self._connections[cid]
                    return

    def subscribe(self, scan_id: str, company_id: str, user_id: int):
        if scan_id not in self._subscriptions:
            self._subscriptions[scan_id] = set()
        self._subscriptions[scan_id].add((company_id, user_id))

    async def send_to_scan(self, scan_id: str, message: dict):
        listeners = self._subscriptions.get(scan_id, set())
        targets = []
        for cid, uid in listeners:
            user_conns = self._connections.get(cid, {}).get(uid, [])
            for ws in user_conns:
                targets.append((ws, cid))

        for ws, cid in targets:
            try:
                await ws.send_text(json.dumps(message))
            except Exception:
                pass

    async def broadcast_to_company(self, company_id: str, message: dict):
        users = self._connections.get(company_id, {})
        for uid, conns in users.items():
            for ws in conns:
                try:
                    await ws.send_text(json.dumps(message))
                except Exception:
                    pass

    def get_company_connections(self, company_id: str) -> int:
        return sum(len(v) for v in self._connections.get(company_id, {}).values())
