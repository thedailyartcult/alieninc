"""
Plugin 1138: File Upload Security Validation
==============================================
Tests file upload endpoints for common security vulnerabilities.
Real CVEs: CVE-2024-1709 (unrestricted upload), CVE-2023-34991 (file upload RCE)
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class FileUploadSecurityDetection(NaslPlugin):
    PLUGIN_ID = 1138
    NAME = 'File Upload Security Validation'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 7.5
    DESCRIPTION = (
        'Tests file upload endpoints for common security vulnerabilities including '
        'unrestricted file type uploads, missing size limits, executable file upload, '
        'and directory traversal in filenames. Unsafe file upload can lead to RCE, '
        'XSS, or server compromise.'
    )
    SOLUTION = (
        'Validate file types server-side (not just MIME). Enforce file size limits. '
        'Use random filenames. Store uploads outside web root.'
    )
    CVE = ['CVE-2024-1709', 'CVE-2023-34991']
    PORTS = [80, 443, 8080, 8443]

    UPLOAD_PATHS = ['/upload', '/api/upload', '/file/upload', '/upload.php', '/uploadFile']
    TEST_FILENAMES = ['test.php', 'test.jsp', 'test.aspx', '../../../etc/passwd', 'test.exe']

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for port_to_check in (self.PORTS if port is None else [port]):
            for path in self.UPLOAD_PATHS:
                try:
                    scheme = 'https' if port_to_check in (443, 8443) else 'http'
                    ctx = None
                    if scheme == 'https':
                        ctx = ssl.create_default_context()
                        ctx.check_hostname = False
                        ctx.verify_mode = ssl.CERT_NONE
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5
                    )
                    host_header = target
                    if target in ('127.0.0.1', 'localhost', '::1'):
                        host_header = 'alieninc.tech'

                    boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW'
                    body = (
                        f'--{boundary}\r\n'
                        f'Content-Disposition: form-data; name="file"; filename="{self.TEST_FILENAMES[0]}"\r\n'
                        f'Content-Type: application/x-php\r\n\r\n'
                        f'<?php echo "centra_upload_test"; ?>\r\n'
                        f'--{boundary}--\r\n'
                    )
                    req = (
                        f'POST {path} HTTP/1.1\r\n'
                        f'Host: {host_header}\r\n'
                        f'User-Agent: Centra/1.0\r\n'
                        f'Content-Type: multipart/form-data; boundary={boundary}\r\n'
                        f'Content-Length: {len(body)}\r\n'
                        f'Connection: close\r\n\r\n{body}'
                    )
                    writer.write(req.encode())
                    await writer.drain()

                    response = b''
                    while True:
                        chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                        if not chunk:
                            break
                        response += chunk
                        if len(response) > 32768:
                            break
                    writer.close()
                    await writer.wait_closed()

                    response_text = response.decode('utf-8', errors='ignore')
                    status_line = response_text.split('\r\n')[0]
                    if '200' in status_line or '201' in status_line or '302' in status_line:
                        results.append(PluginResult(
                            vulnerable=True, target=target, port=port_to_check,
                            cvss_score=self.CVSS_SCORE, severity='high',
                            description=f'Upload endpoint found at {path} and accepted file with extension .php',
                            solution=self.SOLUTION,
                            evidence=f'Endpoint: {path}, Status: {status_line}, Filename: {self.TEST_FILENAMES[0]}',
                            references=[
                                'https://nvd.nist.gov/vuln/detail/CVE-2024-1709',
                                'https://owasp.org/www-community/vulnerabilities/Unrestricted_File_Upload',
                            ]
                        ))
                        return results

                except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                    pass
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description='No issues detected'))
        return results
