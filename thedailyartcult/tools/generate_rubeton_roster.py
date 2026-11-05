#!/usr/bin/env python3
"""Generate assets/data/rubeton_painters.json from art.rubeton.app.

Pulls their public painter database (js/load2.js), normalizes it to the
same record shape as our scraped roster, and bakes collection tags.
Painting images stay on THEIR server - we only store URLs:
    https://art.rubeton.app/pics/paintings/<painterId>/<n>.jpg  n=1..count

Zero image bytes stored locally. Rerun manually to refresh:
    python3 tools/generate_rubeton_roster.py
"""

import json
import os
import re
import subprocess
import sys
import time

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS_DIR)
OUT_PATH = os.path.join(ROOT, "assets", "data", "rubeton_painters.json")
SITE = "https://art.rubeton.app"
IMG_BASE = SITE + "/pics/paintings/"

# Their engine.js set definitions (verified 2026-08-24)
BASIC_SET_IDS = {1, 4, 7, 9, 14, 15, 17, 19, 21, 22, 24, 26, 27, 28, 29, 30,
                 32, 33, 34, 35, 36, 39, 40, 41, 42, 43, 45, 46, 49, 50, 53,
                 54, 55, 57, 58, 61, 62, 63, 69, 72, 73, 75, 77, 79, 80, 82,
                 83, 94, 95, 112, 118}

# Authentic collection menu from art.rubeton.app (engine.js changeSet cases).
# These become the Filter Painters chips on playart.html.
RUBETON_SETS = {
    "basic": BASIC_SET_IDS,
    "impressionism": {2, 3, 9, 16, 17, 21, 30, 36, 49, 53, 57, 60, 61, 69,
                      77, 84, 94, 96},
    "renaissance": {24, 35, 39, 41, 42, 45, 50, 55, 87, 89, 90, 91, 92, 95,
                    98, 100, 101, 104, 106, 108, 110, 111, 112, 114},
    "realism": {5, 8, 18, 25, 37, 47, 48, 58, 85, 113, 116, 117},
    "russian": {3, 4, 5, 6, 8, 10, 11, 12, 13, 16, 19, 20, 23, 25, 26, 27,
                37, 38, 44, 47, 48, 76, 81, 84, 85, 86, 103, 105, 107, 109,
                113, 115},
    "french": {2, 9, 17, 30, 36, 40, 49, 53, 57, 58, 61, 64, 65, 69, 70, 73,
               75, 77, 93, 94, 96, 97},
}
SET_TAG_ORDER = ["basic", "impressionism", "renaissance", "realism",
                 "russian", "french"]

COUNTRY_TAGS = {
    "italian": "italian", "russian": "russian", "french": "french",
    "british": "british", "dutch": "dutch", "german": "german",
    "spanish": "spanish", "american": "american", "flemish": "flemish",
    "mexican": "mexican", "austrian": "austrian", "armenian": "armenian",
    "ukrainian": "ukrainian", "belgian": "belgian", "jewish": "",
    "swiss": "swiss", "norwegian": "norwegian", "swedish": "swedish",
    "greek": "greek", "polish": "polish", "hungarian": "hungarian",
    "czech": "czech", "portuguese": "portuguese", "danish": "danish",
    "finnish": "finnish", "japanese": "japanese", "chinese": "chinese",
}

GENRE_TAGS = {
    "realism": "realist", "romanticism": "romantic",
    "impressionism": "impressionist", "symbolism": "symbolist",
    "northern renaissance": "renaissance",
    "high renaissance": "renaissance",
    "early renaissance": "renaissance",
    "italian renaissance": "renaissance",
    "post-impressionism": "post-impressionist",
    "expressionism": "expressionist", "baroque": "baroque",
    "surrealism": "surrealist", "rococo": "rococo",
    "art nouveau": "art-nouveau", "cubism": "cubist",
    "neoclassicism": "neoclassical", "classicism": "neoclassical",
    "academic art": "academic", "orientalism": "orientalist",
    "primitivism": "primitivist", "fauvism": "fauvist",
    "abstract art": "abstract", "modern": "modern",
    "modernism": "modern", "avant-garde": "modern",
    "peredvizhniki": "realist", "socialist realism": "realist",
    "suprematism": "suprematist", "constructivism": "constructivist",
    "futurism": "futurist", "dada": "dada", "naive art": "naive",
    "pointillism": "pointillist", "neo-impressionism": "pointillist",
    "mannerism": "mannerist", "gouden eeuw": "baroque",
    "dutch golden age painting": "baroque", "genre painting": "genre",
}


