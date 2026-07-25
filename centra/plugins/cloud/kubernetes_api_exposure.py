"""
Plugin 1047: Kubernetes API Exposure Detection
=================================================
Detects publicly accessible Kubernetes API servers.
Real CVEs: CVE-2023-39226, CVE-2022-3294
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class KubernetesApiExposure(NaslPlugin):
    PLUGIN_ID = 1047
    NAME = 'Kubernetes API Exposure Detection'
    FAMILY = 'Cloud Infrastructure'
    CVSS_SCORE = 7.5
    DESCRIPTION = (
        'A Kubernetes API server is accessible without authentication. '
        'Exposed K8s API servers allow attackers to enumerate pods, secrets, '
        'deployments, and potentially execute arbitrary code in the cluster.'
    )
    SOLUTION = (
        'Restrict API server access to authorized IP ranges. Enable '
        'authentication (OIDC, client certs). Use NetworkPolicies. '
        'Enable audit logging. Do not expose kube-apiserver publicly.'
    )
    CVE = ['CVE-2023-39226', 'CVE-2022-3294']
    PORTS = [443, 6443]

    SSL_CTX = None

    K8S_PATHS = [
        '/api',
        '/api/v1',
        '/healthz',
        '/readyz',
        '/livez',
        '/openapi/v2',
        '/version',
        '/api/v1/namespaces',
        '/api/v1/pods',
    ]

    async def check_target(self, target: str, port: int | None = 6443) -> list[PluginResult]:
        port = port or 6443
        if self.SSL_CTX is None:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            type(self).SSL_CTX = ctx

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port, ssl=self.SSL_CTX), timeout=6
            )

            req = (
                f'GET /api HTTP/1.1\r\n'
                f'Host: {target}:{port}\r\n'
                f'Authorization: Bearer test\r\n'
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
                if len(response) > 16384:
                    break

            writer.close()
            await writer.wait_closed()

            header_section = response.split(b'\r\n\r\n')[0].decode('utf-8', errors='ignore')
            status_line = header_section.split('\r\n')[0] if header_section else ''

            body = response.split(b'\r\n\r\n', 1)
            body_text = body[1].decode('utf-8', errors='ignore')[:2000] if len(body) > 1 else ''

            is_k8s = ('kind' in body_text and 'apiVersion' in body_text) or \
                     ('kubernetes' in header_section.lower()) or \
                     ('"groupVersion"' in body_text) or \
                     ('401 Unauthorized' in status_line and 'api' in body_text)

            if '200 OK' in status_line and is_k8s:
                return [PluginResult(
                    vulnerable=True,
                    target=target,
                    port=port,
                    cvss_score=self.CVSS_SCORE,
                    severity='critical',
                    description=f'Kubernetes API server accessible — unauthenticated access to /api',
                    solution=self.SOLUTION,
                    evidence=f'K8s API responded with 200 OK — body excerpt: {body_text[:150]}',
                    references=[
                        'https://nvd.nist.gov/vuln/detail/CVE-2023-39226',
                        'https://www.tenable.com/plugins/nessus/157476',
                    ]
                )]

            if '401 Unauthorized' in status_line or '403 Forbidden' in status_line:
                if is_k8s:
                    return [PluginResult(
                        vulnerable=True,
                        target=target,
                        port=port,
                        cvss_score=5.3,
                        severity='medium',
                        description=f'Kubernetes API server exposed (requires auth — but publicly reachable)',
                        solution=self.SOLUTION,
                        evidence=f'K8s API at {target}:{port} is publicly reachable (HTTP {status_line.split()[1]})',
                        references=[
                            'https://nvd.nist.gov/vuln/detail/CVE-2022-3294',
                        ]
                    )]

        except (ssl.SSLError, asyncio.TimeoutError, ConnectionRefusedError, OSError):
            pass

        return [PluginResult(
            vulnerable=False, target=target, port=port,
            description='No accessible Kubernetes API server detected'
        )]
