#!/usr/bin/env python3
"""Build Labyu (Filipino Founders Directory) static profiles + discovery files.

Source of truth: labyu/founders.json
Outputs (deterministic, static-hosting safe):
  labyu/<slug>/index.html      one per founder (ProfilePage + Person + Organization @graph)
  labyu/sitemap-founders.xml   index + every profile URL
  labyu/llms.txt               one line per founder for LLM-crawler consumption
  labyu/index.html             patched in place: canonical/OG + directory JSON-LD + cards
                               (cards region + JSON-LD block are regenerated; page shell untouched)

Usage:
  python3 tools/build-founders.py            # build
  python3 tools/build-founders.py --check    # CI: rebuild to temp and diff (fail on drift)

Future domain: Labyu will move to its own domain. Override with --base
(e.g. --base https://labyu.ph). Defaults to the current hidden path.
"""
import argparse
import copy
import html
import json
import pathlib
import re
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]
LABYU = ROOT / "labyu"
DATA = LABYU / "founders.json"
INDEX = LABYU / "index.html"
DEFAULT_BASE = "https://alieninc.tech/labyu"

REQUIRED = ["slug", "name", "role", "company", "industry", "location"]
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def load():
    records = json.loads(DATA.read_text(encoding="utf-8"))
    assert isinstance(records, list) and records, "founders.json must be a non-empty list"
    seen = set()
    for i, r in enumerate(records):
        for f in REQUIRED:
            if not str(r.get(f, "")).strip():
                raise ValueError(f"record #{i} missing required field: {f} ({r.get('slug', '?')})")
        if not SLUG_RE.match(r["slug"]):
            raise ValueError(f"bad slug: {r['slug']!r} (lowercase a-z0-9-hyphens only)")
        if r["slug"] in seen:
            raise ValueError(f"duplicate slug: {r['slug']}")
        seen.add(r["slug"])
    return records


def esc(s):
    return html.escape(str(s or ""), quote=True)


def initials(name):
    parts = [p for p in str(name).split() if p]
    return ("".join(p[0] for p in parts[:2]) or "?").upper()


def profile_ld(base, r):
    url = f"{base}/{r['slug']}/"
    same_as = [v for v in (r.get("links") or {}).values() if v]
    person = {
        "@type": "Person",
        "@id": f"{url}#person",
        "name": r["name"],
        "jobTitle": f"{r['role']} at {r['company']}",
        "worksFor": {"@id": f"{url}#org"},
        "homeLocation": {"@type": "Place", "name": r["location"]},
        "knowsAbout": [r["industry"]],
        "url": url,
    }
    if same_as:
        person["sameAs"] = same_as
    if r.get("bio"):
        person["description"] = r["bio"]
    org = {
        "@type": "Organization",
        "@id": f"{url}#org",
        "name": r["company"],
        "founder": {"@id": f"{url}#person"},
        "foundingLocation": {"@type": "Place", "name": "Philippines"},
    }
    if r.get("company_url"):
        org["url"] = r["company_url"]
    if r.get("industry"):
        org["knowsAbout"] = [r["industry"]]
    page = {
        "@type": "ProfilePage",
        "@id": f"{url}#page",
        "name": f"{r['name']} — {r['role']} at {r['company']}",
        "url": url,
        "isPartOf": {"@id": f"{base}/#directory"},
        "about": {"@id": f"{url}#person"},
    }
    if r.get("bio"):
        page["description"] = r["bio"]
    nodes = [page, person, org]
    if r.get("funding_stage"):
        nodes.append({
            "@type": "PropertyValue",
            "@id": f"{url}#funding",
            "name": "fundingStage",
            "value": r["funding_stage"],
            "subjectOf": {"@id": f"{url}#org"},
        })
    return {"@context": "https://schema.org", "@graph": nodes}


PROFILE_CSS = """:root{--ink:#16140f;--beige:#f5f5ee;--line:#e5e0d2;--muted:#6b675e;--brand:#fb651e}
*{box-sizing:border-box}html,body{margin:0;padding:0}
body{font-family:Outfit,ui-sans-serif,system-ui,sans-serif;color:var(--ink);background:#fff;-webkit-font-smoothing:antialiased}
.wrap{max-width:760px;margin:0 auto;padding:48px 16px 64px}
.crumb{font-size:13px;color:var(--muted);margin-bottom:16px}.crumb a{color:var(--brand)}
h1{font-family:"Source Serif 4",serif;font-weight:500;font-size:clamp(2rem,5vw,3rem);margin:0 0 4px}
.role{font-size:17px;color:#333}.meta{margin:16px 0;font-size:14px;color:var(--muted)}
.bio{font-size:16px;line-height:1.6}.pill{display:inline-block;font-size:12px;border:1px solid var(--line);background:var(--beige);border-radius:999px;padding:2px 10px;margin-right:6px}
.back{display:inline-block;margin-top:32px;color:var(--brand);font-size:14px}"""


