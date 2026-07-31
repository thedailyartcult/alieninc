/**
 * NetworkMapData — single source of truth for the interactive network map.
 *
 * Reads the `networkMap` section of the ecosystem data and exposes the
 * globals the map renderer expects:
 *
 *   window.aliensNetworkNodes  — company network nodes (enriched with the
 *                                resident population of their host city)
 *   window.fableDistricts      — district label coordinates
 *   window.fableLgus           — city/LGU data (resident population, census
 *                                year, province). No financial data.
 *
 * Data source order:
 *   1. window.ECOSYSTEM_DATA  — injected server-side (authenticated pages),
 *                               refreshed after client login.
 *   2. /api/ecosystem/public  — the public ecosystem API endpoint.
 *
 * Only the networkMap section is ever copied into the map globals; no
 * financial or client data is exposed to the page.
 *
 * Usage (before the map script):
 *   <script src="data/network-map-data.js"></script>
 *   <script>
 *     NetworkMapData.load(function () { initNetworkMap(); });
 *   </script>
 */

var NetworkMapData = (function () {
  var _data = null;
  var _endpoint = '/api/ecosystem/public';

  // Guarantee the globals exist (empty arrays degrade the map gracefully).
  function ensureGlobals() {
    window.aliensNetworkNodes = window.aliensNetworkNodes || [];
    window.fableDistricts = window.fableDistricts || [];
    window.fableLgus = window.fableLgus || [];
  }

  function extractNetworkMap(data) {
    var map = (data && data.networkMap) || null;
    if (!map) return;
    var meta = map.metadata || {};
    var cities = map.cities || [];
    var byName = {};
    cities.forEach(function (city) {
      byName[String(city.name || '').toLowerCase()] = city;
    });

    window.aliensNetworkNodes = (map.nodes || []).map(function (node) {
      var host = byName[String(node.city || '').toLowerCase()];
      if (host) {
        node.population = host.population;
        node.censusYear = host.censusYear || meta.censusYear || 2020;
        node.province = host.province || '';
      }
      return node;
    });
    window.fableDistricts = map.districts || [];
    window.fableLgus = cities;
    _data = map;
  }

  function load(callback) {
    ensureGlobals();

    if (_data) {
      if (callback) callback(_data);
      return;
    }

    // 1) Server-injected global (authenticated sessions, post-login refresh).
    if (window.ECOSYSTEM_DATA && window.ECOSYSTEM_DATA.networkMap) {
      extractNetworkMap(window.ECOSYSTEM_DATA);
      if (callback) callback(_data);
      return;
    }

    // 2) Public ecosystem API endpoint (same-origin, always available).
    if (typeof window.fetch !== 'function') {
      if (callback) callback(_data);
      return;
    }

    window.fetch(_endpoint, { credentials: 'include' })
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status + ' for ' + _endpoint);
        return res.json();
      })
      .then(function (data) {
        extractNetworkMap(data);
        if (callback) callback(_data);
      })
      .catch(function (err) {
        console.warn('[NetworkMapData] load failed:', err.message, '| attempted URL:', _endpoint);
        if (callback) callback(_data);
      });
  }

  return {
    load: load,
    getEndpoint: function () { return _endpoint; }
  };
})();
