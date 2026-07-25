"""
Plugin 1238: Reverse Tabnabbing Detection
==========================================
Detects reverse tabnabbing vulnerabilities where external links using
target="_blank" without rel="noopener noreferrer" are present.
"""
import asyncio
import re
import ssl

from plugins import NaslPlugin, PluginResult


class TabnabbingDetection(NaslPlugin):
    PLUGIN_ID = 1238
    NAME = 'Reverse Tabnabbing Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 5.3
    DESCRIPTION = (
        'Detects reverse tabnabbing vulnerabilities where external links using '
        'target="_blank" without rel="noopener noreferrer" allow opened pages '
        'to access the original page via window.opener, potentially redirecting '
        'it to phishing sites.'
    )
    SOLUTION = (
        'Always add rel="noopener noreferrer" to all links with target="_blank". '
        'Use rel="noreferrer" when noopener is not supported.'
    )
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    LINK_PATTERN = re.compile(
        r'<a\s[^>]*?href=["\'](https?://[^"\']+)["\'][^>]*?>',
        re.IGNORECASE
    )

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
                host_header = 'alieninc.tech' if target in ('127.0.0.1', 'localhost', '::1') else target
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5
                )
                req = f'GET / HTTP/1.1\r\nHost: {host_header}\r\nUser-Agent: Centra/1.0\r\nConnection: close\r\n\r\n'
                writer.write(req.encode())
                await writer.drain()
                response = b''
                try:
                    while True:
                        chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                        if not chunk:
                            break
                        response += chunk
                        if len(response) > 32768:
                            break
                except asyncio.TimeoutError:
                    pass
                writer.close()
                await writer.wait_closed()
                body = response.split(b'\r\n\r\n', 1)
                if len(body) > 1:
                    html = body[1].decode('utf-8', errors='ignore')
                    affected = []
                    for match in re.finditer(
                        r'<a\s([^>]*?)href=["\'](https?://[^"\']+)["\']([^>]*?)>',
                        html, re.IGNORECASE
                    ):
                        attrs = match.group(1) + ' ' + match.group(3)
                        href = match.group(2)
                        has_target_blank = 'target' in attrs and ('_blank' in attrs or '"blank' in attrs)
                        has_noopener = 'noopener' in attrs
                        has_noreferrer = 'noreferrer' in attrs
                        if has_target_blank and not (has_noopener or has_noreferrer):
                            if not href.startswith('//') and host_header.split(':')[0] not in href:
                                affected.append(href)
                    if affected:
                        results.append(PluginResult(
                            vulnerable=True,
                            target=target,
                            port=port_to_check,
                            cvss_score=self.CVSS_SCORE,
                            severity='medium',
                            description=(
                                f'{len(affected)} external link(s) with target="_blank '
                                f'missing rel="noopener noreferrer"'
                            ),
                            solution=self.SOLUTION,
                            evidence=f'Affected URLs: {affected[:5]}',
                            references=[
                                'https://owasp.org/www-community/attacks/Reverse_Tabnabbing',
                                'https://web.dev/external-anchors-use-rel-noopener/',
                            ]
                        ))
                    else:
                        results.append(PluginResult(
                            vulnerable=False,
                            target=target,
                            port=port_to_check,
                            description='No vulnerable external links detected'
                        ))
                        break
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass
        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='No reverse tabnabbing indicators detected'
            ))
        return results
