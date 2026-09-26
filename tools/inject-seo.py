#!/usr/bin/env python3
"""
Inject missing SEO pack into subdomain index.html files (idempotent):
- <link rel="canonical">
- meta description (only if missing)
- Open Graph + twitter card tags
- Organization JSON-LD with parent Alien Inc + sameAs socials
Run: python3 tools/inject-seo.py
"""
import pathlib, re

ROOT = pathlib.Path(__file__).resolve().parents[1]

SOCIALS = [
    "https://www.linkedin.com/company/alieninc/",
    "https://www.linkedin.com/in/patrickneila/",
    "https://www.facebook.com/alieninc.tech/",
    "https://www.instagram.com/alieninc.tech/",
]

SITES = {
    # subdir: (canonical, site_name, title_hint, description)
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
               "Panteon — Secure Portal",
               "Secure portal by Alien Inc (Panteon). Founded by Patrick Neil Alcantara."),
    "thedailyartcult": ("https://thedailyartcult.lol", "The Daily Art Cult",
               "The Daily Art Cult",
               "The Daily Art Cult — bespoke audiobooks and philosophical reflections. A subsidiary of Alien Inc, founded by Patrick Neil Alcantara."),
}

def build_head(canonical, site, title, desc):
    socials_json = ",\n        ".join(f'"{s}"' for s in SOCIALS)
    return f"""<!-- SEO pack (auto: tools/inject-seo.py) -->
    <link rel="canonical" href="{canonical}">
    <meta property="og:type" content="website">
    <meta property="og:url" content="{canonical}">
    <meta property="og:site_name" content="{site}">
    <meta property="og:title" content="{title}">
    <meta property="og:description" content="{desc}">
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="{title}">
    <meta name="twitter:description" content="{desc}">
    <script type="application/ld+json">
    {{
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": "{site}",
        "url": "{canonical}",
        "description": "{desc}",
        "parentOrganization": {{ "@type": "Organization", "name": "Alien Inc", "url": "https://alieninc.tech" }},
        "founder": {{ "@type": "Person", "name": "Patrick Neil Alcantara", "url": "https://alieninc.tech/founder.html", "sameAs": ["https://www.linkedin.com/in/patrickneila/"] }},
        "sameAs": [
        {socials_json}
        ]
    }}
    </script>
"""

def process(sub, canonical, site, title, desc):
    path = ROOT / sub / "index.html"
    if not path.exists():
        print(f"{sub}: SKIP (no index.html)")
        return False
    html = path.read_text(encoding="utf-8", errors="replace")
    changed = False
    # canonical (+ full SEO pack) if missing
    if "rel=\"canonical\"" not in html:
        # insert full pack after <title> line
        html = re.sub(r"(</title>)", r"\1\n" + build_head(canonical, site, title, desc), html, count=1)
        changed = True
    else:
        # ensure JSON-LD sameAs present; if no sameAs at all, append org block
        if "sameAs" not in html:
            html = re.sub(r"(</title>)", r"\1\n" + build_head(canonical, site, title, desc), html, count=1)
            changed = True
    # meta description if missing
    if 'name="description"' not in html:
        html = re.sub(r"(</title>)", r'\1\n    <meta name="description" content="' + desc + '">', html, count=1)
        changed = True
    if changed:
        path.write_text(html, encoding="utf-8")
        print(f"{sub}: SEO pack injected")
    else:
        print(f"{sub}: already OK")
    return changed

def main():
    for sub, (canon, site, title, desc) in SITES.items():
        try:
            process(sub, canon, site, title, desc)
        except Exception as e:
            print(f"{sub}: ERROR {e}")

if __name__ == "__main__":
    main()
