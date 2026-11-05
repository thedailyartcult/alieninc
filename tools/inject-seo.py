#!/usr/bin/env python3
"""
Inject missing SEO tags across the whole site (idempotent, dry-run capable).

Two passes:
  1. Subdomain roots — the original hand-curated pack (Organization JSON-LD
     with parent Alien Inc + sameAs socials). SITES below.
  2. Every other deployed page — generic injection of:
       - <link rel="canonical">     (self-referencing, unless overridden)
       - <meta name="description">  (derived from page copy if missing)
       - Open Graph + Twitter Card  (og:url/og:title/og:description/og:image)
     Only tags that are MISSING are added; existing tags are never overwritten.

URL mapping mirrors tools/generate-sitemap.py so the canonical we emit matches
the URL Google actually indexes.

Usage:
    python3 tools/inject-seo.py            # apply
    python3 tools/inject-seo.py --dry-run  # report only, change nothing
    python3 tools/inject-seo.py --verbose  # per-file detail
"""
import argparse
import html as html_mod
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]

SOCIALS = [
    "https://www.linkedin.com/company/alieninc/",
    "https://www.linkedin.com/in/patrickneila/",
    "https://www.facebook.com/alieninc.tech/",
    "https://www.instagram.com/alieninc.tech/",
]

SITE_NAME = "Alien Inc"
OG_IMAGE = "https://alieninc.tech/logo.png"

# Hand-curated pack for subdomain roots: (canonical, site_name, title_hint, description)
SITES = {
    "a-san": ("https://a-san.alieninc.tech/", "A-SAN",
              "A-SAN - ASEAN Superiority Aerospace Navigator",
              "A-SAN (ASEAN Superiority Aerospace Navigator) by Alien Inc — aerospace awareness, founded by Patrick Neil Alcantara."),
    "centra": ("https://centra.alieninc.tech/", "Centra",
               "Centra Trust and Security Portal | Alien Inc",
               "Centra Trust and Security Portal by Alien Inc — compliance, security and trust. Founded by Patrick Neil Alcantara."),
    "genesis": ("https://genesis.alieninc.tech/", "Genesis",
                "Genesis Core — Alien Inc.",
                "Genesis Core by Alien Inc — research and exploration platform. Founded by Patrick Neil Alcantara."),
    "immanuel": ("https://immanuel.alieninc.tech/", "Immanuel",
                 "Global Security & Risk Management | Immanuel",
                 "Immanuel by Alien Inc — global security and risk management. Founded by Patrick Neil Alcantara."),
    "kmt": ("https://kmt.alieninc.tech/", "KMT Consulting Group",
            "Where Strategic Clarity Meets Applied AI | KMT Consulting Group",
            "KMT Consulting Group by Alien Inc — strategic clarity meets applied AI. Founded by Patrick Neil Alcantara."),
    "rousseau": ("https://rousseau.alieninc.tech/", "Rousseau",
                 "Rousseau | Home",
                 "Rousseau by Alien Inc. Founded by Patrick Neil Alcantara."),
    "secure": ("https://secure.alieninc.tech/", "Alien Inc Secure Portal",
               "Secure Portal Login | Alien Inc",
               "Secure portal by Alien Inc (Panteon). Founded by Patrick Neil Alcantara."),
    "thedailyartcult": ("https://thedailyartcult.lol", "The Daily Art Cult",
               "The Daily Art Cult",
               "The Daily Art Cult — bespoke audiobooks and philosophical reflections. A subsidiary of Alien Inc, founded by Patrick Neil Alcantara."),
}

# Subdomains whose pages live at https://<sub>.alieninc.tech/<file>
SUBDOMAINS = ["a-san", "centra", "genesis", "immanuel", "kmt", "rousseau", "secure"]

# Canonical overrides for known duplicate-title pairs.
# The dated article index.html and the named article share a title; the pretty
# URL is canonical. map: repo-relative posix path -> canonical URL
CANONICAL_OVERRIDES = {
    "articles/2026/09/24/index.html":
        "https://alieninc.tech/articles/2026/09/24/The-Alien-Minds-We-Built.html",
}

