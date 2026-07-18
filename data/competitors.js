/**
 * Competitors — live market data for global conglomerates vs Alien Inc.
 *
 * Fetches from the local server proxy (/api/competitors) which handles
 * the Yahoo Finance crumb authentication flow server-side.
 * Falls back to stale localStorage cache if the proxy is unavailable.
 */

var Competitors = (function () {
  var CACHE_KEY = 'alieninc_competitor_cache_v2';
  var CACHE_TTL = 6 * 60 * 60 * 1000;

  function fmt(val) {
    if (val === null || val === undefined) return '—';
    var abs = Math.abs(val);
    if (abs >= 1e12) return (val / 1e12).toFixed(1) + 'T';
    if (abs >= 1e9) return (val / 1e9).toFixed(1) + 'B';
    if (abs >= 1e6) return (val / 1e6).toFixed(1) + 'M';
    if (abs >= 1e3) return (val / 1e3).toFixed(0) + 'K';
    return val.toString();
  }

  function curr(val, ccy, targetCcy) {
    if (val === null || val === undefined) return '—';
    var displayCcy = targetCcy || ccy;
    var converted = (targetCcy && typeof ExchangeRates !== 'undefined')
      ? ExchangeRates.convert(val, ccy, targetCcy)
      : val;
    var sym = displayCcy === 'USD' ? '$' : displayCcy === 'EUR' ? '\u20AC' : displayCcy === 'KRW' ? '\u20A9' : displayCcy === 'PHP' ? '\u20B1' : '';
    return sym + fmt(converted);
  }

  function getCache() {
    try {
      var raw = localStorage.getItem(CACHE_KEY);
      if (!raw) return null;
      return JSON.parse(raw);
    } catch (e) {
      return null;
    }
  }

  function getValidCache() {
    var data = getCache();
    if (!data) return null;
    if (Date.now() - data.ts > CACHE_TTL) return null;
    var list = data.competitors;
    if (!list || list.length === 0) return null;
    var anyLive = list.some(function (c) { return c.status === 'live'; });
    if (!anyLive) { invalidate(); return null; }
    return list;
  }

  function saveCache(list) {
    try {
      localStorage.setItem(CACHE_KEY, JSON.stringify({
        ts: Date.now(),
        competitors: list
      }));
    } catch (e) {}
  }

  function fetchFromProxy() {
    return fetch('/api/competitors?_t=' + Date.now())
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (json) {
        return json.competitors || [];
      });
  }

  function init() {
    return fetchFromProxy().then(function (list) {
      if (list && list.length > 0) {
        var anyLive = list.some(function (c) { return c.status === 'live'; });
        if (anyLive) saveCache(list);
      }
      return list || [];
    }).catch(function (err) {
      console.warn('[Competitors] Proxy fetch failed:', err.message);
      var cached = getValidCache();
      if (cached) return cached;
      var stale = getCache();
      if (stale && stale.competitors) return stale.competitors;
      return [];
    });
  }

  function invalidate() {
    localStorage.removeItem(CACHE_KEY);
  }

  return {
    init: init,
    curr: curr
  };
})();
