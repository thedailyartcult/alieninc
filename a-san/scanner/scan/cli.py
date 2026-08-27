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
import html as html_lib
import json
import logging
import os
import re
import sys
import urllib.parse
from collections import defaultdict
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
from .parsers_navweaps import parse_navweaps_missile_links
from .parsers_rheinmetall import RHEINMETALL_PRODUCT_URLS
from .parsers_gdls import GDLS_PRODUCT_URLS
from .parsers_qinetiq import QINETIQ_PRODUCT_URLS
from .parsers_amgeneral import AMGENERAL_VEHICLE_PATHS
from .parsers_navalencyclopedia import is_naval_encyclopedia_ship_url
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
            if ".." in href or href.startswith(("mailto:", "javascript:")):
                continue
            if href.startswith(("http://", "https://")):
                if "globalsecurity.org" not in href or "/military/systems/" not in href:
                    continue
                child = href
                path = "/" + child.split("globalsecurity.org/", 1)[1]
            elif href.startswith("/"):
                child = f"https://www.globalsecurity.org{href}"
                path = href
            else:
                # base is already an absolute URL; never re-prefix the host.
                child = f"{base}/{href}"
                path = "/" + child.split("globalsecurity.org/", 1)[1]
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


def cmd_discover_round4(args, s: Settings):
    """Enumerate the four round-4 sources (added 2026-08-25):
    www.navweaps.com (WM* naval-missile index pages only — guns/torpedoes
    skipped, no matching category), www.rheinmetall.com and www.gdls.com
    (curated product URLs), oshkoshdefense.com (/vehicles/ tree from its
    page-sitemap). robots.txt-gated, polite, cached. Run once, then crawl."""
    eng = Engine(s)
    eng.seed_from_catalog()
    summary: dict[str, int] = {}

    # --- navweaps.com: WM*_Main.php missile indexes -> WMxx_<name>.php ---
    # Some indexes (notably Russia/USSR) print whole data tables inline; those
    # rows are parsed + admitted here at discovery time. Detail pages are
    # enqueued for the crawl.
    from .parsers_navweaps import parse_navweaps_main_listing
    n_nw = 0
    res = eng._fetcher("www.navweaps.com").fetch(
        "https://www.navweaps.com/Weapons/index_weapons.php",
        store=eng.store, use_cache=True)
    if res.status == 200 and res.html:
        main_pages = sorted(set(re.findall(
            r'href="(WM[A-Z]{2,4}_Main\.php)"', res.html)))[:args.nw_max_mains]
        for mp in main_pages:
            murl = f"https://www.navweaps.com/Weapons/{mp}"
            res2 = eng._fetcher("www.navweaps.com").fetch(
                murl, store=eng.store, use_cache=True)
            if res2.status != 200 or not res2.html:
                continue
            for entry in parse_navweaps_main_listing(murl, res2.html):
                if eng._admit(entry, murl) != "rejected":
                    n_nw += 1
            for durl in parse_navweaps_missile_links(res2.html):
                n_nw += eng.store.enqueue(durl, "www.navweaps.com",
                                          kind="product")
    summary["www.navweaps.com"] = n_nw

    # --- rheinmetall.com: curated uncrewed-systems product URLs ---
    n_rm = 0
    for url, cat in RHEINMETALL_PRODUCT_URLS:
        n_rm += eng.store.enqueue(url, "www.rheinmetall.com",
                                  category=cat, kind="product")
    summary["www.rheinmetall.com"] = n_rm

    # --- gdls.com: curated product URLs (TRX/MUTT -> UGVs, rest armored) ---
    n_gd = 0
    for url, cat in GDLS_PRODUCT_URLS:
        n_gd += eng.store.enqueue(url, "www.gdls.com", category=cat,
                                  kind="product")
    summary["www.gdls.com"] = n_gd

    # --- oshkoshdefense.com: /vehicles/ pages from page-sitemap.xml ---
    n_os = 0
    from .parsers_oshkosh import categorize_oshkosh_url
    res = eng._fetcher("oshkoshdefense.com").fetch(
        "https://oshkoshdefense.com/page-sitemap.xml",
        store=eng.store, use_cache=True)
    if res.status == 200 and res.html:
        for m in re.finditer(r"<loc>(https?://oshkoshdefense\.com[^<]+)</loc>",
                             res.html):
            u = m.group(1)
            cat = categorize_oshkosh_url(u)
            if cat:
                n_os += eng.store.enqueue(u, "oshkoshdefense.com",
                                          category=cat, kind="product")
    summary["oshkoshdefense.com"] = n_os

    print(json.dumps({
        "enqueued_by_source": summary,
        "total_enqueued": sum(summary.values()),
        "status": eng.status(),
        "next": ("python -m scan crawl --domains www.navweaps.com "
                 "(navweaps self-classifies at parse time; rheinmetall/gdls/"
                 "oshkosh are pre-categorized)"),
    }, indent=2))
    eng.close()