# Curated meta descriptions for pages where auto-derivation would pull a
# narrative hook or a thin stub instead of a usable search snippet. Maps
# repo-relative posix path -> description. Auto-derivation is the fallback.
DESCRIPTION_OVERRIDES = {
    "founder.html": (
        "Patrick Neil Alcantara — founder of Alien Inc, the seven-company "
        "operating group and independent guardian of Philippine digital "
        "infrastructure. Background, mission, and public profiles."
    ),
    "mission.html": (
        "The Alien Inc mission: sovereign continuity infrastructure for the "
        "next thousand years — detecting sabotage, verifying facilities, and "
        "preserving recoverable archives."
    ),
    "dashboard.html": (
        "Live Alien Inc network dashboard — operating companies, facility "
        "verification status, and real-time compliance posture across the "
        "seven-company group."
    ),
    "access-my-data.html": (
        "Request a copy of the personal data Alien Inc holds about you, "
        "exercising your right of access under GDPR, CCPA, and related "
        "frameworks."
    ),
    "delete-my-data.html": (
        "Request deletion of the personal data Alien Inc holds about you, "
        "exercising your right to erasure under GDPR, CCPA, and related "
        "frameworks."
    ),
    "do-not-sell.html": (
        "Opt out of the sale or sharing of your personal information under "
        "CCPA/CPRA. Alien Inc does not sell data; this page records your "
        "opt-out preference."
    ),
    "panteon/play.html": (
        "Panteon Play — interactive type test and live demo of the Panteon "
        "defense-grade SI automation platform by Alien Inc."
    ),
    # NOTE: panteon/login.html and panteon/admin.html are intentionally absent.
    # They are auth gates, skipped by the AUTH_FILES filter — an override here
    # would never be applied.
}


def esc(s: str) -> str:
    """Escape a value for use inside a double-quoted HTML attribute."""
    return html_mod.escape(s, quote=True)


def clean_text(fragment: str) -> str:
    """Strip tags/scripts and collapse whitespace."""
    fragment = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", fragment)
    fragment = re.sub(r"(?s)<[^>]+>", " ", fragment)
    fragment = html_mod.unescape(fragment)
    return re.sub(r"\s+", " ", fragment).strip()


def extract_title(html: str) -> str:
    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
    return clean_text(m.group(1)) if m else ""


def extract_description(html: str, title: str) -> str:
    """Prefer an existing og:description; else first substantial <p> after the
    first <h1>; else fall back to the title."""
    m = re.search(
        r'(?is)<meta[^>]+property=["\']og:description["\'][^>]+content=["\'](.*?)["\']',
        html,
    ) or re.search(
        r'(?is)<meta[^>]+content=["\'](.*?)["\'][^>]+property=["\']og:description["\']',
        html,
    )
    if m and clean_text(m.group(1)):
        return clip(clean_text(m.group(1)))

    # Find body after first </h1> (or <h1 ...>...</h1>) and take the first
    # paragraph with enough real text.
    body = html
    h1 = re.search(r"(?is)<h1[^>]*>.*?</h1>", html)
    if h1:
        body = html[h1.end():]
    for p in re.finditer(r"(?is)<p[^>]*>(.*?)</p>", body):
        text = clean_text(p.group(1))
        if len(text) >= 60:
            return clip(text)

    # No good paragraph — any <p> at all, else the title.
    for p in re.finditer(r"(?is)<p[^>]*>(.*?)</p>", html):
        text = clean_text(p.group(1))
        if len(text) >= 40:
            return clip(text)
    return clip(title) if title else ""


def clip(text: str, limit: int = 158) -> str:
    """Trim to <= limit chars on a word boundary, no trailing punctuation."""
    text = text.strip()
    if len(text) <= limit:
        return text.rstrip(".;, ")
    cut = text[:limit]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(".;, ")


