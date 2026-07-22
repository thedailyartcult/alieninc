#!/usr/bin/env node
/**
 * Statute & Precedent — WAT Runner
 * =================================
 * Puppeteer-based website auditor using the EDPB WAT's own
 * @ghostery/adblocker libraries for tracker detection.
 *
 * Collects: cookies, localStorage, beacons/trackers, HTTPS status,
 * security headers, and third-party traffic for each company site.
 *
 * Usage: node wat_runner.js [--output-dir <path>] [--url <url>]
 * Default output: ./wat_reports/
 */

const fs = require('fs');
const path = require('path');
const puppeteer = require('puppeteer-core');
const { FiltersEngine } = require('@ghostery/adblocker');

// ── Configuration ─────────────────────────────────────────────────────────────
const OUTPUT_DIR = process.argv.includes('--output-dir')
    ? process.argv[process.argv.indexOf('--output-dir') + 1]
    : path.join(__dirname, 'wat_reports');

const SINGLE_URL = process.argv.includes('--url')
    ? process.argv[process.argv.indexOf('--url') + 1]
    : null;

const CHROMIUM_PATH = process.env.CHROMIUM_PATH || process.argv.includes('--chromium')
    ? (process.argv.includes('--chromium') ? process.argv[process.argv.indexOf('--chromium') + 1] : process.env.CHROMIUM_PATH)
    : '/usr/bin/chromium';
const PAGE_TIMEOUT = 30000;
const WAIT_AFTER_LOAD = 5000;

const COMPANIES = {
    alieninc:         { name: 'Alien.Inc',                    url: 'https://alieninc.tech/' },
    'rousseau':   { name: 'Rousseau',               url: 'https://rousseau.alieninc.tech' },
    panteon:        { name: 'Panteon',                    url: 'https://panteon.alieninc.tech' },
    immanuel:       { name: 'Immanuel',                   url: 'https://immanuel.alieninc.tech' },
    centra:         { name: 'Centra',                     url: 'https://centra.alieninc.tech' },
    kmt:              { name: 'KMT Consulting Group',         url: 'https://kmt.alieninc.tech' },
    thedailyartcult:  { name: 'The Daily Art Cult',           url: 'https://thedailyartcult.lol' },
    alcantara:        { name: 'Alcantara Art Foundation',     url: 'https://alcantaraartfoundation.alieninc.tech' },
};

// ── Load EDPB WAT adblocker filter lists ──────────────────────────────────────
const WAT_ASSETS = path.join(__dirname, 'assets');
const blockerOptions = {
    debug: true,
    enableOptimizations: false,
    loadCosmeticFilters: false,
};

let blockers = {};
try {
    blockers = {
        'easyprivacy': FiltersEngine.parse(
            fs.readFileSync(path.join(WAT_ASSETS, 'easyprivacy.txt'), 'utf8'),
            blockerOptions
        ),
        'fanboy-annoyance': FiltersEngine.parse(
            fs.readFileSync(path.join(WAT_ASSETS, 'fanboy-annoyance.txt'), 'utf8'),
            blockerOptions
        ),
    };
    console.log(`  Loaded ${Object.keys(blockers).length} filter lists from EDPB WAT assets`);
} catch (e) {
    console.error(`  Warning: Could not load filter lists: ${e.message}`);
    console.error(`  Tracker detection will be limited.`);
}

