#!/usr/bin/env python3
"""Fetch verified company logos for Labyu: title-match + touch-icon-first.

For every company with a candidate domain:
  1. Download the homepage, check the <title> actually mentions the company
     (this rejects wrong-company domains like the orangeandbronze.com incident).
  2. Prefer apple-touch-icon (180px, real brand mark) over favicon-service icons.
  3. Save to labyu/logos/<slug>.<ext>; report grade + size for review.

Usage:
  python3 tools/fetch-logos.py                # probe + download, report only
  python3 tools/fetch-logos.py --apply        # also write "logo" fields into companies.json

After --apply: run tools/build-founders.py, then tools/generate-sitemap.py.
"""
import json
import pathlib
import re
import sys
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
LABYU = ROOT / "labyu"
LOGOS = LABYU / "logos"
COMPANIES_JSON = LABYU / "companies.json"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) LabyuDirectory/1.0"}

# slug -> candidate official domain (researched; title-match gate decides).
CANDIDATES = {
    # verified official domains (from prior research)
    "paymongo": "paymongo.com", "nextpay": "nextpay.ph", "alien-inc": "alieninc.tech",
    "kumu": "kumu.ph", "kalibrr": "kalibrr.com", "coins-ph": "coins.ph",
    "pdax": "pdax.ph", "ayannah": "ayannah.com", "converge": "convergeict.com",
    "xurpas": "xurpas.com", "expedock": "expedock.com", "taxumo": "taxumo.com",
    "moneybees": "moneybees.ph", "prosperna": "prosperna.com",
    "multisys": "multisyscorp.com", "bloomx": "bx8.io", "edukasyon": "edukasyon.ph",
    "beautymnl": "beautymnl.com", "dragonpay": "dragonpay.ph",
    "eskwelabs": "eskwelabs.com", "agrabah": "agrabah.ph",
    "packworks": "packworks.io", "thinking-machines": "thinkingmachin.es",
    "hoppler": "hoppler.com.ph", "zipmatch": "zipmatch.com",
    "cherry": "cherryshop.com.ph", "sunnies": "sunniesstudios.com",
    "mayani": "mayani.ph", "kwik-insure": "kwik.insure", "aide": "aide-app.com",
    "plentina": "plentina.com",
    # best-guess candidates (title-match gate decides; rejects are expected)
    "voyager": "voyager.com.ph", "sarisuki": "sarisuki.ph", "sprout": "sprout.ph",
    "invested": "invested.ph", "chatgenie": "chatgenie.ph", "sulit": "sulit.com.ph",
    "tier-one": "tier.one", "ygg": "yieldguild.io", "virtualahan": "virtualahan.com",
    "rags2riches": "rags2riches.ph", "cropital": "cropital.com",
    "human-nature": "humanheartnature.com", "messy-bessy": "messybessy.com",
    "anthill": "anthillfabricgallery.com", "team-manila": "teammanila.com",
    "plus63": "plus63.com", "cloudeats": "cloudeats.com", "kravers": "kravers.ph",
    "mober": "mober.ph", "talino": "talino.io", "sci-ventures": "sciventures.com",
    "nexplay": "nexplay.gg", "acadarena": "acadarena.com",
    "whitecloak": "whitecloak.com", "theo-philo": "theoandphilo.com",
    "engkanto": "engkantobrewery.com", "mineski": "mineski.net",
    "bren": "brenesports.com", "traxion": "traxion.tech", "growsari": "growsari.com",
    "pawnhero": "pawnhero.ph", "peddlr": "peddlr.ph",
    "happy-skin": "happyskin.com", "vice-cosmetics": "vicecosmetics.com.ph",
    "medgrocer": "medgrocer.com", "tnc": "tnc.com.ph",
}


# Domains press-verified but unreachable from this sandbox: favicon only,
# every one gets a visual check before wiring.
FAVICON_DIRECT = {"zipmatch": "zipmatch.com"}


def token(company_name):
    # First word, cut at dots so "Coins.ph" -> "coins" (not "coinsph").
    first = company_name.split()[0].split(".")[0]
    return re.sub(r"[^a-z0-9]", "", first.lower())


def get(url, timeout=25):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(), r.headers.get_content_type()


def title_of(html):
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def icon_links(html, base):
    found = []
    for m in re.finditer(
            r'<link[^>]+rel=["\']([^"\']*)["\'][^>]+href=["\']([^"\']+)["\']', html, re.I):
        rel, href = m.group(1).lower(), m.group(2)
        if "icon" not in rel:
            continue
        size_m = re.search(r"(\d+)\s*x\s*(\d+)", m.group(0))
        size = int(size_m.group(1)) if size_m else 0
        if "apple-touch" in rel:
            size = size or 180
            prio = 0
        else:
            prio = 1
        found.append((prio, -size, urllib.parse.urljoin(base, href)))
    found.sort()
    return [u for _, _, u in found]


