"""
Centra Compliance Mapper
========================
Maps Centra scan plugin results to specific compliance framework controls.

Each plugin verifies one or more technical controls. This module maps those
plugin results to the numbered controls in each compliance framework,
producing a structured compliance status report.

Frameworks covered:
  - SOC 2 Type II (AICPA Trust Service Criteria)
  - ISO 27001:2022 (Annex A Controls)
  - GDPR (Articles & Technical Measures)
  - CCPA (Technical Requirements)
  - HIPAA (Technical Safeguards)
  - FedRAMP High (NIST 800-53 Controls)
  - CMMC Level 2 (NIST SP 800-171)
  - CSA STAR (Cloud Controls Matrix)
  - VPAT / WCAG 2.1 AA
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ControlStatus:
    """Status of a single compliance control."""
    control_id: str
    control_name: str
    status: str  # 'verified', 'partial', 'not_verified', 'not_testable'
    evidence: list[str] = field(default_factory=list)
    plugins: list[int] = field(default_factory=list)
    notes: str = ''


@dataclass
class FrameworkReport:
    """Compliance status for a single framework."""
    framework_id: str
    framework_name: str
    controls: list[ControlStatus] = field(default_factory=list)
    verified: int = 0
    partial: int = 0
    not_verified: int = 0
    not_testable: int = 0
    score: float = 0.0


# =============================================================================
# CONTROL MAPPINGS
# =============================================================================
# Each mapping: framework -> control_id -> (control_name, [plugin_ids])
# A plugin passing = control verified. A plugin failing = control at risk.
# Multiple plugins can contribute to one control.

CONTROLS = {

    'soc2': {
        'name': 'SOC 2 Type II',
        'controls': {
            'CC6.1': ('Logical and Physical Access Controls', [1027, 1028]),
            'CC6.2': ('Encryption and Data Protection in Transit', [1005, 1029, 1030]),
            'CC6.3': ('Access Security for Systems', [1027, 1028]),
            'CC6.6': ('Boundary Protection', [1003, 1010, 1011, 1012, 1018]),
            'CC6.7': ('Data Transmission Restrictions', [1022, 1023]),
            'CC6.8': ('Vulnerability Management', [1001, 1002, 1004, 1005, 1006, 1007, 1008, 1009]),
            'CC7.1': ('Change Detection', [1012, 1014]),
            'CC7.2': ('Threat and Vulnerability Monitoring', [1010, 1011, 1014, 1017, 1021]),
            'CC7.3': ('Incident Response', [1014, 1024, 1031]),
            'CC7.4': ('Incident Analysis', [1010, 1012, 1024]),
            'CC8.1': ('Change Management Controls', [1004, 1009, 1031]),
        }
    },

    'iso27001': {
        'name': 'ISO 27001:2022',
        'controls': {
            'A.5.7': ('Threat Intelligence', [1024]),
            'A.5.23': ('Information Security for Cloud Services', [1005, 1030]),
            'A.5.34': ('Privacy and PII Protection', [1025, 1031]),
            'A.5.35': ('Independent Review of ISMS', [1024]),
            'A.8.4': ('Access to Source Code', [1004]),
            'A.8.5': ('Secure Authentication', [1027, 1028]),
            'A.8.7': ('Protection Against Malware', [1010, 1011]),
            'A.8.8': ('Vulnerability Management', [1001, 1002, 1003, 1004, 1005, 1006, 1007, 1008, 1009]),
            'A.8.9': ('Configuration Management', [1003, 1009]),
            'A.8.11': ('Data Masking', [1010, 1023]),
            'A.8.12': ('Data Leakage Prevention', [1010, 1011, 1014, 1021]),
            'A.8.15': ('Logging', [1014]),
            'A.8.16': ('Monitoring Activities', [1010, 1011, 1012, 1017, 1024]),
            'A.8.20': ('Network Security', [1001, 1006, 1007, 1008]),
            'A.8.21': ('Security of Network Services', [1005, 1022]),
            'A.8.23': ('Web Security', [1003, 1004, 1009, 1018, 1020, 1029]),
            'A.8.24': ('Use of Cryptography', [1005, 1029, 1030]),
        }
    },

    'gdpr': {
        'name': 'GDPR',
        'controls': {
            'Art.5': ('Data Processing Principles', [1025, 1031]),
            'Art.7': ('Conditions for Consent', [1025, 1031]),
            'Art.12': ('Transparency — Privacy Notice', [1025, 1031]),
            'Art.13': ('Information to Data Subject', [1025, 1031]),
            'Art.15': ('Right of Access', [1025, 1031]),
            'Art.17': ('Right to Erasure', [1025, 1031]),
            'Art.20': ('Data Portability', [1025]),
            'Art.25': ('Data Protection by Design', [1003, 1026, 1027]),
            'Art.30': ('Records of Processing', [1024]),
            'Art.32': ('Security of Processing', [1001, 1003, 1004, 1005, 1009, 1010, 1011, 1018, 1027, 1028]),
            'Art.33': ('Breach Notification', [1014, 1024, 1031]),
            'Art.35': ('Data Protection Impact Assessment', [1024]),
        }
    },

    'ccpa': {
        'name': 'CCPA',
        'controls': {
            '1798.100': ('Right to Know', [1025]),
            '1798.105': ('Right to Delete', [1025]),
            '1798.110': ('Notice at Collection', [1025, 1031]),
            '1798.120': ('Right to Opt-Out of Sale', [1025, 1031]),
            '1798.130': ('Consumer Rights Processes', [1025]),
            '1798.150': ('Data Security — Reasonable Security', [1001, 1003, 1004, 1005, 1010, 1011, 1027, 1028]),
        }
    },

    'hipaa': {
        'name': 'HIPAA',
        'controls': {
            '164.308(a)(3)': ('Access Control', [1027, 1028]),
            '164.308(a)(4)': ('Person or Entity Authentication', [1027, 1028]),
            '164.310(a)(1)': ('Facility Access Controls', [1007, 1008]),
            '164.310(d)(1)': ('Device and Media Controls', [1007, 1008]),
            '164.312(a)(1)': ('Access Control — Technical', [1027, 1028]),
            '164.312(c)(1)': ('Integrity', [1004, 1005, 1029]),
            '164.312(d)': ('Person or Entity Authentication', [1027, 1028]),
            '164.312(e)(1)': ('Transmission Security', [1005, 1029, 1030]),
        }
    },

    'fedramp': {
        'name': 'FedRAMP High',
        'controls': {
            'AC-2': ('Account Management', [1027, 1028]),
            'AC-3': ('Access Enforcement', [1027, 1028]),
            'AC-7': ('Unsuccessful Login Attempts', [1028]),
            'AC-17': ('Remote Access', [1001, 1005]),
            'AU-2': ('Audit Events', [1014, 1031]),
            'CM-6': ('Configuration Settings', [1003, 1009, 1031]),
            'IA-2': ('Identification and Authentication', [1027, 1028]),
            'IA-5': ('Authenticator Management', [1027, 1028]),
            'IR-6': ('Incident Reporting', [1014, 1024, 1031]),
            'SC-8': ('Transmission Confidentiality and Integrity', [1005, 1029, 1030]),
            'SC-12': ('Cryptographic Key Management', [1005, 1030]),
            'SC-13': ('Cryptographic Protection', [1005, 1029, 1030]),
            'SI-2': ('Flaw Remediation', [1001, 1004, 1005]),
            'SI-3': ('Malicious Code Protection', [1010, 1011]),
            'SI-10': ('Information Input Validation', [1020, 1022]),
            'SI-11': ('Error Handling', [1014]),
        }
    },

    'cmmc': {
        'name': 'CMMC Level 2',
        'controls': {
            'AC.1.001': ('Limit Information Access', [1027, 1028]),
            'AC.2.006': ('Control Information Flow', [1022, 1023]),
            'AU.2.001': ('Audit Events', [1014]),
            'CM.2.001': ('Baseline Configurations', [1003, 1009]),
            'IA.2.001': ('Identification and Authentication', [1027, 1028]),
            'IR.1.001': ('Incident Reporting', [1014, 1024, 1031]),
            'SC.2.001': ('Boundary Protection', [1001, 1006, 1022]),
            'SC.3.001': ('Access Control for Mobile', [1007, 1008]),
            'SI.1.001': ('Identify and Manage Flaws', [1001, 1004, 1005]),
            'SI.1.002': ('Malicious Code Protection', [1010, 1011]),
            'SI.1.003': ('Anomaly Detection', [1010, 1012, 1017, 1024]),
        }
    },

    'csastar': {
        'name': 'CSA STAR',
        'controls': {
            'AIS-03': ('Application Security', [1003, 1004, 1009, 1021]),
            'AIS-04': ('Encryption', [1005, 1029, 1030]),
            'BCR-01': ('Backup and Recovery', [1004]),
            'CEK-01': ('Key and Certificate Management', [1005, 1030]),
            'DSI-01': ('Data Security', [1003, 1004, 1010, 1011, 1031]),
            'IAM-01': ('Identity and Access Management', [1027, 1028]),
            'IAM-02': ('Authentication', [1027, 1028]),
            'IVM-01': ('Vulnerability and Patch Management', [1001, 1004, 1005, 1006, 1009]),
            'NEC-01': ('Network Security', [1001, 1006, 1022]),
            'SEF-01': ('Security Event and Logging', [1014, 1031]),
            'STA-01': ('Secure Application Development', [1004, 1009, 1021]),
            'TPM-01': ('Third-Party Risk', [1022, 1029]),
        }
    },

    'vpat': {
        'name': 'VPAT / WCAG 2.1 AA',
        'controls': {
            '1.1.1': ('Non-text Content — Alt Text', [1026]),
            '1.3.1': ('Info and Relationships — Headings', [1026]),
            '1.3.4': ('Orientation', [1026]),
            '1.4.4': ('Resize Text', [1026]),
            '2.1.1': ('Keyboard Accessible', [1026]),
            '2.4.1': ('Bypass Blocks — Skip Nav', [1026, 1031]),
            '3.1.1': ('Language of Page', [1026, 1031]),
            '4.1.1': ('Parsing — Valid HTML', [1026]),
            '4.1.2': ('Name, Role, Value — ARIA', [1026, 1031]),
        }
    },

    'sox': {
        'name': 'SOX',
        'controls': {
            '302': ('Corporate Responsibility — Financial Data Integrity', [1004, 1010]),
            '404': ('Internal Control Assessment', [1003, 1004, 1009, 1027]),
            '409': ('Real-Time Disclosure', [1010, 1024]),
            '802': ('Document Alteration Prevention', [1004, 1029]),
        }
    },

    'tisax': {
        'name': 'TISAX',
        'controls': {
            '3.1': ('Information Security Policies', [1024]),
            '4.1': ('Access Control', [1027, 1028]),
            '4.2': ('Cryptography', [1005, 1029, 1030]),
            '5.1': ('Network Security', [1001, 1006, 1022]),
            '5.2': ('Web Application Security', [1003, 1004, 1009, 1018]),
            '6.1': ('Incident Management', [1014, 1024, 1031]),
            '7.1': ('Data Protection', [1010, 1011, 1025]),
            '8.1': ('Prototype Protection', [1004, 1021]),
        }
    },
}


# =============================================================================
# COMPLIANCE REPORT GENERATION
# =============================================================================

def generate_compliance_report(scan_results: dict) -> list[FrameworkReport]:
    """
    Generate compliance reports for all frameworks based on scan results.

    Args:
        scan_results: dict mapping plugin_id -> {vulnerable: bool, severity: str, evidence: str}

    Returns:
        list of FrameworkReport objects
    """
    reports = []

    for fw_id, fw_data in CONTROLS.items():
        report = FrameworkReport(
            framework_id=fw_id,
            framework_name=fw_data['name'],
        )

        for ctrl_id, (ctrl_name, plugin_ids) in fw_data['controls'].items():
            status = _evaluate_control(ctrl_id, ctrl_name, plugin_ids, scan_results)
            report.controls.append(status)

            if status.status == 'verified':
                report.verified += 1
            elif status.status == 'partial':
                report.partial += 1
            elif status.status == 'not_verified':
                report.not_verified += 1
            else:
                report.not_testable += 1

        total = len(report.controls)
        if total > 0:
            report.score = round(
                (report.verified * 1.0 + report.partial * 0.5) / total * 100, 1
            )

        reports.append(report)

    return reports


def _evaluate_control(
    ctrl_id: str,
    ctrl_name: str,
    plugin_ids: list[int],
    scan_results: dict,
) -> ControlStatus:
    """Evaluate a single control based on its associated plugin results."""
    evidence = []
    passing_plugins = []
    failing_plugins = []
    missing_plugins = []
    untested_plugins = []

    for pid in plugin_ids:
        result = scan_results.get(pid)
        if result is None:
            missing_plugins.append(pid)
        elif result.get('not_tested'):
            untested_plugins.append(pid)
            if result.get('evidence'):
                evidence.append(f'Plugin {pid}: {result["evidence"][:80]}')
        elif not result.get('vulnerable', True):
            passing_plugins.append(pid)
            if result.get('evidence'):
                evidence.append(f'Plugin {pid}: {result["evidence"][:80]}')
        else:
            failing_plugins.append(pid)
            if result.get('evidence'):
                evidence.append(f'Plugin {pid} FAILED: {result["evidence"][:80]}')

    if not plugin_ids:
        status = 'not_testable'
    elif failing_plugins:
        status = 'not_verified'
    elif untested_plugins and not passing_plugins:
        status = 'not_testable'
    elif untested_plugins:
        status = 'partial'
    elif missing_plugins and not passing_plugins:
        status = 'not_testable'
    elif missing_plugins:
        status = 'partial'
    else:
        status = 'verified'

    notes = ''
    if failing_plugins:
        notes = f'Failed plugins: {", ".join(str(p) for p in failing_plugins)}'
    elif untested_plugins:
        notes = f'Plugins not executed on scanned ports: {", ".join(str(p) for p in untested_plugins)}'
    elif missing_plugins:
        notes = f'Missing plugins: {", ".join(str(p) for p in missing_plugins)}'

    return ControlStatus(
        control_id=ctrl_id,
        control_name=ctrl_name,
        status=status,
        evidence=evidence[:5],
        plugins=plugin_ids,
        notes=notes,
    )


def get_framework_summary(reports: list[FrameworkReport]) -> dict:
    """Get a high-level summary of all framework compliance statuses."""
    summary = {}
    for r in reports:
        summary[r.framework_id] = {
            'name': r.framework_name,
            'score': r.score,
            'verified': r.verified,
            'partial': r.partial,
            'not_verified': r.not_verified,
            'not_testable': r.not_testable,
            'total_controls': len(r.controls),
            'status': 'compliant' if r.score >= 90 else 'partial' if r.score >= 60 else 'non_compliant',
        }
    return summary
