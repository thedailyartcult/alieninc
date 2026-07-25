"""
Plugin 1135: Subdomain DNS Enumeration
========================================
Enumerates common subdomains via DNS resolution.
"""
import asyncio
import socket

from plugins import NaslPlugin, PluginResult


class SubdomainEnumeration(NaslPlugin):
    PLUGIN_ID = 1135
    NAME = 'Subdomain DNS Enumeration'
    FAMILY = 'Misc.'
    CVSS_SCORE = 3.7
    DESCRIPTION = (
        'Enumerates common subdomains via DNS resolution to discover exposed '
        'services. Common subdomains (www, mail, api, admin, dev, stage, test, '
        'dashboard, portal, cdn, static, assets, blog, wiki, docs, support, '
        'status, help, beta, demo) can reveal development servers, internal '
        'tools, or forgotten services.'
    )
    SOLUTION = (
        'Remove unnecessary DNS records. Use wildcard DNS denial. Ensure '
        'staging/dev subdomains are not accessible from the internet.'
    )
    CVE = []
    PORTS = [53, 80, 443]

    COMMON_SUBDOMAINS = [
        'www', 'mail', 'api', 'admin', 'dev', 'stage', 'test',
        'dashboard', 'portal', 'cdn', 'static', 'assets',
        'blog', 'wiki', 'docs', 'support', 'status', 'help',
        'beta', 'demo', 'app', 'web', 'm', 'mobile',
        'staging', 'development', 'production', 'vpn',
        'jenkins', 'gitlab', 'jira', 'confluence', 'grafana',
        'prometheus', 'kibana', 'elastic', 'redis', 'mysql',
        'db', 'database', 'backup', 'monitor', 'monitoring',
        'api-dev', 'api-staging', 'api-v1', 'api-v2',
        'auth', 'login', 'signin', 'register', 'sso',
        'adminer', 'phpmyadmin', 'pma', 'manager',
        'console', 'panel', 'cp', 'whm', 'cpanel',
        'ftp', 'sftp', 'ssh', 'remote', 'shell',
        'ns1', 'ns2', 'mx', 'pop', 'smtp', 'imap',
        'calendar', 'mailgun', 'sendgrid', 'sparkpost',
        'sentry', 'logs', 'log', 'syslog',
        's3', 'storage', 'files', 'uploads', 'media',
        'images', 'img', 'css', 'js', 'static2',
        'sandbox', 'playground', 'lab', 'demo2',
        'new', 'old', 'v2', 'v3', 'next', 'latest',
    ]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []

        domain = target
        if target in ('127.0.0.1', 'localhost', '::1'):
            domain = 'alieninc.tech'
        elif target.replace('.', '').isdigit():
            return [PluginResult(
                vulnerable=False, target=target, port=0,
                description='Target is an IP address, DNS enumeration not applicable'
            )]

        resolved = []

        sem = asyncio.Semaphore(20)

        async def try_sub(sub: str) -> tuple[str, str, str] | None:
            full = f'{sub}.{domain}'
            async with sem:
                try:
                    addrs = await asyncio.wait_for(
                        asyncio.get_event_loop().getaddrinfo(full, 80, type=socket.SOCK_STREAM),
                        timeout=3
                    )
                    ips = list(set(a[4][0] for a in addrs))
                    if ips:
                        return (sub, full, ', '.join(ips))
                except Exception:
                    pass
            return None

        tasks = [try_sub(sub) for sub in self.COMMON_SUBDOMAINS]
        done = await asyncio.gather(*tasks)

        for d in done:
            if d:
                resolved.append(d)

        if resolved:
            results.append(PluginResult(
                vulnerable=True, target=target, port=0,
                cvss_score=self.CVSS_SCORE, severity='low',
                description=f'DNS enumeration: {len(resolved)} subdomain(s) resolve for {domain}',
                solution=self.SOLUTION,
                evidence='; '.join(f'{s} ({d}) -> {i}' for s, d, i in resolved),
                references=[
                    'https://owasp.org/www-community/attacks/DNS_Enumeration',
                    'https://www.tenable.com/plugins/nessus/10656',
                ]
            ))
        else:
            results.append(PluginResult(
                vulnerable=False, target=target, port=0,
                description=f'No additional subdomains resolved for {domain}'
            ))

        return results
