"""
Plugin 1121: HTTP Request Smuggling Detection
===============================================
Detects HTTP Request Smuggling vulnerabilities (CL.TE, TE.CL, TE.TE)
by sending ambiguous Content-Length and Transfer-Encoding headers.
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class RequestSmugglingDetection(NaslPlugin):
    PLUGIN_ID = 1121
    NAME = 'HTTP Request Smuggling Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 8.6
    DESCRIPTION = (
        'Detects HTTP Request Smuggling vulnerabilities (CL.TE, TE.CL, TE.TE) '
        'by sending ambiguous Content-Length and Transfer-Encoding headers. '
        'Request smuggling can bypass security controls, poison caches, and '
        'hijack user sessions, especially when reverse proxies are used.'
    )
    SOLUTION = (
        'Use HTTP/2 which eliminates ambiguity. Ensure consistent HTTP parsing '
        'across proxies and backends. Disable Transfer-Encoding header forwarding.'
    )
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    SMUGGLING_TESTS = [
        {
            'name': 'CL.TE',
            'req': (
                'POST / HTTP/1.1\r\n'
                'Host: {host}\r\n'
                'Content-Length: 13\r\n'
                'Transfer-Encoding: chunked\r\n'
                'Connection: close\r\n\r\n'
                '0\r\n'
                '\r\n'
                'GET /404 HTTP/1.1\r\n'
                'Host: {host}\r\n'
                '\r\n'
            ),
            'indicator': '404',
        },
        {
            'name': 'TE.CL',
            'req': (
                'POST / HTTP/1.1\r\n'
                'Host: {host}\r\n'
                'Content-Length: 3\r\n'
                'Transfer-Encoding: chunked\r\n'
                'Connection: close\r\n\r\n'
                '5e\r\n'
                'POST /404 HTTP/1.1\r\n'
                'Host: {host}\r\n'
                'Content-Length: 15\r\n'
                '\r\n'
                'x=1\r\n'
                '0\r\n'
                '\r\n'
            ),
            'indicator': '404',
        },
        {
            'name': 'TE.TE',
            'req': (
                'POST / HTTP/1.1\r\n'
                'Host: {host}\r\n'
                'Transfer-Encoding: xchunked\r\n'
                'Transfer-Encoding: chunked\r\n'
                'Connection: close\r\n\r\n'
                '0\r\n'
                '\r\n'
                'GET /404 HTTP/1.1\r\n'
                'Host: {host}\r\n'
                '\r\n'
            ),
            'indicator': '404',
        },
    ]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []

        for port_to_check in (self.PORTS if port is None else [port]):
            try:
                scheme = 'https' if port_to_check in (443, 8443) else 'http'
                ctx = None
                if scheme == 'https':
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE

                host_header = target
                if target in ('127.0.0.1', 'localhost', '::1'):
                    host_header = 'alieninc.tech'

                for test in self.SMUGGLING_TESTS:
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(target, port_to_check, ssl=ctx),
                        timeout=5
                    )

                    raw_req = test['req'].format(host=host_header)
                    writer.write(raw_req.encode())
                    await writer.drain()

                    response = b''
                    try:
                        while True:
                            chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                            if not chunk:
                                break
                            response += chunk
                            if len(response) > 16384:
                                break
                    except asyncio.TimeoutError:
                        pass

                    writer.close()
                    await writer.wait_closed()

                    body_text = response.decode('utf-8', errors='ignore')
                    if test['indicator'] in body_text:
                        status_line = body_text.split('\r\n')[0] if '\r\n' in body_text else ''
                        results.append(PluginResult(
                            vulnerable=True,
                            target=target,
                            port=port_to_check,
                            cvss_score=self.CVSS_SCORE,
                            severity='high',
                            description=f'HTTP Request Smuggling detected ({test["name"]})',
                            solution=self.SOLUTION,
                            evidence=f'Smuggling variant: {test["name"]}, response indicated secondary request processing: {status_line}',
                            references=[
                                'https://portswigger.net/web-security/request-smuggling',
                                'https://owasp.org/www-community/attacks/HTTP_Request_Smuggling',
                            ]
                        ))
                        break

                if not results:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=port_to_check,
                        description=f'No request smuggling indicators on port {port_to_check}'
                    ))

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass

        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='No HTTP request smuggling indicators detected on checked ports'
            ))

        return results
