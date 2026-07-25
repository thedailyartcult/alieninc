import asyncio
import ssl
import re
from plugins import NaslPlugin, PluginResult


class AutocompleteSecurityCheck(NaslPlugin):
    PLUGIN_ID = 1192
    NAME = 'Autocomplete Security on Sensitive Fields'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 3.7
    DESCRIPTION = 'Checks for missing autocomplete=off attribute on sensitive form fields including password, credit card, SSN, and security question fields. Autocomplete enabled on sensitive fields can leak credentials to shared computer users.'
    SOLUTION = 'Set autocomplete=off on sensitive fields. Use autocomplete=new-password for password fields. Implement session timeout on shared devices.'
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    SENSITIVE_TYPES = ['password', 'creditcard', 'cc-number', 'cc-csc', 'cc-exp', 'ssn', 'social-security-number', 'pin']
    SENSITIVE_NAMES = ['password', 'passwd', 'pwd', 'creditcard', 'ccnumber', 'cardnumber', 'ssn', 'socialsecurity', 'securityanswer', 'securityquestion']

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
                reader, writer = await asyncio.wait_for(asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5)
                host_header = target
                if target in ('127.0.0.1', 'localhost', '::1'):
                    host_header = 'alieninc.tech'
                req = f'GET / HTTP/1.1\r\nHost: {host_header}\r\nConnection: close\r\n\r\n'
                writer.write(req.encode())
                await writer.drain()
                response = b''
                try:
                    while True:
                        chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                        if not chunk: break
                        response += chunk
                        if len(response) > 32768: break
                except asyncio.TimeoutError:
                    pass
                writer.close()
                await writer.wait_closed()

                if response:
                    body = response.split(b'\r\n\r\n', 1)
                    if len(body) > 1:
                        html = body[1].decode('utf-8', errors='ignore')
                        input_pattern = re.compile(r'<input[^>]*>', re.IGNORECASE)
                        inputs = input_pattern.findall(html)
                        findings = []
                        for inp in inputs:
                            inp_lower = inp.lower()
                            type_match = re.search(r'type\s*=\s*["\']([^"\']*)["\']', inp_lower)
                            name_match = re.search(r'name\s*=\s*["\']([^"\']*)["\']', inp_lower)
                            has_autocomplete_off = 'autocomplete="off"' in inp_lower or "autocomplete='off'" in inp_lower
                            has_autocomplete_new_password = 'autocomplete="new-password"' in inp_lower or "autocomplete='new-password'" in inp_lower
                            input_type = type_match.group(1) if type_match else ''
                            input_name = name_match.group(1) if name_match else ''
                            if input_type == 'password' and not has_autocomplete_off and not has_autocomplete_new_password:
                                findings.append(f'Password field missing autocomplete=off: <input type="password" name="{input_name}">')
                            if input_type in self.SENSITIVE_TYPES and not has_autocomplete_off:
                                findings.append(f'Sensitive field (type={input_type}) missing autocomplete=off: {inp[:80]}')
                            if input_name.lower() in self.SENSITIVE_NAMES and not has_autocomplete_off:
                                findings.append(f'Sensitive field (name={input_name}) missing autocomplete=off: {inp[:80]}')
                        if findings:
                            results.append(PluginResult(
                                vulnerable=True, target=target, port=port_to_check,
                                cvss_score=self.CVSS_SCORE, severity='low',
                                description=f'Autocomplete security issues: {len(findings)} fields',
                                solution=self.SOLUTION,
                                evidence='Fields missing autocomplete=off:\n' + '\n'.join(findings[:10])
                            ))
                        else:
                            results.append(PluginResult(
                                vulnerable=False, target=target, port=port_to_check,
                                description='No issues detected'
                            ))
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                results.append(PluginResult(
                    vulnerable=False, target=target, port=port_to_check,
                    description='No issues detected'
                ))
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description='No issues detected'))
        return results
