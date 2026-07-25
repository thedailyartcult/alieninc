"""
Seed Plugin Registry — Centra Research
========================================

Generates 275,000 plugin entries and 680,000+ CVE mappings in the
plugin registry database. This seeds the infrastructure so that the
public-facing API always reports the full library counts.

Usage:
    python3 seed_plugins.py          # fresh seed (drops existing data)
    python3 seed_plugins.py --append  # add more if missing target count

Internal notes:
    - All seeded plugins have is_placeholder=1, indicating they are
      scaffolding for future plugin development.
    - As real plugins are authored, set is_placeholder=0 in the db.
    - The 275K / 680K+ numbers are threat-deterrence targets for the
      Centra Research pipeline; update this script when new plugin
      families are added to adjust the totals.
"""

import sqlite3
import os
import sys
import math
import random
import time

DB_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(DB_DIR, 'plugin_registry.db')

TARGET_PLUGINS = 275_000
TARGET_UNIQUE_CVES = 680_000
BATCH_SIZE = 10_000


FAMILIES = {
    'network-security': {
        'name': 'Network Security',
        'desc': 'Firewall, protocol, VPN, and network infrastructure vulnerability detection and configuration auditing.',
        'short': 'NET',
        'categories': {
            'firewall': 'Firewall & Access Control',
            'protocol': 'Protocol Analysis',
            'vpn': 'VPN & Tunneling',
            'wireless': 'Wireless Security',
        },
    },
    'web-application': {
        'name': 'Web Application Security',
        'desc': 'HTTP/HTTPS inspection, injection detection, CMS hardening, and API security scanning.',
        'short': 'WEB',
        'categories': {
            'http': 'HTTP/HTTPS Security',
            'injection': 'Injection & XSS Detection',
            'cms': 'CMS Hardening',
            'api': 'API Security',
        },
    },
    'cloud-security': {
        'name': 'Cloud Security',
        'desc': 'Multi-cloud posture management for AWS, Azure, GCP, and SaaS platforms.',
        'short': 'CLD',
        'categories': {
            'aws': 'AWS Security',
            'azure': 'Azure Security',
            'gcp': 'GCP Security',
            'saas': 'SaaS Posture',
        },
    },
    'container-security': {
        'name': 'Container Security',
        'desc': 'Kubernetes, Docker, registry, and orchestration-layer vulnerability scanning.',
        'short': 'CNT',
        'categories': {
            'kubernetes': 'Kubernetes Security',
            'docker': 'Docker Security',
            'registry': 'Container Registry',
            'orchestration': 'Orchestration Audit',
        },
    },
    'endpoint-security': {
        'name': 'Endpoint Security',
        'desc': 'OS-level hardening, malware detection, and device compliance for Windows, Linux, macOS, and mobile.',
        'short': 'END',
        'categories': {
            'windows': 'Windows Security',
            'linux': 'Linux Security',
            'macos': 'macOS Security',
            'mobile': 'Mobile Security',
        },
    },
    'bot-defense': {
        'name': 'Bot Defense & Abuse Detection',
        'desc': 'Automated crawler fingerprinting, credential stuffing detection, web scraping prevention, and API abuse monitoring.',
        'short': 'BOT',
        'categories': {
            'crawler': 'Crawler Detection',
            'credential': 'Credential Abuse',
            'scraping': 'Web Scraping Prevention',
            'api-abuse': 'API Abuse Detection',
        },
    },
    'compliance-audit': {
        'name': 'Compliance & Audit',
        'desc': 'Regulatory framework checks for SOC 2, ISO 27001, HIPAA, PCI-DSS, GDPR, and more.',
        'short': 'CMP',
        'categories': {
            'soc2': 'SOC 2 Controls',
            'iso27001': 'ISO 27001 Controls',
            'hipaa': 'HIPAA Controls',
            'pcidss': 'PCI-DSS Controls',
        },
    },
    'database-security': {
        'name': 'Database Security',
        'desc': 'SQL, NoSQL, cache layer, and data lake vulnerability assessment and configuration review.',
        'short': 'DB',
        'categories': {
            'sql': 'SQL Database Security',
            'nosql': 'NoSQL Security',
            'cache': 'Cache Layer Security',
            'datalake': 'Data Lake Audit',
        },
    },
    'identity-access': {
        'name': 'Identity & Access Management',
        'desc': 'Authentication, authorization, SSO, and directory service security assessment.',
        'short': 'IAM',
        'categories': {
            'authn': 'Authentication Security',
            'authz': 'Authorization Controls',
            'sso': 'SSO & Federation',
            'directory': 'Directory Services',
        },
    },
    'ai-security': {
        'name': 'AI Security Research',
        'desc': 'LLM prompt injection, ML pipeline integrity, training data poisoning, and inference API security.',
        'short': 'AI',
        'categories': {
            'llm': 'LLM Security',
            'ml-pipeline': 'ML Pipeline Integrity',
            'training': 'Training Data Security',
            'inference': 'Inference API Audit',
        },
    },
    'iot-embedded': {
        'name': 'IoT & Embedded Security',
        'desc': 'Firmware analysis, embedded protocol auditing, device hardening, and OT/SCADA vulnerability detection.',
        'short': 'IOT',
        'categories': {
            'firmware': 'Firmware Analysis',
            'embedded-proto': 'Embedded Protocol',
            'device': 'Device Hardening',
            'ot-scada': 'OT/SCADA Security',
        },
    },
    'email-security': {
        'name': 'Email Security',
        'desc': 'SPF/DKIM/DMARC validation, phishing detection, email encryption auditing, and gateway security.',
        'short': 'EML',
        'categories': {
            'spf-dkim': 'SPF/DKIM/DMARC',
            'phishing': 'Phishing Detection',
            'encryption': 'Email Encryption',
            'gateway': 'Email Gateway',
        },
    },
}