def cmd_discover_round5(args, s: Settings):
    """Enumerate the round-5 sources (added 2026-08-25):
    www.naval-encyclopedia.com (warship articles from its flat sitemap,
    ww1/ww2/cold-war/industrial-era/modern sections only) and www.qinetiq.com
    (curated robotic-product URLs -> UGVs). tanks-encyclopedia.com was
    rejected this round (Cloudflare WAF despite open robots). Run once,
    then crawl."""
    eng = Engine(s)
    eng.seed_from_catalog()
    summary: dict[str, int] = {}

    # --- naval-encyclopedia.com: flat sitemap -> era/country/<slug>.php ---
    n_ne = 0
    res = eng._fetcher("www.naval-encyclopedia.com").fetch(
        "https://www.naval-encyclopedia.com/sitemap.xml",
        store=eng.store, use_cache=True)
    if res.status == 200 and res.html:
        for m in re.finditer(r"<loc>([^<]+)</loc>", res.html):
            u = m.group(1).strip().replace("http://", "https://")
            if is_naval_encyclopedia_ship_url(u):
                cat = "Naval vessels"
                n_ne += eng.store.enqueue(u, "www.naval-encyclopedia.com",
                                          category=cat, kind="product")
    summary["www.naval-encyclopedia.com"] = n_ne

    # --- qinetiq.com: curated robotic-product URLs (UGVs) ---
    n_qq = 0
    for url, cat in QINETIQ_PRODUCT_URLS:
        n_qq += eng.store.enqueue(url, "www.qinetiq.com", category=cat,
                                  kind="product")
    summary["www.qinetiq.com"] = n_qq

    print(json.dumps({
        "enqueued_by_source": summary,
        "total_enqueued": sum(summary.values()),
        "status": eng.status(),
        "next": ("python -m scan crawl --domains www.naval-encyclopedia.com "
                 "(~2000 pages at 1.5s delay; both sources pre-categorized "
                 "and resumable)"),
    }, indent=2))
    eng.close()


