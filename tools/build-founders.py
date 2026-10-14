#!/usr/bin/env python3
"""Build Labyu (Filipino Founders Directory) static pages + discovery files.

Sources of truth: labyu/founders.json, labyu/companies.json
Outputs (deterministic, static-hosting safe):
  labyu/c/<company>/index.html   one per COMPANY, YC company-page design language:
                                 header pills, Company/Founders tabs, about prose,
                                 fact sidebar card, founders section
                                 (WebPage + Organization + Person JSON-LD @graph)
  labyu/<slug>/index.html        one per founder, links up to its company page
  labyu/sitemap-founders.xml     index + every company + founder URL
  labyu/llms.txt                 companies + founders, one line each
  labyu/index.html               patched in place: canonical/OG + directory JSON-LD + cards
                                 (cards point at company pages; page shell untouched)

Usage:
  python3 tools/build-founders.py            # build
  python3 tools/build-founders.py --check    # CI: rebuild to temp and diff (fail on drift)

Future domain: Labyu will move to its own domain. Override with --base.
"""
import argparse
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
FOUNDERS_JSON = LABYU / "founders.json"
COMPANIES_JSON = LABYU / "companies.json"
INDEX = LABYU / "index.html"
DEFAULT_BASE = "https://alieninc.tech/labyu"

REQUIRED_F = ["slug", "name", "role", "company", "company_slug", "industry", "location"]
REQUIRED_C = ["slug", "name", "tagline", "status", "location"]
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FONTS = ("https://fonts.googleapis.com/css2?family=Source+Serif+4:ital,opsz,wght@0,8..60,200..900"
         ";1,8..60,200..900&family=Outfit:wght@300;400;500;600;700&display=swap")


def load():
    founders = json.loads(FOUNDERS_JSON.read_text(encoding="utf-8"))
    companies = json.loads(COMPANIES_JSON.read_text(encoding="utf-8"))
    assert founders and companies, "founders.json and companies.json must be non-empty lists"
    cslugs = set()
    for i, c in enumerate(companies):
        for f in REQUIRED_C:
            if not str(c.get(f, "")).strip():
                raise ValueError(f"company #{i} missing required field: {f}")
        if not SLUG_RE.match(c["slug"]) or c["slug"] in cslugs:
            raise ValueError(f"bad/duplicate company slug: {c['slug']!r}")
        cslugs.add(c["slug"])
    seen = set()
    for i, r in enumerate(founders):
        for f in REQUIRED_F:
            if not str(r.get(f, "")).strip():
                raise ValueError(f"founder #{i} missing required field: {f}")
        if not SLUG_RE.match(r["slug"]) or r["slug"] in seen:
            raise ValueError(f"bad/duplicate founder slug: {r['slug']!r}")
        seen.add(r["slug"])
        if r["company_slug"] not in cslugs:
            raise ValueError(f"founder {r['slug']} references unknown company: {r['company_slug']}")
    by_company = {}
    for r in founders:
        by_company.setdefault(r["company_slug"], []).append(r)
    return founders, companies, by_company


def esc(s):
    return html.escape(str(s or ""), quote=True)


def initials(name):
    parts = [p for p in str(name).split() if p]
    return ("".join(p[0] for p in parts[:2]) or "?").upper()


# ---------------------------------------------------------------- YC-style company page

