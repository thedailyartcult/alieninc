"""Parser for tanks-encyclopedia.com — online tank & AFV museum.

robots.txt (2026-08-26): User-agent:* Allow:/ with Cloudflare Content-Signals
search=yes, ai-train=no, use=reference — fact extraction with attribution is
permitted; no AI training use. Sitemap files are bot-blocked; discovery uses
the public category index pages instead (/modern-tanks.php,
/cold-war-tanks.php, /ww2-tanks.php, /ww1-tanks.php).

Article structure: <h1> designation; a 'Specifications' block where
'Key Value Key Value ...' runs together in text (keys come from a fixed
vocabulary); operator tables ('Country Quantity Order Delivery'); long-form
prose history. © Tank Encyclopedia — fact extraction with attribution.
"""
from __future__ import annotations

import html as html_lib
import re

from .models import CatalogEntry, SourceRef, now_iso

_HOST = "tanks-encyclopedia.com"

# Category index pages used for discovery.
TE_INDEX_URLS = [
    "https://tanks-encyclopedia.com/modern-tanks.php",
    "https://tanks-encyclopedia.com/cold-war-tanks.php",
    "https://tanks-encyclopedia.com/ww2-tanks.php",
    "https://tanks-encyclopedia.com/ww1-tanks.php",
]

# Ordered usage: matched longest-first, matched spans are blanked out of the
# working copy so short keys cannot re-match inside compound ones
# ('weight' inside 'Empty Weight').
_SPEC_KEYS = [
    "Dimensions (LxWxH)", "Ground pressure", "Power-to-weight ratio",
    "Maximum speed", "Operational range", "Effective firing range",
    "Fuel Capacity", "Fording depth", "Vertical obstacle",
    "Trench crossing", "Angle of approach", "Angle of departure",
    "Turning circle", "Empty Weight", "Gross Weight", "Combat Weight",
    "Battle Range", "Engine type", "Engine power", "Max grade",
    "Secondary armament", "Main armament", "Brake system",
    "Transmission", "Suspension", "Dimensions", "Armour", "Armor",
    "Armament", "Crew", "Weight", "Speed", "Range", "Engine", "Power",
    "Length", "Width", "Height", "Wheelbase", "Ground clearance",
    "Clearance", "Caliber", "Elevation",
    "Traverse", "Ammunition", "Fire rate", "Radio", "Sight", "Capacity",
    "Payload", "Tires", "Drive", "Fuel", "Protection", "Obstacle",
]


def is_te_article_url(url: str) -> bool:
    """Article URLs: /<era>/<country>/<slug>/ or /<era>/<country>/<slug>.php"""
    if not re.match(r"https://tanks-encyclopedia\.com/", url, re.I):
        return False
    path = url.lower().rsplit("tanks-encyclopedia.com/", 1)[-1].rstrip("/")
    parts = [p for p in path.split("/") if p]
    if len(parts) < 3:
        return False
    if any(p.endswith((".jpg", ".png", ".gif", ".webp")) for p in parts):
        return False
    era = parts[0]
    if era not in ("modern", "cold-war", "ww2", "ww1", "interwar"):
        return False
    last = parts[-1]
    if last in ("index", "about", "contact") or "." in last.rsplit("/", 0)[0] \
            and not last.endswith(".php"):
        return False
    return True


def parse_te_listing(html: str) -> list[str]:
    """Extract article URLs from an index page."""
    links = re.findall(r'href="(https://tanks-encyclopedia\.com/[^"]+)"',
                       html or "", re.I)
    seen: set[str] = set()
    out: list[str] = []
    for u in links:
        u = u.rstrip("/") + ("/" if not u.endswith(".php") else "")
        if u in seen or not is_te_article_url(u):
            continue
        seen.add(u)
        out.append(u)
    return out


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", html_lib.unescape(
        re.sub(r"<[^>]+>", " ", text))).strip()


def parse_tanks_encyclopedia(url: str, html: str,
                             category_display: str = "") -> CatalogEntry | None:
    """Parse one tanks-encyclopedia.com article."""
    if not html:
        return None
    h1_m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S | re.I)
    name = _clean(h1_m.group(1)) if h1_m else ""
    name = re.sub(r"\s*(Tank Encyclopedia)$", "", name).strip()
    if not name or len(name) > 120:
        return None

    specs: list[str] = []
    # Locate the Specifications block and split on known keys.
    body = re.sub(r"<script.*?</script>|<style.*?</style>", "", html,
                  flags=re.S | re.I)
    text = _clean(body)
    m = re.search(r"Specifications?\s*[:\-–]?\s*(.{80,4000}?)(?:Sources?|"
                  r"Further reading|References|Bibliography|Gallery|$)",
                  text, re.I)
    if m:
        block = m.group(1)
        low = block.lower()
        found: list[tuple[int, int, str]] = []  # (start, end, key)
        for k in sorted(_SPEC_KEYS, key=len, reverse=True):
            kl = k.lower()
            start = 0
            while True:
                i = low.find(kl, start)
                if i == -1:
                    break
                j = i + len(kl)
                before_ok = i == 0 or not (low[i - 1].isalnum())
                after_ok = j >= len(low) or not low[j].isalnum()
                inside_taken = any(fs <= i and j <= fe for fs, fe, _ in found)
                if before_ok and after_ok and not inside_taken:
                    found.append((i, j, k))
                    start = j
                else:
                    start = i + 1
        found.sort()
        for idx, (i, j, k) in enumerate(found):
            end = found[idx + 1][0] if idx + 1 < len(found) else len(block)
            val = block[j:end].strip(" :-–—.,;")
            val = re.sub(r"\s+", " ", val)[:170]
            if len(val) >= 1 and not val.lower().startswith(("see ", "n/a")):
                specs.append(f"{k}: {val}")
        specs = specs[:22]

    # Description: first substantial paragraph of the article body.
    desc = ""
    paras = re.findall(r"<p[^>]*>(.*?)</p>", body, re.S | re.I)
    for p in paras:
        t = _clean(p)
        if len(t) > 120 and not t.startswith(("Leander", "September", "©")):
            desc = t[:600]
            break

    if not specs and not desc:
        return None

    return CatalogEntry(
        designation=name,
        alt_names=[],
        country="",
        manufacturer="",
        category=category_display or "Armored vehicles and equipment",
        description=desc,
        specs=specs,
        sources=[SourceRef("Tank Encyclopedia", url)],
        fetched_at=now_iso(),
    )
