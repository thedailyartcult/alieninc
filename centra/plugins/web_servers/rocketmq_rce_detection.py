"""
Plugin 1110: Apache RocketMQ RCE (CVE-2023-33246)
==================================================
Detects CVE-2023-33246 RCE in Apache RocketMQ.
Real CVE: CVE-2023-33246 (CVSS 9.8)
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class RocketmqRceDetection(NaslPlugin):
    PLUGIN_ID = 1110
    NAME = 'Apache RocketMQ RCE (CVE-2023-33246)'
    FAMILY = 'Web Servers'
    CVSS_SCORE = 9.8
    CVSS = 9.8
    DESCRIPTION = (
        'Apache RocketMQ versions 5.1.0 and earlier, and 4.9.6 and earlier contain '
        'a remote code execution vulnerability. An attacker can exploit the updateConfig '
        'or createAccount endpoints to execute arbitrary commands with the privilege of '
        'the RocketMQ broker process.'
    )
    SOLUTION = (
        'Upgrade RocketMQ to 4.9.7 or 5.1.1 or later. Restrict access to RocketMQ '
        'administration endpoints.'
    )
    CVE = ['CVE-2023-33246']
    PORTS = [9876, 10909, 10911, 80, 443]

    ROCKETMQ_PATHS = [
        '/',
        '/dashboard',
        '/rocketmq',
        '/cluster',
        '/admin',
    ]

    ROCKETMQ_HINTS = [
        b'RocketMQ',
        b'rocketmq',
        b'RocketMQ_Broker',
        b'updateConfig',
        b'createAccount',
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

                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, port_to_check, ssl=ctx),
                    timeout=5
                )

                host_header = target
                if target in ('127.0.0.1', 'localhost', '::1'):
                    host_header = 'alieninc.tech'

                for path in self.ROCKETMQ_PATHS:
                    req = (
                        f'GET {path} HTTP/1.1\r\n'
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
                            if len(response) > 8192:
                                break
                    except asyncio.TimeoutError:
                        pass

                    if response:
                        status_line = response.split(b'\r\n')[0].decode('utf-8', errors='ignore')
                        body_start = response.find(b'\r\n\r\n')
                        body = response[body_start + 4:] if body_start != -1 else b''
                        body_str = body.decode('utf-8', errors='ignore')

                        is_200 = b'200' in response[:50]
                        rocketmq_hits = [h for h in self.ROCKETMQ_HINTS if h in response]

                        if rocketmq_hits or (is_200 and b'RocketMQ' in response):
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=self.CVSS_SCORE,
                                severity='critical',
                                description=(
                                    f'Apache RocketMQ detected on port {port_to_check} — '
                                    f'potentially vulnerable to CVE-2023-33246 RCE'
                                ),
                                solution=self.SOLUTION,
                                evidence=(
                                    f'Path: {path}, Status: {status_line}, '
                                    f'RocketMQ indicators: {rocketmq_hits}'
                                ),
                                references=[
                                    'https://nvd.nist.gov/vuln/detail/CVE-2023-33246',
                                    'https://www.tenable.com/plugins/nessus/177305',
                                ]
                            ))
                            break

                writer.close()
                await writer.wait_closed()

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass

        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='No Apache RocketMQ indicators detected'
            ))

        return results
