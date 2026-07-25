"""
Plugin 1232: Python Pickle Deserialization Detection
======================================================
Detects Python pickle deserialization vulnerabilities in API endpoints
and cookies. Unsafe pickle deserialization can execute arbitrary Python code.
"""
import asyncio
import base64
import ssl
import urllib.parse

from plugins import NaslPlugin, PluginResult


class PythonPickleDeserialization(NaslPlugin):
    PLUGIN_ID = 1232
    NAME = 'Python Pickle Deserialization Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 9.8
    DESCRIPTION = (
        'Detects Python pickle deserialization vulnerabilities in API endpoints '
        'and cookies. Unsafe pickle deserialization can execute arbitrary Python '
        'code, leading to full server compromise. Tests by sending crafted pickle '
        'opcodes in base64-encoded form.'
    )
    SOLUTION = (
        'Never deserialize pickle data from untrusted sources. Use JSON or other '
        'safe serialization formats. If pickle is required, use HMAC signing for '
        'integrity. Use pickle.Unpickler with restricted __find_class__.'
    )
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    COOKIE_NAMES = [
        'session', 'profile', 'prefs', 'settings', 'user', 'token',
    ]

    PATHS = ['/', '/api', '/profile', '/settings']

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
                    for cookie_name in self.COOKIE_NAMES:
                        try:
                            reader, writer = await asyncio.wait_for(
                                asyncio.open_connection(target, port_to_check, ssl=ctx),
                                timeout=5
                            )

                            cookie_val = base64.b64encode(b'\x80\x04\x95\x05\x00\x00\x00\x00\x00\x00\x00N.').decode()
                            req = (
                                f'GET {path} HTTP/1.1\r\n'
                                f'Host: {host_header}\r\n'
                                f'Cookie: {cookie_name}={cookie_val}\r\n'
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

                            indicators = ['pickle', 'unpickling', 'unpickle', 'insecure deserialize',
                                          'unsafe deserialize', 'stack', 'marshalling', 'opcode']
                            if any(ind in body_text.lower() for ind in indicators):
                                results.append(PluginResult(
                                    vulnerable=True,
                                    target=target,
                                    port=port_to_check,
                                    cvss_score=self.CVSS_SCORE,
                                    severity='critical',
                                    description=f'Python pickle deserialization detected in cookie "{cookie_name}" on {path}',
                                    solution=self.SOLUTION,
                                    evidence=f'Cookie: {cookie_name}, pickle opcode sent, error indicators found in response',
                                    references=[
                                        'https://owasp.org/www-community/attacks/Deserialization_of_untrusted_data',
                                    ]
                                ))
                                break
                        except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                            pass
                    if results:
                        break

                if not results:
                    for path in self.PATHS:
                        try:
                            payload = urllib.parse.quote(base64.b64encode(b'\x80\x04\x95\x05\x00\x00\x00\x00\x00\x00\x00N.').decode())
                            reader, writer = await asyncio.wait_for(
                                asyncio.open_connection(target, port_to_check, ssl=ctx),
                                timeout=5
                            )
                            req = (
                                f'GET {path}?data={payload} HTTP/1.1\r\n'
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

                            indicators = ['pickle', 'unpickling', 'unpickle', 'insecure deserialize',
                                          'unsafe deserialize', 'stack', 'marshalling', 'opcode']
                            if any(ind in body_text.lower() for ind in indicators):
                                results.append(PluginResult(
                                    vulnerable=True,
                                    target=target,
                                    port=port_to_check,
                                    cvss_score=self.CVSS_SCORE,
                                    severity='critical',
                                    description=f'Python pickle deserialization detected in data parameter on {path}',
                                    solution=self.SOLUTION,
                                    evidence=f'Base64 pickle payload sent, error indicators found in response',
                                    references=[
                                        'https://owasp.org/www-community/attacks/Deserialization_of_untrusted_data',
                                    ]
                                ))
                                break
                        except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                            pass
                    if results:
                        break

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass

        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='No Python pickle deserialization indicators detected on checked ports'
            ))

        return results