// ── Audit a single URL ────────────────────────────────────────────────────────
async function auditUrl(browser, url, companyName) {
    const page = await browser.newPage();
    await page.setExtraHTTPHeaders({
        'X-AlienInc-Audit': 'statute',
    });
    const results = {
        url,
        company: companyName,
        audit_time: new Date().toISOString(),
        cookies: [],
        localstorage: [],
        beacons: [],
        hosts: [],
        https: {},
        security_headers: {},
        errors: [],
    };

    // Collect network requests for beacons + hosts
    const requests = [];
    const hostsSet = new Set();

    // Cookie collection from HTTP headers
    const httpCookies = [];

    page.on('request', (req) => {
        const parsed = new URL(req.url());
        if (parsed.protocol !== 'data:') {
            hostsSet.add(parsed.hostname);
        }
        requests.push({
            url: req.url(),
            method: req.method(),
            resourceType: req.resourceType(),
            headers: req.headers(),
            sourceUrl: req.frame()?.url() || url,
        });
    });

    page.on('response', async (res) => {
        const resUrl = res.url();
        // Remove trailing slash for matching
        const cleanUrl = resUrl.replace(/\/$/, '');
        const pageUrl = url.replace(/\/$/, '');

        // Collect Set-Cookie headers
        const headers = res.headers();
        const setCookie = headers['set-cookie'];
        if (setCookie) {
            const cookieStrings = Array.isArray(setCookie) ? setCookie : [setCookie];
            for (const raw of cookieStrings) {
                httpCookies.push({
                    raw,
                    source: 'Set-Cookie header',
                    url: resUrl,
                    type: 'Cookie.HTTP',
                });
            }
        }

        // Collect security headers from the main page response
        if (cleanUrl === pageUrl || resUrl === url || cleanUrl.endsWith(pageUrl) || pageUrl.endsWith(cleanUrl)) {
            results.security_headers = {
                'strict-transport-security': headers['strict-transport-security'] || null,
                'content-security-policy': headers['content-security-policy'] || null,
                'x-frame-options': headers['x-frame-options'] || null,
                'x-content-type-options': headers['x-content-type-options'] || null,
                'x-xss-protection': headers['x-xss-protection'] || null,
                'referrer-policy': headers['referrer-policy'] || null,
                'permissions-policy': headers['permissions-policy'] || null,
                'server': headers['server'] || null,
            };
        }
    });

    // Intercept document.cookie writes
    await page.evaluateOnNewDocument(() => {
        window.__wat_js_cookies = [];
        const origDescriptor = Object.getOwnPropertyDescriptor(Document.prototype, 'cookie');
        Object.defineProperty(document, 'cookie', {
            get: function() {
                return origDescriptor.get.call(this);
            },
            set: function(val) {
                window.__wat_js_cookies.push({ raw: val, type: 'Cookie.JS' });
                return origDescriptor.set.call(this, val);
            },
        });

        // Hook localStorage.setItem
        window.__wat_localstorage = [];
        const origSetItem = Storage.prototype.setItem;
        Storage.prototype.setItem = function(key, value) {
            try {
                window.__wat_localstorage.push({
                    host: window.location.hostname,
                    key,
                    value: String(value).substring(0, 500),
                });
            } catch(e) {}
            return origSetItem.call(this, key, value);
        };
    });

    try {
        // Navigate
        const response = await page.goto(url, {
            waitUntil: 'networkidle2',
            timeout: PAGE_TIMEOUT,
        });

        // Capture headers from the main response directly
        if (response) {
            const respHeaders = response.headers();
            results.security_headers = {
                'strict-transport-security': respHeaders['strict-transport-security'] || null,
                'content-security-policy': respHeaders['content-security-policy'] || null,
                'x-frame-options': respHeaders['x-frame-options'] || null,
                'x-content-type-options': respHeaders['x-content-type-options'] || null,
                'x-xss-protection': respHeaders['x-xss-protection'] || null,
                'referrer-policy': respHeaders['referrer-policy'] || null,
                'permissions-policy': respHeaders['permissions-policy'] || null,
                'server': respHeaders['server'] || null,
            };
        }

        // HTTPS check
        const finalUrl = page.url();
        results.https = {
            original_url: url,
            final_url: finalUrl,
            https_redirect: url.startsWith('http://') && finalUrl.startsWith('https://'),
            https_support: finalUrl.startsWith('https://'),
            status_code: response?.status() || 0,
        };

        // Wait for JS-set cookies and localStorage
        await new Promise(r => setTimeout(r, WAIT_AFTER_LOAD));

        // Collect JS cookies
        const jsCookies = await page.evaluate(() => window.__wat_js_cookies || []);
        const jsLocalstorage = await page.evaluate(() => window.__wat_localstorage || []);

        // Browser cookies
        const browserCookies = await page.cookies();

        // Parse all cookies
        results.cookies = parseCookies(browserCookies, httpCookies, jsCookies, finalUrl);
        results.localstorage = jsLocalstorage;

        // Match network requests against adblocker filter lists
        results.beacons = matchTrackers(requests);

        // Third-party hosts
        const pageHost = new URL(finalUrl).hostname;
        results.hosts = Array.from(hostsSet).map(h => ({
            hostname: h,
            firstParty: h === pageHost || h.endsWith('.' + pageHost),
        }));

        // Page metadata
        results.page_title = await page.title();

    } catch (e) {
        results.errors.push({ message: e.message, stack: e.stack });
    }

    await page.close();
    return results;
}