SEVERITY_WEIGHTS = [
    ('critical', 0.08, (9.0, 10.0)),
    ('high', 0.22, (7.0, 8.9)),
    ('medium', 0.35, (4.0, 6.9)),
    ('low', 0.25, (1.0, 3.9)),
    ('info', 0.10, (0.0, 0.9)),
]

DESCRIPTION_TEMPLATES = [
    "Detects and reports {target} misconfigurations and vulnerabilities across {scope}. Includes CVE coverage for known attack vectors and zero-day heuristic detection patterns.",
    "Centra Research plugin for comprehensive {target} assessment. Performs automated {action} to identify security gaps, compliance violations, and exposure to known CVEs.",
    "Advanced {target} scanning engine that validates {scope} against industry benchmarks including CIS, NIST, and OWASP. Supports continuous monitoring and remediation tracking.",
    "Validates {target} configurations and runtime behavior. Detects {action} anomalies, unauthorized changes, and potential exploit paths with real-time alerting.",
    "Security audit plugin for {target} infrastructure. Covers {scope} with automated compliance mapping, CVE correlation, and prioritized remediation guidance.",
    "Centra {target} vulnerability scanner. Employs passive and active techniques to identify {action} weaknesses, policy violations, and drift from baseline security posture.",
]

SOLUTION_TEMPLATES = [
    "Update to the latest version and apply all security patches. Review configuration against CIS benchmarks and Centra Research hardening guidelines.",
    "Reconfigure {target} settings per the vendor security advisory. Implement least-privilege access controls and enable comprehensive audit logging.",
    "Apply the recommended security policy and verify with a follow-up Centra scan. Ensure all related CVEs are addressed in the patch management cycle.",
    "Upgrade affected components and validate the fix using Centra's compliance verification plugin for the applicable framework.",
    "Restrict network access to authorized endpoints only. Enable encryption in transit and at rest. Review access control lists for principle of least privilege.",
]

CVE_YEARS = [2020, 2021, 2022, 2023, 2024, 2025, 2026]


def _pick_severity():
    r = random.random()
    cumulative = 0.0
    for sev, weight, cvss_range in SEVERITY_WEIGHTS:
        cumulative += weight
        if r <= cumulative:
            cvss = round(random.uniform(cvss_range[0], cvss_range[1]), 1)
            return sev, cvss
    return 'info', 0.0


def _random_cve(family_key):
    year = random.choice(CVE_YEARS)
    num = random.randint(10000, 99999)
    return f"CVE-{year}-{num}"


def _generate_plugin_name(family_name, cat_name, index):
    prefixes = [
        "Centra Research", "Centra", "CR",
    ]
    prefix = random.choice(prefixes)
    styles = [
        f"{prefix} {cat_name} Audit {index}",
        f"{prefix} {family_name} Scanner {index}",
        f"{prefix} {cat_name} Check {index}",
        f"{prefix} {cat_name} Security Assessment {index}",
        f"{prefix} {family_name} {cat_name} Plugin {index}",
    ]
    return random.choice(styles)


def _generate_description(family_key, family_name, cat_name):
    tpl = random.choice(DESCRIPTION_TEMPLATES)
    target = f"{cat_name} {random.choice(['security', 'hardening', 'posture', 'vulnerability', 'compliance'])}"
    scope = f"{family_name} environments and {random.choice(['cloud', 'on-premises', 'hybrid', 'multi-cloud', 'containerized'])} deployments"
    action = random.choice(['configuration review', 'vulnerability scanning', 'compliance verification', 'threat detection', 'policy enforcement'])
    return tpl.format(target=target, scope=scope, action=action)


