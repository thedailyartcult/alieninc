#!/usr/bin/env python3
"""
Seed global_tech_stack with companies from Wikipedia's country-specific
company lists. Covers the top 20+ economies, giving us thousands of
international small/mid-cap companies with their industries and HQ cities.

Skips companies already in the DB (matched by name). Geocodes new HQs.

Usage:
  python3 db/seed_international.py                    # seed + geocode
  python3 db/seed_international.py --no-geocode       # skip geocoding
"""
import json
import os
import sys
import time
import requests
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from schema import get_connection

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "AlienInc-Ecosystem-Seeder/1.0 (contact: founder@alieninc.tech)"}

COUNTRY_PAGES = [
    ("United States", "https://en.wikipedia.org/wiki/List_of_companies_of_the_United_States"),
    ("Japan", "https://en.wikipedia.org/wiki/List_of_companies_of_Japan"),
    ("Germany", "https://en.wikipedia.org/wiki/List_of_companies_of_Germany"),
    ("United Kingdom", "https://en.wikipedia.org/wiki/List_of_companies_of_the_United_Kingdom"),
    ("France", "https://en.wikipedia.org/wiki/List_of_companies_of_France"),
    ("China", "https://en.wikipedia.org/wiki/List_of_companies_of_China"),
    ("India", "https://en.wikipedia.org/wiki/List_of_companies_of_India"),
    ("South Korea", "https://en.wikipedia.org/wiki/List_of_companies_of_South_Korea"),
    ("Canada", "https://en.wikipedia.org/wiki/List_of_companies_of_Canada"),
    ("Australia", "https://en.wikipedia.org/wiki/List_of_companies_of_Australia"),
    ("Switzerland", "https://en.wikipedia.org/wiki/List_of_companies_of_Switzerland"),
    ("Netherlands", "https://en.wikipedia.org/wiki/List_of_companies_of_the_Netherlands"),
    ("Brazil", "https://en.wikipedia.org/wiki/List_of_companies_of_Brazil"),
    ("Italy", "https://en.wikipedia.org/wiki/List_of_companies_of_Italy"),
    ("Spain", "https://en.wikipedia.org/wiki/List_of_companies_of_Spain"),
    ("Sweden", "https://en.wikipedia.org/wiki/List_of_companies_of_Sweden"),
    ("Singapore", "https://en.wikipedia.org/wiki/List_of_companies_of_Singapore"),
    ("Taiwan", "https://en.wikipedia.org/wiki/List_of_companies_of_Taiwan"),
    ("Mexico", "https://en.wikipedia.org/wiki/List_of_companies_of_Mexico"),
    ("Saudi Arabia", "https://en.wikipedia.org/wiki/List_of_companies_of_Saudi_Arabia"),
    ("Russia", "https://en.wikipedia.org/wiki/List_of_companies_of_Russia"),
    ("Turkey", "https://en.wikipedia.org/wiki/List_of_companies_of_Turkey"),
    ("Indonesia", "https://en.wikipedia.org/wiki/List_of_companies_of_Indonesia"),
    ("South Africa", "https://en.wikipedia.org/wiki/List_of_companies_of_South_Africa"),
    ("Ireland", "https://en.wikipedia.org/wiki/List_of_companies_of_Ireland"),
    ("Nordic", "https://en.wikipedia.org/wiki/List_of_companies_of_Denmark"),
    ("Finland", "https://en.wikipedia.org/wiki/List_of_companies_of_Finland"),
    ("Norway", "https://en.wikipedia.org/wiki/List_of_companies_of_Norway"),
    ("Poland", "https://en.wikipedia.org/wiki/List_of_companies_of_Poland"),
    ("UAE", "https://en.wikipedia.org/wiki/List_of_companies_of_the_United_Arab_Emirates"),
]