// ── Parse cookies from all sources ────────────────────────────────────────────
function parseCookies(browserCookies, httpCookies, jsCookies, pageUrl) {
    const seen = new Map();

    // Browser cookies (from Puppeteer cookie jar)
    for (const c of browserCookies) {
        const key = `${c.name}|${c.domain}|${c.path}`;
        seen.set(key, {
            name: c.name,
            value: c.value,
            domain: c.domain.replace(/^\./, ''),
            path: c.path,
            secure: c.secure,
            httpOnly: c.httpOnly,
            sameSite: c.sameSite || 'unspecified',
            session: !c.expires || c.expires === -1,
            expires: c.expires || -1,
            firstPartyStorage: isFirstParty(c.domain, pageUrl),
            source: 'browser',
        });
    }

    // HTTP Set-Cookie parsed
    for (const hc of httpCookies) {
        const parts = hc.raw.split(';')[0].split('=');
        if (parts.length >= 2) {
            const name = parts[0].trim();
            const key = `${name}|${new URL(hc.url).hostname}|/`;
            if (!seen.has(key)) {
                seen.set(key, {
                    name,
                    value: parts.slice(1).join('=').trim(),
                    domain: new URL(hc.url).hostname,
                    path: '/',
                    secure: hc.raw.toLowerCase().includes('secure'),
                    httpOnly: hc.raw.toLowerCase().includes('httponly'),
                    sameSite: extractSameSite(hc.raw),
                    session: hc.raw.toLowerCase().includes('session') || !hc.raw.toLowerCase().includes('expires'),
                    expires: -1,
                    firstPartyStorage: true,
                    source: 'http-header',
                });
            }
        }
    }

    // JS-set cookies
    for (const jc of jsCookies) {
        const parts = jc.raw.split(';')[0].split('=');
        if (parts.length >= 2) {
            const name = parts[0].trim();
            const key = `${name}||/`;
            if (!seen.has(key)) {
                seen.set(key, {
                    name,
                    value: parts.slice(1).join('=').trim(),
                    domain: new URL(pageUrl).hostname,
                    path: '/',
                    secure: pageUrl.startsWith('https'),
                    httpOnly: false,
                    sameSite: 'unspecified',
                    session: jc.raw.toLowerCase().includes('session') || !jc.raw.toLowerCase().includes('expires'),
                    expires: -1,
                    firstPartyStorage: true,
                    source: 'javascript',
                });
            }
        }
    }

    return Array.from(seen.values());
}

function isFirstParty(cookieDomain, pageUrl) {
    try {
        const pageHost = new URL(pageUrl).hostname;
        const domain = cookieDomain.replace(/^\./, '');
        return pageHost === domain || pageHost.endsWith('.' + domain) || domain.endsWith('.' + pageHost);
    } catch { return false; }
}

