"""Build the a-san identification-game dataset (data/play.json).

Reads the curated flagship picklist (data/picklist.json) and resolves one
verified lead image per entry from English Wikipedia:

  1. exact-title pass   — all candidate titles (designation + alt_names) in
                          ONE batched query; first non-missing page with a
                          thumbnail wins (candidate order preserved)
  2. search pass        — generator=search on the raw designation; accepted
                          only if the top hit carries a thumbnail

Politeness: descriptive User-Agent, ~1 request / min_delay between calls,
exponential backoff on 429/5xx, disk cache (scanner/data/play_cache.json) so
reruns are free and resumable. The MediaWiki API at /w/api.php is this repo's
sanctioned Wikipedia route (see parsers_wikipedia.py header and the
import-wikipedia command); no naive /w/ robots substring check here.

Entries that resolve to the SAME wiki article are deduplicated (first wins) —
duplicate imagery would make ambiguous game answers. Entries with no image are
reported as unresolved and excluded. A manual blocklist
(data/play-blocklist.json, list of designations) survives regeneration.

With expand_to=N the pool is topped up beyond the curated picklist: extra
catalog entries are drawn round-robin across category files in data/
(deterministic seeded shuffle within each category), resolved through the same
cache/guards, and tagged origin="expanded" in play.json.

Output: <site-root>/data/play.json — consumed by play.html at the site root.
"""

from __future__ import annotations

import json
import random
import re
import time
import urllib.parse
import urllib.request
import urllib.robotparser
from datetime import datetime, timezone
from pathlib import Path

from .config import Settings, category_key

WIKI_API = "https://en.wikipedia.org/w/api.php"
WIKI_ARTICLE = "https://en.wikipedia.org/wiki/"
THUMB_SIZE = 800
MAX_CANDIDATES = 5
MAX_ALT_NAMES = 4


def _strip_html(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s or "").replace("\n", " ").strip()


def _slug(designation: str, idx: int) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", designation.lower()).strip("-")[:48].strip("-")
    return f"{s or 'item'}-{idx:03d}"


class WikiClient:
    """Minimal polite MediaWiki API JSON client (read-only queries)."""

    def __init__(self, settings: Settings):
        self.ua = settings.user_agent
        self.delay = max(1.0, settings.min_delay_seconds)
        self.timeout = settings.request_timeout
        self._last = 0.0

    def _throttle(self):
        wait = self.delay - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)

    def query(self, params: dict, retries: int = 3):
        base = {"format": "json", "formatversion": "2", "origin": "*"}
        url = WIKI_API + "?" + urllib.parse.urlencode({**base, **params})
        last_err: Exception | None = None
        for attempt in range(1, retries + 1):
            self._throttle()
            try:
                self._last = time.monotonic()
                req = urllib.request.Request(url, headers={"User-Agent": self.ua})
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return json.load(resp)
            except Exception as exc:  # noqa: BLE001 - single retry policy here
                last_err = exc
                code = getattr(exc, "code", None)
                pause = (10.0 if code == 429 else 2.0 * attempt)
                time.sleep(pause)
        raise RuntimeError(f"wikipedia api failed after {retries} attempts: {last_err}")


def _page_thumb(page: dict) -> dict | None:
    thumb = page.get("thumbnail") or {}
    src = thumb.get("source")
    if not src:
        return None
    meta = {}
    for ii in page.get("imageinfo", []) or []:
        ext = ii.get("extmetadata") or {}
        if ext.get("Artist"):
            meta["artist"] = _strip_html(ext["Artist"].get("value", ""))[:120]
        if ext.get("LicenseShortName"):
            meta["license"] = _strip_html(ext["LicenseShortName"].get("value", ""))
    return {
        "thumb_url": src,
        "width": thumb.get("width"),
        "height": thumb.get("height"),
        **meta,
    }


def _fold(s: str) -> str:
    """ASCII-fold + unify Turkish dotless i, so 'Kızılelma' ~ 'kizilelma'."""
    import unicodedata
    s = s.replace("ı", "i").replace("İ", "i")
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", _fold(s).lower())


