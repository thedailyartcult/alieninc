# INTEGRATION — serving CMB from the panteon admin

CMB (Cosmic Microwave Background) is the memory dashboard for the
alieninc/panteon stack. Everything below assumes the memory engine — the
`/api/*` backend, loopback on `:8700` — is already running and reachable
from the admin host.

## Artifacts

- `cmb.html` — self-contained single file (styles + all 4 scripts inlined).
- `cmb-design.html` — external-ref version (styles inline, JS from `/v2-assets`).
- `cmb-src/` — the source tree: `cmb.js`, `cmb.css`, `index.html`,
  `cmb-graph.js`, `cmb-graph-compat.js`, `vendor/` (d3, force-graph + MIT
  licenses), `cmb.ico`, `cmb-icon.png`, `favicon-32.png`.

## 1. Where to copy files

Serve the UI from the admin's static assets, for example:

    /srv/panteon/static/cmb/{cmb.html, cmb-design.html, cmb-src/}

For the external-ref file, alias `/v2-assets/*` to the CMB tree:

    /v2-assets/*  ->  /srv/panteon/static/cmb/cmb-src/*

`cmb.html` needs no external assets — it is fully self-contained apart from
the API calls and its embedded favicon.

## 2. How the API is reached

`apiRoot` is `${location.origin}/api` (set in `cmb.js`). Two wiring options:

- (a) Same-origin reverse proxy (recommended): the admin's reverse proxy
      (nginx/Caddy) forwards `/api/*` to the memory engine sidecar:

          location /api/ { proxy_pass http://127.0.0.1:8700; }

- (b) Sidecar on `:8700` behind the proxy: serve CMB from any origin and map
      `/api/*` -> `http://127.0.0.1:8700/api/*` at the proxy.

Browser requests carry the session header `X-CMB-Browser-Session`. Token auth
posts to `POST /api/auth/session` (token via the `#token=` URL fragment) and
returns a session cookie. Keep the engine loopback-only in development (see
`run_oneshot.py`) and terminate TLS at the proxy in production.

## 3. Nav entry

Add a route or link in the panteon admin that opens `/cmb.html` (or
`/cmb-design.html` behind the alias). Example nav item:

    <a href="/cmb.html">CMB — Cosmic Microwave Background</a>

## 4. Script order (do not change)

    d3.min.js -> force-graph.min.js -> cmb-graph.js -> cmb.js (last)

`cmb.js` reads `window.d3`, `window.ForceGraph`, `window.CmbGraph`. In the
external-ref version `ensureGraphAssets()` lazily loads the engine when the
Relations tab opens; in `cmb.html` all four scripts are already inlined.

## 5. Security notes

- All outbound links are validated to `http(s)` only.
- Local-first: recall and storage stay on the device; nothing is uploaded
  unless the Automation policy is explicitly enabled.
- Production CSP: allow `'self'` for script/style. The loopback dev server
  relaxes CSP for preview only.
- Do not expose `/v2-assets/` with directory listing.