def profile_html(base, r):
    url = f"{base}/{r['slug']}/"
    ld = json.dumps(profile_ld(base, r), ensure_ascii=False)
    title = f"{r['name']} — {r['role']} at {r['company']} | Labyu"
    desc = r.get("bio") or f"{r['name']}, {r['role']} at {r['company']} ({r['industry']}, {r['location']})."
    crumbs = (
        '<nav class="crumb" aria-label="Breadcrumb">'
        f'<a href="{base}/">Filipino Founders</a> › {esc(r["name"])}</nav>'
    )
    pills = "".join(f'<span class="pill">{esc(x)}</span>' for x in [r.get("batch"), r.get("funding_stage"), r["industry"], r["location"]] if x)
    same = "".join(
        f'<div><a href="{esc(v)}">{esc(k)}</a></div>'
        for k, v in (r.get("links") or {}).items()
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{esc(url)}">
<meta property="og:type" content="profile">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{esc(url)}">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="{esc(title)}">
<meta name="twitter:description" content="{esc(desc)}">
<script type="application/ld+json">
{ld}
</script>
<link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:ital,opsz,wght@0,8..60,200..900;1,8..60,200..900&family=Outfit:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>{PROFILE_CSS}</style>
</head>
<body>
<main class="wrap">
<article>
{crumbs}
<h1>{esc(r["name"])}</h1>
<div class="role">{esc(r["role"])} at {esc(r["company"])}</div>
<div class="meta">{pills}</div>
<p class="bio">{esc(desc)}</p>
{same}
<a class="back" href="{base}/">← All Filipino founders</a>
</article>
</main>
</body>
</html>
"""


def directory_ld(base, records):
    items = [
        {
            "@type": "ListItem",
            "position": i + 1,
            "name": r["name"],
            "url": f"{base}/{r['slug']}/",
        }
        for i, r in enumerate(records)
    ]
    return {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "CollectionPage",
                "@id": f"{base}/#directory",
                "name": "Labyu — Filipino Founders Directory",
                "url": f"{base}/",
                "description": "A directory of Filipino builders — search by place, industry, role, or company.",
                "isPartOf": {"@type": "WebSite", "name": "Alien Inc", "url": "https://alieninc.tech"},
            },
            {
                "@type": "ItemList",
                "@id": f"{base}/#founders",
                "name": "Filipino founders",
                "numberOfItems": len(records),
                "itemListElement": items,
            },
        ],
    }


CARD_TPL = ('      <a class="card" href="./{slug}/"><div class="ava">{initials}</div>'
            '<div><div class="cname">{name}</div><div class="cdesc">{role} at {company}'
            '<div>{pills}</div></div></div></a>')


def cards_html(records):
    out = []
    for r in records:
        pills = " ".join(
            f'<span class="pill">{esc(x)}</span>'
            for x in [r.get("batch"), r["industry"]] if x
        )
        out.append(CARD_TPL.format(
            slug=esc(r["slug"]), initials=esc(initials(r["name"])),
            name=esc(r["name"]), role=esc(r["role"]),
            company=esc(r["company"]), pills=pills,
        ))
    return "\n".join(out)


def patch_index(base, records, dry=False):
    src = INDEX.read_text(encoding="utf-8")
    orig = src

    # 1. Ensure canonical + OG/Twitter/description meta (insert after viewport if missing).
    if 'rel="canonical"' not in src:
        src = src.replace(
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f'<link rel="canonical" href="{base}/">\n'
            '<meta name="description" content="Labyu — a directory of Filipino builders. Search by place, industry, role, or company.">\n'
            '<meta property="og:type" content="website">\n'
            '<meta property="og:site_name" content="Labyu">\n'
            '<meta property="og:title" content="Labyu — Filipino Founders Directory">\n'
            '<meta property="og:description" content="A directory of Filipino builders — search by place, industry, role, or company.">\n'
            f'<meta property="og:url" content="{base}/">\n'
            '<meta name="twitter:card" content="summary">\n'
            '<meta name="twitter:title" content="Labyu — Filipino Founders Directory">\n'
            '<meta name="twitter:description" content="A directory of Filipino builders — search by place, industry, role, or company.">',
            1,
        )

    # 2. Ensure/refresh directory JSON-LD block (id-anchored so rebuilds are idempotent).
    ld = json.dumps(directory_ld(base, records), ensure_ascii=False)
    block = f'<script type="application/ld+json" id="labyu-directory-ld">\n{ld}\n</script>'
    if 'id="labyu-directory-ld"' in src:
        src = re.sub(r'<script type="application/ld\+json" id="labyu-directory-ld">.*?</script>',
                     lambda _: block, src, count=1, flags=re.S)
    else:
        src = src.replace("</title>", "</title>\n" + block, 1)

    # 3. Rebuild cards + count from JSON (single source of truth).
    cards = cards_html(records)
    if '<div class="cards">' in src:
        src = re.sub(r'(<div class="cards">).*?(</div>\s*</main>)',
                     lambda m: m.group(1) + "\n" + cards + "\n    " + m.group(2),
                     src, count=1, flags=re.S)
    src = re.sub(r'Showing \d+ of \d+ founders',
                 f'Showing {len(records)} of {len(records)} founders', src)

    # 4. Retitle to Labyu (future domain name), keep visible H1 for now.
    if "<title>Filipino Founders Directory</title>" in src:
        src = src.replace("<title>Filipino Founders Directory</title>",
                          "<title>Labyu — Filipino Founders Directory</title>", 1)
    if dry:
        return src
    if src != orig:
        INDEX.write_text(src, encoding="utf-8")
    return src


def build(base, out_root=LABYU):
    records = load()
    # profiles
    for r in records:
        d = out_root / r["slug"]
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(profile_html(base, r), encoding="utf-8")
    # prune stale slug dirs (only ones that look generated: contain index.html with labyu marker)
    slugs = {r["slug"] for r in records}
    for child in out_root.iterdir():
        if child.is_dir() and child.name not in slugs:
            idx = child / "index.html"
            if idx.exists() and "#person" in idx.read_text(encoding="utf-8", errors="ignore"):
                shutil.rmtree(child)
    # sitemap
    urlset = ET.Element("urlset", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")
    for loc in [f"{base}/"] + [f"{base}/{r['slug']}/" for r in records]:
        u = ET.SubElement(urlset, "url")
        ET.SubElement(u, "loc").text = loc
        ET.SubElement(u, "changefreq").text = "monthly"
    tree = ET.ElementTree(urlset)
    ET.indent(tree, space="  ")
    tree.write(out_root / "sitemap-founders.xml", encoding="utf-8", xml_declaration=True)
    # llms.txt
    lines = ["# Labyu — Filipino Founders Directory", f"# {base}/", ""]
    for r in records:
        bits = [r["role"] + " at " + r["company"], r["industry"], r["location"]]
        if r.get("funding_stage"):
            bits.append(r["funding_stage"])
        lines.append(f"- {r['name']} — {', '.join(bits)}: {base}/{r['slug']}/")
    (out_root / "llms.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    patch_index(base, records)
    # validate: every generated profile parses as JSON-LD with 3+ nodes
    for r in records:
        txt = (out_root / r["slug"] / "index.html").read_text(encoding="utf-8")
        m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>', txt, re.S)
        doc = json.loads(m.group(1))
        assert len(doc.get("@graph", [])) >= 3, r["slug"]
    return records


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    base = args.base.rstrip("/")
    if args.check:
        records = load()
        with tempfile.TemporaryDirectory() as tmp:
            # profiles/sitemap/llms into temp; index patch compared as string
            tmp_root = pathlib.Path(tmp)
            build(base, out_root=tmp_root)
            got_index = patch_index(base, records, dry=True)
            want_index = INDEX.read_text(encoding="utf-8")
            if got_index != want_index:
                print("DRIFT: labyu/index.html is stale — run tools/build-founders.py", file=sys.stderr)
                return 1
            # compare generated files
            for r in records:
                got = (tmp_root / r["slug"] / "index.html").read_text()
                want_p = LABYU / r["slug"] / "index.html"
                if not want_p.exists() or want_p.read_text() != got:
                    print(f"DRIFT: labyu/{r['slug']}/index.html stale", file=sys.stderr)
                    return 1
            for f in ("sitemap-founders.xml", "llms.txt"):
                if (tmp_root / f).read_text() != (LABYU / f).read_text():
                    print(f"DRIFT: labyu/{f} stale", file=sys.stderr)
                    return 1
        print(f"OK: labyu/ in sync ({len(records)} founders)")
        return 0
    records = build(base)
    print(f"Built labyu/: {len(records)} profiles + sitemap-founders.xml + llms.txt (base {base}/)")


if __name__ == "__main__":
    sys.exit(main())
