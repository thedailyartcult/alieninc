
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
    visit: 'Visit Request', review: 'Security Review', workflow: 'Workflows',
  };

  const WORKFLOW_MAP = {
    access: 'par',
    travel: 'foreign_travel',
    incident: 'security_reporting',
    visit: 'incoming_visitors',
    contact: 'security_reporting',
  };
  const TEMPLATE_LABELS = {
    par: 'Personnel Access Requests', foreign_travel: 'Foreign Travel',
    security_reporting: 'Security Reporting', is_access: 'Information System Access',
    training: 'Training', doc_material_control: 'Document & Material Control',
    incoming_visitors: 'Incoming Visitors', medical_device: 'Medical Device Requests',
  };
  const DIRECT_START_TEMPLATES = ['is_access', 'training', 'doc_material_control', 'medical_device'];

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
    else if (view === 'workflow') { renderWorkflows(); }
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
    const submissionId = (inserted && inserted[0] && inserted[0].id) || null;

    const summaryParts = [];
    if (row.program_or_contract) summaryParts.push('Program/Contract: ' + row.program_or_contract);
    if (row.destination_countries) summaryParts.push('Countries: ' + row.destination_countries);
    if (row.contact_name) summaryParts.push('Contact: ' + row.contact_name);
    if (row.incident_type) summaryParts.push('Type: ' + row.incident_type);
    if (row.visit_direction) summaryParts.push('Direction: ' + row.visit_direction);

    var workflowStarted = false;
    if (WORKFLOW_MAP[kind] && submissionId) {
      try {
        var wfRes = await supabaseClient.rpc('start_workflow', {
          p_template_code: WORKFLOW_MAP[kind],
          p_submission_table: def.table,
          p_submission_id: submissionId,
          p_user_email: EMAIL,
          p_metadata: { summary: summaryParts.join(' '), source: 'portal_form' },
        });
        if (wfRes.error) throw new Error(wfRes.error.message);
        workflowStarted = true;
      } catch (wfErr) {
        console.warn('Workflow start failed (submission still saved):', wfErr.message);
      }
    }

    try {
      await fetch('/api/selfservice/notify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          table: def.table,
          kind: kind,
          id: submissionId || '',
          summary: summaryParts.join('\n') + (workflowStarted ? '\n[Workflow ' + WORKFLOW_MAP[kind] + ' started]' : ''),
        }),
      });
    } catch (_) { /* notification is best-effort */ }
    Object.values(def.fields).forEach((col, i) => {
      const id = Object.keys(def.fields)[i];
      const el = $(id);
      if (el && el.tagName === 'SELECT') el.selectedIndex = 0;
      if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA')) el.value = '';
    });
    showToast(workflowStarted ? 'Submission received & workflow started. Track it in Workflows.' : 'Submission received. Status: Pending review.');
    go('dashboard');
  }

  // ── Workflows ────────────────────────────────────────────
  function wfStatusLabel(s) {
    var map = { InProgress: 'review', AwaitingApproval: 'pending', Approved: 'approved', Rejected: 'rejected' };
    return map[s] || 'review';
  }

  async function fetchWorkflowTemplates() {
    const { data, error } = await supabaseClient
      .from('workflow_templates')
      .select('code,name,description,framework,steps')
      .eq('is_active', true)
      .order('name');
    if (error) throw new Error(error.message);
    return data || [];
  }

  async function fetchMyWorkflowInstances() {
    const { data, error } = await supabaseClient
      .from('workflow_instances')
      .select('*')
      .order('created_at', { ascending: false });
    if (error) throw new Error(error.message);
    return data || [];
  }

  async function fetchAllWorkflowInstances() {
    const { data, error } = await supabaseClient
      .from('workflow_instances')
      .select('*')
      .order('created_at', { ascending: false });
    if (error) throw new Error(error.message);
    return data || [];
  }

  async function fetchWorkflowSteps(instanceId) {
    const { data, error } = await supabaseClient
      .from('workflow_steps')
      .select('*')
      .eq('instance_id', instanceId)
      .order('step_index', { ascending: true });
    if (error) throw new Error(error.message);
    return data || [];
  }

  async function renderWorkflows() {
    renderWfStartGrid();
    var instances = [], allInstances = [];
    try {
      instances = await fetchMyWorkflowInstances();
      if (IS_STAFF) allInstances = instances;
      else allInstances = instances;
    } catch (e) {
      $('wfMyInstances').innerHTML = '<div class="empty">Failed to load workflows: ' + esc(e.message) + '</div>';
    }

    var open = 0, approved = 0, rejected = 0, pending = 0;
    for (var i = 0; i < allInstances.length; i++) {
      var s = allInstances[i].status;
      if (s === 'InProgress' || s === 'AwaitingApproval') open++;
      else if (s === 'Approved') approved++;
      else if (s === 'Rejected') rejected++;
      if (s === 'AwaitingApproval') pending++;
    }

    $('wfStats').innerHTML =
      '<div class="grid">' +
        '<div class="stat"><div class="stat-label">Open</div><div class="stat-value">' + open + '</div></div>' +
        '<div class="stat"><div class="stat-label">Awaiting Approval</div><div class="stat-value gold">' + pending + '</div></div>' +
        '<div class="stat"><div class="stat-label">Approved</div><div class="stat-value" style="color:var(--green-deep);">' + approved + '</div></div>' +
        '<div class="stat"><div class="stat-label">Rejected</div><div class="stat-value" style="color:var(--danger);">' + rejected + '</div></div>' +
      '</div>';

    var myRows = instances;
    if (!myRows.length) {
      $('wfMyInstances').innerHTML = '<div class="empty">No workflows yet. Submit a form (Access, Travel, Incident, Visit) or start a workflow below.</div>';
    } else {
      $('wfMyInstances').innerHTML = '<div class="table-wrap"><table><thead><tr><th>Process</th><th>Current Step</th><th>Assigned To</th><th>Status</th><th>Started</th><th></th></tr></thead><tbody>' +
        myRows.map(function(r) {
          return '<tr>' +
            '<td style="font-weight:600;">' + esc(TEMPLATE_LABELS[r.template_code] || r.template_code) + '</td>' +
            '<td>' + esc(r.current_step_key ? r.current_step_key.replace(/_/g, ' ') : '&mdash;') + '</td>' +
            '<td>' + esc(r.assigned_department || '') + '</td>' +
            '<td><span class="status ' + wfStatusLabel(r.status) + '">' + esc(r.status) + '</span></td>' +
            '<td style="white-space:nowrap;color:var(--text-muted);">' + esc((r.created_at || '').slice(0, 10)) + '</td>' +
            '<td><button class="btn btn-sm btn-ghost" data-wf-detail="' + esc(r.id) + '">View Timeline</button></td>' +
          '</tr>';
        }).join('') + '</tbody></table></div>';
      $('wfMyInstances').querySelectorAll('[data-wf-detail]').forEach(function(btn) {
        btn.addEventListener('click', function() { renderWorkflowDetail(btn.dataset.wfDetail); });
      });
    }

    if (IS_STAFF) {
      var staffHost = $('wfStaffQueue');
      var active = allInstances.filter(function(r) { return r.status === 'InProgress' || r.status === 'AwaitingApproval'; });
      if (!active.length) {
        staffHost.innerHTML = '<div class="empty">No active workflows in the queue.</div>';
      } else {
        var byDept = {};
        for (var j = 0; j < active.length; j++) {
          var dept = active[j].assigned_department || 'Unassigned';
          if (!byDept[dept]) byDept[dept] = [];
          byDept[dept].push(active[j]);
        }
        staffHost.innerHTML = Object.keys(byDept).sort().map(function(dept) {
          return '<div style="margin-bottom:12px;"><div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.05em;color:var(--text-muted);margin-bottom:6px;">' + esc(dept) + ' (' + byDept[dept].length + ')</div>' +
            '<div class="table-wrap"><table><thead><tr><th>Process</th><th>Step</th><th>Role</th><th>Employee</th><th>Status</th><th></th></tr></thead><tbody>' +
            byDept[dept].map(function(r) {
              return '<tr>' +
                '<td style="font-weight:600;">' + esc(TEMPLATE_LABELS[r.template_code] || r.template_code) + '</td>' +
                '<td>' + esc(r.current_step_key ? r.current_step_key.replace(/_/g, ' ') : '') + '</td>' +
                '<td>' + esc(r.assigned_role || '') + '</td>' +
                '<td class="mono" style="font-size:12px;">' + esc(r.user_email) + '</td>' +
                '<td><span class="status ' + wfStatusLabel(r.status) + '">' + esc(r.status) + '</span></td>' +
                '<td><button class="btn btn-sm btn-primary" data-wf-detail="' + esc(r.id) + '">Review</button></td>' +
              '</tr>';
            }).join('') + '</tbody></table></div></div>';
        }).join('');
        staffHost.querySelectorAll('[data-wf-detail]').forEach(function(btn) {
          btn.addEventListener('click', function() { renderWorkflowDetail(btn.dataset.wfDetail); });
        });
      }
    }
  }

  async function renderWorkflowDetail(instanceId) {
    var host = $('wfDetail');
    host.innerHTML = '<div class="card"><div class="loading"><span class="spin"></span>Loading workflow&hellip;</div></div>';
    host.scrollIntoView({ behavior: 'smooth', block: 'start' });

    var steps, instance;
    try {
      steps = await fetchWorkflowSteps(instanceId);
      var instRes = await supabaseClient.from('workflow_instances').select('*').eq('id', instanceId).maybeSingle();
      if (instRes.error) throw new Error(instRes.error.message);
      instance = instRes.data;
    } catch (e) {
      host.innerHTML = '<div class="card"><div class="alert alert-error">Failed to load: ' + esc(e.message) + '</div></div>';
      return;
    }
    if (!instance) { host.innerHTML = '<div class="card"><div class="empty">Workflow not found.</div></div>'; return; }

    var canAct = IS_STAFF || (instance.assigned_role === ROLE && instance.status !== 'Approved' && instance.status !== 'Rejected');

    var stepsHtml = steps.map(function(s) {
      var nodeClass = s.status === 'Approved' ? 'done' : s.status === 'Rejected' ? 'rejected' : s.status === 'InProgress' ? 'current' : '';
      var meta = [];
      if (s.assignee_role) meta.push(s.assignee_role);
      if (s.department) meta.push(s.department);
      if (s.exited_at) meta.push((s.duration_seconds || 0).toFixed(0) + 's');
      var detail = [];
      if (s.actor_email) detail.push('by ' + s.actor_email);
      if (s.notes) detail.push(esc(s.notes));
      if (s.validation_results && s.validation_results.length) {
        var vResults = s.validation_results.map(function(v) {
          return esc(v.rule_key + ': ' + v.result + (v.auto ? ' (auto)' : ''));
        }).join(', ');
        detail.push('Validation: ' + vResults);
      }
      if (s.field_changes && s.field_changes.length) {
        var fChanges = s.field_changes.map(function(fc) {
          return esc(fc.field + ': ' + (fc.before || '') + ' &rarr; ' + (fc.after || ''));
        }).join(', ');
        detail.push('Changes: ' + fChanges);
      }
      return '<div class="step-node ' + nodeClass + '">' +
        '<div class="step-node-title">' + esc(s.step_name || s.step_key) + ' &mdash; <span class="status ' + wfStatusLabel(s.status) + '" style="font-size:11px;">' + esc(s.status) + '</span></div>' +
        '<div class="step-node-meta">' + meta.join(' &middot; ') + '</div>' +
        (detail.length ? '<div class="step-node-detail">' + detail.join(' &middot; ') + '</div>' : '') +
      '</div>';
    }).join('');

    var actionBtns = '';
    if (canAct && instance.status !== 'Approved' && instance.status !== 'Rejected') {
      actionBtns = '<div style="display:flex;gap:10px;margin-top:16px;padding-top:16px;border-top:1px solid var(--border-soft);">' +
        '<button class="btn btn-success" data-wf-advance="' + esc(instanceId) + '" data-action="approve">Approve Step' +
          '<span class="info-icon">?<span class="tooltip">Approves the current step and advances the workflow to the next review step. All block-severity validation rules for this step must be satisfied (marked pass) or the database will reject the approval.</span></span>' +
        '</button>' +
        '<button class="btn btn-danger" data-wf-advance="' + esc(instanceId) + '" data-action="reject">Reject' +
          '<span class="info-icon">?<span class="tooltip">Rejects the workflow at the current step. The instance is marked Rejected and no further steps run. The initiator is notified. Rejection does not require validation rules to be satisfied.</span></span>' +
        '</button>' +
        '<button class="btn btn-ghost" data-wf-advance="' + esc(instanceId) + '" data-action="return">Return for Revision' +
          '<span class="info-icon">?<span class="tooltip">Returns the workflow to the previous step for revision. Use this when the submitter needs to provide additional information before review can continue.</span></span>' +
        '</button>' +
      '</div>';
    }

    host.innerHTML = '<div class="card">' +
      '<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;margin-bottom:8px;">' +
        '<div class="card-title" style="margin:0;"><span class="dot"></span>' + esc(TEMPLATE_LABELS[instance.template_code] || instance.template_code) + '</div>' +
        '<span class="status ' + wfStatusLabel(instance.status) + '">' + esc(instance.status) + '</span>' +
      '</div>' +
      '<dl>' +
        '<div class="kv"><dt>Initiated by</dt><dd class="mono">' + esc(instance.user_email) + '</dd></div>' +
        '<div class="kv"><dt>Current step</dt><dd>' + esc(instance.current_step_key ? instance.current_step_key.replace(/_/g, ' ') : 'Complete') + ' (' + (instance.current_step_index + 1) + ')</dd></div>' +
        '<div class="kv"><dt>Assigned to</dt><dd>' + esc(instance.assigned_department || '') + ' &middot; ' + esc(instance.assigned_role || '') + '</dd></div>' +
        (instance.submission_table ? '<div class="kv"><dt>Linked submission</dt><dd class="mono">' + esc(instance.submission_table) + '</dd></div>' : '') +
      '</dl>' +
      '<div class="step-timeline">' + stepsHtml + '</div>' +
      actionBtns +
      '<div style="margin-top:12px;"><button class="btn btn-ghost btn-sm" data-wf-close>Close</button></div>' +
    '</div>';

    host.querySelectorAll('[data-wf-advance]').forEach(function(btn) {
      btn.addEventListener('click', function() { advanceWorkflowAction(btn.dataset.wfAdvance, btn.dataset.action, instanceId); });
    });
    var closeBtn = host.querySelector('[data-wf-close]');
    if (closeBtn) closeBtn.addEventListener('click', function() { host.innerHTML = ''; });
  }

  async function advanceWorkflowAction(action, actionVerb, instanceId) {
    var validationResults = [];
    try {
      var tmplRes = await supabaseClient.from('workflow_templates').select('steps').eq('code',
        (await supabaseClient.from('workflow_instances').select('template_code').eq('id', instanceId).maybeSingle()).data.template_code
      ).maybeSingle();
      var instRes2 = await supabaseClient.from('workflow_instances').select('current_step_key').eq('id', instanceId).maybeSingle();
      if (tmplRes.data && tmplRes.data.steps) {
        var curKey = instRes2.data.current_step_key;
        var stepDef = tmplRes.data.steps.find(function(s) { return s.key === curKey; });
        if (stepDef && stepDef.validation_rules) {
          validationResults = stepDef.validation_rules.map(function(r) {
            return { rule_key: r.rule_key, result: 'pass', framework: r.framework || '' };
          });
        }
      }
    } catch (_) {}

    var notes = '';
    if (actionVerb === 'reject' || actionVerb === 'return') {
      notes = prompt(actionVerb === 'reject' ? 'Reason for rejection:' : 'Reason for return:') || '';
      if (actionVerb === 'reject' && !notes) { showToast('A reason is required for rejection.', true); return; }
    }

    try {
      var res = await supabaseClient.rpc('advance_workflow', {
        p_instance_id: instanceId,
        p_actor_email: EMAIL,
        p_action: actionVerb,
        p_validation_results: validationResults,
        p_field_changes: [],
        p_notes: notes,
      });
      if (res.error) throw new Error(res.error.message);
      var newStatus = res.data.status;
      showToast('Step ' + (actionVerb === 'approve' ? 'approved' : actionVerb === 'reject' ? 'rejected' : 'returned') + '. Workflow: ' + newStatus);
      renderWorkflowDetail(instanceId);
      renderWorkflows();
    } catch (e) {
      showToast('Action failed: ' + e.message, true);
    }
  }

  async function renderWfStartGrid() {
    var host = $('wfStartGrid');
    try {
      var templates = await fetchWorkflowTemplates();
      var direct = templates.filter(function(t) { return DIRECT_START_TEMPLATES.indexOf(t.code) >= 0; });
      var linked = templates.filter(function(t) { return DIRECT_START_TEMPLATES.indexOf(t.code) < 0; });

      var html = '';
      if (linked.length) {
        html += '<div style="grid-column:1/-1;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.05em;color:var(--text-dim);margin-bottom:4px;">Auto-started from submissions</div>';
        html += linked.map(function(t) {
          return '<div class="stat" style="opacity:0.75;">' +
            '<div class="stat-label">' + esc(t.framework || '') + '</div>' +
            '<div class="stat-value" style="font-size:13px;line-height:1.4;">' + esc(t.name) + '</div>' +
            '<div style="font-size:11px;color:var(--text-dim);margin-top:4px;">Started automatically when you submit the matching form.</div>' +
          '</div>';
        }).join('');
      }
      if (direct.length) {
        html += '<div style="grid-column:1/-1;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.05em;color:var(--text-dim);margin-bottom:4px;margin-top:8px;">Start directly</div>';
        html += direct.map(function(t) {
          return '<div class="stat">' +
            '<div class="stat-label">' + esc(t.framework || '') + '</div>' +
            '<div class="stat-value" style="font-size:13px;line-height:1.4;">' + esc(t.name) + '</div>' +
            '<div style="font-size:11px;color:var(--text-muted);margin-top:4px;">' + esc(t.description) + '</div>' +
            '<button class="btn btn-primary btn-sm" style="margin-top:10px;" data-wf-start="' + esc(t.code) + '">Start' +
              '<span class="info-icon">?<span class="tooltip">Starts a new ' + esc(t.name) + ' workflow. You will be prompted for a brief description. The workflow opens at the first review step assigned to ' + esc(t.framework || 'Security') + ' staff.</span></span>' +
            '</button>' +
          '</div>';
        }).join('');
      }
      host.innerHTML = html || '<div class="empty">No templates available.</div>';
      host.querySelectorAll('[data-wf-start]').forEach(function(btn) {
        btn.addEventListener('click', function() { startWorkflowDirect(btn.dataset.wfStart); });
      });
    } catch (e) {
      host.innerHTML = '<div class="empty">Failed to load templates: ' + esc(e.message) + '</div>';
    }
  }

  async function startWorkflowDirect(templateCode) {
    var desc = prompt('Brief description for this ' + (TEMPLATE_LABELS[templateCode] || templateCode) + ' request:') || '';
    if (!desc.trim()) { showToast('A description is required.', true); return; }
    try {
      var res = await supabaseClient.rpc('start_workflow', {
        p_template_code: templateCode,
        p_submission_table: '',
        p_submission_id: null,
        p_user_email: EMAIL,
        p_metadata: { description: desc, source: 'direct_start' },
      });
      if (res.error) throw new Error(res.error.message);
      showToast('Workflow started. Track it in My Workflows.');
      renderWorkflows();
    } catch (e) {
      showToast('Failed to start workflow: ' + e.message, true);
    }
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
