"""
Plugin 1092: PHPUnit Remote Code Execution (CVE-2017-9841)
============================================================
Detects PHPUnit eval-stdin.php RCE vulnerability.
Real CVE: CVE-2017-9841 (CVSS 9.8)
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class PhpunitRceDetection(NaslPlugin):
    PLUGIN_ID = 1092
    NAME = 'PHPUnit Remote Code Execution (CVE-2017-9841)'
    FAMILY = 'Web Servers'
    CVSS_SCORE = 9.8
    DESCRIPTION = (
        'PHPUnit before 5.6.3 and 6.x before 6.5.13 allows attackers to execute '
        'arbitrary PHP code via the eval-stdin.php script. When PHPUnit is installed '
        'on a production web server, unauthenticated attackers can execute arbitrary '
        'PHP commands by sending PHP code to eval-stdin.php.'
    )
    SOLUTION = (
        'Remove PHPUnit from production web servers. For development servers, '
        'restrict access to the vendor directory. Upgrade to PHPUnit 5.6.3 or 6.5.13+.'
    )
    CVE = ['CVE-2017-9841']
    PORTS = [80, 443, 8080, 8443]

    PHPUNIT_PATHS = [
        '/vendor/phpunit/phpunit/src/Util/PHP/eval-stdin.php',
        '/phpunit/phpunit/src/Util/PHP/eval-stdin.php',
        '/vendor/phpunit/src/Util/PHP/eval-stdin.php',
    ]

    PHPUNIT_HINTS = [
        b'PHPUnit',
        b'phpunit',
        b'Sebastian Bergmann',
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

                for path in self.PHPUNIT_PATHS:
                    body = '<?php echo "PHPUNIT_TEST_OK"; ?>'
                    req = (
                        f'POST {path} HTTP/1.1\r\n'
                        f'Host: {host_header}\r\n'
                        f'Content-Type: application/x-www-form-urlencoded\r\n'
                        f'Content-Length: {len(body)}\r\n'
                        f'User-Agent: Centra/1.0\r\n'
                        f'Connection: close\r\n\r\n'
                        f'{body}'
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
                        body_resp = response[body_start + 4:] if body_start != -1 else b''
                        body_str = body_resp.decode('utf-8', errors='ignore')

                        is_200 = b'200 OK' in response[:50]
                        phpunit_test_ok = b'PHPUNIT_TEST_OK' in body_resp
                        phpunit_hits = [h for h in self.PHPUNIT_HINTS if h in response]

                        if phpunit_test_ok:
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=self.CVSS_SCORE,
                                severity='critical',
                                description=(
                                    f'PHPUnit eval-stdin.php RCE confirmed on port {port_to_check} '
                                    f'— arbitrary PHP code execution via CVE-2017-9841'
                                ),
                                solution=self.SOLUTION,
                                evidence=(
                                    f'Path: {path}, Status: {status_line}, '
                                    f'PHP code execution confirmed via eval-stdin.php'
                                ),
                                references=[
                                    'https://nvd.nist.gov/vuln/detail/CVE-2017-9841',
                                    'https://github.com/phpunit/phpunit/security/advisories/GHSA-3q5w-7m7h-6p6m',
                                ]
                            ))
                            break

                        if is_200 and phpunit_hits:
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=self.CVSS_SCORE,
                                severity='critical',
                                description=(
                                    f'PHPUnit detected on port {port_to_check} — '
                                    f'eval-stdin.php endpoint accessible (CVE-2017-9841)'
                                ),
                                solution=self.SOLUTION,
                                evidence=(
                                    f'Path: {path}, Status: {status_line}, '
                                    f'PHPUnit hints: {phpunit_hits}'
                                ),
                                references=[
                                    'https://nvd.nist.gov/vuln/detail/CVE-2017-9841',
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
                description='No PHPUnit eval-stdin.php indicators detected'
            ))

        return results
