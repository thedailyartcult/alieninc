"""
Centra Bulk Plugin Generator
Generates Python PluginResult-format plugins from a CSV definition file.

Usage:
  python3 plugin_generator.py --csv plugins.csv --output-dir ../plugins/ --start-id 1386
"""

import csv
import os
import re
import sys
from pathlib import Path


TEMPLATE = '''import asyncio
{ssl_import}
from plugins import NaslPlugin, PluginResult


class {class_name}(NaslPlugin):
    PLUGIN_ID = {plugin_id}
    NAME = "{name}"
    DESCRIPTION = "{description}"
    SOLUTION = "{solution}"
    CVSS_SCORE = {cvss}
    SEVERITY = "{severity}"
    FAMILY = "{family}"
    CVE = {cve_list}
    PORTS = [{ports}]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for p in ([port] if port else self.PORTS):
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, p{ssl_args}), timeout=5
                )
{detection_code}
                resp = await asyncio.wait_for(reader.read({read_size}), timeout=5)
                writer.close()
                await writer.wait_closed()
                body = resp.decode("utf-8", errors="replace")
{vuln_check}
            except Exception:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description="Could not connect",
                    solution="", evidence="", references=[]
                ))
        return results
'''


def sanitize(s, max_len=80):
    result = s.replace("\\", "\\\\").replace('"', '\\"').replace("\r", " ").replace("\n", " ")
    result = ''.join(c for c in result if ord(c) >= 32 or c in '\n\t')
    result = result.strip()[:max_len]
    # Avoid trailing backslash (escapes closing quote in template)
    while result.endswith("\\"):
        result = result[:-1]
    return result


def make_class_name(name, plugin_id):
    cn = re.sub(r'[^a-zA-Z0-9]', '', name.title())[:40]
    if not cn or cn[0].isdigit():
        cn = f"Vuln{plugin_id}"
    return f"{cn}Plugin"


