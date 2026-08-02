#!/usr/bin/env python3
"""
Panteon Article Publisher
=========================
Drop .md files into source/, run this script, and it publishes them.

Usage:
    python publish.py              # publish all source/*.md
    python publish.py my-article.md  # publish one file

Each .md must have YAML front-matter at the top:
---
title: The Article Title
tag: Research Institute
date: 2026-08-02
author: Patrick Neil A.
slug: the-article-title
---

Body text follows. Use:
  # Heading       → h2
  ## Subheading   → h3
  > quote         → pull-quote blockquote
  *italic*        → em
  **bold**        → strong
  ---             → section divider (dark section break)
  [cta text](url) → CTA button at page end
"""

import sys
import os
import re
import glob
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCE_DIR = os.path.join(BASE_DIR, "source")
ARTICLES_DIR = os.path.join(BASE_DIR, "articles")
INDEX_PATH = os.path.join(BASE_DIR, "index.html")

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_frontmatter(text):
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    fm = {}
    for line in m.group(1).strip().split("\n"):
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip().lower()] = v.strip()
    return fm, text[m.end():]


def md_to_html(body):
    """Minimal Markdown → HTML converter (no dependencies)."""
    lines = body.strip().split("\n")
    html_parts = []
    in_paragraph = False
    current_paragraph = []

    def flush_paragraph():
        if current_paragraph:
            text = " ".join(current_paragraph)
            text = _inline_format(text)
            html_parts.append(f"<p>{text}</p>")
            current_paragraph.clear()

    for line in lines:
        stripped = line.strip()

        if stripped == "":
            flush_paragraph()
            continue

        # Horizontal rule → dark section divider
        if stripped == "---":
            flush_paragraph()
            html_parts.append('<div class="section-divider"></div>')
            continue

        # Blockquote → pull quote
        if stripped.startswith(">"):
            flush_paragraph()
            quote_text = stripped.lstrip("> ").strip()
            quote_text = _inline_format(quote_text)
            html_parts.append(f'<blockquote class="pull-quote">{quote_text}</blockquote>')
            continue

        # Headings
        if stripped.startswith("## "):
            flush_paragraph()
            html_parts.append(f'<h3>{_inline_format(stripped[3:])}</h3>')
            continue
        if stripped.startswith("# "):
            flush_paragraph()
            html_parts.append(f'<h2>{_inline_format(stripped[2:])}</h2>')
            continue

        current_paragraph.append(stripped)

    flush_paragraph()
    return "\n".join(html_parts)


def _inline_format(text):
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    text = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2">\1</a>', text)
    return text


