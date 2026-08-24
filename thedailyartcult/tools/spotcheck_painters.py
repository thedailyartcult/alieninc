#!/usr/bin/env python3
"""Spot-check painters.json against the production Commons fetch path.

Samples N painters and replays the exact API call play.html's
fetchPaintingsForPainter() makes, reporting how many yield usable paintings.
"""

import argparse
import json
import os
import random
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from generate_painters import http_json, OUT_PATH, UA  # noqa: E402


def production_fetch(category):
    """Mirror play.html fetchPaintingsForPainter exactly."""
    params = {
        "action": "query",
        "generator": "categorymembers",
        "gcmtitle": "Category:" + category,
        "gcmtype": "file",
        "gcmlimit": 45,
        "prop": "imageinfo",
        "iiprop": "url|dimensions",
        "iiurlwidth": 800,
        "format": "json",
        "origin": "*",
    }
    data = http_json("https://commons.wikimedia.org/w/api.php", params)
    pages = data.get("query", {}).get("pages")
    if not pages:
        return []
    paintings = []
    for page in pages.values():
        info = page.get("imageinfo", [{}])[0]
        if info.get("thumburl") and info.get("width", 0) > 220 \
                and info.get("height", 0) > 160:
            paintings.append(info["thumburl"])
    return paintings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=30)
    args = parser.parse_args()

    with open(OUT_PATH, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    painters = payload["painters"]
    sample = random.sample(painters, min(args.sample, len(painters)))

    ok = fail = 0
    failures = []
    for i, painter in enumerate(sample):
        manifest_path = os.path.join(
            os.path.dirname(OUT_PATH), "..", "painters", painter["id"],
            "manifest.json")
        manifest_ok = False
        n_manifest = 0
        try:
            with open(manifest_path, "r", encoding="utf-8") as fh:
                m = json.load(fh)
            if isinstance(m.get("paintings"), list):
                n_manifest = len(m["paintings"])
                manifest_ok = n_manifest >= 4
        except (OSError, ValueError):
            pass
        try:
            urls = production_fetch(painter["category"])
        except RuntimeError as exc:
            urls = []
            print(f"  [{i + 1}] {painter['name']}: HTTP error {exc}")
        live_ok = len(urls) >= 4 or manifest_ok
        if live_ok:
            ok += 1
            print(f"  [{i + 1}] OK   {painter['name']:32s} "
                  f"folder:{n_manifest:2d} imgs")
        else:
            fail += 1
            failures.append((painter["name"], painter["category"],
                             len(urls)))
            print(f"  [{i + 1}] FAIL {painter['name']:32s} "
                  f"folder:{n_manifest}")
        time.sleep(0.15)

    print(f"\n{ok}/{ok + fail} sampled painters render "
          f"({100 * ok / max(1, ok + fail):.0f}% pass rate)")
    if failures:
        print("failures:")
        for name, cat, n in failures:
            print(f"  - {name} -> {cat} ({n} imgs)")
    sys.exit(0 if not failures else 1)


if __name__ == "__main__":
    main()