# Pills: uppercase 10px letterspaced chips on #E6E4DC;
# status pill carries the green dot.
CO_CSS = """:root{--ink:#16140f;--beige:#f5f5ee;--line:#e5e0d2;--muted:#6b675e;--brand:#fb651e;--page-max:1280px}
*{box-sizing:border-box}html,body{margin:0;padding:0}
body{font-family:Outfit,ui-sans-serif,system-ui,sans-serif;color:var(--ink);background:#fff;-webkit-font-smoothing:antialiased}
a{color:inherit}
.topnav{position:sticky;top:0;z-index:50;background:var(--beige)}
.nav-mobile{display:flex;align-items:center;justify-content:center;padding:8px;position:relative;background:var(--beige)}
.nav-desktop{display:none;align-items:center;justify-content:center;padding:12px 20px;background:var(--beige);position:relative}
@media(min-width:1200px){.nav-mobile{display:none}.nav-desktop{display:flex}}
@media(max-width:1199px){.nav-desktop{display:none!important}}
.logo-mark{width:40px;height:40px;margin:4px 0;border-radius:6px;overflow:hidden;display:inline-block;flex-shrink:0;text-decoration:none;line-height:0}
.logo-mark img{width:100%;height:100%;object-fit:cover;display:block}
.nav-inner{width:100%;max-width:1400px;display:flex;align-items:center;gap:24px}
.nav-group{display:flex;flex:1 1 0;align-items:center;gap:16px;min-width:0}
.nav-group.left{justify-content:flex-end}.nav-group.right{justify-content:flex-start}
.nav-link{font-size:15px;text-decoration:none;white-space:nowrap}
.wrap{max-width:var(--page-max);margin:0 auto;padding:16px 16px 64px}
.crumb{display:flex;align-items:center;gap:6px;font-size:13px;color:var(--muted);padding:8px 0 16px}
.crumb a{color:var(--brand);text-decoration:none}
.co{display:flex;gap:32px;align-items:flex-start}
.main{flex:1;min-width:0}
.side{width:300px;flex-shrink:0}
@media(max-width:900px){.co{flex-direction:column}.side{width:100%}}
.co-head{display:flex;gap:16px;align-items:flex-start}
.co-logo{width:64px;height:64px;border-radius:12px;background:#d9d5ca;flex-shrink:0;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:20px;margin-top:8px;overflow:hidden}
.co-name{font-size:24px;font-weight:500;margin:0}
.co-tag{font-size:18px;font-weight:300;margin:4px 0 8px}
.pills{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.ypill{display:inline-flex;align-items:center;gap:5px;background:#E6E4DC;border-radius:3px;padding:2px 5px;font-size:10px;text-transform:uppercase;letter-spacing:.08em;text-decoration:none;color:var(--ink)}
.dot{width:8px;height:8px;border-radius:50%;background:#22c55e;margin-right:6px}
.tabs{display:flex;justify-content:space-between;align-items:center;border-top:1px solid var(--line);border-bottom:1px solid var(--line);margin-top:16px}
.tabnav{display:flex;gap:24px}
.tab{display:inline-block;padding:20px 12px;text-decoration:none;color:#334155;font-size:15px}
.tab.active{font-weight:700;color:var(--ink)}
.badge{display:inline-block;margin-left:4px;padding:0 6px;font-size:12px;font-weight:700}
.sitelink{font-size:14px;color:var(--brand);text-decoration:none;white-space:nowrap}
.prose{font-size:16px;line-height:1.65;max-width:100%;white-space:pre-line}
.sect{font-size:24px;font-weight:700;color:#333;margin:24px 0 8px}
.card{border:1px solid var(--line);border-radius:12px;background:#fff;padding:16px}
.card .clogo{max-width:140px;margin:8px auto 12px;display:flex;align-items:center;justify-content:center;height:64px;border-radius:12px;background:var(--beige);font-weight:700;font-size:24px}
.fact{display:flex;justify-content:space-between;font-size:14px;padding:6px 0}
.fact span:first-child{color:var(--muted)}
.frow{display:flex;gap:8px;padding-top:8px}
.fcard{display:flex;gap:12px;padding:12px 0;border-top:1px solid var(--line)}
.fava{width:64px;height:64px;border-radius:12px;background:#d9d5ca;flex-shrink:0;display:flex;align-items:center;justify-content:center;font-weight:700;overflow:hidden}
.fname{font-weight:700;font-size:18px}.fname a{text-decoration:none}
.frole{font-size:14px;color:#4b5563;padding-top:2px}
footer{background:#000;color:var(--beige);margin-top:48px}
.f-inner{max-width:var(--page-max);margin:0 auto;padding:48px 24px;display:flex;gap:48px}
@media(max-width:768px){.f-inner{flex-direction:column}}
.f-bottom{max-width:var(--page-max);margin:0 auto;padding:24px;display:flex;justify-content:space-between;border-top:1px solid #333;font-size:14px;font-weight:300}"""


def yc_description(c, founders):
    """YC-pattern meta sentence: tagline + founded-by + headcount + hiring line."""
    names = ", ".join(f["name"] for f in founders)
    bits = [c["tagline"]]
    if c.get("founded"):
        bits.append(f"Founded in {c['founded']} by {names}, {c['name']} is based in {c['location']}.")
    else:
        bits.append(f"Founded by {names}, {c['name']} is based in {c['location']}.")
    return " ".join(bits)


