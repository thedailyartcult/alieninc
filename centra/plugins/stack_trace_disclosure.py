"""
Plugin 1129: Stack Trace Disclosure Detection
===============================================
Sends malformed requests to trigger and detect stack trace disclosures.
"""
import asyncio
import json
import ssl

from plugins import NaslPlugin, PluginResult


class StackTraceDisclosure(NaslPlugin):
    PLUGIN_ID = 1129
    NAME = 'Stack Trace Disclosure Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 5.3
    DESCRIPTION = (
        'Detects disclosure of stack traces in error responses by sending '
        'malformed requests that trigger application errors. Full stack traces '
        'reveal internal file paths, class names, library versions, and database '
        'queries — all useful for crafting targeted exploits.'
    )
    SOLUTION = (
        'Configure custom error handlers. Disable debug tracebacks in production. '
        'Never expose internal paths or code structure in error messages.'
    )
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    TRIGGER_PATHS = ['/', '/api/', '/api/v1/', '/api/v1/users', '/login', '/admin']

    STACK_PATTERNS = [
        b'Traceback (most recent call last)',
        b'File "', b'at ', b'in <module>',
        b'Stack trace:', b'Stacktrace:',
        b'#0 ', b'#1 ', b'at com.',
        b'at org.', b'at java.', b'at javax.',
        b'in /var/www', b'in /app', b'in /home',
        b'Warning: ', b'Fatal error: ', b'Parse error: ',
        b'SQLSTATE[', b'PDOException', b' Unexpected',
        b'Undefined variable', b'Undefined index',
        b'Notice: ', b'Deprecated: ',
        b'System.Exception', b' at System.',
        b'in /usr/local', b'Doctrine\\',
        b'Symfony\\', b'Zend_',
        b'on line ', b'called in ',
        b'args = ', b'kwargs = ',
    ]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        ports = self.PORTS if port is None else [port]

        for p in ports:
            try:
                scheme = 'https' if p in (443, 8443) else 'http'
                ctx = None
                if scheme == 'https':
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE

                all_traces = []

                requests = self._build_malformed_requests()
                for method, path, body_bytes in requests:
                    response = await self._send_request(target, p, method, path, body_bytes, ctx)
                    if response:
                        status = response.split(b'\r\n')[0].decode(errors='ignore')
                        _, _, resp_body = response.partition(b'\r\n\r\n')
                        if '200' not in status:
                            matches = [p for p in self.STACK_PATTERNS if p.lower() in resp_body.lower()]
                            if matches:
                                snippet = resp_body[:300].decode(errors='ignore').replace('\n', ' ').strip()
                                all_traces.append(f'{method} {path} -> {matches[0].decode(errors="ignore")[:30]}: {snippet[:80]}')
                                if len(all_traces) >= 5:
                                    break

                if all_traces:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity='medium',
                        description=f'Stack trace disclosure detected: {len(all_traces)} endpoint(s) leak traces',
                        solution=self.SOLUTION,
                        evidence='; '.join(all_traces),
                        references=[
                            'https://owasp.org/www-community/attacks/Stack_Trace_Disclosure',
                            'https://www.tenable.com/plugins/nessus/10656',
                        ]
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        description='No stack trace disclosures detected'
                    ))

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    description=f'Port {p} not reachable'
                ))

        return results

    def _build_malformed_requests(self) -> list[tuple[str, str, bytes]]:
        reqs = []
        for path in self.TRIGGER_PATHS:
            reqs.append(('GET', f'{path}?__debug__=1&__dev__=1', b''))
            reqs.append(('POST', path, b'not-json'))
            reqs.append(('POST', path, b'{"broken": }'))
            reqs.append(('GET', f'{path}?id[]=1&id[]=2', b''))
            reqs.append(('POST', path, json.dumps({"id": "not_an_int"}).encode()))
        return reqs

    async def _send_request(self, target: str, port: int, method: str, path: str,
                            body: bytes, ctx: ssl.SSLContext | None) -> bytes | None:
        try:
            host_header = target
            if target in ('127.0.0.1', 'localhost', '::1'):
                host_header = 'alieninc.tech'

            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port, ssl=ctx), timeout=5
            )

            req = (
                f'{method} {path} HTTP/1.1\r\n'
                f'Host: {host_header}\r\n'
                f'User-Agent: Centra/1.0\r\n'
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
                if len(response) > 32768:
                    break

            writer.close()
            await writer.wait_closed()
            return response

        except Exception:
            return None
