
  const SESSION = (() => {
    try {
      const el = document.getElementById('session-data');
      return el ? JSON.parse(el.textContent || '{}') : {};
    } catch (_) { return {}; }
  })();
  const EMAIL = SESSION.email || '';
  const ROLE = (SESSION.role || 'employee').toLowerCase();
  const IS_STAFF = ROLE === 'security_staff';
  const IS_MANAGER = IS_STAFF || ROLE === 'manager';

  const supabaseClient = window.supabase.createClient(SESSION.supabaseUrl, SESSION.anonKey);
  if (SESSION.accessToken) {
    supabaseClient.auth.setSession({
      access_token: SESSION.accessToken,
      refresh_token: SESSION.refreshToken || '',
    });
  }

  const TABLES = {
    access: 'access_requests',
    travel: 'foreign_travel_reports',
    contact: 'foreign_contact_disclosures',
    incident: 'reportable_incidents',
    visit: 'visit_requests',
  };

  const $ = (id) => document.getElementById(id);
  const showToast = (msg, isError) => {
    const t = $('toast');
    t.textContent = msg;
    t.className = 'toast show' + (isError ? ' error' : '');
    clearTimeout(showToast._t);
    showToast._t = setTimeout(() => { t.className = 'toast'; }, 4000);
  };
  const alertBox = (type, msg) => {
    const host = $('alerts');
    const el = document.createElement('div');
    el.className = 'alert alert-' + type;
    el.textContent = msg;
    host.appendChild(el);
    setTimeout(() => el.remove(), 6000);
  };
  const esc = (s) => String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
  const statusClass = (s) => String(s || '').toLowerCase().replace(/\s+/g, '-');

  const NAV = {
    dashboard: 'My Record', reports: 'Direct Reports', access: 'Request Access',
    travel: 'Foreign Travel', contact: 'Foreign Contact', incident: 'Report Incident',
    visit: 'Visit Request', review: 'Security Review',
  };

  function currentView() {
    const p = new URLSearchParams(location.search);
    const v = p.get('view') || 'dashboard';
    if (v === 'review' && !IS_STAFF) return 'dashboard';
    if (v === 'reports' && !IS_MANAGER) return 'dashboard';
    return v;
  }
  function go(view) {
    history.replaceState(null, '', location.pathname + '?view=' + view);
    show(view);
  }
  function show(view) {
    document.querySelectorAll('[data-section]').forEach(s => s.classList.add('hidden'));
    const target = document.querySelector('[data-section="' + view + '"]');
    if (target) target.classList.remove('hidden');
    document.querySelectorAll('.nav-item').forEach(b => b.classList.toggle('active', b.dataset.view === view));
    const title = $('pageTitle');
    if (title) title.textContent = NAV[view] || '';
    load(view);
  }

  async function load(view) {
    if (view === 'dashboard') { renderDash(); }
    else if (view === 'reports') { renderReports(); }
    else if (view === 'review') { renderReview(); renderNotifyFeed(); }
  }

  async function fetchRows(table, opts) {
    let q = supabaseClient.from(table).select('*');
    if (opts && opts.order) q = q.order(opts.order, { ascending: false });
    const { data, error } = await q;
    if (error) throw new Error(error.message);
    return data || [];
  }

  async function fetchMyRecord() {
    const { data, error } = await supabaseClient
      .from('personnel_records')
      .select('*')
      .eq('user_email', EMAIL)
      .maybeSingle();
    if (error) throw new Error(error.message);
    return data || null;
  }

  // ── Dashboard ────────────────────────────────────────────
  async function renderDash() {
    const host = $('dashRecord');
    host.innerHTML = '<div class="loading"><span class="spin"></span>Loading record&hellip;</div>';
    let rec;
    try { rec = await fetchMyRecord(); } catch (e) { host.innerHTML = ''; alertBox('error', 'Failed to load record: ' + esc(e.message)); return; }

    if (!rec) {
      host.innerHTML = '<div class="card"><div class="empty"><div class="big">&#128274;</div>No personnel record found for your account yet.<br>Contact security staff if this is unexpected.</div></div>';
    } else {
      const parse = (v) => { try { const j = JSON.parse(v || '[]'); return Array.isArray(j) ? j : []; } catch { return []; } };
      const list = (arr) => arr.length ? '<ul style="margin-left:18px;font-size:13px;color:var(--text);">' + arr.map(a => '<li>' + esc(typeof a === 'string' ? a : JSON.stringify(a)) + '</li>').join('') + '</ul>' : '<span style="color:var(--text-dim)">None on file</span>';
      const chips = (arr) => arr.length ? '<div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:6px;">' + arr.map(a => '<span style="background:var(--bg-raised);border:1px solid var(--border);border-radius:999px;padding:3px 10px;font-size:12px;">' + esc(typeof a === 'string' ? a : JSON.stringify(a)) + '</span>').join('') + '</div>' : '<span style="color:var(--text-dim)">None on file</span>';

      const clearances = ['None', 'Secret', 'Top Secret', 'TS/SCI', 'TS/SCI-Poly'];
      const lvl = clearances.indexOf(rec.clearance_status);
      const badgeColor = lvl <= 0 ? 'var(--text-dim)' : lvl === 1 ? '#2563eb' : lvl === 2 ? '#f59e0b' : 'var(--danger)';

      host.innerHTML = '<div class="card">' +
        '<div class="card-title"><span class="dot"></span>' + esc(rec.employee_name || 'Personnel Record') + '</div>' +
        '<dl>' +
          '<div class="kv"><dt>Clearance Status</dt><dd><span style="color:' + badgeColor + ';font-weight:700;">' + esc(rec.clearance_status || 'None') + '</span></dd></div>' +
          '<div class="kv"><dt>Active Accesses</dt><dd class="mono">' + (parse(rec.active_accesses).length) + '</dd></div>' +
        '</dl>' +
        '<div style="margin-top:14px;">' + chips(parse(rec.active_accesses)) + '</div>' +
      '</div>' +
      '<div class="card"><div class="card-title"><span class="dot"></span> Foreign Travel History</div>' + list(parse(rec.foreign_travel_history)) + '</div>' +
      '<div class="card"><div class="card-title"><span class="dot"></span> Foreign Contacts on File</div>' + list(parse(rec.foreign_contacts)) + '</div>' +
      '<div class="card"><div class="card-title"><span class="dot"></span> Training Completions</div>' + list(parse(rec.training_completions)) + '</div>';
    }

    const subHost = $('dashSubmissions');
    subHost.innerHTML = '<div class="loading"><span class="spin"></span>Loading&hellip;</div>';
    try {
      const all = {};
      for (const [k, table] of Object.entries(TABLES)) {
        all[k] = await fetchRows(table, { order: 'submission_date' });
      }
      const rows = [];
      for (const [k, table] of Object.entries(TABLES)) {
        for (const r of all[k]) rows.push({ kind: k, label: NAV[k], id: (r.id || r[k + '_id']), row: r });
      }
      rows.sort((a, b) => String(b.row.submission_date).localeCompare(String(a.row.submission_date)));
      if (!rows.length) {
        subHost.innerHTML = '<div class="empty">No submissions yet.</div>';
      } else {
        subHost.innerHTML = '<div class="table-wrap"><table><thead><tr><th>Type</th><th>Details</th><th>Submitted</th><th>Status</th></tr></thead><tbody>' +
          rows.map(r => {
            const d = r.row;
            const detail = r.kind === 'access' ? esc(d.program_or_contract || '') :
              r.kind === 'travel' ? esc(d.destination_countries || '') :
              r.kind === 'contact' ? esc(d.contact_name || '') :
              r.kind === 'incident' ? esc(d.incident_type || '') :
              esc(d.visit_direction || '');
            return '<tr><td style="white-space:nowrap;font-weight:600;">' + esc(r.label) + '</td><td>' + detail + '</td><td style="white-space:nowrap;color:var(--text-muted);">' + esc((d.submission_date || '').slice(0, 10)) + '</td><td><span class="status ' + statusClass(d.status) + '">' + esc(d.status || 'Pending') + '</span></td></tr>';
          }).join('') + '</tbody></table></div>';
      }
    } catch (e) {
      subHost.innerHTML = '';
      alertBox('error', 'Failed to load submissions: ' + esc(e.message));
    }
  }

  // ── Direct Reports ───────────────────────────────────────
  async function renderReports() {
    const host = $('reportsList');
    host.innerHTML = '<div class="loading"><span class="spin"></span>Loading&hellip;</div>';
    try {
      const { data, error } = await supabaseClient
        .from('personnel_records')
        .select('*')
        .eq('manager_email', EMAIL);
      if (error) throw new Error(error.message);
      const rows = data || [];
      if (!rows.length) {
        host.innerHTML = '<div class="card"><div class="empty">No direct reports on file.</div></div>';
        return;
      }
      host.innerHTML = '<div class="card"><div class="table-wrap"><table><thead><tr><th>Employee</th><th>Clearance</th><th>Active Accesses</th><th>Training</th></tr></thead><tbody>' +
        rows.map(r => '<tr><td style="font-weight:600;">' + esc(r.employee_name || r.user_email) + '</td><td>' + esc(r.clearance_status || 'None') + '</td><td class="mono">' + (() => { try { return (JSON.parse(r.active_accesses || '[]') || []).length; } catch { return 0; } })() + '</td><td class="mono">' + (() => { try { return (JSON.parse(r.training_completions || '[]') || []).length; } catch { return 0; } })() + '</td></tr>').join('') +
        '</tbody></table></div></div>';
    } catch (e) {
      host.innerHTML = '';
      alertBox('error', 'Failed to load direct reports: ' + esc(e.message));
    }
  }

  // ── Security Review ──────────────────────────────────────
  async function renderNotifyFeed() {
    const host = $('notifyFeed');
    if (!host) return;
    try {
      const r = await fetch('/api/selfservice/notifications', { cache: 'no-store' });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const j = await r.json();
      const rows = (j.notifications || []).slice(0, 50);
      if (!rows.length) {
        host.innerHTML = '<div class="empty" style="padding:8px;">No notifications yet.</div>';
        return;
      }
      host.innerHTML = rows.map(n =>
        '<div style="padding:6px 0;border-bottom:1px solid var(--border);display:flex;gap:10px;justify-content:space-between;">' +
          '<div><span style="font-weight:600;">' + esc(n.kind || n.table) + '</span> &mdash; <span class="mono">' + esc(n.user_email || '') + '</span>' +
          (n.summary ? '<div style="color:var(--text-muted);white-space:pre-wrap;">' + esc(n.summary) + '</div>' : '') + '</div>' +
          '<div style="white-space:nowrap;color:var(--text-dim);font-size:11px;">' + esc((n.ts || '').replace('T', ' ').slice(0, 19)) + '</div>' +
        '</div>'
      ).join('');
    } catch (e) {
      host.innerHTML = '<div class="empty" style="padding:8px;">Failed to load feed: ' + esc(e.message) + '</div>';
    }
  }

  async function renderReview() {
    const host = $('reviewContainer');
    host.innerHTML = '<div class="loading"><span class="spin"></span>Loading submissions&hellip;</div>';
    try {
      const all = {};
      for (const [k, table] of Object.entries(TABLES)) all[k] = await fetchRows(table, { order: 'submission_date' });
      const rows = [];
      for (const [k, table] of Object.entries(TABLES)) {
        for (const r of all[k]) rows.push({ kind: k, label: NAV[k], row: r });
      }
      rows.sort((a, b) => String(a.row.submission_date).localeCompare(String(b.row.submission_date)));
      if (!rows.length) {
        host.innerHTML = '<div class="card"><div class="empty">No submissions in the queue.</div></div>';
        return;
      }
      host.innerHTML = rows.map(r => {
        const d = r.row;
        const detail = (() => {
          switch (r.kind) {
            case 'access': return '<dt>Program/Contract</dt><dd>' + esc(d.program_or_contract) + '</dd><dt>Justification</dt><dd>' + esc(d.justification) + '</dd>';
            case 'travel': return '<dt>Countries</dt><dd>' + esc(d.destination_countries) + '</dd><dt>Dates</dt><dd>' + esc((d.departure_date || '').slice(0,10)) + ' &rarr; ' + esc((d.return_date || '').slice(0,10)) + '</dd>';
            case 'contact': return '<dt>Contact</dt><dd>' + esc(d.contact_name) + '</dd><dt>Relationship</dt><dd>' + esc(d.relationship_type) + '</dd>';
            case 'incident': return '<dt>Type</dt><dd>' + esc(d.incident_type) + '</dd><dt>Occurred</dt><dd>' + esc((d.date_occurred || '').slice(0,10)) + '</dd>';
            case 'visit': return '<dt>Direction</dt><dd>' + esc(d.visit_direction) + '</dd><dt>Org</dt><dd>' + esc(d.host_organization) + '</dd>';
          }
        })();
        const notes = d.approval_notes ? '<dt>Approval Notes</dt><dd>' + esc(d.approval_notes) + '</dd>' : '';
        const act = (d.status || 'Pending').toLowerCase() === 'pending'
          ? '<div style="display:flex;gap:8px;margin-top:10px;">' +
              '<button class="btn btn-sm btn-success" data-review="' + r.kind + '" data-id="' + esc(d.id) + '" data-action="approved">Approve</button>' +
              '<button class="btn btn-sm btn-danger" data-review="' + r.kind + '" data-id="' + esc(d.id) + '" data-action="rejected">Reject</button>' +
            '</div>'
          : '';
        return '<div class="card">' +
          '<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">' +
            '<div class="card-title" style="margin:0;"><span class="dot"></span>' + esc(r.label) + ' &mdash; ' + esc(d.user_email || '') + '</div>' +
            '<span class="status ' + statusClass(d.status) + '">' + esc(d.status || 'Pending') + '</span>' +
          '</div>' +
          '<dl style="margin-top:12px;">' + detail + notes + '</dl>' + act +
        '</div>';
      }).join('');
      host.querySelectorAll('[data-review]').forEach(btn => {
        btn.addEventListener('click', async () => {
          const table = TABLES[btn.dataset.review];
          const id = btn.dataset.id;
          const action = btn.dataset.action;
          const { error } = await supabaseClient
            .from(table).update({
              status: action,
              approval_notes: 'Reviewed by ' + EMAIL + ' on ' + new Date().toISOString(),
              updated_by: EMAIL,
              updated_at: new Date().toISOString(),
              reviewed_by: EMAIL,
              reviewed_at: new Date().toISOString(),
            })
            .eq('id', id);
          if (error) { showToast('Review failed: ' + error.message, true); return; }
          showToast('Submission ' + action + '.');
          renderReview();
          renderNotifyFeed();
        });
      });
    } catch (e) {
      host.innerHTML = '';
      alertBox('error', 'Failed to load review queue: ' + esc(e.message));
    }
  }

  // ── Form submission ──────────────────────────────────────
  const FORM_DEFS = {
    access: {
      table: 'access_requests',
      fields: { 'f-access-prog': 'program_or_contract', 'f-access-just': 'justification' },
      required: ['f-access-prog', 'f-access-just'],
    },
    travel: {
      table: 'foreign_travel_reports',
      fields: {
        'f-travel-dest': 'destination_countries', 'f-travel-purpose': 'travel_purpose',
        'f-travel-dep': 'departure_date', 'f-travel-ret': 'return_date',
        'f-travel-pre': 'sead3_pretravel', 'f-travel-post': 'sead3_posttravel',
      },
      required: ['f-travel-dest', 'f-travel-dep', 'f-travel-ret'],
    },
    contact: {
      table: 'foreign_contact_disclosures',
      fields: {
        'f-contact-name': 'contact_name', 'f-contact-rel': 'relationship_type',
        'f-contact-cit': 'contact_citizenship', 'f-contact-notes': 'psq_form_data',
      },
      required: ['f-contact-name', 'f-contact-rel'],
    },
    incident: {
      table: 'reportable_incidents',
      fields: { 'f-incident-type': 'incident_type', 'f-incident-date': 'date_occurred', 'f-incident-desc': 'incident_description' },
      required: ['f-incident-type', 'f-incident-date', 'f-incident-desc'],
    },
    visit: {
      table: 'visit_requests',
      fields: { 'f-visit-dir': 'visit_direction', 'f-visit-host': 'host_organization', 'f-visit-date': 'visit_date', 'f-visit-group': 'group_visitors' },
      required: ['f-visit-dir', 'f-visit-date'],
    },
  };

  async function submitForm(kind) {
    const def = FORM_DEFS[kind];
    const missing = def.required.filter(id => !$(id).value.trim());
    if (missing.length) { showToast('Please fill in all required fields.', true); return; }
    const row = {
      user_email: EMAIL,
      submission_date: new Date().toISOString(),
      status: 'Pending',
    };
    for (const [id, col] of Object.entries(def.fields)) {
      let v = $(id).value.trim();
      if (id === 'f-visit-group' && v) {
        try { v = JSON.parse(v); } catch { showToast('Group Visitor List must be valid JSON.', true); return; }
      }
      if (v !== '') row[col] = v;
    }
    const { data: inserted, error } = await supabaseClient.from(def.table).insert([row]).select('id');
    if (error) { showToast('Submission failed: ' + error.message, true); return; }
    try {
      const summaryParts = [];
      if (row.program_or_contract) summaryParts.push('Program/Contract: ' + row.program_or_contract);
      if (row.destination_countries) summaryParts.push('Countries: ' + row.destination_countries);
      if (row.contact_name) summaryParts.push('Contact: ' + row.contact_name);
      if (row.incident_type) summaryParts.push('Type: ' + row.incident_type);
      if (row.visit_direction) summaryParts.push('Direction: ' + row.visit_direction);
      await fetch('/api/selfservice/notify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          table: def.table,
          kind: kind,
          id: (inserted && inserted[0] && inserted[0].id) || '',
          summary: summaryParts.join('\n'),
        }),
      });
    } catch (_) { /* notification is best-effort */ }
    Object.values(def.fields).forEach((col, i) => {
      const id = Object.keys(def.fields)[i];
      const el = $(id);
      if (el && el.tagName === 'SELECT') el.selectedIndex = 0;
      if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA')) el.value = '';
    });
    showToast('Submission received. Status: Pending review.');
    go('dashboard');
  }

  // ── Wire up ──────────────────────────────────────────────
  function init() {
    $('userEmail').textContent = EMAIL || 'unknown';
    $('userRole').textContent = ROLE;
    $('userAvatar').textContent = (EMAIL || '?').charAt(0).toUpperCase();
    if (IS_STAFF) document.querySelectorAll('.js-staff-only').forEach(el => el.classList.remove('hidden'));
    if (IS_MANAGER) document.querySelectorAll('.js-manager').forEach(el => el.classList.remove('hidden'));
    document.querySelectorAll('.nav-item').forEach(btn => btn.addEventListener('click', () => go(btn.dataset.view)));
    document.querySelectorAll('[data-quick]').forEach(a => a.addEventListener('click', (e) => { e.preventDefault(); go(a.dataset.quick); }));
    document.querySelectorAll('[data-cancel]').forEach(btn => btn.addEventListener('click', () => go('dashboard')));
    document.querySelectorAll('[data-submit]').forEach(btn => btn.addEventListener('click', async () => {
      btn.disabled = true;
      try { await submitForm(btn.dataset.submit); } finally { btn.disabled = false; }
    }));
    $('logoutBtn').addEventListener('click', async () => {
      try { await supabaseClient.auth.signOut(); } catch (_) {}
      location.href = '/';
    });
    show(currentView());
  }

  if (!EMAIL) {
    $('userEmail').textContent = 'Not signed in';
    $('userRole').textContent = 'Redirecting&hellip;';
    location.href = '/';
  } else {
    init();
  }
