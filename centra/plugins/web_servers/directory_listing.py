"""
Plugin 1038: Directory Listing Detection
===========================================
Detects enabled directory listing on web servers.
Real CVEs: CVE-2022-30625 (directory listing), CVE-2006-3835 (Tomcat listing)
"""
import asyncio

from plugins import NaslPlugin, PluginResult


class DirectoryListing(NaslPlugin):
    PLUGIN_ID = 1038
    NAME = 'Directory Listing Detection'
    FAMILY = 'Web Servers'
    CVSS_SCORE = 5.3
    DESCRIPTION = (
        'Directory listing is enabled on the web server. Attackers can browse '
        'the filesystem, enumerate directories, and discover sensitive files, '
        'backup archives, and application source code.'
    )
    SOLUTION = (
        'Disable directory listing in web server configuration. For Apache: '
        'Options -Indexes. For Nginx: autoindex off. For IIS: disable '
        'directory browsing.'
    )
    CVE = ['CVE-2022-30625', 'CVE-2006-3835']
    PORTS = [80, 443]

    LISTING_PATTERNS = [
        b'Index of /',
        b'<title>Index of',
        b'Directory listing for',
        b'[DIR]',
        b'&lt;dir&gt;',
        b'Parent Directory',
        b'Directory:',
    ]

    PROBE_PATHS = [
        '/',
        '/assets/',
        '/images/',
        '/css/',
        '/js/',
        '/uploads/',
        '/backup/',
        '/static/',
        '/media/',
        '/downloads/',
    ]

    NON_LISTING_PATTERNS = [
        b'<html', b'<!DOCTYPE', b'<body', b'<head', b'<?xml',
        b'<script', b'<style', b'server-status', b'server-info',
    ]

    async def check_target(self, target: str, port: int | None = 80) -> list[PluginResult]:
        port = port or 80
        results_by_path = []

        for path in self.PROBE_PATHS:
            try:
                is_listing = await self._check_path(target, port, path)
                if is_listing:
                    results_by_path.append(path)
            except Exception:
                pass

        if results_by_path:
            return [PluginResult(
                vulnerable=True,
                target=target,
                port=port,
                cvss_score=self.CVSS_SCORE,
                severity='medium',
                description=f'Directory listing enabled on {len(results_by_path)} path(s)',
                solution=self.SOLUTION,
                evidence=f'Paths with directory listing: {", ".join(results_by_path)}',
                references=[
                    'https://nvd.nist.gov/vuln/detail/CVE-2023-44487',
                    'https://www.tenable.com/plugins/nessus/10542',
                ]
            )]

        return [PluginResult(
            vulnerable=False, target=target, port=port,
            description='No directory listing detected'
        )]

    async def _check_path(self, target: str, port: int, path: str) -> bool:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(target, port), timeout=5
        )

        req = f'GET {path} HTTP/1.1\r\nHost: {target}\r\nUser-Agent: Centra/1.0\r\nConnection: close\r\n\r\n'
        writer.write(req.encode())
        await writer.drain()

        response = b''
        while True:
            chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
            if not chunk:
                break
            response += chunk
            if len(response) > 16384:
                break

        writer.close()
        await writer.wait_closed()

        header, _, body = response.partition(b'\r\n\r\n')
        status_line = header.split(b'\r\n')[0] if header else b''

        if b'200' not in status_line and b'200 OK' not in status_line:
            return False

        body_lower = body.lower()

        if b'index of /' in body_lower or b'index of' in body_lower:
            return True

        if b'parent directory' in body_lower and b'/' in body_lower:
            return True

        dir_hints = sum(1 for p in self.LISTING_PATTERNS if p.lower() in body_lower)
        dir_hints += body_lower.count(b'<a href=\"') / 3
        dir_hints += body_lower.count(b'size:') + body_lower.count(b'[dir]')

        return dir_hints >= 2
