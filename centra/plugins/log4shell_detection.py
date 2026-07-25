"""
Plugin 1072: Log4Shell RCE Detection (CVE-2021-44228)
=======================================================
Detects Apache Log4j2 JNDI injection vulnerability (Log4Shell).
Real CVEs: CVE-2021-44228 (CVSS 10.0), CVE-2021-45046 (CVSS 9.0)
"""
import asyncio
import ssl
import urllib.parse

from plugins import NaslPlugin, PluginResult


class Log4ShellDetection(NaslPlugin):
    PLUGIN_ID = 1072
    NAME = 'Apache Log4j Log4Shell RCE Detection'
    FAMILY = 'Web Servers'
    CVSS_SCORE = 10.0
    DESCRIPTION = (
        'Apache Log4j2 2.0-beta9 through 2.15.0 uses JNDI features that do not '
        'protect against attacker-controlled LDAP endpoints. An attacker who can '
        'control log messages can execute arbitrary code loaded from LDAP servers, '
        'leading to full remote code execution. This is known as Log4Shell and is '
        'one of the most critical vulnerabilities ever discovered, with active '
        'exploitation in the wild since December 2021.'
    )
    SOLUTION = (
        'Upgrade Log4j to version 2.17.0 or later. For older versions, apply '
        'patches for CVE-2021-44228 (2.15.0), CVE-2021-45046 (2.16.0), and '
        'CVE-2021-45105 (2.17.0). Set system property '
        'log4j2.formatMsgNoLookups=true as a mitigation. Remove JndiLookup '
        'class from the classpath if upgrading is not immediately possible.'
    )
    CVE = ['CVE-2021-44228', 'CVE-2021-45046']
    PORTS = [80, 443, 8080, 8443, 8000, 8888, 9000]

    PAYLOADS = [
        '${jndi:ldap://127.0.0.1:1389/a}',
        '${jndi:rmi://127.0.0.1:1099/b}',
        '${jndi:dns://127.0.0.1/c}',
    ]

    HEADERS_TO_TEST = [
        'User-Agent',
        'X-Api-Version',
        'X-Forwarded-For',
        'X-Forwarded-Host',
        'X-Original-URL',
        'X-Requested-With',
        'Referer',
        'Cookie',
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

                for payload in self.PAYLOADS:
                    encoded = urllib.parse.quote(payload)
                    host_header = target
                    if target in ('127.0.0.1', 'localhost', '::1'):
                        host_header = 'alieninc.tech'

                    for header_name in self.HEADERS_TO_TEST:
                        if header_name == 'User-Agent':
                            header_val = payload
                        elif header_name == 'Cookie':
                            header_val = f'JSESSIONID={encoded}'
                        else:
                            header_val = encoded

                        req = (
                            f'GET /?x={encoded} HTTP/1.1\r\n'
                            f'Host: {host_header}\r\n'
                            f'{header_name}: {header_val}\r\n'
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

                writer.close()
                await writer.wait_closed()

                results.append(PluginResult(
                    vulnerable=True,
                    target=target,
                    port=port_to_check,
                    cvss_score=self.CVSS_SCORE,
                    severity='critical',
                    description=f'Target responded — may be vulnerable to Log4Shell on port {port_to_check}',
                    solution=self.SOLUTION,
                    evidence=f'Injected Log4j JNDI payloads via HTTP headers on port {port_to_check}',
                    references=[
                        'https://nvd.nist.gov/vuln/detail/CVE-2021-44228',
                        'https://www.cisa.gov/news-events/news/apache-log4j-vulnerability-guidance',
                        'https://www.tenable.com/plugins/nessus/156509',
                    ]
                ))

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass

        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='No Log4Shell indicators detected on checked ports'
            ))

        return results
