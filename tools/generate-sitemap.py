#!/usr/bin/env python3
"""
Generate sitemap.xml for alieninc.tech + panteon.alieninc.tech
- Walks top-level *.html, articles/, panteon/**/*.html
- Uses git log last-mod or file mtime, outputs <lastmod> ISO 8601
- Priorities: / 1.0, /panteon/ 0.9, articles 0.8, product subpages 0.7
- Run in pages.yml before upload-pages-artifact
"""
import os, pathlib, datetime, subprocess, xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAGES_ROOT = ROOT / "_pages"  # generated at build time, but we generate for ROOT first
OUTPUT = ROOT / "sitemap.xml"

def git_lastmod(path: pathlib.Path):
    try:
        out = subprocess.check_output(
            ["git", "log", "-1", "--format=%cI", "--", str(path.relative_to(ROOT))],
            cwd=ROOT, stderr=subprocess.DEVNULL
        ).decode().strip()
        if out:
            return out.split("T")[0]  # YYYY-MM-DD
    except: pass
    try:
        ts = path.stat().st_mtime
        return datetime.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")
    except: return datetime.date.today().isoformat()

def add_url(urlset, loc, lastmod, priority, changefreq="weekly"):
    url = ET.SubElement(urlset, "url")
    ET.SubElement(url, "loc").text = loc
    ET.SubElement(url, "lastmod").text = lastmod
    ET.SubElement(url, "changefreq").text = changefreq
    ET.SubElement(url, "priority").text = priority

def main():
    urlset = ET.Element("urlset", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")
    today = datetime.date.today().isoformat()

    # Core pages
    core = [
        ("https://alieninc.tech/", ROOT / "index.html", "1.0", "daily"),
        ("https://alieninc.tech/about.html", ROOT / "about.html", "0.9", "monthly"),
        ("https://alieninc.tech/founder.html", ROOT / "founder.html", "0.9", "monthly"),
        ("https://alieninc.tech/mission.html", ROOT / "mission.html", "0.8", "monthly"),
        ("https://alieninc.tech/dashboard.html", ROOT / "dashboard.html", "0.7", "weekly"),
        ("https://panteon.alieninc.tech/", ROOT / "panteon" / "index.html", "1.0", "daily"),
        ("https://panteon.alieninc.tech/play.html", ROOT / "panteon" / "play.html", "0.9", "weekly"),
        ("https://panteon.alieninc.tech/cmb-product.html", ROOT / "panteon" / "cmb-product.html", "0.8", "weekly"),
        ("https://panteon.alieninc.tech/yono-forge.html", ROOT / "panteon" / "yono-forge.html", "0.8", "weekly"),
    ]
    for loc, path, pri, freq in core:
        if path.exists():
            add_url(urlset, loc, git_lastmod(path), pri, freq)
        else:
            add_url(urlset, loc, today, pri, freq)

    # Articles
    for p in sorted((ROOT / "articles").rglob("*.html")):
        if p.name.startswith("."): continue
        # Map to https://alieninc.tech/articles/...
        rel = p.relative_to(ROOT).as_posix()
        loc = f"https://alieninc.tech/{rel}"
        add_url(urlset, loc, git_lastmod(p), "0.8", "weekly")

    # Panteon subpages (excluding backups, backend, data)
    for p in sorted((ROOT / "panteon").rglob("*.html")):
        if any(x in p.parts for x in [".git","backend","__pycache__","data","logs"]): continue
        if ".bak" in p.name: continue
        rel = p.relative_to(ROOT / "panteon").as_posix()
        # Skip already added core panteon pages to avoid dup
        if rel in ("index.html","play.html","cmb-product.html","yono-forge.html"): continue
        loc = f"https://panteon.alieninc.tech/{rel}"
        # Use 0.7 for product/capability pages, 0.5 for deep docs
        pri = "0.6" if "cmb-docs" in rel else "0.7"
        add_url(urlset, loc, git_lastmod(p), pri, "weekly")

    # Subdomain sites (each has canonical https://<sub>.alieninc.tech/ + worker route)
    SUBS = ["a-san", "centra", "genesis", "immanuel", "kmt", "rousseau", "secure"]
    for sub in SUBS:
        idx = ROOT / sub / "index.html"
        if idx.exists():
            add_url(urlset, f"https://{sub}.alieninc.tech/", git_lastmod(idx), "0.9", "daily")
        for page in sorted((ROOT / sub).glob("*.html")):
            if page.name in ("index.html", "404.html") or ".bak" in page.name:
                continue
            add_url(urlset, f"https://{sub}.alieninc.tech/{page.name}", git_lastmod(page), "0.7", "weekly")
    # The Daily Art Cult (separate apex domain, served via tdac-proxy worker)
    tdac = ROOT / "thedailyartcult" / "index.html"
    if tdac.exists():
        add_url(urlset, "https://thedailyartcult.lol", git_lastmod(tdac), "0.9", "daily")
        for page in sorted((ROOT / "thedailyartcult").glob("*.html")):
            if page.name in ("index.html", "404.html") or ".bak" in page.name:
                continue
            add_url(urlset, f"https://thedailyartcult.lol/{page.name}", git_lastmod(page), "0.7", "weekly")

    # Also add trust subpages if exist
    for p in sorted((ROOT / "trust").rglob("*.html")) if (ROOT/"trust").exists() else []:
        rel = p.relative_to(ROOT).as_posix()
        loc = f"https://alieninc.tech/{rel}"
        add_url(urlset, loc, git_lastmod(p), "0.6", "monthly")

    tree = ET.ElementTree(urlset)
    ET.indent(tree, space="  ")
    tree.write(OUTPUT, encoding="utf-8", xml_declaration=True)
    print(f"Wrote {OUTPUT} with {len(urlset)} URLs")
    # Also copy to _pages if exists
    pages_sitemap = ROOT / "_pages" / "sitemap.xml"
    if pages_sitemap.parent.exists():
        import shutil
        shutil.copy2(OUTPUT, pages_sitemap)
        # Also write panteon sitemap reference
        panteon_sitemap = ROOT / "_pages" / "panteon" / "sitemap.xml"
        panteon_sitemap.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(OUTPUT, panteon_sitemap)
        print(f"Copied to _pages")

if __name__ == "__main__":
    main()
