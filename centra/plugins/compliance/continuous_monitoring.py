"""
Plugin 1049: Continuous Monitoring — Configuration Drift Detection
=====================================================================
Type: summary — compares current scan results against previous KB
entries to detect configuration drift across scan cycles.
"""
from plugins import NaslPlugin, PluginResult, ScanContext


class ContinuousMonitoring(NaslPlugin):
    PLUGIN_ID = 1049
    NAME = 'Continuous Monitoring — Configuration Drift Detection'
    FAMILY = 'Compliance & Audit'
    PLUGIN_TYPE = 'summary'
    CVSS_SCORE = 0.0
    DESCRIPTION = (
        'Detects configuration drift and recurring vulnerabilities across '
        'scan cycles. Continuous monitoring compares current findings against '
        'baseline scans to identify new exposures and unresolved issues.'
    )
    SOLUTION = (
        'Implement automated remediation for recurring findings. Use '
        'Infrastructure-as-Code (IaC) to enforce known-good configurations. '
        'Establish a patch management SLA. Review new findings as they appear.'
    )

    async def check_target(self, target: str, port: int | None = None,
                           scan_context: ScanContext | None = None) -> list[PluginResult]:
        if scan_context is None:
            return [PluginResult(vulnerable=False, target=target, severity='info',
                                 description='Drift detection requires scan context')]

        all_results = scan_context.get_all_results()
        previous_findings = scan_context.get_kb_item('Host/previous-findings')

        new_vulns = 0
        recurring_vulns = 0
        resolved_vulns = 0
        total_current_vulns = 0
        details = []

        for pid, results in all_results.items():
            for r in results:
                if r.vulnerable:
                    total_current_vulns += 1
                    finding_key = f'P{pid}:{r.target}:{r.port}'
                    plugin = scan_context.get_kb_item(f'Host/plugin-name-{pid}') or str(pid)

                    if previous_findings and isinstance(previous_findings, dict):
                        if finding_key in previous_findings:
                            recurring_vulns += 1
                        else:
                            new_vulns += 1
                            details.append(f'  NEW: {plugin} on {r.target}:{r.port} — {r.description[:80]}')
                    else:
                        new_vulns += 1
                        details.append(f'  NEW (baseline): {plugin} on {r.target}:{r.port}')

        if previous_findings and isinstance(previous_findings, dict):
            for key in previous_findings:
                still_present = False
                for pid, results in all_results.items():
                    for r in results:
                        if r.vulnerable and f'P{pid}:{r.target}:{r.port}' == key:
                            still_present = True
                            break
                if not still_present:
                    resolved_vulns += 1
                    details.append(f'  RESOLVED: {previous_findings[key]}')

        change_count = new_vulns + resolved_vulns
        status = 'drift_detected' if change_count > 0 else 'stable'

        severity = 'info'
        cvss = 0.0
        if new_vulns > 3:
            severity = 'high'
            cvss = 7.0
        elif new_vulns > 0:
            severity = 'medium'
            cvss = 4.0

        return [PluginResult(
            vulnerable=new_vulns > 0,
            target=target,
            cvss_score=cvss,
            severity=severity,
            description=f'Continuous monitoring: {new_vulns} new, {recurring_vulns} recurring, '
                        f'{resolved_vulns} resolved, {total_current_vulns} total ({status})',
            evidence=' | '.join(details[:10]) if details else 'No drift detected',
            references=[
                'https://www.tenable.com/plugins/nessus/141561',
            ]
        )]