_TITLE_REJECT = ("airport", "valley", "industries", "company", "corporation",
                 "university", "museum", "disambiguation")

# short ALL-CAPS tokens that are really common English nouns — useless as
# identity evidence ("AT-4 HEAT" -> "Heat pump", "Sharp Claw" -> "Claw")
_ACRONYM_STOP = {"heat", "claw", "wolf", "fire", "star", "moon", "king",
                 "rose", "case", "lamp", "wave"}


_STOP_WORDS = {
    "class", "with", "and", "the", "system", "systems", "vehicle", "vehicles",
    "missile", "missiles", "munition", "munitions", "drone", "drones", "uav",
    "uavs", "ugv", "ugvs", "radar", "frigate", "destroyer", "submarine",
    "carrier", "aircraft", "tank", "rocket", "rockets", "launcher", "launchers",
    "loitering", "improved", "advanced", "attack", "combat", "unmanned",
    "aerial", "ground", "guided", "long", "range", "version", "variant",
    "project", "air", "surface", "defense", "defence", "block", "based",
}


def _candidate_signals(candidates: list[str]) -> tuple[set[str], set[str], set[str]]:
    """(normalized codes, significant words >=5 chars, ALL-CAPS acronyms >=4).

    Chunk-based: whitespace/slash-separated chunks keep hyphenated military
    designators intact ('V-BAT' -> acronym vbat, 'Kh-59' -> code kh59,
    'FLM 136' -> joined code flm136). Bare numbers never count as codes.
    """
    codes: set[str] = set()
    words: set[str] = set()
    acronyms: set[str] = set()
    for text in candidates:
        t = _fold(text)
        prev_core = ""
        for chunk in re.split(r"[\s/]+", t):
            if not chunk:
                continue
            core = re.sub(r"[^a-z0-9]", "", chunk.lower())
            letters = re.sub(r"[^a-z]", "", core)
            digits = re.sub(r"[^0-9]", "", core)
            stripped = chunk.strip("-().,")
            if len(letters) >= 5 and letters not in _STOP_WORDS:
                words.add(letters)
            for part in re.split(r"[-]", chunk):
                pl_ = re.sub(r"[^a-z]", "", part.lower())
                if len(pl_) >= 5 and pl_ not in _STOP_WORDS:
                    words.add(pl_)
            if (len(stripped) >= 4 and stripped.isupper()
                    and len(letters) >= 4 and letters not in _STOP_WORDS
                    and letters not in _ACRONYM_STOP):
                acronyms.add(letters)
            if digits and letters and len(core) >= 3:
                codes.add(core)                      # kh59, aim120, flm136 …
            elif digits and not letters and re.fullmatch(r"[a-z]+", prev_core or "") \
                    and 2 <= len(prev_core) <= 6:
                codes.add(prev_core + digits)        # 'Kh' + '59' across a space
            prev_core = core
    return codes, words, acronyms


