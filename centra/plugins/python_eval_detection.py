"""
Plugin 1234: Python Code Injection / Eval Injection Detection
==============================================================
Detects Python code injection vulnerabilities by injecting Python
expressions (eval, exec, compile) into API parameters.
"""
import asyncio
import ssl
import urllib.parse

from plugins import NaslPlugin, PluginResult


class PythonEvalDetection(NaslPlugin):
    PLUGIN_ID = 1234
    NAME = 'Python Code Injection / Eval Injection Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 9.8
    DESCRIPTION = (
        'Detects Python code injection vulnerabilities by injecting Python '
        'expressions (__import__("os").system("id"), eval, exec, compile) into '
        'API parameters. Python eval/exec injection gives attackers full RCE on '
        'the server.'
    )
    SOLUTION = (
        'Never use eval() or exec() on user input. Use ast.literal_eval() for '
        'safe evaluation of Python literals. Validate and sanitize all user input.'
    )
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    EVAL_PAYLOADS = [
        '__import__("os").system("id")',
        'eval(__import__("os").popen("id").read())',
        "eval(exec('import os; os.system(\"id\")'))",
        'exec("import os; os.system(\'id\')")',
    ]

    PARAMS = [
        'expr', 'expression', 'eval', 'exec', 'code', 'input',
        'q', 'data', 'cmd', 'func',
    ]

    PATHS = [
        '/', '/api', '/api/eval', '/eval', '/execute',
        '/api/exec', '/api/run', '/run',
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

                for path in self.PATHS:
                    for param in self.PARAMS[:5]:
                        for payload in self.EVAL_PAYLOADS:
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

                                indicators = ['uid=', 'gid=', 'root:', 'traceback', 'nameerror',
                                              'typeerror', 'syntaxerror', 'zerodivisionerror',
                                              'importerror', 'attributeerror']
                                if any(ind in body_text.lower() for ind in indicators):
                                    results.append(PluginResult(
                                        vulnerable=True,
                                        target=target,
                                        port=port_to_check,
                                        cvss_score=self.CVSS_SCORE,
                                        severity='critical',
                                        description=f'Python code injection detected via param "{param}" on {path}',
                                        solution=self.SOLUTION,
                                        evidence=f'Payload: {payload}, execution indicators found in response',
                                        references=[
                                            'https://owasp.org/www-community/attacks/Code_Injection',
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
                description='No Python code injection indicators detected on checked ports'
            ))

        return results
