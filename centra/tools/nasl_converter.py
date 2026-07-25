"""
NASL-to-Centra Plugin Converter
Parses OpenVAS/Greenbone NASL NVT scripts and generates Python PluginResult-format plugins.

Usage:
  python3 nasl_converter.py <input.nasl> [--output-dir <dir>]
  python3 nasl_converter.py --batch <dir> [--output-dir <dir>]
"""

import re
import sys
from pathlib import Path


def parse_nasl_metadata(content: str) -> dict:
    meta = {
        "oid": "",
        "name": "",
        "description": "",
        "solution": "",
        "impact": "",
        "affected": "",
        "insight": "",
        "cvss_base": 0.0,
        "cvss_vector": "",
        "family": "Unknown",
        "category": "",
        "cve_ids": [],
        "ports": [],
        "copyright": "",
        "dependencies": [],
        "require_ports": [],
    }

    # Extract OID
    m = re.search(r'script_oid\s*\(\s*["\']([^"\']+)["\']\s*\)', content)
    if m:
        meta["oid"] = m.group(1)

    # Extract name
    m = re.search(r'script_name\s*\(\s*["\']([^"\']+)["\']\s*\)', content)
    if m:
        meta["name"] = m.group(1)

    # Extract tags
    tag_pattern = r'script_tag\s*\(\s*name:\s*["\']([^"\']+)["\']\s*,\s*value:\s*["\']([^"\']+)["\']\s*\)'
    for m in re.finditer(tag_pattern, content, re.DOTALL):
        tag_name = m.group(1).lower()
        tag_value = m.group(2).strip()
        if tag_name == "summary":
            meta["description"] = tag_value
        elif tag_name == "solution":
            meta["solution"] = tag_value
        elif tag_name == "impact":
            meta["impact"] = tag_value
        elif tag_name == "affected":
            meta["affected"] = tag_value
        elif tag_name == "insight":
            meta["insight"] = tag_value
        elif tag_name == "cvss_base":
            try:
                meta["cvss_base"] = float(tag_value)
            except ValueError:
                pass
        elif tag_name == "cvss_base_vector":
            meta["cvss_vector"] = tag_value

    # Extract family
    m = re.search(r'script_family\s*\(\s*["\']([^"\']+)["\']\s*\)', content)
    if m:
        meta["family"] = m.group(1)

    # Extract category
    m = re.search(r'script_category\s*\(\s*["\']([^"\']+)["\']\s*\)', content)
    if m:
        meta["category"] = m.group(1)

    # Extract CVE IDs
    cve_pattern = r'script_cve_id\s*\(\s*["\']([^"\']+)["\']\s*\)'
    for m in re.finditer(cve_pattern, content):
        meta["cve_ids"] = [c.strip() for c in m.group(1).split(",")]

    # Extract require_ports
    port_pattern = r'script_require_ports\s*\([^)]*?["\'](\d+)["\'][^)]*\)'
    for m in re.finditer(port_pattern, content):
        meta["require_ports"].append(int(m.group(1)))
    port_pattern2 = r'script_require_ports\s*\(\s*["\']Services/www["\']\s*,\s*(\d+)\s*\)'
    for m in re.finditer(port_pattern2, content):
        meta["require_ports"].append(int(m.group(1)))

    # Extract copyright
    m = re.search(r'script_copyright\s*\(\s*["\']([^"\']+)["\']\s*\)', content)
    if m:
        meta["copyright"] = m.group(1)

    # Extract dependencies
    dep_pattern = r'script_dependencies\s*\(\s*["\']([^"\']+)["\']\s*\)'
    for m in re.finditer(dep_pattern, content):
        meta["dependencies"].append(m.group(1))

    return meta


def determine_ports(family: str, require_ports: list, content: str) -> list:
    web_ports = [80, 443, 8080, 8443]
    ssl_ports = [443, 8443]
    smb_ports = [139, 445]
    ssh_ports = [22]
    sql_ports = [3306, 5432, 1433, 1521]

    family_lower = family.lower()
    content_lower = content.lower()

    if require_ports:
        return list(set(require_ports))

    if "web" in family_lower or "http" in family_lower or "www" in content_lower:
        return web_ports
    if "ssl" in family_lower or "tls" in family_lower:
        return ssl_ports
    if "smb" in family_lower or "windows" in family_lower:
        return smb_ports
    if "ssh" in family_lower:
        return ssh_ports
    if "sql" in family_lower or "database" in family_lower:
        return sql_ports
    if "general" in family_lower:
        return [0]
    return [80, 443]


def family_to_centra(family: str) -> str:
    mapping = {
        "web application abuses": "Web Application",
        "web servers": "Web Servers",
        "cgi abuses": "Web Security",
        "general": "Information Gathering",
        "windows": "Windows",
        "linux": "Linux",
        "network devices": "Network Devices",
        "default accounts": "Web Security",
        "denial of service": "Web Security",
        "ftp": "Network Devices",
        "smb": "Windows",
    }
    return mapping.get(family.lower(), family)


