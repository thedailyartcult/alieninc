"""
Plugin 1079: Spring4Shell — Spring Framework RCE (CVE-2022-22965)
===================================================================
Detects Spring4Shell vulnerability in Spring Framework applications.
Real CVE: CVE-2022-22965 (CVSS 9.8)
"""
import asyncio
import ssl
import urllib.parse

from plugins import NaslPlugin, PluginResult


class Spring4ShellDetection(NaslPlugin):
    PLUGIN_ID = 1079
    NAME = 'Spring4Shell Spring Framework RCE Detection (CVE-2022-22965)'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 9.8
    DESCRIPTION = (
        'Spring Framework 5.3.x before 5.3.18 and 5.2.x before 5.2.20 running on '
        'JDK 9+ may be vulnerable to remote code execution via data binding. The '
        'exploit requires the application to run on Tomcat as a WAR deployment. An '
        'attacker can send specially crafted HTTP parameters using dot-notation to '
        'traverse the Java ClassLoader and modify Tomcat access log configuration '
        'to write a JSP webshell.'
    )
    SOLUTION = (
        'Upgrade Spring Framework to 5.3.18 or 5.2.20 (or later). For Spring Boot, '
        'upgrade to 2.6.6 or 2.5.12. As an immediate mitigation, set disallowedFields '
        'on DataBinder to block class.* parameter patterns.'
    )
    CVE = ['CVE-2022-22965']
    PORTS = [8080, 8443, 80, 443]

    SPRING_PATHS = ['/', '/api', '/app', '/spring', '/actuator']

    PROBE_PARAMS = [
        'class.module.classLoader.URLs[0]',
        'class.module.classLoader.resources.context.parent.pipeline.first.pattern',
    ]

    PROBE_VALUE = '%25%7Bc%7Di'

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

                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, port_to_check, ssl=ctx),
                    timeout=5
                )

                host_header = target
                if target in ('127.0.0.1', 'localhost', '::1'):
                    host_header = 'alieninc.tech'

                for path in self.SPRING_PATHS:
                    param_str = '&'.join(
                        f'{p}={self.PROBE_VALUE}' for p in self.PROBE_PARAMS
                    )
                    get_path = f'{path}?{param_str}'

                    req = (
                        f'GET {get_path} HTTP/1.1\r\n'
                        f'Host: {host_header}\r\n'
                        f'User-Agent: Centra/1.0\r\n'
                        f'Connection: close\r\n\r\n'
                    )
                    writer.write(req.encode())
                    await writer.drain()

                    response = b''
                    try:
                        while True:
                            chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                            if not chunk:
                                break
                            response += chunk
                            if len(response) > 8192:
                                break
                    except asyncio.TimeoutError:
                        pass

                    if response:
                        status_line = response.split(b'\r\n')[0].decode('utf-8', errors='ignore')
                        body_start = response.find(b'\r\n\r\n')
                        body = response[body_start + 4:] if body_start != -1 else b''
                        body_str = body.decode('utf-8', errors='ignore')

                        classloader_hints = [
                            'class.module.classLoader',
                            'ClassLoader',
                            'java.lang.ClassLoader',
                            'BeanPropertyBindingResult',
                            'InvalidPropertyException',
                            'FieldError',
                            'org.springframework',
                        ]
                        found_hints = [h for h in classloader_hints if h.lower() in body_str.lower()]

                        error_500 = b'500' in response[:100]
                        error_400 = b'400' in response[:100]

                        if found_hints or (error_500 and any(h in body_str.lower() for h in ['classloader', 'classload'])):
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=self.CVSS_SCORE,
                                severity='critical',
                                description=(
                                    f'Spring application on port {port_to_check} reflected '
                                    f'ClassLoader-related content — potentially vulnerable to Spring4Shell'
                                ),
                                solution=self.SOLUTION,
                                evidence=(
                                    f'Path: {path}, Status: {status_line}, '
                                    f'Reflected ClassLoader hints: {found_hints}'
                                ),
                                references=[
                                    'https://nvd.nist.gov/vuln/detail/CVE-2022-22965',
                                    'https://www.tenable.com/plugins/nessus/159235',
                                ]
                            ))
                            break

                writer.close()
                await writer.wait_closed()

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass

        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='No Spring4Shell indicators detected on checked ports'
            ))

        return results