def fetch(url):
    """curl-based fetch: their server 403s the default python UA."""
    out = subprocess.run(["curl", "-sf", "--max-time", "90", url],
                         capture_output=True)
    if out.returncode != 0:
        raise RuntimeError(f"fetch failed: {url}")
    return out.stdout.decode("utf-8", errors="replace")


def parse_years(years):
    match = re.search(r"(\d{3,4})", years or "")
    born = int(match.group(1)) if match else None
    nums = re.findall(r"(\d{3,4})", years or "")
    died = int(nums[1]) if len(nums) > 1 else None
    return born, died


def main():
    print("[1/3] Downloading painter database ...")
    src = fetch(SITE + "/js/load2.js")
    start = src.find("var painters")
    begin = src.find("[", start)
    end = src.find("];", start) + 1
    painters = json.loads(src[begin:end])
    print(f"      got {len(painters)} painters")

    print("[2/3] Normalizing ...")
    records = []
    for p in painters:
        born, died = parse_years(p.get("years", ""))
        if not born:
            continue
        rid = p["id"]
        tags = ["full"]
        for set_tag in SET_TAG_ORDER:
            if rid in RUBETON_SETS[set_tag]:
                tags.append(set_tag)
        if "basic" not in tags:
            # keep a popularity alias so shared tooling still works
            pass
        for genre in p.get("genre", []):
            tag = GENRE_TAGS.get(genre.strip().lower())
            # never let derived tags blur the authentic set membership
            if tag and tag not in tags and tag not in RUBETON_SETS:
                tags.append(tag)
        nationality = ""
        for nat in p.get("nationality", []):
            nationality = nationality or nat.strip()
            tag = COUNTRY_TAGS.get(nat.strip().lower())
            if tag and tag not in tags and tag not in RUBETON_SETS:
                tags.append(tag)
        count = int(p.get("paintings", 0))
        if count < 5:
            continue  # too few paintings for a fair game round
        records.append({
            "id": f"r{rid}",
            "rid": rid,
            "name": p["name"],
            "category": "",  # unused: images come from img_base pattern
            "tags": tags,
            "nationality": nationality,
            "born": born,
            "died": died or born + 60,
            "era": born // 100,
            "img_count": count,
            "img_base": IMG_BASE + str(rid) + "/",
            "years_label": p.get("years", ""),
            "source": "art.rubeton.app (Art Challenge)",
        })

    records.sort(key=lambda r: (-("basic" in r["tags"]), r["name"]))
    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": "art.rubeton.app js/load2.js painter database; "
                  "images hotlinked from art.rubeton.app/pics/paintings/",
        "count": len(records),
        "sets": {k: sorted(v) for k, v in RUBETON_SETS.items()},
        "painters": records,
    }
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))

    popular = sum(1 for r in records if "basic" in r["tags"])
    total_imgs = sum(r["img_count"] for r in records)
    tag_hist = {}
    for r in records:
        for t in r["tags"]:
            if t != "full":
                tag_hist[t] = tag_hist.get(t, 0) + 1
    size_kb = os.path.getsize(OUT_PATH) // 1024
    print(f"[3/3] wrote {OUT_PATH}")
    print(f"      {len(records)} painters ({size_kb} KB), "
          f"{popular} in basic set, {total_imgs} hotlinked paintings total")
    print(f"      set sizes: "
          f"{ {k: len(v & {r['rid'] for r in records}) for k, v in RUBETON_SETS.items()} }")
    print(f"      tags: {sorted(tag_hist.items(), key=lambda kv: -kv[1])[:16]}")


if __name__ == "__main__":
    main()