ARTICLE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Panteon | {{title}}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="../styles.css">
    <style>
        .cap-hero{background-color:var(--bg-dark);color:var(--text-light);padding:180px 40px 120px;text-align:center;position:relative;overflow:hidden}
        .cap-hero::before{content:'';position:absolute;top:0;left:50%;transform:translateX(-50%);width:1px;height:80px;background:linear-gradient(to bottom,transparent,rgba(154,180,193,.4),transparent);animation:heroLine 1.8s ease-out forwards;opacity:0}
        @keyframes heroLine{0%{opacity:0;height:0}50%{opacity:1}100%{opacity:1;height:80px}}
        .cap-hero-inner{max-width:900px;margin:0 auto;position:relative;z-index:1}
        .cap-hero .tag{font-family:var(--font-mono);font-size:.7rem;letter-spacing:.12em;text-transform:uppercase;color:#9ab4c1;margin-bottom:20px;display:block;opacity:0;animation:fadeUp .8s ease-out .4s forwards}
        .cap-hero h1{font-size:clamp(2.4rem,5.5vw,4rem);font-weight:300;line-height:1.08;letter-spacing:-.03em;margin-bottom:24px;opacity:0;animation:fadeUp .8s ease-out .7s forwards}
        .cap-hero p{font-size:1.15rem;line-height:1.6;color:rgba(255,255,255,.65);max-width:600px;margin:0 auto;opacity:0;animation:fadeUp .8s ease-out 1s forwards}
        @keyframes fadeUp{from{opacity:0;transform:translateY(20px)}to{opacity:1;transform:translateY(0)}}

        .article-body{max-width:760px;margin:0 auto;padding:100px 40px}
        .article-body h2{font-size:2.4rem;font-weight:300;letter-spacing:-.02em;margin-bottom:48px;opacity:0;transform:translateY(16px);transition:opacity .7s ease,transform .7s ease}
        .article-body h2.in-view{opacity:1;transform:translateY(0)}
        .article-body h3{font-size:1.4rem;font-weight:400;margin-bottom:20px;margin-top:48px}
        .article-body p{font-size:1rem;line-height:1.75;color:var(--text-muted);margin-bottom:24px;opacity:0;transform:translateY(14px);transition:opacity .6s ease,transform .6s ease}
        .article-body p.in-view{opacity:1;transform:translateY(0)}
        .article-body em{font-style:italic}
        .article-body a{color:var(--text-dark);border-bottom:1px solid var(--text-muted);text-decoration:none}
        .article-body a:hover{color:var(--text-muted)}

        .dark-section{background:var(--bg-dark);color:var(--text-light);padding:100px 40px;position:relative;overflow:hidden}
        .dark-section::after{content:'';position:absolute;top:0;left:60px;width:1px;height:100%;background:linear-gradient(to bottom,transparent,rgba(154,180,193,.2) 30%,rgba(154,180,193,.2) 70%,transparent);opacity:0;transition:opacity 1s ease}
        .dark-section.in-view::after{opacity:1}
        .dark-section .article-body{position:relative;z-index:1}
        .dark-section .article-body p{color:rgba(255,255,255,.7);border-left:2px solid transparent;transition:opacity .6s ease,transform .6s ease,border-color .6s ease}
        .dark-section .article-body p.in-view{border-left-color:rgba(154,180,193,.3)}
        .dark-section h2{color:var(--text-light);margin-bottom:40px;opacity:0;transform:translateY(16px);transition:opacity .7s ease,transform .7s ease}
        .dark-section h2.in-view{opacity:1;transform:translateY(0)}

        .pull-quote{font-size:clamp(1.1rem,2vw,1.35rem);font-weight:300;font-style:italic;line-height:1.6;color:rgba(255,255,255,.5);border-left:2px solid #9ab4c1;padding-left:24px;margin:40px 0;max-width:640px;opacity:0;transform:translateY(12px);transition:opacity .7s ease .2s,transform .7s ease .2s}
        .pull-quote.in-view{opacity:1;transform:translateY(0)}

        .section-divider{height:1px;background:linear-gradient(90deg,transparent 10%,#d2d2d7 50%,transparent 90%);margin:60px auto;max-width:400px;opacity:0;transition:opacity .8s ease}
        .section-divider.in-view{opacity:1}

        .closing-section{text-align:center;padding:120px 40px 140px;position:relative}
        .closing-section .section-line{width:1px;height:60px;background:linear-gradient(to bottom,#d2d2d7,transparent);margin:0 auto 40px;opacity:0;transition:opacity .8s ease}
        .closing-section .section-line.in-view{opacity:1}
        .closing-section h2{font-size:2rem;font-weight:300;letter-spacing:-.02em;margin-bottom:16px;opacity:0;transform:translateY(12px);transition:opacity .7s ease .2s,transform .7s ease .2s}
        .closing-section h2.in-view{opacity:1;transform:translateY(0)}
        .closing-section .closing-meta{color:var(--text-muted);font-size:.9rem;line-height:1.7;max-width:480px;margin:0 auto 48px;opacity:0;transform:translateY(12px);transition:opacity .7s ease .4s,transform .7s ease .4s}
        .closing-section .closing-meta.in-view{opacity:1;transform:translateY(0)}

        .logo svg{fill:currentColor;width:118px;height:34px;transition:transform .4s cubic-bezier(.16,1,.3,1)}
        .logo:hover svg{transform:none}

        @media(max-width:768px){.cap-hero{padding:140px 24px 80px}.article-body{padding:60px 24px}.dark-section::after{left:24px}}
    </style>
</head>
<body>

    <svg aria-hidden="true" width="0" height="0" style="position:absolute;overflow:hidden">
        <defs>
            <filter id="panteon-brush" x="-10%" y="-10%" width="120%" height="120%"><feTurbulence type="fractalNoise" baseFrequency="0.23" numOctaves="4" result="noise"/><feDisplacementMap in="SourceGraphic" in2="noise" scale="0.85" xChannelSelector="R" yChannelSelector="B"/></filter>
            <mask id="panteon-roll"><rect width="100" height="100" fill="white"/><path d="M16 60 C20 58 24 59 27 63" fill="none" stroke="black" stroke-width="1.5" stroke-linecap="round"/></mask>
            <g id="panteon-lockup" fill="currentColor"><g filter="url(#panteon-brush)"><path d="M63 19 C57 19 54 23 54 29 L54 55 C54 59 56 62 60 64 L46 64 C42 64 40 66 40 68 C41 70 44 70 48 70 L65 70 C69 70 72 67 72 63 L72 29 C72 23 69 19 63 19 Z"/><circle cx="20" cy="64" r="7" mask="url(#panteon-roll)"/></g><text x="82" y="67" fill="currentColor" font-family="Inter, Arial, sans-serif" font-size="40" font-weight="500" letter-spacing="1.5">PANTEON</text></g>
        </defs>
    </svg>

    <div class="announcement-bar" id="top-announcement">
        Read CEO Patrick Neil's <a href="../letters/shareholder-letter.html">Letter to Shareholders ↗</a>
        <button class="close-btn" onclick="document.getElementById('top-announcement').style.display='none">×</button>
    </div>

    <header id="main-header">
        <a href="../index.html" class="logo">
            <svg viewBox="0 0 295 100" role="img" aria-label="Panteon"><use href="#panteon-lockup"/></svg>
        </a>
        <div class="nav-right">
            <button class="get-started-btn"><span>↖</span> Get Started</button>
            <button class="header-icon-box" aria-label="Search button">
                <svg width="15" height="15" fill="none" stroke="currentColor" viewBox="0 0 16 16">
                    <circle cx="9.5" cy="6.5" r="5.5" stroke-width="1.5"></circle>
                    <path d="M5.5 10.5l-4.5 4.5" stroke-width="1.5"></path>
                </svg>
            </button>
            <button class="header-icon-box" aria-label="Menu button">
                <div class="burger-lines"><span></span><span></span><span></span></div>
            </button>
        </div>
    </header>

    <section class="cap-hero">
        <div class="cap-hero-inner">
            <span class="tag">{{tag}}</span>
            <h1>{{title}}</h1>
            <p>{{excerpt}}</p>
        </div>
    </section>

    <main class="main-content">
        <div class="article-body">
{{article_html}}
        </div>

        <section class="closing-section">
            <div class="section-line"></div>
            <h2>{{title}}</h2>
            <p class="closing-meta">{{date}} · {{author}}</p>
            <a href="index.html" class="get-started-btn" style="background-color:var(--text-dark);color:var(--text-light);border-color:var(--text-dark);padding:14px 40px;font-size:.85rem;text-decoration:none">Back to Articles</a>
        </section>
    </main>

    <footer>
        <div class="footer-container">
            <div class="footer-left-branding">
                <p>© 2026 Panteon Technologies Inc.</p>
                <p class="all-rights">All rights reserved.</p>
                <div class="footer-divider-line"></div>
                <a href="../cookies.html" class="footer-cookie-btn" style="text-decoration:none;">Cookies Settings</a>
                <div class="footer-divider-line"></div>
                <div class="footer-divider-line"></div>
                <div class="footer-social-container">
                    <a href="#" class="social-capsule">Youtube</a>
                    <a href="#" class="social-capsule">X</a>
                    <a href="#" class="social-capsule">Linkedin</a>
                    <a href="#" class="social-capsule">Github</a>
                    <a href="#" class="social-capsule">Store</a>
                </div>
            </div>
            <div class="footer-links-grid">
                <div class="footer-links-col">
                    <h4>Research</h4>
                    <ul>
                        <li><a href="index.html">Panteon Research Institute</a></li>
                    </ul>
                </div>
                <div class="footer-links-col">
                    <h4>Alien Inc</h4>
                    <ul>
                        <li><a href="https://rousseau.alieninc.tech" target="_blank">Rousseau</a></li>
                        <li><a href="https://thedailyartcult.alieninc.tech" target="_blank">The Daily Art Cult</a></li>
                        <li><a href="https://kmt.alieninc.tech" target="_blank">KMT Consulting Group</a></li>
                        <li><a href="https://immanuel.alieninc.tech" target="_blank">Immanuel</a></li>
                        <li><a href="https://alcantaraartfoundation.alieninc.tech" target="_blank">St. Alcantara Foundation</a></li>
                        <li><a href="https://sp.alieninc.tech" target="_blank">Statute & Precedent</a></li>
                        <li><a href="https://centra.alieninc.tech" target="_blank">Centra</a></li>
                    </ul>
                </div>
                <div class="footer-links-col">
                    <h4>Capabilities</h4>
                    <ul>
                        <li><a href="../capabilities/ai-ml.html">AI + ML</a></li>
                        <li><a href="../capabilities/yono-for-developers.html">YONO for Developers</a></li>
                        <li><a href="../capabilities/data-integration.html">Data Integration</a></li>
                        <li><a href="../capabilities/digital-twin.html">Digital Twin</a></li>
                        <li><a href="../capabilities/dynamic-scheduling.html">Dynamic Scheduling</a></li>
                        <li><a href="../capabilities/edge-ai.html">Edge AI</a></li>
                        <li><a href="../capabilities/marketplace.html">Marketplace</a></li>
                    </ul>
                </div>
                <div class="footer-links-col">
                    <h4>Documents</h4>
                    <ul>
                        <li><a href="../developers/community.html">Developer Community</a></li>
                        <li><a href="../developers/documentation.html">Platform Documentation</a></li>
                        <li><a href="../developers/panteon-developers.html">Panteon Developers</a></li>
                        <li><a href="index.html">Panteon Research Institute</a></li>
                        <li><a href="../trust/trust-center.html">Trust Center</a></li>
                        <li><a href="../trust/modern-slavery.html">Modern Slavery Statement</a></li>
                        <li><a href="../cookies.html">Cookies</a></li>
                        <li><a href="../trust/privacy-civil-liberties.html">Privacy and Civil Liberties</a></li>
                    </ul>
                </div>
            </div>
        </div>
    </footer>

    <script>
        const header = document.getElementById('main-header');
        const scrollThreshold = window.innerHeight * 0.4;
        window.addEventListener('scroll', () => {
            if (window.scrollY >= scrollThreshold) {
                header.classList.add('scrolled');
            } else {
                header.classList.remove('scrolled');
            }
        });

        const revealTargets = document.querySelectorAll(
            '.article-body h2, .article-body h3, .article-body p, .pull-quote, .section-divider, .dark-section, .section-line, .closing-section h2, .closing-meta'
        );
        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    entry.target.classList.add('in-view');
                    observer.unobserve(entry.target);
                }
            });
        }, { threshold: 0.15, rootMargin: '0px 0px -40px 0px' });
        revealTargets.forEach(el => observer.observe(el));
    </script>
</body>
</html>"""

INDEX_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Panteon | Panteon Research Institute</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="../styles.css">
    <style>
        .cap-hero{background-color:var(--bg-dark);color:var(--text-light);padding:180px 40px 120px;text-align:center;position:relative;overflow:hidden}
        .cap-hero::before{content:'';position:absolute;top:0;left:50%;transform:translateX(-50%);width:1px;height:80px;background:linear-gradient(to bottom,transparent,rgba(154,180,193,.4),transparent);animation:heroLine 1.8s ease-out forwards;opacity:0}
        @keyframes heroLine{0%{opacity:0;height:0}50%{opacity:1}100%{opacity:1;height:80px}}
        .cap-hero-inner{max-width:900px;margin:0 auto;position:relative;z-index:1}
        .cap-hero .tag{font-family:var(--font-mono);font-size:.7rem;letter-spacing:.12em;text-transform:uppercase;color:#9ab4c1;margin-bottom:20px;display:block;opacity:0;animation:fadeUp .8s ease-out .4s forwards}
        .cap-hero h1{font-size:clamp(2.4rem,5.5vw,4rem);font-weight:300;line-height:1.08;letter-spacing:-.03em;margin-bottom:24px;opacity:0;animation:fadeUp .8s ease-out .7s forwards}
        .cap-hero p{font-size:1.15rem;line-height:1.6;color:rgba(255,255,255,.65);max-width:600px;margin:0 auto;opacity:0;animation:fadeUp .8s ease-out 1s forwards}
        @keyframes fadeUp{from{opacity:0;transform:translateY(20px)}to{opacity:1;transform:translateY(0)}}

        .articles-grid{max-width:1400px;margin:0 auto;padding:100px 40px}
        .articles-grid h2{font-size:2.4rem;font-weight:300;letter-spacing:-.02em;margin-bottom:48px}
        .article-list{display:grid;gap:0}
        .article-row{display:grid;grid-template-columns:1fr auto;gap:20px;align-items:center;padding:40px 20px;border-top:1px solid var(--border-dark);cursor:pointer;transition:background-color .3s ease}
        .article-row:last-child{border-bottom:1px solid var(--border-dark)}
        .article-row:hover{background-color:var(--bg-gray)}
        .article-row:hover .article-row-title{color:var(--text-dark)}
        .article-row:hover .article-row-arrow{transform:translateX(4px);opacity:1}
        .article-row-title{font-size:1.2rem;font-weight:400;letter-spacing:-.01em;margin-bottom:8px;transition:color .3s ease}
        .article-row-meta{font-size:.85rem;color:var(--text-muted)}
        .article-row-arrow{font-size:1.2rem;opacity:.3;transition:transform .3s ease,opacity .3s ease}

        .mission-card{max-width:1400px;margin:0 auto;padding:0 40px 100px}
        .mission-card-inner{border:1px solid var(--border-dark);border-radius:2px;padding:48px;background:var(--bg-light)}
        .mission-card-inner h3{font-size:1.3rem;font-weight:400;margin-bottom:12px}
        .mission-card-inner p{font-size:.95rem;line-height:1.55;color:var(--text-muted);margin-bottom:16px}
        .mission-card-inner a{display:inline-flex;align-items:center;gap:8px;font-size:.8rem;font-weight:600;letter-spacing:.05em;text-transform:uppercase;color:var(--text-dark);border-bottom:1px solid var(--text-muted);padding-bottom:2px;text-decoration:none;margin-top:8px}

        .logo svg{fill:currentColor;width:118px;height:34px;transition:transform .4s cubic-bezier(.16,1,.3,1)}
        .logo:hover svg{transform:none}

        @media(max-width:768px){.cap-hero{padding:140px 24px 80px}.articles-grid{padding:60px 24px}.article-row{grid-template-columns:1fr;padding:30px 0}}
    </style>
</head>
<body>

    <svg aria-hidden="true" width="0" height="0" style="position:absolute;overflow:hidden">
        <defs>
            <filter id="panteon-brush" x="-10%" y="-10%" width="120%" height="120%"><feTurbulence type="fractalNoise" baseFrequency="0.23" numOctaves="4" result="noise"/><feDisplacementMap in="SourceGraphic" in2="noise" scale="0.85" xChannelSelector="R" yChannelSelector="B"/></filter>
            <mask id="panteon-roll"><rect width="100" height="100" fill="white"/><path d="M16 60 C20 58 24 59 27 63" fill="none" stroke="black" stroke-width="1.5" stroke-linecap="round"/></mask>
            <g id="panteon-lockup" fill="currentColor"><g filter="url(#panteon-brush)"><path d="M63 19 C57 19 54 23 54 29 L54 55 C54 59 56 62 60 64 L46 64 C42 64 40 66 40 68 C41 70 44 70 48 70 L65 70 C69 70 72 67 72 63 L72 29 C72 23 69 19 63 19 Z"/><circle cx="20" cy="64" r="7" mask="url(#panteon-roll)"/></g><text x="82" y="67" fill="currentColor" font-family="Inter, Arial, sans-serif" font-size="40" font-weight="500" letter-spacing="1.5">PANTEON</text></g>
        </defs>
    </svg>

    <div class="announcement-bar" id="top-announcement">
        Read CEO Patrick Neil's <a href="../letters/shareholder-letter.html">Letter to Shareholders ↗</a>
        <button class="close-btn" onclick="document.getElementById('top-announcement').style.display='none">×</button>
    </div>

    <header id="main-header">
        <a href="../index.html" class="logo">
            <svg viewBox="0 0 295 100" role="img" aria-label="Panteon"><use href="#panteon-lockup"/></svg>
        </a>
        <div class="nav-right">
            <button class="get-started-btn"><span>↖</span> Get Started</button>
            <button class="header-icon-box" aria-label="Search button">
                <svg width="15" height="15" fill="none" stroke="currentColor" viewBox="0 0 16 16">
                    <circle cx="9.5" cy="6.5" r="5.5" stroke-width="1.5"></circle>
                    <path d="M5.5 10.5l-4.5 4.5" stroke-width="1.5"></path>
                </svg>
            </button>
            <button class="header-icon-box" aria-label="Menu button">
                <div class="burger-lines"><span></span><span></span><span></span></div>
            </button>
        </div>
    </header>

    <section class="cap-hero">
        <div class="cap-hero-inner">
            <span class="tag">Panteon Research Institute</span>
            <h1>Articles &amp; Publications</h1>
            <p>Falsifiable research on the boundary between AI-defined success and human-defined success.</p>
        </div>
    </section>

    <main class="main-content">

        <div class="mission-card">
            <div class="mission-card-inner">
                <h3>Mission &amp; Vision</h3>
                <p>The founding charter of the Panteon Research Institute — why human judgment cannot be automated away, and how philosophical frameworks become instruments rather than content.</p>
                <a href="mission-and-vision.html">Read Mission & Vision <span>→</span></a>
            </div>
        </div>

        <section class="articles-grid">
            <h2>Published Articles</h2>
            <div class="article-list">
{{article_rows}}
            </div>
        </section>

    </main>

    <footer>
        <div class="footer-container">
            <div class="footer-left-branding">
                <p>© 2026 Panteon Technologies Inc.</p>
                <p class="all-rights">All rights reserved.</p>
                <div class="footer-divider-line"></div>
                <a href="../cookies.html" class="footer-cookie-btn" style="text-decoration:none;">Cookies Settings</a>
                <div class="footer-divider-line"></div>
                <div class="footer-divider-line"></div>
                <div class="footer-social-container">
                    <a href="#" class="social-capsule">Youtube</a>
                    <a href="#" class="social-capsule">X</a>
                    <a href="#" class="social-capsule">Linkedin</a>
                    <a href="#" class="social-capsule">Github</a>
                    <a href="#" class="social-capsule">Store</a>
                </div>
            </div>
            <div class="footer-links-grid">
                <div class="footer-links-col">
                    <h4>Research</h4>
                    <ul>
                        <li><a href="index.html">Panteon Research Institute</a></li>
                    </ul>
                </div>
                <div class="footer-links-col">
                    <h4>Alien Inc</h4>
                    <ul>
                        <li><a href="https://rousseau.alieninc.tech" target="_blank">Rousseau</a></li>
                        <li><a href="https://thedailyartcult.alieninc.tech" target="_blank">The Daily Art Cult</a></li>
                        <li><a href="https://kmt.alieninc.tech" target="_blank">KMT Consulting Group</a></li>
                        <li><a href="https://immanuel.alieninc.tech" target="_blank">Immanuel</a></li>
                        <li><a href="https://alcantaraartfoundation.alieninc.tech" target="_blank">St. Alcantara Foundation</a></li>
                        <li><a href="https://sp.alieninc.tech" target="_blank">Statute & Precedent</a></li>
                        <li><a href="https://centra.alieninc.tech" target="_blank">Centra</a></li>
                    </ul>
                </div>
                <div class="footer-links-col">
                    <h4>Capabilities</h4>
                    <ul>
                        <li><a href="../capabilities/ai-ml.html">AI + ML</a></li>
                        <li><a href="../capabilities/yono-for-developers.html">YONO for Developers</a></li>
                        <li><a href="../capabilities/data-integration.html">Data Integration</a></li>
                        <li><a href="../capabilities/digital-twin.html">Digital Twin</a></li>
                        <li><a href="../capabilities/dynamic-scheduling.html">Dynamic Scheduling</a></li>
                        <li><a href="../capabilities/edge-ai.html">Edge AI</a></li>
                        <li><a href="../capabilities/marketplace.html">Marketplace</a></li>
                    </ul>
                </div>
                <div class="footer-links-col">
                    <h4>Documents</h4>
                    <ul>
                        <li><a href="../developers/community.html">Developer Community</a></li>
                        <li><a href="../developers/documentation.html">Platform Documentation</a></li>
                        <li><a href="../developers/panteon-developers.html">Panteon Developers</a></li>
                        <li><a href="index.html">Panteon Research Institute</a></li>
                        <li><a href="../trust/trust-center.html">Trust Center</a></li>
                        <li><a href="../trust/modern-slavery.html">Modern Slavery Statement</a></li>
                        <li><a href="../cookies.html">Cookies</a></li>
                        <li><a href="../trust/privacy-civil-liberties.html">Privacy and Civil Liberties</a></li>
                    </ul>
                </div>
            </div>
        </div>
    </footer>

    <script>
        const header = document.getElementById('main-header');
        const scrollThreshold = window.innerHeight * 0.4;
        window.addEventListener('scroll', () => {
            if (window.scrollY >= scrollThreshold) {
                header.classList.add('scrolled');
            } else {
                header.classList.remove('scrolled');
            }
        });
    </script>
</body>
</html>"""


def get_excerpt(body, max_chars=160):
    first_para = body.strip().split("\n\n")[0]
    first_para = re.sub(r"[#>*_]", "", first_para).strip()
    if len(first_para) > max_chars:
        return first_para[:max_chars].rsplit(" ", 1)[0] + "…"
    return first_para


def build_article(source_path):
    with open(source_path, "r", encoding="utf-8") as f:
        raw = f.read()

    fm, body = parse_frontmatter(raw)
    title = fm.get("title", "Untitled Article")
    tag = fm.get("tag", "Panteon Research Institute")
    date = fm.get("date", datetime.now().strftime("%Y-%m-%d"))
    author = fm.get("author", "Patrick Neil A.")
    slug = fm.get("slug", re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-"))

    excerpt = get_excerpt(body)
    article_html = md_to_html(body)

    html = ARTICLE_TEMPLATE
    html = html.replace("{{title}}", title)
    html = html.replace("{{tag}}", tag)
    html = html.replace("{{excerpt}}", excerpt)
    html = html.replace("{{date}}", date)
    html = html.replace("{{author}}", author)
    html = html.replace("{{article_html}}", article_html)

    out_path = os.path.join(ARTICLES_DIR, f"{slug}.html")
    os.makedirs(ARTICLES_DIR, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    return {"slug": slug, "title": title, "date": date, "author": author, "excerpt": excerpt}


def build_index(articles):
    rows = []
    for a in sorted(articles, key=lambda x: x["date"], reverse=True):
        rows.append(
            f'                <a href="articles/{a["slug"]}.html" class="article-row">\n'
            f'                    <div>\n'
            f'                        <div class="article-row-title">{a["title"]}</div>\n'
            f'                        <div class="article-row-meta">{a["date"]} · {a["author"]}</div>\n'
            f"                    </div>\n"
            f'                    <div class="article-row-arrow">→</div>\n'
            f"                </a>"
        )

    html = INDEX_TEMPLATE.replace("{{article_rows}}", "\n".join(rows))
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        f.write(html)


def main():
    if len(sys.argv) > 1:
        files = [os.path.join(SOURCE_DIR, f) for f in sys.argv[1:]]
    else:
        files = sorted(glob.glob(os.path.join(SOURCE_DIR, "*.md")))

    if not files:
        print("No .md files found in source/. Drop one there and run again.")
        return

    articles = []
    for fp in files:
        print(f"Publishing {os.path.basename(fp)}...")
        meta = build_article(fp)
        articles.append(meta)
        print(f"  → articles/{meta['slug']}.html")

    # Also load any previously published articles metadata
    existing = glob.glob(os.path.join(ARTICLES_DIR, "*.html"))
    existing_slugs = {a["slug"] for a in articles}
    for ep in existing:
        slug = os.path.splitext(os.path.basename(ep))[0]
        if slug not in existing_slugs:
            # Re-parse from the HTML to get metadata
            with open(ep, "r", encoding="utf-8") as f:
                content = f.read()
            title_m = re.search(r"<title>Panteon \| (.+?)</title>", content)
            date_m = re.search(r'<p class="closing-meta">(.+?) ·', content)
            author_m = re.search(r'· (.+?)</p>', content)
            articles.append({
                "slug": slug,
                "title": title_m.group(1) if title_m else slug,
                "date": date_m.group(1) if date_m else "Unknown",
                "author": author_m.group(1) if author_m else "Unknown",
                "excerpt": "",
            })

    build_index(articles)
    print(f"\nIndex updated: {len(articles)} article(s) listed.")


if __name__ == "__main__":
    main()
