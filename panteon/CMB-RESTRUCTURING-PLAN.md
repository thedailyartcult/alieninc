# CMB Section Restructuring Plan
## Admin.html Design Language Alignment

**Created:** 2026-08-10  
**Status:** Planning Phase  
**Session ID:** ses_01KZNQVTX59NNY1GRKMTXZZVC1

---

## Executive Summary

Restructure the CMB section in `admin.html` (6 pages: dashboard, status, workspaces, history, analytics, sharing) to match the Panteon design language established in `index.html`. **No functionality changes** — only structural design, visual hierarchy, animations, and component patterns.

---

## Current State Analysis

### CMB Pages in admin.html (Lines 1689-1812)

1. **cmb-dashboard** (Memory Dashboard) — iframe embed
2. **cmb-status** (System Status) — 4 stat cards + 2 content cards + architecture card
3. **cmb-workspaces** (Workspaces) — header + savings card + workspace grid
4. **cmb-history** (Timeline) — search form + results card
5. **cmb-analytics** (Analytics) — header + tab buttons + content card
6. **cmb-sharing** (Memory Sharing) — not shown in excerpt but exists

### Current Design Issues

- Basic `.card` containers with minimal visual hierarchy
- Simple `.grid-4`, `.grid-2` layouts without sophistication
- Inline styles scattered throughout (violates AGENTS.md)
- No section header patterns (`.section-header-bar` + `.section-badge`)
- No reveal animations (`.reveal-text-line`)
- Buttons lack refinement (no hover transforms, no proper spacing)
- Typography doesn't leverage Space Grotesk font-weight 300 for headers
- Missing visual separators and border treatments from index.html
- No parallax or interactive elements

---

## Target Design Language (from index.html)

### Key Patterns to Apply

#### 1. Section Header Pattern
```css
.section-header-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid var(--border-light);
    padding-bottom: 16px;
    margin-bottom: 30px;
}

.section-header-bar h2 {
    font-family: var(--font-tech);
    font-size: 1.8rem;
    font-weight: 300;
    letter-spacing: -0.02em;
    color: var(--text-light);
}

.section-badge {
    font-family: var(--font-mono);
    font-size: 0.65rem;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    background-color: var(--accent-neon);
    color: var(--bg-dark);
    padding: 6px 14px;
    font-weight: 600;
}
```

#### 2. Card Pattern (Software Card Style)
```css
.cmb-card {
    background-color: var(--bg-card);
    border: 1px solid var(--border-light);
    display: flex;
    flex-direction: column;
    padding: 24px;
    position: relative;
    transition: border-color 0.3s, box-shadow 0.3s, transform 0.3s;
}

.cmb-card:hover {
    border-color: var(--accent-neon);
    box-shadow: 0 8px 24px rgba(223, 241, 64, 0.08);
    transform: translateY(-2px);
}

.cmb-card .card-num-bar {
    display: flex;
    align-items: center;
    gap: 8px;
    border-bottom: 1px solid var(--border-light);
    padding-bottom: 12px;
    margin-bottom: 16px;
}

.cmb-card .card-num-bar .square-block {
    width: 6px;
    height: 6px;
    background-color: var(--accent-neon);
}

.cmb-card .card-num-bar .num-tag {
    font-family: var(--font-tech);
    font-size: 0.75rem;
    font-weight: 600;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.08em;
}
```

#### 3. Reveal Animation Pattern
```css
.reveal-text-line {
    display: inline-block;
    transition: transform 1.1s cubic-bezier(0.16, 1, 0.3, 1), 
                filter 1.1s ease, 
                opacity 1.1s ease;
    will-change: transform, filter, opacity;
    transform: translate3d(0, 0, 0);
    opacity: 1;
    filter: blur(0px);
}

.reveal-text-line.hidden-reveal {
    transform: translate3d(0, 115%, 0) scale(1.02);
    filter: blur(6px);
    opacity: 0;
}
```