def canonical_for(rel_posix: str) -> str:
    """Map a repo-relative path to its public canonical URL.

    Mirrors tools/generate-sitemap.py. rel_posix is relative to ROOT.
    """
    if rel_posix in CANONICAL_OVERRIDES:
        return CANONICAL_OVERRIDES[rel_posix]

    parts = rel_posix.split("/")
    top = parts[0]

    # Subdomain pages: a-san/index.html -> https://a-san.alieninc.tech/
    # Directory indexes strip the trailing index.html:
    #   kmt/dashboard/index.html -> https://kmt.alieninc.tech/dashboard/
    if top in SUBDOMAINS:
        rest = "/".join(parts[1:])
        if rest in ("", "index.html"):
            return f"https://{top}.alieninc.tech/"
        if rest.endswith("/index.html"):
            rest = rest[: -len("index.html")]
        return f"https://{top}.alieninc.tech/{rest}"

    # Panteon pages: panteon/foo/bar.html -> https://panteon.alieninc.tech/foo/bar.html
    if top == "panteon":
        rest = "/".join(parts[1:])
        if rest in ("", "index.html"):
            return "https://panteon.alieninc.tech/"
        if rest.endswith("/index.html"):
            rest = rest[: -len("index.html")]
        return f"https://panteon.alieninc.tech/{rest}"

    # Directory indexes: strip the trailing index.html so
    # kmt/dashboard/index.html -> https://kmt.alieninc.tech/dashboard/
    # and why/index.html        -> https://alieninc.tech/why/
    if rel_posix.endswith("/index.html"):
        dirpath = rel_posix[: -len("index.html")]
        return f"https://alieninc.tech/{dirpath}"

    # Everything else on the apex domain.
    return f"https://alieninc.tech/{rel_posix}"


def site_name_for(rel_posix: str) -> str:
    top = rel_posix.split("/")[0]
    if top in SITES:
        return SITES[top][1]
    if top == "panteon":
        return "Panteon"
    return SITE_NAME


def _site_root_for(rel_posix: str):
    """Return (root_url, root_name) for a repo path's site."""
    top = rel_posix.split("/")[0]
    if top in SITES:
        return SITES[top][0], SITES[top][1]
    if top == "panteon":
        return "https://panteon.alieninc.tech/", "Panteon"
    return "https://alieninc.tech/", SITE_NAME


def build_jsonld(rel_posix: str, title: str, desc: str, canonical: str,
                 site: str) -> str:
    """Build a site-appropriate JSON-LD block. Returns '' if nothing to add.

    Articles get Article schema (rich-result eligible). Everything else gets a
    WebPage node; non-root pages also get a BreadcrumbList built from the
    canonical URL path so Google can render a breadcrumb trail.
    """
    import json as _json
    from urllib.parse import urlparse

    parts = rel_posix.split("/")
    root, root_name = _site_root_for(rel_posix)
    data = None

    if parts[0] == "articles" and parts[-1] != "index.html":
        m = re.search(r"/(\d{4})/(\d{2})/(\d{2})/", rel_posix)
        data = {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": title,
            "url": canonical,
            "description": desc,
            "image": OG_IMAGE,
            "mainEntityOfPage": canonical,
            "author": {"@type": "Person", "name": "Patrick Neil Alcantara",
                       "url": "https://alieninc.tech/founder.html"},
            "publisher": {"@type": "Organization", "name": "Alien Inc",
                          "url": "https://alieninc.tech/",
                          "logo": {"@type": "ImageObject", "url": OG_IMAGE}},
        }
        if m:
            data["datePublished"] = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    else:
        page = {
            "@type": "WebPage",
            "name": title,
            "url": canonical,
            "isPartOf": {"@type": "WebSite", "name": root_name, "url": root},
        }
        if desc:
            page["description"] = desc
        segs = [s for s in urlparse(canonical).path.strip("/").split("/") if s]
        if segs:
            crumbs = [{"@type": "ListItem", "position": 1, "name": root_name,
                       "item": root}]
            accum = root.rstrip("/")
            for i, seg in enumerate(segs):
                accum = f"{accum}/{seg}"
                last = (i == len(segs) - 1)
                name = title if last else seg.replace("-", " ").replace(".html", "").title()
                item = canonical if last else accum
                crumbs.append({"@type": "ListItem", "position": i + 2,
                               "name": name, "item": item})
            if len(crumbs) > 1:
                page["breadcrumb"] = {"@type": "BreadcrumbList", "itemListElement": crumbs}
        data = {"@context": "https://schema.org", "@graph": [
            {"@type": "WebSite", "name": root_name, "url": root},
            page,
        ]}

    if not data:
        return ""
    body = _json.dumps(data, indent=4, ensure_ascii=False)
    return f'    <script type="application/ld+json">\n{body}\n    </script>'


