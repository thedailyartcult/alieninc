"""Offline eval: run a parser over sampled cached detail HTML and report
how many entries it produces and average spec counts. No network."""
import re
import sqlite3
import sys

sys.path.insert(0, ".")

DETAIL_FILTERS = {
    "modernfirearms": (r"%modernfirearms.net/en/%", r"-eng/|/[a-z0-9-]+/?$"),
    "fas": (r"%man.fas.org/dod-101/sys/%", r""),
    "globalsecurity": (r"%globalsecurity.org/military/systems/%", r"intro\.|index\.|agency"),
    "hisutton": (r"%hisutton.com/%", r"Article|index"),
    "seaforces": (r"%seaforces.org%", r"index"),
}

LISTING_PAT = re.compile(
    r"/(category|tag|page/\d|index|intro|about|contact)/?$|-[a-z]+-rifles/$"
    r"|-guns[^/]*$|-launchers/$|-shotguns/$|-ammunition/$|/en/?$"
    r"|dod-101/sys/(land|ship|air|space|naval)?/?$|/dod-101/$", re.I)


def eval_source(name, parse_fn, limit=120, verbose=False):
    like = DETAIL_FILTERS[name][0]
    db = sqlite3.connect("data/scan.db")
    rows = db.execute(
        "SELECT url, html FROM raw_html WHERE url LIKE ? LIMIT 400", (like,)
    ).fetchall()
    db.close()
    n = ok = 0
    spec_counts = []
    fails = []
    for u, h in rows:
        if not h or len(h) < 8000:
            continue
        if LISTING_PAT.search(u):
            continue
        if name == "fas" and u.rstrip("/").count("/") < 5:
            continue
        n += 1
        if n > limit:
            break
        try:
            e = parse_fn(u, h)
        except Exception as ex:
            fails.append((u, str(ex)[:60]))
            continue
        if e and getattr(e, "specs", None):
            ok += 1
            spec_counts.append(len(e.specs))
        elif verbose and len(fails) < 3:
            fails.append((u, "no specs"))
    avg = sum(spec_counts) / max(len(spec_counts), 1)
    print(f"{name:16s} detail_pages={n:4d} with_specs={ok:4d} "
          f"({100 * ok / max(n, 1):.0f}%)  avg_specs={avg:.1f}")
    for u, err in fails[:2]:
        print(f"   MISS {u} :: {err}")
