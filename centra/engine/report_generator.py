"""
Centra Audit Report Generator
================================
Generates formal HTML audit reports per compliance framework.
Reports include scope, methodology, control-by-control evidence,
findings, and compliance determination.
"""
import json
import logging
from pathlib import Path
from datetime import datetime, timezone

logger = logging.getLogger('centra.reports')

REPORTS_DIR = Path('/home/alieninc/trust/reports')
FRAMEWORK_REPORTS_DIR = REPORTS_DIR / 'frameworks'


def generate_framework_reports(report_data: dict):
    """Generate individual HTML reports for each framework."""
    FRAMEWORK_REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = report_data.get('timestamp', datetime.now(timezone.utc).isoformat())
    scan_id = report_data.get('scan_id', 'unknown')
    overall_score = report_data.get('overall_score', 0)

    for fw_id, fw_data in report_data.get('frameworks', {}).items():
        html = _render_framework_report(
            fw_id=fw_id,
            fw_name=fw_data['name'],
            fw_score=fw_data['score'],
            fw_status=fw_data['status'],
            controls=fw_data['controls'],
            scan_id=scan_id,
            timestamp=timestamp,
            overall_score=overall_score,
            total_verified=report_data.get('total_controls_verified', 0),
            total_tested=report_data.get('total_controls_tested', 0),
        )

        output_path = FRAMEWORK_REPORTS_DIR / f'{fw_id}.html'
        output_path.write_text(html)
        logger.info(f'Framework report generated: {output_path}')