def company_ld(base, c, founders):
    url = f"{base}/c/{c['slug']}/"
    people = []
    for f in founders:
        p = {
            "@type": "Person",
            "@id": f"{base}/{f['slug']}/#person",
            "name": f["name"],
            "jobTitle": f"{f['role']} at {c['name']}",
            "worksFor": {"@id": f"{url}#org"},
            "url": f"{base}/{f['slug']}/",
        }
        if f.get("bio"):
            p["description"] = f["bio"]
        people.append(p)
    org = {
        "@type": "Organization",
        "@id": f"{url}#org",
        "name": c["name"],
        "url": c.get("website") or url,
        "description": c.get("description") or c["tagline"],
        "foundingLocation": {"@type": "Place", "name": "Philippines"},
        "founder": [{"@id": f"{base}/{f['slug']}/#person"} for f in founders],
        "knowsAbout": c.get("industries", []),
    }
    if c.get("founded"):
        org["foundingDate"] = c["founded"]
    same = [v for v in (c.get("links") or {}).values() if v]
    if same:
        org["sameAs"] = same
    page = {
        "@type": "ProfilePage",
        "@id": f"{url}#page",
        "name": f"{c['name']}: {c['tagline']}",
        "url": url,
        "description": yc_description(c, founders),
        "isPartOf": {"@id": f"{base}/#directory"},
        "about": {"@id": f"{url}#org"},
    }
    return {"@context": "https://schema.org", "@graph": [page, org] + people}


def pills_html(c):
    parts = []
    if c.get("status"):
        parts.append(f'<span class="ypill"><span class="dot"></span>{esc(c["status"])}</span>')
    for ind in c.get("industries", []):
        parts.append(f'<span class="ypill">{esc(ind)}</span>')
    if c.get("location"):
        parts.append(f'<span class="ypill">{esc(c["location"])}</span>')
    return "".join(parts)


def company_html(base, c, founders):
    url = f"{base}/c/{c['slug']}/"
    ld = json.dumps(company_ld(base, c, founders), ensure_ascii=False)
    title = f"{c['name']}: {c['tagline']} | Labyu"
    desc = yc_description(c, founders)
    facts = []
    if c.get("founded"):
        facts.append(("Founded:", c["founded"]))
    facts += [("Status:", c["status"]), ("Location:", c["location"])]
    if c.get("industries"):
        facts.append(("Industry:", ", ".join(c["industries"])))
    fact_rows = "".join(
        f'<div class="fact"><span>{esc(k)}</span><span>{esc(v)}</span></div>' for k, v in facts)
    fcards = ""
    for f in founders:
        li = ""
        if (f.get("links") or {}).get("linkedin"):
            li = (f'<a href="{esc(f["links"]["linkedin"])}" rel="nofollow" target="_blank" '
                  f'aria-label="{esc(f["name"])} on LinkedIn">in</a>')
        fcards += (
            f'<div class="fcard"><div class="fava">{esc(initials(f["name"]))}</div>'
            f'<div><div class="fname"><a href="{base}/{esc(f["slug"])}/">{esc(f["name"])}</a> {li}</div>'
            f'<div class="frole">{esc(f["role"])}</div></div></div>')
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="title" content="{esc(title)}">
<meta name="description" content="{esc(desc)}">
<meta name="robots" content="follow">
<link rel="canonical" href="{esc(url)}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Labyu">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{esc(url)}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{esc(title)}">
<meta name="twitter:description" content="{esc(desc)}">
<script type="application/ld+json">
{ld}
</script>
<link rel="icon" type="image/png" sizes="32x32" href="../../favicon-32.png?v=2">
<link href="{FONTS}" rel="stylesheet">
<style>{CO_CSS}</style>
</head>
<body>
<div class="topnav">
  <nav class="nav-mobile"><a class="logo-mark" href="{base}/" aria-label="home"><img src="../../logo.png" alt="logo"></a></nav>
  <nav class="nav-desktop"><div class="nav-inner">
    <div class="nav-group left"><a class="nav-link" href="{base}/">Directory</a><a class="nav-link" href="{base}/">Companies</a></div>
    <a class="logo-mark" href="{base}/" aria-label="home"><img src="../../logo.png" alt="logo"></a>
    <div class="nav-group right"><a class="nav-link" href="{base}/">Founders</a><a class="nav-link" href="{base}/">About</a></div>
  </div></nav>
