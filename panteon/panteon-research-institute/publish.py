#!/usr/bin/env python3
"""
Panteon Article Publisher
=========================
Drop .md files into source/, run this script, and it publishes them.

Usage:
    python publish.py               # publish all source/*.md
    python publish.py my-article.md # publish one file

Two article styles are supported:

STYLE 1 — Bare writing style (no front-matter required). Just write the way
you naturally write an essay:

    # The Article Title          -> becomes the page title (hero, <title>, slug)

    Opening paragraph here. This becomes the excerpt shown in the hero and
    on the research institute landing page.

    ## A Major Section           -> rendered as an h2 section heading

    ## Another Major Section

    ### A Subsection             -> rendered as h3

STYLE 2 — Front-matter style (traditional):

    ---
    title: The Article Title
    tag: Panteon Research Institute
    date: 2026-08-02
    author: Patrick Neil A.
    slug: the-article-title
    ---

    # A Section Heading          -> h2
    ## A Subsection Heading      -> h3

Body syntax (both styles):
    # Heading        -> h2 (consumed as the page title when no front-matter)
    ## Subheading    -> h3 (h2 when the title comes from a bare '#')
    ### Subsub       -> h4 (h3 when the title comes from a bare '#')
    > quote          -> pull-quote blockquote
    - item           -> bullet list
    1. item          -> numbered list
    **bold**         -> strong
    *italic*         -> em
    `code`           -> inline code
    [text](url)      -> link
    ---              -> section divider
"""

import sys
import os
import re
import glob
import json
import html
from urllib.parse import quote
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCE_DIR = os.path.join(BASE_DIR, "source")
ARTICLES_DIR = os.path.join(BASE_DIR, "articles")
INDEX_PATH = os.path.join(BASE_DIR, "index.html")
LOCKED_PAGE_PATH = os.path.join(BASE_DIR, "locked.html")
ARCHIVE_LOCK_DATE = "2016-12-22"
# Private store OUTSIDE the public web root (server.py blocks /data/). The
# FastAPI backend serves these to authenticated users via /api/v1/research/{slug}.
PRIVATE_DIR = os.path.join(BASE_DIR, "..", "..", "data", "research-locked")
LOCKED_MANIFEST_PATH = os.path.join(PRIVATE_DIR, "manifest.json")

SUPABASE_URL = "https://frwjaixxlgthkgjtafhz.supabase.co"
SUPABASE_ANON_KEY = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZyd2phaXh4bGd0aGtnanRhZmh6Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzkwNDUzNDQsImV4cCI6MjA5NDYyMTM0NH0.j2DKz__QMml4WplMYNmsQpTUw0qu-kZG7Md3qBEEdEc")

LOCK_ICON = ('<svg viewBox="0 0 24 24" class="lock-icon" fill="none" stroke="currentColor" '
             'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
             '<rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>'
             '<path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>')

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
UL_ITEM_RE = re.compile(r"^[-*+]\s+(.*)$")
OL_ITEM_RE = re.compile(r"^\d+\.\s+(.*)$")


def esc(value):
    return html.escape(str(value), quote=False)


# ---------------------------------------------------------------------------
# Full site navigation CSS (matches the home page exactly)
# ---------------------------------------------------------------------------
NAV_CSS = """
    :root{--accent-neon:#DFF140;--font-tech:"Space Grotesk",monospace}
    .scroll-progress-bar{position:fixed;top:0;left:0;height:2px;width:0%;background-color:var(--accent-neon);z-index:1005;transition:width .1s ease-out}
    .announcement-bar{background-color:#08090a;color:var(--text-light);display:flex;justify-content:center;align-items:center;padding:10px 40px;font-size:.75rem;font-family:var(--font-tech);letter-spacing:.05em;text-transform:uppercase;border-bottom:1px solid var(--border-light);position:relative;z-index:1001;text-align:center}
    .announcement-bar a{text-decoration:none;margin-left:6px;font-weight:300;color:var(--accent-neon);border-bottom:1px solid var(--accent-neon);padding-bottom:1px}
    .announcement-bar .close-btn{position:absolute;right:40px;background:none;border:none;color:var(--text-light);cursor:pointer;font-size:1.1rem;opacity:.5;transition:opacity .2s}
    .announcement-bar .close-btn:hover{opacity:1}
    header{display:block;padding:0;position:sticky;top:0;z-index:1000;background-color:rgba(0,0,0,.4);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);border-bottom:1px solid var(--border-light);color:var(--text-light);transition:background-color .4s ease,color .4s ease,border-color .4s ease}
    header.scrolled{background-color:rgba(255,255,255,.9);color:var(--text-dark);border-bottom-color:var(--border-dark);box-shadow:0 4px 30px rgba(0,0,0,.01)}
    header.menu-active{background-color:#000000 !important;color:#ffffff !important;border-bottom-color:rgba(255,255,255,.1) !important}
    .navWrapper{max-width:1400px;margin:0 auto;padding:0 40px}
    .top-nav{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;height:72px}
    .left-wrapper{display:flex;align-items:center}
    .logo{font-family:var(--font-sans);font-weight:500;font-size:.98rem;letter-spacing:.11em;text-transform:uppercase;display:flex;align-items:center;gap:0;line-height:1;white-space:nowrap;cursor:pointer}
    .logo svg{fill:currentColor;width:118px;height:34px;transition:transform .4s cubic-bezier(.16,1,.3,1)}
    .logo:hover svg{transform:none}
    .center-wrapper{display:flex;align-items:center;gap:32px}
    .nav-item-dropdown{cursor:pointer;font-family:var(--font-tech);font-size:.8rem;font-weight:500;letter-spacing:.08em;text-transform:uppercase;display:flex;align-items:center;padding:24px 0;position:relative}
    .nav-item-dropdown:hover{color:var(--accent-neon)}
    header.menu-active .nav-item-dropdown:hover{color:var(--accent-neon) !important}
    .plus-sign{position:relative;width:8px;height:8px;margin-left:6px;display:inline-flex;align-items:center;justify-content:center}
    .plus-sign span{position:absolute;background-color:currentColor;transition:transform .4s cubic-bezier(.16,1,.3,1)}
    .plus-sign span:nth-child(1){width:100%;height:1.5px}
    .plus-sign span:nth-child(2){width:1.5px;height:100%}
    .nav-item-dropdown:hover .plus-sign span:nth-child(2){transform:rotate(90deg) scaleY(0)}
    .right-wrapper{display:flex;align-items:center;justify-content:flex-end;gap:12px}
    .get-started-btn{background-color:var(--text-light);color:var(--bg-dark);border:1px solid var(--text-light);padding:9px 24px;font-family:var(--font-tech);font-size:.75rem;font-weight:600;letter-spacing:.05em;text-transform:uppercase;border-radius:2px;display:flex;align-items:center;gap:6px;text-decoration:none;transition:all .3s ease}
    .get-started-btn span{font-size:.85rem;transition:transform .2s}
    .get-started-btn:hover span{transform:translate(-2px,-2px)}
    header.scrolled .get-started-btn{background-color:var(--text-dark);color:var(--text-light);border-color:var(--text-dark)}
    header.menu-active .get-started-btn{background-color:var(--text-light) !important;color:var(--bg-dark) !important;border-color:var(--text-light) !important}
    .header-icon-box{width:38px;height:38px;border:1px solid rgba(255,255,255,.15);border-radius:2px;display:flex;align-items:center;justify-content:center;background:transparent;cursor:pointer;color:inherit;transition:border-color .2s,background-color .2s}
    .header-icon-box:hover{border-color:rgba(255,255,255,.5);background-color:rgba(255,255,255,.05)}
    header.scrolled .header-icon-box{border-color:rgba(0,0,0,.1)}
    header.scrolled .header-icon-box:hover{border-color:rgba(0,0,0,.3);background-color:rgba(0,0,0,.02)}
    header.menu-active .header-icon-box{border-color:rgba(255,255,255,.2) !important}
    .burger-lines{width:14px;height:8px;display:flex;flex-direction:column;justify-content:space-between}
    .burger-lines span{display:block;width:100%;height:1.5px;background-color:currentColor}
    .mega-menu-overlay{position:fixed;top:72px;left:0;width:100%;height:calc(100vh - 72px);background-color:rgba(0,0,0,.5);opacity:0;pointer-events:none;z-index:998;transition:opacity .4s ease}
    .mega-menu-overlay.active{opacity:1;pointer-events:auto}
    .mega-menu-container{position:absolute;top:72px;left:0;width:100%;background-color:#000000;border-bottom:1px solid rgba(255,255,255,.1);color:#ffffff;z-index:999;transform:translateY(-20px);opacity:0;pointer-events:none;transition:transform .4s cubic-bezier(.16,1,.3,1),opacity .4s cubic-bezier(.16,1,.3,1);padding:60px 40px}
    .mega-menu-container.active{transform:translateY(0);opacity:1;pointer-events:auto}
    .mega-menu-grid{max-width:1400px;margin:0 auto;display:grid;grid-template-columns:1.2fr 1fr 1fr;gap:60px}
    .mega-menu-grid .col-1{border-right:1px solid rgba(255,255,255,.1);padding-right:60px}
    .mega-menu-grid h3{font-family:var(--font-tech);font-size:.75rem;letter-spacing:.15em;text-transform:uppercase;color:var(--text-muted);margin-bottom:24px;opacity:0;transform:translateY(6px);transition:opacity .3s ease,transform .3s ease}
    .mega-menu-container.active h3{opacity:1;transform:translateY(0)}
    .mega-menu-grid .col-1 p{font-size:1.1rem;font-weight:300;line-height:1.5;color:#e2e3e5;opacity:0;transform:translateY(6px);transition:opacity .35s ease .08s,transform .35s ease .08s}
    .mega-menu-container.active .col-1 p{opacity:1;transform:translateY(0)}
    .mega-menu-grid .menu-link-item{display:flex;align-items:center;margin-bottom:16px;font-size:.95rem;font-weight:500;opacity:0;transform:translateY(8px);transition:opacity .3s ease .05s,transform .3s ease .05s}
    .mega-menu-container.active .menu-link-item{opacity:1;transform:translateY(0)}
    .mega-menu-container.active .menu-link-item:nth-child(2){transition-delay:.1s}
    .mega-menu-container.active .menu-link-item:nth-child(3){transition-delay:.15s}
    .mega-menu-container.active .menu-link-item:nth-child(4){transition-delay:.2s}
    .mega-menu-container.active .menu-link-item:nth-child(5){transition-delay:.25s}
    .mega-menu-container.active .menu-link-item:nth-child(6){transition-delay:.3s}
    .mega-menu-grid .menu-link-item .plus-sign{margin-right:12px;margin-left:0;color:var(--accent-neon)}
    .mega-menu-grid .menu-link-item a{transition:transform .3s cubic-bezier(.16,1,.3,1)}
    .mega-menu-grid .menu-link-item:hover a{transform:translateX(4px);color:var(--accent-neon)}
    .mega-menu-grid .product-group{display:flex;flex-direction:column;gap:14px;opacity:0;transform:translateY(8px);transition:opacity .3s ease,transform .3s ease}
    .mega-menu-grid .product-group.has-content{opacity:1;transform:translateY(0)}
    .mega-menu-grid .product-group a{font-size:.9rem;color:#b1b2b5}
    .mega-menu-grid .product-group a:hover{color:#ffffff;text-decoration:underline}
    .mobile-drawer{position:fixed;top:0;right:0;width:100%;max-width:440px;height:100vh;background-color:#050607;z-index:1010;transform:translateX(100%);transition:transform .4s cubic-bezier(.16,1,.3,1);border-left:1px solid var(--border-light);padding:40px;display:flex;flex-direction:column;justify-content:space-between}
    .mobile-drawer.active{transform:translateX(0)}
    .mobile-drawer-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:40px}
    .mobile-drawer-header .close-drawer-btn{background:none;border:none;color:#ffffff;cursor:pointer;font-size:1.8rem}
    .mobile-drawer-links{display:flex;flex-direction:column;gap:24px}
    .mobile-drawer-group-title{font-family:var(--font-tech);font-size:.7rem;letter-spacing:.15em;text-transform:uppercase;color:var(--text-muted);margin-bottom:12px}
    .mobile-drawer-item{font-family:var(--font-tech);font-size:1.3rem;font-weight:300;letter-spacing:.05em;text-transform:uppercase;display:flex;align-items:center;gap:12px;color:#ffffff;opacity:0;transform:translateY(15px);transition:opacity .3s ease,transform .3s ease}
    .mobile-drawer.active .mobile-drawer-item{opacity:1;transform:translateY(0)}
    .mobile-drawer.active .mobile-drawer-item:nth-child(1){transition-delay:.1s}
    .mobile-drawer.active .mobile-drawer-item:nth-child(2){transition-delay:.15s}
    .mobile-drawer.active .mobile-drawer-item:nth-child(3){transition-delay:.2s}
    .mobile-drawer.active .mobile-drawer-item:nth-child(4){transition-delay:.25s}
    .mobile-drawer-footer{border-top:1px solid var(--border-light);padding-top:24px}
    .mobile-drawer-footer .get-started-btn{width:100%;justify-content:center}
    @media(max-width:768px){.top-nav{grid-template-columns:1fr auto;height:64px}.center-wrapper,.right-wrapper .get-started-btn{display:none}.navWrapper{padding:0 24px}.announcement-bar .close-btn{right:20px}}
"""