def generate_plugin(row, plugin_id):
    name = row.get("name", f"Plugin {plugin_id}")
    description = row.get("description", name)
    solution = row.get("solution", "Apply vendor patches.")
    cvss = float(row.get("cvss", "5.0"))
    severity = row.get("severity", "Medium")
    family = row.get("family", "Web Security")
    cve = row.get("cve", "")
    ports = row.get("ports", "80, 443")
    detect_type = row.get("type", "path")
    detect_path = row.get("path", "/")
    detect_indicator = row.get("indicator", "")
    detect_header = row.get("header", "")
    read_size = row.get("read_size", "4096")
    use_ssl = row.get("ssl", "false").lower() == "true"

    if use_ssl:
        ssl_import = "import ssl"
        ssl_args = ', ssl=ssl.create_default_context()'
    else:
        ssl_import = ""
        ssl_args = ""

    cve_list = []
    if cve:
        cve_list = [c.strip() for c in cve.split(";") if c.strip().startswith("CVE-")]
    cve_str = repr(cve_list) if cve_list else "[]"

    cn = make_class_name(name, plugin_id)
    name_s = sanitize(name, 80)
    desc_s = sanitize(description, 200)
    sol_s = sanitize(solution, 200)

    detection_code = ""
    vuln_check = ""
    path_encoded = detect_path.replace("\\", "\\\\").replace('"', '\\"')

    if detect_type == "header":
        detection_code = f'''                request = (
                    f"GET / HTTP/1.1\\r\\n"
                    f"Host: {{target}}\\r\\n"
                    f"User-Agent: CentraScanner/1.0\\r\\n"
                    f"Accept: */*\\r\\n"
                    f"Connection: close\\r\\n\\r\\n"
                )
                writer.write(request.encode())
                await writer.drain()
                headers_resp = await asyncio.wait_for(reader.readuntil(b"\\r\\n\\r\\n"), timeout=5)'''
        vuln_check = f'''                headers_lower = headers_resp.decode("utf-8", errors="replace").lower()
                has_header = "{detect_header.lower()}" in headers_lower
                if {f'not has_header' if row.get('negate', 'false').lower() == 'true' else 'has_header'}:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                        description=self.DESCRIPTION,
                        solution=self.SOLUTION,
                        evidence=f"{'Missing' if row.get('negate', 'false').lower() == 'true' else 'Found'} header: {detect_header}",
                        references=self.CVE if self.CVE else []
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description="Check passed",
                        solution="", evidence="", references=[]
                    ))'''

    elif detect_type == "cookie":
        detection_code = f'''                request = (
                    f"GET / HTTP/1.1\\r\\n"
                    f"Host: {{target}}\\r\\n"
                    f"User-Agent: CentraScanner/1.0\\r\\n"
                    f"Accept: */*\\r\\n"
                    f"Connection: close\\r\\n\\r\\n"
                )
                writer.write(request.encode())
                await writer.drain()'''
        vuln_check = f'''                found_cookies = []
                for line in body.split("\\r\\n"):
                    if "set-cookie" in line.lower():
                        found_cookies.append(line)
                missing_flags = []
                if found_cookies:
                    for sc in found_cookies:
                        if "secure" not in sc.lower():
                            missing_flags.append("Secure")
                        if "httponly" not in sc.lower():
                            missing_flags.append("HttpOnly")
                        if "samesite" not in sc.lower():
                            missing_flags.append("SameSite")
                if missing_flags:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                        description=self.DESCRIPTION,
                        solution=self.SOLUTION,
                        evidence=f"Missing flags: {{', '.join(missing_flags)}}",
                        references=self.CVE if self.CVE else []
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description="Cookies properly configured",
                        solution="", evidence="", references=[]
                    ))'''

    elif detect_type == "banner":
        detection_code = f'''                banner = await asyncio.wait_for(reader.read(256), timeout=3)
                writer.close()
                await writer.wait_closed()
                banner_str = banner.decode("utf-8", errors="replace")'''
        vuln_check = f'''                if "{detect_indicator}" in banner_str:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                        description=self.DESCRIPTION,
                        solution=self.SOLUTION,
                        evidence=f"Banner: {{banner_str[:200]}}",
                        references=self.CVE if self.CVE else []
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description="Not detected",
                        solution="", evidence="", references=[]
                    ))'''

    elif detect_type == "method":
        method = row.get("method", "OPTIONS")
        detection_code = f'''                request = (
                    f"{method} / HTTP/1.1\\r\\n"
                    f"Host: {{target}}\\r\\n"
                    f"User-Agent: CentraScanner/1.0\\r\\n"
                    f"Accept: */*\\r\\n"
                    f"Connection: close\\r\\n\\r\\n"
                )
                writer.write(request.encode())
                await writer.drain()'''
        vuln_check = f'''                if "HTTP/1.1 200" in body or "HTTP/1.1 201" in body or "HTTP/1.1 204" in body:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                        description=self.DESCRIPTION,
                        solution=self.SOLUTION,
                        evidence=f"{method} method allowed",
                        references=self.CVE if self.CVE else []
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description=f"{method} method blocked",
                        solution="", evidence="", references=[]
                    ))'''

    else:
        # Default: path check
        detection_code = f'''                request = (
                    f"GET {path_encoded} HTTP/1.1\\r\\n"
                    f"Host: {{target}}\\r\\n"
                    f"User-Agent: CentraScanner/1.0\\r\\n"
                    f"Accept: */*\\r\\n"
                    f"Connection: close\\r\\n\\r\\n"
                )
                writer.write(request.encode())
                await writer.drain()'''

        if detect_indicator:
            vuln_check = f'''                if "HTTP/1.1 200" in body and "{detect_indicator}" in body:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                        description=self.DESCRIPTION,
                        solution=self.SOLUTION,
                        evidence=f"Indicator '{detect_indicator}' found at {path_encoded}",
                        references=self.CVE if self.CVE else []
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description="Not detected",
                        solution="", evidence="", references=[]
                    ))'''
        else:
            vuln_check = f'''                if "HTTP/1.1 200" in body or "HTTP/1.1 401" in body or "HTTP/1.1 403" in body:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                        description=self.DESCRIPTION,
                        solution=self.SOLUTION,
                        evidence=f"Path accessible: {path_encoded}",
                        references=self.CVE if self.CVE else []
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description="Not detected",
                        solution="", evidence="", references=[]
                    ))'''

    plugin_code = TEMPLATE.format(
        class_name=cn,
        plugin_id=plugin_id,
        name=name_s,
        description=desc_s,
        solution=sol_s,
        cvss=cvss,
        severity=severity,
        family=family,
        cve_list=cve_str,
        ports=ports,
        detection_code=detection_code,
        vuln_check=vuln_check,
        read_size=read_size,
        ssl_import=ssl_import,
        ssl_args=ssl_args,
    )
    return plugin_code


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Bulk generate Centra plugins from CSV")
    parser.add_argument("--csv", required=True, help="CSV with plugin definitions")
    parser.add_argument("--output-dir", required=True, help="Output directory for .py files")
    parser.add_argument("--start-id", type=int, default=1386, help="Starting plugin ID")
    parser.add_argument("--prefix", default="gen_", help="Output file prefix")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(args.csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        plugin_id = args.start_id
        generated = 0
        for row in reader:
            plugin_code = generate_plugin(row, plugin_id)
            slug = re.sub(r'[^a-z0-9]+', '_', row.get("name", f"plugin_{plugin_id}").lower())[:50].strip("_")
            filename = f"{args.prefix}{slug}_{plugin_id}.py"
            filepath = output_dir / filename
            filepath.write_text(plugin_code)
            print(f"  [{plugin_id}] {row.get('name', 'Unknown')[:60]} -> {filename}")
            plugin_id += 1
            generated += 1

        print(f"\nGenerated {generated} plugins (IDs {args.start_id}-{args.start_id + generated - 1})")


if __name__ == "__main__":
    sys.exit(main() or 0)
