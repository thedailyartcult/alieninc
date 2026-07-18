/**
 * EcosystemData — single data layer for all Alien.Inc sites.
 *
 * Usage:
 *   <script src="path/to/ecosystem-data.js"></script>
 *   <script>
 *     EcosystemData.init().then(function(data) { ... });
 *     EcosystemData.onChange(function(data) { ... });
 *   </script>
 *
 * The script auto-detects whether it lives at root or inside a company
 * folder (one level deep) and resolves the JSON path accordingly.
 */

var EcosystemData = (function () {
  var _data = null;
  var _listeners = [];
  var _timer = null;
  var _jsonUrl = null;

  // Capture document.currentScript NOW, during synchronous IIFE execution.
  // By the time resolveJsonUrl() is called from load() → init(), this will be null.
  var _ownScriptEl = (typeof document !== 'undefined' && document.currentScript)
    ? document.currentScript
    : null;

  function resolveJsonUrl() {
    if (_jsonUrl) return _jsonUrl;

    // Strategy 1: Use the script tag's own src (most reliable — works from any directory)
    if (_ownScriptEl && _ownScriptEl.src) {
      var scriptDir = _ownScriptEl.src.replace(/\/[^\/]*$/, '/');
      _jsonUrl = scriptDir + 'alieninc-ecosystem.json';
      return _jsonUrl;
    }

    // Strategy 2: Try relative path from the page (works for file:// protocol)
    var testUrl = 'data/alieninc-ecosystem.json';
    _jsonUrl = testUrl;
    return _jsonUrl;
  }

  function load() {
    var url = resolveJsonUrl() + '?t=' + Date.now();
    return window.fetch(url)
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status + ' for ' + url);
        return res.json();
      })
      .then(function (next) {
        var changed = JSON.stringify(next) !== JSON.stringify(_data);
        _data = next;
        if (changed) notify();
        return _data;
      })
      .catch(function (err) {
        console.warn('[EcosystemData] load failed:', err.message, '| attempted URL:', url);
        return _data;
      });
  }

  function notify() {
    for (var i = 0; i < _listeners.length; i++) {
      try { _listeners[i](_data); } catch (e) { console.error('[EcosystemData]', e); }
    }
  }

  function onChange(fn) {
    _listeners.push(fn);
    if (_data) fn(_data);
    return function () {
      _listeners = _listeners.filter(function (l) { return l !== fn; });
    };
  }

  function startPolling(ms) {
    stopPolling();
    _timer = setInterval(load, ms || 5000);
  }

  function stopPolling() {
    if (_timer) { clearInterval(_timer); _timer = null; }
  }

  function get()             { return _data; }
  function getCompany(id)    { return _data && _data.companies ? _data.companies.find(function (c) { return c.id === id; }) : null; }
  function getRollup()       { return _data ? (_data.groupRollup || null) : null; }

  function getUrl() {
    return resolveJsonUrl();
  }

  function init() {
    startPolling();
    return load();
  }

  /**
   * Returns a public-safe copy of the data with a 24-hour delay applied
   * to timestamps. Financial figures are unchanged (they are annual
   * forecasts), but lastUpdated and asOf dates are shifted back 24h
   * so the public dashboard never shows real-time internal state.
   */
  function getPublicData() {
    if (!_data) return null;
    var copy = JSON.parse(JSON.stringify(_data));
    var delay = 24 * 60 * 60 * 1000;
    var now = Date.now();
    // Shift fundCentre.lastUpdated
    if (copy.fundCentre && copy.fundCentre.lastUpdated) {
      var ts = new Date(copy.fundCentre.lastUpdated).getTime();
      copy.fundCentre.lastUpdated = new Date(Math.min(ts, now - delay)).toISOString();
    }
    // Shift metadata.asOf
    if (copy.metadata && copy.metadata.asOf) {
      var ts2 = new Date(copy.metadata.asOf).getTime();
      copy.metadata.asOf = new Date(Math.min(ts2, now - delay)).toISOString().split('T')[0];
    }
    // Add a computed public timestamp
    copy._publicAsOf = new Date(now - delay).toISOString();
    return copy;
  }

  return {
    init: init,
    load: load,
    getUrl: getUrl,
    onChange: onChange,
    get: get,
    getPublicData: getPublicData
  };
})();