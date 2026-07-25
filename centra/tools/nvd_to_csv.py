"""Convert NVD JSON feeds to Centra plugin CSV format."""
import csv
import gzip
import json
import os
import re
import sys
from pathlib import Path


def load_nvd(path):
    with open(path) as f:
        data = json.load(f)
    return data.get('cve_items', [])


def get_en_description(item):
    descs = item.get('descriptions', [])
    for d in descs:
        if d.get('lang') == 'en':
            return d.get('value', '')
    return descs[0].get('value', '') if descs else ''


def get_cvss_v3(item):
    metrics = item.get('metrics', {})
    for version in ['cvssMetricV31', 'cvssMetricV30']:
        if version in metrics:
            cvss = metrics[version][0]['cvssData']
            return float(cvss['baseScore']), cvss.get('baseSeverity', 'MEDIUM')
    return None, None


def get_affected_products(item):
    products = []
    affected = item.get('affected', [])
    for a in affected:
        if isinstance(a, dict):
            for ad in a.get('affectedData', []):
                if isinstance(ad, dict):
                    prod = ad.get('product', '')
                    vendor = ad.get('vendor', '')
                    if prod:
                        products.append(f"{vendor}:{prod}" if vendor else prod)
    return products


def get_cwe(item):
    weaknesses = item.get('weaknesses', [])
    for w in weaknesses:
        descs = w.get('description', [])
        for d in descs:
            val = d.get('value', '')
            if val.startswith('CWE-') and 'NVD-CWE' not in val:
                return val
    for w in weaknesses:
        descs = w.get('description', [])
        for d in descs:
            val = d.get('value', '')
            if val.startswith('CWE-'):
                return val
    return ''


def guess_family_and_type(cwe, products, description):
    desc_lower = description.lower()
    products_str = ' '.join(products).lower()

    if cwe and any(x in cwe for x in ['CWE-79', 'CWE-89', 'CWE-22', 'CWE-352', 'CWE-862', 'CWE-200']):
        return 'Web Application', 'path'
    if any(kw in desc_lower or kw in products_str for kw in
           ['android', 'ios', 'windows', 'linux', 'kernel', 'macos', 'iphone', 'samsung']):
        return 'Operating System', 'path'
    if any(kw in desc_lower or kw in products_str for kw in
           ['mysql', 'postgresql', 'oracle', 'sqlite', 'mariadb', 'mongodb', 'redis',
            'database', 'sql server', 'db2']):
        return 'Databases', 'banner'
    if any(kw in desc_lower or kw in products_str for kw in
           ['apache', 'nginx', 'iis', 'tomcat', 'http server', 'web server',
            'cgi', 'php', 'wordpress', 'drupal', 'joomla', 'cpanel']):
        return 'Web Servers', 'path'
    if any(kw in desc_lower or kw in products_str for kw in
           ['router', 'switch', 'firewall', 'cisco', 'fortinet', 'palo alto',
            'juniper', 'network', 'vpn', 'gateway']):
        return 'Network Devices', 'banner'
    if any(kw in desc_lower or kw in products_str for kw in
           ['printer', 'scanner', 'copier', 'embedded', 'iot', 'camera']):
        return 'Embedded/IoT', 'path'
    return 'General Vulnerability', 'path'


def guess_ports(cwe, products, description, family):
    family_lower = family.lower()
    desc_lower = description.lower()
    products_str = ' '.join(products).lower()

    if 'database' in family_lower or any(kw in desc_lower or kw in products_str for kw in
                                          ['mysql', 'postgresql', 'oracle', 'mongodb', 'redis']):
        return '3306, 5432, 1521, 27017, 6379, 80, 443'
    if any(kw in desc_lower or kw in products_str for kw in
           ['ssh', 'telnet', 'ftp', 'smtp', 'snmp', 'dns']):
        return '22, 23, 21, 25, 161, 53, 80, 443'
    return '80, 443, 8080, 8443'


def truncate(text, max_len):
    return text[:max_len] if text else ''


def convert_nvd_to_csv(nvd_items, output_csv, max_rows=None, start_index=0):
    """Convert NVD JSON items to plugin CSV rows."""
    fieldnames = ["name", "description", "solution", "cvss", "severity",
                  "family", "type", "path", "indicator", "header",
                  "ports", "cve", "negate", "method", "read_size"]

    written = 0
    seen_cves = set()

    with open(output_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for idx, item in enumerate(nvd_items):
            if idx < start_index:
                continue
            if max_rows and written >= max_rows:
                break

            cve_id = item.get('id', '')
            if not cve_id or cve_id in seen_cves:
                continue
            seen_cves.add(cve_id)

            score, severity = get_cvss_v3(item)
            if score is None:
                continue

            description = get_en_description(item)
            products = get_affected_products(item)
            cwe = get_cwe(item)
            family, detect_type = guess_family_and_type(cwe, products, description)
            ports = guess_ports(cwe, products, description, family)
            product_hint = products[0] if products else cwe or 'generic'

            name = f"{cve_id}"
            short_desc = truncate(description, 200)
            solution = f"Apply vendor patch for {cve_id}. Upgrade to latest version."

            if detect_type == 'banner':
                path_val = '/'
                indicator_val = product_hint[:40]
                header_val = ''
            else:
                path_val = '/'
                indicator_val = ''
                header_val = ''

            writer.writerow({
                "name": name,
                "description": short_desc,
                "solution": solution,
                "cvss": str(score),
                "severity": severity.capitalize() if severity else 'MEDIUM',
                "family": family,
                "type": detect_type,
                "path": path_val,
                "indicator": indicator_val,
                "header": header_val,
                "ports": ports,
                "cve": cve_id,
                "negate": "",
                "method": "",
                "read_size": "4096",
            })
            written += 1

            if written % 1000 == 0:
                print(f"  Processed {written} CVEs...")

    print(f"Wrote {written} CVEs to {output_csv}")
    return written


def main():
    years = ['2024', '2025', '2026']
    input_dir = Path('/tmp/opencode')
    output_csv = Path('/tmp/opencode/batch5_nvd_plugins.csv')

    all_items = []
    for year in years:
        path = input_dir / f'CVE-{year}.json'
        if path.exists():
            items = load_nvd(path)
            print(f"{year}: {len(items)} CVE items loaded")
            all_items.extend(items)
        else:
            print(f"Warning: {path} not found")

    print(f"Total items: {len(all_items)}")

    # Filter only items with CVSS v3
    filtered = []
    for item in all_items:
        score, _ = get_cvss_v3(item)
        if score is not None:
            filtered.append(item)
    print(f"With CVSS v3: {len(filtered)}")

    total = convert_nvd_to_csv(filtered, output_csv, max_rows=5000)
    print(f"\nBatch 5: {total} plugins (IDs 2667–{2666 + total})")


if __name__ == '__main__':
    main()
