#!/usr/bin/env python3
"""
Seed the global_tech_stack table with S&P 500 companies.

Fetches the company list from Wikipedia (automated), geocodes each
unique HQ city using Nominatim / OpenStreetMap (free, cached so we
hit the API ~150 times instead of 500), and inserts every company
into the database with is_featured=0.

Tech stacks are enriched from two free sources:
  1. A curated dataset for ~35 major companies whose stacks are
     well-documented in engineering blogs and conference talks.
  2. Wikipedia article text-mining — fetches each company's page
     summary and extracts technology keyword matches.

The script is idempotent: re-running upserts (deletes + inserts by name).
Featured data centers (is_featured=1) are never touched.

Usage:
  python3 db/seed_sp500.py                    # seed + enrich
  python3 db/seed_sp500.py --no-enrich        # seed locations only (fast)
  python3 db/seed_sp500.py --no-geocode       # skip geocoding (use 0,0)
"""
import json
import os
import sys
import time
import sqlite3
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from schema import get_connection

import requests
import pandas as pd

WIKIPEDIA_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_HEADERS = {
    "User-Agent": "AlienInc-Ecosystem-Seeder/1.0 (contact: founder@alieninc.tech)"
}

# ── Curated tech stacks for major companies ──────────────────────
# Sourced from public engineering blogs, conference talks, and
# StackShare public pages. These are well-documented public knowledge.
CURATED_TECHSTACKS = {
    "Apple Inc.": [
        {"name": "Swift", "role": "First-party app language"},
        {"name": "Objective-C", "role": "Legacy macOS/iOS frameworks"},
        {"name": "AWS", "role": "Cloud infrastructure"},
        {"name": "Kubernetes", "role": "Container orchestration"},
        {"name": "Mesos", "role": "Internal cluster scheduling"},
    ],
    "Microsoft": [
        {"name": "Azure", "role": "Cloud platform"},
        {"name": "C#", "role": "Primary backend language"},
        {"name": ".NET", "role": "Application framework"},
        {"name": "TypeScript", "role": "Frontend language"},
        {"name": "SQL Server", "role": "Database"},
    ],
    "Alphabet Inc.(Class A)": [
        {"name": "Go", "role": "Backend services language"},
        {"name": "Python", "role": "ML & data pipelines"},
        {"name": "Borg/Kubernetes", "role": "Cluster orchestration"},
        {"name": "Tensor Processing Units", "role": "AI accelerator hardware"},
        {"name": "Bigtable", "role": "NoSQL storage"},
    ],
    "Alphabet Inc.(Class C)": [
        {"name": "Go", "role": "Backend services language"},
        {"name": "Python", "role": "ML & data pipelines"},
        {"name": "Borg/Kubernetes", "role": "Cluster orchestration"},
        {"name": "Tensor Processing Units", "role": "AI accelerator hardware"},
        {"name": "Bigtable", "role": "NoSQL storage"},
    ],
    "Amazon.com": [
        {"name": "AWS", "role": "Cloud infrastructure"},
        {"name": "Java", "role": "Backend services"},
        {"name": "DynamoDB", "role": "Key-value database"},
        {"name": "S3", "role": "Object storage"},
        {"name": "Lambda", "role": "Serverless compute"},
    ],
    "Meta Platforms": [
        {"name": "React", "role": "Frontend framework"},
        {"name": "Hack/PHP", "role": "Backend services"},
        {"name": "PyTorch", "role": "ML framework"},
        {"name": "Cassandra", "role": "Distributed database"},
        {"name": "Memcached", "role": "Caching layer"},
    ],
    "Netflix": [
        {"name": "AWS", "role": "Cloud infrastructure"},
        {"name": "Spring Boot", "role": "Microservices framework"},
        {"name": "Cassandra", "role": "View-state storage"},
        {"name": "EVCache", "role": "Distributed caching"},
        {"name": "Spinnaker", "role": "Continuous delivery"},
    ],
    "Nvidia": [
        {"name": "CUDA", "role": "GPU computing platform"},
        {"name": "cuDNN", "role": "Deep learning primitives"},
        {"name": "TensorRT", "role": "Inference optimization"},
        {"name": "Python", "role": "ML tooling"},
        {"name": "Kubernetes", "role": "Container orchestration"},
    ],
    "Tesla, Inc.": [
        {"name": "Python", "role": "Backend & automation"},
        {"name": "C++", "role": "Vehicle firmware"},
        {"name": "Rust", "role": "Vehicle software"},
        {"name": "Kafka", "role": "Telemetry streaming"},
        {"name": "Kubernetes", "role": "Infrastructure orchestration"},
    ],
    "JPMorgan Chase": [
        {"name": "Java", "role": "Core banking systems"},
        {"name": "Kubernetes", "role": "Container orchestration"},
        {"name": "Apache Kafka", "role": "Event streaming"},
        {"name": "Python", "role": "Quant & analytics"},
        {"name": "Onyx", "role": "Internal blockchain platform"},
    ],
    "Salesforce": [
        {"name": "Apex", "role": "Platform programming language"},
        {"name": "Lightning Web Components", "role": "Frontend framework"},
        {"name": "Heroku", "role": "App deployment platform"},
        {"name": "AWS", "role": "Cloud infrastructure"},
        {"name": "MuleSoft", "role": "API integration layer"},
    ],
    "Oracle Corporation": [
        {"name": "Oracle Database", "role": "Relational database"},
        {"name": "Java", "role": "Application platform"},
        {"name": "OCI", "role": "Cloud infrastructure"},
        {"name": "Exadata", "role": "Converged database machine"},
        {"name": "MySQL", "role": "Open-source database"},
    ],
    "Adobe Inc.": [
        {"name": "AWS", "role": "Cloud infrastructure"},
        {"name": "Apache Kafka", "role": "Event streaming"},
        {"name": "React", "role": "Frontend framework"},
        {"name": "C++", "role": "Desktop application engines"},
        {"name": "DocumentDB", "role": "Content storage"},
    ],
    "Cisco": [
        {"name": "IOS XE", "role": "Network operating system"},
        {"name": "Python", "role": "Automation & scripting"},
        {"name": "Go", "role": "Cloud-native services"},
        {"name": "Kubernetes", "role": "Container orchestration"},
        {"name": "Webex", "role": "Collaboration platform"},
    ],
    "Intel": [
        {"name": "C++", "role": "Driver & firmware"},
        {"name": "Python", "role": "Tooling & automation"},
        {"name": "oneAPI", "role": "Cross-architecture programming"},
        {"name": "OpenVINO", "role": "AI inference toolkit"},
        {"name": "Linux", "role": "Development environment"},
    ],
    "IBM": [
        {"name": "IBM Cloud", "role": "Cloud platform"},
        {"name": "Red Hat OpenShift", "role": "Kubernetes platform"},
        {"name": "Db2", "role": "Enterprise database"},
        {"name": "Watson", "role": "AI services platform"},
        {"name": "Java", "role": "Enterprise application language"},
    ],
    "Goldman Sachs": [
        {"name": "Java", "role": "Trading systems"},
        {"name": "Python", "role": "Quant research"},
        {"name": "Kubernetes", "role": "Container orchestration"},
        {"name": "Apache Spark", "role": "Data processing"},
        {"name": "Slang/SecDB", "role": "Proprietary trading platform"},
    ],
    "Bank of America": [
        {"name": "Java", "role": "Core banking"},
        {"name": ".NET", "role": "Internal applications"},
        {"name": "Python", "role": "Data analytics"},
        {"name": "AWS", "role": "Cloud infrastructure"},
        {"name": "Kubernetes", "role": "Container platform"},
    ],
    "Walt Disney Company (The)": [
        {"name": "AWS", "role": "Disney+ streaming infrastructure"},
        {"name": "Node.js", "role": "Backend services"},
        {"name": "React", "role": "Frontend framework"},
        {"name": "Kubernetes", "role": "Container orchestration"},
        {"name": "Elasticsearch", "role": "Content search"},
    ],
    "Visa Inc.": [
        {"name": "Java", "role": "Payment processing"},
        {"name": "Kafka", "role": "Transaction streaming"},
        {"name": "Kubernetes", "role": "Container orchestration"},
        {"name": "AWS", "role": "Cloud infrastructure"},
        {"name": "Couchbase", "role": "High-throughput data store"},
    ],
    "PayPal": [
        {"name": "Java", "role": "Backend services"},
        {"name": "Node.js", "role": "API layer"},
        {"name": "Kafka", "role": "Event streaming"},
        {"name": "Kubernetes", "role": "Container orchestration"},
        {"name": "React", "role": "Frontend framework"},
    ],
    "Qualcomm": [
        {"name": "C/C++", "role": "Embedded firmware"},
        {"name": "Python", "role": "Tooling & testing"},
        {"name": "Linux", "role": "Development environment"},
        {"name": "Android", "role": "Mobile platform"},
        {"name": "ARM Assembly", "role": "Low-level optimization"},
    ],
    "Texas Instruments": [
        {"name": "C/C++", "role": "Embedded firmware"},
        {"name": "Python", "role": "Tooling & automation"},
        {"name": "Verilog", "role": "Hardware design"},
        {"name": "Linux", "role": "Development environment"},
        {"name": "MATLAB", "role": "Signal processing design"},
    ],
    "Applied Materials": [
        {"name": "C++", "role": "Equipment control software"},
        {"name": "Python", "role": "Data analysis & automation"},
        {"name": "LabVIEW", "role": "Test automation"},
        {"name": "SQL Server", "role": "Manufacturing data"},
        {"name": "Linux", "role": "Development environment"},
    ],
    "Advanced Micro Devices": [
        {"name": "C++", "role": "Driver & firmware"},
        {"name": "Python", "role": "Tooling & automation"},
        {"name": "ROCm", "role": "GPU compute platform"},
        {"name": "Linux", "role": "Development environment"},
        {"name": "MLIR", "role": "Compiler infrastructure"},
    ],
    "Broadcom": [
        {"name": "C/C++", "role": "Embedded firmware"},
        {"name": "Python", "role": "Tooling & automation"},
        {"name": "Verilog", "role": "Hardware design"},
        {"name": "Linux", "role": "Development environment"},
        {"name": "VMware", "role": "Virtualization platform"},
    ],
    "ServiceNow": [
        {"name": "Glide", "role": "Platform framework"},
        {"name": "JavaScript", "role": "Client & server scripting"},
        {"name": "Angular", "role": "Frontend framework"},
        {"name": "Java", "role": "Backend services"},
        {"name": "Kubernetes", "role": "Container orchestration"},
    ],
    "Intuit": [
        {"name": "AWS", "role": "Cloud infrastructure"},
        {"name": "Kubernetes", "role": "Container orchestration"},
        {"name": "Java", "role": "Backend services"},
        {"name": "React", "role": "Frontend framework"},
        {"name": "Kafka", "role": "Event streaming"},
    ],
    "Autodesk": [
        {"name": "C++", "role": "Desktop application engines"},
        {"name": "AWS", "role": "Cloud infrastructure"},
        {"name": "React", "role": "Web frontend"},
        {"name": "Node.js", "role": "Backend services"},
        {"name": "Kubernetes", "role": "Container orchestration"},
    ],
    "Datadog": [
        {"name": "Go", "role": "Backend services"},
        {"name": "Python", "role": "Data processing"},
        {"name": "React", "role": "Frontend framework"},
        {"name": "Kafka", "role": "Event streaming"},
        {"name": "PostgreSQL", "role": "Metadata storage"},
    ],
    "Palantir Technologies": [
        {"name": "Java", "role": "Backend services"},
        {"name": "TypeScript", "role": "Frontend language"},
        {"name": "Python", "role": "Data integration"},
        {"name": "Apache Spark", "role": "Data processing"},
        {"name": "Kubernetes", "role": "Container orchestration"},
    ],
    "CrowdStrike": [
        {"name": "Go", "role": "Sensor & cloud services"},
        {"name": "Python", "role": "Threat analysis"},
        {"name": "Kafka", "role": "Telemetry streaming"},
        {"name": "AWS", "role": "Cloud infrastructure"},
        {"name": "React", "role": "Frontend framework"},
    ],
    "Palo Alto Networks": [
        {"name": "Python", "role": "Automation & ML"},
        {"name": "Go", "role": "Cloud services"},
        {"name": "AWS", "role": "Cloud infrastructure"},
        {"name": "Kubernetes", "role": "Container orchestration"},
        {"name": "React", "role": "Frontend framework"},
    ],
    "Mastercard": [
        {"name": "Java", "role": "Payment processing"},
        {"name": "Python", "role": "Data analytics"},
        {"name": "Kafka", "role": "Event streaming"},
        {"name": "AWS", "role": "Cloud infrastructure"},
        {"name": "Kubernetes", "role": "Container orchestration"},
    ],
    "Johnson & Johnson": [
        {"name": "SAP", "role": "ERP system"},
        {"name": "Salesforce", "role": "CRM platform"},
        {"name": "AWS", "role": "Cloud infrastructure"},
        {"name": "Python", "role": "Data analytics"},
        {"name": "Java", "role": "Enterprise applications"},
    ],
}