#### 4. Button Pattern
```css
.cmb-btn {
    background-color: transparent;
    color: var(--text-light);
    border: 1px solid var(--border-light);
    padding: 10px 24px;
    font-family: var(--font-tech);
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    display: inline-flex;
    align-items: center;
    gap: 8px;
    transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
    cursor: pointer;
}

.cmb-btn:hover {
    background-color: var(--accent-neon);
    color: var(--bg-dark);
    border-color: var(--accent-neon);
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(223, 241, 64, 0.2);
}

.cmb-btn-primary {
    background-color: var(--accent-neon);
    color: var(--bg-dark);
    border-color: var(--accent-neon);
}

.cmb-btn-primary:hover {
    background-color: var(--text-light);
    border-color: var(--text-light);
}
```

#### 5. Grid Pattern
```css
.cmb-grid-2 {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 24px;
}

.cmb-grid-4 {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 20px;
}

@media (max-width: 1200px) {
    .cmb-grid-4 { grid-template-columns: repeat(2, 1fr); }
}

@media (max-width: 768px) {
    .cmb-grid-2, .cmb-grid-4 { grid-template-columns: 1fr; }
}
```

#### 6. Stat Card Pattern
```css
.stat-card {
    background-color: var(--bg-card);
    border: 1px solid var(--border-light);
    padding: 20px;
    position: relative;
    overflow: hidden;
}

.stat-card::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    width: 3px;
    height: 100%;
    background-color: var(--accent-neon);
}

.stat-card .stat-label {
    font-family: var(--font-mono);
    font-size: 0.65rem;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: var(--text-muted);
    margin-bottom: 8px;
}

.stat-card .stat-value {
    font-family: var(--font-tech);
    font-size: 2rem;
    font-weight: 300;
    color: var(--text-light);
    letter-spacing: -0.02em;
}

.stat-card .stat-sub {
    font-size: 0.75rem;
    color: var(--text-muted);
    margin-top: 4px;
}
```

---

## Step-by-Step Restructuring Plan

### Phase 1: CSS Foundation (Lines 12-509)

**Step 1.1:** Add new CMB-specific design classes after existing styles (line ~508)

```css
/* ===== CMB SECTION DESIGN LANGUAGE ===== */

/* Section Headers */
.cmb-section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid var(--border-light);
    padding-bottom: 16px;
    margin-bottom: 30px;
}

.cmb-section-title {
    font-family: var(--font-tech);
    font-size: 1.8rem;
    font-weight: 300;
    letter-spacing: -0.02em;
    color: var(--text-light);
}

.cmb-section-badge {
    font-family: var(--font-mono);
    font-size: 0.65rem;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    background-color: var(--accent-neon);
    color: var(--bg-dark);
    padding: 6px 14px;
    font-weight: 600;
}

/* Cards */
.cmb-card {
    background-color: var(--bg-card);
    border: 1px solid var(--border-light);
    padding: 24px;
    transition: border-color 0.3s, box-shadow 0.3s, transform 0.3s;
}

.cmb-card:hover {
    border-color: var(--accent-neon);
    box-shadow: 0 8px 24px rgba(223, 241, 64, 0.08);
    transform: translateY(-2px);
}

.cmb-card-header {
    display: flex;
    align-items: center;
    gap: 8px;
    border-bottom: 1px solid var(--border-light);
    padding-bottom: 12px;
    margin-bottom: 16px;
}

.cmb-card-header .square-block {
    width: 6px;
    height: 6px;
    background-color: var(--accent-neon);
}

.cmb-card-header .card-label {
    font-family: var(--font-tech);
    font-size: 0.75rem;
    font-weight: 600;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.08em;
}

/* Stat Cards */
.cmb-stat-card {
    background-color: var(--bg-card);
    border: 1px solid var(--border-light);
    padding: 20px;
    position: relative;
    overflow: hidden;
}

.cmb-stat-card::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    width: 3px;
    height: 100%;
    background-color: var(--accent-neon);
}

.cmb-stat-label {
    font-family: var(--font-mono);
    font-size: 0.65rem;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: var(--text-muted);
    margin-bottom: 8px;
}

.cmb-stat-value {
    font-family: var(--font-tech);
    font-size: 2rem;
    font-weight: 300;
    color: var(--text-light);
    letter-spacing: -0.02em;
}

.cmb-stat-sub {
    font-size: 0.75rem;
    color: var(--text-muted);
    margin-top: 4px;
}

/* Grids */
.cmb-grid-2 {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 24px;
}

.cmb-grid-4 {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 20px;
}

/* Buttons */
.cmb-btn {
    background-color: transparent;
    color: var(--text-light);
    border: 1px solid var(--border-light);
    padding: 10px 24px;
    font-family: var(--font-tech);
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    display: inline-flex;
    align-items: center;
    gap: 8px;
    transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
    cursor: pointer;
}

.cmb-btn:hover {
    background-color: var(--accent-neon);
    color: var(--bg-dark);
    border-color: var(--accent-neon);
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(223, 241, 64, 0.2);
}

.cmb-btn-primary {
    background-color: var(--accent-neon);
    color: var(--bg-dark);
    border-color: var(--accent-neon);
}

.cmb-btn-primary:hover {
    background-color: var(--text-light);
    border-color: var(--text-light);
}

.cmb-btn-sm {
    padding: 6px 16px;
    font-size: 0.7rem;
}

/* Reveal Animation */
.cmb-reveal {
    display: inline-block;
    transition: transform 1.1s cubic-bezier(0.16, 1, 0.3, 1), 
                filter 1.1s ease, 
                opacity 1.1s ease;
    will-change: transform, filter, opacity;
    transform: translate3d(0, 0, 0);
    opacity: 1;
    filter: blur(0px);
}

.cmb-reveal.hidden-reveal {
    transform: translate3d(0, 115%, 0) scale(1.02);
    filter: blur(6px);
    opacity: 0;
}

/* Responsive */
@media (max-width: 1200px) {
    .cmb-grid-4 { grid-template-columns: repeat(2, 1fr); }
}

@media (max-width: 768px) {
    .cmb-grid-2, .cmb-grid-4 { grid-template-columns: 1fr; }
    .cmb-section-title { font-size: 1.4rem; }
}
```

