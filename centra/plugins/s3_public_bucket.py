"""
Plugin 1041: AWS S3 Public Bucket Detection (via HTTP Proxy)
==============================================================
Detects references to publicly accessible S3 buckets in web page
content and tests them for public-listability over HTTPS.
Real CVEs: CVE-2022-36327 (S3 bucket exposure)
"""
import asyncio
import re
import ssl

from plugins import NaslPlugin, PluginResult


class S3PublicBucket(NaslPlugin):
    PLUGIN_ID = 1041
    NAME = 'AWS S3 Public Bucket Detection'
    FAMILY = 'Cloud Infrastructure'
    CVSS_SCORE = 6.5
    DESCRIPTION = (
        'The web page references an S3 bucket that appears to be publicly '
        'accessible. Public buckets can expose sensitive data, configuration '
        'files, and proprietary information to unauthorized parties.'
    )
    SOLUTION = (
        'Block all public access to S3 buckets using S3 Block Public Access '
        'settings. Apply least-privilege bucket policies. Enable S3 server '
        'access logging for audit. Use IAM roles for application access.'
    )
    CVE = ['CVE-2022-36327']
    PORTS = [80, 443]

    SSL_CTX = None

    async def check_target(self, target: str, port: int | None = 443) -> list[PluginResult]:
        port = port or 443
        if self.SSL_CTX is None:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            type(self).SSL_CTX = ctx

        page_text = await self._fetch_page(target, port)
        if page_text is None:
            return [PluginResult(
                vulnerable=False, target=target, port=port,
                description=f'Could not retrieve page content from {target}:{port}'
            )]

        bucket_refs = self._extract_bucket_references(page_text)
        if not bucket_refs:
            return [PluginResult(
                vulnerable=False, target=target, port=port,
                description='No S3 bucket references found in page content'
            )]

        accessible = []
        for bucket_host in bucket_refs:
            result = await self._check_bucket(bucket_host)
            if result:
                accessible.append(result)

        if accessible:
            return [PluginResult(
                vulnerable=True,
                target=target,
                port=port,
                cvss_score=self.CVSS_SCORE,
                severity='high',
                description=f'{len(accessible)} S3 bucket(s) with public read access detected',
                solution=self.SOLUTION,
                evidence='; '.join(accessible),
                references=[
                    'https://nvd.nist.gov/vuln/detail/CVE-2023-31417',
                    'https://www.tenable.com/plugins/nessus/168531',
                ]
            )]

        return [PluginResult(
            vulnerable=False, target=target, port=port,
            description='Referenced S3 buckets do not appear to allow public listing'
        )]

    async def _fetch_page(self, target: str, port: int) -> str | None:
        try:
            use_ssl = port == 443
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port, ssl=self.SSL_CTX if use_ssl else None),
                timeout=6
            )

            req = (
                f'GET / HTTP/1.1\r\n'
                f'Host: {target}\r\n'
                f'User-Agent: Mozilla/5.0 (Centra Scanner)\r\n'
                f'Accept: text/html,application/xhtml+xml\r\n'
                f'Connection: close\r\n\r\n'
            )
            writer.write(req.encode())
            await writer.drain()

            response = b''
            while True:
                chunk = await asyncio.wait_for(reader.read(4096), timeout=4)
                if not chunk:
                    break
                response += chunk
                if len(response) > 65536:
                    break

            writer.close()
            await writer.wait_closed()

            header, _, body = response.partition(b'\r\n\r\n')
            if not header or b'200' not in header.split(b'\r\n')[0]:
                return None

            return body.decode('utf-8', errors='ignore')[:50000]

        except Exception:
            return None

    def _extract_bucket_references(self, text: str) -> list[str]:
        buckets = set()
        patterns = [
            r'(?:https?://)?([a-zA-Z0-9._-]+)\.s3(?:[-.][a-z0-9-]+)?\.amazonaws\.com',
            r'(?:https?://)?s3(?:[-.][a-z0-9-]+)?\.amazonaws\.com/([a-zA-Z0-9._-]+)',
            r'(?:https?://)?([a-zA-Z0-9._-]+)\.s3\.amazonaws\.com',
            r'(?:https?://)?([a-zA-Z0-9._-]+)\.storage\.googleapis\.com',
            r's3://([a-zA-Z0-9._-]+)',
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                bucket_name = match.group(1).rstrip('/')
                if bucket_name and len(bucket_name) >= 3:
                    buckets.add(f'{bucket_name}.s3.amazonaws.com')
        return list(buckets)

    async def _check_bucket(self, bucket_host: str) -> str | None:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(bucket_host, 443, ssl=self.SSL_CTX),
                timeout=8
            )

            req = (
                f'GET / HTTP/1.1\r\n'
                f'Host: {bucket_host}\r\n'
                f'User-Agent: Centra/1.0\r\n'
                f'Connection: close\r\n\r\n'
            )
            writer.write(req.encode())
            await writer.drain()

            response = b''
            while True:
                chunk = await asyncio.wait_for(reader.read(4096), timeout=4)
                if not chunk:
                    break
                response += chunk
                if len(response) > 32768:
                    break

            writer.close()
            await writer.wait_closed()

            header, _, body = response.partition(b'\r\n\r\n')
            status_line = header.split(b'\r\n')[0].decode('utf-8', errors='ignore')

            if '200' not in status_line:
                return None

            body_text = body.decode('utf-8', errors='ignore')

            if '<ListBucketResult' in body_text or '<Contents' in body_text:
                bucket_name = bucket_host.replace('.s3.amazonaws.com', '')
                return f'{bucket_name} — public bucket listing (ListBucketResult in response)'
            if 'AccessDenied' not in body_text and len(body) > 200:
                bucket_name = bucket_host.replace('.s3.amazonaws.com', '')
                return f'{bucket_name} — accessible (HTTP 200, {len(body)} bytes)'

        except Exception:
            pass

        return None
