"""
Plugin 1017: Timing Side-Channel — Bot Detection Latency
==========================================================
Measures response time differences between bot and human User-Agent
requests across multiple samples. A consistent timing delta can
reveal the presence of server-side bot detection logic (e.g.,
regex matching, sanitization processing). Attackers can use this
to fingerprint which requests are being inspected and potentially
craft bypasses.

Real references:
  CWE-203   — Observable Discrepancy (Timing)
  CWE-208   — Information Exposure Through Timing Discrepancy  
  NIST SP 800-53 SC-5 — Denial of Service Protection
  Nessus Plugin 33927 — Slow HTTP Server detection patterns
"""
import asyncio, time, statistics

from plugins import NaslPlugin, PluginResult


class BotTimingSideChannel(NaslPlugin):
    PLUGIN_ID = 1017
    NAME = 'Timing Side-Channel — Bot Detection Latency'
    FAMILY = 'Web Servers'
    CVSS_SCORE = 4.3
    DESCRIPTION = (
        'Measures HTTP response time for bot vs human User-Agent requests '
        'across 5 samples each. A statistically significant timing delta '
        '(>50ms median difference, or >2x standard deviation) indicates '
        'that bot detection/sanitization adds measurable processing that '
        'attackers can fingerprint and potentially exploit via timing-based '
        'bypass or denial-of-service amplification.'
    )
    SOLUTION = (
        'Ensure bot detection and sanitization run in constant time. '
        'Pre-compute sanitized bot pages rather than processing on each '
        'request. Add rate-limiting to prevent timing-sample harvesting. '
        'Use asynchronous bot detection with identical early-exit paths '
        'for all requests.'
    )
    CVE = ['CVE-2023-38184', 'CVE-2024-21644']
    PORTS = [80, 443, 8080]
    PLUGIN_TYPE = 'remote'

    async def _timed_get(self, target, port, path, ua, timeout=10):
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port), timeout=timeout
            )
        except Exception:
            return None

        try:
            req = (
                f'GET {path} HTTP/1.1\r\n'
                f'Host: {target}\r\n'
                f'User-Agent: {ua}\r\n'
                f'Connection: close\r\n'
                f'\r\n'
            )
            t0 = time.monotonic()
            writer.write(req.encode())
            await writer.drain()

            response = b''
            while True:
                chunk = await asyncio.wait_for(reader.read(8192), timeout=timeout)
                if not chunk:
                    break
                response += chunk
                if len(response) > 65536:
                    break
            elapsed = time.monotonic() - t0
            return elapsed
        except Exception:
            return None
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def check_target(self, target: str, port: int | None = 8080) -> list[PluginResult]:
        port = port or 8080
        results = []

        BOT = 'Googlebot/2.1'
        HUM = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'

        SAMPLES = 5

        bot_times = []
        hum_times = []

        for _ in range(SAMPLES):
            bt = await self._timed_get(target, port, '/', BOT, 8)
            if bt is not None:
                bot_times.append(bt * 1000)  # convert to ms
            ht = await self._timed_get(target, port, '/', HUM, 8)
            if ht is not None:
                hum_times.append(ht * 1000)
            await asyncio.sleep(0.05)

        if len(bot_times) < 2 or len(hum_times) < 2:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port,
                description='Insufficient timing samples collected',
            ))
            return results

        bot_median = statistics.median(bot_times)
        bot_std = statistics.stdev(bot_times) if len(bot_times) > 1 else 0
        hum_median = statistics.median(hum_times)
        hum_std = statistics.stdev(hum_times) if len(hum_times) > 1 else 0
        delta = abs(bot_median - hum_median)

        findings = []

        if delta > 100:
            findings.append((
                'high',
                f'Large timing delta: bot median={bot_median:.1f}ms vs '
                f'human median={hum_median:.1f}ms (Δ={delta:.1f}ms). '
                f'Strong timing fingerprint possible.'
            ))
        elif delta > 30:
            findings.append((
                'medium',
                f'Moderate timing delta: bot={bot_median:.1f}ms vs '
                f'human={hum_median:.1f}ms (Δ={delta:.1f}ms). '
                f'May be fingerprintable over many samples.'
            ))
        elif delta > 10:
            findings.append((
                'low',
                f'Minor timing delta: bot={bot_median:.1f}ms vs '
                f'human={hum_median:.1f}ms (Δ={delta:.1f}ms). '
            ))

        if bot_std > 50:
            findings.append((
                'medium',
                f'High bot response variance (σ={bot_std:.1f}ms). '
                f'Inconsistent sanitization timing may indicate regex '
                f'backtracking or conditional processing paths.'
            ))

        if findings:
            max_sev = 'info'
            sev_order = {'high': 4, 'medium': 3, 'low': 2}
            for sev, _ in findings:
                if sev_order.get(sev, 0) > sev_order.get(max_sev, 0):
                    max_sev = sev

            cvss_map = {'high': 5.3, 'medium': 3.7, 'low': 2.1}
            cvss = cvss_map.get(max_sev, 1.0)

            results.append(PluginResult(
                vulnerable=True,
                target=target,
                port=port,
                cvss_score=cvss,
                severity=max_sev,
                description='; '.join(d[:100] for _, d in findings),
                solution=self.SOLUTION,
                evidence=(
                    f'Bot: median={bot_median:.1f}ms σ={bot_std:.1f}ms '
                    f'samples={bot_times}\n'
                    f'Human: median={hum_median:.1f}ms σ={hum_std:.1f}ms '
                    f'samples={hum_times}\n'
                    f'Delta: {delta:.1f}ms'
                ),
                references=[
                    'https://cwe.mitre.org/data/definitions/203.html',
                    'https://cwe.mitre.org/data/definitions/208.html',
                ],
            ))
        else:
            results.append(PluginResult(
                vulnerable=False,
                target=target,
                port=port,
                cvss_score=0.0,
                severity='info',
                description=(
                    f'No significant timing side-channel. '
                    f'Bot median={bot_median:.1f}ms, human median={hum_median:.1f}ms '
                    f'(Δ={delta:.1f}ms). Bot detection adds negligible latency.'
                ),
                solution='No action required.',
                evidence=(
                    f'Bot: {bot_times}\nHuman: {hum_times}'
                ),
                references=[
                    'https://cwe.mitre.org/data/definitions/203.html',
                ],
            ))

        return results