# ---------------------------------------------------------------------------
# Full site header: mega-menu nav + mobile slide drawer
# {{ROOT}} is replaced with "../" for the institute index or "../../" for
# articles so every link resolves no matter how deep the page sits.
# ---------------------------------------------------------------------------
HEADER_HTML = """
    <div class="scroll-progress-bar" id="scroll-bar"></div>

    <div class="announcement-bar" id="top-announcement">
        Read CEO Patrick Neil's <a href="{{ROOT}}letters/shareholder-letter.html">Letter to Shareholders ↗</a>
        <button class="close-btn" onclick="document.getElementById('top-announcement').style.display='none'">×</button>
    </div>

    <header id="main-header">
        <div class="navWrapper">
            <div class="top-nav">
                <div class="left-wrapper">
                    <a href="{{ROOT}}index.html" class="logo">
                        <svg viewBox="0 0 295 100" role="img" aria-label="Panteon"><use href="#panteon-lockup"/></svg>
                    </a>
                </div>
                <div class="center-wrapper">
                    <div class="nav-item-dropdown" data-menu="five-elements">Five Elements<div class="plus-sign"><span></span><span></span></div></div>
                    <div class="nav-item-dropdown" data-menu="capabilities">Capabilities<div class="plus-sign"><span></span><span></span></div></div>
                    <div class="nav-item-dropdown" data-menu="company">Company<div class="plus-sign"><span></span><span></span></div></div>
                </div>
                <div class="right-wrapper">
                    <a href="{{ROOT}}login.html" class="get-started-btn">Get Started <span>↖</span></a>
                    <button class="header-icon-box" data-research-search aria-label="Search the research archive">
                        <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 16 16">
                            <circle cx="9.5" cy="6.5" r="5.5" stroke-width="1.5"></circle>
                            <path d="M5.5 10.5l-4.5 4.5" stroke-width="1.5"></path>
                        </svg>
                    </button>
                    <button class="header-icon-box" id="open-menu-drawer-btn" aria-label="Menu button">
                        <div class="burger-lines"><span></span><span></span><span></span></div>
                    </button>
                </div>
            </div>
        </div>

        <div class="mega-menu-overlay" id="mega-menu-overlay"></div>

        <div class="mega-menu-container" id="menu-five-elements">
            <div class="mega-menu-grid">
                <div class="col-1">
                    <h3>Overview</h3>
                    <p>The Five Elements of Effective Warfare. Decisive military technology, deployed across every domain — wherever the terrain demands it.</p>
                    <a href="{{ROOT}}overview-full-article.html" class="cta-link-arrow">READ FULL BRIEFING <span>↗</span></a>
                </div>
                <div class="col-2">
                    <h3>The Domains</h3>
                    <div class="menu-link-item" data-group="terra"><div class="plus-sign"><span></span><span></span></div><a href="{{ROOT}}platforms/yono.html">Terra <span style="color:#88898c;font-weight:300;font-size:0.8rem">(Land)</span></a></div>
                    <div class="menu-link-item" data-group="abyss"><div class="plus-sign"><span></span><span></span></div><a href="{{ROOT}}platforms/babel.html">Abyss <span style="color:#88898c;font-weight:300;font-size:0.8rem">(Sea)</span></a></div>
                    <div class="menu-link-item" data-group="stratos"><div class="plus-sign"><span></span><span></span></div><a href="{{ROOT}}platforms/apollo.html">Stratos <span style="color:#88898c;font-weight:300;font-size:0.8rem">(Air)</span></a></div>
                    <div class="menu-link-item" data-group="cosmos"><div class="plus-sign"><span></span><span></span></div><a href="{{ROOT}}platforms/spinal-craker.html">Cosmos <span style="color:#88898c;font-weight:300;font-size:0.8rem">(Space)</span></a></div>
                    <div class="menu-link-item" data-group="cyber"><div class="plus-sign"><span></span><span></span></div><a href="{{ROOT}}capabilities/yono-for-developers.html">Cyber <span style="color:#88898c;font-weight:300;font-size:0.8rem">(World Wide Web)</span></a></div>
                </div>
                <div class="col-3">
                    <h3 id="fe-col3-title">&nbsp;</h3>
                    <div class="product-group" id="fe-col3-links"></div>
                </div>
            </div>
        </div>

        <div class="mega-menu-container" id="menu-capabilities">
            <div class="mega-menu-grid">
                <div class="col-1">
                    <h3>Capabilities</h3>
                    <p>Advanced capabilities built on our software platform to drive ontology-powered intelligence, twin visualization, and edge AI across all five elements.</p>
                </div>
                <div class="col-2">
                    <h3>Intelligence & AI</h3>
                    <div class="menu-link-item" data-group="aiml"><div class="plus-sign"><span></span><span></span></div><a href="{{ROOT}}capabilities/ai-ml.html">AI + ML</a></div>
                    <div class="menu-link-item" data-group="edgeai"><div class="plus-sign"><span></span><span></span></div><a href="{{ROOT}}capabilities/edge-ai.html">Edge AI</a></div>
                    <div class="menu-link-item" data-group="data"><div class="plus-sign"><span></span><span></span></div><a href="{{ROOT}}capabilities/data-integration.html">Data Integration</a></div>
                </div>
                <div class="col-3">
                    <h3 id="cap-col3-title">&nbsp;</h3>
                    <div class="product-group" id="cap-col3-links"></div>
                </div>
            </div>
        </div>

        <div class="mega-menu-container" id="menu-company">
            <div class="mega-menu-grid">
                <div class="col-1">
                    <h3>Company</h3>
                    <p>Panteon Technologies is building the operating system for the next century. Explore our mission, impact stories, and the people behind the platforms.</p>
                </div>
                <div class="col-2">
                    <h3>Organization</h3>
                    <div class="menu-link-item" data-group="impact"><div class="plus-sign"><span></span><span></span></div><a href="{{ROOT}}index.html#scroll-content">Alien Inc</a></div>
                    <div class="menu-link-item" data-group="letters"><div class="plus-sign"><span></span><span></span></div><a href="{{ROOT}}letters/shareholder-letter.html">Shareholder Letter</a></div>
                    <div class="menu-link-item" data-group="devs"><div class="plus-sign"><span></span><span></span></div><a href="{{ROOT}}developers/community.html">Developer Community</a></div>
                    <div class="menu-link-item" data-group="pri"><div class="plus-sign"><span></span><span></span></div><a href="{{ROOT}}panteon-research-institute/index.html">Panteon Research Institute</a></div>
                </div>
                <div class="col-3">
                    <h3 id="co-col3-title">&nbsp;</h3>
                    <div class="product-group" id="co-col3-links"></div>
                </div>
            </div>
        </div>
    </header>

    <div class="mobile-drawer" id="mobile-drawer-overlay">
        <div class="mobile-drawer-header">
            <a href="{{ROOT}}index.html" class="logo">
                <svg viewBox="0 0 295 100" role="img" aria-label="Panteon"><use href="#panteon-lockup"/></svg>
            </a>
            <button class="close-drawer-btn" id="close-menu-drawer-btn">×</button>
        </div>
        <div class="mobile-drawer-links">
            <div>
                <p class="mobile-drawer-group-title">Five Elements</p>
                <a href="{{ROOT}}platforms/yono.html" class="mobile-drawer-item">Terra (Land) <div class="plus-sign"><span></span><span></span></div></a>
                <a href="{{ROOT}}platforms/babel.html" class="mobile-drawer-item">Abyss (Sea) <div class="plus-sign"><span></span><span></span></div></a>
                <a href="{{ROOT}}platforms/apollo.html" class="mobile-drawer-item">Stratos (Air) <div class="plus-sign"><span></span><span></span></div></a>
                <a href="{{ROOT}}platforms/spinal-craker.html" class="mobile-drawer-item">Cosmos (Space) <div class="plus-sign"><span></span><span></span></div></a>
                <a href="{{ROOT}}capabilities/yono-for-developers.html" class="mobile-drawer-item">Cyber (Web) <div class="plus-sign"><span></span><span></span></div></a>
            </div>
            <div>
                <p class="mobile-drawer-group-title">Capabilities</p>
                <a href="{{ROOT}}capabilities/ai-ml.html" class="mobile-drawer-item">AI + ML <div class="plus-sign"><span></span><span></span></div></a>
                <a href="{{ROOT}}capabilities/edge-ai.html" class="mobile-drawer-item">Edge AI <div class="plus-sign"><span></span><span></span></div></a>
                <a href="{{ROOT}}capabilities/digital-twin.html" class="mobile-drawer-item">Digital Twin <div class="plus-sign"><span></span><span></span></div></a>
                <a href="{{ROOT}}capabilities/data-integration.html" class="mobile-drawer-item">Data Integration <div class="plus-sign"><span></span><span></span></div></a>
            </div>
            <div>
                <p class="mobile-drawer-group-title">Company</p>
                <a href="{{ROOT}}index.html#scroll-content" class="mobile-drawer-item">Alien Inc</a>
                <a href="{{ROOT}}trust/trust-center.html" class="mobile-drawer-item">Trust Center</a>
                <a href="{{ROOT}}developers/community.html" class="mobile-drawer-item">Developer Community</a>
                <a href="{{ROOT}}panteon-research-institute/index.html" class="mobile-drawer-item">Panteon Research Institute</a>
            </div>
        </div>
        <div class="mobile-drawer-footer">
            <a href="{{ROOT}}login.html" class="get-started-btn">Get Started <span>↖</span></a>
        </div>
    </div>
"""