def cmd_discover_round6(args, s: Settings):
    """Enumerate the round-6 sources (added 2026-08-25):
    elbitsystems.com (/land product tree from its sitemap.xml; the old
    'JS-rendered' verdict is obsolete — pages are server-rendered Drupal)
    and amgeneral.com (curated vehicle URLs from page-sitemap.xml).
    Both are © all-rights-reserved: fact-extraction with attribution.
    Run once, then crawl."""
    from .parsers_elbit import elbit_category_for
    eng = Engine(s)
    eng.seed_from_catalog()
    summary: dict[str, int] = {}

    # --- elbitsystems.com: sitemap -> /land/ leaf products ---
    n_el = 0
    res = eng._fetcher("elbitsystems.com").fetch(
        "https://www.elbitsystems.com/sitemap.xml",
        store=eng.store, use_cache=True)
    if res.status == 200 and res.html:
        for m in re.finditer(r"<loc>([^<]+)</loc>", res.html):
            u = m.group(1).strip().rstrip("/")
            if "/land/" not in u or u.count("/") < 4:
                continue
            cat = elbit_category_for(u)
            if not cat:
                continue
            n_el += eng.store.enqueue(u, "elbitsystems.com",
                                      category=cat, kind="product")
    summary["elbitsystems.com"] = n_el

    # --- amgeneral.com: curated vehicle URLs (Automotive vehicles) ---
    n_am = 0
    for path in AMGENERAL_VEHICLE_PATHS:
        n_am += eng.store.enqueue(
            f"https://www.amgeneral.com{path}", "www.amgeneral.com",
            category="Automotive vehicles", kind="product")
    summary["www.amgeneral.com"] = n_am

    print(json.dumps({
        "enqueued_by_source": summary,
        "total_enqueued": sum(summary.values()),
        "status": eng.status(),
        "next": ("python -m scan crawl --domains elbitsystems.com "
                 "(~100 product pages at default delay) then crawl "
                 "--domains www.amgeneral.com (~14 pages); both "
                 "pre-categorized and resumable"),
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


def cmd_reenrich_all(args, s: Settings):
    """Offline enrichment pass: re-parse cached detail HTML with the improved
    parsers and merge richer specs into existing entries. NO network — reads
    only raw_html already in the store.

    Sources whose legacy parsers stuffed prose paragraphs into 'specs'
    (globalsecurity, hisutton, seaforces) get spec replacement vetted per
    entry: junk prose is purged, real table specs are never downgraded."""
    import json as _json

    eng = Engine(s)

    def parse_gs(u, h):
        from .parsers_globalsecurity import parse_globalsecurity
        return parse_globalsecurity(u, h)

    def parse_hs(u, h):
        from .parsers_hisutton import parse_hisutton_article
        return parse_hisutton_article(u, h)

    def parse_sf(u, h):
        from .parsers_seaforces import parse_seaforces
        return parse_seaforces(u, h)

    def parse_mf(u, h):
        from .parsers_modernfirearms import parse_modernfirearms
        return parse_modernfirearms(u, h)

    def parse_f(u, h):
        from .parsers_fas import parse_fas
        return parse_fas(u, h)

    def parse_wiki(u, h):
        from .parsers_wikipedia import parse_wikipedia_infobox
        return parse_wikipedia_infobox(u, h)

    # (url LIKE pattern, parser, detail-only filter or None, prefer_specs)
    DISPATCH = [
        ("https://modernfirearms.net/en/%", parse_mf, None, False),
        ("https://man.fas.org/dod-101/sys/%", parse_f, None, False),
        ("https://www.globalsecurity.org/military/%", parse_gs, None, True),
        ("https://www.hisutton.com/%", parse_hs, None, True),
        ("https://www.seaforces.org/%", parse_sf, None, True),
        ("https://en.wikipedia.org/wiki/%", parse_wiki, None, False),
    ]
    LISTING = re.compile(
        r"/(category|tag|index|intro|Covert_Shores_Articles|List_|Portal:|"
        r"Category:|page/\d)" , re.I)
    MF_SEED_SLUGS = {u.rstrip("/").rsplit("/", 1)[-1]
                     for u in MODERNFIREARMS_SEED_URLS.values()}
    FAS_HUBS = {"index.htm", "intro.htm", "direct.htm", "refs.htm"}

    ops = {}
    per_source = {}
    rows = eng.store._conn.execute(
        "SELECT url, html FROM raw_html WHERE "
        + " OR ".join("url LIKE ?" for pat, _, _, _ in DISPATCH)
        + " ORDER BY url",
        [pat for pat, _, _, _ in DISPATCH]).fetchall()
    for row in rows:
        url, html = row["url"], row["html"]
        if not html or len(html) < 8000:
            continue
        hit = next(((p, fn, filt, pref) for p, fn, filt, pref in DISPATCH
                    if url.startswith(p.replace("%", ""))), None)
        if not hit:
            continue
        pat, fn, filt, prefer = hit
        path_last = url.rstrip("/").rsplit("/", 1)[-1].lower()
        segs = [x for x in url.replace("https://", "").split("/") if x]
        # detail-page guards
        if "modernfirearms.net" in url and (path_last in MF_SEED_SLUGS or len(segs) < 5):
            continue
        if "fas.org" in url and (not path_last.endswith(".htm")
                                 or path_last in FAS_HUBS or len(segs) < 5):
            continue
        if "wikipedia.org" in url and ("#" in url or ":" in url.rsplit("/", 1)[-1]):
            continue
        if LISTING.search(url):
            continue
        try:
            e = fn(url, html)
        except Exception as ex:
            logging.warning("reenrich parse failed %s: %s", url, ex)
            continue
        if e is None:
            continue
        src_key = pat.split("//")[1].split("/")[0].replace("www.", "")
        stat = per_source.setdefault(src_key, {"parsed": 0, "with_specs": 0})
        stat["parsed"] += 1
        if e.specs:
            stat["with_specs"] += 1

        force = prefer
        if prefer and e.specs:
            old = eng.store._conn.execute(
                "SELECT data FROM entries WHERE fingerprint=? OR designation_key=?",
                (e.fingerprint(), e.designation_key())).fetchone()
            if old:
                od = _json.loads(old["data"])
                ospecs = od.get("specs", [])
                if ospecs:
                    avg_len = sum(len(x) for x in ospecs) / len(ospecs)
                    prose_junk = avg_len > 90
                    force = prose_junk or len(e.specs) >= len(ospecs)
                else:
                    force = True
        op = eng.store.upsert_entry(e, url, prefer_specs=force)
        ops[op] = ops.get(op, 0) + 1

    print(_json.dumps({
        "cached_pages_scanned": len(rows),
        "results": ops,
        "per_source": {k: v for k, v in sorted(per_source.items())},
        "next": "python -m scan export && python -m scan build-web && arsenal_sync",
    }, indent=2))
    eng.close()


def cmd_clean_specs(args, s: Settings):
    """Catalog hygiene sweep over every entry (offline):
      1. keyless continuation fragments merge into the previous spec (' / ')
      2. verbose prose values trimmed at a sentence boundary (~170 chars)
      3. nav/boilerplate specs (HOME:, links, ©) dropped
      4. placeholder fallback descriptions replaced with '' when the entry
         has real specs (better empty than fake text)
    Deterministic and idempotent."""
    import json as _json

    eng = Engine(s)
    rows = eng.store._conn.execute(
        "SELECT fingerprint, designation, data FROM entries").fetchall()
    changed = {"fragment_merged": 0, "trimmed": 0, "dropped_nav": 0,
               "desc_fixed": 0}
    PLACEHOLDER_RES = [
        re.compile(r"^Modern Firearms encyclopedia entry:", re.I),
        re.compile(r"^FAS equipment profile:", re.I),
        re.compile(r" — Seaforces profile\.$"),
        re.compile(r"^Public technical profile of .+ from Weaponsystems\.net\.$", re.I),
        re.compile(r"^Army Recognition product page", re.I),
    ]
    NAV_RE = re.compile(r"\b(HOME|http://|https://|www\.|©|all rights reserved)\b",
                        re.I)
    updates = []
    for fp, desig, data in rows:
        d = _json.loads(data)
        specs = d.get("specs", [])
        out = []
        n_frag = n_trim = n_drop = 0
        for sp in specs:
            if NAV_RE.search(sp[:40]):
                n_drop += 1
                continue
            if ":" not in sp:
                if out and len(sp) <= 120 and len(out[-1]) + len(sp) < 240:
                    out[-1] = f"{out[-1]} / {sp}"
                    n_frag += 1
                    continue
                # keyless leftovers: drop sentence-like prose outright; keep
                # terse value-like fragments ('4 x 5-inch guns') under 60 chars
                words = sp.split()
                stopish = sum(1 for w in words
                              if w.lower().strip(",.[]()") in (
                                  "the", "a", "an", "and", "of", "to", "in",
                                  "is", "was", "are", "for", "with", "that",
                                  "it", "has", "have", "on", "by", "from", "as"))
                if len(words) >= 8 and stopish >= 3:
                    n_drop += 1
                elif len(sp) <= 60 and stopish < 3:
                    out.append(sp)
                else:
                    n_drop += 1
                continue
            if len(sp) > 170:
                head = sp[:170]
                cut = -1
                for sep in (". ", "; "):
                    i = head.rfind(sep)
                    if i > 60:
                        cut = i + 1
                        break
                sp2 = (head[:cut].rstrip() if cut > 0
                       else head[:head.rfind(" ")].rstrip(" ,;:") if head.rfind(" ") > 60
                       else head.rstrip(" ,;:"))
                if sp2 != sp:
                    n_trim += 1
                sp = sp2
            out.append(sp)
        desc = d.get("description", "")
        if desc and any(pr.search(desc) for pr in PLACEHOLDER_RES) \
                and not desc.startswith(desig):
            d["description"] = ""
            changed["desc_fixed"] += 1
        if (n_frag or n_trim or n_drop) or (len(out) != len(specs)) \
                or d["description"] != desc:
            d["specs"] = out
            changed["fragment_merged"] += n_frag
            changed["trimmed"] += n_trim
            changed["dropped_nav"] += n_drop
            updates.append((fp, d))
    for fp, d in updates:
        eng.store._conn.execute(
            "UPDATE entries SET data=? WHERE fingerprint=?",
            (_json.dumps(d, ensure_ascii=False), fp))
    eng.store._conn.commit()
    print(_json.dumps({"entries_scanned": len(rows), "entries_updated": len(updates),
                       "changes": changed}, indent=2))
    eng.close()


def _known_country_set() -> set[str]:
    return {
        "united states", "united kingdom", "russia", "soviet union", "china",
        "france", "germany", "italy", "spain", "sweden", "israel", "india",
        "japan", "south korea", "north korea", "turkey", "türkiye", "ukraine",
        "poland", "czech republic", "slovakia", "austria", "switzerland",
        "netherlands", "belgium", "norway", "denmark", "finland", "greece",
        "portugal", "romania", "bulgaria", "hungary", "serbia", "croatia",
        "brazil", "argentina", "chile", "canada", "mexico", "australia",
        "new zealand", "south africa", "egypt", "iran", "iraq", "saudi arabia",
        "uae", "qatar", "pakistan", "bangladesh", "indonesia", "malaysia",
        "singapore", "thailand", "vietnam", "taiwan", "philippines", "myanmar",
        "belarus", "kazakhstan", "algeria", "morocco", "nigeria", "ethiopia",
        "kenya", "colombia", "peru", "venezuela", "ecuador", "ireland",
        "lithuania", "latvia", "estonia", "slovenia", "yugoslavia",
    }


def cmd_backfill_country(args, s: Settings):
    """Fill missing country fields in five escalating tiers (offline):

      T1 own-specs      'Origin:'/'Country of origin:'/'Country users:' already
                        in the entry's spec list
      T2 html-mining    cached Wikipedia infoboxes (Origin / Used by / Users)
      T3 cross-source   strict designation token match against entries that
                        have a country (>=2 shared tokens, >=70% overlap,
                        unique agreeing country)
      T4 fas-heuristic  man.fas.org/dod-101 documents US DoD systems; assign
                        'United States' unless foreign evidence present
      T5 prose-hisutton exactly one known country named in the first 500 chars

    Every fill records provenance in data['country_source']. Idempotent:
    entries that already have a country are never touched."""
    import json as _json

    eng = Engine(s)
    KNOWN = _known_country_set()
    from .config import COUNTRIES as CANON_SET, COUNTRY_FIXUPS
    rows = eng.store._conn.execute(
        "SELECT fingerprint, designation, data FROM entries").fetchall()
    entries = {}
    for r in rows:
        entries[r["fingerprint"]] = (r["designation"], _json.loads(r["data"]))

    def save(fp, d, source):
        d["country_source"] = source
        eng.store._conn.execute(
            "UPDATE entries SET data=? WHERE fingerprint=?",
            (_json.dumps(d, ensure_ascii=False), fp))

    stats = {"T0_normalized": 0, "T0_cleared": 0,
             "T1_spec": 0, "T2_infobox": 0, "T3_cross": 0, "T4_fas": 0,
             "T5_prose": 0}
    conflicts_t3 = 0

    # ---- T0: normalize / clear existing country values ----
    def canon_part(p):
        p2 = re.sub(r"\(.*?\)", "", p).strip(" .;:")
        low = p2.lower().rstrip(".")
        if low in COUNTRY_FIXUPS:
            return COUNTRY_FIXUPS[low]
        if low in CANON_SET:
            return {"usa": "United States", "us": "United States",
                    "uk": "United Kingdom", "ussr": "Soviet Union",
                    "türkiye": "Turkey"}.get(low, p2.title())
        return None

    for fp, (desig, d) in list(entries.items()):
        c = (d.get("country") or "").strip()
        if not c:
            continue
        parts = [p.strip() for p in re.split(r",| and ", c) if p.strip()]
        canon = []
        bad = False
        for p in parts:
            cp = canon_part(p)
            if cp:
                if cp not in canon:
                    canon.append(cp)
            else:
                bad = True
        if not canon:
            # nothing salvageable — clear so later tiers can refill properly
            d["country"] = ""
            stats["T0_cleared"] += 1
            save(fp, d, "T0_cleared-invalid")
        elif bad or len(canon) != len(parts) or \
                any(canon[i] != parts[i] for i in range(min(len(canon), len(parts)))):
            d["country"] = ", ".join(canon)
            stats["T0_normalized"] += 1
            save(fp, d, "T0_normalized")

    # rebuild the working copy after T0 mutations
    for fp in list(entries.keys()):
        row = eng.store._conn.execute(
            "SELECT designation, data FROM entries WHERE fingerprint=?",
            (fp,)).fetchone()
        entries[fp] = (row["designation"], _json.loads(row["data"]))

    # ---- T1: own specs ----
    SPEC_LABELS = ("origin:", "country of origin:", "country users:",
                   "operator country:", "country:")
    for fp, (desig, d) in list(entries.items()):
        if (d.get("country") or "").strip():
            continue
        for sp in d.get("specs", []):
            sl = sp.lower()
            for lab in SPEC_LABELS:
                if not sl.startswith(lab):
                    continue
                val = sp[len(lab):].strip().strip(".").strip()
                # strip trailing commentary and annotations
                val = re.split(r";|\bpotential\b|\baccording\b", val, 1)[0]
                parts = [p.strip() for p in re.split(r",| and ", val) if p.strip()]
                canon = [canon_part(p) for p in parts]
                canon = [c for c in canon if c]
                if not canon or len(canon) != len(parts) or \
                        len(", ".join(canon)) > 120 or \
                        re.match(r"^(various|none|unknown|see |multiple)",
                                 val, re.I):
                    continue
                d["country"] = ", ".join(dict.fromkeys(canon))
                stats["T1_spec"] += 1
                save(fp, d, f"T1_spec ({lab.rstrip(':')})")
                break
            if (d.get("country") or "").strip():
                break

    # ---- T2: cached Wikipedia infobox mining ----
    INFOLABEL = re.compile(r"^\s*(origin(?:\s+country)?|used?d?\s+by(?:\s+\w+)?|"
                           r"users|primary users|operators?)\s*:?\s*$", re.I)
    for fp, (desig, d) in list(entries.items()):
        if (d.get("country") or "").strip():
            continue
        url = (d.get("sources") or [{}])[0].get("url", "")
        if "wikipedia.org" not in url:
            continue
        hrow = eng.store._conn.execute(
            "SELECT html FROM raw_html WHERE url=?", (url,)).fetchone()
        if not hrow or not hrow["html"]:
            continue
        m = re.search(r'<table[^>]*class="[^"]*infobox[^"]*"[^>]*>(.*?)</table>',
                      hrow["html"], re.S | re.I)
        if not m:
            continue
        val = ""
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", m.group(1), re.S | re.I):
            cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S | re.I)
            if len(cells) >= 2 and INFOLABEL.match(
                    re.sub(r"\s+", " ", re.sub(
                        r"<[^>]+>", "", re.sub(r"<style.*?</style>", "",
                                               cells[0], flags=re.S | re.I))).strip()):
                val = re.sub(r"\s+", " ", html_lib.unescape(re.sub(
                    r"<[^>]+>", " ", re.sub(r"<style.*?</style>", "",
                                            cells[1], flags=re.S | re.I)))).strip(" ,;")
                break
        if not val or len(val) > 250:
            continue
        # keep only recognised nation names appearing in the cell text
        low = f" {val.lower()} "
        nations = []
        for k in sorted(KNOWN, key=len, reverse=True):
            if k in low and not any(k in n.lower() for n in nations):
                nations.append(k.title().replace("Of ", "of "))
        if nations:
            d["country"] = ", ".join(nations)[:120]
            stats["T2_infobox"] += 1
            save(fp, d, "T2_wiki-infobox")

    # ---- T3: strict cross-source token match ----
    def toks(s):
        return {t for t in re.findall(r"[a-z0-9]{2,}", s.lower())
                if not t.isdigit() and len(t) >= 3
                and t not in ("the", "and", "for")}

    have_index = defaultdict(set)   # token -> {(country, designation)}
    for fp, (desig, d) in entries.items():
        c = (d.get("country") or "").strip()
        if not c:
            continue
        for t in toks(desig):
            have_index[t].add((c, desig))
    for fp, (desig, d) in list(entries.items()):
        if (d.get("country") or "").strip():
            continue
        dt = toks(desig)
        if len(dt) < 2:
            continue
        cand = {}
        for t in dt:
            for c, hd in have_index.get(t, ()):
                cand.setdefault(hd, [set(), c])[0].add(t)
        agree = None
        for hd, (inter, c) in cand.items():
            ht = toks(hd)
            if len(inter) >= 2 and len(inter) >= 0.7 * min(len(dt), len(ht)):
                if agree is None:
                    agree = c
                elif agree != c:
                    agree = None
                    conflicts_t3 += 1
                    break
        if agree:
            d["country"] = agree[:120]
            stats["T3_cross"] += 1
            save(fp, d, "T3_cross-source")

    # ---- T4: FAS dod-101 US heuristic ----
    FOREIGN = re.compile(
        r"\b(soviet|russian|chinese|french|german|british|ukrainian|israeli|"
        r"indian|japanese|swedish|italian|iranian|north korean|european)\b", re.I)
    for fp, (desig, d) in list(entries.items()):
        if (d.get("country") or "").strip():
            continue
        url = (d.get("sources") or [{}])[0].get("url", "")
        if "man.fas.org/dod-101/sys/" not in url:
            continue
        txt = f"{desig} {d.get('description', '')} {' '.join(d.get('specs', [])[:6])}"
        if not FOREIGN.search(txt):
            d["country"] = "United States"
            stats["T4_fas"] += 1
            save(fp, d, "T4_fas-dod101-heuristic")

    # ---- T5: hisutton single-nation prose ----
    for fp, (desig, d) in list(entries.items()):
        if (d.get("country") or "").strip():
            continue
        url = (d.get("sources") or [{}])[0].get("url", "")
        if "hisutton.com" not in url:
            continue
        window = (d.get("description") or "")[:500].lower()
        found = {k.title() if k != "united states" else "United States"
                 for k in KNOWN if k in window}
        # exclude multi-national roundups
        if len(found) == 1:
            d["country"] = next(iter(found))
            stats["T5_prose"] += 1
            save(fp, d, "T5_hisutton-prose")

    eng.store._conn.commit()
    remaining = sum(1 for _, (x, d) in entries.items()
                    if not (d.get("country") or "").strip())
    print(_json.dumps({
        "entries_scanned": len(rows), "filled_by_tier": stats,
        "t3_ambiguous_skipped": conflicts_t3,
        "still_missing_country": remaining,
    }, indent=2))
    eng.close()


def cmd_discover_round7(args, s: Settings):
    """Enumerate globalmilitary.net (added 2026-08-26): an open military
    equipment database whose robots.txt explicitly welcomes crawlers with
    attribution. Equipment detail URLs come from sitemap-main.xml; every
    entry carries origin + operators + a structured spec table.
    Run once, then crawl --domains www.globalmilitary.net."""
    from .parsers_globalmilitary import GM_SITEMAP, gm_category_for, is_gm_detail
    eng = Engine(s)
    eng.seed_from_catalog()
    res = eng._fetcher("www.globalmilitary.net").fetch(
        GM_SITEMAP, store=eng.store, use_cache=True)
    if res.status != 200 or not res.html:
        print(json.dumps({"error": f"sitemap fetch failed ({res.status})"}))
        eng.close()
        return
    by_cat: dict[str, int] = {}
    n = 0
    for m in re.finditer(r"<loc>([^<]+)</loc>", res.html):
        u = m.group(1).strip()
        if not is_gm_detail(u):
            continue
        cat = gm_category_for(u)
        if not cat:
            continue
        n += eng.store.enqueue(u, "www.globalmilitary.net",
                               category=cat, kind="product")
        by_cat[cat] = by_cat.get(cat, 0) + 1
    print(json.dumps({
        "enqueued_total": n,
        "enqueued_by_category": by_cat,
        "next": ("python -m scan crawl --domains www.globalmilitary.net "
                 "(~2600 pages; robots welcomes us, default delay applies)"),
    }, indent=2))
    eng.close()


def cmd_discover_te(args, s: Settings):
    """Enumerate tanks-encyclopedia.com (added 2026-08-26): robots allows
    generic crawlers (Content-Signal use=reference); sitemaps are bot-blocked
    so discovery walks the four era index pages. Articles are pre-categorized
    as Armored vehicles and equipment."""
    from .parsers_tanksencyclopedia import TE_INDEX_URLS, parse_te_listing, is_te_article_url
    eng = Engine(s)
    eng.seed_from_catalog()
    fetcher = eng._fetcher("tanks-encyclopedia.com")
    seen: set[str] = set()
    n = 0
    # Level 1: era indexes -> article links + country hubs (/<era>/<country>/)
    for idx_url in TE_INDEX_URLS:
        res = fetcher.fetch(idx_url, store=eng.store, use_cache=True)
        if res.status != 200 or not res.html:
            continue
        for u in parse_te_listing(res.html):
            if u in seen or not is_te_article_url(u):
                continue
            seen.add(u)
            n += eng.store.enqueue(u, "tanks-encyclopedia.com",
                                   category="Armored vehicles and equipment",
                                   kind="product")
        for m in re.finditer(
                r'href="(https://tanks-encyclopedia\.com/'
                r'(?:modern|cold-war|coldwar|ww2|ww1|interwar)/'
                r'[a-z-]{3,22})/?"',
                res.html or "", re.I):
            hub = m.group(1).rstrip("/") + "/"
            if hub in seen:
                continue
            seen.add(hub)
            hres = fetcher.fetch(hub, store=eng.store, use_cache=True)
            if hres.status != 200 or not hres.html:
                continue
            for u in parse_te_listing(hres.html):
                if u in seen or not is_te_article_url(u):
                    continue
                seen.add(u)
                n += eng.store.enqueue(u, "tanks-encyclopedia.com",
                                       category="Armored vehicles and equipment",
                                       kind="product")
    print(json.dumps({
        "enqueued_total": n,
        "next": ("python -m scan crawl --domains tanks-encyclopedia.com "
                 "(default delay; robots permits with attribution)"),
    }, indent=2))
    eng.close()


def cmd_discover_helis(args, s: Settings):
    """Enumerate helis.com model pages (added 2026-08-26): walk the
    manufacturer matrix (/database/model/ -> 134 manufacturer pages ->
    /database/model/<id>/ detail pages). Robots allows; spec tables are
    structured. Pre-categorized as Aircraft."""
    from .parsers_helis import parse_helis_listing
    eng = Engine(s)
    eng.seed_from_catalog()
    fetcher = eng._fetcher("www.helis.com")
    seen: set[str] = set()
    n = 0
    r = fetcher.fetch("https://www.helis.com/database/model/",
                      store=eng.store, use_cache=True)
    hubs = sorted(set(re.findall(
        r'href="(/database/(?:model|manufacturer)/\d+/)"', r.html or "")))
    for hub in hubs:
        hub_url = "https://www.helis.com" + hub
        res = fetcher.fetch(hub_url, store=eng.store, use_cache=True)
        if res.status != 200 or not res.html:
            continue
        for u in parse_helis_listing(res.html):
            if u in seen:
                continue
            seen.add(u)
            n += eng.store.enqueue(u, "www.helis.com",
                                   category="Aircraft", kind="product")
    print(json.dumps({
        "hubs_walked": len(hubs),
        "enqueued_total": n,
        "next": "python -m scan crawl --domains www.helis.com",
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
    report = build_play_dataset(s, force_refresh=args.requery,
                                expand_to=args.expand)
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
    bp.add_argument("--expand", type=int, default=0, metavar="N",
                    help="top the pool up to N total items with extra catalog "
                         "entries resolved through the same Wikipedia pipeline")
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
    r4p = sub.add_parser("discover-round4",
                         help="enumerate the round-4 sources (navweaps.com WM* "
                              "missile pages, rheinmetall.com + gdls.com product "
                              "pages, oshkoshdefense.com /vehicles/ sitemap) and "
                              "enqueue their detail URLs")
    r4p.add_argument("--nw-max-mains", type=int, default=10,
                     help="max navweaps WM*_Main.php index pages to walk")
    _add_common(r4p)
    r5p = sub.add_parser("discover-round5",
                         help="enumerate the round-5 sources (naval-"
                              "encyclopedia.com warship articles from its "
                              "sitemap + qinetiq.com robotic products) and "
                              "enqueue them")
    _add_common(r5p)
    r6p = sub.add_parser("discover-round6",
                         help="enumerate the round-6 sources (elbit-"
                              "systems.com /land product tree from its "
                              "sitemap + amgeneral.com vehicle pages) and "
                              "enqueue them")
    _add_common(r6p)
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
    rea = sub.add_parser("re-enrich-all",
                         help="offline: re-parse cached detail HTML with improved "
                              "parsers and merge richer specs (no network)")
    _add_common(rea)
    cs = sub.add_parser("clean-specs",
                        help="offline hygiene sweep: merge keyless fragments, trim "
                             "prose values, drop nav junk, clear placeholder text")
    _add_common(cs)
    bc = sub.add_parser("backfill-country",
                        help="offline: fill missing country via own-specs, wiki "
                             "infoboxes, cross-source match, FAS US-heuristic, "
                             "hisutton prose (provenance recorded)")
    _add_common(bc)
    r7 = sub.add_parser("discover-round7",
                        help="enumerate globalmilitary.net equipment pages "
                             "(crawler-friendly open database)")
    _add_common(r7)
    te = sub.add_parser("discover-tanks-encyclopedia",
                        help="enumerate tanks-encyclopedia.com articles from "
                             "era index pages")
    _add_common(te)
    hl = sub.add_parser("discover-helis",
                        help="enumerate helis.com helicopter model pages via "
                             "manufacturer matrix")
    _add_common(hl)
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
    elif args.cmd == "discover-round4":
        cmd_discover_round4(args, s)
    elif args.cmd == "discover-round5":
        cmd_discover_round5(args, s)
    elif args.cmd == "discover-round6":
        cmd_discover_round6(args, s)
    elif args.cmd == "recategorize":
        cmd_recategorize(args, s)
    elif args.cmd == "dedupe-keys":
        cmd_dedupe_keys(args, s)
    elif args.cmd == "re-enrich-weaponsystems":
        cmd_reenrich_weaponsystems(args, s)
    elif args.cmd == "re-enrich-all":
        cmd_reenrich_all(args, s)
    elif args.cmd == "clean-specs":
        cmd_clean_specs(args, s)
    elif args.cmd == "backfill-country":
        cmd_backfill_country(args, s)
    elif args.cmd == "discover-round7":
        cmd_discover_round7(args, s)
    elif args.cmd == "discover-tanks-encyclopedia":
        cmd_discover_te(args, s)
    elif args.cmd == "discover-helis":
        cmd_discover_helis(args, s)
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
