"""
Plugin 1075: Apache ActiveMQ RCE Detection (CVE-2023-46604)
=============================================================
Detects Apache ActiveMQ OpenWire protocol RCE vulnerability.
Real CVEs: CVE-2023-46604 (CVSS 10.0)
"""
import asyncio
import socket

from plugins import NaslPlugin, PluginResult


class ActivemqRceDetection(NaslPlugin):
    PLUGIN_ID = 1075
    NAME = 'Apache ActiveMQ OpenWire RCE (CVE-2023-46604)'
    FAMILY = 'Misc.'
    CVSS_SCORE = 10.0
    DESCRIPTION = (
        'The Java OpenWire protocol marshaller in Apache ActiveMQ is vulnerable '
        'to Remote Code Execution. This vulnerability allows a remote attacker '
        'with network access to an OpenWire broker to run arbitrary shell commands '
        'by manipulating serialized class types. Active exploitation has been '
        'observed in the wild with HelloKitty ransomware deployment. All versions '
        'before 5.15.16, 5.16.7, 5.17.6, and 5.18.3 are affected.'
    )
    SOLUTION = (
        'Upgrade Apache ActiveMQ broker to version 5.15.16, 5.16.7, 5.17.6, '
        'or 5.18.3 or later, depending on your release line. If upgrade is '
        'not immediately possible, restrict network access to the OpenWire '
        'port (61616) to trusted hosts only. Monitor for suspicious '
        'deserialization attempts.'
    )
    CVE = ['CVE-2023-46604']
    PORTS = [61616, 61613, 61614, 8161]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []

        for port_to_check in (self.PORTS if port is None else [port]):
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, port_to_check),
                    timeout=5
                )

                writer.write(b'\x00')
                await writer.drain()

                response = b''
                try:
                    response = await asyncio.wait_for(reader.read(1024), timeout=3)
                except asyncio.TimeoutError:
                    pass

                writer.close()
                await writer.wait_closed()

                if response:
                    detected = False
                    evidence = ''

                    if b'ActiveMQ' in response:
                        detected = True
                        evidence = f'ActiveMQ detected via raw connection on port {port_to_check}'
                    elif len(response) > 0:
                        hex_preview = response[:50].hex()
                        evidence = f'Non-empty response on port {port_to_check}: {hex_preview}'

                    if detected:
                        results.append(PluginResult(
                            vulnerable=True,
                            target=target,
                            port=port_to_check,
                            cvss_score=self.CVSS_SCORE,
                            severity='critical',
                            description=f'ActiveMQ service detected on port {port_to_check}. '
                                        f'Check version — versions before 5.15.16/5.16.7/5.17.6/5.18.3 '
                                        f'are vulnerable to RCE via CVE-2023-46604.',
                            solution=self.SOLUTION,
                            evidence=evidence,
                            references=[
                                'https://nvd.nist.gov/vuln/detail/CVE-2023-46604',
                                'https://activemq.apache.org/security-advisories.data/CVE-2023-46604-announcement.txt',
                                'https://www.tenable.com/plugins/nessus/186650',
                                'https://www.cisa.gov/known-exploited-vulnerabilities-catalog',
                            ]
                        ))

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
                pass

        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='ActiveMQ service not detected on checked ports'
            ))

        return results
