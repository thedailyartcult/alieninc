/**
 * EcosystemRender — shared DOM helpers for all Alien.Inc sites.
 *
 * Depends on EcosystemData (load ecosystem-data.js first).
 *
 * Usage — auto-bind all [data-ecosystem] elements:
 *
 *   <script src="data/ecosystem-data.js"></script>
 *   <script src="data/ecosystem-render.js"></script>
 *   <script>
 *     EcosystemData.init().then(EcosystemRender.bindAll);
 *     EcosystemData.onChange(EcosystemRender.bindAll);
 *   </script>
 *
 * Usage — bind specific sections:
 *
 *   EcosystemRender.bindFundTable(data);
 */

var EcosystemRender = (function () {

  // ── Formatting helpers ──────────────────────────────────────────────

  function fundCentreSummaryStr(fc) {
    var s = (fc && fc.summary) || {};
    return (s.totalFunds || 0) + ' funds \u00b7 ' +
           (s.totalShareClasses || 0) + ' share classes \u00b7 AUM ' +
           (s.totalAumFormatted || '\u2014');
  }

  function currency(val, prefix) {
    if (val == null) return '—';
    prefix = prefix || '$';
    if (Math.abs(val) >= 1e6) return prefix + (val / 1e6).toFixed(2) + 'M';
    if (Math.abs(val) >= 1e3) return prefix + (val / 1e3).toFixed(0) + 'K';
    return prefix + val;
  }

  function pct(val, decimals) {
    if (val == null) return '—';
    return val.toFixed(decimals != null ? decimals : 2) + '%';
  }

  function date(iso) {
    if (!iso) return '';
    var d = new Date(iso);
    var dd = String(d.getDate()).padStart(2, '0');
    var mm = String(d.getMonth() + 1).padStart(2, '0');
    return dd + '/' + mm + '/' + d.getFullYear();
  }

  // ── DOM binding: [data-ecosystem] ───────────────────────────────────
  //
  // Keys resolved from the ecosystem JSON:
  //   companyCount, standaloneRevenue, externalRevenue, ebitdaTotal
  //   company-{id}-revenue, company-{id}-ebitda, company-{id}-clients
  //   fundCentreSummary

  function buildKeyMap(data) {
    var m = {};
    if (!data) return m;
    var r = data.groupRollup || {};
    var companies = data.companies || [];

    m.companyCount       = companies.length;
    m.standaloneRevenue  = currency(r.standaloneRevenueTotal2026F);
    m.externalRevenue    = currency(r.estimatedExternalRevenue2026F);
    m.ebitdaTotal        = currency(r.standaloneEbitdaTotal2026F);
    m.primaryUser        = 'KMT';

    // Per-company revenue keys
    var rev = r.standaloneRevenue2026F || {};
    for (var id in rev) {
      m['company-' + id + '-revenue'] = currency(rev[id]);
    }

    // Per-company client count
    var clients = data.clientDatabase || [];
    var counts = {};
    clients.forEach(function (c) {
      counts[c.companyId] = (counts[c.companyId] || 0) + 1;
    });
    for (var cid in counts) {
      m['company-' + cid + '-clients'] = counts[cid] + ' client' + (counts[cid] !== 1 ? 's' : '');
    }

    // Fund centre summary
    var fc = data.fundCentre;
    if (fc) {
      m.fundCentreSummary = fundCentreSummaryStr(fc);
    }

    return m;
  }

  /**
   * Walk the DOM and set textContent for every [data-ecosystem] element.
   */
  function bindAll(data) {
    var map = buildKeyMap(data);
    var els = document.querySelectorAll('[data-ecosystem]');
    for (var i = 0; i < els.length; i++) {
      var key = els[i].getAttribute('data-ecosystem');
      if (map[key] !== undefined) {
        els[i].textContent = map[key];
      }
    }
  }

  // ── Fund Centre table ───────────────────────────────────────────────

  function perfCell(val) {
    if (val == null) return '<td class="perf-val">\u2014</td>';
    var cls = val < 0 ? ' class="perf-val" style="color:#ef4444;"' : ' class="perf-val"';
    return '<td' + cls + '>' + pct(val) + '</td>';
  }

  var ACTION_ICONS = [
    '<svg width="12" height="14" viewBox="0 0 12 14"><path d="M1 1H7L11 5V13H1V1Z"/></svg>',
    '<svg width="14" height="14" viewBox="0 0 14 14"><path d="M2 2H12V9H6L2 12V2Z"/></svg>',
    '<svg width="14" height="12" viewBox="0 0 14 12"><path d="M1 11H13M2 8L5 4L8 6L12 2"/></svg>',
    '<svg width="12" height="12" viewBox="0 0 12 12"><rect x="1" y="6" width="2" height="5"/><rect x="5" y="3" width="2" height="8"/><rect x="9" y="1" width="2" height="10"/></svg>',
    '<svg width="12" height="12" viewBox="0 0 12 12"><circle cx="6" cy="6" r="5"/><path d="M6 3V6L8 8"/></svg>',
    '<svg width="12" height="12" viewBox="0 0 12 12"><path d="M1 3H11M1 6H11M1 9H11" stroke-linecap="round"/></svg>'
  ];
  var DETAILS_ICON = '<svg width="14" height="14" viewBox="0 0 24 24"><circle cx="5" cy="12" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="19" cy="12" r="2"/></svg>';
  var EXPAND_ICON  = '<svg width="10" height="6" viewBox="0 0 10 6"><path d="M1 1L5 5L9 1" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';

  function actionsHtml() {
    return '<div class="quick-actions">' +
      ACTION_ICONS.map(function (s) { return '<button class="action-btn">' + s + '</button>'; }).join('') +
      '</div>';
  }

  function bindFundTable(data) {
    var tbody = document.querySelector('.fund-table tbody');
    if (!tbody) return;
    var fc = data && data.fundCentre;
    if (!fc) return;

    var funds = fc.funds || [];
    var html = '';

    funds.forEach(function (fund) {
      (fund.shareClasses || []).forEach(function (sc, i) {
        var isChild = i > 0;
        var p = sc.performance || {};

        html += '<tr' + (isChild ? ' class="child-row"' : '') + '>' +
          '<td class="col-expand">' + EXPAND_ICON + '</td>' +
          (isChild
            ? '<td class="fund-name-cell"></td>'
            : '<td class="fund-name-cell">' + fund.name + '<span class="fund-category">' + fund.category + '</span></td>') +
          '<td><span class="val-bold">' + sc.name + '</span><span class="info-sub">' + sc.isin + '</span></td>' +
          '<td><span class="val-bold">' + sc.nav.toFixed(2) + '</span><span class="info-sub">' + date(sc.navDate) + '</span></td>' +
          '<td><span class="val-bold">' + pct(sc.annualisedReturn) + '</span><span class="info-sub">' + date(sc.inceptionDate) + '</span></td>' +
          perfCell(p.ytd) + perfCell(p.oneYear) + perfCell(p.threeYear) + perfCell(p.fiveYear) + perfCell(p.tenYear) +
          '<td class="val-bold">' + pct(sc.volatility3Year) + '</td>' +
          '<td class="val-bold">' + sc.aumFormatted + '</td>' +
          '<td>' + actionsHtml() + '</td>' +
          '<td><button class="btn-details">' + DETAILS_ICON + '</button></td>' +
          '</tr>';
      });
    });

    tbody.innerHTML = html;
  }

  function bindFundBanner(data) {
    var wrapper = document.querySelector('.fund-table-wrapper');
    if (!wrapper) return;
    var fc = data && data.fundCentre;
    if (!fc) return;

    var banner = document.getElementById('ecosystem-banner');
    if (!banner) {
      banner = document.createElement('div');
      banner.id = 'ecosystem-banner';
      banner.className = 'ecosystem-banner';
      wrapper.parentNode.insertBefore(banner, wrapper);
    }

    var updated = fc.lastUpdated ? new Date(fc.lastUpdated).toLocaleString() : '\u2014';
    banner.innerHTML =
      '<span class="ecosystem-banner__live">LIVE DATA</span>' +
      '<span class="ecosystem-banner__stats">' + fundCentreSummaryStr(fc) + '</span>' +
      '<span class="ecosystem-banner__updated">Last updated: ' + updated + '</span>';
  }

  // ── Public API ──────────────────────────────────────────────────────

  return {
    currency: currency,
    pct: pct,
    date: date,
    bindAll: bindAll,
    bindFundTable: bindFundTable,
    bindFundBanner: bindFundBanner,
    buildKeyMap: buildKeyMap
  };

})();