**Step 1.2:** Add JavaScript for reveal animations (after line ~3940)

```javascript
// CMB Reveal Animation Engine
function initCMBRevealAnimations() {
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.remove('hidden-reveal');
            }
        });
    }, { threshold: 0.1 });

    document.querySelectorAll('.cmb-reveal').forEach(el => {
        el.classList.add('hidden-reveal');
        observer.observe(el);
    });
}

// Call on page load
document.addEventListener('DOMContentLoaded', initCMBRevealAnimations);
```

---

### Phase 2: Restructure Each CMB Page

#### Page 1: cmb-dashboard (Lines 1689-1703)

**Current Structure:**
```html
<div class="page" id="page-cmb-dashboard">
    <div style="display:flex;flex-direction:column;height:calc(100vh - 68px)">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
            <div style="display:flex;align-items:center;gap:10px">
                <span class="status-dot" id="cmbEngineDot"></span>
                <span id="cmbEngineStatus">Checking engine...</span>
            </div>
            <div style="display:flex;gap:8px">
                <button class="btn btn-sm" onclick="reloadCMB()">Reload</button>
                <button class="btn btn-sm" onclick="openCMBExternal()">Open Full ↗</button>
            </div>
        </div>
        <iframe id="cmbFrame" style="..."></iframe>
    </div>
</div>
```

**New Structure:**
```html
<div class="page" id="page-cmb-dashboard">
    <div style="display:flex;flex-direction:column;height:calc(100vh - 68px)">
        <!-- Section Header -->
        <div class="cmb-section-header">
            <div style="display:flex;align-items:center;gap:16px">
                <h2 class="cmb-section-title cmb-reveal">Memory Dashboard</h2>
                <div style="display:flex;align-items:center;gap:10px">
                    <span class="status-dot" id="cmbEngineDot"></span>
                    <span style="font-family:var(--font-mono);font-size:0.75rem;color:var(--text-muted)" id="cmbEngineStatus">Checking engine...</span>
                </div>
            </div>
            <div style="display:flex;gap:12px">
                <button class="cmb-btn cmb-btn-sm" onclick="reloadCMB()">
                    <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M2 8a6 6 0 0 1 10.5-4M14 8a6 6 0 0 1-10.5 4"/>
                        <path d="M12 2v4h-4M4 14v-4h4"/>
                    </svg>
                    Reload
                </button>
                <button class="cmb-btn cmb-btn-sm" onclick="openCMBExternal()">
                    Open Full
                    <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M6 2h8v8M14 2L6 10"/>
                    </svg>
                </button>
            </div>
        </div>
        
        <!-- iframe Container -->
        <div class="cmb-card" style="flex:1;padding:0;overflow:hidden">
            <iframe id="cmbFrame" style="width:100%;height:100%;border:none;background:var(--bg-card)" 
                    sandbox="allow-scripts allow-same-origin allow-forms allow-popups" 
                    title="CMB Memory Dashboard"></iframe>
        </div>
    </div>
</div>
```