# ---------------------------------------------------------------------------
# Full site navigation JS (matches the home page exactly)
# ---------------------------------------------------------------------------
NAV_JS = """
    const header = document.getElementById('main-header');
    const scrollProgress = document.getElementById('scroll-bar');
    const scrollThreshold = window.innerHeight * 0.35;

    window.addEventListener('scroll', () => {
        if (window.scrollY >= scrollThreshold) {
            header.classList.add('scrolled');
        } else {
            header.classList.remove('scrolled');
        }
        const totalScroll = document.documentElement.scrollHeight - window.innerHeight;
        scrollProgress.style.width = `${(window.scrollY / totalScroll) * 100}%`;
    });

    const dropdowns = document.querySelectorAll('.nav-item-dropdown');
    const overlay = document.getElementById('mega-menu-overlay');

    const COL3_DATA = {
        'terra': { title: 'PRODUCTS', links: [['{{ROOT}}platforms/terranean-eteology.html','Terranean Eteology'],['{{ROOT}}platforms/terranean-teliology.html','Terranean Teliology'],['{{ROOT}}developers/terranean-documentation.html','Documentation']] },
        'abyss': { title: 'PRODUCTS', links: [['{{ROOT}}platforms/babel.html','Babel Platform'],['{{ROOT}}developers/documentation.html','Documentation'],['{{ROOT}}panteon-research-institute/index.html','Panteon Research Institute'],['https://rousseau.alieninc.tech','Rousseau']] },
        'stratos': { title: 'PRODUCTS', links: [['{{ROOT}}platforms/apollo.html','Apollo Platform'],['{{ROOT}}capabilities/edge-ai.html','Edge AI'],['{{ROOT}}capabilities/dynamic-scheduling.html','Dynamic Scheduling'],['{{ROOT}}panteon-research-institute/index.html','Panteon Research Institute']] },
        'cosmos': { title: 'PRODUCTS', links: [['{{ROOT}}platforms/spinal-craker.html','Spinal Craker'],['{{ROOT}}cmb-product.html','CMB'],['{{ROOT}}capabilities/data-integration.html','Data Integration'],['{{ROOT}}capabilities/digital-twin.html','Digital Twin'],['https://sp.alieninc.tech','Statute & Precedent']] },
        'cyber': { title: 'PRODUCTS', links: [['{{ROOT}}capabilities/yono-for-developers.html','YONO for Developers'],['{{ROOT}}developers/panteon-developers.html','Panteon Developers'],['{{ROOT}}developers/community.html','Developer Community'],['{{ROOT}}capabilities/marketplace.html','Marketplace']] },
        'aiml': { title: 'AI + ML', links: [['{{ROOT}}capabilities/ai-ml.html','Overview'],['{{ROOT}}capabilities/edge-ai.html','Edge AI'],['{{ROOT}}capabilities/data-integration.html','Data Integration'],['{{ROOT}}developers/documentation.html','Documentation']] },
        'edgeai': { title: 'Edge AI', links: [['{{ROOT}}capabilities/edge-ai.html','Overview'],['{{ROOT}}capabilities/ai-ml.html','AI + ML'],['{{ROOT}}platforms/apollo.html','Apollo'],['{{ROOT}}platforms/yono.html','YONO']] },
        'data': { title: 'Data Integration', links: [['{{ROOT}}capabilities/data-integration.html','Overview'],['{{ROOT}}capabilities/digital-twin.html','Digital Twin'],['{{ROOT}}capabilities/marketplace.html','Marketplace'],['{{ROOT}}developers/documentation.html','Documentation']] },
        'impact': { title: 'Alien Inc', links: [['https://rousseau.alieninc.tech','Rousseau'],['https://thedailyartcult.alieninc.tech','The Daily Art Cult'],['https://kmt.alieninc.tech','KMT Consulting Group'],['https://sp.alieninc.tech','Statute & Precedent']] },
        'letters': { title: 'Letters', links: [['{{ROOT}}letters/shareholder-letter.html','Shareholder Letter'],['{{ROOT}}trust/trust-center.html','Trust Center'],['{{ROOT}}developers/community.html','Developer Community']] },
        'devs': { title: 'Developers', links: [['{{ROOT}}developers/panteon-developers.html','Panteon Developers'],['{{ROOT}}developers/community.html','Community'],['{{ROOT}}developers/documentation.html','Documentation'],['{{ROOT}}panteon-research-institute/index.html','Panteon Research Institute'],['{{ROOT}}capabilities/yono-for-developers.html','YONO for Developers']] },
    };

    function populateCol3(menuId, groupKey) {
        const data = COL3_DATA[groupKey];
        if (!data) return;
        const prefixes = { 'menu-five-elements': 'fe', 'menu-capabilities': 'cap', 'menu-company': 'co' };
        const p = prefixes[menuId];
        if (!p) return;
        const titleEl = document.getElementById(p + '-col3-title');
        const linksEl = document.getElementById(p + '-col3-links');
        if (!titleEl || !linksEl) return;
        titleEl.textContent = data.title;
        linksEl.innerHTML = data.links.map(function(l) {
            return '<a href="' + l[0] + '">' + l[1] + '</a>';
        }).join('');
        linksEl.classList.add('has-content');
    }

    function clearCol3(menuId) {
        const prefixes = { 'menu-five-elements': 'fe', 'menu-capabilities': 'cap', 'menu-company': 'co' };
        const p = prefixes[menuId];
        if (!p) return;
        const titleEl = document.getElementById(p + '-col3-title');
        const linksEl = document.getElementById(p + '-col3-links');
        if (titleEl) titleEl.innerHTML = '&nbsp;';
        if (linksEl) { linksEl.innerHTML = ''; linksEl.classList.remove('has-content'); }
    }

    dropdowns.forEach(dropdown => {
        dropdown.addEventListener('mouseenter', () => {
            document.querySelectorAll('.mega-menu-container').forEach(menu => menu.classList.remove('active'));
            const targetId = 'menu-' + dropdown.getAttribute('data-menu');
            const targetMenu = document.getElementById(targetId);
            if (targetMenu) {
                targetMenu.classList.add('active');
                overlay.classList.add('active');
                header.classList.add('menu-active');
            }
        });
    });

    document.querySelectorAll('.mega-menu-container').forEach(menu => {
        menu.querySelectorAll('.menu-link-item[data-group]').forEach(item => {
            item.addEventListener('mouseenter', () => {
                populateCol3(menu.id, item.getAttribute('data-group'));
            });
        });
    });

    header.addEventListener('mouseleave', () => {
        document.querySelectorAll('.mega-menu-container').forEach(menu => {
            menu.classList.remove('active');
            clearCol3(menu.id);
        });
        overlay.classList.remove('active');
        header.classList.remove('menu-active');
    });

    const openDrawerBtn = document.getElementById('open-menu-drawer-btn');
    const closeDrawerBtn = document.getElementById('close-menu-drawer-btn');
    const mobileDrawer = document.getElementById('mobile-drawer-overlay');

    openDrawerBtn.addEventListener('click', () => {
        mobileDrawer.classList.add('active');
    });

    closeDrawerBtn.addEventListener('click', () => {
        mobileDrawer.classList.remove('active');
    });

    document.querySelectorAll('.mobile-drawer-item').forEach(link => {
        link.addEventListener('click', () => {
            mobileDrawer.classList.remove('active');
        });
    });
"""


