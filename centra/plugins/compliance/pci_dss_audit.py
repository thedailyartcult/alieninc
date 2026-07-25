"""
Plugin 1048: PCI-DSS Compliance Audit Summary
================================================
Aggregates scan findings and maps them to PCI-DSS v4.0 requirements.
Type: summary — reads KB findings from other plugins.
"""
import asyncio

from plugins import NaslPlugin, PluginResult, ScanContext


class PciDssAudit(NaslPlugin):
    PLUGIN_ID = 1048
    NAME = 'PCI-DSS Compliance Audit Summary'
    FAMILY = 'Compliance & Audit'
    PLUGIN_TYPE = 'summary'
    CVSS_SCORE = 0.0
    DESCRIPTION = (
        'Aggregates vulnerability scan results and maps them to PCI-DSS v4.0 '
        'compliance requirements. Generates a PCI-DSS compliance scorecard '
        'showing which requirements are met and which require remediation.'
    )
    SOLUTION = (
        'Review PCI-DSS requirements with failing status. Remediate associated '
        'vulnerabilities and re-scan. Maintain compliance evidence for the '
        'self-assessment questionnaire (SAQ) or Report on Compliance (ROC).'
    )
    DEPENDENCIES = [1001, 1003, 1004, 1005, 1007, 1008, 1027, 1028, 1029, 1030, 1032, 1037, 1038, 1040]

    PCI_REQUIREMENTS = {
        'req1': ('1.1 — Firewall Configuration', [1003, 1007, 1008, 1037]),
        'req2': ('2.1 — No Vendor Defaults', [1001, 1002, 1034, 1036]),
        'req3': ('3.1 — Cardholder Data Protection', [1004, 1010, 1041]),
        'req4': ('4.1 — Encryption in Transit', [1005, 1029, 1030, 1032]),
        'req5': ('5.1 — Malware Protection', [1010, 1011]),
        'req6': ('6.1 — Secure Application Development', [1009, 1020, 1022, 1039, 1042, 1044]),
        'req7': ('7.1 — Access Control', [1027, 1028, 1036, 1040]),
        'req8': ('8.1 — Authentication', [1027, 1028, 1036]),
        'req9': ('9.1 — Physical Security', []),
        'req10': ('10.1 — Audit Logging', [1014]),
        'req11': ('11.1 — Security Testing', [1039, 1042, 1044]),
        'req12': ('12.1 — Information Security Policy', [1024, 1031]),
    }

    async def check_target(self, target: str, port: int | None = None,
                           scan_context: ScanContext | None = None) -> list[PluginResult]:
        if scan_context is None:
            return [PluginResult(vulnerable=False, target=target, severity='info',
                                 description='PCI-DSS audit requires scan context')]

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

        for req_id, (req_name, plugin_ids) in self.PCI_REQUIREMENTS.items():
            if not plugin_ids:
                not_tested += 1
                continue

            req_failed = any(pid in plugin_vulns for pid in plugin_ids)
            req_tested = any(pid in all_results for pid in plugin_ids)

            if not req_tested:
                not_tested += 1
                details.append(f'  {req_name}: NOT TESTED')
            elif req_failed:
                failed += 1
                failing = [str(pid) for pid in plugin_ids if pid in plugin_vulns]
                details.append(f'  {req_name}: FAIL ({", ".join(failing)})')
            else:
                passed += 1
                details.append(f'  {req_name}: PASS')

        total = len([r for r in self.PCI_REQUIREMENTS if self.PCI_REQUIREMENTS[r][1]])
        score = round(passed / total * 100, 1) if total > 0 else 0

        return [PluginResult(
            vulnerable=failed > 0,
            target=target,
            cvss_score=0.0,
            severity='critical' if failed > 3 else 'high' if failed > 0 else 'info',
            description=f'PCI-DSS: {passed}/{total} reqs passed ({score}%) — {failed} failed, {not_tested} not tested',
            evidence='\n'.join(details),
            references=[
                'https://www.pcisecuritystandards.org/',
                'https://www.tenable.com/plugins/nessus/175895',
            ]
        )]
