"""
Plugin 1244: Cryptominer / Web Miner Detection
==============================================
Detects unauthorized cryptocurrency mining scripts (cryptojacking)
running on the website.
"""
import asyncio
import re
import ssl

from plugins import NaslPlugin, PluginResult


class CryptoMinerDetection(NaslPlugin):
    PLUGIN_ID = 1244
    NAME = 'Cryptominer / Web Miner Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 5.3
    DESCRIPTION = (
        'Detects unauthorized cryptocurrency mining scripts (cryptojacking) '
        'running on the website. Identifies known miner domains, miner script '
        'patterns (CoinHive, CryptoLoot, Minr), and excessive CPU usage triggers '
        'via Web Workers or WASM.'
    )
    SOLUTION = (
        'Implement Content-Security-Policy that blocks unknown script sources. '
        'Monitor for unauthorized script injections. Use SRI on all scripts. '
        'Regular security audits.'
    )
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    MINER_DOMAINS = [
        'coinhive.com', 'coin-hive.com', 'cryptoloot.pro',
        'minr.pw', 'coin-have.com', 'coinnebula.com',
        'jsecoin.com', 'mineralt.io', 'webmine.pro',
        'crypto-loot.com', 'afminr.com', 'bmnr.io',
        'cnhv.co', 'davanu.com', 'gastronomiaitalianamx.com',
        'hashing.win', 'hostpeer.net', 'kiziw.com',
        'lablog.ga', 'libsf.net', 'lmodr.biz',
        'masterminer.me', 'miner.pr0fit', 'miner.video',
        'minerr.biz', 'mining.best', 'mining.gallery',
        'mining.network', 'mining.pm', 'monerominer.rocks',
        'moneropool.com', 'nimiq.watch', 'pmo异味.com',
        'pool.minergate.com', 'reauthenticator.com',
        'rocketr.miner', 'seriousmining.com', 'sneakyminer.com',
        'stratum-miner.com', 'tlsminer.com', 'tlsmines.com',
        'v4.miner', 'virusminer.com', 'webminerpool.com',
        'whereismyminer.com', 'wisewebminer.com',
    ]

    MINER_PATTERNS = [
        (r'CoinHive\.', 'CoinHive API reference'),
        (r'CryptoLoot\.', 'CryptoLoot API reference'),
        (r'new\s+(CoinHive|CryptoLoot|Minr)\s*\(', 'miner constructor'),
        (r'\.start\s*\(\s*(?:CoinHive|CryptoLoot)', 'miner start call'),
        (r'\.stop\s*\(\s*(?:CoinHive|CryptoLoot)', 'miner stop call'),
        (r'\.getTotalAcceptedHashes\s*\(', 'miner hash accounting'),
        (r'\.getHashesPerSecond\s*\(', 'miner hashrate check'),
        (r'miner\s*=\s*new', 'miner instantiation'),
        (r'miner\.(start|stop|setThrottle|getHashesPerSecond)', 'miner method call'),
        (r'\.setThrottle\s*\(', 'miner throttle setting'),
        (r'\.isRunning\s*\(\s*\)', 'miner running check'),
        (r'\.on\s*\(\s*["\'](?:found|accepted|error|job)', 'miner event handler'),
        (r'WebAssembly\.instantiate.*miner', 'WASM miner detection'),
        (r'worker\s*\.\s*postMessage.*mine', 'WebWorker miner message'),
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
                        if len(response) > 65536:
                            break
                except asyncio.TimeoutError:
                    pass
                writer.close()
                await writer.wait_closed()
                body = response.split(b'\r\n\r\n', 1)
                if len(body) > 1:
                    html = body[1].decode('utf-8', errors='ignore')
                    domain_matches = [d for d in self.MINER_DOMAINS if d in html.lower()]
                    pattern_matches = []
                    for pattern, label in self.MINER_PATTERNS:
                        if re.search(pattern, html, re.IGNORECASE):
                            pattern_matches.append(label)
                    if domain_matches or pattern_matches:
                        results.append(PluginResult(
                            vulnerable=True,
                            target=target,
                            port=port_to_check,
                            cvss_score=self.CVSS_SCORE,
                            severity='medium',
                            description='Cryptominer script(s) detected on page',
                            solution=self.SOLUTION,
                            evidence=f'Domains: {domain_matches}, patterns: {pattern_matches}',
                            references=[
                                'https://en.wikipedia.org/wiki/Cryptojacking',
                                'https://portswigger.net/daily-swig/cryptojacking',
                            ]
                        ))
                    else:
                        results.append(PluginResult(
                            vulnerable=False,
                            target=target,
                            port=port_to_check,
                            description='No cryptominer indicators detected'
                        ))
                        break
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass
        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='No cryptominer indicators detected'
            ))
        return results
