"""Patent publication feeds — turn public patent numbers into queued scan URLs.

This is the high-volume scale lever: the armyrecognition.com sitemap caps the
catalog (~1,552 product entries). Patent publications are abundant (hundreds of
thousands for broad defense queries), so feeding their publication numbers into
the scanner queue is how A-SAN reaches catalogue scale.

Each backend returns an iterable of publication numbers (e.g. "US9123467B2",
"US2020010000A1"). Numbers are converted into Google Patents reader URLs —
patents.google.com serves a single clean page per publication and is robots-
friendly; the engine's existing `parse_patent` (engine._process, HOST
patents.google.com) reads them — then enqueued into the scan store.

Sources supported:
  * USPTO Open Data Portal (data.uspto.gov / api.patentsview.org) — requires a
    USPTO.gov account + bearer token (registered, MFA-required since Aug 2026).
    Env: USPTO_ODP_TOKEN.
  * Espacenet OPS (official EPO API, free developer key) — env ESPACENET_OPS_KEY /
    _SECRET (already wired into Settings).
  * A plain text file (--patents-file) listing publication numbers, one per
    line. Use this until a key is registered, or to replay a curated list.

All fetches respect robots.txt and the scanner's politeness settings; the ODP/
OPS endpoints are official APIs (not the browser UIs that block autonomous
access).
"""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .engine import Engine, PATENTS_HOST
from .models import SourceRef  # noqa: F401  (kept for downstream symmetry)
from .net import HttpFetcher, RobotsGate

log = logging.getLogger("scan")

USER_AGENT = "ASAN-Scanner/1.0 (+A-SAN research catalog; ops@asan.local)"
GOOGLE_PATENTS = "https://patents.google.com/patent/{pub}/en"

def _odp_search(token: str, query: str, per_page: int = 50, max_pages: int = 20):
    """USPTO Open Data Portal patent search.

    Returns publication numbers. Yields until the result set is exhausted or
    max_pages is reached. Requires a bearer token from a USPTO.gov account.
    """
    base = "https://api.patentsview.org/api/search"
    body = {"query": {"_text_all": query}, "options": {"per_page": per_page}}
    for page in range(1, max_pages + 1):
        body["options"]["page"] = page
        data = json.dumps(body).encode()
        req = urllib.request.Request(base, data=data,
                                     headers={"User-Agent": USER_AGENT,
                                              "Content-Type": "application/json",
                                              "Accept": "application/json",
                                              "Authorization": f"Bearer {token}"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                d = json.loads(r.read().decode("utf-8", "ignore"))
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise PermissionError("USPTO ODP token missing/invalid — "
                                      "register at data.uspto.gov (requires USPTO.gov account)") from e
            log.warning("ODP HTTP %s on page %s", e.code, page)
            break
        except Exception as e:
            log.warning("ODP fetch error: %s", e)
            break
        results = d.get("results") or []
        if not results:
            break
        for rec in results:
            pub = rec.get("patent_number") or rec.get("publication_number")
            if pub:
                yield pub
        if len(results) < per_page:
            break
        time.sleep(0.5)


def _ops_search(key: str, secret: str, query: str, per_page: int = 50,
                max_pages: int = 20):
    """Espacenet OPS published-data search (official EPO API).

    Requires ESPACENET_OPS_KEY / ESPACENENT_OPS_SECRET env vars (free EPO
    developer account). Yields publication numbers (e.g. "EP1234567A1").
    """
    token_url = "https://ops.epo.org/3.2/auth/accesstoken"
    body = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode()
    req = urllib.request.Request(token_url, data=body, method="POST")
    req.add_header("Authorization", "Basic " +
                   __import__("base64").b64encode(f"{key}:{secret}".encode()).decode())
    with urllib.request.urlopen(req, timeout=30) as r:
        token = json.loads(r.read())["access_token"]
    search_url = "https://ops.epo.org/3.2/rest-services/published-data/search/biblio"
    for page in range(max_pages):
        q = urllib.parse.urlencode({"q": query, "Range": f"{page*per_page+1}-{(page+1)*per_page}"})
        req = urllib.request.Request(f"{search_url}?{q}")
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                d = json.loads(r.read())
        except Exception as e:
            log.warning("OPS fetch error: %s", e)
            break
        docs = (d.get("ops:world-patent-data", {})
                .get("ops:biblio-search-result", {})
                .get("ops:search-result", {})
                .get("ops:publication-reference", []))
        if not docs:
            break
        for doc in docs:
            doc_id = doc.get("ops:document-id", [{}])[0]
            pub = doc_id.get("ops:doc-number")
            if pub:
                yield pub
        if len(docs) < per_page:
            break
        time.sleep(1.0)


def feed_patents(engine: Engine, query: str, category_display: str,
                 limit: int | None = None, per_page: int = 50, max_pages: int = 20):
    """Run whichever authenticated patent feed is configured, enqueue the results
    as Google-Patents reader URLs under `category_display`.

    Returns the count enqueued.
    """
    s = engine.settings
    token = (getattr(s, "uspto_odp_token", "") or "").strip()
    if not token and getattr(s, "espacenet_ops_key", "") and getattr(s, "espacenet_ops_secret", ""):
        gen = _ops_search(s.espacenet_ops_key, s.espacenet_ops_secret, query,
                          per_page=per_page, max_pages=max_pages)
    elif token:
        gen = _odp_search(token, query, per_page=per_page, max_pages=max_pages)
    else:
        raise PermissionError(
            "No patent feed configured. Set USPTO_ODP_TOKEN env var (USAJPTO Open "
            "Data Portal bearer) OR ESPACENET_OPS_KEY/SECRET (EPO OPS), or use "
            "`scan patent-feed --patents-file <list>.txt` to feed a manual list.")

    count = 0
    for pub in gen:
        if limit is not None and count >= limit:
            break
        url = GOOGLE_PATENTS.format(pub=urllib.parse.quote(pub, safe=""))
        if engine.store.enqueue(url, PATENTS_HOST, category=category_display, kind="patent"):
            count += 1
    log.info("patent feed enqueued %d urls for '%s' (query=%r)", count, category_display, query)
    return count


def feed_from_file(engine: Engine, path: str, category_display: str,
                   limit: int | None = None):
    """Enqueue publication numbers listed one-per-line in a text file."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"patents file not found: {path}")
    count = 0
    for line in p.read_text(encoding="utf-8").splitlines():
        pub = line.strip()
        if not pub or pub.startswith("#"):
            continue
        if limit is not None and count >= limit:
            break
        url = GOOGLE_PATENTS.format(pub=urllib.parse.quote(pub, safe=""))
        if engine.store.enqueue(url, PATENTS_HOST, category=category_display, kind="patent"):
            count += 1
    log.info("patent feed enqueued %d urls from %s", count, path)
    return count
