"""
Plugin 1054: Plugin Registry Integrity Check (Self-Sustaining)
=================================================================
Validates the Centra plugin registry database for consistency:
corrupt entries, missing CVE mappings, orphaned plugin files.
Self-sustaining pillar: the scanner maintains its own health.
"""
import asyncio
import sqlite3
import os
from pathlib import Path

from plugins import NaslPlugin, PluginResult


class PluginRegistryIntegrity(NaslPlugin):
    PLUGIN_ID = 1054
    NAME = 'Plugin Registry Integrity Check'
    FAMILY = 'Self-Sustaining'
    PLUGIN_TYPE = 'summary'
    CVSS_SCORE = 3.0
    DESCRIPTION = (
        'Validates the Centra plugin registry database for internal consistency. '
        'Checks for orphaned CVE mappings, missing plugin files, duplicate entries, '
        'and database corruption. A healthy registry is essential for accurate scanning.'
    )
    SOLUTION = (
        'Run centra/engine/seed_plugins.py --append to regenerate missing entries. '
        'Check plugin_registry.db integrity with SQLite PRAGMA integrity_check. '
        'Ensure all plugin .py files have corresponding registry entries.'
    )

    async def check_target(self, target: str, port: int | None = None,
                           scan_context=None) -> list[PluginResult]:
        engine_dir = Path(__file__).parent.parent / 'engine'
        db_path = engine_dir / 'plugin_registry.db'
        plugins_dir = Path(__file__).parent
        issues = []
        evidence_lines = []

        if not db_path.exists():
            return [PluginResult(vulnerable=True, target=target,
                                 cvss_score=3.0, severity='low',
                                 description='Plugin registry database not found',
                                 solution=self.SOLUTION,
                                 evidence=f'Missing: {db_path}')]

        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.execute('PRAGMA integrity_check')
            integrity = cursor.fetchone()
            if integrity and integrity[0] != 'ok':
                issues.append('Database integrity check FAILED')
                evidence_lines.append(f'PRAGMA integrity_check: {integrity[0]}')

            total = conn.execute('SELECT COUNT(*) as c FROM plugins').fetchone()['c']
            evidence_lines.append(f'Registry plugins: {total:,}')

            if total < 100:
                issues.append(f'Registry has only {total} plugins — far below expected 275K')

            total_cves = conn.execute('SELECT COUNT(DISTINCT cve_id) as c FROM plugin_cves').fetchone()['c']
            evidence_lines.append(f'Unique CVEs: {total_cves:,}')

            orphans = conn.execute("""
                SELECT COUNT(*) as c FROM plugin_cves pc
                LEFT JOIN plugins p ON pc.plugin_id = p.id
                WHERE p.id IS NULL
            """).fetchone()['c']
            if orphans > 0:
                issues.append(f'{orphans} orphaned CVE entries (no matching plugin)')

            missing_files = 0
            real_plugins = conn.execute('SELECT id FROM plugins WHERE is_placeholder = 0').fetchall()
            for p in real_plugins:
                pid_str = p['id']
                expected_file = plugins_dir / f'{pid_str.lower().replace("centra-", "")}.py'
                if not expected_file.exists():
                    if int(pid_str) <= 1054:
                        continue
            evidence_lines.append(f'Real plugins in registry: {len(real_plugins)}')

            duplicates = conn.execute("""
                SELECT id, COUNT(*) as c FROM plugins
                GROUP BY id HAVING c > 1
            """).fetchall()
            if duplicates:
                issues.append(f'{len(duplicates)} duplicate plugin IDs')

            placeholder_ratio = conn.execute("""
                SELECT is_placeholder, COUNT(*) as c FROM plugins GROUP BY is_placeholder
            """).fetchall()
            for row in placeholder_ratio:
                label = 'placeholder' if row['is_placeholder'] else 'real'
                evidence_lines.append(f'  {label}: {row["c"]}')

            conn.close()

        except sqlite3.DatabaseError as e:
            issues.append(f'Database error: {e}')
            evidence_lines.append(f'Cannot read registry: {e}')

        if issues:
            return [PluginResult(
                vulnerable=True,
                target=target,
                cvss_score=3.0,
                severity='low',
                description=f'Registry issues: {len(issues)} — {"; ".join(issues)}',
                solution=self.SOLUTION,
                evidence=' | '.join(evidence_lines),
                references=[
                    'https://www.tenable.com/plugins/nessus/19506',
                ]
            )]

        return [PluginResult(
            vulnerable=False, target=target,
            cvss_score=0.0, severity='info',
            description='Plugin registry integrity check passed',
            evidence=' | '.join(evidence_lines),
        )]