def extract_companies_from_page(html, country):
    """Extract company entries from a Wikipedia country company list page."""
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    tables = soup.find_all("table", {"class": "wikitable"})

    for table in tables:
        rows = table.find_all("tr")
        if len(rows) < 3:
            continue

        # Get headers
        header_cells = rows[0].find_all(["th", "td"])
        headers = [h.get_text(strip=True).lower() for h in header_cells]

        # Identify columns
        name_col = None
        hq_col = None
        industry_col = None
        for i, h in enumerate(headers):
            if any(k in h for k in ["name", "company"]):
                name_col = i
            if any(k in h for k in ["headquarters", "hq", "location", "city"]):
                hq_col = i
            if any(k in h for k in ["industry", "sector", "type", "products"]):
                industry_col = i

        # If no clear name column, assume first
        if name_col is None:
            name_col = 0
        # If no HQ column, use country name as fallback
        if hq_col is None:
            hq_col = None  # will use country name

        for row in rows[1:]:
            cells = [td.get_text(strip=True) for td in row.find_all("td")]
            if not cells or len(cells) <= name_col:
                continue

            name = cells[name_col].strip()
            # Skip non-company entries
            if not name or len(name) < 2 or name.startswith("See also") or name.startswith("List of"):
                continue
            # Remove footnote refs like [1], [a]
            import re
            name = re.sub(r'\[.*?\]', '', name).strip()
            if not name:
                continue

            hq = cells[hq_col].strip() if hq_col is not None and hq_col < len(cells) else country
            # Clean up HQ — might have multiple cities
            hq = hq.split("\n")[0].strip() if "\n" in hq else hq
            if not hq:
                hq = country

            industry = ""
            if industry_col is not None and industry_col < len(cells):
                industry = cells[industry_col].strip()

            companies.append({
                "name": name,
                "hq": hq,
                "sector": f"{country} • {industry}" if industry else country,
                "country": country,
            })

    return companies


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
    except Exception:
        pass
    cache[key] = (0.0, 0.0)
    time.sleep(1.05)
    return (0.0, 0.0)


def main():
    do_geocode = "--no-geocode" not in sys.argv

    # Get existing company names
    conn = get_connection()
    existing = set()
    for row in conn.execute("SELECT LOWER(name) FROM global_tech_stack"):
        existing.add(row[0])

    all_new = []
    print("[1/3] Fetching company lists from Wikipedia...")
    for country, url in COUNTRY_PAGES:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                print(f"   {country}: HTTP {resp.status_code}")
                continue
            companies = extract_companies_from_page(resp.text, country)
            new = [c for c in companies if c["name"].lower().strip() not in existing]
            for c in new:
                existing.add(c["name"].lower().strip())
            all_new.extend(new)
            print(f"   {country}: {len(companies)} found, {len(new)} new")
            time.sleep(0.5)  # Be nice to Wikipedia
        except Exception as e:
            print(f"   {country}: ERROR {e}")

    print(f"\n   Total new companies: {len(all_new)}")

    if not all_new:
        print("No new companies to add.")
        conn.close()
        return

    # Geocode
    geocode_cache = {}
    if do_geocode:
        print(f"[2/3] Geocoding {len(all_new)} companies...")
        for i, c in enumerate(all_new):
            lat, lng = geocode_city(c["hq"], geocode_cache)
            c["lat"] = lat
            c["lng"] = lng
            if (i + 1) % 100 == 0:
                print(f"   [{i+1}/{len(all_new)}] geocoded")
    else:
        for c in all_new:
            c["lat"] = 0.0
            c["lng"] = 0.0
        print("[2/3] Geocoding SKIPPED")

    # Insert
    print(f"[3/3] Inserting {len(all_new)} companies...")
    inserted = 0
    for c in all_new:
        conn.execute("""
            INSERT INTO global_tech_stack (name, city, sector, lat, lng, is_featured, tech_stack, source)
            VALUES (?, ?, ?, ?, ?, 0, NULL, 'pending')
        """, (c["name"], c["hq"], c["sector"], c["lat"], c["lng"]))
        inserted += 1
        if inserted % 200 == 0:
            print(f"   [{inserted}/{len(all_new)}] inserted")
    conn.commit()

    total = conn.execute("SELECT COUNT(*) FROM global_tech_stack").fetchone()[0]
    featured = conn.execute("SELECT COUNT(*) FROM global_tech_stack WHERE is_featured=1").fetchone()[0]
    geocoded = conn.execute("SELECT COUNT(*) FROM global_tech_stack WHERE lat != 0.0 AND lng != 0.0").fetchone()[0]
    conn.close()
    print(f"\nDone. Inserted {inserted} new international companies.")
    print(f"   Total: {total} | Featured data centers: {featured} | Companies: {total - featured} | Geocoded: {geocoded}")


if __name__ == "__main__":
    main()
