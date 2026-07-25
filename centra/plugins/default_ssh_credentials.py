"""
Plugin 1036: SSH Default Configuration Detection
===================================================
Identifies SSH servers with default/weak configurations through
banner fingerprinting and algorithm analysis. Without SSH client
libraries, this performs banner-based analysis matching Nessus
approach for identifying default-credential-prone installations.
Real CVEs: CVE-2024-3094 (SSH backdoor), CVE-2020-15778 (OpenSSH injection)
"""
import asyncio
import struct

from plugins import NaslPlugin, PluginResult


class SshDefaultConfig(NaslPlugin):
    PLUGIN_ID = 1036
    NAME = 'SSH Default Configuration Detection'
    FAMILY = 'Authentication & Access Control'
    CVSS_SCORE = 8.1
    DESCRIPTION = (
        'The SSH server banner or algorithm negotiation indicates a default '
        'or outdated configuration associated with devices that commonly ship '
        'with default credentials (IoT, embedded systems, legacy appliances).'
    )
    SOLUTION = (
        'Disable default accounts. Enforce strong passwords. Use SSH key-based '
        'authentication. Implement account lockout and rate limiting on SSH. '
        'Upgrade to a supported OpenSSH version (7.4+).'
    )
    CVE = ['CVE-2024-3094', 'CVE-2020-15778']
    PORTS = [22]

    SUSPICIOUS_BANNERS = [
        (b'dropbear', 'Dropbear SSH — commonly used in IoT/embedded devices with default credentials'),
        (b'Raspbian', 'Raspbian default SSH (pi/raspberry)'),
        (b'OpenWrt', 'OpenWRT default SSH (root/<blank>)'),
        (b'DD-WRT', 'DD-WRT default SSH (root/admin)'),
        (b'Tomato', 'Tomato firmware default SSH'),
        (b'OpenSSH_5', 'OpenSSH 5.x (EOL 2016 — likely unmaintained, default creds possible)'),
        (b'OpenSSH_6', 'OpenSSH 6.x (EOL 2020 — likely unmaintained)'),
        (b'OpenSSH_7.0', 'OpenSSH 7.0 (vulnerable to CVE-2016-10009)'),
        (b'OpenSSH_7.1', 'OpenSSH 7.1 (vulnerable to CVE-2016-10009)'),
        (b'OpenSSH_7.2', 'OpenSSH 7.2 (multiple known vulns)'),
        (b'OpenSSH_7.3', 'OpenSSH 7.3 (multiple known vulns)'),
        (b'libssh', 'libssh default configuration'),
    ]

    WEAK_KEX_ALGOS = {
        b'diffie-hellman-group1-sha1',
        b'diffie-hellman-group-exchange-sha1',
        b'diffie-hellman-group14-sha1',
    }

    WEAK_CIPHERS = {
        b'aes128-cbc',
        b'aes192-cbc',
        b'aes256-cbc',
        b'3des-cbc',
        b'blowfish-cbc',
        b'arcfour',
        b'arcfour128',
        b'arcfour256',
        b'cast128-cbc',
    }

    async def check_target(self, target: str, port: int | None = 22) -> list[PluginResult]:
        port = port or 22
        issues = []
        evidence_lines = []
        banner_text = b''

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port), timeout=5
            )

            banner = await asyncio.wait_for(reader.read(512), timeout=3)
            if not banner or (b'SSH' not in banner and b'ssh' not in banner):
                writer.close()
                await writer.wait_closed()
                return [PluginResult(
                    vulnerable=False, target=target, port=port,
                    description='Service on port does not appear to be SSH'
                )]

            banner_text = banner.split(b'\r\n')[0].split(b'\n')[0].strip()
            evidence_lines.append(f'Banner: {banner_text.decode("utf-8", errors="replace")}')

            for pattern, desc in self.SUSPICIOUS_BANNERS:
                if pattern.lower() in banner_text.lower():
                    issues.append(f'Banner fingerprint: {desc}')
                    evidence_lines.append(f'Matched pattern: {pattern.decode()} — {desc}')

            try:
                kex_data = await self._read_ssh_kex_init(reader, writer)
                if kex_data:
                    weak_kex = self._check_weak_algorithms(kex_data)
                    issues.extend(weak_kex)
                    evidence_lines.extend(weak_kex)
            except Exception:
                pass

            writer.close()
            await writer.wait_closed()

        except (asyncio.TimeoutError, ConnectionRefusedError, OSError) as e:
            return [PluginResult(
                vulnerable=False, target=target, port=port,
                description=f'Port {port} not reachable'
            )]

        if issues:
            return [PluginResult(
                vulnerable=True,
                target=target,
                port=port,
                cvss_score=self.CVSS_SCORE,
                severity='high',
                description=f'SSH default configuration indicators: {len(issues)} finding(s)',
                solution=self.SOLUTION,
                evidence=' | '.join(evidence_lines),
                references=[
                    'https://nvd.nist.gov/vuln/detail/CVE-2023-38114',
                    'https://www.tenable.com/plugins/nessus/10468',
                ]
            )]

        return [PluginResult(
            vulnerable=False, target=target, port=port,
            description='SSH configuration appears standard — no default credential indicators',
            evidence=f'Banner: {banner_text.decode("utf-8", errors="replace") if banner_text else "N/A"}'
        )]

    async def _read_ssh_kex_init(self, reader, writer, banner: bytes = b'') -> bytes | None:
        ssh_ver = b'SSH-2.0-CentraScanner\r\n'
        writer.write(ssh_ver)
        await writer.drain()

        rest = b''
        while True:
            chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
            if not chunk:
                break
            rest += chunk
            if len(rest) > 8192 or (len(rest) >= 5 and rest[0] == 0x14):
                break

        if len(rest) >= 5 and rest[0] == 0x14:
            packet_len = struct.unpack('>I', rest[1:5])[0]
            expected = 5 + packet_len
            while len(rest) < expected:
                chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                if not chunk:
                    break
                rest += chunk
            return rest[:expected]
        return None

    def _check_weak_algorithms(self, kex_data: bytes) -> list[str]:
        issues = []
        if len(kex_data) < 6:
            return issues

        payload = kex_data[5:]
        pos = 1
        names = []
        for _ in range(7):
            if pos + 3 >= len(payload):
                break
            nlen = struct.unpack('>I', payload[pos:pos+4])[0]
            pos += 4
            if pos + nlen > len(payload):
                break
            names.append(payload[pos:pos+nlen].split(b','))
            pos += nlen

        if len(names) >= 2:
            kex_algos = names[0]
            weak_kex = [a for a in kex_algos if a in self.WEAK_KEX_ALGOS]
            if weak_kex:
                issues.append(f'Weak KEX algorithms: {b", ".join(weak_kex).decode("utf-8", errors="replace")}')
            weak_enc = [a for a in (names[1] if len(names) > 1 else []) if a in self.WEAK_CIPHERS]
            if weak_enc:
                issues.append(f'Weak encryption ciphers: {b", ".join(weak_enc).decode("utf-8", errors="replace")}')

        return issues
