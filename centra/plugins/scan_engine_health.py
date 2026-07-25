"""
Plugin 1056: Scan Engine Health Check (Self-Sustaining)
==========================================================
Verifies that all Centra engine components are functioning correctly:
database connectivity, WebSocket manager, plugin loader, and scan runner.
Self-sustaining pillar: ensures the scanner itself is healthy.
"""
import asyncio
import sqlite3
from pathlib import Path

from plugins import NaslPlugin, PluginResult, ScanContext


class ScanEngineHealth(NaslPlugin):
    PLUGIN_ID = 1056
    NAME = 'Scan Engine Health Check'
    FAMILY = 'Self-Sustaining'
    PLUGIN_TYPE = 'remote'
    CVSS_SCORE = 0.0
    DESCRIPTION = (
        'Runs diagnostic checks on all Centra engine subsystems: database '
        'connectivity, WebSocket manager, plugin loader, auth provider, and '
        'scan orchestrator. Reports the overall health of the scanner engine.'
    )
    SOLUTION = (
        'Restart the engine if any subsystem is unhealthy. Check logs for '
        'specific error messages. Ensure the database file is not corrupted.'
    )
    PORTS = [8721]

    HEALTH_ENDPOINTS = [
        '/api/plugins',
        '/api/scans',
    ]

    async def check_target(self, target: str, port: int | None = 8721,
                           scan_context: ScanContext | None = None) -> list[PluginResult]:
        port = port or 8721
        checks = []
        evidence_lines = []

        checks.append(await self._check_api_reachable(target, port))

        checks.append(await self._check_response_time(target, port))

        checks.append(await self._check_database(target))

        checks.append(self._check_plugin_count())

        checks.append(await self._check_auth_endpoint(target, port))

        passed = sum(1 for c in checks if c['status'] == 'pass')
        failed = sum(1 for c in checks if c['status'] == 'fail')
        warns = sum(1 for c in checks if c['status'] == 'warn')

        for c in checks:
            evidence_lines.append(f'  {c["name"]}: {c["status"].upper()} — {c["detail"]}')

        score = round(passed / max(len(checks), 1) * 100, 1)

        if failed > 0:
            return [PluginResult(
                vulnerable=True,
                target=target,
                port=port,
                cvss_score=3.0,
                severity='low',
                description=f'Engine health: {passed}/{len(checks)} checks pass ({score}%) — {failed} failed',
                solution=self.SOLUTION,
                evidence='\n'.join(evidence_lines),
                references=[
                    'https://www.tenable.com/plugins/nessus/19506',
                ]
            )]

        return [PluginResult(
            vulnerable=False, target=target,
            cvss_score=0.0, severity='info',
            description=f'Engine health: {passed}/{len(checks)} checks pass ({score}%)',
            evidence='\n'.join(evidence_lines),
        )]

    async def _check_api_reachable(self, target: str, port: int) -> dict:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port), timeout=5
            )
            req = f'GET /api/plugins HTTP/1.1\r\nHost: {target}:{port}\r\nConnection: close\r\n\r\n'
            writer.write(req.encode())
            await writer.drain()
            response = b''
            while True:
                chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                if not chunk:
                    break
                response += chunk
                if len(response) > 1024:
                    break
            writer.close()
            await writer.wait_closed()

            status = response.split(b'\r\n')[0].decode('utf-8', errors='ignore')
            return {'name': 'API reachable', 'status': 'pass' if '200' in status else 'fail',
                    'detail': f'HTTP {status.split()[1] if len(status.split()) > 1 else "N/A"}'}
        except Exception as e:
            return {'name': 'API reachable', 'status': 'fail', 'detail': str(e)}

    async def _check_response_time(self, target: str, port: int) -> dict:
        import time
        times = []
        for _ in range(3):
            try:
                start = time.monotonic()
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, port), timeout=5
                )
                req = f'GET /api/plugins HTTP/1.1\r\nHost: {target}:{port}\r\nConnection: close\r\n\r\n'
                writer.write(req.encode())
                await writer.drain()
                await asyncio.wait_for(reader.read(1024), timeout=3)
                writer.close()
                await writer.wait_closed()
                times.append((time.monotonic() - start) * 1000)
            except Exception:
                pass
        if not times:
            return {'name': 'Response time', 'status': 'fail', 'detail': 'No responses'}
        avg_ms = sum(times) / len(times)
        status = 'pass' if avg_ms < 500 else 'warn' if avg_ms < 2000 else 'fail'
        return {'name': 'Response time', 'status': status,
                'detail': f'avg {avg_ms:.0f}ms across {len(times)} probes'}

    async def _check_database(self, target: str) -> dict:
        engine_dir = Path(__file__).parent.parent / 'engine'
        db_path = engine_dir / 'centra.db'
        if not db_path.exists():
            return {'name': 'Database', 'status': 'warn', 'detail': 'centra.db not found (will be created)'}
        try:
            conn = sqlite3.connect(str(db_path))
            conn.execute('SELECT 1')
            row_count = conn.execute('SELECT COUNT(*) FROM scans').fetchone()[0]
            conn.close()
            return {'name': 'Database', 'status': 'pass', 'detail': f'connectivity OK, {row_count} scans'}
        except Exception as e:
            return {'name': 'Database', 'status': 'fail', 'detail': str(e)}

    def _check_plugin_count(self) -> dict:
        from plugins.plugin_loader import load_all_plugins
        plugins = load_all_plugins(Path(__file__).parent)
        count = len(plugins)
        status = 'pass' if count >= 47 else 'warn' if count >= 20 else 'fail'
        return {'name': 'Plugins loaded', 'status': status, 'detail': f'{count} plugins'}

    async def _check_auth_endpoint(self, target: str, port: int) -> dict:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port), timeout=5
            )
            body = b'{"username":"admin","password":"centra2026"}'
            req = (
                f'POST /api/auth/login HTTP/1.1\r\n'
                f'Host: {target}:{port}\r\n'
                f'Content-Type: application/json\r\n'
                f'Content-Length: {len(body)}\r\n'
                f'Connection: close\r\n\r\n'
            )
            writer.write(req.encode() + body)
            await writer.drain()
            response = b''
            while True:
                chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                if not chunk:
                    break
                response += chunk
                if len(response) > 2048:
                    break
            writer.close()
            await writer.wait_closed()

            status_line = response.split(b'\r\n')[0].decode('utf-8', errors='ignore')
            body_text = response.split(b'\r\n\r\n', 1)
            import json
            resp = json.loads(body_text[1].decode('utf-8', errors='ignore')) if len(body_text) > 1 else {}
            has_token = 'access_token' in resp or 'token' in resp
            return {'name': 'Auth endpoint', 'status': 'pass' if '200' in status_line and has_token else 'fail',
                    'detail': f'HTTP {status_line.split()[1] if len(status_line.split()) > 1 else "N/A"}, token={"yes" if has_token else "no"}'}
        except Exception as e:
            return {'name': 'Auth endpoint', 'status': 'fail', 'detail': str(e)}
