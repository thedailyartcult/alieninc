"""Discovery: sitemap-based enumeration + category classification of product URLs.

Army Recognition exposes a JMAP sitemap with the full /military-products tree
(observed ~1,733 category+product URLs). Product pages are the 3+-segment leaf
paths. This module pulls the sitemap once per run and enqueues only product
URLs whose path classifies into one of the 10 catalog categories.
"""

from __future__ import annotations

import re
import urllib.parse

from .config import classify_path, CATEGORY_KEYS

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
    return [u.strip() for u in re.findall(r"<loc>(.*?)</loc>", xml, re.S)]


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


def sitemap_urls_to_parse() -> list[str]:
    return SITEMAP_CANDIDATES
