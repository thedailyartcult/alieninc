"""Discovery: sitemap-based enumeration + category classification of product URLs.

Army Recognition exposes a JMAP sitemap with the full /military-products tree
(observed ~1,733 category+product URLs). Product pages are the 3+-segment leaf
paths. This module pulls the sitemap once per run and enqueues only product
URLs whose path classifies into one of the 10 catalog categories.
"""

from __future__ import annotations

import html as html_lib
import re
import urllib.parse

from .config import classify_path, classify_article, CATEGORY_KEYS

SITEMAP_CANDIDATES = [
    "https://www.armyrecognition.com/index.php?option=com_jmap&view=sitemap&format=xml",
    "https://www.armyrecognition.com/sitemap.xml",
]

PRODUCT_TREE = "/military-products/"


def _path_depth(u: str) -> int:
    if PRODUCT_TREE not in u:
        return 0
    return len(u.split(PRODUCT_TREE, 1)[1].split("/"))


def parse_sitemap(xml: str) -> list[str]:
    return [html_lib.unescape(u.strip()) for u in re.findall(r"<loc>(.*?)</loc>", xml, re.S)]


def classify_sitemap_url(url: str, category_display: str | None = None):
    """Classify a sitemap URL -> (is_product, category_key, category_display)."""
    if PRODUCT_TREE not in url:
        return False, None, None
    if _path_depth(url) < 3:
        return False, None, None          # category index page, not a product
    path = url.split(PRODUCT_TREE, 1)[1]
    key = classify_path(path)
    if key is None:
        return False, None, None
    return True, key, CATEGORY_KEYS[key]


def product_urls_from_sitemap(xml: str, wanted_keys: set[str]) -> list[tuple[str, str, str]]:
    """Returns [(url, category_key, category_display)] for wanted categories."""
    out = []
    for u in parse_sitemap(xml):
        is_product, key, disp = classify_sitemap_url(u)
        if is_product and key in wanted_keys:
            out.append((u, key, disp))
    return out


ARTICLE_MARKER = "?view=article"
# Army Recognition news article slugs often embed the system name, e.g.
# .../id=356575:sweden-boosts-...-giraffe-4a-radar-deal&catid=2
_ARTICLE_SLUG_RE = re.compile(r"(?<=:)[^&]+")


def article_urls_from_sitemap(xml: str, wanted_keys: set[str]) -> list[tuple[str, str, str]]:
    """Classify sitemap article URLs into the wanted categories by slug keywords.

    Article URLs look like
      https://www.armyrecognition.com/?view=article&id=356575:sweden-boosts-...-giraffe-4a-radar-deal&catid=2
    The slug after `id=...:` is the headline slug and embeds the system/weapon
    name, so keyword classification on it is a good first pass.
    """
    out = []
    for u in parse_sitemap(xml):
        if ARTICLE_MARKER not in u:
            continue
        slug = ""
        m = re.search(r"view=article&amp;id=\d+:([^&]+)", u)
        if not m:
            m = re.search(r"view=article&id=\d+:([^&]+)", u)
        if m:
            slug = urllib.parse.unquote(m.group(1).replace("&amp;", "&"))
        if not slug:
            # fallback: last path segment
            m2 = re.search(r"com/([\w\-.]+)", u)
            slug = m2.group(1) if m2 else ""
        key = classify_article(slug)
        if key and key in wanted_keys:
            out.append((u, key, CATEGORY_KEYS[key]))
    return out


def sitemap_urls_to_parse() -> list[str]:
    return SITEMAP_CANDIDATES
