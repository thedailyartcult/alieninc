"""
Plugin 1039: Outdated JavaScript Library Detection
=====================================================
Detects known-vulnerable JavaScript library versions served by the application.
Real CVEs: CVE-2023-26136, CVE-2022-25869, CVE-2021-23368
"""
import asyncio
import re

from plugins import NaslPlugin, PluginResult


class OutdatedJsLibraries(NaslPlugin):
    PLUGIN_ID = 1039
    NAME = 'Outdated JavaScript Library Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 6.1
    DESCRIPTION = (
        'The web application includes known-vulnerable JavaScript libraries. '
        'These libraries contain publicly disclosed vulnerabilities that can '
        'be exploited by attackers to compromise the application or its users.'
    )
    SOLUTION = (
        'Update all JavaScript libraries to their latest secure versions. '
        'Use Subresource Integrity (SRI) tags. Implement a Software Bill of '
        'Materials (SBOM) to track library versions.'
    )
    CVE = ['CVE-2023-26136', 'CVE-2022-25869', 'CVE-2021-23368']
    PORTS = [80, 443]

    VULNERABLE_PATTERNS = [
        (r'jquery[-.]1\.(?:[0-9]|1[0-2])\b', 'jQuery < 1.12', 'CVE-2020-11023'),
        (r'jquery[-.]2\.(?:[0-9]|1[0-9]|2[0-4])\b', 'jQuery 2.x < 2.25', 'CVE-2020-11023'),
        (r'jquery[-.]3\.[0-4]\.', 'jQuery 3.x < 3.5', 'CVE-2020-11022'),
        (r'jquery[.-]?(?:min\.)?js.*version["\']?\s*[:=]\s*["\']?1\.(?:[0-9]|1[0-2])\b', 'jQuery < 1.12', 'CVE-2020-11023'),
        (r'jquery[.-]?(?:min\.)?js.*version["\']?\s*[:=]\s*["\']?2\.(?:[0-9]|1[0-9]|2[0-4])\b', 'jQuery 2.x < 2.25', 'CVE-2020-11023'),
        (r'jquery[.-]?(?:min\.)?js.*version["\']?\s*[:=]\s*["\']?3\.[0-4]\.', 'jQuery 3.x < 3.5', 'CVE-2020-11022'),
        (r'angular.*version["\']?\s*[:=]\s*["\']?1\.(?:[0-9]|1[0-5])\.', 'AngularJS < 1.6', 'CVE-2022-25869'),
        (r'react.*version["\']?\s*[:=]\s*["\']?(?:0\.|15\.|16\.[0-8])', 'React < 16.9', 'CVE-2021-23368'),
        (r'vue.*version["\']?\s*[:=]\s*["\']?1\.', 'Vue.js 1.x (EOL)', 'CVE-2023-26136'),
        (r'vue.*version["\']?\s*[:=]\s*["\']?2\.(?:[0-9]|1[0-6])\.', 'Vue.js 2.x < 2.17', 'CVE-2023-26136'),
        (r'bootstrap.*version["\']?\s*[:=]\s*["\']?3\.', 'Bootstrap 3.x (EOL)', 'CVE-2019-14041'),
        (r'bootstrap.*version["\']?\s*[:=]\s*["\']?4\.[0-5]\.', 'Bootstrap 4.x < 4.6', 'CVE-2019-8331'),
        (r'dojo.*version["\']?\s*[:=]\s*["\']?1\.(?:[0-9]|1[0-5])\.', 'Dojo < 1.16', 'CVE-2021-23429'),
        (r'prototype.*version["\']?\s*[:=]\s*["\']?1\.(?:[0-6])\.', 'PrototypeJS < 1.7', 'CVE-2020-27569'),
        (r'mootools.*version["\']?\s*[:=]\s*["\']?1\.(?:[0-5])\.', 'MooTools < 1.6', 'CVE-2019-12957'),
    ]

    COMMON_LIB_PATHS = [
        '/',
        '/js/',
        '/assets/',
        '/static/',
        '/scripts/',
        '/wp-includes/js/',
    ]

    async def check_target(self, target: str, port: int | None = 80) -> list[PluginResult]:
        port = port or 80
        all_body = b''

        for lib_path in self.COMMON_LIB_PATHS:
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, port), timeout=5
                )

                req = f'GET {lib_path} HTTP/1.1\r\nHost: {target}\r\nUser-Agent: Centra/1.0\r\nConnection: close\r\n\r\n'
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

                header, _, body = response.partition(b'\r\n\r\n')
                if header and b'200' in header.split(b'\r\n')[0]:
                    all_body += body

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
                pass

        if not all_body:
            return [PluginResult(
                vulnerable=False, target=target, port=port,
                description='Could not retrieve page content for JS library analysis'
            )]

        text = all_body.decode('utf-8', errors='ignore')
        findings = []

        for pattern, lib_name, cve in self.VULNERABLE_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                findings.append((lib_name, cve))

        deduped = list(dict.fromkeys(findings))

        if deduped:
            libs_found = ', '.join(lib for lib, _ in deduped)
            cves_found = ', '.join(cve for _, cve in deduped)
            return [PluginResult(
                vulnerable=True,
                target=target,
                port=port,
                cvss_score=self.CVSS_SCORE,
                severity='medium',
                description=f'Outdated JS libraries detected: {libs_found}',
                solution=self.SOLUTION,
                evidence=f'Vulnerable libraries: {libs_found}. CVEs: {cves_found}',
                references=[
                    'https://nvd.nist.gov/vuln/detail/' + cve for _, cve in deduped
                ]
            )]

        return [PluginResult(
            vulnerable=False, target=target, port=port,
            description='No outdated JavaScript libraries detected'
        )]