</div>
<div class="wrap">
<nav class="crumb" aria-label="Breadcrumb"><a href="{base}/">Filipino Founders</a><span>›</span><span>{esc(c["name"])}</span></nav>
<div class="co">
<div class="main">
  <article>
  <div class="co-head">
    <div class="co-logo">{esc(initials(c["name"]))}</div>
    <div><h1 class="co-name">{esc(c["name"])}</h1>
    <div class="co-tag">{esc(c["tagline"])}</div>
    <div class="pills">{pills_html(c)}</div></div>
  </div>
  <div class="tabs">
    <nav class="tabnav"><a class="tab active" href="#about">Company</a><a class="tab" href="#founders">Founders</a><span class="tab"><span class="badge">{len(founders)}</span></span></nav>
    <a class="sitelink" href="{esc(c.get("website", ""))}" target="_blank" rel="noopener">↗ {esc(c.get("website", "").replace("https://", ""))}</a>
  </div>
  <section id="about"><div class="prose">{esc(c.get("description") or desc)}</div></section>
  <section id="founders"><h2 class="sect">Founders</h2>{fcards}</section>
  </article>
</div>
<aside class="side">
  <div class="card">
    <div class="clogo">{esc(initials(c["name"]))}</div>
    <div style="font-size:20px;font-weight:500;text-align:center">{esc(c["name"])}</div>
    <div style="padding-top:12px">{fact_rows}</div>
  </div>
