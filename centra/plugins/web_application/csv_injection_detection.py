import asyncio
import ssl
from plugins import NaslPlugin, PluginResult

class CsvInjectionDetection(NaslPlugin):
    PLUGIN_ID = 1200
    NAME = 'CSV Injection / Formula Injection Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 6.1
    DESCRIPTION = 'Detects CSV injection vulnerabilities by checking if user-controlled data is exported to CSV files without proper sanitization of formula metacharacters (=, +, -, @). Formula injection can execute arbitrary commands when the CSV is opened in Excel.'
    SOLUTION = 'Sanitize CSV output by escaping formula characters. Use tab-separated values. Add a single quote prefix to cells starting with =, +, -, @.'
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    EXPORT_PATHS = ['/export.csv', '/download.csv', '/api/export', '/reports/export', '/csv', '/data.csv', '/users.csv']

    FORMULA_PAYLOADS = [
        '=1+1',
        '=2*3',
        '=SUM(1,1)',
        '+SUM(1,1)',
        '-SUM(1,1)',
        '@SUM(1,1)',
        '=CMD| /C calc!A0',
        '=HYPERLINK("http://evil.com","Click")',
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

                for path in self.EXPORT_PATHS:
                    for payload in self.FORMULA_PAYLOADS:
                        try:
                            reader, writer = await asyncio.wait_for(asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5)
                            host_header = target
                            if target in ('127.0.0.1', 'localhost', '::1'):
                                host_header = 'alieninc.tech'

                            qs = f'name={payload}'
                            req = f'GET {path}?{qs} HTTP/1.1\r\nHost: {host_header}\r\nConnection: close\r\n\r\n'
                            writer.write(req.encode())
                            await writer.drain()

                            response = b''
                            try:
                                while True:
                                    chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                                    if not chunk: break
                                    response += chunk
                                    if len(response) > 8192: break
                            except asyncio.TimeoutError:
                                pass

                            writer.close()
                            await writer.wait_closed()

                            if response:
                                body = response.split(b'\r\n\r\n', 1)[-1] if b'\r\n\r\n' in response else response
                                body_str = body.decode('utf-8', errors='ignore')
                                content_type = b''
                                header_section = response.split(b'\r\n\r\n')[0] if b'\r\n\r\n' in response else b''
                                for line in header_section.split(b'\r\n')[1:]:
                                    if b':' in line:
                                        k, v = line.split(b':', 1)
                                        if k.strip().lower() == b'content-type':
                                            content_type = v.strip()
                                            break

                                is_csv = b'csv' in content_type or b'text/csv' in content_type or b'application/csv' in content_type or path.endswith('.csv')
                                if is_csv and any(c in body_str for c in ['=1+1', '=2*3', '=SUM', '+SUM', '-SUM', '@SUM', '=CMD', '=HYPERLINK']):
                                    results.append(PluginResult(
                                        vulnerable=True, target=target, port=port_to_check,
                                        cvss_score=self.CVSS_SCORE, severity='medium',
                                        description=f'CSV injection detected on {path} - formula characters preserved in CSV export',
                                        solution=self.SOLUTION,
                                        evidence=f'Path: {path}, payload: {payload}',
                                        references=['https://owasp.org/www-community/attacks/CSV_Injection']
                                    ))
                        except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                            pass
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description='No CSV injection vulnerabilities detected'))
        return results