**Changes:**
- Replace inline flex styles with `.cmb-section-header`
- Add `.cmb-section-title` with `.cmb-reveal` animation
- Replace `.btn` with `.cmb-btn` for consistency
- Add icons to buttons
- Wrap iframe in `.cmb-card` container
- Remove inline styles from iframe

---

#### Page 2: cmb-status (Lines 1705-1749)

**Current Structure:**
```html
<div class="page" id="page-cmb-status">
    <div class="grid grid-4" style="margin-bottom:16px" id="cmbStatusCards">
        <div class="card" style="padding:12px 14px;border-left:2px solid var(--green)">
            <div class="card-title">Engine</div>
            <div class="card-value" id="cmbEngineHealth">--</div>
            <div class="card-sub">cmb-engine.service</div>
        </div>
        <!-- 3 more cards -->
    </div>
    <div class="grid grid-2" style="margin-bottom:16px">
        <div class="card">
            <div class="card-header"><span class="card-title">Recent Memories</span></div>
            <div id="cmbRecentMemories">...</div>
        </div>
        <div class="card">
            <div class="card-header"><span class="card-title">Active Sessions</span></div>
            <div id="cmbSessions">...</div>
        </div>
    </div>
    <div class="card">
        <div class="card-header"><span class="card-title">Architecture</span></div>
        <div style="font-size:11px;font-family:var(--font-mono)">...</div>
    </div>
</div>
```

**New Structure:**
```html
<div class="page" id="page-cmb-status">
    <!-- Section Header -->
    <div class="cmb-section-header">
        <h2 class="cmb-section-title cmb-reveal">System Status</h2>
        <div class="cmb-section-badge">HEALTH</div>
    </div>

    <!-- Stat Cards Grid -->
    <div class="cmb-grid-4" style="margin-bottom:32px" id="cmbStatusCards">
        <div class="cmb-stat-card cmb-reveal">
            <div class="cmb-stat-label">Engine</div>
            <div class="cmb-stat-value" id="cmbEngineHealth">--</div>
            <div class="cmb-stat-sub">cmb-engine.service</div>
        </div>
        <div class="cmb-stat-card cmb-reveal">
            <div class="cmb-stat-label">Memories</div>
            <div class="cmb-stat-value" id="cmbMemCount">--</div>
            <div class="cmb-stat-sub">Stored facts</div>
        </div>
        <div class="cmb-stat-card cmb-reveal">
            <div class="cmb-stat-label">MCP</div>
            <div class="cmb-stat-value" id="cmbMcpStatus">--</div>
            <div class="cmb-stat-sub">opencode connected</div>
        </div>
        <div class="cmb-stat-card cmb-reveal">
            <div class="cmb-stat-label">Workspaces</div>
            <div class="cmb-stat-value" id="cmbWsCount">--</div>
            <div class="cmb-stat-sub">Active scopes</div>
        </div>
    </div>

    <!-- Content Cards -->
    <div class="cmb-grid-2" style="margin-bottom:32px">
        <div class="cmb-card cmb-reveal">
            <div class="cmb-card-header">
                <div class="square-block"></div>
                <div class="card-label">Recent Memories</div>
            </div>
            <div id="cmbRecentMemories" style="font-size:0.88rem;line-height:1.6">
                <div class="empty-state"><span class="loading"></span></div>
            </div>
        </div>
        <div class="cmb-card cmb-reveal">
            <div class="cmb-card-header">
                <div class="square-block"></div>
                <div class="card-label">Active Sessions</div>
            </div>
            <div id="cmbSessions" style="font-size:0.88rem;line-height:1.6">
                <div class="empty-state"><span class="loading"></span></div>
            </div>
        </div>
    </div>

    <!-- Architecture Card -->
    <div class="cmb-card cmb-reveal">
        <div class="cmb-card-header">
            <div class="square-block"></div>
            <div class="card-label">Architecture</div>
        </div>
        <div style="font-size:0.8rem;font-family:var(--font-mono);color:var(--text-muted);line-height:2">
            <div><span style="color:var(--accent-neon)">Engine</span> &nbsp; systemd cmb-engine.service → 127.0.0.1:8700 (loopback only)</div>
            <div><span style="color:var(--accent-neon)">DB</span> &nbsp;&nbsp;&nbsp;&nbsp; /srv/cmb/data/cmb.db (SQLite WAL, owned by cmb user)</div>
            <div><span style="color:var(--accent-neon)">Web</span> &nbsp;&nbsp;&nbsp; /srv/cmb/web/ → nginx /cmb/</div>
            <div><span style="color:var(--accent-neon)">MCP</span> &nbsp;&nbsp;&nbsp; /srv/cmb/venv/bin/cmb-mcp (stdio, shared DB)</div>
            <div><span style="color:var(--accent-neon)">Auth</span> &nbsp;&nbsp; token-gated (CMB_API_TOKEN + browser session cookie)</div>
            <div><span style="color:var(--accent-neon)">Model</span> all-MiniLM-L6-v2 (local embedder, dim 384)</div>
        </div>
    </div>
</div>
```