ARTICLE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Panteon | {{title}}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Space+Grotesk:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="{{ROOT}}styles.css">
    <style>
        {{NAV_CSS}}
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
        .article-body h4{font-size:1.1rem;font-weight:500;margin-bottom:16px;margin-top:32px;color:var(--text-dark)}
        .article-body p{font-size:1rem;line-height:1.75;color:var(--text-muted);margin-bottom:24px;opacity:0;transform:translateY(14px);transition:opacity .6s ease,transform .6s ease}
        .article-body p.in-view{opacity:1;transform:translateY(0)}
        .article-body em{font-style:italic}
        .article-body a{color:var(--text-dark);border-bottom:1px solid var(--text-muted);text-decoration:none}
        .article-body a:hover{color:var(--text-muted)}
        .article-body ul,.article-body ol{margin:0 0 24px 24px;font-size:1rem;line-height:1.75;color:var(--text-muted)}
        .article-body li{margin-bottom:8px}
        .article-body code{font-family:var(--font-mono);font-size:.9em;background:var(--bg-gray);padding:2px 6px;border-radius:2px}
        .article-body ul li::marker,.article-body ol li::marker{color:var(--text-dark)}

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

{{HEADER_HTML}}

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
            <a href="{{ROOT}}panteon-research-institute/index.html" class="get-started-btn" style="background-color:var(--text-dark);color:var(--text-light);border-color:var(--text-dark);padding:14px 40px;font-size:.85rem;text-decoration:none">Back to Articles</a>
        </section>
    </main>

    <dialog class="archive-search" id="archive-search" aria-labelledby="archive-search-heading">
        <div class="search-dialog-inner">
            <div class="search-dialog-top">
                <h2 id="archive-search-heading">Looking for something specific?</h2>
                <button type="button" id="close-archive-search" aria-label="Close search">×</button>
            </div>
            <p>Search is available to authorized personnel through the restricted PRI archive.</p>
            <label for="archive-query">Research archive query</label>
            <input id="archive-query" type="search" placeholder="Enter a title, subject, or author" autocomplete="off">
            <div class="search-dialog-actions">
                <span class="restricted-badge">Restricted access</span>
                <a href="../login.html">Sign in to search <span>→</span></a>
            </div>
        </div>
    </dialog>

    <footer>
        <div class="footer-container">
            <div class="footer-left-branding">
                <p>© 2026 Panteon Technologies Inc.</p>
                <p class="all-rights">All rights reserved.</p>
                <div class="footer-divider-line"></div>
                <a href="{{ROOT}}cookies.html" class="footer-cookie-btn" style="text-decoration:none;">Cookies Settings</a>
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
                        <li><a href="{{ROOT}}panteon-research-institute/index.html">Panteon Research Institute</a></li>
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
                        <li><a href="{{ROOT}}capabilities/ai-ml.html">AI + ML</a></li>
                        <li><a href="{{ROOT}}capabilities/yono-for-developers.html">YONO for Developers</a></li>
                        <li><a href="{{ROOT}}capabilities/data-integration.html">Data Integration</a></li>
                        <li><a href="{{ROOT}}capabilities/digital-twin.html">Digital Twin</a></li>
                        <li><a href="{{ROOT}}capabilities/dynamic-scheduling.html">Dynamic Scheduling</a></li>
                        <li><a href="{{ROOT}}capabilities/edge-ai.html">Edge AI</a></li>
                        <li><a href="{{ROOT}}capabilities/marketplace.html">Marketplace</a></li>
                    </ul>
                </div>
                <div class="footer-links-col">
                    <h4>Documents</h4>
                    <ul>
                        <li><a href="{{ROOT}}developers/community.html">Developer Community</a></li>
                        <li><a href="{{ROOT}}developers/documentation.html">Platform Documentation</a></li>
                        <li><a href="{{ROOT}}developers/panteon-developers.html">Panteon Developers</a></li>
                        <li><a href="{{ROOT}}panteon-research-institute/index.html">Panteon Research Institute</a></li>
                        <li><a href="{{ROOT}}trust/trust-center.html">Trust Center</a></li>
                        <li><a href="{{ROOT}}trust/modern-slavery.html">Modern Slavery Statement</a></li>
                        <li><a href="{{ROOT}}cookies.html">Cookies</a></li>
                        <li><a href="{{ROOT}}trust/privacy-civil-liberties.html">Privacy and Civil Liberties</a></li>
                    </ul>
                </div>
            </div>
        </div>
    </footer>

    <script>
{{NAV_JS}}

        const revealTargets = document.querySelectorAll(
            '.article-body h2, .article-body h3, .article-body h4, .article-body p, .pull-quote, .section-divider, .dark-section, .section-line, .closing-section h2, .closing-meta'
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


LOCKED_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Panteon | Restricted Document</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Space+Grotesk:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="{{ROOT}}styles.css">
    <meta http-equiv="Content-Security-Policy" content="default-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: https:; connect-src 'self' https://*.supabase.co">
    <style>
        {{NAV_CSS}}
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
        .article-body a{color:var(--text-dark);border-bottom:1px solid var(--text-muted);text-decoration:none}
        .article-body a:hover{color:var(--text-muted)}

        .gate-status{font-family:var(--font-mono);font-size:.7rem;letter-spacing:.12em;text-transform:uppercase;color:var(--text-muted);text-align:center;margin-bottom:56px}
        .gate-status.ok{color:#2e7d32}
        .gate-status.locked{color:#b3261e}

        .gate-panel{max-width:640px;margin:0 auto 40px;border:1px solid var(--border-dark);border-left:3px solid #9ab4c1;padding:48px 40px;text-align:center}
        .gate-panel .gate-icon{width:40px;height:40px;color:var(--text-muted);margin:0 auto 24px;display:block}
        .gate-panel h3{font-size:1.4rem;font-weight:400;letter-spacing:-.01em;margin-bottom:16px}
        .gate-panel p{font-size:.95rem;line-height:1.7;color:var(--text-muted);max-width:440px;margin:0 auto 32px}
        .gate-actions{display:flex;flex-direction:column;align-items:center;gap:16px}
        .gate-actions .gate-back{font-size:.78rem;font-weight:600;letter-spacing:.05em;text-transform:uppercase;color:var(--text-muted);text-decoration:none;border-bottom:1px solid var(--text-muted);padding-bottom:2px}
        .gate-actions .gate-back:hover{color:var(--text-dark)}

        .doc-meta{font-family:var(--font-mono);font-size:.7rem;letter-spacing:.12em;text-transform:uppercase;color:#9ab4c1;text-align:center;margin-bottom:56px}
        .doc-placeholder{max-width:640px;margin:0 auto;text-align:center}

        .closing-section{text-align:center;padding:120px 40px 140px;position:relative}
        .closing-section .section-line{width:1px;height:60px;background:linear-gradient(to bottom,#d2d2d7,transparent);margin:0 auto 40px;opacity:0;transition:opacity .8s ease}
        .closing-section .section-line.in-view{opacity:1}
        .closing-section h2{font-size:2rem;font-weight:300;letter-spacing:-.02em;margin-bottom:16px;opacity:0;transform:translateY(12px);transition:opacity .7s ease .2s,transform .7s ease .2s}
        .closing-section h2.in-view{opacity:1;transform:translateY(0)}
        .closing-section .closing-meta{color:var(--text-muted);font-size:.9rem;line-height:1.7;max-width:480px;margin:0 auto 48px;opacity:0;transform:translateY(12px);transition:opacity .7s ease .4s,transform .7s ease .4s}
        .closing-section .closing-meta.in-view{opacity:1;transform:translateY(0)}

        @media(max-width:768px){.cap-hero{padding:140px 24px 80px}.article-body{padding:60px 24px}.gate-panel{padding:36px 24px}}
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

{{HEADER_HTML}}

    <section class="cap-hero">
        <div class="cap-hero-inner">
            <span class="tag">Panteon Research Institute · Restricted Archive</span>
            <h1 id="heroTitle">Restricted Document</h1>
            <p id="heroMeta">Authenticated archive — visible to authorized personnel only.</p>
        </div>
    </section>

    <main class="main-content">
        <div class="article-body">

            <div class="gate-status" id="statusLine">Verifying session&hellip;</div>

            <div class="gate-panel" id="gatePanel" style="display:none">
                <svg class="gate-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
                <h3>Restricted Document</h3>
                <p>This research archive document is restricted to authorized personnel. Sign in with your Panteon credentials to continue.</p>
                <div class="gate-actions">
                    <a class="get-started-btn" id="signInBtn" href="#" style="background-color:var(--text-dark);color:var(--text-light);border-color:var(--text-dark);padding:14px 40px;font-size:.85rem;text-decoration:none">Sign In</a>
                    <a class="gate-back" href="index.html">Back to Research Archive</a>
                </div>
            </div>

            <div id="docContainer" style="display:none">
                <div class="doc-meta" id="docMeta"></div>
                <div id="docBody"></div>
            </div>

        </div>

        <section class="closing-section">
            <div class="section-line"></div>
            <h2>Research Archive</h2>
            <p class="closing-meta">Restricted documents require an authorized Panteon session.</p>
            <a href="{{ROOT}}panteon-research-institute/index.html" class="get-started-btn" style="background-color:var(--text-dark);color:var(--text-light);border-color:var(--text-dark);padding:14px 40px;font-size:.85rem;text-decoration:none">Back to Articles</a>
        </section>
    </main>

    <footer>
        <div class="footer-container">
            <div class="footer-left-branding">
                <p>© 2026 Panteon Technologies Inc.</p>
                <p class="all-rights">All rights reserved.</p>
                <div class="footer-divider-line"></div>
                <a href="{{ROOT}}cookies.html" class="footer-cookie-btn" style="text-decoration:none;">Cookies Settings</a>
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
                        <li><a href="{{ROOT}}panteon-research-institute/index.html">Panteon Research Institute</a></li>
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
                        <li><a href="{{ROOT}}capabilities/ai-ml.html">AI + ML</a></li>
                        <li><a href="{{ROOT}}capabilities/yono-for-developers.html">YONO for Developers</a></li>
                        <li><a href="{{ROOT}}capabilities/data-integration.html">Data Integration</a></li>
                        <li><a href="{{ROOT}}capabilities/digital-twin.html">Digital Twin</a></li>
                        <li><a href="{{ROOT}}capabilities/dynamic-scheduling.html">Dynamic Scheduling</a></li>
                        <li><a href="{{ROOT}}capabilities/edge-ai.html">Edge AI</a></li>
                        <li><a href="{{ROOT}}capabilities/marketplace.html">Marketplace</a></li>
                    </ul>
                </div>
                <div class="footer-links-col">
                    <h4>Documents</h4>
                    <ul>
                        <li><a href="{{ROOT}}developers/community.html">Developer Community</a></li>
                        <li><a href="{{ROOT}}developers/documentation.html">Platform Documentation</a></li>
                        <li><a href="{{ROOT}}developers/panteon-developers.html">Panteon Developers</a></li>
                        <li><a href="{{ROOT}}panteon-research-institute/index.html">Panteon Research Institute</a></li>
                        <li><a href="{{ROOT}}trust/trust-center.html">Trust Center</a></li>
                        <li><a href="{{ROOT}}trust/modern-slavery.html">Modern Slavery Statement</a></li>
                        <li><a href="{{ROOT}}cookies.html">Cookies</a></li>
                        <li><a href="{{ROOT}}trust/privacy-civil-liberties.html">Privacy and Civil Liberties</a></li>
                    </ul>
                </div>
            </div>
        </div>
    </footer>

    <script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>

    <script>
{{NAV_JS}}
    </script>

    <script>
    (function() {
        var SUPABASE_URL = '{{SUPABASE_URL}}';
        var SUPABASE_ANON_KEY = '{{SUPABASE_ANON_KEY}}';
        var supabaseClient = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

        var params = new URLSearchParams(window.location.search);
        var slug = params.get('slug') || '';
        var title = params.get('title') || 'Restricted Document';
        var date = params.get('date') || '';
        var author = params.get('author') || 'Panteon Research Institute';

        var heroTitle = document.getElementById('heroTitle');
        var heroMeta = document.getElementById('heroMeta');
        var statusLine = document.getElementById('statusLine');
        var gatePanel = document.getElementById('gatePanel');
        var docContainer = document.getElementById('docContainer');
        var docMeta = document.getElementById('docMeta');
        var docBody = document.getElementById('docBody');
        var signInBtn = document.getElementById('signInBtn');

        heroTitle.textContent = title;
        heroMeta.textContent = author + (date ? ' · ' + date : '');

        function setStatus(text, cls) {
            statusLine.textContent = text;
            statusLine.className = 'gate-status' + (cls ? ' ' + cls : '');
        }

        function showGate() {
            setStatus('Restricted — sign in required', 'locked');
            gatePanel.style.display = 'block';
            docContainer.style.display = 'none';
            var returnPath = window.location.pathname + window.location.search;
            signInBtn.href = '/login.html?redirect=' + encodeURIComponent(returnPath);
        }

        function showDoc(metaText) {
            setStatus('Authenticated — document unlocked', 'ok');
            gatePanel.style.display = 'none';
            docContainer.style.display = 'block';
            if (metaText && docMeta) docMeta.textContent = metaText;
            else if (docMeta && date) docMeta.textContent = date + ' · ' + author;
        }

        function revealTargets(root) {
            var els = (root || document).querySelectorAll(
                '.article-body h2, .article-body h3, .article-body p, .pull-quote'
            );
            var io = new IntersectionObserver(function(entries) {
                entries.forEach(function(en) {
                    if (en.isIntersecting) {
                        en.target.classList.add('in-view');
                        io.unobserve(en.target);
                    }
                });
            }, { threshold: 0.15, rootMargin: '0px 0px -40px 0px' });
            els.forEach(function(el) { io.observe(el); });
        }

        function showPlaceholder() {
            showDoc();
            docBody.innerHTML =
                '<div class="doc-placeholder">' +
                '<p>The requested document could not be loaded from the restricted archive. Please return to the archive and search again, or contact the research administrator.</p>' +
                '</div>';
            revealTargets(docBody);
        }

        function loadDocument(token) {
            if (!slug) { showDoc(); return; }
            setStatus('Authenticated — loading document&hellip;', 'ok');
            fetch('/api/v1/research/' + encodeURIComponent(slug), {
                headers: {
                    'Authorization': 'Bearer ' + token,
                    'Accept': 'application/json'
                }
            })
            .then(function(resp) {
                return resp.json().then(function(data) { return { ok: resp.ok, data: data }; });
            })
            .then(function(result) {
                if (result.ok && result.data && result.data.html) {
                    docBody.innerHTML = result.data.html;
                    showDoc();
                    revealTargets(docBody);
                } else {
                    showPlaceholder();
                }
            })
            .catch(function() {
                showPlaceholder();
            });
        }

        function restoreSession() {
            return supabaseClient.auth.getSession()
                .then(function(rest) {
                    if (rest.data && rest.data.session) return rest.data.session;
                    var raw = localStorage.getItem('hs_session');
                    if (!raw) return null;
                    var stored = JSON.parse(raw);
                    if (!stored.access_token || !stored.refresh_token) return null;
                    return supabaseClient.auth.setSession({
                        access_token: stored.access_token,
                        refresh_token: stored.refresh_token
                    }).then(function(res) {
                        if (res.error || !res.data.session) return null;
                        return res.data.session;
                    });
                })
                .catch(function() { return null; });
        }

        restoreSession().then(function(session) {
            if (session) loadDocument(session.access_token);
            else showGate();
        });

        supabaseClient.auth.onAuthStateChange(function(event, session) {
            if (session) loadDocument(session.access_token);
        });
    })();
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
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Space+Grotesk:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="{{ROOT}}styles.css">
    <style>
        {{NAV_CSS}}
        .cap-hero{background-color:var(--bg-dark);color:var(--text-light);padding:180px 40px 120px;text-align:center;position:relative;overflow:hidden}
        .cap-hero::before{content:'';position:absolute;top:0;left:50%;transform:translateX(-50%);width:1px;height:80px;background:linear-gradient(to bottom,transparent,rgba(154,180,193,.4),transparent);animation:heroLine 1.8s ease-out forwards;opacity:0}
        @keyframes heroLine{0%{opacity:0;height:0}50%{opacity:1}100%{opacity:1;height:80px}}
        .cap-hero-inner{max-width:900px;margin:0 auto;position:relative;z-index:1}
        .cap-hero .tag{font-family:var(--font-mono);font-size:.7rem;letter-spacing:.12em;text-transform:uppercase;color:#9ab4c1;margin-bottom:20px;display:block;opacity:0;animation:fadeUp .8s ease-out .4s forwards}
        .cap-hero h1{font-size:clamp(2.4rem,5.5vw,4rem);font-weight:300;line-height:1.08;letter-spacing:-.03em;margin-bottom:24px;opacity:0;animation:fadeUp .8s ease-out .7s forwards}
        .cap-hero p{font-size:1.15rem;line-height:1.6;color:rgba(255,255,255,.65);max-width:600px;margin:0 auto;opacity:0;animation:fadeUp .8s ease-out 1s forwards}
        @keyframes fadeUp{from{opacity:0;transform:translateY(20px)}to{opacity:1;transform:translateY(0)}}

        .archive-index{max-width:1400px;margin:0 auto;padding:100px 40px}
        .archive-section{padding:64px 0;border-top:1px solid var(--border-dark)}
        .archive-section:first-child{border-top:0;padding-top:0}
        .archive-section h2{font-size:2.4rem;font-weight:300;letter-spacing:-.02em;margin-bottom:16px}
        .archive-section-intro{max-width:620px;font-size:1rem;line-height:1.65;color:var(--text-muted);margin-bottom:32px}
        .archive-action{display:inline-flex;align-items:center;gap:10px;background:var(--text-dark);border:1px solid var(--text-dark);border-radius:2px;color:var(--text-light);cursor:pointer;font-family:var(--font-mono);font-size:.72rem;font-weight:600;letter-spacing:.08em;padding:13px 18px;text-transform:uppercase;transition:opacity .2s ease}
        .archive-action:hover{opacity:.78}
        .topic-gate{display:flex;align-items:flex-start;justify-content:space-between;gap:32px;padding:32px;border:1px solid var(--border-dark);background:var(--bg-gray)}
        .topic-gate .tag{display:block;font-family:var(--font-mono);font-size:.7rem;letter-spacing:.12em;text-transform:uppercase;color:var(--text-muted);margin-bottom:10px}
        .topic-gate h3{font-size:1.25rem;font-weight:400;letter-spacing:-.01em;margin-bottom:8px}
        .topic-gate p{max-width:600px;font-size:.95rem;line-height:1.6;color:var(--text-muted)}
        .year-picker{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:30px}
        .year-picker button{min-width:66px;padding:11px 12px;background:transparent;border:1px solid var(--border-dark);border-radius:2px;color:var(--text-dark);cursor:pointer;font-family:var(--font-mono);font-size:.72rem;letter-spacing:.06em;transition:background-color .2s ease,color .2s ease}
        .year-picker button:hover,.year-picker button[aria-pressed="true"]{background:var(--text-dark);border-color:var(--text-dark);color:var(--text-light)}
        .month-access{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));border-top:1px solid var(--border-dark);border-left:1px solid var(--border-dark)}
        .month-access button{min-height:88px;padding:14px 10px;background:var(--bg-light);border:0;border-right:1px solid var(--border-dark);border-bottom:1px solid var(--border-dark);color:var(--text-muted);font-family:var(--font-mono);font-size:.68rem;letter-spacing:.08em;text-transform:uppercase}
        .month-access button[disabled]{cursor:not-allowed;opacity:.45}
        .month-access .available-month{color:var(--text-dark);cursor:pointer;position:relative;transition:background-color .2s ease}
        .month-access .available-month:hover{background:var(--bg-gray)}
        .month-access .available-month::after{content:'Restricted';display:block;margin-top:8px;font-size:.56rem;color:var(--text-muted)}
        .archive-status{margin-top:18px;font-size:.85rem;color:var(--text-muted)}
        dialog.archive-search{width:min(560px,calc(100% - 48px));margin:auto;padding:0;border:1px solid var(--border-dark);border-radius:2px;background:var(--bg-light);color:var(--text-dark)}
        dialog.archive-search::backdrop{background:rgba(7,8,9,.72)}
        .search-dialog-inner{padding:36px}
        .search-dialog-top{display:flex;justify-content:space-between;gap:20px;align-items:flex-start;margin-bottom:24px}
        .search-dialog-top h2{font-size:1.8rem;font-weight:300;letter-spacing:-.02em}
        .search-dialog-top button{background:transparent;border:0;color:var(--text-dark);cursor:pointer;font-size:1.4rem;line-height:1}
        .search-dialog-inner p{font-size:.95rem;line-height:1.6;color:var(--text-muted);margin-bottom:20px}
        .search-dialog-inner label{display:block;font-family:var(--font-mono);font-size:.68rem;letter-spacing:.1em;text-transform:uppercase;margin-bottom:8px}
        .search-dialog-inner input{width:100%;padding:14px;border:1px solid var(--border-dark);border-radius:2px;font:inherit;color:var(--text-dark);margin-bottom:18px}
        .search-dialog-actions{display:flex;align-items:center;justify-content:space-between;gap:16px}
        .restricted-badge{display:inline-block;font-family:var(--font-mono);font-size:.6rem;letter-spacing:.12em;text-transform:uppercase;color:var(--text-muted);border:1px solid var(--border-dark);padding:4px 8px;border-radius:2px}
        .search-dialog-actions a{font-family:var(--font-mono);font-size:.7rem;letter-spacing:.08em;text-transform:uppercase;color:var(--text-dark);text-decoration:none;border-bottom:1px solid var(--text-muted);padding-bottom:2px}

        .mission-card{max-width:1400px;margin:0 auto;padding:0 40px 100px}
        .mission-card-inner{border:1px solid var(--border-dark);border-radius:2px;padding:48px;background:var(--bg-light)}
        .mission-card-inner h3{font-size:1.3rem;font-weight:400;margin-bottom:12px}
        .mission-card-inner p{font-size:.95rem;line-height:1.55;color:var(--text-muted);margin-bottom:16px}
        .mission-card-inner a{display:inline-flex;align-items:center;gap:8px;font-size:.8rem;font-weight:600;letter-spacing:.05em;text-transform:uppercase;color:var(--text-dark);border-bottom:1px solid var(--text-muted);padding-bottom:2px;text-decoration:none;margin-top:8px}

        @media(max-width:1024px){.month-access{grid-template-columns:repeat(6,minmax(0,1fr))}}
        @media(max-width:768px){.cap-hero{padding:140px 24px 80px}.archive-index{padding:60px 24px}.archive-section{padding:48px 0}.topic-gate{display:block;padding:24px}.topic-gate .archive-action{margin-top:24px}.month-access{grid-template-columns:repeat(3,minmax(0,1fr))}}
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

{{HEADER_HTML}}

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

        <div class="archive-index">
            <section class="archive-section" aria-labelledby="topic-heading">
                <h2 id="topic-heading">Articles by Topic</h2>
                <p class="archive-section-intro">The PRI subject index is maintained inside the restricted archive. Sign in to search across the institute’s complete research record.</p>
                <div class="topic-gate">
                    <div>
                        <span class="tag">Restricted archive</span>
                        <h3>Research is available to authorized personnel.</h3>
                        <p>Topic classifications and document records are not published on this site.</p>
                    </div>
                    <button class="archive-action" type="button" data-open-search>Search the archive <span>→</span></button>
                </div>
            </section>

            <section class="archive-section" aria-labelledby="date-heading">
                <h2 id="date-heading">Articles by Date</h2>
                <p class="archive-section-intro">Select a year. August is the only month available for archive navigation; document access remains restricted from the institute’s founding on December 22, 2016.</p>
                <div class="year-picker" aria-label="Select an archive year">
                    <button type="button" aria-pressed="true" data-year="2026">2026</button>
                    <button type="button" aria-pressed="false" data-year="2025">2025</button>
                    <button type="button" aria-pressed="false" data-year="2024">2024</button>
                    <button type="button" aria-pressed="false" data-year="2023">2023</button>
                    <button type="button" aria-pressed="false" data-year="2022">2022</button>
                    <button type="button" aria-pressed="false" data-year="2021">2021</button>
                    <button type="button" aria-pressed="false" data-year="2020">2020</button>
                    <button type="button" aria-pressed="false" data-year="2019">2019</button>
                    <button type="button" aria-pressed="false" data-year="2018">2018</button>
                    <button type="button" aria-pressed="false" data-year="2017">2017</button>
                    <button type="button" aria-pressed="false" data-year="2016">2016</button>
                </div>
                <div class="month-access" aria-label="Archive months">
                    <button type="button" disabled>Jan</button><button type="button" disabled>Feb</button><button type="button" disabled>Mar</button><button type="button" disabled>Apr</button><button type="button" disabled>May</button><button type="button" disabled>Jun</button><button type="button" disabled>Jul</button>
                    <button type="button" class="available-month" data-open-search>Aug</button>
                    <button type="button" disabled>Sep</button><button type="button" disabled>Oct</button><button type="button" disabled>Nov</button><button type="button" disabled>Dec</button>
                </div>
                <p class="archive-status" id="archive-status">Selected: 2026 · August archive navigation requires authorization.</p>
            </section>
        </div>

    </main>

    <footer>
        <div class="footer-container">
            <div class="footer-left-branding">
                <p>© 2026 Panteon Technologies Inc.</p>
                <p class="all-rights">All rights reserved.</p>
                <div class="footer-divider-line"></div>
                <a href="{{ROOT}}cookies.html" class="footer-cookie-btn" style="text-decoration:none;">Cookies Settings</a>
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
                        <li><a href="{{ROOT}}panteon-research-institute/index.html">Panteon Research Institute</a></li>
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
                        <li><a href="{{ROOT}}capabilities/ai-ml.html">AI + ML</a></li>
                        <li><a href="{{ROOT}}capabilities/yono-for-developers.html">YONO for Developers</a></li>
                        <li><a href="{{ROOT}}capabilities/data-integration.html">Data Integration</a></li>
                        <li><a href="{{ROOT}}capabilities/digital-twin.html">Digital Twin</a></li>
                        <li><a href="{{ROOT}}capabilities/dynamic-scheduling.html">Dynamic Scheduling</a></li>
                        <li><a href="{{ROOT}}capabilities/edge-ai.html">Edge AI</a></li>
                        <li><a href="{{ROOT}}capabilities/marketplace.html">Marketplace</a></li>
                    </ul>
                </div>
                <div class="footer-links-col">
                    <h4>Documents</h4>
                    <ul>
                        <li><a href="{{ROOT}}developers/community.html">Developer Community</a></li>
                        <li><a href="{{ROOT}}developers/documentation.html">Platform Documentation</a></li>
                        <li><a href="{{ROOT}}developers/panteon-developers.html">Panteon Developers</a></li>
                        <li><a href="{{ROOT}}panteon-research-institute/index.html">Panteon Research Institute</a></li>
                        <li><a href="{{ROOT}}trust/trust-center.html">Trust Center</a></li>
                        <li><a href="{{ROOT}}trust/modern-slavery.html">Modern Slavery Statement</a></li>
                        <li><a href="{{ROOT}}cookies.html">Cookies</a></li>
                        <li><a href="{{ROOT}}trust/privacy-civil-liberties.html">Privacy and Civil Liberties</a></li>
                    </ul>
                </div>
            </div>
        </div>
    </footer>

    <script>
{{NAV_JS}}
        (function () {
            var dialog = document.getElementById('archive-search');
            var status = document.getElementById('archive-status');
            var yearButtons = document.querySelectorAll('[data-year]');
            document.querySelectorAll('[data-open-search], [data-research-search]').forEach(function (button) {
                button.addEventListener('click', function () { dialog.showModal(); });
            });
            document.getElementById('close-archive-search').addEventListener('click', function () { dialog.close(); });
            yearButtons.forEach(function (button) {
                button.addEventListener('click', function () {
                    yearButtons.forEach(function (item) { item.setAttribute('aria-pressed', 'false'); });
                    button.setAttribute('aria-pressed', 'true');
                    status.textContent = 'Selected: ' + button.getAttribute('data-year') + ' · August archive navigation requires authorization.';
                });
            });
        })();
    </script>
</body>
</html>"""


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


def extract_h1(body):
    for line in body.split("\n"):
        s = line.strip()
        if s.startswith("# ") and s.strip("#").strip():
            return s[2:].strip()
    return None


def slugify(title):
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug or "untitled-article"


def _inline_format(text):
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    text = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2">\1</a>', text)
    return text


def md_to_html(body, bare_mode=False):
    """Convert the article body to HTML.

    bare_mode=True means the page title came from the first '# ' line, so that
    line is consumed as the title and every heading below it renders one level
    up (## -> h2, ### -> h3), which matches how the articles are actually
    written. bare_mode=False means the title came from front-matter, so body
    headings keep the classic offset (# -> h2, ## -> h3).
    """
    lines = body.strip().split("\n")
    html_parts = []
    current_paragraph = []
    in_list = None

    def flush_paragraph():
        if current_paragraph:
            html_parts.append(f"<p>{_inline_format(' '.join(current_paragraph))}</p>")
            current_paragraph.clear()

    def close_list():
        nonlocal in_list
        if in_list:
            html_parts.append(f"</{in_list}>")
            in_list = None

    for line in lines:
        stripped = line.strip()

        if stripped == "":
            flush_paragraph()
            close_list()
            continue

        if stripped == "---":
            flush_paragraph()
            close_list()
            html_parts.append('<div class="section-divider"></div>')
            continue

        if stripped.startswith(">"):
            flush_paragraph()
            close_list()
            quote_text = _inline_format(stripped.lstrip("> ").strip())
            html_parts.append(f'<blockquote class="pull-quote">{quote_text}</blockquote>')
            continue

        m = HEADING_RE.match(stripped)
        if m:
            flush_paragraph()
            close_list()
            hashes, text = m.group(1), m.group(2).strip()
            n = len(hashes)
            if bare_mode and n == 1:
                continue
            if bare_mode:
                level = n if n >= 2 else 2
            else:
                level = n + 1
            html_parts.append(f"<h{level}>{_inline_format(text)}</h{level}>")
            continue

        um = UL_ITEM_RE.match(stripped)
        if um:
            flush_paragraph()
            if in_list != "ul":
                close_list()
                html_parts.append("<ul>")
                in_list = "ul"
            html_parts.append(f"<li>{_inline_format(um.group(1).strip())}</li>")
            continue

        om = OL_ITEM_RE.match(stripped)
        if om:
            flush_paragraph()
            if in_list != "ol":
                close_list()
                html_parts.append("<ol>")
                in_list = "ol"
            html_parts.append(f"<li>{_inline_format(om.group(1).strip())}</li>")
            continue

        if in_list:
            close_list()
        current_paragraph.append(stripped)

    flush_paragraph()
    close_list()
    return "\n".join(html_parts)


def get_excerpt(body, max_chars=180):
    """First real paragraph (skips the title heading) -> hero + listing excerpt."""
    for block in body.strip().split("\n\n"):
        lines = block.strip().split("\n")
        if not lines:
            continue
        first = lines[0].strip()
        if not first or first.startswith(("#", ">", "---")):
            continue
        if first.startswith(("- ", "* ", "+ ")) or re.match(r"^\d+\.\s", first):
            continue
        text = " ".join(
            l.strip() for l in lines
            if l.strip() and not l.strip().startswith(("#", ">", "---"))
        )
        text = re.sub(r"[#*_`>]", "", text)
        text = re.sub(r"\[(.+?)\]\((.+?)\)", r"\1", text)
        text = text.strip()
        if len(text) > max_chars:
            return text[:max_chars].rsplit(" ", 1)[0] + "…"
        return text
    return ""


def build_article(source_path):
    with open(source_path, "r", encoding="utf-8") as f:
        raw = f.read()

    fm, body = parse_frontmatter(raw)

    title = fm.get("title")
    bare_mode = not title
    if bare_mode:
        title = extract_h1(body) or "Untitled Article"

    tag = fm.get("tag", "Panteon Research Institute")
    date = fm.get("date", datetime.now().strftime("%Y-%m-%d"))
    author = fm.get("author", "Patrick Neil A.")
    slug = fm.get("slug") or slugify(title)
    # The PRI archive begins on its founding day. Every document dated from
    # that day onward is served only through the authenticated archive.
    locked = bool(fm.get("locked", False)) or date >= ARCHIVE_LOCK_DATE

    excerpt = get_excerpt(body)
    article_html = md_to_html(body, bare_mode=bare_mode)

    root = "../../"
    html_out = ARTICLE_TEMPLATE
    html_out = html_out.replace("{{NAV_CSS}}", NAV_CSS)
    html_out = html_out.replace("{{HEADER_HTML}}", HEADER_HTML)
    html_out = html_out.replace("{{NAV_JS}}", NAV_JS)
    html_out = html_out.replace("{{ROOT}}", root)
    html_out = html_out.replace("{{title}}", esc(title))
    html_out = html_out.replace("{{tag}}", esc(tag))
    html_out = html_out.replace("{{excerpt}}", esc(excerpt))
    html_out = html_out.replace("{{date}}", esc(date))
    html_out = html_out.replace("{{author}}", esc(author))
    html_out = html_out.replace("{{article_html}}", article_html)

    if not locked:
        out_path = os.path.join(ARTICLES_DIR, f"{slug}.html")
        os.makedirs(ARTICLES_DIR, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html_out)
    else:
        # Do not leave a previously generated public copy reachable after a
        # document enters the restricted archive.
        public_copy = os.path.join(ARTICLES_DIR, f"{slug}.html")
        if os.path.exists(public_copy):
            os.remove(public_copy)

    return {"slug": slug, "title": title, "date": date, "author": author,
            "excerpt": excerpt, "locked": locked, "html": article_html}


def _public_row(a):
    return (
        f'                    <a href="articles/{esc(a["slug"])}.html" class="article-row">\n'
        f'                        <div>\n'
        f'                            <div class="article-row-title">{esc(a["title"])}</div>\n'
        f'                            <div class="article-row-meta">{esc(a["date"])} · {esc(a["author"])}</div>\n'
        f"                        </div>\n"
        f'                        <div class="article-row-arrow">→</div>\n'
        f"                    </a>"
    )


def _locked_row(a):
    href = ("locked.html?slug=%s&title=%s&date=%s&author=%s" % (
        quote(a["slug"]), quote(a["title"]), quote(a["date"]), quote(a["author"])))
    return (
        f'                    <a href="{href}" class="article-row locked">\n'
        f'                        <div>\n'
        f'                            <div class="article-row-title">{LOCK_ICON}{esc(a["title"])}</div>\n'
        f'                            <div class="article-row-meta">{esc(a["date"])} · {esc(a["author"])}'
        f'<span class="restricted-badge">Restricted</span></div>\n'
        f"                        </div>\n"
        f'                        <div class="article-row-arrow">→</div>\n'
        f"                    </a>"
    )


def build_index(articles, locked_articles=None):
    root = "../"
    html = INDEX_TEMPLATE
    html = html.replace("{{NAV_CSS}}", NAV_CSS)
    html = html.replace("{{HEADER_HTML}}", HEADER_HTML)
    html = html.replace("{{NAV_JS}}", NAV_JS)
    html = html.replace("{{ROOT}}", root)
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        f.write(html)


def write_locked_manifest(locked_articles):
    manifest = {}
    for a in sorted(locked_articles, key=lambda x: x["date"]):
        year = a["date"][:4]
        manifest.setdefault(year, []).append({
            "slug": a["slug"], "title": a["title"],
            "date": a["date"], "author": a["author"],
        })
    os.makedirs(PRIVATE_DIR, exist_ok=True)
    with open(LOCKED_MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)


def write_locked_content(locked_articles):
    """Render locked doc bodies to the private store (outside the public web
    root) for the Phase 4 backend endpoint GET /api/v1/research/{slug}."""
    if not locked_articles:
        return
    os.makedirs(PRIVATE_DIR, exist_ok=True)
    for a in locked_articles:
        payload = {
            "slug": a["slug"], "title": a["title"],
            "date": a["date"], "author": a["author"],
            "html": a.get("html", ""),
        }
        out_path = os.path.join(PRIVATE_DIR, f"{a['slug']}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"  Locked content written to private store: {PRIVATE_DIR} "
          f"({len(locked_articles)} doc(s))")


def build_locked_guard():
    html_out = LOCKED_TEMPLATE
    html_out = html_out.replace("{{NAV_CSS}}", NAV_CSS)
    html_out = html_out.replace("{{HEADER_HTML}}", HEADER_HTML)
    html_out = html_out.replace("{{NAV_JS}}", NAV_JS)
    html_out = html_out.replace("{{ROOT}}", "../")
    html_out = html_out.replace("{{SUPABASE_URL}}", SUPABASE_URL)
    html_out = html_out.replace("{{SUPABASE_ANON_KEY}}", SUPABASE_ANON_KEY)
    with open(LOCKED_PAGE_PATH, "w", encoding="utf-8") as f:
        f.write(html_out)


def main():
    if len(sys.argv) > 1:
        files = [os.path.join(SOURCE_DIR, f) for f in sys.argv[1:]]
    else:
        files = sorted(glob.glob(os.path.join(SOURCE_DIR, "*.md")))

    if not files:
        print("No .md files found in source/. Drop one there and run again.")
        return

    articles = []
    locked_articles = []
    for fp in files:
        print(f"Publishing {os.path.basename(fp)}...")
        meta = build_article(fp)
        if meta.get("locked"):
            print(f"  → LOCKED archive doc, not published publicly")
            locked_articles.append(meta)
            continue
        articles.append(meta)
        print(f"  → articles/{meta['slug']}.html")

    existing = glob.glob(os.path.join(ARTICLES_DIR, "*.html"))
    existing_slugs = {a["slug"] for a in articles}
    for ep in existing:
        slug = os.path.splitext(os.path.basename(ep))[0]
        if slug not in existing_slugs:
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

    build_index(articles, locked_articles)
    write_locked_manifest(locked_articles)
    write_locked_content(locked_articles)
    build_locked_guard()
    print(f"\nIndex updated: {len(articles)} public article(s) listed, "
          f"{len(locked_articles)} locked archive doc(s). Manifest written to the private archive store.")


if __name__ == "__main__":
    main()
