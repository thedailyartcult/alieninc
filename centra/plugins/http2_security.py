"""
Plugin 1153: HTTP/2 Protocol Security Check
==============================================
Checks if the server supports HTTP/2 and evaluates its configuration.
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class Http2Security(NaslPlugin):
    PLUGIN_ID = 1153
    NAME = 'HTTP/2 Protocol Security Check'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 4.0
    DESCRIPTION = (
        'Checks if the server supports HTTP/2 and evaluates its configuration '
        'for known issues. HTTP/2 improves performance but can introduce new '
        'attack surfaces including stream multiplexing abuse, HPACK bomb, and '
        'downgrade attacks.'
    )
    SOLUTION = (
        'Use HTTP/2 with proper configuration. Keep web server software updated. '
        'Implement stream timeouts and limits.'
    )
    CVE = []
    PORTS = [443, 8443]

    H2_FRAME_PREAMBLE = b'PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n'
    SETTINGS_FRAME_TYPE = 4

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []

        for port_to_check in (self.PORTS if port is None else [port]):
            try:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                ctx.set_alpn_protocols(['h2', 'http/1.1'])

                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, port_to_check, ssl=ctx),
                    timeout=5
                )

                host_header = target
                if target in ('127.0.0.1', 'localhost', '::1'):
                    host_header = 'alieninc.tech'

                negotiated = writer.get_extra_info('alpn_protocol')

                if negotiated != b'h2' and negotiated != 'h2':
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=port_to_check,
                        description='HTTP/2 not supported via ALPN (negotiated: ' + str(negotiated) + ')'
                    ))
                    writer.close()
                    await writer.wait_closed()
                    continue

                writer.write(self.H2_FRAME_PREAMBLE)
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
                except (asyncio.TimeoutError, ConnectionResetError):
                    pass

                writer.close()
                await writer.wait_closed()

                issues = []

                if response and len(response) >= 9:
                    frame_type = response[3]
                    if frame_type == self.SETTINGS_FRAME_TYPE:
                        settings_frame = response[:9]
                        frame_length = int.from_bytes(settings_frame[:3], 'big')
                        settings_data = response[9:9+frame_length] if frame_length > 0 else b''

                        if settings_data:
                            for i in range(0, len(settings_data), 6):
                                if i + 6 <= len(settings_data):
                                    setting_id = int.from_bytes(settings_data[i:i+2], 'big')
                                    setting_value = int.from_bytes(settings_data[i+2:i+6], 'big')

                                    if setting_id == 3 and setting_value == 0:
                                        issues.append('SETTINGS_MAX_CONCURRENT_STREAMS is 0 (connection refusal)')
                                    elif setting_id == 4 and setting_value == 0:
                                        issues.append('SETTINGS_INITIAL_WINDOW_SIZE is 0 (flow control disabled)')
                                    elif setting_id == 5 and setting_value > 16777215:
                                        issues.append(f'SETTINGS_MAX_FRAME_SIZE exceeds limit: {setting_value}')

                    if not settings_data:
                        issues.append('No SETTINGS frame received')

                    server_header = None
                    if b'server:' in response[:512]:
                        pass

                if not issues:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=port_to_check,
                        description='HTTP/2 supported via ALPN, no basic security issues detected',
                        evidence=f'ALPN negotiated: h2',
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=port_to_check,
                        cvss_score=self.CVSS_SCORE, severity='medium',
                        description=f'HTTP/2 security issue(s) detected: {len(issues)} found',
                        solution=self.SOLUTION,
                        evidence='; '.join(issues),
                        references=[
                            'https://www.rfc-editor.org/rfc/rfc9113',
                            'https://portswigger.net/web-security/request-smuggling/http2',
                            'https://www.tenable.com/plugins/nessus/115029',
                        ]
                    ))

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                results.append(PluginResult(
                    vulnerable=False, target=target, port=port_to_check,
                    description='Port not reachable or TLS connection failed'
                ))

        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='No ports reachable for HTTP/2 check'
            ))

        return results