**Changes:**
- Add `.cmb-section-header` with title and badge
- Replace `.grid-4` with `.cmb-grid-4`
- Replace `.card` with `.cmb-stat-card` for stat cards
- Replace `.card` with `.cmb-card` for content cards
- Add `.cmb-reveal` animations to all cards
- Replace `.card-header` with `.cmb-card-header` + `.square-block`
- Update typography to match index.html (font-size in rem, line-height)
- Change accent color from `var(--accent-cyan)` to `var(--accent-neon)`

---

#### Page 3: cmb-workspaces (Lines 1751-1769)

**Current Structure:**
```html
<div class="page" id="page-cmb-workspaces">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:16px">
        <div>
            <div style="font-family:var(--font-tech);font-size:20px;font-weight:600">Workspaces</div>
            <div style="font-size:12px;color:var(--text-muted)">Tenant scopes...</div>
        </div>
        <button class="btn btn-sm" onclick="createCMBWorkspace()">+ New Workspace</button>
    </div>
    <div class="card" style="padding:14px 16px;margin-bottom:16px">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
            <div style="font-weight:600;font-size:13px">Token Savings</div>
            <div style="font-size:11px;color:var(--text-muted)" id="cmbWsSavingsTotal"></div>
        </div>
        <div id="cmbWsSavings">...</div>
    </div>
    <div class="grid grid-2" id="cmbWsGrid">...</div>
</div>
```

**New Structure:**
```html
<div class="page" id="page-cmb-workspaces">
    <!-- Section Header -->
    <div class="cmb-section-header">
        <div>
            <h2 class="cmb-section-title cmb-reveal">Workspaces</h2>
            <p style="font-size:0.88rem;color:var(--text-muted);margin-top:8px">
                Tenant scopes for CMB memory — isolated by default, shareable on demand
            </p>
        </div>
        <button class="cmb-btn cmb-btn-primary cmb-btn-sm" onclick="createCMBWorkspace()">
            <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M8 2v12M2 8h12"/>
            </svg>
            New Workspace
        </button>
    </div>

    <!-- Token Savings Card -->
    <div class="cmb-card cmb-reveal" style="margin-bottom:32px">
        <div class="cmb-card-header">
            <div class="square-block"></div>
            <div class="card-label">Token Savings</div>
            <div style="margin-left:auto;font-size:0.75rem;color:var(--text-muted);font-family:var(--font-mono)" id="cmbWsSavingsTotal"></div>
        </div>
        <div id="cmbWsSavings" style="display:flex;flex-direction:column;gap:12px">
            <span class="loading"></span>
        </div>
    </div>

    <!-- Workspace Grid -->
    <div class="cmb-grid-2" id="cmbWsGrid">
        <div class="empty-state" style="grid-column:1/-1"><span class="loading"></span></div>
    </div>
</div>
```

