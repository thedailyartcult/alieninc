#!/usr/bin/env python3
"""Regenerate data/featured-facilities.js from db/seed_tech_stack.py DATACENTERS.

The network map ("Where The Network Operates") loads facilities from the
/api/techstack SQLite endpoint when the laptop backend is up, and falls back
to this static snapshot on GitHub Pages. Re-run after editing DATACENTERS.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'db'))
from seed_tech_stack import DATACENTERS  # noqa: E402

rows = []
for d in DATACENTERS:
    if not d.get('is_featured'):
        continue
    rows.append({
        'name': d['name'],
        'city': d.get('city', ''),
        'sector': d.get('sector', ''),
        'lat': d.get('lat'),
        'lng': d.get('lng'),
        'markerColor': d.get('marker_color'),
        'techStack': d.get('tech_stack') or [],
    })
rows.sort(key=lambda r: r['name'])

out = os.path.join(ROOT, 'data', 'featured-facilities.js')
with open(out, 'w') as f:
    f.write('/**\n')
    f.write(' * FEATURED_FACILITIES — static snapshot of the curated facility dataset\n')
    f.write(' * (data centers / semiconductor fabs) so the "Where The Network Operates"\n')
    f.write(' * map renders on static hosting (GitHub Pages) with no backend.\n')
    f.write(' * Generated from db/seed_tech_stack.py DATACENTERS — regenerate after edits:\n')
    f.write(' *   python3 tools/export-featured-facilities.py\n')
    f.write(' */\n')
    f.write('window.FEATURED_FACILITIES = ')
    json.dump(rows, f, ensure_ascii=False)
    f.write(';\n')
print(f'{len(rows)} facilities written to {out}')