# ── Technology keywords for Wikipedia text mining ────────────────
TECH_KEYWORDS = [
    "AWS", "Azure", "Google Cloud", "GCP", "Kubernetes", "Docker",
    "React", "Angular", "Vue", "Node.js", "Python", "Java", "JavaScript",
    "TypeScript", "Go", "Rust", "C++", "C#", ".NET", "Swift", "Kotlin",
    "Scala", "Ruby", "PHP", "Perl", "Hadoop", "Spark", "Kafka",
    "PostgreSQL", "MySQL", "MongoDB", "Cassandra", "Redis", "Oracle Database",
    "SQL Server", "Elasticsearch", "GraphQL", "gRPC", "Terraform",
    "Ansible", "Jenkins", "GitLab", "Linux", "Windows Server",
    "VMware", "OpenStack", "HBase", "Snowflake", "Databricks",
    "TensorFlow", "PyTorch", "Machine Learning", "Artificial Intelligence",
    "SAP", "Salesforce", "ServiceNow", "Tableau", "Power BI",
    "Spring Boot", "Django", "Flask", "FastAPI", "Express",
    "Next.js", "Nuxt.js", "Svelte", "Tailwind", "Bootstrap",
    "Nginx", "Apache", "HAProxy", "Cloudflare", "Fastly",
    "RabbitMQ", "ActiveMQ", "Pulsar", "NATS",
    "Helm", "Istio", "Envoy", "Linkerd", "Consul", "Vault",
]


