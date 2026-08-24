"""CLI for the A-SAN deep scanner.

Commands:
  seed       load existing catalog + seeds file into the scan store
  discover   pull the sitemap and enqueue category-mapped product URLs
  crawl      process the queued product URLs (resumable)
  run        seed + discover + crawl + export (the full cycle)
  export     write catalog-data.json from the scan store
  status     queue/entry summary
  import-janes  ingest a research-desk CSV (licensed Janes data)

Examples:
  python -m scan run --categories aircraft,uavs --limit 25
  python -m scan run                        # deep, full run
  python -m scan crawl --resume
  python -m scan discover
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

from .config import Settings, CATEGORY_KEYS, category_key, classify_article
from .engine import Engine
from .models import CatalogEntry, SourceRef, now_iso
from .parsers import janes_import_csv
from .parsers_militaryfactory import parse_militaryfactory_country, build_entries, parse_militaryfactory_detail
from .parsers_designation import parse_designation_listing
from .parsers_missilethreat import parse_missilethreat_listing
from .parsers_modernfirearms import parse_modernfirearms_listing, MODERNFIREARMS_SEED_URLS
from .parsers_milrem import MILREM_PRODUCT_URLS
from .parsers_fas import FAS_INDEX_URLS, parse_fas_listing
from .parsers_wikipedia import WIKIPEDIA_LIST_URLS, parse_wikipedia_list
from .parsers_warsanctions import parse_warsanctions_uav_listing
from .parsers_armyguide import parse_armyguide_listing
from .picklist import CurationRules, curate, write_outputs
from .patent_feed import feed_patents, feed_from_file
from .play_build import build_play_dataset


def _settings(args) -> Settings:
    s = Settings(
        min_delay_seconds=args.delay,
        max_workers=args.workers,
        max_retries=args.retries,
        refresh=args.refresh,
        limit=args.limit,
        obey_robots=not args.no_robots,
        espacenet_ops_key=os.environ.get("ESPACENET_OPS_KEY", ""),
        espacenet_ops_secret=os.environ.get("ESPACENET_OPS_SECRET", ""),
        uspto_odp_token=os.environ.get("USPTO_ODP_TOKEN", ""),
    )
    if args.catalog:
        s.catalog_path = Path(args.catalog)
    if args.db:
        s.db_path = Path(args.db)
    if args.seeds:
        s.seeds_path = Path(args.seeds)
    return s


def _categories(args) -> list[str]:
    if not args.categories:
        return list(CATEGORY_KEYS.values())
    out = []
    for c in args.categories.split(","):
        c = c.strip()
        if not c:
            continue
        key = c if c in CATEGORY_KEYS else category_key(c)
        out.append(CATEGORY_KEYS[key])
    return out


def cmd_seed(args, s: Settings):
    eng = Engine(s)
    eng.seed_from_catalog()
    eng.seed_file()
    print(json.dumps(eng.status(), indent=2))
    eng.close()


def cmd_discover(args, s: Settings):
    eng = Engine(s)
    eng.seed_from_catalog()
    wanted = set(category_key(c) for c in _categories(args))
    added = eng.discover(wanted)
    print(f"discovered/enqueued: {added}")
    print(json.dumps(eng.status(), indent=2))
    eng.close()


def cmd_crawl(args, s: Settings):
    eng = Engine(s)
    eng.seed_from_catalog()
    domains = [d.strip() for d in args.domains.split(",")] if getattr(args, "domains", None) else None
    eng.crawl(_categories(args), limit=args.limit, domains=domains)
    print(json.dumps(eng.status(), indent=2))
    eng.close()


def cmd_run(args, s: Settings):
    eng = Engine(s)
    eng.seed_from_catalog()
    eng.seed_file()
    wanted = set(category_key(c) for c in _categories(args))
    eng.discover(wanted)
    eng.crawl(_categories(args), limit=args.limit)
    eng.export()
    print(json.dumps(eng.status(), indent=2))
    eng.close()


def cmd_discover_sources(args, s: Settings):
    """Enumerate the catalog listing pages of the three fact-extraction sources
    (designation-systems.net, missilethreat.csis.org, modernfirearms.net) and
    enqueue every detail URL into the scan store. robots.txt-gated, polite,
    cached. Run this once per source to populate the queue, then `crawl`."""
    eng = Engine(s)
    eng.seed_from_catalog()
    summary: dict[str, int] = {}

    # --- designation-systems.net: /usmilav/missiles.html catalog table ---
    ds_listing_url = "https://www.designation-systems.net/usmilav/missiles.html"
    res = eng._fetcher("www.designation-systems.net").fetch(
        ds_listing_url, store=eng.store, use_cache=True)
    n_ds = 0
    if res.status == 200 and res.html:
        for url, _desig, _mfr in parse_designation_listing(res.html, ds_listing_url):
            n_ds += eng.store.enqueue(
                url, "www.designation-systems.net", kind="product")
    summary["designation-systems.net"] = n_ds

    # --- missilethreat.csis.org: /missile/ dropdown (full catalog) ---
    mt_listing_url = "https://missilethreat.csis.org/missile/"
    res = eng._fetcher("missilethreat.csis.org").fetch(
        mt_listing_url, store=eng.store, use_cache=True)
    n_mt = 0
    if res.status == 200 and res.html:
        for url, _name in parse_missilethreat_listing(res.html):
            n_mt += eng.store.enqueue(
                url, "missilethreat.csis.org", kind="product")
    summary["missilethreat.csis.org"] = n_mt

    # --- modernfirearms.net: each working category index page ---
    n_mf = 0
    for _mf_cat, idx_url in MODERNFIREARMS_SEED_URLS.items():
        res = eng._fetcher("modernfirearms.net").fetch(
            idx_url, store=eng.store, use_cache=True)
        if res.status == 200 and res.html:
            for url, _name, _excerpt in parse_modernfirearms_listing(res.html):
                n_mf += eng.store.enqueue(
                    url, "modernfirearms.net", kind="product")
    summary["modernfirearms.net"] = n_mf

    # --- milremrobotics.com: 6 known UGV product pages ---
    n_milrem = 0
    for url in MILREM_PRODUCT_URLS:
        n_milrem += eng.store.enqueue(
            url, "milremrobotics.com", category="UGVs", kind="product")
    summary["milremrobotics.com"] = n_milrem

    # --- fas.org (man.fas.org): 3 equipment indexes → detail pages ---
    n_fas = 0
    for idx_url in FAS_INDEX_URLS:
        res = eng._fetcher("man.fas.org").fetch(
            idx_url, store=eng.store, use_cache=True)
        if res.status == 200 and res.html:
            for url in parse_fas_listing(res.html, idx_url):
                n_fas += eng.store.enqueue(
                    url, "man.fas.org", kind="product")
    summary["man.fas.org"] = n_fas

    print(json.dumps({
        "enqueued_by_source": summary,
        "total_enqueued": sum(summary.values()),
        "status": eng.status(),
        "next": "python -m scan crawl --categories uavs,naval-vessels,armored-vehicles-and-equipment,automotive-vehicles,air-launched-munitions,ew-assets",
    }, indent=2))
    eng.close()


def cmd_discover_ua(args, s: Settings):
    """Enumerate the two Ukraine-theater sources (added 2026-08):
    war-sanctions.gur.gov.ua — GUR portal, UAV catalog via /en/uav pagination;
    en.defence-ua.com — Defense Express weapon_and_tech articles via monthly
    post-YYYY-MM.xml sitemaps. robots.txt-gated, polite, cached. Run once, then
    `crawl`. war-sanctions is crawled at a fixed 3s/host delay (net.py): it is a
    government intelligence portal operated during an active war."""
    eng = Engine(s)
    eng.seed_from_catalog()
    summary: dict[str, int] = {}

    # --- war-sanctions.gur.gov.ua: paginated UAV catalog (/en/uav?page=N) ---
    n_ws = 0
    seen_ids: set[str] = set()
    empty_pages = 0
    for page in range(1, args.max_ws_pages + 1):
        res = eng._fetcher("war-sanctions.gur.gov.ua").fetch(
            f"https://war-sanctions.gur.gov.ua/en/uav?page={page}&per-page=12",
            store=eng.store, use_cache=True)
        if res.status != 200 or not res.html:
            break
        urls = parse_warsanctions_uav_listing(res.html)
        fresh = [u for u in urls
                 if u.rstrip("/").rsplit("/", 1)[-1] not in seen_ids]
        for u in urls:
            seen_ids.add(u.rstrip("/").rsplit("/", 1)[-1])
        for u in fresh:
            n_ws += eng.store.enqueue(
                u, "war-sanctions.gur.gov.ua", category="UAVs", kind="product")
        if not fresh:
            empty_pages += 1
            if empty_pages >= 2 and seen_ids:
                break
    summary["war-sanctions.gur.gov.ua"] = n_ws

    # --- en.defence-ua.com: articles from monthly post-YYYY-MM.xml sitemaps.
    # NOTE: the EN sitemap index omits the post-* files, but they exist mirrored
    # under https://en.defence-ua.com/sitemap/post-YYYY-MM.xml — we walk the
    # most recent N months directly (robots.txt does not disallow /sitemap/).
    n_de = 0
    loc_re = re.compile(
        r"<loc>(https://en\.defence-ua\.com/(?:weapon_and_tech|analysis)/[^<]+\.html)</loc>")
    now = datetime.now(timezone.utc)
    months = []
    for back in range(args.de_months):
        y, m = now.year, now.month - back
        while m <= 0:
            m += 12
            y -= 1
        months.append(f"{y}-{m:02d}")
    for ym in months:
        res = eng._fetcher("en.defence-ua.com").fetch(
            f"https://en.defence-ua.com/sitemap/post-{ym}.xml",
            store=eng.store, use_cache=True)
        if res.status != 200 or not res.html:
            continue
        for m in loc_re.finditer(res.html):
            n_de += eng.store.enqueue(m.group(1), "en.defence-ua.com", kind="article")
    summary["en.defence-ua.com"] = n_de

    print(json.dumps({
        "enqueued_by_source": summary,
        "total_enqueued": sum(summary.values()),
        "status": eng.status(),
        "next": ("python -m scan crawl --categories uavs "
                 "(war-sanctions entries are pre-categorized as UAVs); "
                 "defence-ua articles self-classify at parse time"),
    }, indent=2))
    eng.close()


GS_HUB_PAGES = {"ammo", "dumb", "intro", "lasers", "missile", "smart"}


def cmd_discover_more(args, s: Settings):
    """Enumerate the four round-2 sources (added 2026-08-22):
    baykartech.com (EN sitemap /en/uav/ product pages), army-guide.com
    (/eng/products.php pagination -> productNNNN.html), www.globalsecurity.org
    (BFS over /military/systems/ hub pages only — leaves enqueued unfetched),
    www.hisutton.com (homepage article links). robots.txt-gated, polite,
    cached. Run once, then `crawl`."""
    eng = Engine(s)
    eng.seed_from_catalog()
    summary: dict[str, int] = {}

    # --- baykartech.com: EN sitemap -> /en/uav/<slug>/ product pages ---
    n_bk = 0
    res = eng._fetcher("baykartech.com").fetch(
        "https://baykartech.com/en/sitemap.xml", store=eng.store, use_cache=True)
    if res.status == 200 and res.html:
        for m in re.finditer(r"<loc>(https?://baykartech\.com/en/uav/[^<]+)</loc>", res.html):
            n_bk += eng.store.enqueue(m.group(1), "baykartech.com",
                                      category="UAVs", kind="product")
    summary["baykartech.com"] = n_bk

    # --- army-guide.com: products.php pagination -> detail URLs ---
    n_ag = 0
    seen_products: set[str] = set()
    for p in range(args.ag_pages):
        lurl = (f"https://army-guide.com/eng/products.php?pageNum={p}"
                f"&p1=&p2=&p3=1&p4=&p5=&p6=")
        res = eng._fetcher("army-guide.com").fetch(lurl, store=eng.store,
                                                   use_cache=True)
        if res.status != 200 or not res.html:
            continue
        fresh = [u for u in parse_armyguide_listing(res.html) if u not in seen_products]
        for u in fresh:
            seen_products.add(u)
            n_ag += eng.store.enqueue(u, "army-guide.com", kind="product")
    summary["army-guide.com"] = n_ag

    # --- globalsecurity.org: BFS over hub/index pages only; leaves are
    #     enqueued WITHOUT being fetched (politeness + bounded discovery).
    n_gs = 0
    seeds = [
        "https://www.globalsecurity.org/military/systems/munitions/intro.htm",
        "https://www.globalsecurity.org/military/systems/munitions/ammo.htm",
        "https://www.globalsecurity.org/military/systems/munitions/dumb.htm",
        "https://www.globalsecurity.org/military/systems/munitions/lasers.htm",
        "https://www.globalsecurity.org/military/systems/munitions/missile.htm",
        "https://www.globalsecurity.org/military/systems/munitions/smart.htm",
        "https://www.globalsecurity.org/military/systems/aircraft/index.html",
        "https://www.globalsecurity.org/military/systems/ground/index.html",
        "https://www.globalsecurity.org/military/systems/aircraft/systems/index.html",
    ]
    link_re = re.compile(r'href="([^"#?]+?\.(?:htm|html))"', re.I)
    visited: set[str] = set()
    queue = list(seeds)
    while queue and len(visited) < args.gs_max_hubs:
        page_url = queue.pop(0)
        norm = page_url.split("#")[0]
        if norm in visited:
            continue
        visited.add(norm)
        res = eng._fetcher("www.globalsecurity.org").fetch(norm, store=eng.store,
                                                           use_cache=True)
        if res.status != 200 or not res.html:
            continue
        base = norm.rsplit("/", 1)[0]
        for m in link_re.finditer(res.html):
            href = m.group(1).split("#")[0]
            if href.startswith(("http://", "https://")):
                if "globalsecurity.org" not in href or "/military/systems/" not in href:
                    continue
                child = href
                path = "/" + child.split("globalsecurity.org/", 1)[1]
            elif href.startswith("/"):
                child = f"https://www.globalsecurity.org{href}"
                path = href
            else:
                path = f"{base}/{href}"
                child = f"https://www.globalsecurity.org{path}"
            is_hub = path.endswith("/index.html") or \
                any(path.endswith(f"/{hub}.htm") for hub in GS_HUB_PAGES)
            if is_hub:
                if child not in visited and len(visited) < args.gs_max_hubs:
                    queue.append(child)
                continue
            n_gs += eng.store.enqueue(child, "www.globalsecurity.org", kind="product")
    summary["www.globalsecurity.org"] = n_gs

    # --- hisutton.com: homepage article links (flat *.html) ---
    n_hs = 0
    res = eng._fetcher("www.hisutton.com").fetch(
        "https://www.hisutton.com/", store=eng.store, use_cache=True)
    if res.status == 200 and res.html:
        for m in re.finditer(r'href="(/[^"/]+?\.html)"', res.html):
            url2 = f"https://www.hisutton.com{urllib.parse.quote(m.group(1))}"
            n_hs += eng.store.enqueue(url2, "www.hisutton.com", kind="product")
    summary["www.hisutton.com"] = n_hs

    print(json.dumps({
        "enqueued_by_source": summary,
        "total_enqueued": sum(summary.values()),
        "status": eng.status(),
        "next": ("python -m scan crawl (baykar pre-categorized UAVs; army-guide "
                 "self-categorizes; globalsecurity/hisutton classify at parse time)"),
    }, indent=2))
    eng.close()


def cmd_discover_seaforces(args, s: Settings):
    """Enumerate seaforces.org via its flat sitemap.txt (robots allow-all):
    enqueue /wpnsys/, /usnships/ and /marint/ pages. /usnair/, /usmcair/
    (squadron org pages) and /spcrep/ are deliberately skipped. Run once,
    then `crawl`."""
    eng = Engine(s)
    eng.seed_from_catalog()
    res = eng._fetcher("www.seaforces.org").fetch(
        "https://www.seaforces.org/sitemap.txt", store=eng.store, use_cache=True)
    n = 0
    if res.status == 200 and res.html:
        for line in res.html.splitlines():
            u = line.strip()
            if not u or not u.startswith("http"):
                continue
            path = urllib.parse.urlsplit(u).path.lower()
            if any(path.startswith(p) for p in ("/wpnsys/", "/usnships/", "/marint/")) \
                    and path.endswith(".htm"):
                n += eng.store.enqueue(u, "www.seaforces.org", kind="product")
    print(json.dumps({
        "enqueued_by_source": {"www.seaforces.org": n},
        "status": eng.status(),
        "next": "python -m scan crawl",
    }, indent=2))
    eng.close()


def cmd_recategorize(args, s: Settings):
    """Catalog quality pass (no inflation):
    1. Uncategorized entries -> classify_article on title+description+specs.
    2. weaponsystems.net entries -> re-run the corrected platform classifier
       (ground vehicles now checked before naval; 'amphibious' APCs no longer
       misfiled as Naval vessels).
    3. Report near-duplicate designation groups (punctuation variants) without
       merging them automatically.
    Safe to run while crawling (SQLite WAL), best run after."""
    import re as _re
    eng = Engine(s)
    changes: dict[str, int] = {"recategorized_uncategorized": 0,
                               "reclassified_weaponsystems": 0}
    from .parsers_weaponsystems import _classify_weaponsystem
    for row in eng.store.raw_entries():
        d = row["data"]
        text = " ".join([row["designation"], d.get("description", ""),
                         *d.get("specs", [])]).lower()
        cat = row["category"].strip()
        new_cat = ""
        if not cat or cat == "Uncategorized":
            key = classify_article(text)
            if key:
                new_cat = CATEGORY_KEYS[key]
        elif "weaponsystems.net" in (d.get("sources") or [{}])[0].get("url", ""):
            fixed = _classify_weaponsystem(row["designation"],
                                           d.get("description", ""),
                                           d.get("specs", []))
            if fixed and fixed != cat and fixed != "Aircraft":
                # 'Aircraft' was the old blanket fallback — only accept it if
                # the entry genuinely looks like one.
                if fixed != "Aircraft" or any(
                        k in text for k in ("helicopter", "aircraft", "plane",
                                            "rotor", "wing", "airframe")):
                    new_cat = fixed
            elif cat == "Aircraft" and not any(
                    k in text for k in ("helicopter", "aircraft", "plane",
                                        "rotorcraft", "airframe", "fuselage",
                                        "wing ", "jet")) \
                    and _re.search(r"\b(rifle|pistol|carbine|sniper|handgun|"
                                   r"revolver|submachine gun)\b", text):
                # Old blanket-fallback victims: firearms misfiled as Aircraft.
                new_cat = "Small arms"
        if new_cat and new_cat != cat:
            eng.store.set_category(row["fingerprint"], new_cat)
            changes["recategorized_uncategorized" if (
                not cat or cat == "Uncategorized")
                else "reclassified_weaponsystems"] += 1

    # 3. near-duplicate report (normalized keys, no auto-merge)
    groups: dict[str, list[str]] = {}
    for row in eng.store.raw_entries():
        k = " ".join(_re.sub(r"[^a-z0-9]+", " ", row["designation"].lower()).split())
        src = (row["data"].get("sources") or [{}])[0].get("url", "?")
        groups.setdefault(k, []).append(
            f"{row['designation']} [{row['category']}] {src.split('/')[2] if '://' in src else src}")
    dup_groups = [v for v in groups.values() if len(v) > 1]

    print(json.dumps({
        "changes": changes,
        "near_duplicate_groups": len(dup_groups),
        "examples": dup_groups[:15],
        "entries": eng.store.entry_count(),
        "next": ("python -m scan dedupe-keys  (after crawls finish) then "
                 "python -m scan export"),
    }, indent=2))
    eng.close()


def cmd_dedupe_keys(args, s: Settings):
    """Rebuild normalized designation keys and merge punctuation-variant
    duplicates ('LAV-25' vs 'LAV 25'). Run ONLY when no crawl is writing."""
    eng = Engine(s)
    merged = eng.store.rebuild_designation_keys()
    print(json.dumps({
        "duplicates_merged": merged,
        "entries": eng.store.entry_count(),
        "next": "python -m scan export",
    }, indent=2))
    eng.close()


def cmd_reenrich_weaponsystems(args, s: Settings):
    """Re-parse every weaponsystems.net entry from CACHED HTML with the current
    parser (handles the site's redesigned generalFactsTable* markup) and update
    specs + category. No network traffic — cache-only by construction."""
    from .parsers_weaponsystems import parse_weaponsystem
    eng = Engine(s)
    updated, spec_upgrades, skipped = 0, 0, 0
    for row in eng.store.raw_entries():
        srcs = [x.get("url", "") for x in row["data"].get("sources", [])]
        ws = [u for u in srcs if "weaponsystems.net" in u]
        if not ws:
            continue
        html = eng.store.get_html(ws[0])
        if not html:
            skipped += 1
            continue
        e = parse_weaponsystem(ws[0], html, "")
        if not e:
            skipped += 1
            continue
        d = row["data"]
        new_specs, new_cat = e.specs, (e.category or "").strip()
        old_cat = row["category"].strip()
        changed = False
        if len(new_specs) > len(d.get("specs", [])):
            d["specs"] = new_specs
            spec_upgrades += 1
            changed = True
        if new_cat and new_cat != "Aircraft" and new_cat != old_cat:
            # 'Aircraft' accepted only with real aviation signal in the text
            text = " ".join([e.designation, e.description, *new_specs]).lower()
            if new_cat != "Aircraft" or any(
                    k in text for k in ("helicopter", "aircraft", "plane",
                                        "rotorcraft", "rotor", "airframe",
                                        "fuselage", "sortie")):
                d["category"] = new_cat
                eng.store.set_category(row["fingerprint"], d["category"])
                updated += 1
                changed = True
        if changed:
            self_conn_update = (
                "UPDATE entries SET data=? WHERE fingerprint=?")
            eng.store._lock.acquire()
            try:
                eng.store._conn.execute(
                    self_conn_update,
                    (json.dumps(d, ensure_ascii=False), row["fingerprint"]))
                eng.store._conn.commit()
            finally:
                eng.store._lock.release()
    print(json.dumps({
        "entries_reclassified": updated,
        "spec_sets_upgraded": spec_upgrades,
        "skipped_no_cache_or_unparseable": skipped,
        "entries_total": eng.store.entry_count(),
        "next": "python -m scan recategorize && python -m scan dedupe-keys && python -m scan export",
    }, indent=2))
    eng.close()


def cmd_import_wikipedia(args, s: Settings):
    """Parse the Wikipedia 'List of military electronics' pages inline and
    upsert all entries directly (no crawl queue — the list pages ARE the data).
    Also enqueues individual pages from Wikipedia categories for a follow-up
    crawl (those have infobox spec tables).

    --wiki-categories: comma-separated list of Wikipedia category names to
    enqueue (default: Electronic_countermeasures plus any extras specified).
    Use 'all' to enqueue the full set of EW-relevant categories."""
    import time as _time
    import urllib.request, json as _json

    eng = Engine(s)
    eng.seed_from_catalog()
    summary: dict[str, int] = {}

    # 1. Parse the two master list pages (A–G, M–Z) — entries go straight in
    total_list_entries = 0
    for list_url in WIKIPEDIA_LIST_URLS:
        res = eng._fetcher("en.wikipedia.org").fetch(
            list_url, store=eng.store, use_cache=True)
        n = 0
        if res.status == 200 and res.html:
            entries = parse_wikipedia_list(res.html, list_url)
            for e in entries:
                op = eng.store.upsert_entry(e, list_url)
                if op == "inserted":
                    n += 1
            eng.store.mark(list_url, "done", status=200)
        summary[list_url.split("/")[-1][:20]] = n
        total_list_entries += n
    summary["list_total_inserted"] = total_list_entries

    # 2. Enqueue pages from Wikipedia categories via the API
    ALL_EW_CATEGORIES = [
        "Electronic_countermeasures",
        "Electronic_warfare",
        "Military_electronics_of_the_United_States",
        "Radar",
        "Military_radars",
        "Signals_intelligence",
        "Anti-aircraft_warfare",
        "Military_communications",
    ]
    wiki_cats_arg = getattr(args, "wiki_categories", None) or ""
    if wiki_cats_arg.strip().lower() == "all":
        categories = ALL_EW_CATEGORIES
    elif wiki_cats_arg.strip():
        categories = [c.strip() for c in wiki_cats_arg.split(",") if c.strip()]
    else:
        categories = ["Electronic_countermeasures"]

    total_enqueued = 0
    for cat in categories:
        n_cat = 0
        cmcontinue = ""
        while True:
            api_url = (
                f"https://en.wikipedia.org/w/api.php?action=query&list=categorymembers"
                f"&cmtitle=Category:{urllib.parse.quote(cat)}"
                f"&cmlimit=500&cmtype=page&format=json"
            )
            if cmcontinue:
                api_url += f"&cmcontinue={urllib.parse.quote(cmcontinue)}"
            try:
                req = urllib.request.Request(api_url, headers={
                    "User-Agent": s.user_agent, "Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = _json.loads(resp.read().decode("utf-8"))
                members = data.get("query", {}).get("categorymembers", [])
                for m in members:
                    if m["ns"] != 0:
                        continue
                    title = m["title"].replace(" ", "_")
                    page_url = f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title)}"
                    n_cat += eng.store.enqueue(page_url, "en.wikipedia.org", kind="product")
                cmcontinue = data.get("continue", {}).get("cmcontinue", "")
                if not cmcontinue:
                    break
                _time.sleep(1)  # polite delay between paginated requests
            except Exception as e:
                log.warning(f"Wikipedia API fetch failed for {cat}: {e}")
                break
        summary[f"cat_{cat}"] = n_cat
        total_enqueued += n_cat
        _time.sleep(2)  # polite delay between categories
    summary["categories_total_enqueued"] = total_enqueued

    print(json.dumps({
        "summary": summary,
        "status": eng.status(),
        "next": "python -m scan crawl --categories ew-assets",
    }, indent=2))
    eng.close()


def cmd_export(args, s: Settings):
    eng = Engine(s)
    eng.export()
    eng.close()


def cmd_status(args, s: Settings):
    eng = Engine(s)
    print(json.dumps(eng.status(), indent=2))
    eng.close()


def cmd_import_military(args, s: Settings):
    """Ingest the operator-scraped militaryfactory.com by-country pages
    (scanner/data/military/*.html) into the scan store. Rows are merged by the
    stable aircraft_id so the same aircraft listed under several countries
    accumulates its operators; clearly civilian-only types are dropped."""
    eng = Engine(s)
    src_dir = Path(args.military_dir)
    if not src_dir.is_absolute():
        src_dir = s.root / src_dir
    if not src_dir.exists():
        print(f"military data dir not found: {src_dir}")
        eng.close()
        return
    merged: dict[int, dict] = {}
    for p in sorted(src_dir.glob("*.html")):
        country = p.stem.replace("militaryfactory", "").upper()
        rows = parse_militaryfactory_country(
            p.read_text(encoding="utf-8", errors="replace"), country)
        for r in rows:
            aid = r["aircraft_id"]
            if aid in merged:
                merged[aid]["operators"] |= r["operators"]
            else:
                merged[aid] = r
    entries = build_entries(list(merged.values()))
    ops = {"inserted": 0, "merged": 0}
    for e in entries:
        ops[eng.store.upsert_entry(e, e.sources[0].url if e.sources else "")] += 1
    # Enqueue the per-aircraft detail pages so the crawler can enrich the
    # entries with full specs. Each detail URL is unique per aircraft_id.
    enqueued = 0
    for u, cat in {e.sources[0].url: e.category for e in entries if e.sources}.items():
        enqueued += eng.store.enqueue(u, "www.militaryfactory.com", category=cat, kind="product")
    print(json.dumps({
        "files_parsed": len(list(src_dir.glob("*.html"))),
        "unique_aircraft": len(merged),
        "entries_upserted": len(entries),
        "inserted": ops["inserted"],
        "merged": ops["merged"],
        "dropped_civilian": len(merged) - len(entries),
        "detail_urls_enqueued": enqueued,
        "next": "python -m scan crawl --categories aircraft,uavs --delay 1",
    }, indent=2))
    eng.close()


def cmd_re_enrich_military(args, s: Settings):
    """Re-parse the cached militaryfactory detail HTML (already fetched) with
    the latest parser and re-upsert, so enriched specs (Mission Roles, etc.)
    fold into the existing entries. No network needed."""
    eng = Engine(s)
    rows = eng.store._conn.execute(
        "SELECT url, html FROM raw_html WHERE url LIKE "
        "'https://www.militaryfactory.com/aircraft/detail.php?aircraft_id=%'").fetchall()
    ops = {"inserted": 0, "merged": 0, "skipped": 0}
    for row in rows:
        e = parse_militaryfactory_detail(row["url"], row["html"])
        if e is None:
            ops["skipped"] += 1
            continue
        ops[eng.store.upsert_entry(e, row["url"])] += 1
    print(json.dumps({
        "cached_detail_pages": len(rows),
        "re_upserted": ops["inserted"] + ops["merged"],
        "inserted": ops["inserted"],
        "merged": ops["merged"],
        "skipped": ops["skipped"],
        "next": "python -m scan export && python -m scan build-web && python -m scan curate",
    }, indent=2))
    eng.close()


def cmd_import_janes(args, s: Settings):
    rows = janes_import_csv(args.csv)
    print(f"imported {len(rows)} Janes rows (research-desk licensed data); "
          f"review manually before merge.")
    for r in rows[:5]:
        print("  -", r.get("designation", ""), "|", r.get("category", ""))


def cmd_curate(args, s: Settings):
    eng = Engine(s)
    rules = CurationRules(
        min_score=args.min_score,
        max_per_category=args.max_per_category,
        max_total=args.max_total,
    )
    report = curate(eng.store.all_entries(), rules)
    write_outputs(report, s.root / "data")
    print(json.dumps({
        "raw_pool_size": report["raw_pool_size"],
        "after_filters_size": report["after_filters_size"],
        "picklist_size": report["picklist_size"],
        "excluded_counts": report["excluded_counts"],
        "rules": report["rules"],
    }, indent=2))
    print(f"wrote data/picklist.json + data/picklist.csv (schema {report['picklist_schema_version']})")
    eng.close()


def cmd_build_web(args, s: Settings):
    eng = Engine(s)
    # Default: the A-SAN site root (repo root, sibling of index.html) so
    # https://a-san.alieninc.tech/category.html serves the catalog. Override
    # with --out to stage elsewhere.
    default_out = s.root.parent
    out = Path(args.out) if args.out else default_out
    if not out.is_absolute():
        out = s.root.parent / out
    eng.export_web(out)
    eng.close()
    # Refresh Panteon's MIL-contacts airframe index from the fresh export.
    try:
        from .aircraft_index import build_index, DEFAULT_OUT
        idx_out = Path(os.environ.get("PANTEON_AIRCRAFT_INDEX", str(DEFAULT_OUT)))
        idx = build_index(Path(out) / "data" / "aircraft.json")
        idx_out.parent.mkdir(parents=True, exist_ok=True)
        idx_out.write_text(json.dumps(idx, ensure_ascii=False,
                                      separators=(",", ":")), encoding="utf-8")
        print(f"aircraft index: {idx['count']} type keys -> {idx_out}")
    except Exception as exc:
        print(f"aircraft index refresh skipped: {exc}")
    print(json.dumps({
        "out": str(out),
        "note": "serve with:  python3 -m http.server 8000 --directory %s" % out,
        "deployed": "https://a-san.alieninc.tech/category.html",
    }, indent=2))


def cmd_build_play(args, s: Settings):
    """Resolve one verified Wikipedia lead image per curated flagship entry
    and write the identification-game dataset (data/play.json)."""
    report = build_play_dataset(s, force_refresh=args.requery)
    print(json.dumps(report, indent=2))


def cmd_patent_feed(args, s: Settings):
    """Enqueue patent publication numbers as Google-Patents reader URLs.

    Either `--patents-file list.txt` (one pub number per line) or, with no file,
    a live API query (USPTO Open Data Portal bearer token, or Espacenet OPS
    key/secret — whichever is configured in the env). Each resulting
    publication number becomes a `patents.google.com/patent/<pub>` URL and is
    enqueued under `--category`. Then run `python -m scan crawl`.
    """
    eng = Engine(s)
    cat = args.category
    category_display = _categories(argparse.Namespace(categories=cat))[0] if cat else "Uncategorized"
    try:
        if args.patents_file:
            count = feed_from_file(eng, args.patents_file, category_display, limit=args.limit)
        else:
            count = feed_patents(eng, args.query, category_display,
                                 limit=args.limit, per_page=args.per_page,
                                 max_pages=args.max_pages)
    finally:
        eng.close()
    print(json.dumps({
        "enqueued": count,
        "category": category_display,
        "query": args.query,
        "next": "python -m scan crawl",
    }, indent=2))


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m scan", description="A-SAN deep scanner")
    sub = p.add_subparsers(dest="cmd", required=True)

    for name in ("run", "crawl", "discover", "seed", "export", "status"):
        sp = sub.add_parser(name)
        _add_common(sp)
    cp = sub.add_parser("curate")
    cp.add_argument("--min-score", type=float, default=40.0)
    cp.add_argument("--max-per-category", type=int, default=15)
    cp.add_argument("--max-total", type=int, default=100)
    _add_common(cp)
    wp = sub.add_parser("build-web")
    wp.add_argument("--out", default=None, help="output dir (default <scanner>/web)")
    _add_common(wp)
    bp = sub.add_parser("build-play",
                        help="build data/play.json: resolve a verified Wikipedia "
                             "lead image for every curated flagship picklist entry")
    bp.add_argument("--requery", action="store_true",
                    help="ignore the resolution cache and re-query Wikipedia")
    _add_common(bp)
    fp = sub.add_parser("patent-feed", help="enqueue patent pub-numbers as google-patents URLs")
    fp.add_argument("--query", default="guided missile defense", help="search text for the API feed")
    fp.add_argument("--category", default="Rocket and missile weapons", help="category to assign (key or display name)")
    fp.add_argument("--patents-file", default=None, help="txt list of pub numbers (one per line) instead of an API query")
    fp.add_argument("--per-page", type=int, default=50, help="results per API page")
    fp.add_argument("--max-pages", type=int, default=20, help="max API pages to pull")
    _add_common(fp)
    sp = sub.add_parser("import-janes")
    sp.add_argument("csv")
    _add_common(sp)
    rp = sub.add_parser("import-military",
                        help="ingest operator-scraped militaryfactory.com by-country pages")
    rp.add_argument("--military-dir", default="data/military",
                    help="dir containing militaryfactory<COUNTRY>.html pages")
    _add_common(rp)
    rep = sub.add_parser("re-enrich-military",
                         help="re-parse cached militaryfactory detail HTML and re-upsert")
    _add_common(rep)
    dsp = sub.add_parser("discover-sources",
                         help="enumerate listing pages of designation-systems.net, "
                              "missilethreat.csis.org, modernfirearms.net and enqueue "
                              "their detail URLs")
    _add_common(dsp)
    dsp = sub.add_parser("discover-ua",
                         help="enumerate war-sanctions.gur.gov.ua UAV catalog and "
                              "en.defence-ua.com weapon_and_tech articles, enqueue "
                              "their detail URLs")
    dsp.add_argument("--max-ws-pages", type=int, default=40,
                     help="max war-sanctions /en/uav listing pages to walk")
    dsp.add_argument("--de-months", type=int, default=12,
                     help="how many most-recent defence-ua monthly sitemaps to pull")
    _add_common(dsp)
    msp = sub.add_parser("discover-more",
                         help="enumerate baykartech.com, army-guide.com, "
                              "globalsecurity.org and hisutton.com; enqueue their "
                              "detail URLs")
    msp.add_argument("--ag-pages", type=int, default=70,
                     help="max army-guide products.php listing pages to walk")
    msp.add_argument("--gs-max-hubs", type=int, default=60,
                     help="max globalsecurity hub/index pages to fetch during BFS")
    _add_common(msp)
    sfp = sub.add_parser("discover-seaforces",
                         help="enumerate seaforces.org wpnsys/usnships/marint "
                              "sections from its flat sitemap.txt and enqueue them")
    _add_common(sfp)
    rcp = sub.add_parser("recategorize",
                         help="quality pass: fill Uncategorized entries, repair "
                              "weaponsystems.net platform misclassification, "
                              "report near-duplicates")
    _add_common(rcp)
    dkp = sub.add_parser("dedupe-keys",
                         help="rebuild normalized designation keys and merge "
                              "punctuation-variant duplicates (run when no crawl "
                              "is writing)")
    _add_common(dkp)
    rew = sub.add_parser("re-enrich-weaponsystems",
                         help="re-parse weaponsystems.net entries from cached "
                              "HTML with current parser (handles site redesign)")
    _add_common(rew)
    wp = sub.add_parser("import-wikipedia",
                        help="parse Wikipedia 'List of military electronics' pages "
                             "(CC BY-SA 4.0) + enqueue EW system pages from "
                             "Wikipedia categories")
    wp.add_argument("--wiki-categories",
                    help="comma-separated Wikipedia category names to enqueue, "
                         "or 'all' for the full EW-relevant set "
                         "(default: Electronic_countermeasures only)")
    _add_common(wp)

    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO if not args.quiet else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(message)s")
    s = _settings(args)
    if args.cmd == "seed":
        cmd_seed(args, s)
    elif args.cmd == "discover":
        cmd_discover(args, s)
    elif args.cmd == "crawl":
        cmd_crawl(args, s)
    elif args.cmd == "run":
        cmd_run(args, s)
    elif args.cmd == "export":
        cmd_export(args, s)
    elif args.cmd == "status":
        cmd_status(args, s)
    elif args.cmd == "import-janes":
        cmd_import_janes(args, s)
    elif args.cmd == "import-military":
        cmd_import_military(args, s)
    elif args.cmd == "re-enrich-military":
        cmd_re_enrich_military(args, s)
    elif args.cmd == "discover-sources":
        cmd_discover_sources(args, s)
    elif args.cmd == "discover-ua":
        cmd_discover_ua(args, s)
    elif args.cmd == "discover-more":
        cmd_discover_more(args, s)
    elif args.cmd == "discover-seaforces":
        cmd_discover_seaforces(args, s)
    elif args.cmd == "recategorize":
        cmd_recategorize(args, s)
    elif args.cmd == "dedupe-keys":
        cmd_dedupe_keys(args, s)
    elif args.cmd == "re-enrich-weaponsystems":
        cmd_reenrich_weaponsystems(args, s)
    elif args.cmd == "import-wikipedia":
        cmd_import_wikipedia(args, s)
    elif args.cmd == "curate":
        cmd_curate(args, s)
    elif args.cmd == "build-web":
        cmd_build_web(args, s)
    elif args.cmd == "build-play":
        cmd_build_play(args, s)
    elif args.cmd == "patent-feed":
        cmd_patent_feed(args, s)


def _add_common(sp):
    sp.add_argument("--categories", help="comma-separated keys or names, e.g. aircraft,uavs")
    sp.add_argument("--domains", help="restrict crawl to these domains (comma-separated)")
    sp.add_argument("--limit", type=int, default=None, help="cap product pages this run")
    sp.add_argument("--delay", type=float, default=1.5, help="min seconds between requests/host")
    sp.add_argument("--workers", type=int, default=1, help="parallel hosts (politeness kept per host)")
    sp.add_argument("--retries", type=int, default=3)
    sp.add_argument("--refresh", action="store_true", help="ignore the raw-HTML cache")
    sp.add_argument("--no-robots", action="store_true",
                    help="FORBIDDEN unless site ops whitelisted the scanner UA (see POLICY.md)")
    sp.add_argument("--catalog", help="output catalog path")
    sp.add_argument("--db", help="scan store path")
    sp.add_argument("--seeds", help="seeds json path")
    sp.add_argument("-q", "--quiet", action="store_true")


if __name__ == "__main__":
    sys.exit(main())
