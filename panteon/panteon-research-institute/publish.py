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
import html
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCE_DIR = os.path.join(BASE_DIR, "source")
ARTICLES_DIR = os.path.join(BASE_DIR, "articles")
INDEX_PATH = os.path.join(BASE_DIR, "index.html")

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
                    <button class="header-icon-box" aria-label="Search button">
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

    out_path = os.path.join(ARTICLES_DIR, f"{slug}.html")
    os.makedirs(ARTICLES_DIR, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_out)

    return {"slug": slug, "title": title, "date": date, "author": author, "excerpt": excerpt}


def build_index(articles):
    rows = []
    for a in sorted(articles, key=lambda x: x["date"], reverse=True):
        rows.append(
            f'                <a href="articles/{esc(a["slug"])}.html" class="article-row">\n'
            f'                    <div>\n'
            f'                        <div class="article-row-title">{esc(a["title"])}</div>\n'
            f'                        <div class="article-row-meta">{esc(a["date"])} · {esc(a["author"])}</div>\n'
            f"                    </div>\n"
            f'                    <div class="article-row-arrow">→</div>\n'
            f"                </a>"
        )

    root = "../"
    html = INDEX_TEMPLATE
    html = html.replace("{{NAV_CSS}}", NAV_CSS)
    html = html.replace("{{HEADER_HTML}}", HEADER_HTML)
    html = html.replace("{{NAV_JS}}", NAV_JS)
    html = html.replace("{{ROOT}}", root)
    html = html.replace("{{article_rows}}", "\n".join(rows))
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

    build_index(articles)
    print(f"\nIndex updated: {len(articles)} article(s) listed.")


if __name__ == "__main__":
    main()