def fetch_sp500_table():
    """Fetch the S&P 500 constituents table from Wikipedia."""
    print("[1/4] Fetching S&P 500 table from Wikipedia...")
    from bs4 import BeautifulSoup
    resp = requests.get(WIKIPEDIA_URL, headers=NOMINATIM_HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table", {"id": "constituents"})
    if not table:
        raise RuntimeError("Could not find constituents table on Wikipedia page")
    rows = table.find_all("tr")
    headers = [th.get_text(strip=True) for th in rows[0].find_all(["th", "td"])]
    data = []
    for row in rows[1:]:
        cells = [td.get_text(strip=True) for td in row.find_all("td")]
        if len(cells) >= 5:
            data.append(cells)
    df = pd.DataFrame(data, columns=headers[:len(data[0])] if data else headers)
    col_map = {}
    for c in df.columns:
        cl = c.lower()
        if "symbol" in cl or cl == "ticker":
            col_map[c] = "Symbol"
        elif "security" in cl or cl == "company":
            col_map[c] = "Security"
        elif "sector" in cl and "sub" not in cl:
            col_map[c] = "GICS Sector"
        elif "sub-industry" in cl or "subindustry" in cl:
            col_map[c] = "GICS Sub-Industry"
        elif "headquarters" in cl or "hq" in cl:
            col_map[c] = "Headquarters Location"
    df = df.rename(columns=col_map)
    expected = {"Security", "Headquarters Location"}
    if not expected.issubset(set(df.columns)):
        raise RuntimeError(f"Unexpected Wikipedia table columns: {list(df.columns)}")
    if "GICS Sector" not in df.columns:
        df["GICS Sector"] = ""
    if "GICS Sub-Industry" not in df.columns:
        df["GICS Sub-Industry"] = ""
    df = df.dropna(subset=["Security", "Headquarters Location"])
    print(f"   Found {len(df)} companies")
    return df


def geocode_city(city_str, cache):
    """Geocode a city string using Nominatim (cached by normalized city)."""
    key = city_str.lower().strip()
    if key in cache:
        return cache[key]
    try:
        resp = requests.get(
            NOMINATIM_URL,
            params={"q": city_str, "format": "json", "limit": 1, "countrycodes": ""},
            headers=NOMINATIM_HEADERS,
            timeout=10,
        )
        if resp.status_code == 200 and resp.json():
            data = resp.json()[0]
            lat, lng = float(data["lat"]), float(data["lon"])
            cache[key] = (lat, lng)
            time.sleep(1.1)  # Nominatim rate limit: 1 req/sec
            return (lat, lng)
    except Exception as e:
        print(f"   [GEOCODE WARN] {city_str}: {e}")
    cache[key] = (0.0, 0.0)
    time.sleep(1.1)
    return (0.0, 0.0)


def geocode_all(df):
    """Geocode all unique HQ cities, returning a {city: (lat, lng)} cache."""
    print("[2/4] Geocoding HQ cities (Nominatim, cached by city)...")
    cache = {}
    cities = df["Headquarters Location"].unique()
    print(f"   {len(cities)} unique cities to geocode (1 req/sec)")
    for i, city in enumerate(cities):
        lat, lng = geocode_city(city, cache)
        if i % 25 == 0:
            print(f"   [{i}/{len(cities)}] {city} -> {lat:.4f}, {lng:.4f}")
    succeeded = sum(1 for v in cache.values() if v != (0.0, 0.0))
    print(f"   Geocoded {succeeded}/{len(cities)} cities successfully")
    return cache


def enrich_from_wikipedia(company_name):
    """Fetch a company's Wikipedia summary and extract tech keyword matches."""
    try:
        api_url = "https://en.wikipedia.org/api/rest_v1/page/summary/" + \
                  company_name.replace(" ", "_")
        resp = requests.get(api_url, headers=NOMINATIM_HEADERS, timeout=8)
        if resp.status_code != 200:
            return []
        data = resp.json()
        text = (data.get("extract") or "").lower()
        if not text:
            return []
        matches = []
        for kw in TECH_KEYWORDS:
            if kw.lower() in text:
                matches.append({"name": kw, "role": "Mentioned in public profile"})
        time.sleep(0.3)
        return matches[:8]
    except Exception:
        return []


def seed_database(df, geocode_cache, do_enrich=True):
    """Insert S&P 500 companies into global_tech_stack."""
    print(f"[3/4] Seeding database{' (+ tech stack enrichment)' if do_enrich else ''}...")
    conn = get_connection()
    inserted = 0
    enriched = 0
    for _, row in df.iterrows():
        name = str(row["Security"]).strip()
        sector = str(row.get("GICS Sector", "")).strip()
        sub_industry = str(row.get("GICS Sub-Industry", "")).strip()
        hq = str(row["Headquarters Location"]).strip()
        lat, lng = geocode_cache.get(hq.lower().strip(), (0.0, 0.0))

        # Tech stack: curated first, then Wikipedia enrichment
        tech_stack = CURATED_TECHSTACKS.get(name, [])
        source = "curated"
        if not tech_stack and do_enrich:
            tech_stack = enrich_from_wikipedia(name)
            source = "wikipedia" if tech_stack else "pending"
        elif not tech_stack:
            source = "pending"

        if tech_stack:
            enriched += 1

        # Upsert: delete existing non-featured entry with same name, then insert
        conn.execute(
            "DELETE FROM global_tech_stack WHERE name = ? AND is_featured = 0",
            (name,)
        )
        conn.execute("""
            INSERT INTO global_tech_stack
                (name, city, sector, lat, lng, is_featured, tech_stack, source)
            VALUES (?, ?, ?, ?, ?, 0, ?, ?)
        """, (
            name, hq, f"{sector} • {sub_industry}" if sub_industry else sector,
            lat, lng, json.dumps(tech_stack) if tech_stack else None, source
        ))
        inserted += 1
        if inserted % 50 == 0:
            print(f"   [{inserted}/{len(df)}] inserted, {enriched} with tech stacks")
    conn.commit()
    conn.close()
    print(f"   Inserted {inserted} companies, {enriched} with tech stacks")
    return inserted, enriched


def verify():
    """Print a summary of the database after seeding."""
    print("[4/4] Verifying...")
    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) FROM global_tech_stack").fetchone()[0]
    featured = conn.execute("SELECT COUNT(*) FROM global_tech_stack WHERE is_featured=1").fetchone()[0]
    with_stack = conn.execute("SELECT COUNT(*) FROM global_tech_stack WHERE tech_stack IS NOT NULL AND tech_stack != '[]'").fetchone()[0]
    by_source = conn.execute(
        "SELECT source, COUNT(*) FROM global_tech_stack GROUP BY source ORDER BY COUNT(*) DESC"
    ).fetchall()
    conn.close()
    print(f"   Total: {total} | Featured: {featured} | With tech stack: {with_stack}")
    print("   By source:")
    for src, cnt in by_source:
        print(f"     {src}: {cnt}")


def main():
    do_enrich = "--no-enrich" not in sys.argv
    do_geocode = "--no-geocode" not in sys.argv

    df = fetch_sp500_table()

    if do_geocode:
        geocode_cache = geocode_all(df)
    else:
        geocode_cache = {c.lower().strip(): (0.0, 0.0) for c in df["Headquarters Location"].unique()}
        print("[2/4] Geocoding SKIPPED (--no-geocode)")

    seed_database(df, geocode_cache, do_enrich=do_enrich)
    verify()
    print("\nDone. S&P 500 companies are now searchable in the map search bar.")
    print("Non-authed users see location + sector; tech stack is LOCKED.")
    print("Authed users see the full tech stack where available.")


if __name__ == "__main__":
    main()