def fetch_icon(url):
    try:
        data, ct = get(url)
    except Exception:
        return None, None
    if data[:4] == b"\x89PNG":
        return data, "png"
    if data[:2] == b"\xff\xd8":
        return data, "jpg"
    if data[:4] in (b"\x00\x00\x01\x00",):
        return data, "ico"
    if "image" in (ct or "") and len(data) > 800:
        return data, "png"
    return None, None


def process(slug, company):
    domain = CANDIDATES.get(slug)
    if not domain:
        return {"slug": slug, "status": "no-domain"}
    if slug in FAVICON_DIRECT:
        # Homepage unreachable from here but domain verified via press coverage;
        # favicon + mandatory visual check (see report grade).
        try:
            data, _ = get(f"https://www.google.com/s2/favicons?domain={domain}&sz=128")
            if data[:4] == b"\x89PNG" and len(data) >= 300:
                return save(slug, domain, "[press-verified]", data, "png",
                            "favicon-direct", "google-s2")
        except Exception:
            pass
        return {"slug": slug, "domain": domain, "status": "no-icon"}
    tok = token(company)
    try:
        raw, _ = get(f"https://{domain}/")
    except Exception as e:
        return {"slug": slug, "domain": domain, "status": f"fetch-fail: {type(e).__name__}"}
    try:
        html = raw.decode("utf-8", errors="ignore")
    except Exception:
        return {"slug": slug, "domain": domain, "status": "decode-fail"}
    title = title_of(html)
    # Strict gate: the brand must be in the <title>. A looser body-fallback
    # was tried and produced parked-domain junk, stock clipart, and a casino
    # logo — never weaken this without a visual check of every accept.
    if len(tok) < 3 or not re.search(rf"\b{re.escape(tok)}", title.lower()):
        return {"slug": slug, "domain": domain, "status": "title-reject",
                "title": title[:80]}
    for icon_url in icon_links(html, f"https://{domain}/"):
        data, ext = fetch_icon(icon_url)
        if data and len(data) >= 800 and ext in ("png", "jpg"):
            return save(slug, domain, title, data, ext, "touch-icon", icon_url)
    for probe in (f"https://{domain}/apple-touch-icon.png",):
        data, ext = fetch_icon(probe)
        if data and len(data) >= 800 and ext in ("png", "jpg"):
            return save(slug, domain, title, data, ext, "touch-probe", probe)
    try:
        data, _ = get(f"https://www.google.com/s2/favicons?domain={domain}&sz=128")
        if data[:4] == b"\x89PNG" and len(data) >= 300:
            return save(slug, domain, title, data, "png", "favicon", "google-s2")
    except Exception:
        pass
    return {"slug": slug, "domain": domain, "status": "no-icon", "title": title[:80]}


def save(slug, domain, title, data, ext, grade, src):
    LOGOS.mkdir(parents=True, exist_ok=True)
    for old in LOGOS.glob(slug + ".*"):
        old.unlink()
    path = LOGOS / f"{slug}.{ext}"
    path.write_bytes(data)
    return {"slug": slug, "domain": domain, "status": "ok", "grade": grade,
            "bytes": len(data), "file": f"logos/{slug}.{ext}", "title": title[:60]}


def main():
    apply = "--apply" in sys.argv
    companies = json.loads(COMPANIES_JSON.read_text(encoding="utf-8"))
    by_slug = {c["slug"]: c for c in companies}
    ok, rejected, failed = [], [], []
    for slug in sorted(by_slug):
        r = process(slug, by_slug[slug]["name"])
        print(f"{r['slug']:20s} {r.get('domain', '-'):28s} {r['status']:22s} "
              f"{r.get('grade', '')} {r.get('bytes', '')} {r.get('title', '')[:50]}")
        (ok if r["status"] == "ok" else
         rejected if r["status"] in ("title-reject", "no-domain") else failed).append(r)
    print(f"\nOK: {len(ok)} | rejected/no-domain: {len(rejected)} | failed/no-icon: {len(failed)}")
    if apply:
        for r in ok:
            by_slug[r["slug"]]["logo"] = r["file"]
            # Backfill verified official websites (never overwrite existing).
            if not by_slug[r["slug"]].get("website"):
                by_slug[r["slug"]]["website"] = f"https://{r['domain']}"
                by_slug[r["slug"]]["links"] = {"website": f"https://{r['domain']}"}
        COMPANIES_JSON.write_text(json.dumps(companies, ensure_ascii=False, indent=2) + "\n",
                                  encoding="utf-8")
        print(f"Wired {len(ok)} logo fields into companies.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
