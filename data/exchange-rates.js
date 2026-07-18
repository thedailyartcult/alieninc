/**
 * ExchangeRates — live currency conversion for the dashboard.
 *
 * Fetches ECB rates from frankfurter.app (free, no API key).
 * Caches in localStorage for 1 hour.
 * Falls back to static approximate rates if offline.
 */

var ExchangeRates = (function () {
  var CACHE_KEY = 'alieninc_exchange_rates';
  var CACHE_TTL = 60 * 60 * 1000; // 1 hour
  var API_BASE = 'https://api.frankfurter.app/latest?from=USD';

  var FALLBACK = { USD: 1.0, EUR: 0.85, KRW: 1350, PHP: 56 };
  var SUPPORTED = ['USD', 'EUR', 'KRW', 'PHP'];
  var rates = null;

  function getCache() {
    try {
      var raw = localStorage.getItem(CACHE_KEY);
      if (!raw) return null;
      var data = JSON.parse(raw);
      if (Date.now() - data.ts > CACHE_TTL) return null;
      return data.rates;
    } catch (e) {
      return null;
    }
  }

  function saveCache(r) {
    try {
      localStorage.setItem(CACHE_KEY, JSON.stringify({ ts: Date.now(), rates: r }));
    } catch (e) {}
  }

  function fetchRates() {
    var toParam = SUPPORTED.filter(function (c) { return c !== 'USD'; }).join(',');
    return fetch(API_BASE + '&to=' + toParam)
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (json) {
        var r = Object.assign({ USD: 1.0 }, json.rates);
        saveCache(r);
        return r;
      });
  }

  function init() {
    var cached = getCache();
    if (cached) {
      rates = cached;
      return Promise.resolve(rates);
    }
    return fetchRates().then(function (r) {
      rates = r;
      return r;
    }).catch(function () {
      rates = Object.assign({}, FALLBACK);
      return rates;
    });
  }

  function getRates() {
    return rates || Object.assign({}, FALLBACK);
  }

  function convert(amount, fromCcy, toCcy) {
    if (amount === null || amount === undefined) return null;
    if (fromCcy === toCcy) return amount;
    var r = getRates();
    var fromRate = r[fromCcy];
    var toRate = r[toCcy];
    if (!fromRate || !toRate) return amount;
    return amount * (toRate / fromRate);
  }

  function symbol(ccy) {
    if (ccy === 'USD') return '$';
    if (ccy === 'EUR') return '\u20AC';
    if (ccy === 'KRW') return '\u20A9';
    if (ccy === 'PHP') return '\u20B1';
    return '';
  }

  return {
    init: init,
    convert: convert,
    getRates: getRates,
    symbol: symbol,
    SUPPORTED: SUPPORTED
  };
})();
