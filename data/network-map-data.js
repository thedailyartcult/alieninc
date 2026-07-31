/**
 * NetworkMapData — single source of truth for the interactive network map.
 *
 * Reads the `networkMap` section of the ecosystem data and exposes the
 * globals the map renderer expects:
 *
 *   window.aliensNetworkNodes  — company network nodes (enriched with the
 *                                resident population of their host city and
 *                                the public company record behind each node)
 *   window.fableDistricts      — district label coordinates
 *   window.fableLgus           — city/LGU data (resident population, census
 *                                year, province). No financial data.
 *   window.ecosystemSummary    — real group numbers derived from the data:
 *                                node/company counts, group headcount,
 *                                earliest founding year, data as-of date.
 *
 * Data source order:
 *   1. window.ECOSYSTEM_DATA  — injected server-side (authenticated pages),
 *                               refreshed after client login.
 *   2. /api/ecosystem/public  — the public ecosystem API endpoint.
 *
 * Only the networkMap section and the public (non-financial) company profile
 * fields are ever copied into the map globals; no cash, revenue, or margin
 * data is exposed to the page.
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
    window.ecosystemSummary = window.ecosystemSummary || null;
  }

  // Public, non-financial fields of a company profile that the map may render.
  var COMPANY_FIELDS = [
    'id', 'brandName', 'category', 'yearFounded', 'foundingDate', 'mission',
    'headcount', 'runtimeState'
  ];

  function pickPublicCompany(company) {
    if (!company) return null;
    var out = {};
    COMPANY_FIELDS.forEach(function (key) {
      if (company[key] !== undefined && company[key] !== null) out[key] = company[key];
    });
    // Only operational counts from runtimeState — never cash/revenue/margins.
    if (company.runtimeState) {
      out.clientCount = company.runtimeState.clientCount;
      out.activeProjectCount = company.runtimeState.activeProjectCount;
    }
    return out;
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

    var companiesById = {};
    (data.companies || []).forEach(function (company) {
      if (company && company.id) companiesById[company.id] = pickPublicCompany(company);
    });

    window.aliensNetworkNodes = (map.nodes || []).map(function (node) {
      var host = byName[String(node.city || '').toLowerCase()];
      if (host) {
        node.population = host.population;
        node.censusYear = host.censusYear || meta.censusYear || 2020;
        node.province = host.province || '';
      }
      if (node.companyId && companiesById[node.companyId]) {
        node.company = companiesById[node.companyId];
      }
      return node;
    });

    window.fableDistricts = map.districts || [];
    window.fableLgus = cities;

    window.ecosystemSummary = buildSummary(data, map, window.aliensNetworkNodes);
    _data = map;
  }

  // Real group numbers, all derived from the single source of truth.
  function buildSummary(data, map, nodes) {
    var summary = {
      nodeCount: (nodes || []).length,
      companyCount: ((data && data.companies) || []).length,
      groupHeadcount2026F: 0,
      earliestFounded: null,
      asOf: (map && map.metadata && map.metadata.asOf) ||
            (data && data.metadata && data.metadata.asOf) || '',
      source: (data && data.metadata && data.metadata.source) || ''
    };

    (nodes || []).forEach(function (node) {
      var company = node.company;
      if (!company) return;
      var hc = company.headcount;
      if (hc && typeof hc['2026F'] === 'number') {
        summary.groupHeadcount2026F += hc['2026F'];
      }
      if (typeof company.yearFounded === 'number') {
        summary.earliestFounded = (summary.earliestFounded === null)
          ? company.yearFounded
          : Math.min(summary.earliestFounded, company.yearFounded);
      }
    });

    return summary;
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