**Changes:**
- Add `.cmb-section-header` with title, description, and action button
- Replace `.btn` with `.cmb-btn-primary` + icon
- Replace `.card` with `.cmb-card` + `.cmb-card-header`
- Replace `.grid-2` with `.cmb-grid-2`
- Add `.cmb-reveal` animations
- Update typography to rem units

---

#### Page 4: cmb-history (Lines 1771-1792)

**Current Structure:**
```html
<div class="page" id="page-cmb-history">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:16px">
        <div>
            <div style="font-family:var(--font-tech);font-size:20px;font-weight:600">Timeline</div>
            <div style="font-size:12px;color:var(--text-muted)">Bi-temporal history...</div>
        </div>
    </div>
    <div class="card" style="padding:14px 16px;margin-bottom:16px">
        <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center">
            <input id="cmbHistQuery" type="text" placeholder="Query a fact..." style="..." />
            <select id="cmbHistWs" style="..."></select>
            <button class="btn btn-sm" onclick="loadCMBHistory()">Search</button>
            <label style="...">
                <input type="checkbox" id="cmbHistWhy" /> Show supersession (why)
            </label>
        </div>
    </div>
    <div class="card">
        <div class="card-header"><span class="card-title" id="cmbHistTitle">History</span></div>
        <div id="cmbHistory">...</div>
    </div>
</div>
```

**New Structure:**
```html
<div class="page" id="page-cmb-history">
    <!-- Section Header -->
    <div class="cmb-section-header">
        <div>
            <h2 class="cmb-section-title cmb-reveal">Timeline</h2>
            <p style="font-size:0.88rem;color:var(--text-muted);margin-top:8px">
                Bi-temporal history — what CMB believed, and when it changed
            </p>
        </div>
        <div class="cmb-section-badge">HISTORY</div>
    </div>

    <!-- Search Form Card -->
    <div class="cmb-card cmb-reveal" style="margin-bottom:32px">
        <div class="cmb-card-header">
            <div class="square-block"></div>
            <div class="card-label">Search</div>
        </div>
        <div style="display:flex;gap:12px;flex-wrap:wrap;align-items:center">
            <input id="cmbHistQuery" type="text" placeholder="Query a fact, e.g. nginx config" 
                   style="flex:1;min-width:240px;background:var(--bg-input);border:1px solid var(--border-light);color:var(--text);padding:10px 14px;font-size:0.88rem;outline:none;transition:border-color 0.2s" />
            <select id="cmbHistWs" 
                    style="background:var(--bg-input);border:1px solid var(--border-light);color:var(--text);padding:10px 14px;font-size:0.88rem;outline:none"></select>
            <button class="cmb-btn cmb-btn-sm" onclick="loadCMBHistory()">
                <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="7" cy="7" r="5"/>
                    <path d="M11 11l3 3"/>
                </svg>
                Search
            </button>
            <label style="display:flex;align-items:center;gap:8px;font-size:0.88rem;color:var(--text-muted);cursor:pointer">
                <input type="checkbox" id="cmbHistWhy" style="accent-color:var(--accent-neon)" />
                Show supersession (why)
            </label>
        </div>
    </div>

    <!-- Results Card -->
    <div class="cmb-card cmb-reveal">
        <div class="cmb-card-header">
            <div class="square-block"></div>
            <div class="card-label" id="cmbHistTitle">History</div>
        </div>
        <div id="cmbHistory" style="font-size:0.88rem;line-height:1.6">
            <div class="empty-state" style="padding:24px 0">Enter a query and press Search to see the versions of a fact.</div>
        </div>
    </div>
</div>
```

**Changes:**
- Add `.cmb-section-header` with title, description, and badge
- Replace `.card` with `.cmb-card` + `.cmb-card-header`
- Update input/select styling to match design tokens
- Replace `.btn` with `.cmb-btn` + icon
- Add `.cmb-reveal` animations
- Update typography to rem units

---

#### Page 5: cmb-analytics (Lines 1794-1812)