def _search_acceptable(candidates: list[str], title: str) -> bool:
    """Guard for search-pass results: the found article title must genuinely
    look like the requested system. Rejects generic/wrong-article landings
    (e.g. 'Loitering munition' for Hero-120, airports, manufacturer pages)."""
    if any(bad in title.lower() for bad in _TITLE_REJECT):
        return False
    tn = _norm(title)
    tl = _fold(title).lower()
    codes, words, acronyms = _candidate_signals(candidates)
    if any(c in tn for c in codes):
        return True
    # whole-word hits only: 'engineer' must not match 'engineering'
    hits = [w for w in words if re.search(rf"\b{re.escape(w)}\b", tl)]
    if len(hits) >= 2 or any(len(w) >= 6 for w in hits):
        return True
    # weak word evidence: demand most notable ALL-CAPS acronyms to appear
    if acronyms:
        found = sum(1 for a in acronyms if a in tn)
        if found >= max(1, (len(acronyms) + 1) // 2):
            return True
    return False


def _title_score(candidates: list[str], title: str) -> int:
    """Higher = stronger evidence the title IS the requested system.
    Exact normalized candidate match dominates; then full-candidate
    containment; then per-signal overlap (codes, distinctive words)."""
    tn = _norm(title)
    tl = _fold(title).lower()
    codes, words, _acronyms = _candidate_signals(candidates)
    score = 1
    if any(_norm(c) == tn for c in candidates):
        return 100
    if any(c in tn or (len(tn) >= 4 and tn in c) for c in codes):
        score += 2
    score += sum(1 for w in words if w in tl)
    for cand in candidates:
        cn = _norm(cand)
        if len(cn) >= 5 and cn in tn:
            score += 5
        elif len(tn) >= 5 and tn in cn:
            score += 5
    return score


def resolve_entry(client: WikiClient, entry: dict) -> tuple[dict | None, str]:
    """Returns (image_record|None, status) where status explains misses."""
    candidates = [entry["designation"]] + [a for a in entry.get("alt_names", [])[:MAX_ALT_NAMES]]
    candidates = [c.strip() for c in candidates if c and c.strip()][:MAX_CANDIDATES]

    # Pass 1: batched exact-title lookup (redirects resolved server-side).
    data = client.query({
        "action": "query",
        "titles": "|".join(candidates),
        "redirects": 1,
        "prop": "pageimages|imageinfo",
        "piprop": "thumbnail",
        "pithumbsize": THUMB_SIZE,
        "iiprop": "extmetadata",
        "iiextmetadatafilter": "Artist|LicenseShortName",
    })
    pages = {p["title"]: p for p in data.get("query", {}).get("pages", [])}
    # honour redirects/normalizations so candidate order maps onto final titles
    for mapping in ("normalized", "redirects"):
        for m in data.get("query", {}).get(mapping, []) or []:
            if m.get("to") in pages:
                pages[m["from"]] = pages[m["to"]]
    for cand in candidates:
        page = pages.get(cand)
        if page and "missing" not in page:
            thumb = _page_thumb(page)
            if thumb:
                rec = {"wiki_title": page["title"], **thumb}
                return rec, "title"

    # Pass 2: search fallback on the raw designation — walk the ranked hits,
    # keep those passing the title guard, prefer the strongest title match.
    data = client.query({
        "action": "query",
        "generator": "search",
        "gsrsearch": candidates[0],
        "gsrlimit": 5,
        "redirects": 1,
        "prop": "pageimages|imageinfo",
        "piprop": "thumbnail",
        "pithumbsize": THUMB_SIZE,
        "iiprop": "extmetadata",
        "iiextmetadatafilter": "Artist|LicenseShortName",
    })
    scored: list[tuple[int, int, dict, dict]] = []  # (-score, index, page, thumb)
    for pos, page in enumerate(data.get("query", {}).get("pages", []) or []):
        if "missing" in page:
            continue
        if not _search_acceptable(candidates, page.get("title", "")):
            continue
        thumb = _page_thumb(page) or {}
        scored.append((-_title_score(candidates, page.get("title", "")),
                       pos, page, thumb))
    scored.sort()
    for _, _, page, thumb in scored:   # best-scoring hit WITH an image wins
        if thumb:
            rec = {"wiki_title": page["title"], **thumb}
            return rec, "search"
    return (None, "no-image") if scored else (None, "no-wikipedia-image")


def _expansion_pools(site_data: Path, blocked: set[str],
                     used: set[str]) -> dict[str, list[dict]]:
    """Eligible extra entries per category key for pool expansion.

    Reads every data/<category_key>.json catalog file (read-only), drops
    blocked / already-attempted designations, then seeded-shuffles each pool
    so expansion order is deterministic across reruns."""
    cats = json.loads(
        (site_data / "categories.json").read_text(encoding="utf-8"))["categories"]
    rng = random.Random(20260824)
    pools: dict[str, list[dict]] = {}
    for c in cats:
        f = site_data / f"{c['key']}.json"
        if not f.exists():
            continue
        data = json.loads(f.read_text(encoding="utf-8"))
        cand = [e for e in data.get("entries", [])
                if e.get("designation", "").strip()
                and e["designation"].strip() not in blocked
                and e["designation"].strip() not in used]
        rng.shuffle(cand)
        if cand:
            pools[c["key"]] = cand
    return pools


def build_play_dataset(s: Settings, force_refresh: bool = False,
                       expand_to: int = 0) -> dict:
    site_data = s.root.parent / "data"
    picklist_path = site_data / "picklist.json"
    out_path = site_data / "play.json"
    blocklist_path = site_data / "play-blocklist.json"
    cache_path = s.root / "data" / "play_cache.json"

    picklist = json.loads(picklist_path.read_text(encoding="utf-8"))
    entries = picklist.get("entries", [])
    blocked = set()
    if blocklist_path.exists():
        blocked = set(json.loads(blocklist_path.read_text(encoding="utf-8")))

    cache: dict = {}
    if cache_path.exists() and not force_refresh:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))

    client = WikiClient(s)
    items: list[dict] = []
    unresolved: list[dict] = []
    duplicates_dropped: list[str] = []
    seen_titles: set[str] = set()
    attempted: set[str] = set()
    cache_dirty = False

    def resolve_and_append(e: dict, origin: str) -> str:
        """Shared resolution path for curated and expanded entries.
        Returns one of: added, unresolved, duplicate, blocked."""
        nonlocal cache_dirty
        desig = e.get("designation", "").strip()
        cat = e.get("category", "")
        if not desig or desig in blocked:
            return "blocked"
        attempted.add(desig)
        try:
            key = category_key(cat)
        except KeyError:
            key = re.sub(r"[^a-z0-9]+", "-", cat.lower()).strip("-")

        cached = cache.get(desig)
        if cached is None:
            rec, status = resolve_entry(client, e)
            cache[desig] = {"rec": rec, "status": status}
            cache_dirty = True
        else:
            rec, status = cached["rec"], cached["status"]

        if rec is None:
            unresolved.append({"designation": desig, "reason": status})
            return "unresolved"
        if rec["wiki_title"] in seen_titles:
            duplicates_dropped.append(f"{desig} == {rec['wiki_title']}")
            return "duplicate"
        seen_titles.add(rec["wiki_title"])
        items.append({
            "id": _slug(desig, len(items)),
            "designation": desig,
            "alt_names": e.get("alt_names", []),
            "category": cat,
            "category_key": key,
            "country": e.get("country", ""),
            "manufacturer": e.get("manufacturer", ""),
            "wiki_title": rec["wiki_title"],
            "wiki_url": WIKI_ARTICLE + rec["wiki_title"].replace(" ", "_"),
            "image_url": rec["thumb_url"],
            "image_w": rec.get("width"),
            "image_h": rec.get("height"),
            "credit_artist": rec.get("artist", ""),
            "credit_license": rec.get("license", ""),
            "origin": origin,
        })
        return "added"

    for e in entries:
        resolve_and_append(e, "curated")

    curated_count = len(items)
    expanded_count = 0
    if expand_to > curated_count:
        pools = _expansion_pools(site_data, blocked, attempted)
        keys = sorted(pools)
        while len(items) < expand_to and pools:
            for k in list(keys):
                if len(items) >= expand_to:
                    break
                lst = pools.get(k)
                if not lst:
                    pools.pop(k, None)
                    continue
                resolve_and_append(lst.pop(0), "expanded")
                expanded_count = len(items) - curated_count

    if cache_dirty:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

    dataset = {
        "schema_version": 2,
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": ("curated flagship picklist -> en.wikipedia lead images"
                   if not expanded_count else
                   "curated flagship picklist + catalog expansion -> "
                   "en.wikipedia lead images"),
        "count": len(items),
        "items": items,
    }
    out_path.write_text(json.dumps(dataset, ensure_ascii=False, indent=1),
                        encoding="utf-8")

    by_cat: dict[str, int] = {}
    for it in items:
        by_cat[it["category"]] = by_cat.get(it["category"], 0) + 1
    return {
        "picklist_entries": len(entries),
        "blocked": sorted(blocked & {e.get("designation", "") for e in entries}),
        "resolved": len(items),
        "curated": curated_count,
        "expanded": expanded_count,
        "by_category": by_cat,
        "unresolved": unresolved,
        "duplicates_dropped": duplicates_dropped,
        "cache": str(cache_path),
        "out": str(out_path),
    }
