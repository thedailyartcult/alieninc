#!/usr/bin/env python3
"""
Background geocoder + tech-stack enricher for global_tech_stack.

Run with nohup — geocodes all companies with lat=0/lng=0 using Nominatim
(cached, 1 req/sec), then enriches tech stacks for companies with
source='pending' using Wikipedia article text mining.

Usage:
  nohup python3 db/geocode_and_enrich.py > /tmp/geocode_enrich.log 2>&1 &
"""
import json
import os
import sys
import time
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from schema import get_connection

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
WIKI_API = "https://en.wikipedia.org/api/rest_v1/page/summary/"
HEADERS = {"User-Agent": "AlienInc-Ecosystem-Seeder/1.0 (contact: founder@alieninc.tech)"}

TECH_KEYWORDS = [
    "AWS", "Azure", "Google Cloud", "GCP", "Kubernetes", "Docker",
    "React", "Angular", "Vue", "Node.js", "Python", "Java", "JavaScript",
    "TypeScript", "Go", "Rust", "C++", "C#", ".NET", "Swift", "Kotlin",
    "Scala", "Ruby", "PHP", "Perl", "Hadoop", "Spark", "Kafka",
    "PostgreSQL", "MySQL", "MongoDB", "Cassandra", "Redis",
    "SQL Server", "Elasticsearch", "GraphQL", "gRPC", "Terraform",
    "Ansible", "Jenkins", "GitLab", "Linux", "Windows Server",
    "VMware", "OpenStack", "Snowflake", "Databricks",
    "TensorFlow", "PyTorch", "SAP", "Salesforce", "ServiceNow",
    "Spring Boot", "Django", "Flask", "FastAPI",
    "Nginx", "Apache", "Cloudflare",
    "RabbitMQ", "Helm", "Istio", "Consul", "Vault",
]


def geocode_city(city_str, cache):
    key = city_str.lower().strip()
    if key in cache:
        return cache[key]
    try:
        resp = requests.get(
            NOMINATIM_URL,
            params={"q": city_str, "format": "json", "limit": 1},
            headers=HEADERS,
            timeout=10,
        )
        if resp.status_code == 200 and resp.json():
            data = resp.json()[0]
            lat, lng = float(data["lat"]), float(data["lon"])
            cache[key] = (lat, lng)
            time.sleep(1.1)
            return (lat, lng)
    except Exception as e:
        print(f"  [GEOCODE WARN] {city_str}: {e}")
    cache[key] = (None, None)
    time.sleep(1.1)
    return (None, None)


def enrich_from_wikipedia(company_name):
    try:
        resp = requests.get(WIKI_API + company_name.replace(" ", "_").replace(",", ""), headers=HEADERS, timeout=8)
        if resp.status_code != 200:
            return []
        data = resp.json()
        text = ((data.get("extract") or "") + " " + (data.get("description") or "")).lower()
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


def main():
    conn = get_connection()

    # Phase 1: Geocode
    print("=== Phase 1: Geocoding ===")
    ungeocoded = conn.execute(
        "SELECT DISTINCT city FROM global_tech_stack WHERE lat = 0.0 AND lng = 0.0 AND is_featured = 0"
    ).fetchall()
    cities = [r["city"] for r in ungeocoded if r["city"]]
    print(f"  {len(cities)} unique cities to geocode")
    cache = {}
    done = 0
    for city in cities:
        lat, lng = geocode_city(city, cache)
        if lat is not None:
            conn.execute(
                "UPDATE global_tech_stack SET lat = ?, lng = ?, updated_at = datetime('now') WHERE city = ? AND lat = 0.0",
                (lat, lng, city)
            )
            conn.commit()
        done += 1
        if done % 25 == 0:
            print(f"  [{done}/{len(cities)}] geocoded")
    print(f"  Geocoding complete: {done} cities processed")

    # Phase 2: Enrich tech stacks
    print("=== Phase 2: Wikipedia tech-stack enrichment ===")
    pending = conn.execute(
        "SELECT name FROM global_tech_stack WHERE source = 'pending' AND is_featured = 0"
    ).fetchall()
    names = [r["name"] for r in pending]
    print(f"  {len(names)} companies to enrich")
    enriched = 0
    for i, name in enumerate(names):
        stack = enrich_from_wikipedia(name)
        if stack:
            conn.execute(
                "UPDATE global_tech_stack SET tech_stack = ?, source = 'wikipedia', updated_at = datetime('now') WHERE name = ?",
                (json.dumps(stack), name)
            )
            conn.commit()
            enriched += 1
        if (i + 1) % 50 == 0:
            print(f"  [{i+1}/{len(names)}] processed, {enriched} enriched")
    print(f"  Enrichment complete: {enriched}/{len(names)} companies got tech stacks")

    # Summary
    total = conn.execute("SELECT COUNT(*) FROM global_tech_stack").fetchone()[0]
    with_stack = conn.execute("SELECT COUNT(*) FROM global_tech_stack WHERE tech_stack IS NOT NULL AND tech_stack != '[]'").fetchone()[0]
    geocoded = conn.execute("SELECT COUNT(*) FROM global_tech_stack WHERE lat != 0.0 AND lng != 0.0").fetchone()[0]
    conn.close()
    print(f"\n=== Final Summary ===")
    print(f"  Total: {total} | With tech stack: {with_stack} | Geocoded: {geocoded}")


if __name__ == "__main__":
    main()