def iter_deployed_pages():
    """Yield repo-relative posix paths of pages that are actually deployed.

    Mirrors the pages.yml whitelist + generate-sitemap.py coverage. Skips
    backups, build output, caches, and heavy data dirs.
    """
    skip_dirs = {
        ".backups", ".git", ".github", "__pycache__", "node_modules",
        "backend", "engine", "scanner", "data", "dataset", "db", "logs",
        "audit-logs", "connectors", "deploy", "tools", "nginx", "static",
        "alphazero", "bbg", "budibase", "gotham", "sims-suite", "platoon",
        "genesis-sub", "seo-audit", "_pages", "reports",
    }

    def ignored(p: pathlib.Path) -> bool:
        for part in p.parts:
            if part in skip_dirs or part.startswith("."):
                return True
        if ".bak" in p.name or p.name.endswith(".bak"):
            return True
        # Lazy-loaded platform FRAGMENTS (admin.html fetches these and injects the
        # returned <div> into a shell). Not standalone pages — no <html>/<head>.
        if "platforms" in p.parts and "pages" in p.parts:
            return True
        # Underscore-prefixed debug/internal files (e.g. hazards/noah/_diag2.html,
        # an 857KB MapLibre bundle).
        if p.name.startswith("_"):
            return True
        return False

    # Apex root pages. pages.yml whitelists these explicitly; try.html and
    # secure.html exist in the repo but are NOT deployed, so skip them.
    deployed_root = {
        "index.html", "404.html", "mission.html", "privacy.html", "terms.html",
        "founder.html", "about.html", "cookies.html", "dashboard.html",
        "access-my-data.html", "delete-my-data.html", "do-not-sell.html",
    }
    for p in sorted(ROOT.glob("*.html")):
        rel = p.relative_to(ROOT)
        if ignored(rel):
            continue
        if p.name not in deployed_root:
            continue
        yield rel.as_posix()

    # First-level directory indexes + their html files, for deployable dirs.
    deploy_dirs = ["articles", "panteon", "why", "trust", "labyu"] + SUBDOMAINS
    for d in deploy_dirs:
        base = ROOT / d
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*.html")):
            rel = p.relative_to(ROOT)
            if ignored(rel):
                continue
            # panteon backend/data already excluded via skip_dirs.
            yield rel.as_posix()


def build_head_pack(canonical: str, site: str, title: str, desc: str) -> str:
    socials_json = ",\n        ".join(f'"{s}"' for s in SOCIALS)
    return f"""    <link rel="canonical" href="{esc(canonical)}">
    <meta property="og:type" content="website">
    <meta property="og:url" content="{esc(canonical)}">
    <meta property="og:site_name" content="{esc(site)}">
    <meta property="og:title" content="{esc(title)}">
    <meta property="og:description" content="{esc(desc)}">
    <meta property="og:image" content="{esc(OG_IMAGE)}">
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="{esc(title)}">
    <meta name="twitter:description" content="{esc(desc)}">
    <meta name="twitter:image" content="{esc(OG_IMAGE)}">
    <script type="application/ld+json">
    {{
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": "{esc(site)}",
        "url": "{esc(canonical)}",
        "description": "{esc(desc)}",
        "parentOrganization": {{ "@type": "Organization", "name": "Alien Inc", "url": "https://alieninc.tech" }},
        "founder": {{ "@type": "Person", "name": "Patrick Neil Alcantara", "url": "https://alieninc.tech/founder.html", "sameAs": ["https://www.linkedin.com/in/patrickneila/"] }},
        "sameAs": [
        {socials_json}
        ]
    }}
    </script>"""


