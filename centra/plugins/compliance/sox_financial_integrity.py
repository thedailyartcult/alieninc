"""
Plugin 1050: SOX Financial Data Integrity Audit
==================================================
Type: summary — aggregates findings and maps them to SOX
financial reporting controls (Sections 302, 404, 409, 802).
"""
from plugins import NaslPlugin, PluginResult, ScanContext


class SoxFinancialIntegrity(NaslPlugin):
    PLUGIN_ID = 1050
    NAME = 'SOX Financial Data Integrity Audit'
    FAMILY = 'Compliance & Audit'
    PLUGIN_TYPE = 'summary'
    CVSS_SCORE = 0.0
    DESCRIPTION = (
        'Audits financial data integrity controls mapped to SOX requirements. '
        'Validates that systems processing financial data have appropriate '
        'access controls, change management, audit trails, and data protection.'
    )
    SOLUTION = (
        'Remediate failing controls to ensure financial data integrity. '
        'Maintain audit trails for all financial data modifications. '
        'Implement segregation of duties. Review access controls quarterly.'
    )

    SOX_MAPPING = {
        '302': ('Corporate Responsibility — Data Integrity',
                'Financial data must be accurate and complete',
                [1004, 1010, 1041]),
        '404': ('Internal Control Assessment',
                'Management must assess internal controls over financial reporting',
                [1003, 1004, 1009, 1027, 1037, 1038, 1039, 1045, 1046]),
        '409': ('Real-Time Disclosure',
                'Material changes in financial condition must be disclosed promptly',
                [1010, 1024, 1014]),
        '802': ('Document Alteration Prevention',
                'Records must be protected against alteration or destruction',
                [1004, 1029, 1038, 1045]),
    }

    async def check_target(self, target: str, port: int | None = None,
                           scan_context: ScanContext | None = None) -> list[PluginResult]:
        if scan_context is None:
            return [PluginResult(vulnerable=False, target=target, severity='info',
                                 description='SOX audit requires scan context')]

        all_results = scan_context.get_all_results()
        plugin_vulns = {}
        for pid, results in all_results.items():
            for r in results:
                if r.vulnerable:
                    plugin_vulns[pid] = r

        passed = 0
        failed = 0
        not_tested = 0
        details = []

        for section, (name, desc, plugin_ids) in self.SOX_MAPPING.items():
            section_failed = any(pid in plugin_vulns for pid in plugin_ids)
            section_tested = any(pid in all_results for pid in plugin_ids)

            if not section_tested:
                not_tested += 1
                details.append(f'  §{section} ({name}): NOT TESTED')
            elif section_failed:
                failed += 1
                failing = [str(pid) for pid in plugin_ids if pid in plugin_vulns]
                details.append(f'  §{section} ({name}): FAIL (P{", P".join(failing)})')
            else:
                passed += 1
                details.append(f'  §{section} ({name}): PASS')

        score = round(passed / len(self.SOX_MAPPING) * 100, 1) if self.SOX_MAPPING else 0
        status = 'compliant' if score >= 90 else 'partial' if score >= 60 else 'non_compliant'

        return [PluginResult(
            vulnerable=failed > 0,
            target=target,
            cvss_score=0.0,
            severity='high' if failed > 0 else 'info',
            description=f'SOX compliance: {passed}/{len(self.SOX_MAPPING)} sections passed — {score}% ({status})',
            evidence='\n'.join(details),
            references=[
                'https://www.tenable.com/plugins/nessus/10407',
                'https://www.pcaobus.org/oversight/standards/auditing-standards',
            ]
        )]