**Current Structure:**
```html
<div class="page" id="page-cmb-analytics">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:16px">
        <div>
            <div style="font-family:var(--font-tech);font-size:20px;font-weight:600">CMB Analytics</div>
            <div style="font-size:12px;color:var(--text-muted)">Token savings, memory portfolio...</div>
        </div>
        <select id="cmbAnalyticsWs" style="..."></select>
    </div>
    <div style="display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap">
        <button class="btn btn-sm active" id="cmbTabSavings">Token Savings</button>
        <button class="btn btn-sm" id="cmbTabPortfolio">Memory Portfolio</button>
        <button class="btn btn-sm" id="cmbTabConsolidation">Consolidation</button>
        <button class="btn btn-sm" id="cmbTabSessions">Session Handoff</button>
        <button class="btn btn-sm" id="cmbTabQuality">Quality Distribution</button>
    </div>
    <div class="card" style="padding:16px">
        <div id="cmbAnalyticsContent">...</div>
    </div>
</div>
```

**New Structure:**
```html
<div class="page" id="page-cmb-analytics">
    <!-- Section Header -->
    <div class="cmb-section-header">
        <div>
            <h2 class="cmb-section-title cmb-reveal">Analytics</h2>
            <p style="font-size:0.88rem;color:var(--text-muted);margin-top:8px">
                Token savings, memory portfolio, consolidation, session handoff, and quality distribution
            </p>
        </div>
        <select id="cmbAnalyticsWs" 
                style="background:var(--bg-input);border:1px solid var(--border-light);color:var(--text);padding:10px 14px;font-size:0.88rem;outline:none"></select>
    </div>

    <!-- Tab Buttons -->
    <div style="display:flex;gap:12px;margin-bottom:32px;flex-wrap:wrap;border-bottom:1px solid var(--border-light);padding-bottom:16px">
        <button class="cmb-btn cmb-btn-sm active" id="cmbTabSavings" onclick="loadCMBAnalyticsTab('savings')">Token Savings</button>
        <button class="cmb-btn cmb-btn-sm" id="cmbTabPortfolio" onclick="loadCMBAnalyticsTab('portfolio')">Memory Portfolio</button>
        <button class="cmb-btn cmb-btn-sm" id="cmbTabConsolidation" onclick="loadCMBAnalyticsTab('consolidation')">Consolidation</button>
        <button class="cmb-btn cmb-btn-sm" id="cmbTabSessions" onclick="loadCMBAnalyticsTab('sessions')">Session Handoff</button>
        <button class="cmb-btn cmb-btn-sm" id="cmbTabQuality" onclick="loadCMBAnalyticsTab('quality')">Quality Distribution</button>
    </div>

    <!-- Content Card -->
    <div class="cmb-card cmb-reveal">
        <div id="cmbAnalyticsContent" style="font-size:0.88rem;line-height:1.6">
            <div class="empty-state">Select a workspace and tab to view analytics.</div>
        </div>
    </div>
</div>
```

**Changes:**
- Add `.cmb-section-header` with title, description, and workspace selector
- Replace `.btn` with `.cmb-btn` for tab buttons
- Add border-bottom separator for tabs
- Replace `.card` with `.cmb-card`
- Add `.cmb-reveal` animation
- Update typography to rem units

---

#### Page 6: cmb-sharing (Not shown in excerpt)

**Note:** This page exists but wasn't in the excerpt. Apply the same pattern:
- `.cmb-section-header` with title + badge
- `.cmb-card` containers with `.cmb-card-header`
- `.cmb-btn` for buttons
- `.cmb-reveal` animations
- Typography in rem units

---

### Phase 3: JavaScript Enhancements (Lines 3484-3941)

**Step 3.1:** Update CMB API functions to work with new structure

No changes needed to the API logic itself — only the DOM selectors have changed (e.g., `.card` → `.cmb-card`, `.grid-4` → `.cmb-grid-4`).

**Step 3.2:** Add reveal animation initialization

```javascript
// Add after line ~3940
function initCMBRevealAnimations() {
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.remove('hidden-reveal');
            }
        });
    }, { threshold: 0.1, rootMargin: '0px 0px -50px 0px' });

    document.querySelectorAll('.cmb-reveal').forEach(el => {
        el.classList.add('hidden-reveal');
        observer.observe(el);
    });
}

// Re-initialize on page switch
function switchPage(pageId) {
    // ... existing code ...
    
    // Re-init animations for new page
    setTimeout(initCMBRevealAnimations, 100);
}
```

