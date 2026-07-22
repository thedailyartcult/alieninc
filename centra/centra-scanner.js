/**
 * CENTRA Vulnerability Scanner
 * ================================
 * Client-side security scanner for the Alien Inc ecosystem.
 * Scans for exposed files, missing headers, misconfigurations,
 * and common web vulnerabilities across all 7 company sites.
 *
 * Centra — Exposure & Vulnerability Management
 * A subsidiary of Alien Inc.
 *
 * Usage:
 *   CentraScanner.scan()           — run full scan, returns results object
 *   CentraScanner.scanTarget(url)  — scan a single URL
 *   CentraScanner.getReport()      — get last scan report
 *   CentraScanner.printReport()    — print report to console
 */
var CentraScanner = (function () {
  'use strict';

  var SCAN_VERSION = '1.0.0';
  var scanTimestamp = null;
  var lastReport = null;

  // =========================================================================
  // TARGETS — Alien Inc ecosystem
  // =========================================================================
  var ECOSYSTEM_DOMAINS = [
    { id: 'alieninc',     name: 'Alien.Inc',                url: '/' },
    { id: 'panteon',      name: 'Panteon',                  url: 'https://panteon.alieninc.tech' },
    { id: 'alcantara',    name: 'Alcantara Art Foundation', url: 'https://alcantaraartfoundation.alieninc.tech' },
    { id: 'tdac',         name: 'The Daily Art Cult',       url: 'https://thedailyartcult.lol' },
    { id: 'rousseau',     name: 'Rousseau Holdings',        url: 'https://rousseau.alieninc.tech' },
    { id: 'immanuel',     name: 'Immanuel',                 url: 'https://immanuel.alieninc.tech' },
    { id: 'centra',       name: 'Centra',                   url: 'https://centra.alieninc.tech' },
    { id: 'kmt',          name: 'KMT Consulting Group',     url: 'https://kmt.alieninc.tech' }
  ];

  // =========================================================================
  // VULNERABILITY CHECK DEFINITIONS
  // =========================================================================
  var SENSITIVE_PATHS = [
    { path: '/.git/config',            severity: 'critical', name: 'Exposed .git directory',         desc: 'Git repository config is publicly accessible. Attackers can reconstruct source code and extract secrets from commit history.' },
    { path: '/.git/HEAD',              severity: 'critical', name: 'Exposed .git/HEAD',              desc: 'Git HEAD pointer is accessible. Indicates full .git directory exposure.' },
    { path: '/.env',                   severity: 'critical', name: 'Exposed .env file',              desc: 'Environment variables file is publicly accessible. May contain API keys, database credentials, and secrets.' },
    { path: '/.env.production',        severity: 'critical', name: 'Exposed production .env',        desc: 'Production environment file is publicly accessible.' },
    { path: '/.env.backup',            severity: 'critical', name: 'Exposed .env backup',            desc: 'Backup environment file is publicly accessible.' },
    { path: '/.env.local',             severity: 'critical', name: 'Exposed .env.local',             desc: 'Local environment file is publicly accessible.' },
    { path: '/.htaccess',              severity: 'high',     name: 'Exposed .htaccess',              desc: 'Apache configuration file is publicly accessible. May reveal directory structure and access rules.' },
    { path: '/.htpasswd',              severity: 'critical', name: 'Exposed .htpasswd',              desc: 'Password file is publicly accessible. Contains hashed credentials.' },
    { path: '/config/database.yml',    severity: 'critical', name: 'Exposed database config',        desc: 'Database configuration file is publicly accessible. May contain credentials.' },
    { path: '/config/secrets.yml',     severity: 'critical', name: 'Exposed secrets config',         desc: 'Secrets configuration file is publicly accessible.' },
    { path: '/server-status',          severity: 'high',     name: 'Apache server-status',           desc: 'Apache server status page is publicly accessible. Reveals server configuration and connected clients.' },
    { path: '/server-info',            severity: 'high',     name: 'Apache server-info',             desc: 'Apache server info page is publicly accessible. Reveals detailed server configuration.' },
    { path: '/wp-admin/',              severity: 'medium',   name: 'WordPress admin panel',          desc: 'WordPress admin panel is accessible. May indicate a WordPress installation.' },
    { path: '/wp-login.php',           severity: 'medium',   name: 'WordPress login page',           desc: 'WordPress login page is accessible.' },
    { path: '/xmlrpc.php',             severity: 'high',     name: 'XML-RPC endpoint',               desc: 'XML-RPC endpoint is accessible. Can be used for brute force attacks and DDoS amplification.' },
    { path: '/backup/',                severity: 'high',     name: 'Backup directory',               desc: 'Backup directory is publicly accessible.' },
    { path: '/backups/',               severity: 'high',     name: 'Backups directory',              desc: 'Backups directory is publicly accessible.' },
    { path: '/dump/',                  severity: 'high',     name: 'Data dump directory',            desc: 'Data dump directory is publicly accessible.' },
    { path: '/phpmyadmin/',            severity: 'critical', name: 'phpMyAdmin',                     desc: 'phpMyAdmin is publicly accessible. Direct database management interface exposed.' },
    { path: '/admin/',                 severity: 'medium',   name: 'Admin directory',                desc: 'Admin directory listing is accessible.' },
    { path: '/debug/',                 severity: 'high',     name: 'Debug endpoint',                 desc: 'Debug endpoint is publicly accessible. May leak stack traces and internal data.' },
    { path: '/test/',                  severity: 'medium',   name: 'Test directory',                 desc: 'Test directory is publicly accessible. May contain test data or experimental code.' },
    { path: '/staging/',               severity: 'high',     name: 'Staging environment',            desc: 'Staging environment is publicly accessible.' },
    { path: '/.ssh/authorized_keys',   severity: 'critical', name: 'Exposed SSH keys',               desc: 'SSH authorized keys file is publicly accessible.' },
    { path: '/.aws/credentials',       severity: 'critical', name: 'Exposed AWS credentials',        desc: 'AWS credentials file is publicly accessible.' },
    { path: '/composer.json',          severity: 'medium',   name: 'Composer config',                desc: 'Composer.json is publicly accessible. May reveal dependency versions and project structure.' },
    { path: '/package.json',           severity: 'low',      name: 'Package config',                 desc: 'Package.json is publicly accessible. Reveals project dependencies.' },
    { path: '/.DS_Store',              severity: 'medium',   name: 'macOS .DS_Store',               desc: 'macOS directory metadata file is exposed. May reveal directory structure.' },
    { path: '/Thumbs.db',              severity: 'low',      name: 'Windows Thumbs.db',              desc: 'Windows thumbnail cache file is exposed.' },
    { path: '/.svn/entries',           severity: 'high',     name: 'SVN metadata',                   desc: 'SVN version control metadata is publicly accessible.' },
    { path: '/.hg/',                   severity: 'high',     name: 'Mercurial metadata',             desc: 'Mercurial version control metadata is publicly accessible.' }
  ];

  var SECURITY_HEADERS = [
    { header: 'Content-Security-Policy',    severity: 'high',   name: 'Content Security Policy',        desc: 'Missing CSP header. Vulnerable to XSS and data injection attacks.' },
    { header: 'X-Frame-Options',            severity: 'high',   name: 'X-Frame-Options',                desc: 'Missing X-Frame-Options header. Site may be embeddable in iframes (clickjacking).' },
    { header: 'X-Content-Type-Options',     severity: 'medium', name: 'X-Content-Type-Options',         desc: 'Missing X-Content-Type-Options header. Browser may MIME-sniff responses.' },
    { header: 'Strict-Transport-Security',  severity: 'high',   name: 'HSTS',                           desc: 'Missing Strict-Transport-Security header. Connections may be downgraded to HTTP.' },
    { header: 'Referrer-Policy',            severity: 'medium', name: 'Referrer-Policy',                desc: 'Missing Referrer-Policy header. Full URLs may leak in referrer headers.' },
    { header: 'Permissions-Policy',         severity: 'medium', name: 'Permissions-Policy',             desc: 'Missing Permissions-Policy header. Browser features not restricted.' },
    { header: 'X-XSS-Protection',          severity: 'low',    name: 'X-XSS-Protection',              desc: 'Missing X-XSS-Protection header (legacy but still useful for older browsers).' },
    { header: 'Cross-Origin-Opener-Policy', severity: 'medium', name: 'Cross-Origin-Opener-Policy',     desc: 'Missing COOP header. May be vulnerable to cross-origin attacks.' },
    { header: 'Cross-Origin-Resource-Policy', severity: 'medium', name: 'Cross-Origin-Resource-Policy', desc: 'Missing CORP header. Resources may be loaded cross-origin.' }
  ];

  var JS_VULNERABILITY_PATTERNS = [
    { pattern: /eval\s*\(/g,                         severity: 'high',   name: 'eval() usage',                  desc: 'eval() is used in JavaScript. Potential code injection vector.' },
    { pattern: /innerHTML\s*=/g,                     severity: 'medium', name: 'innerHTML assignment',           desc: 'innerHTML is used. May be vulnerable to XSS if data is not sanitized.' },
    { pattern: /document\.write\s*\(/g,              severity: 'high',   name: 'document.write() usage',        desc: 'document.write() is used. Potential injection vector.' },
    { pattern: /new\s+Function\s*\(/g,               severity: 'high',   name: 'new Function() usage',          desc: 'Dynamic function constructor is used. Potential code injection vector.' },
    { pattern: /setTimeout\s*(['"`]|\x60)/g,         severity: 'medium', name: 'setTimeout with string',        desc: 'setTimeout is called with a string argument. Equivalent to eval().' },
    { pattern: /setInterval\s*(['"`]|\x60)/g,        severity: 'medium', name: 'setInterval with string',       desc: 'setInterval is called with a string argument. Equivalent to eval().' },
    { pattern: /on(error|load)\s*=\s*['"]/g,         severity: 'low',    name: 'Inline event handler',          desc: 'Inline event handler detected. Violates CSP best practices.' },
    { pattern: /javascript\s*:/g,                    severity: 'high',   name: 'javascript: URI',               desc: 'javascript: URI scheme detected. Potential XSS vector.' },
    { pattern: /document\.cookie\s*=/g,              severity: 'medium', name: 'Cookie write',                  desc: 'Cookie is being set via JavaScript. Verify HttpOnly and Secure flags.' },
    { pattern: /localStorage\.setItem\s*\(/g,        severity: 'low',    name: 'localStorage write',            desc: 'Data stored in localStorage. Ensure no sensitive data is stored client-side.' },
    { pattern: /sessionStorage\.setItem\s*\(/g,      severity: 'low',    name: 'sessionStorage write',          desc: 'Data stored in sessionStorage. Ensure no sensitive data is stored client-side.' },
    { pattern: /XMLHttpRequest/g,                    severity: 'info',   name: 'XHR request',                   desc: 'XMLHttpRequest detected. Verify all endpoints require authentication.' },
    { pattern: /fetch\s*\(/g,                        severity: 'info',   name: 'Fetch API call',                desc: 'Fetch API call detected. Verify all endpoints require authentication.' },
    { pattern: /window\.open\s*\(/g,                 severity: 'low',    name: 'window.open()',                 desc: 'window.open() detected. Verify popup blockers are respected.' },
    { pattern: /\.src\s*=\s*[^'"]*\+/g,              severity: 'medium', name: 'Dynamic image src',             desc: 'Dynamic image source concatenation. May be vulnerable to image injection.' },
    { pattern: /postMessage/g,                       severity: 'medium', name: 'postMessage usage',             desc: 'postMessage detected. Verify origin validation is implemented.' }
  ];

  // Paths that should NOT exist on a static site (honeypot checks)
  var HONEYPOT_PATHS = [
    '/admin/backup-db',
    '/admin/restore',
    '/api/v1/users',
    '/api/v1/secrets',
    '/internal/audit-log',
    '/backup/alieninc-full.sql',
    '/.env.production',
    '/.env.backup',
    '/config/database.yml',
    '/wp-content/uploads/private/'
  ];

  // =========================================================================
  // UTILITY FUNCTIONS
  // =========================================================================

  function fetchWithTimeout(url, timeoutMs) {
    timeoutMs = timeoutMs || 5000;
    var controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
    var timer = null;
    var opts = { method: 'HEAD', mode: 'no-cors' };
    if (controller) {
      opts.signal = controller.signal;
      timer = setTimeout(function () { controller.abort(); }, timeoutMs);
    }
    return window.fetch(url, opts).then(function (res) {
      if (timer) clearTimeout(timer);
      return res;
    }).catch(function (err) {
      if (timer) clearTimeout(timer);
      throw err;
    });
  }

  function getBaseUrl() {
    return window.location.protocol + '//' + window.location.host;
  }

  function resolvePath(basePath, checkPath) {
    var base = basePath.replace(/\/+$/, '');
    return base + checkPath;
  }

  // =========================================================================
  // CHECK: Exposed Sensitive Files
  // =========================================================================
  function checkExposedFiles(basePath) {
    var results = [];
    var promises = SENSITIVE_PATHS.map(function (item) {
      var url = resolvePath(basePath, item.path);
      return fetchWithTimeout(url, 3000).then(function (res) {
        // In no-cors mode, status is 0 but type is 'opaque'
        // If we get any response (even opaque), the file likely exists
        var accessible = res.type === 'opaque' || (res.status >= 200 && res.status < 400);
        if (accessible) {
          results.push({
            type: 'exposed_file',
            severity: item.severity,
            name: item.name,
            path: item.path,
            desc: item.desc,
            url: url,
            evidence: 'Response received (status: ' + res.status + ', type: ' + res.type + ')'
          });
        }
      }).catch(function () {
        // Connection refused or CORS block = likely doesn't exist or properly blocked
      });
    });
    return Promise.all(promises).then(function () { return results; });
  }

  // =========================================================================
  // CHECK: Security Headers (via meta tags since we can't read headers cross-origin)
  // =========================================================================
  function checkSecurityHeaders() {
    var results = [];

    // Check meta tags (limited but useful for static sites)
    var metaChecks = {
      'Content-Security-Policy': document.querySelector('meta[http-equiv="Content-Security-Policy"]'),
      'X-Frame-Options': document.querySelector('meta[http-equiv="X-Frame-Options"]'),
      'X-Content-Type-Options': document.querySelector('meta[http-equiv="X-Content-Type-Options"]'),
      'Referrer-Policy': document.querySelector('meta[http-equiv="Referrer-Policy"]'),
      'Permissions-Policy': document.querySelector('meta[http-equiv="Permissions-Policy"]')
    };

    SECURITY_HEADERS.forEach(function (item) {
      var metaTag = metaChecks[item.header];
      var hasHeader = !!metaTag;

      // Also check if CSP is set via meta tag content
      if (item.header === 'Content-Security-Policy' && metaTag) {
        var cspContent = metaTag.getAttribute('content') || '';
        if (cspContent.length < 20) {
          hasHeader = false; // CSP is too weak
        }
      }

      if (!hasHeader) {
        results.push({
          type: 'missing_header',
          severity: item.severity,
          name: item.name,
          header: item.header,
          desc: item.desc,
          evidence: 'Header not found in meta tags or response'
        });
      }
    });

    return Promise.resolve(results);
  }

  // =========================================================================
  // CHECK: JavaScript Vulnerabilities
  // =========================================================================
  function checkJsVulnerabilities() {
    var results = [];
    var scripts = document.querySelectorAll('script:not([src])');

    scripts.forEach(function (script, idx) {
      var code = script.textContent || '';
      if (code.length < 10) return; // Skip tiny inline scripts

      JS_VULNERABILITY_PATTERNS.forEach(function (pattern) {
        var matches = code.match(pattern.pattern);
        if (matches && matches.length > 0) {
          results.push({
            type: 'js_vulnerability',
            severity: pattern.severity,
            name: pattern.name,
            desc: pattern.desc,
            count: matches.length,
            scriptIndex: idx,
            evidence: matches.length + ' occurrence(s) found in inline script #' + (idx + 1)
          });
        }
      });
    });

    // Also check external script sources for suspicious patterns
    var externalScripts = document.querySelectorAll('script[src]');
    externalScripts.forEach(function (script) {
      var src = script.getAttribute('src') || '';
      if (src.indexOf('javascript:') === 0) {
        results.push({
          type: 'js_vulnerability',
          severity: 'high',
          name: 'External javascript: URI',
          desc: 'External script loaded via javascript: URI. Highly suspicious.',
          evidence: 'src="' + src + '"'
        });
      }
    });

    return Promise.resolve(results);
  }

  // =========================================================================
  // CHECK: Information Disclosure
  // =========================================================================
  function checkInfoDisclosure() {
    var results = [];

    // Check for comments containing sensitive info
    var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_COMMENT, null, false);
    var sensitivePatterns = [
      { pattern: /password|passwd|pwd/i, name: 'Password reference in HTML comment' },
      { pattern: /api[_\s]?key|apikey|api_secret/i, name: 'API key reference in HTML comment' },
      { pattern: /todo|fixme|hack|bug/i, name: 'Development note in HTML comment' },
      { pattern: /admin|root|sudo/i, name: 'Admin reference in HTML comment' },
      { pattern: /token|secret|credential/i, name: 'Credential reference in HTML comment' },
      { pattern: /internal|private|confidential/i, name: 'Internal reference in HTML comment' }
    ];

    var commentCount = 0;
    while (walker.nextNode()) {
      commentCount++;
      var text = walker.currentNode.textContent;
      sensitivePatterns.forEach(function (item) {
        if (item.pattern.test(text)) {
          results.push({
            type: 'info_disclosure',
            severity: 'medium',
            name: item.name,
            desc: 'HTML comment contains sensitive keywords that could aid reconnaissance.',
            evidence: 'Comment #' + commentCount + ' matches pattern'
          });
        }
      });
    }

    // Check for meta tags that leak info
    var generatorMeta = document.querySelector('meta[name="generator"]');
    if (generatorMeta) {
      results.push({
        type: 'info_disclosure',
        severity: 'low',
        name: 'Generator meta tag',
        desc: 'Generator meta tag reveals technology stack.',
        evidence: 'content="' + generatorMeta.getAttribute('content') + '"'
      });
    }

    // Check for exposed API endpoints in inline scripts
    var inlineScripts = document.querySelectorAll('script:not([src])');
    var apiPattern = /https?:\/\/[^\s'"]+api[^\s'"]+/gi;
    inlineScripts.forEach(function (script) {
      var code = script.textContent || '';
      var apiMatches = code.match(apiPattern);
      if (apiMatches) {
        apiMatches.forEach(function (url) {
          if (url.indexOf('localhost') === -1 && url.indexOf('127.0.0.1') === -1) {
            results.push({
              type: 'info_disclosure',
              severity: 'medium',
              name: 'Exposed API endpoint',
              desc: 'API endpoint URL found in inline JavaScript.',
              evidence: url
            });
          }
        });
      }
    });

    return Promise.resolve(results);
  }

  // =========================================================================
  // CHECK: Clickjacking & Framing
  // =========================================================================
  function checkFraming() {
    var results = [];

    // Check if page is frameable
    if (window.self !== window.top) {
      results.push({
        type: 'framing',
        severity: 'high',
        name: 'Page is framed',
        desc: 'This page is loaded inside an iframe. May be vulnerable to clickjacking.',
        evidence: 'window.self !== window.top'
      });
    }

    // Check for X-Frame-Options in meta (already covered in headers but double-check)
    var xfo = document.querySelector('meta[http-equiv="X-Frame-Options"]');
    if (!xfo) {
      results.push({
        type: 'framing',
        severity: 'medium',
        name: 'No frame-busting protection',
        desc: 'Page has no X-Frame-Options or CSP frame-ancestors to prevent framing.',
        evidence: 'No framing protection detected'
      });
    }

    return Promise.resolve(results);
  }

  // =========================================================================
  // CHECK: Honeypot Link Detection (visible only to bots)
  // =========================================================================
  function checkHoneypotIntegrity() {
    var results = [];

    // Verify honeypot links are properly hidden from humans
    var honeypots = document.querySelectorAll('[data-hs-honeypot]');
    honeypots.forEach(function (el) {
      var style = window.getComputedStyle(el);
      var isVisible = style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0';

      if (isVisible) {
        // Check if it has proper anti-bot attributes
        var tabIndex = el.getAttribute('tabindex');
        var ariaHidden = el.getAttribute('aria-hidden');
        if (tabIndex !== '-1' || ariaHidden !== 'true') {
          results.push({
            type: 'honeypot_issue',
            severity: 'medium',
            name: 'Honeypot link visible to keyboard navigation',
            desc: 'A honeypot link may be accessible to screen readers or keyboard users.',
            evidence: 'tabindex=' + tabIndex + ', aria-hidden=' + ariaHidden
          });
        }
      }
    });

    return Promise.resolve(results);
  }

  // =========================================================================
  // CHECK: Ecosystem Data Exposure
  // =========================================================================
  function checkEcosystemExposure(basePath) {
    var results = [];
    var dataPaths = [
      '/data/alieninc-ecosystem.json',
      '/data/ecosystem-data.js',
      '/data/ecosystem-render.js'
    ];

    var promises = dataPaths.map(function (path) {
      var url = resolvePath(basePath, path);
      return fetchWithTimeout(url, 3000).then(function (res) {
        var accessible = res.type === 'opaque' || (res.status >= 200 && res.status < 400);
        if (accessible) {
          results.push({
            type: 'data_exposure',
            severity: path.indexOf('.json') !== -1 ? 'high' : 'medium',
            name: 'Ecosystem data accessible',
            desc: 'Internal data file is publicly accessible: ' + path,
            path: path,
            url: url,
            evidence: 'Response received (status: ' + res.status + ', type: ' + res.type + ')',
            recommendation: 'Restrict access to data files via robots.txt, server config, or CDN rules.'
          });
        }
      }).catch(function () {});
    });

    return Promise.all(promises).then(function () { return results; });
  }

  // =========================================================================
  // CHECK: Bot Scraper Boundary
  // =========================================================================
  function checkBotScraperBoundary() {
    var results = [];
    var ecosystemEls = document.querySelectorAll('[data-ecosystem]');
    var placeholderCount = 0;
    var hasMonetary = false;
    var monetaryRegex = /\$\d+\.?\d*[KMB]/i;

    ecosystemEls.forEach(function (el) {
      var text = (el.textContent || '').trim();
      if (text === 'Private — login required') {
        placeholderCount++;
      }
      if (monetaryRegex.test(text)) {
        hasMonetary = true;
      }
    });

    var ecosystemDataLoaded = typeof EcosystemData !== 'undefined';
    var ecosystemRenderLoaded = typeof EcosystemRender !== 'undefined';

    // Check for PII/sensitive data in visible page text
    var bodyText = (document.body && document.body.innerText) || '';
    var emailMatches = bodyText.match(/\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b/g) || [];
    var phoneMatches = bodyText.match(/\b(?:\+?\d{1,3}[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b/g) || [];

    if (ecosystemEls.length > 0 && placeholderCount === ecosystemEls.length) {
      results.push({
        type: 'bot_data_leak',
        severity: 'high',
        name: 'Human visitor served bot-sanitized page',
        desc: placeholderCount + ' data-ecosystem element(s) contain "Private — login required" — the bot-sanitized version is being served to human visitors. Dynamic rendering misconfigured.',
        evidence: 'All ' + ecosystemEls.length + ' data elements show placeholder text instead of real values.',
        recommendation: 'Verify server-side bot detection logic. Ensure human User-Agent strings are not matching bot patterns. Check bypass header configuration.'
      });
    } else if (ecosystemEls.length > 0 && placeholderCount > 0) {
      results.push({
        type: 'bot_data_leak',
        severity: 'medium',
        name: 'Partial bot-sanitized content leaking to humans',
        desc: placeholderCount + ' of ' + ecosystemEls.length + ' data-ecosystem element(s) contain placeholder text. Some data may be hidden from human visitors.',
        evidence: placeholderCount + '/' + ecosystemEls.length + ' elements show "Private — login required".',
        recommendation: 'Review dynamic rendering logic for partial sanitization or stale cached bot responses.'
      });
    } else if (!ecosystemDataLoaded && !ecosystemRenderLoaded) {
      results.push({
        type: 'bot_data_leak',
        severity: 'low',
        name: 'Ecosystem scripts not loaded',
        desc: 'EcosystemData and EcosystemRender are not available in the global scope. Dynamic data may fail to render.',
        evidence: 'typeof EcosystemData: ' + ecosystemDataLoaded + ', typeof EcosystemRender: ' + ecosystemRenderLoaded,
        recommendation: 'Verify that ecosystem-data.js and ecosystem-render.js are correctly included and not blocked.'
      });
    } else if (hasMonetary) {
      results.push({
        type: 'bot_data_leak',
        severity: 'info',
        name: 'Dynamic rendering active — real data visible to humans',
        desc: ecosystemEls.length + ' data-ecosystem element(s) display real financial values. Ecosystem scripts loaded. Dynamic rendering boundary appears correct for human visitors.',
        evidence: 'EcosystemData: ' + ecosystemDataLoaded + ', EcosystemRender: ' + ecosystemRenderLoaded + ', monetary values present: ' + hasMonetary,
        recommendation: 'No action required. Bot boundary should be verified server-side via automated scanner (plugin 1010).'
      });
    }

    // PII detection in visible page text (emails, phones visible to current UA)
    if (emailMatches.length > 0) {
      results.push({
        type: 'bot_data_leak',
        severity: 'medium',
        name: 'Email addresses visible in page text',
        desc: emailMatches.length + ' email(s) found in visible page content: ' + emailMatches.slice(0, 3).join(', '),
        evidence: 'Emails in page: ' + emailMatches.join(', '),
        recommendation: 'Ensure email addresses are redacted for bot User-Agent requests. Add email pattern to server-side sanitizer.'
      });
    }
    if (phoneMatches.length > 0) {
      results.push({
        type: 'bot_data_leak',
        severity: 'medium',
        name: 'Phone numbers visible in page text',
        desc: phoneMatches.length + ' phone number(s) found in visible page content: ' + phoneMatches.slice(0, 3).join(', '),
        evidence: 'Phones in page: ' + phoneMatches.join(', '),
        recommendation: 'Ensure phone numbers are redacted for bot User-Agent requests. Add phone pattern to server-side sanitizer.'
      });
    }

    return Promise.resolve(results);
  }

  // =========================================================================
  // MAIN SCAN FUNCTION
  // =========================================================================
  function scan() {
    scanTimestamp = new Date().toISOString();
    var baseUrl = getBaseUrl();
    var allResults = [];
    var scanTargets = ECOSYSTEM_DOMAINS;

    // Run checks on current page first (fast, no network requests)
    var localChecks = Promise.all([
      checkSecurityHeaders(),
      checkJsVulnerabilities(),
      checkInfoDisclosure(),
      checkFraming(),
      checkHoneypotIntegrity(),
      checkBotScraperBoundary()
    ]).then(function (resultSets) {
      resultSets.forEach(function (r) { allResults = allResults.concat(r); });
    });

    // Run network checks for each ecosystem domain
    var networkChecks = Promise.resolve();
    scanTargets.forEach(function (target) {
      networkChecks = networkChecks.then(function () {
        var targetUrl = baseUrl + target.url;
        return Promise.all([
          checkExposedFiles(targetUrl),
          checkEcosystemExposure(targetUrl)
        ]).then(function (resultSets) {
          resultSets.forEach(function (r) {
            r.forEach(function (item) {
              item.target = target.id;
              item.targetName = target.name;
              allResults.push(item);
            });
          });
        });
      });
    });

    return Promise.all([localChecks, networkChecks]).then(function () {
      // Build report
      var report = buildReport(allResults);
      lastReport = report;
      return report;
    });
  }

  // =========================================================================
  // SCAN SINGLE TARGET
  // =========================================================================
  function scanTarget(url) {
    scanTimestamp = new Date().toISOString();
    var allResults = [];

    return Promise.all([
      checkExposedFiles(url),
      checkEcosystemExposure(url),
      checkSecurityHeaders(),
      checkJsVulnerabilities(),
      checkInfoDisclosure(),
      checkFraming(),
      checkBotScraperBoundary()
    ]).then(function (resultSets) {
      resultSets.forEach(function (r) { allResults = allResults.concat(r); });
      var report = buildReport(allResults);
      lastReport = report;
      return report;
    });
  }

  // =========================================================================
  // BUILD REPORT
  // =========================================================================
  function buildReport(results) {
    var critical = results.filter(function (r) { return r.severity === 'critical'; });
    var high = results.filter(function (r) { return r.severity === 'high'; });
    var medium = results.filter(function (r) { return r.severity === 'medium'; });
    var low = results.filter(function (r) { return r.severity === 'low'; });
    var info = results.filter(function (r) { return r.severity === 'info'; });

    var score = 100;
    critical.forEach(function () { score -= 15; });
    high.forEach(function () { score -= 8; });
    medium.forEach(function () { score -= 3; });
    low.forEach(function () { score -= 1; });
    score = Math.max(0, score);

    var grade;
    if (score >= 90) grade = 'A';
    else if (score >= 80) grade = 'B';
    else if (score >= 70) grade = 'C';
    else if (score >= 60) grade = 'D';
    else grade = 'F';

    return {
      version: SCAN_VERSION,
      timestamp: scanTimestamp,
      scannedAt: new Date(scanTimestamp).toLocaleString(),
      score: score,
      grade: grade,
      summary: {
        total: results.length,
        critical: critical.length,
        high: high.length,
        medium: medium.length,
        low: low.length,
        info: info.length
      },
      results: results,
      findings: {
        critical: critical,
        high: high,
        medium: medium,
        low: low,
        info: info
      },
      targets: ECOSYSTEM_DOMAINS,
      recommendations: generateRecommendations(results)
    };
  }

  // =========================================================================
  // GENERATE RECOMMENDATIONS
  // =========================================================================
  function generateRecommendations(results) {
    var recs = [];
    var types = {};

    results.forEach(function (r) {
      if (!types[r.type]) types[r.type] = 0;
      types[r.type]++;
    });

    if (types.exposed_file) {
      recs.push({
        priority: 'immediate',
        title: 'Remove exposed sensitive files',
        desc: types.exposed_file + ' sensitive file(s) are publicly accessible. Remove them from production or restrict access via server configuration.',
        action: 'Add server-level access controls for sensitive paths, or remove files from the public directory.'
      });
    }

    if (types.missing_header) {
      recs.push({
        priority: 'high',
        title: 'Add security headers',
        desc: types.missing_header + ' security header(s) are missing. These headers protect against XSS, clickjacking, and other attacks.',
        action: 'Configure your web server or CDN to send the missing headers. For static hosting, add meta tags as a fallback.'
      });
    }

    if (types.js_vulnerability) {
      recs.push({
        priority: 'high',
        title: 'Audit JavaScript for injection vulnerabilities',
        desc: types.js_vulnerability + ' potential JavaScript vulnerability pattern(s) detected.',
        action: 'Review inline scripts for eval(), innerHTML, and document.write() usage. Replace with safe alternatives.'
      });
    }

    if (types.data_exposure) {
      recs.push({
        priority: 'high',
        title: 'Restrict access to ecosystem data',
        desc: 'Internal data files are publicly accessible via HTTP requests.',
        action: 'Move data files behind authentication or restrict access at the server/CDN level.'
      });
    }

    if (types.bot_data_leak) {
      recs.push({
        priority: 'high',
        title: 'Enforce bot vs human dynamic rendering boundary',
        desc: types.bot_data_leak + ' bot data leak finding(s) detected. Crawlers may be receiving real operating data that should only be visible to human visitors.',
        action: 'Implement server-side User-Agent detection. Serve sanitized HTML to bots with placeholder text instead of real revenue figures. Verify the boundary with plugin 1010.'
      });
    }

    if (types.info_disclosure) {
      recs.push({
        priority: 'medium',
        title: 'Remove information disclosure',
        desc: types.info_disclosure + ' instance(s) of information leakage found in HTML comments and meta tags.',
        action: 'Audit HTML comments and remove any sensitive information before deployment.'
      });
    }

    if (types.framing) {
      recs.push({
        priority: 'medium',
        title: 'Add clickjacking protection',
        desc: 'Page can be embedded in iframes without restriction.',
        action: 'Add X-Frame-Options or CSP frame-ancestors header/meta tag.'
      });
    }

    return recs;
  }

  // =========================================================================
  // PRINT REPORT
  // =========================================================================
  function printReport(report) {
    report = report || lastReport;
    if (!report) {
      console.log('[Centra] No scan report available. Run CentraScanner.scan() first.');
      return;
    }

    var divider = '═══════════════════════════════════════════════════════';
    console.log('\n' + divider);
    console.log('  CENTRA Vulnerability Scan Report');
    console.log('  Scan version: ' + report.version);
    console.log('  Scanned at: ' + report.scannedAt);
    console.log(divider);
    console.log('');
    console.log('  SECURITY SCORE: ' + report.score + '/100 (Grade: ' + report.grade + ')');
    console.log('');
    console.log('  FINDINGS SUMMARY:');
    console.log('    Critical: ' + report.summary.critical);
    console.log('    High:     ' + report.summary.high);
    console.log('    Medium:   ' + report.summary.medium);
    console.log('    Low:      ' + report.summary.low);
    console.log('    Info:     ' + report.summary.info);
    console.log('    Total:    ' + report.summary.total);
    console.log('');

    if (report.findings.critical.length > 0) {
      console.log('  ─── CRITICAL FINDINGS ───');
      report.findings.critical.forEach(function (f, i) {
        console.log('  ' + (i + 1) + '. [' + (f.targetName || 'Current Page') + '] ' + f.name);
        console.log('     ' + f.desc);
        if (f.evidence) console.log('     Evidence: ' + f.evidence);
        console.log('');
      });
    }

    if (report.findings.high.length > 0) {
      console.log('  ─── HIGH FINDINGS ───');
      report.findings.high.forEach(function (f, i) {
        console.log('  ' + (i + 1) + '. [' + (f.targetName || 'Current Page') + '] ' + f.name);
        console.log('     ' + f.desc);
        console.log('');
      });
    }

    if (report.findings.medium.length > 0) {
      console.log('  ─── MEDIUM FINDINGS ───');
      report.findings.medium.forEach(function (f, i) {
        console.log('  ' + (i + 1) + '. [' + (f.targetName || 'Current Page') + '] ' + f.name);
        console.log('');
      });
    }

    if (report.recommendations.length > 0) {
      console.log('  ─── RECOMMENDATIONS ───');
      report.recommendations.forEach(function (r, i) {
        console.log('  ' + (i + 1) + '. [' + r.priority.toUpperCase() + '] ' + r.title);
        console.log('     ' + r.desc);
        console.log('     Action: ' + r.action);
        console.log('');
      });
    }

    console.log(divider);
    console.log('  Report generated by Centra v' + SCAN_VERSION);
    console.log('  Centra — Exposure & Vulnerability Management');
    console.log('  A subsidiary of Alien Inc.');
    console.log(divider + '\n');
  }

  // =========================================================================
  // PUBLIC API
  // =========================================================================
  return {
    scan: scan,
    scanTarget: scanTarget,
    getReport: function () { return lastReport; },
    printReport: printReport,
    getTargets: function () { return ECOSYSTEM_DOMAINS.slice(); },
    version: SCAN_VERSION
  };
})();

// Auto-export for module environments
if (typeof module !== 'undefined' && module.exports) {
  module.exports = CentraScanner;
}