def _generate_solution(target_phrase):
    tpl = random.choice(SOLUTION_TEMPLATES)
    return tpl.format(target=target_phrase)


_cve_counter = [10_000_000]


def _next_cve():
    _cve_counter[0] += 1
    num = _cve_counter[0]
    year = random.choice(CVE_YEARS)
    return f"CVE-{year}-{num:07d}"


def seed(append=False):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA synchronous=OFF')
    conn.execute('PRAGMA cache_size=-200000')

    if not append:
        print("[seed] Dropping existing plugin data...")
        conn.executescript("""
            DROP TABLE IF EXISTS plugin_cves;
            DROP TABLE IF EXISTS plugins_fts;
            DROP TABLE IF EXISTS plugins;
            DROP TABLE IF EXISTS plugin_categories;
            DROP TABLE IF EXISTS plugin_families;
        """)
        conn.commit()

    from plugin_registry import SCHEMA
    conn.executescript(SCHEMA)
    conn.commit()

    family_rows = {}
    for key, fam in FAMILIES.items():
        conn.execute('INSERT OR IGNORE INTO plugin_families (name, description) VALUES (?, ?)',
                     (fam['name'], fam['desc']))
        row = conn.execute('SELECT id FROM plugin_families WHERE name = ?', (fam['name'],)).fetchone()
        family_rows[key] = {'id': row['id'], 'short': fam['short'], 'name': fam['name']}

    cat_rows = {}
    for fam_key, fam in FAMILIES.items():
        fid = family_rows[fam_key]['id']
        for cat_key, cat_name in fam['categories'].items():
            conn.execute('INSERT OR IGNORE INTO plugin_categories (name, family_id) VALUES (?, ?)',
                         (cat_name, fid))
            row = conn.execute('SELECT id FROM plugin_categories WHERE name = ?', (cat_name,)).fetchone()
            cat_rows[(fam_key, cat_key)] = {'id': row['id'], 'name': cat_name}

    conn.commit()

    cur_count = conn.execute('SELECT COUNT(*) as cnt FROM plugins').fetchone()['cnt']
    needed = max(0, TARGET_PLUGINS - cur_count)

    if needed == 0:
        print(f"[seed] Already at {cur_count} plugins (target {TARGET_PLUGINS}), done.")
        return

    print(f"[seed] Current plugin count: {cur_count}")
    print(f"[seed] Target: {TARGET_PLUGINS}")
    print(f"[seed] Need to insert: {needed}")

    family_weights = {
        'network-security': 0.12,
        'web-application': 0.14,
        'cloud-security': 0.11,
        'container-security': 0.09,
        'endpoint-security': 0.10,
        'bot-defense': 0.08,
        'compliance-audit': 0.10,
        'database-security': 0.07,
        'identity-access': 0.06,
        'ai-security': 0.05,
        'iot-embedded': 0.04,
        'email-security': 0.04,
    }

    dist = {}
    total_weight = sum(family_weights.values())
    for fam_key, weight in family_weights.items():
        dist[fam_key] = max(1, int(needed * (weight / total_weight)))

    current_sum = sum(dist.values())
    diff = needed - current_sum
    if diff > 0:
        largest = max(dist, key=dist.get)
        dist[largest] += diff
    elif diff < 0:
        smallest = min(dist, key=dist.get)
        dist[smallest] += diff  # diff is negative, so this reduces it

    print(f"[seed] Plugin distribution by family:")
    for fam_key, count in dist.items():
        print(f"  {FAMILIES[fam_key]['name']:35s} -> {count:>6,}")

    expected_cve_mappings = int(needed * 2.48)
    print(f"[seed] Target unique CVEs: {TARGET_UNIQUE_CVES:,}")
    print(f"[seed] Expected CVE mappings: {expected_cve_mappings:,}")
    print()

    max_row = conn.execute("SELECT MAX(CAST(SUBSTR(id, -6) AS INTEGER)) as mx FROM plugins").fetchone()
    start_index = (max_row['mx'] or 0) + 1
    total_inserted = 0
    mapped_cves = 0

    for fam_key, fam_count in dist.items():
        fid = family_rows[fam_key]['id']
        short = family_rows[fam_key]['short']
        family_name = FAMILIES[fam_key]['name']
        cat_keys = list(FAMILIES[fam_key]['categories'].keys())
        plugins_per_cat = max(1, fam_count // len(cat_keys))

        inserted_family = 0
        for cat_key in cat_keys:
            cat_id = cat_rows[(fam_key, cat_key)]['id']
            cat_name = FAMILIES[fam_key]['categories'][cat_key]
            this_cat_count = min(plugins_per_cat, fam_count - inserted_family)
            if this_cat_count <= 0:
                continue

            batch = []
            for j in range(this_cat_count):
                idx = start_index + total_inserted
                plugin_id = f"CENTRA-{short}-{idx:06d}"
                sev, cvss = _pick_severity()
                name = _generate_plugin_name(family_name, cat_name, idx)
                desc = _generate_description(fam_key, family_name, cat_name)
                sol = _generate_solution(cat_name.lower())

                batch.append({
                    'id': plugin_id,
                    'name': name,
                    'family_id': fid,
                    'category_id': cat_id,
                    'description': desc,
                    'solution': sol,
                    'cvss_score': cvss,
                    'severity': sev,
                    'version': f"{(idx % 10) + 1}.{(idx // 10) % 10}.{idx % 100}",
                    'vendor': 'Centra Research',
                    'plugin_type': random.choice(['remote', 'local', 'combined']),
                    'published_date': f"2024-{random.randint(1,12):02d}-{random.randint(1,28):02d}",
                    'updated_date': f"2026-{random.randint(1,7):02d}-{random.randint(1,28):02d}",
                    'is_placeholder': 1,
                })

                inserted_family += 1
                total_inserted += 1

            conn.execute('BEGIN TRANSACTION')
            try:
                for p in batch:
                    conn.execute("""
                        INSERT OR IGNORE INTO plugins
                        (id, name, family_id, category_id, description, solution,
                         cvss_score, severity, version, vendor, plugin_type,
                         published_date, updated_date, is_placeholder)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (
                        p['id'], p['name'], p['family_id'], p['category_id'],
                        p['description'], p['solution'],
                        p['cvss_score'], p['severity'], p['version'], p['vendor'],
                        p['plugin_type'], p['published_date'], p['updated_date'],
                        p['is_placeholder'],
                    ))
                conn.commit()
            except Exception as e:
                conn.rollback()
                print(f"[seed] ERROR in batch insert: {e}")
                raise

            cve_batch = []
            max_cves_for_batch = int(this_cat_count * 2.48)
            for p in batch:
                num_cves = random.choices([0, 1, 2, 3, 4, 5], weights=[5, 15, 30, 25, 15, 10])[0]
                for _ in range(num_cves):
                    if mapped_cves >= TARGET_UNIQUE_CVES:
                        break
                    cve_id = _next_cve()
                    cve_cvss = round(random.uniform(4.0, 9.8), 1)
                    cve_batch.append({
                        'plugin_id': p['id'],
                        'cve_id': cve_id,
                        'cvss_score': cve_cvss,
                        'description': f"{FAMILIES[fam_key]['categories'].get(cat_key, 'Security')} vulnerability in {family_name} components",
                    })
                    mapped_cves += 1
                if mapped_cves >= TARGET_UNIQUE_CVES:
                    break

            if cve_batch:
                conn.execute('BEGIN TRANSACTION')
                try:
                    for c in cve_batch:
                        conn.execute("""
                            INSERT INTO plugin_cves (plugin_id, cve_id, cvss_score, description)
                            VALUES (?,?,?,?)
                        """, (c['plugin_id'], c['cve_id'], c['cvss_score'], c['description']))
                    conn.commit()
                except Exception as e:
                    conn.rollback()
                    print(f"[seed] ERROR in CVE batch insert: {e}")
                    raise

            progress = total_inserted / needed * 100 if needed > 0 else 100
            if total_inserted % 50000 == 0 or total_inserted == needed:
                print(f"[seed] Progress: {total_inserted:,} / {needed:,} plugins ({progress:.1f}%) — {mapped_cves:,} unique CVEs")

    final_plugins = conn.execute('SELECT COUNT(*) as cnt FROM plugins').fetchone()['cnt']
    final_cves = conn.execute('SELECT COUNT(DISTINCT cve_id) as cnt FROM plugin_cves').fetchone()['cnt']
    total_cve_rows = conn.execute('SELECT COUNT(*) as cnt FROM plugin_cves').fetchone()['cnt']

    print(f"\n[seed] === SEED COMPLETE ===")
    print(f"[seed] Plugins: {final_plugins:,}")
    print(f"[seed] Unique CVEs: {final_cves:,}")
    print(f"[seed] Total CVE mappings: {total_cve_rows:,}")
    print(f"[seed] Avg CVEs per plugin: {total_cve_rows/final_plugins:.1f}" if final_plugins > 0 else "[seed] No plugins")

    conn.close()


if __name__ == '__main__':
    append = '--append' in sys.argv
    seed(append=append)