def process_subdomain_root(sub: str, canonical: str, site: str, title_hint: str,
                           desc: str, dry: bool, verbose: bool) -> bool:
    path = ROOT / sub / "index.html"
    if not path.exists():
        if verbose:
            print(f"{sub}: SKIP (no index.html)")
        return False
    html = path.read_text(encoding="utf-8", errors="replace")
    changed = False
    if 'rel="canonical"' not in html:
        html = re.sub(r"(</title>)", r"\1\n" + build_head_pack(canonical, site, title_hint, desc), html, count=1)
        changed = True
    else:
        if "sameAs" not in html:
            html = re.sub(r"(</title>)", r"\1\n" + build_head_pack(canonical, site, title_hint, desc), html, count=1)
            changed = True
    if 'name="description"' not in html:
        html = re.sub(r"(</title>)", r'\1\n    <meta name="description" content="' + esc(desc) + '">', html, count=1)
        changed = True

    # Image backfill. These roots got their OG/Twitter tags from an earlier,
    # narrower run that omitted og:image/twitter:image; the pack above is only
    # injected when canonical/sameAs are missing, so already-complete roots
    # would otherwise keep shipping image-less cards.
    if 'property="og:image"' not in html and 'property="og:title"' in html:
        img = f'\n    <meta property="og:image" content="{esc(OG_IMAGE)}">'
        for anchor in (r'(?i)(<meta[^>]+property="og:description"[^>]*>)',
                       r'(?i)(<meta[^>]+property="og:title"[^>]*>)',
                       r'(?i)(<meta[^>]+property="og:url"[^>]*>)'):
            html, n = re.subn(anchor, r'\1' + img, html, count=1)
            if n:
                changed = True
                break
    if 'name="twitter:image"' not in html and 'name="twitter:card"' in html:
        img = f'\n    <meta name="twitter:image" content="{esc(OG_IMAGE)}">'
        for anchor in (r'(?i)(<meta[^>]+name="twitter:description"[^>]*>)',
                       r'(?i)(<meta[^>]+name="twitter:title"[^>]*>)',
                       r'(?i)(<meta[^>]+name="twitter:card"[^>]*>)'):
            html, n = re.subn(anchor, r'\1' + img, html, count=1)
            if n:
                changed = True
                break

    if changed:
        if not dry:
            path.write_text(html, encoding="utf-8")
        print(f"{sub}/index.html: SEO pack injected{' (dry-run)' if dry else ''}")
    elif verbose:
        print(f"{sub}/index.html: already OK")
    return changed