def _render_framework_report(
    fw_id: str,
    fw_name: str,
    fw_score: float,
    fw_status: str,
    controls: list,
    scan_id: str,
    timestamp: str,
    overall_score: float,
    total_verified: int,
    total_tested: int,
) -> str:
    """Render a single framework audit report as HTML."""
    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
    formatted_date = dt.strftime('%B %d, %Y at %H:%M UTC')

    verified_count = sum(1 for c in controls if c['status'] == 'verified')
    partial_count = sum(1 for c in controls if c['status'] == 'partial')
    not_verified_count = sum(1 for c in controls if c['status'] == 'not_verified')
    not_applicable_count = sum(1 for c in controls if c.get('notes', '').startswith('Not applicable'))

    status_color = '#10b981' if fw_status == 'compliant' else '#f59e0b' if fw_status == 'partial' else '#ef4444'
    status_label = fw_status.upper().replace('_', ' ')

    unique_plugins = set()
    for c in controls:
        unique_plugins.update(c.get('plugins', []))
    plugin_count = len(unique_plugins)

    controls_html = ''
    for c in controls:
        ctrl_status = c['status']
        badge_color = {
            'verified': '#10b981',
            'partial': '#f59e0b',
            'not_verified': '#ef4444',
            'not_testable': '#6b7280',
        }.get(ctrl_status, '#6b7280')

        evidence_html = ''
        if c.get('evidence'):
            evidence_items = ''.join(f'<li class="evidence-item">{e}</li>' for e in c['evidence'])
            evidence_html = f'<ul class="evidence-list">{evidence_items}</ul>'

        notes_html = ''
        if c.get('notes'):
            notes_html = f'<p class="control-notes">{c["notes"]}</p>'

        plugins_html = ', '.join(f'Plugin {p}' for p in c.get('plugins', []))

        controls_html += f'''
        <div class="control-card">
            <div class="control-header">
                <div class="control-id">{c["control_id"]}</div>
                <div class="control-name">{c["control_name"]}</div>
                <div class="control-badge" style="background:{badge_color}">{ctrl_status.replace("_", " ").upper()}</div>
            </div>
            <div class="control-plugins">{plugins_html}</div>
            {evidence_html}
            {notes_html}
        </div>'''

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{fw_name} — Centra Audit Report</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #f9fafb;
            color: #101828;
            line-height: 1.6;
        }}
        .report-header {{
            background: linear-gradient(135deg, #0a0e1c 0%, #16213e 100%);
            color: white;
            padding: 48px 40px;
        }}
        .report-header h1 {{
            font-size: 2rem;
            font-weight: 700;
            margin-bottom: 8px;
        }}
        .report-header .subtitle {{
            color: rgba(255,255,255,0.7);
            font-size: 0.95rem;
        }}
        .report-meta {{
            display: flex;
            gap: 32px;
            margin-top: 24px;
            flex-wrap: wrap;
        }}
        .meta-item {{
            display: flex;
            flex-direction: column;
        }}
        .meta-label {{
            font-size: 0.7rem;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: rgba(255,255,255,0.5);
        }}
        .meta-value {{
            font-size: 1.1rem;
            font-weight: 600;
        }}
        .score-banner {{
            background: white;
            border: 1px solid #eaecf0;
            border-radius: 12px;
            padding: 32px 40px;
            margin: -24px 40px 32px;
            display: flex;
            align-items: center;
            gap: 24px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.06);
            position: relative;
            z-index: 1;
        }}
        .score-number {{
            font-size: 3.5rem;
            font-weight: 800;
            color: {status_color};
            line-height: 1;
        }}
        .score-details {{
            flex: 1;
        }}
        .score-details .determination {{
            font-size: 1.2rem;
            font-weight: 700;
            color: {status_color};
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        .score-details .summary {{
            color: #666;
            font-size: 0.9rem;
            margin-top: 4px;
        }}
        .report-body {{
            max-width: 960px;
            margin: 0 auto;
            padding: 0 40px 48px;
        }}
        .section {{
            margin-bottom: 32px;
        }}
        .section h2 {{
            font-size: 1.1rem;
            font-weight: 700;
            color: #101828;
            margin-bottom: 12px;
            padding-bottom: 8px;
            border-bottom: 2px solid #eaecf0;
        }}
        .section p {{
            font-size: 0.9rem;
            color: #475467;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 16px;
            margin-bottom: 32px;
        }}
        .stat-card {{
            background: white;
            border: 1px solid #eaecf0;
            border-radius: 8px;
            padding: 16px;
            text-align: center;
        }}
        .stat-value {{
            font-size: 1.8rem;
            font-weight: 800;
        }}
        .stat-label {{
            font-size: 0.7rem;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: #666;
            margin-top: 4px;
        }}
        .control-card {{
            background: white;
            border: 1px solid #eaecf0;
            border-radius: 8px;
            padding: 16px 20px;
            margin-bottom: 12px;
        }}
        .control-header {{
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 8px;
        }}
        .control-id {{
            font-size: 0.8rem;
            font-weight: 700;
            color: #19256e;
            background: #f0f1ff;
            padding: 2px 8px;
            border-radius: 4px;
        }}
        .control-name {{
            font-size: 0.9rem;
            font-weight: 600;
            flex: 1;
        }}
        .control-badge {{
            font-size: 0.65rem;
            font-weight: 700;
            color: white;
            padding: 2px 8px;
            border-radius: 4px;
            letter-spacing: 0.5px;
        }}
        .control-plugins {{
            font-size: 0.75rem;
            color: #999;
            margin-bottom: 8px;
        }}
        .evidence-list {{
            list-style: none;
            padding: 0;
        }}
        .evidence-item {{
            font-size: 0.8rem;
            color: #475467;
            padding: 4px 0 4px 16px;
            position: relative;
        }}
        .evidence-item::before {{
            content: '>';
            position: absolute;
            left: 0;
            color: #10b981;
            font-weight: bold;
        }}
        .control-notes {{
            font-size: 0.8rem;
            color: #f59e0b;
            font-style: italic;
            margin-top: 4px;
        }}
        .report-footer {{
            text-align: center;
            padding: 32px;
            color: #999;
            font-size: 0.8rem;
            border-top: 1px solid #eaecf0;
        }}
        @media (max-width: 768px) {{
            .stats-grid {{ grid-template-columns: repeat(2, 1fr); }}
            .score-banner {{ flex-direction: column; text-align: center; margin: -24px 16px 32px; padding: 24px; }}
            .report-body {{ padding: 0 16px 32px; }}
        }}
    </style>
</head>
<body>
    <div class="report-header">
        <h1>{fw_name}</h1>
        <div class="subtitle">Centra Compliance Audit Report — Alien Inc</div>
        <div class="report-meta">
            <div class="meta-item">
                <span class="meta-label">Scan ID</span>
                <span class="meta-value">{scan_id}</span>
            </div>
            <div class="meta-item">
                <span class="meta-label">Report Date</span>
                <span class="meta-value">{formatted_date}</span>
            </div>
            <div class="meta-item">
                <span class="meta-label">Auditor</span>
                <span class="meta-value">Centra Automated Scanner</span>
            </div>
            <div class="meta-item">
                <span class="meta-label">Overall Score</span>
                <span class="meta-value">{overall_score}%</span>
            </div>
        </div>
    </div>

    <div class="score-banner">
        <div class="score-number">{fw_score}%</div>
        <div class="score-details">
            <div class="determination">{status_label}</div>
            <div class="summary">{verified_count} of {len(controls)} controls verified &middot; {total_verified}/{total_tested} total across all frameworks</div>
        </div>
    </div>

    <div class="report-body">
        <div class="section">
            <h2>Scope</h2>
            <p>This report covers the assessment of {fw_name} technical controls as implemented on the Alien Inc production infrastructure (Hetzner dedicated server, nginx/1.22.1, Python/3.11, Cloudflare CDN). The assessment was performed by Centra's automated compliance scanner using {plugin_count} security plugins across ports 443 (HTTPS) and 22 (SSH).</p>
        </div>

        <div class="section">
            <h2>Methodology</h2>
            <p>Centra's scanner performs remote, non-intrusive security assessments against live production endpoints. Each control is evaluated by one or more plugins that verify specific technical configurations: HTTP response headers, TLS/SSL parameters, bot detection mechanisms, session security, rate limiting, content integrity, and policy artifact presence. Evidence is captured from actual HTTP responses and archived with each scan.</p>
        </div>

        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value" style="color:#10b981">{verified_count}</div>
                <div class="stat-label">Verified</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" style="color:#f59e0b">{partial_count}</div>
                <div class="stat-label">Partial</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" style="color:#ef4444">{not_verified_count}</div>
                <div class="stat-label">Not Verified</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" style="color:#6b7280">{not_applicable_count}</div>
                <div class="stat-label">N/A</div>
            </div>
        </div>

        <div class="section">
            <h2>Controls Assessment</h2>
            {controls_html}
        </div>
    </div>

    <div class="report-footer">
        <p>Generated by Centra Compliance Scanner &middot; Alien Inc Security Division</p>
        <p>Scan ID: {scan_id} &middot; {formatted_date}</p>
    </div>
</body>
</html>'''