def cvss_to_severity(cvss: float) -> str:
    if cvss >= 9.0:
        return "Critical"
    elif cvss >= 7.0:
        return "High"
    elif cvss >= 4.0:
        return "Medium"
    elif cvss > 0:
        return "Low"
    return "Info"


def generate_plugin_from_meta(meta: dict, plugin_id: int) -> str:
    ports = determine_ports(meta["family"], meta["require_ports"], "")
    ports_str = ", ".join(str(p) for p in ports)
    name = meta["name"] or "Unknown Vulnerability"
    description = meta["description"] or meta["summary"] or f"OpenVAS NVT: {name}"
    solution = meta["solution"] or "Apply vendor patches."
    cvss = meta["cvss_base"]
    severity = cvss_to_severity(cvss)
    family = family_to_centra(meta["family"])
    cve_list = meta["cve_ids"]
    cve_str = repr(cve_list) if cve_list else "[]"
    oid = meta["oid"]

    # Build evidence from NVT metadata
    evidence_parts = []
    if oid:
        evidence_parts.append(f"OpenVAS OID: {oid}")
    if meta["cvss_vector"]:
        evidence_parts.append(f"CVSS Vector: {meta['cvss_vector']}")
    if meta["impact"]:
        evidence_parts.append(f"Impact: {meta['impact'][:100]}")
    evidence_str = "\\n".join(evidence_parts)

    solution_escaped = solution.replace('"', '\\"').replace("\n", " ")
    desc_escaped = description.replace('"', '\\"').replace("\n", " ")

    class_name = name.replace("(", "").replace(")", "").replace(" ", "").replace("/", "").replace("-", "")[:40]
    if class_name[0].isdigit():
        class_name = "Vuln" + class_name

    return f'''import asyncio
from plugins import NaslPlugin, PluginResult


class {class_name}Plugin(NaslPlugin):
    PLUGIN_ID = {plugin_id}
    NAME = "{name}"
    DESCRIPTION = "{desc_escaped}"
    SOLUTION = "{solution_escaped}"
    CVSS_SCORE = {cvss}
    SEVERITY = "{severity}"
    FAMILY = "{family}"
    CVE = {cve_str}
    PORTS = [{ports_str}]
    OID = "{oid}"

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for p in ([port] if port else self.PORTS):
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, p), timeout=5
                )
                request = (
                    f"GET / HTTP/1.1\\r\\n"
                    f"Host: {{target}}:{{p}}\\r\\n"
                    f"User-Agent: CentraScanner/1.0\\r\\n"
                    f"Accept: */*\\r\\n"
                    f"Connection: close\\r\\n\\r\\n"
                )
                writer.write(request.encode())
                await writer.drain()
                resp = await asyncio.wait_for(reader.read(4096), timeout=5)
                writer.close()
                await writer.wait_closed()
                body = resp.decode("utf-8", errors="replace")
                if "HTTP/1.1 200" in body:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                        description=self.DESCRIPTION,
                        solution=self.SOLUTION,
                        evidence="{evidence_str}",
                        references=self.CVE if self.CVE else []
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description="Target not vulnerable",
                        solution="", evidence="", references=[]
                    ))
            except Exception:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description="Could not connect",
                    solution="", evidence="", references=[]
                ))
        return results
'''


def convert_nasl_file(input_path: Path, output_dir: Path, plugin_id: int) -> str | None:
    content = input_path.read_text(encoding="utf-8", errors="replace")
    meta = parse_nasl_metadata(content)
    if not meta["name"]:
        return None
    plugin_code = generate_plugin_from_meta(meta, plugin_id)
    class_name = meta["name"].replace(" ", "_").replace("(", "").replace(")", "").replace("/", "_")[:30]
    output_file = output_dir / f"openvas_{class_name.lower()}_{plugin_id}.py"
    output_file.write_text(plugin_code)
    return str(output_file)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Convert NASL/NVT scripts to Centra plugins")
    parser.add_argument("input", help="NASL file or directory (with --batch)")
    parser.add_argument("--output-dir", default=".", help="Output directory")
    parser.add_argument("--batch", action="store_true", help="Process all .nasl files in input directory")
    parser.add_argument("--start-id", type=int, default=1356, help="Starting plugin ID")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.batch:
        input_dir = Path(args.input)
        nasl_files = sorted(input_dir.glob("*.nasl"))
        if not nasl_files:
            print(f"No .nasl files found in {input_dir}")
            return 1
        plugin_id = args.start_id
        converted = 0
        for nasl_file in nasl_files:
            out = convert_nasl_file(nasl_file, output_dir, plugin_id)
            if out:
                print(f"  [{plugin_id}] {nasl_file.name} -> {out}")
                plugin_id += 1
                converted += 1
        print(f"\nConverted {converted} scripts (IDs {args.start_id}-{args.start_id + converted - 1})")
    else:
        input_path = Path(args.input)
        out = convert_nasl_file(input_path, output_dir, args.start_id)
        if out:
            print(f"Converted {input_path} -> {out}")
        else:
            print(f"Failed to parse {input_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
