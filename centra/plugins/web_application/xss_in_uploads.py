import asyncio
import ssl
from plugins import NaslPlugin, PluginResult

class XSSInUploadsDetection(NaslPlugin):
    PLUGIN_ID = 1209
    NAME = 'XSS via File Upload Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 7.5
    DESCRIPTION = 'Detects XSS vulnerabilities in file upload functionality by uploading files with HTML/JavaScript content (SVG with onload, HTML file with script). If the server serves uploaded files with the original content type, XSS payloads execute in the context of the origin.'
    SOLUTION = 'Serve uploaded files with Content-Disposition: attachment. Validate file content not just extension. Serve user content from a separate domain. Strip active content from SVG and image uploads.'
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        upload_endpoints = ['/upload', '/uploads', '/file/upload', '/api/upload', '/media/upload', '/upload.php', '/upload.html', '/uploadFile']
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

                svg_payload = b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"/>'
                boundary = b'----WebKitFormBoundary7MA4YWxkTrZu0gW'
                body = (
                    boundary + b'\r\n'
                    b'Content-Disposition: form-data; name="file"; filename="xss.svg"\r\n'
                    b'Content-Type: image/svg+xml\r\n\r\n'
                    + svg_payload + b'\r\n'
                    + boundary + b'--\r\n'
                )

                for endpoint in upload_endpoints:
                    req = (
                        f'POST {endpoint} HTTP/1.1\r\n'
                        f'Host: {host_header}\r\n'
                        f'Content-Type: multipart/form-data; boundary={boundary.decode()}\r\n'
                        f'Content-Length: {len(body)}\r\n'
                        f'Connection: close\r\n\r\n'
                    ).encode() + body

                    reader, writer = await asyncio.wait_for(asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5)
                    writer.write(req)
                    await writer.drain()
                    resp = b''
                    try:
                        while True:
                            chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                            if not chunk: break
                            resp += chunk
                            if len(resp) > 8192: break
                    except asyncio.TimeoutError:
                        pass
                    writer.close()
                    await writer.wait_closed()

                    if resp and b'200' in resp[:64]:
                        header_section = resp.split(b'\r\n\r\n')[0] if b'\r\n\r\n' in resp else resp
                        if b'Content-Type: image/svg+xml' in header_section or b'Content-Disposition: inline' in header_section:
                            results.append(PluginResult(vulnerable=True, target=target, port=port_to_check, description=f'Upload endpoint {endpoint} serves SVG without attachment disposition'))
                            break
                else:
                    results.append(PluginResult(vulnerable=False, target=target, port=port_to_check, description='No vulnerable upload endpoint detected'))
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                results.append(PluginResult(vulnerable=False, target=target, port=port_to_check, description='Connection failed'))
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description='No issues detected'))
        return results