def process_generic(rel_posix: str, dry: bool, verbose: bool) -> bool:
    path = ROOT / rel_posix
    parts = rel_posix.split("/")
    # Panteon platform page FRAGMENTS. These are not pages — admin.html lazy-loads
    # them via fetch("/static/platforms/{plat}/pages/{page}.html") and injects the
    # returned <div> into a shell. They have no <html>/<head>/<title>. Injecting a
    # canonical/description here is meaningless, and listing them as pages is a bug.
    if "platforms" in parts and "pages" in parts:
        if verbose:
            print(f"{rel_posix}: SKIP (lazy-loaded fragment)")
        return False

    # Underscore-prefixed files are debug/internal (e.g. hazards/noah/_diag2.html,
    # an 857KB MapLibre bundle) — never SEO targets.
    if parts[-1].startswith("_"):
        if verbose:
            print(f"{rel_posix}: SKIP (underscore debug file)")
        return False

    try:
        html = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        print(f"{rel_posix}: ERROR reading {e}")
        return False

    original = html

    # 404 pages are never SEO targets. Injecting a canonical + description
    # there asks Google to index a page whose whole job is to say "not here".
    # Covers root 404.html (which has noindex) and the bare subdomain stubs
    # (centra/kmt/panteon/rousseau/thedailyartcult) which have no robots meta.
    if pathlib.Path(rel_posix).name.lower() in ("404.html", "404.php"):
        if verbose:
            print(f"{rel_posix}: SKIP (404 page)")
        return False

    # Internal / non-public modules. These are reachable but declare themselves
    # non-public in copy; a canonical + description would recruit them into the
    # index against their stated purpose.
    #
    # Strip FOOTER boilerplate first: every centra/panteon legal page carries
    # "<span class=\"confidential-tag\">Confidential — Internal use only ·
    # Alien.Inc group companies</span>" in the footer. That tag is a
    # confidentiality notice about the *document*, not a claim that the page is
    # non-public — matching it would wrongly skip the public privacy/terms/cookies
    # pages from SEO. Only body-level markers count.
    INTERNAL_MARKERS = (
        "not intended for public access",
        "internal analytics module",
        "internal use only",
        "authorized personnel only",
    )
    body_for_check = re.sub(r"(?is)<footer\b.*?</footer>", " ", html)
    body_for_check = re.sub(r'(?is)<span[^>]*class="[^"]*confidential-tag[^"]*"[^>]*>.*?</span>', " ", body_for_check)
    low = body_for_check.lower()
    if any(marker in low for marker in INTERNAL_MARKERS):
        if verbose:
            print(f"{rel_posix}: SKIP (internal module)")
        return False

    # Auth gates and back-office surfaces. A login/admin/vault page has no
    # search intent worth capturing; canonical + description there only
    # invites crawlers toward an authentication wall.
    AUTH_DIRS = {"vault", "moderation", "admin", "private-area"}
    AUTH_FILES = {"login.html", "admin.html", "private-area.html"}
    if parts[-1].lower() in AUTH_FILES or any(p in AUTH_DIRS for p in parts[:-1]):
        if verbose:
            print(f"{rel_posix}: SKIP (auth/back-office)")
        return False

    # Never inject SEO signals into a page that declares noindex (auth gates,
    # previews). A canonical + description there is contradictory:
    # it asks Google to index a page it is simultaneously told to drop.
    if re.search(r'(?i)<meta[^>]+name=["\']robots["\'][^>]+content=["\'][^"\']*noindex', html):
        if verbose:
            print(f"{rel_posix}: SKIP (noindex)")
        return False

    title = extract_title(html)
    # A page with no <title> is almost certainly a lazy-loaded fragment or an
    # app shell, not an indexable document. Skip rather than invent a title.
    if not title:
        if verbose:
            print(f"{rel_posix}: SKIP (no <title> — fragment/shell)")
        return False

    # Curated override wins over auto-derivation. Overrides are hand-written to
    # length, so they are NOT clipped — clipping a curated snippet mid-sentence
    # (e.g. ending on "...Background") reads worse than a slightly long one.
    # Auto-derived text IS clipped to a word boundary at 158 chars.
    override = DESCRIPTION_OVERRIDES.get(rel_posix)
    if override:
        desc = override.strip()
    else:
        desc = clip(extract_description(html, title)) if extract_description(html, title) else ""
    canonical = canonical_for(rel_posix)
    site = site_name_for(rel_posix)
    inserted = []

    # 1. canonical
    if 'rel="canonical"' not in html and desc is not None:
        tag = f'    <link rel="canonical" href="{esc(canonical)}">'
        html, n = re.subn(r"(?i)(</title>)", lambda m: m.group(1) + "\n" + tag, html, count=1)
        if n:
            inserted.append("canonical")

    # 2. meta description
    if 'name="description"' not in html and desc:
        tag = f'    <meta name="description" content="{esc(desc)}">'
        html, n = re.subn(r"(?i)(</title>)", lambda m: m.group(1) + "\n" + tag, html, count=1)
        if n:
            inserted.append("description")

    # 3. Open Graph
    if 'property="og:title"' not in html and title:
        og = (
            f'    <meta property="og:type" content="website">\n'
            f'    <meta property="og:url" content="{esc(canonical)}">\n'
            f'    <meta property="og:site_name" content="{esc(site)}">\n'
            f'    <meta property="og:title" content="{esc(title)}">\n'
            f'    <meta property="og:description" content="{esc(desc or title)}">\n'
            f'    <meta property="og:image" content="{esc(OG_IMAGE)}">'
        )
        html, n = re.subn(r"(?i)(</title>)", lambda m: m.group(1) + "\n" + og, html, count=1)
        if n:
            inserted.append("og")

    # 4. Twitter Card
    if 'name="twitter:card"' not in html and title:
        tw = (
            f'    <meta name="twitter:card" content="summary_large_image">\n'
            f'    <meta name="twitter:title" content="{esc(title)}">\n'
            f'    <meta name="twitter:description" content="{esc(desc or title)}">\n'
            f'    <meta name="twitter:image" content="{esc(OG_IMAGE)}">'
        )
        html, n = re.subn(r"(?i)(</title>)", lambda m: m.group(1) + "\n" + tw, html, count=1)
        if n:
            inserted.append("twitter")

    # 5. og:image / twitter:image BACKFILL.
    # Pages written before this tool existed often have a partial OG block —
    # og:title/og:description/og:url but no og:image. Without an image the
    # card renders as plain text (no preview) on Slack/Discord/WhatsApp/X.
    # Anchor on the existing og:title/og:description so the image lands inside
    # the OG cluster rather than after </title> where the block may not be.
    if 'property="og:image"' not in html and 'property="og:title"' in html:
        img = f'\n    <meta property="og:image" content="{esc(OG_IMAGE)}">'
        for anchor in (r'(?i)(<meta[^>]+property="og:description"[^>]*>)',
                       r'(?i)(<meta[^>]+property="og:title"[^>]*>)',
                       r'(?i)(<meta[^>]+property="og:url"[^>]*>)'):
            html, n = re.subn(anchor, r'\1' + img, html, count=1)
            if n:
                inserted.append("og:image")
                break

    if 'name="twitter:image"' not in html and 'name="twitter:card"' in html:
        img = f'\n    <meta name="twitter:image" content="{esc(OG_IMAGE)}">'
        for anchor in (r'(?i)(<meta[^>]+name="twitter:description"[^>]*>)',
                       r'(?i)(<meta[^>]+name="twitter:title"[^>]*>)',
                       r'(?i)(<meta[^>]+name="twitter:card"[^>]*>)'):
            html, n = re.subn(anchor, r'\1' + img, html, count=1)
            if n:
                inserted.append("twitter:image")
                break

    # 6. Structured data (JSON-LD). Pages with none get Article schema (articles)
    # or WebPage + BreadcrumbList (everything else). Skipped when a page already
    # declares any ld+json so we never stack two conflicting graphs.
    if "application/ld+json" not in html:
        ld = build_jsonld(rel_posix, title, desc or "", canonical, site)
        if ld:
            html, n = re.subn(r"(?i)(</head>)", lambda m: ld + "\n" + m.group(1), html, count=1)
            if n:
                inserted.append("jsonld")

    if html != original:
        if not dry:
            path.write_text(html, encoding="utf-8")
        print(f"{rel_posix}: +{','.join(inserted) or 'touch'}{' (dry-run)' if dry else ''}")
        return True
    if verbose:
        print(f"{rel_posix}: already OK")
    return False


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would change, write nothing")
    ap.add_argument("--verbose", action="store_true",
                    help="also print pages that already have everything")
    args = ap.parse_args()

    if args.dry_run:
        print("=== DRY RUN — no files will be written ===\n")

    changed = 0

    print("--- Pass 1: subdomain roots (curated Organization pack) ---")
    for sub, (canon, site, title_hint, desc) in SITES.items():
        try:
            if process_subdomain_root(sub, canon, site, title_hint, desc,
                                      args.dry_run, args.verbose):
                changed += 1
        except Exception as e:
            print(f"{sub}: ERROR {e}")

    print("\n--- Pass 2: all deployed pages (generic canonical/desc/OG/Twitter) ---")
    seen = set()
    for rel in iter_deployed_pages():
        top = rel.split("/")[0]
        # Roots already handled by pass 1 (their pack is richer).
        if rel == f"{top}/index.html" and top in SITES:
            continue
        if rel in seen:
            continue
        seen.add(rel)
        try:
            if process_generic(rel, args.dry_run, args.verbose):
                changed += 1
        except Exception as e:
            print(f"{rel}: ERROR {e}")

    print(f"\n{'Would update' if args.dry_run else 'Updated'} {changed} files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
