"""
CENTRA Scan Engine
=====================
Async scan orchestrator. Runs plugins concurrently, streams results via WebSocket,
logs everything to the database.
"""
import asyncio
import json
import time
import logging

from database import Database
from ws_manager import ConnectionManager
from plugins import NaslPlugin, PluginResult, ScanContext

logger = logging.getLogger('centra.engine')

# Default scan targets for each Alien Inc company
COMPANY_TARGETS = {
    'alieninc': [
        {'host': 'localhost', 'name': 'Alien Inc Root', 'ports': [80, 443, 8721]},
    ],
    'rousseau': [
        {'host': 'localhost', 'name': 'Rousseau', 'ports': [80, 443]},
    ],
    'centra': [
        {'host': 'localhost', 'name': 'Centra', 'ports': [80, 443, 8721]},
    ],
    'kmt': [
        {'host': 'localhost', 'name': 'KMT Consulting', 'ports': [80, 443]},
    ],
    'alcantara': [
        {'host': 'localhost', 'name': 'Alcantara Art Foundation', 'ports': [80, 443]},
    ],
    'tdac': [
        {'host': 'localhost', 'name': 'The Daily Art Cult', 'ports': [80, 443]},
    ],
}


class ScanEngine:
    def __init__(self, db: Database, manager: ConnectionManager, plugins: list[NaslPlugin]):
        self.db = db
        self.manager = manager
        self.plugins = {p.PLUGIN_ID: p for p in plugins}
        self._active_scans: dict[str, asyncio.Event] = {}

    async def run_scan(self, scan_id: str, company_id: str, user_id: int,
                       targets: list[str], plugin_ids: list[str] | None = None):
        """Execute a full scan across all targets with selected plugins."""
        cancel = asyncio.Event()
        self._active_scans[scan_id] = cancel

        t0 = time.time()

        if plugin_ids:
            active_plugins = [self.plugins[int(pid)] for pid in plugin_ids
                              if int(pid) in self.plugins]
        else:
            active_plugins = list(self.plugins.values())

        # Sort plugins by type: settings → remote/local/combined → summary
        TYPE_ORDER = {'settings': 0, 'remote': 1, 'local': 1, 'combined': 1, 'summary': 2}
        active_plugins.sort(key=lambda p: TYPE_ORDER.get(p.PLUGIN_TYPE, 1))

        scan_context = ScanContext()
        total_plugins = len(active_plugins)
        total_tasks = total_plugins * len(targets)
        completed = 0

        await self.db.update_scan(
            scan_id, status='running', started_at=t0,
            total_plugins=total_plugins, plugin_ids=json.dumps([p.PLUGIN_ID for p in active_plugins])
        )

        await self._emit(scan_id, {
            'type': 'scan_started',
            'scan_id': scan_id,
            'total_plugins': total_plugins,
            'total_targets': len(targets),
            'total_tasks': total_tasks,
        })

        await self.db.add_log(scan_id, company_id, 'info', None,
                              f'Scan started: {total_plugins} plugins, {len(targets)} targets, {total_tasks} tasks')

        all_findings = []

        for plugin in active_plugins:
            if cancel.is_set():
                await self._emit(scan_id, {'type': 'scan_cancelled', 'scan_id': scan_id})
                await self.db.update_scan(scan_id, status='cancelled', finished_at=time.time())
                return

            # Dependency check (Nessus-style): ensure all deps have run
            if plugin.DEPENDENCIES:
                missing = [d for d in plugin.DEPENDENCIES
                          if scan_context.get_kb_item(f'findings/{d}/vuln') is None
                          and d not in {p.PLUGIN_ID for p in active_plugins}]
                if missing:
                    await self.db.add_log(
                        scan_id, company_id, 'warning', plugin.PLUGIN_ID,
                        f'Skipping {plugin.NAME}: dependencies not met {missing}'
                    )
                    continue

            await self._emit(scan_id, {
                'type': 'plugin_started',
                'plugin_id': plugin.PLUGIN_ID,
                'plugin_name': plugin.NAME,
                'family': plugin.FAMILY,
                'cvss': plugin.CVSS_SCORE,
            })

            await self.db.add_log(scan_id, company_id, 'info', plugin.PLUGIN_ID,
                                  f'Running: {plugin.NAME} (family={plugin.FAMILY}, cvss={plugin.CVSS_SCORE})')

            for target in targets:
                if cancel.is_set():
                    break

                if isinstance(target, str):
                    if ':' in target:
                        parts = target.rsplit(':', 1)
                        host = parts[0]
                        port_list = [int(parts[1])]
                    else:
                        host = target
                        port_list = [None]
                else:
                    host = target.get('host', target)
                    port_list = target.get('ports', [None])

                for port in port_list:
                    if cancel.is_set():
                        break

                    await self._emit(scan_id, {
                        'type': 'plugin_checking',
                        'plugin_id': plugin.PLUGIN_ID,
                        'target': host,
                        'port': port,
                        'log': f'Checking {host}:{port or "*"} with {plugin.NAME}',
                    })

                    results = await plugin.run(host, port, scan_context)

                    # Write to KB (Nessus KB convention)
                    scan_context.add_plugin_results(plugin.PLUGIN_ID, results)
                    vuln_results = [r for r in results if r.vulnerable]
                    scan_context.set_kb_item(
                        f'findings/{plugin.PLUGIN_ID}/vuln',
                        len(vuln_results) > 0
                    )
                    if vuln_results:
                        max_sev = max(vuln_results, key=lambda r: {
                            'critical': 5, 'high': 4, 'medium': 3, 'low': 2, 'info': 1
                        }.get(r.severity, 0))
                        scan_context.set_kb_item(
                            f'findings/{plugin.PLUGIN_ID}/sev',
                            max_sev.severity
                        )
                        scan_context.set_kb_item(
                            f'findings/{plugin.PLUGIN_ID}/detail',
                            max_sev.description[:200]
                        )
                    elif results:
                        scan_context.set_kb_item(
                            f'findings/{plugin.PLUGIN_ID}/sev', 'info'
                        )
                        scan_context.set_kb_item(
                            f'findings/{plugin.PLUGIN_ID}/detail',
                            results[0].description[:200]
                        )

                    for result in results:
                        all_findings.append(result)

                        severity = result.severity or plugin.severity_from_cvss(result.cvss_score)
                        status = 'fail' if result.vulnerable else 'pass'

                        await self.db.add_finding(
                            scan_id, company_id, plugin.PLUGIN_ID,
                            plugin.NAME, plugin.FAMILY, result.cvss_score,
                            result.target, result.port, severity,
                            result.description, result.solution,
                            result.references, result.evidence,
                            status=status
                        )

                        if result.vulnerable:
                            await self._emit(scan_id, {
                                'type': 'finding',
                                'plugin_id': plugin.PLUGIN_ID,
                                'plugin_name': plugin.NAME,
                                'family': plugin.FAMILY,
                                'cvss': result.cvss_score,
                                'severity': severity,
                                'target': result.target,
                                'port': result.port,
                                'description': result.description,
                                'solution': result.solution,
                                'evidence': result.evidence,
                                'references': result.references,
                            })

                            await self.db.add_log(
                                scan_id, company_id, 'warning', plugin.PLUGIN_ID,
                                f'FINDING: {plugin.NAME} on {result.target}:{result.port or "*"} — {severity.upper()} (CVSS {result.cvss_score})'
                            )

                    completed += 1
                    progress = round((completed / total_tasks) * 100, 1)

                    await self.db.update_scan(scan_id, progress=progress, completed_plugins=completed)
                    await self._emit(scan_id, {
                        'type': 'progress',
                        'scan_id': scan_id,
                        'progress': progress,
                        'completed': completed,
                        'total': total_tasks,
                        'current_plugin': plugin.NAME,
                    })

            await self._emit(scan_id, {
                'type': 'plugin_completed',
                'plugin_id': plugin.PLUGIN_ID,
                'plugin_name': plugin.NAME,
                'findings_count': sum(1 for f in all_findings if True),
            })

        elapsed = round(time.time() - t0, 2)
        severity_counts = {'critical': 0, 'high': 0, 'medium': 0, 'low': 0, 'info': 0}
        for f in all_findings:
            sev = f.severity or 'info'
            if sev in severity_counts:
                severity_counts[sev] += 1

        summary = {
            'total_findings': len(all_findings),
            'severity': severity_counts,
            'elapsed_seconds': elapsed,
            'plugins_run': total_plugins,
            'targets_scanned': len(targets),
        }

        await self.db.update_scan(
            scan_id, status='completed', progress=100,
            completed_plugins=total_plugins, finished_at=time.time()
        )

        await self._emit(scan_id, {
            'type': 'scan_completed',
            'scan_id': scan_id,
            'elapsed': elapsed,
            'summary': summary,
        })

        await self.db.add_log(
            scan_id, company_id, 'info', None,
            f'Scan completed in {elapsed}s: {len(all_findings)} findings '
            f'(critical={severity_counts["critical"]}, high={severity_counts["high"]}, '
            f'medium={severity_counts["medium"]}, low={severity_counts["low"]})'
        )

        logger.info(f'Scan {scan_id} completed: {len(all_findings)} findings in {elapsed}s')
        del self._active_scans[scan_id]

    async def cancel_scan(self, scan_id: str, company_id: str):
        cancel = self._active_scans.get(scan_id)
        if cancel:
            cancel.set()
            await self.db.add_log(scan_id, company_id, 'warning', None, 'Scan cancelled by user')

    async def _emit(self, scan_id: str, message: dict):
        message['scan_id'] = scan_id
        await self.manager.send_to_scan(scan_id, message)