</aside>
</div>
</div>
<footer><div class="f-inner"><div><span class="logo-mark"><img src="../../logo.png" alt="logo"></span><div style="margin-top:12px;font-weight:300">Labyu — a directory of Filipino builders.</div></div></div>
<div class="f-bottom"><span>© 2026 Labyu</span><span><a href="{base}/" style="text-decoration:none">All companies</a></span></div></footer>
</body>
</html>
"""


# ---------------------------------------------------------------- founder page (links up to company)

PROFILE_CSS = """:root{--ink:#16140f;--beige:#f5f5ee;--line:#e5e0d2;--muted:#6b675e;--brand:#fb651e}
*{box-sizing:border-box}html,body{margin:0;padding:0}
body{font-family:Outfit,ui-sans-serif,system-ui,sans-serif;color:var(--ink);background:#fff;-webkit-font-smoothing:antialiased}
.wrap{max-width:760px;margin:0 auto;padding:48px 16px 64px}
.crumb{font-size:13px;color:var(--muted);margin-bottom:16px}.crumb a{color:var(--brand)}
h1{font-family:"Source Serif 4",serif;font-weight:500;font-size:clamp(2rem,5vw,3rem);margin:0 0 4px}
.role{font-size:17px;color:#333}.meta{margin:16px 0;font-size:14px;color:var(--muted)}
.bio{font-size:16px;line-height:1.6}.pill{display:inline-block;font-size:12px;border:1px solid var(--line);background:var(--beige);border-radius:999px;padding:2px 10px;margin-right:6px}
.cobox{margin-top:24px;border:1px solid var(--line);border-radius:12px;background:var(--beige);padding:16px}
.cobox a{color:var(--brand);font-weight:600;text-decoration:none}
.back{display:inline-block;margin-top:32px;color:var(--brand);font-size:14px}"""


def profile_ld(base, r):
    url = f"{base}/{r['slug']}/"
    courl = f"{base}/c/{r['company_slug']}/"
    person = {
        "@type": "Person", "@id": f"{url}#person", "name": r["name"],
        "jobTitle": f"{r['role']} at {r['company']}",
        "worksFor": {"@id": f"{courl}#org"},
        "homeLocation": {"@type": "Place", "name": r["location"]},
        "knowsAbout": [r["industry"]], "url": url,
    }
    same_as = [v for v in (r.get("links") or {}).values() if v]
    if same_as:
        person["sameAs"] = same_as
    if r.get("bio"):
        person["description"] = r["bio"]
    org = {
        "@type": "Organization", "@id": f"{courl}#org", "name": r["company"],
        "founder": {"@id": f"{url}#person"},
        "foundingLocation": {"@type": "Place", "name": "Philippines"},
    }
    if r.get("company_url"):
        org["url"] = r["company_url"]
    page = {
        "@type": "ProfilePage", "@id": f"{url}#page",
        "name": f"{r['name']} — {r['role']} at {r['company']}",
        "url": url, "isPartOf": {"@id": f"{base}/#directory"},
        "about": {"@id": f"{url}#person"},
    }
    nodes = [page, person, org]
    if r.get("funding_stage"):
        nodes.append({"@type": "PropertyValue", "@id": f"{url}#funding",
                      "name": "fundingStage", "value": r["funding_stage"],
                      "subjectOf": {"@id": f"{courl}#org"}})
    return {"@context": "https://schema.org", "@graph": nodes}


def profile_html(base, r, companies_by_slug):
    url = f"{base}/{r['slug']}/"
    c = companies_by_slug[r["company_slug"]]
    courl = f"{base}/c/{c['slug']}/"
    ld = json.dumps(profile_ld(base, r), ensure_ascii=False)
    title = f"{r['name']} — {r['role']} at {r['company']} | Labyu"
    desc = r.get("bio") or f"{r['name']}, {r['role']} at {r['company']}."
    pills = "".join(f'<span class="pill">{esc(x)}</span>'
                    for x in [r.get("funding_stage"), r["industry"], r["location"]] if x)
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
<script type="application/ld+json">
{ld}
</script>
<link href="{FONTS}" rel="stylesheet">
<style>{PROFILE_CSS}</style>
</head>
<body>
<main class="wrap">
<article>
<nav class="crumb" aria-label="Breadcrumb"><a href="{base}/">Filipino Founders</a> › <a href="{courl}">{esc(c["name"])}</a> › {esc(r["name"])}</nav>
<h1>{esc(r["name"])}</h1>
<div class="role">{esc(r["role"])} at {esc(r["company"])}</div>
<div class="meta">{pills}</div>
<p class="bio">{esc(desc)}</p>
<div class="cobox"><div style="font-size:20px;font-weight:500">{esc(c["name"])}</div>
<div style="margin:4px 0 8px">{esc(c["tagline"])}</div>
<a href="{courl}">View company →</a></div>
<a class="back" href="{base}/">← All Filipino founders</a>
</article>
</main>
</body>
</html>
"""


# ---------------------------------------------------------------- directory

def directory_ld(base, companies):
    items = [{"@type": "ListItem", "position": i + 1, "name": c["name"],
              "url": f"{base}/c/{c['slug']}/"} for i, c in enumerate(companies)]
    return {"@context": "https://schema.org", "@graph": [
        {"@type": "CollectionPage", "@id": f"{base}/#directory",
         "name": "Labyu — Filipino Founders Directory", "url": f"{base}/",
         "description": "A directory of Filipino builders — search by place, industry, role, or company.",
         "isPartOf": {"@type": "WebSite", "name": "Alien Inc", "url": "https://alieninc.tech"}},
        {"@type": "ItemList", "@id": f"{base}/#companies", "name": "Filipino startups",
         "numberOfItems": len(companies), "itemListElement": items}]}


CARD_TPL = ('      <a class="card" href="./c/{cslug}/"><div class="ava">{initials}</div>'
            '<div><div class="cname">{name}</div><div class="cdesc">{role} at {company}'
            '<div>{pills}</div></div></div></a>')


def cards_html(records):
    out = []
    for r in records:
        pills = " ".join(f'<span class="pill">{esc(x)}</span>'
                         for x in [r["industry"]] if x)
        out.append(CARD_TPL.format(
            cslug=esc(r["company_slug"]), initials=esc(initials(r["name"])),
            name=esc(r["name"]), role=esc(r["role"]),
            company=esc(r["company"]), pills=pills))
    return "\n".join(out)


def patch_index(base, records, companies, dry=False):
    src = INDEX.read_text(encoding="utf-8")
    orig = src
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
            1)
    ld = json.dumps(directory_ld(base, companies), ensure_ascii=False)
    block = f'<script type="application/ld+json" id="labyu-directory-ld">\n{ld}\n</script>'
    if 'id="labyu-directory-ld"' in src:
        src = re.sub(r'<script type="application/ld\+json" id="labyu-directory-ld">.*?</script>',
                     lambda _: block, src, count=1, flags=re.S)
    else:
        src = src.replace("</title>", "</title>\n" + block, 1)
    cards = cards_html(records)
    if '<div class="cards">' in src:
        src = re.sub(r'(<div class="cards">).*?(</div>\s*</main>)',
                     lambda m: m.group(1) + "\n" + cards + "\n    " + m.group(2),
                     src, count=1, flags=re.S)
    src = re.sub(r'Showing \d+ of \d+ founders',
                 f'Showing {len(records)} of {len(records)} founders', src)
    if "<title>Filipino Founders Directory</title>" in src:
        src = src.replace("<title>Filipino Founders Directory</title>",
                          "<title>Labyu — Filipino Founders Directory</title>", 1)
    if dry:
        return src
    if src != orig:
        INDEX.write_text(src, encoding="utf-8")
    return src


# ---------------------------------------------------------------- build

def build(base, out_root=LABYU):
    founders, companies, by_company = load()
    cby = {c["slug"]: c for c in companies}
    for c in companies:
        d = out_root / "c" / c["slug"]
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(
            company_html(base, c, by_company.get(c["slug"], [])), encoding="utf-8")
    for r in founders:
        d = out_root / r["slug"]
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(profile_html(base, r, cby), encoding="utf-8")
    # prune stale generated dirs (company + founder pages carry #org/#person markers)
    keep = {r["slug"] for r in founders} | {"c"}
    for child in out_root.iterdir():
        if child.is_dir() and child.name not in keep and child.name not in (
                "c",):
            idx = child / "index.html"
            if idx.exists() and ("#person" in idx.read_text(encoding="utf-8", errors="ignore")):
                shutil.rmtree(child)
    cdir = out_root / "c"
    if cdir.exists():
        for child in cdir.iterdir():
            if child.is_dir() and child.name not in {c["slug"] for c in companies}:
                shutil.rmtree(child)
    urlset = ET.Element("urlset", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")

    def add(loc, freq):
        u = ET.SubElement(urlset, "url")
        ET.SubElement(u, "loc").text = loc
        ET.SubElement(u, "changefreq").text = freq

    add(f"{base}/", "weekly")
    for c in companies:
        add(f"{base}/c/{c['slug']}/", "weekly")
    for r in founders:
        add(f"{base}/{r['slug']}/", "monthly")
    tree = ET.ElementTree(urlset)
    ET.indent(tree, space="  ")
    tree.write(out_root / "sitemap-founders.xml", encoding="utf-8", xml_declaration=True)
    lines = ["# Labyu — Filipino Founders Directory", f"# {base}/", "", "## Companies", ""]
    for c in companies:
        lines.append(f"- {c['name']}: {c['tagline']} {base}/c/{c['slug']}/")
    lines += ["", "## Founders", ""]
    for r in founders:
        lines.append(f"- {r['name']} — {r['role']} at {r['company']}: {base}/{r['slug']}/")
    (out_root / "llms.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    patch_index(base, founders, companies)
    for c in companies:
        txt = (out_root / "c" / c["slug"] / "index.html").read_text(encoding="utf-8")
        m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>', txt, re.S)
        doc = json.loads(m.group(1))
        assert len(doc.get("@graph", [])) >= 2 + len(by_company.get(c["slug"], [])), c["slug"]
    return founders, companies


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    base = args.base.rstrip("/")
    if args.check:
        founders, companies, _ = load()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = pathlib.Path(tmp)
            build(base, out_root=tmp_root)
            got_index = patch_index(base, founders, companies, dry=True)
            if got_index != INDEX.read_text(encoding="utf-8"):
                print("DRIFT: labyu/index.html is stale — run tools/build-founders.py",
                      file=sys.stderr)
                return 1

            def cmp_tree(rel):
                got = (tmp_root / rel).read_text()
                want_p = LABYU / rel
                if not want_p.exists() or want_p.read_text() != got:
                    print(f"DRIFT: labyu/{rel} stale", file=sys.stderr)
                    return False
                return True

            ok = True
            for c in companies:
                ok &= cmp_tree(f"c/{c['slug']}/index.html")
            for r in founders:
                ok &= cmp_tree(f"{r['slug']}/index.html")
            for f in ("sitemap-founders.xml", "llms.txt"):
                ok &= cmp_tree(f)
            if not ok:
                return 1
        print(f"OK: labyu/ in sync ({len(companies)} companies, {len(founders)} founders)")
        return 0
    founders, companies = build(base)
    print(f"Built labyu/: {len(companies)} companies + {len(founders)} founders "
          f"+ sitemap-founders.xml + llms.txt (base {base}/)")


if __name__ == "__main__":
    sys.exit(main())
