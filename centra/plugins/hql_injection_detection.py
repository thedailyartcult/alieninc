"""
Plugin 1227: Hibernate Query Language (HQL) Injection Detection
=================================================================
Detects Hibernate Query Language (HQL) injection vulnerabilities by
injecting HQL metacharacters and logical operators.
"""
import asyncio
import ssl
import urllib.parse

from plugins import NaslPlugin, PluginResult


class HqlInjectionDetection(NaslPlugin):
    PLUGIN_ID = 1227
    NAME = 'Hibernate Query Language (HQL) Injection Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 9.8
    DESCRIPTION = (
        'Detects Hibernate Query Language (HQL) injection vulnerabilities by '
        'injecting HQL metacharacters and logical operators. HQL injection can '
        'bypass authentication, extract data, and potentially execute arbitrary '
        'commands via database xp_cmdshell or similar functions.'
    )
    SOLUTION = (
        'Use parameterized HQL queries. Never concatenate user input directly '
        'into HQL strings. Use Criteria API for dynamic queries. Validate and '
        'sanitize all user input.'
    )
    CVE = ['CVE-2017-15782']
    PORTS = [80, 443, 8080, 8443]

    HQL_PAYLOADS = [
        "' OR '1'='1",
        "' OR 1=1 --",
        "' OR 'x'='x",
        "' OR '1'='1' --",
    ]

    PARAMS = [
        'name', 'id', 'user', 'username', 'search', 'q', 'input',
        'email', 'password',
    ]

    PATHS = ['/', '/api', '/login', '/search', '/users']

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

                for path in self.PATHS:
                    for param in self.PARAMS[:4]:
                        for payload in self.HQL_PAYLOADS:
                            try:
                                reader, writer = await asyncio.wait_for(
                                    asyncio.open_connection(target, port_to_check, ssl=ctx),
                                    timeout=5
                                )
                                encoded = urllib.parse.quote(payload)
                                req = (
                                    f'GET {path}?{param}={encoded} HTTP/1.1\r\n'
                                    f'Host: {host_header}\r\n'
                                    f'User-Agent: Centra/1.0\r\n'
                                    f'Connection: close\r\n\r\n'
                                )
                                writer.write(req.encode())
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

                                body = response.split(b'\r\n\r\n', 1)
                                body_text = body[1].decode('utf-8', errors='ignore') if len(body) > 1 else ''

                                indicators = ['sql', 'hql', 'hibernate', 'query', 'unexpected token',
                                              'unexpected char', 'expecting', 'member at', 'path expression',
                                              'unexpected end of subtree']
                                if any(ind in body_text.lower() for ind in indicators):
                                    results.append(PluginResult(
                                        vulnerable=True,
                                        target=target,
                                        port=port_to_check,
                                        cvss_score=self.CVSS_SCORE,
                                        severity='critical',
                                        description=f'HQL injection detected via param "{param}" on {path}',
                                        solution=self.SOLUTION,
                                        evidence=f'Payload: {payload}, error indicators found in response',
                                        references=[
                                            'https://owasp.org/www-community/attacks/HQL_Injection',
                                        ]
                                    ))
                                    break
                            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                                pass
                        if results:
                            break
                    if results:
                        break

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass

        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='No HQL injection indicators detected on checked ports'
            ))

        return results