**Step 3.3:** Add button hover effects (optional enhancement)

```javascript
// Add subtle scale on button hover
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.cmb-btn').forEach(btn => {
        btn.addEventListener('mouseenter', () => {
            btn.style.transform = 'translateY(-1px)';
        });
        btn.addEventListener('mouseleave', () => {
            btn.style.transform = 'translateY(0)';
        });
    });
});
```

---

## Testing Checklist

### Visual Testing
- [ ] All CMB pages load without console errors
- [ ] Section headers display correctly with title + badge
- [ ] Cards have proper spacing and borders
- [ ] Stat cards show left accent border
- [ ] Buttons have hover effects (color change, transform)
- [ ] Reveal animations trigger on page load
- [ ] Reveal animations trigger on page switch
- [ ] Grid layouts collapse properly on mobile

### Functional Testing
- [ ] cmb-dashboard: iframe loads, reload button works, open full button works
- [ ] cmb-status: all 4 stat cards update, recent memories load, sessions load
- [ ] cmb-workspaces: create workspace button works, savings display updates, grid populates
- [ ] cmb-history: search form works, results display, checkbox functions
- [ ] cmb-analytics: workspace selector works, all 5 tabs load content
- [ ] cmb-sharing: (test all existing functionality)

### Responsive Testing
- [ ] 1920px: 4-column grid displays correctly
- [ ] 1200px: 2-column grid displays correctly
- [ ] 768px: 1-column grid displays correctly
- [ ] Mobile: section headers stack, buttons wrap

### Performance Testing
- [ ] No layout shift on page load
- [ ] Animations don't cause jank
- [ ] iframe loads within 2 seconds
- [ ] API calls complete within 1 second

---

## Rollback Strategy

### Git Backup
```bash
# Before starting
git add panteon/admin.html
git commit -m "backup: admin.html before CMB restructuring"

# If rollback needed
git checkout HEAD~1 panteon/admin.html
```

### Incremental Commits
```bash
# After Phase 1 (CSS)
git add panteon/admin.html
git commit -m "feat: add CMB design language CSS foundation"

# After Phase 2 (HTML restructuring)
git add panteon/admin.html
git commit -m "refactor: restructure CMB pages to match Panteon design"

# After Phase 3 (JavaScript)
git add panteon/admin.html
git commit -m "feat: add CMB reveal animations and enhancements"
```

---

## Execution Order

1. **Phase 1** (30 min): Add CSS foundation
   - Add new CSS classes after line 508
   - Add reveal animation JS after line 3940
   - Test: verify no console errors

2. **Phase 2** (2 hours): Restructure pages one by one
   - Start with cmb-status (simplest, most visual impact)
   - Then cmb-workspaces
   - Then cmb-history
   - Then cmb-analytics
   - Then cmb-dashboard
   - Finally cmb-sharing
   - Test each page after restructuring

3. **Phase 3** (30 min): JavaScript enhancements
   - Add reveal animation initialization
   - Update page switch to re-init animations
   - Test: verify animations work on all pages

4. **Final Testing** (30 min): Run full checklist
   - Visual testing
   - Functional testing
   - Responsive testing
   - Performance testing

**Total Estimated Time:** 3.5 hours

---

## Notes

- **No functionality changes**: All existing JavaScript functions remain unchanged
- **No text changes**: All labels, titles, and descriptions remain identical
- **No color changes**: Using existing design tokens (--accent-neon, --text-light, etc.)
- **Only structural changes**: Replacing inline styles with design system classes
- **Progressive enhancement**: Animations are optional — if JS fails, content still displays

---

## References

- Design Language Spec: `/home/tablet/alieninc/panteon/AGENTS.md`
- Homepage Reference: `/home/tablet/alieninc/panteon/index.html`
- Current Admin: `/home/tablet/alieninc/panteon/admin.html`
- CMB Session: `ses_01KZNQVTX59NNY1GRKMTXZZVC1`

---

## Next Steps

After completing this restructuring:
1. Update AGENTS.md to document the CMB section design patterns
2. Store this plan in CMB for future reference
3. Create a visual comparison (before/after screenshots)
4. Document any deviations or exceptions

---

**End of Plan**