function extractSameSite(raw) {
    const lower = raw.toLowerCase();
    if (lower.includes('samesite=strict')) return 'Strict';
    if (lower.includes('samesite=lax')) return 'Lax';
    if (lower.includes('samesite=none')) return 'None';
    return 'unspecified';
}

// ── Match network requests against adblocker filter lists ─────────────────────
function matchTrackers(requests) {
    const trackerMap = new Map();

    for (const req of requests) {
        if (req.resourceType === 'document' || req.resourceType === '') continue;

        const sourceUrl = req.sourceUrl || '';
        const adblockerReq = {
            url: req.url,
            sourceUrl,
            type: req.resourceType,
        };

        for (const [listName, blocker] of Object.entries(blockers)) {
            try {
                const { match, filter } = blocker.match(adblockerReq);
                if (match) {
                    const parsed = new URL(req.url);
                    const key = `${parsed.hostname}${parsed.pathname}`;
                    if (!trackerMap.has(key)) {
                        trackerMap.set(key, {
                            url: req.url,
                            hostname: parsed.hostname,
                            pathname: parsed.pathname,
                            filter: filter ? filter.toString() : '',
                            listName,
                            occurrences: 0,
                            resources: [],
                        });
                    }
                    const entry = trackerMap.get(key);
                    entry.occurrences++;
                    if (entry.resources.length < 5) {
                        entry.resources.push(req.url);
                    }
                }
            } catch (e) {
                // Skip malformed URLs
            }
        }
    }

    return Array.from(trackerMap.values()).sort((a, b) => b.occurrences - a.occurrences);
}

// ── Main ──────────────────────────────────────────────────────────────────────
async function main() {
    console.log('\n  Statute & Precedent — WAT Runner');
    console.log('  ─────────────────────────────────────────');
    console.log('  EDPB Website Auditing Tool integration');
    console.log('  Using @ghostery/adblocker for tracker detection\n');

    // Ensure output directory
    fs.mkdirSync(OUTPUT_DIR, { recursive: true });

    // Launch browser
    console.log('  Launching Chromium...');
    const browser = await puppeteer.launch({
        executablePath: CHROMIUM_PATH,
        headless: 'new',
        args: [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-gpu',
            '--disable-dev-shm-usage',
        ],
    });
    console.log('  Browser ready.\n');

    const targets = SINGLE_URL
        ? { custom: { name: 'Custom URL', url: SINGLE_URL } }
        : COMPANIES;

    const allResults = {};

    for (const [id, info] of Object.entries(targets)) {
        console.log(`  Auditing ${info.name}...`);
        try {
            const result = await auditUrl(browser, info.url, info.name);
            allResults[id] = result;

            const cookieCount = result.cookies.length;
            const trackerCount = result.beacons.length;
            const hostCount = result.hosts.length;
            const httpsOk = result.https.https_support ? 'HTTPS' : 'HTTP';

            console.log(`    ${httpsOk} | ${cookieCount} cookies | ${trackerCount} trackers | ${hostCount} hosts`);

            // Save individual report
            const reportPath = path.join(OUTPUT_DIR, `${id}.json`);
            fs.writeFileSync(reportPath, JSON.stringify(result, null, 2));
        } catch (e) {
            console.error(`    Error: ${e.message}`);
            allResults[id] = { error: e.message };
        }
    }

    // Save combined report
    const combinedPath = path.join(OUTPUT_DIR, 'combined_report.json');
    const combined = {
        report_date: new Date().toISOString(),
        tool: 'EDPB WAT Runner (Puppeteer)',
        version: '2.0.1',
        companies: allResults,
    };
    fs.writeFileSync(combinedPath, JSON.stringify(combined, null, 2));

    await browser.close();

    console.log(`\n  Reports saved to ${OUTPUT_DIR}/`);
    console.log(`  Combined report: ${combinedPath}\n`);

    return combined;
}

main().catch(e => {
    console.error('Fatal error:', e);
    process.exit(1);
});
