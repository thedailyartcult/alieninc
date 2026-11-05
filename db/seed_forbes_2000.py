#!/usr/bin/env python3
"""
Seed the global_tech_stack table with Forbes Global 2000 companies.

Adds international small/mid-cap companies that aren't in the S&P 500.
Skips companies already in the DB (matched by name). Geocodes new HQ
cities using Nominatim (cached).

Usage:
  python3 db/seed_forbes_2000.py                    # seed + geocode
  python3 db/seed_forbes_2000.py --no-geocode       # skip geocoding
"""
import json
import os
import sys
import time
import requests
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from schema import get_connection

FORBES_URLS = [
    "https://en.wikipedia.org/wiki/Forbes_Global_2000",
    "https://en.wikipedia.org/wiki/List_of_largest_companies_by_revenue",
]
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "AlienInc-Ecosystem-Seeder/1.0 (contact: founder@alieninc.tech)"}


def fetch_forbes_2000():
    """Fetch the Forbes Global 2000 table from Wikipedia."""
    print("[1/3] Fetching Forbes Global 2000 from Wikipedia...")
    resp = requests.get(FORBES_URLS[0], headers=HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # Find all sortable tables — the Forbes list is usually the first big one
    tables = soup.find_all("table", {"class": "wikitable"})
    print(f"   Found {len(tables)} wikitables on page")

    for table in tables:
        rows = table.find_all("tr")
        if len(rows) < 50:
            continue
        headers = [th.get_text(strip=True) for th in rows[0].find_all(["th", "td"])]
        print(f"   Table has {len(rows)-1} rows, headers: {headers[:6]}")

        # Look for a table with company name + headquarters columns
        data = []
        for row in rows[1:]:
            cells = [td.get_text(strip=True) for td in row.find_all("td")]
            if len(cells) >= 3:
                data.append(cells)

        if not data:
            continue

        # Try to identify columns by header names
        h_lower = [h.lower() for h in headers]
        name_col = None
        hq_col = None
        sector_col = None
        for i, h in enumerate(h_lower):
            if "company" in h or "name" in h:
                name_col = i
            if "headquarters" in h or "hq" in h or "country" in h:
                hq_col = i
            if "industry" in h or "sector" in h:
                sector_col = i

        # If no clear name column, assume first column
        if name_col is None:
            name_col = 0
        if hq_col is None:
            # Try last column or second-to-last
            if len(headers) >= 2:
                hq_col = len(headers) - 1
            else:
                hq_col = 1

        print(f"   Using name_col={name_col}, hq_col={hq_col}, sector_col={sector_col}")

        companies = []
        for cells in data:
            if len(cells) <= max(name_col, hq_col):
                continue
            name = cells[name_col].strip()
            hq = cells[hq_col].strip() if hq_col < len(cells) else ""
            sector = cells[sector_col].strip() if sector_col is not None and sector_col < len(cells) else ""
            if name and name not in ("Rank", "#", "No."):
                companies.append({"name": name, "hq": hq, "sector": sector})

        if len(companies) > 100:
            print(f"   Extracted {len(companies)} companies")
            return companies

    # Fallback: try the second URL
    print("   Forbes table not found, trying fallback...")
    resp = requests.get(FORBES_URLS[1], headers=HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    tables = soup.find_all("table", {"class": "wikitable"})
    for table in tables:
        rows = table.find_all("tr")
        if len(rows) < 50:
            continue
        data = []
        for row in rows[1:]:
            cells = [td.get_text(strip=True) for td in row.find_all("td")]
            if len(cells) >= 2:
                data.append(cells)
        companies = []
        for cells in data:
            name = cells[0].strip() if cells else ""
            hq = cells[-1].strip() if cells else ""
            if name and len(name) > 2:
                companies.append({"name": name, "hq": hq, "sector": ""})
        if len(companies) > 100:
            print(f"   Extracted {len(companies)} companies from fallback")
            return companies

    print("   WARNING: Could not extract company list")
    return []


def geocode_city(city_str, cache):
    key = city_str.lower().strip()
    if key in cache:
        return cache[key]
    if not city_str:
        cache[key] = (0.0, 0.0)
        return (0.0, 0.0)
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
            time.sleep(1.05)
            return (lat, lng)
    except Exception as e:
        print(f"   [GEOCODE WARN] {city_str}: {e}")
    cache[key] = (0.0, 0.0)
    time.sleep(1.05)
    return (0.0, 0.0)


def main():
    do_geocode = "--no-geocode" not in sys.argv

    companies = fetch_forbes_2000()
    if not companies:
        print("No companies to seed.")
        return

    # Check which are already in the DB
    conn = get_connection()
    existing_names = set()
    for row in conn.execute("SELECT name FROM global_tech_stack"):
        existing_names.add(row["name"].lower().strip())

    new_companies = []
    for c in companies:
        if c["name"].lower().strip() not in existing_names:
            new_companies.append(c)
    print(f"[2/3] {len(new_companies)} new companies to add (skipped {len(companies) - len(new_companies)} already in DB)")

    if not new_companies:
        print("All companies already in database.")
        conn.close()
        return

    # Geocode
    geocode_cache = {}
    if do_geocode:
        print(f"   Geocoding {len(new_companies)} companies...")
        for i, c in enumerate(new_companies):
            lat, lng = geocode_city(c["hq"], geocode_cache)
            c["lat"] = lat
            c["lng"] = lng
            if (i + 1) % 50 == 0:
                print(f"   [{i+1}/{len(new_companies)}] geocoded")
    else:
        for c in new_companies:
            c["lat"] = 0.0
            c["lng"] = 0.0
        print("   Geocoding SKIPPED (--no-geocode)")

    # Insert
    print(f"[3/3] Inserting {len(new_companies)} companies into database...")
    inserted = 0
    for c in new_companies:
        conn.execute("""
            INSERT INTO global_tech_stack (name, city, sector, lat, lng, is_featured, tech_stack, source)
            VALUES (?, ?, ?, ?, ?, 0, NULL, 'pending')
        """, (c["name"], c["hq"], c["sector"], c["lat"], c["lng"]))
        inserted += 1
        if inserted % 100 == 0:
            print(f"   [{inserted}/{len(new_companies)}] inserted")
    conn.commit()

    total = conn.execute("SELECT COUNT(*) FROM global_tech_stack").fetchone()[0]
    featured = conn.execute("SELECT COUNT(*) FROM global_tech_stack WHERE is_featured=1").fetchone()[0]
    conn.close()
    print(f"\nDone. Inserted {inserted} new companies.")
    print(f"   Total: {total} | Featured (data centers): {featured} | Companies: {total - featured}")
    print("   Run geocode_and_enrich.py to geocode + enrich tech stacks.")


if __name__ == "__main__":
    main()
