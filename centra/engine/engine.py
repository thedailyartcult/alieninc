"""
CENTRA Scan Engine
====================
Async scan orchestrator. Runs plugins concurrently with bounded parallelism,
batches DB writes, and enforces wall-clock timeouts.
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

# Tuning constants
MAX_CONCURRENT = 50        # parallel plugin executions
PLUGIN_TIMEOUT = 2.0       # seconds per plugin (network timeout cap)
DEFAULT_PLUGIN_CAP = 2000  # max plugins per scan (compliance_report uses this)
DB_BATCH_SIZE = 100        # findings to buffer before commit
PROGRESS_INTERVAL = 2.0    # seconds between progress updates


class ScanEngine:
    def __init__(self, db: Database, manager: ConnectionManager, plugins: list[NaslPlugin]):
        self.db = db
        self.manager = manager
        self.plugins = {p.PLUGIN_ID: p for p in plugins}
        self._active_scans: dict[str, asyncio.Event] = {}

    async def run_scan(self, scan_id: str, company_id: str, user_id: int,
                       targets: list[str], plugin_ids: list[str] | None = None,
                       plugin_cap: int = DEFAULT_PLUGIN_CAP,
                       wall_timeout: float = 300.0):
        """
        Execute a scan across targets with selected plugins.

        Args:
            plugin_cap: Max plugins to run (samples if more available).
            wall_timeout: Hard wall-clock limit in seconds. Returns partial results if hit.
        """
        cancel = asyncio.Event()
        self._active_scans[scan_id] = cancel

        t0 = time.time()

        if plugin_ids:
            all_plugins = [self.plugins[int(pid)] for pid in plugin_ids
                           if int(pid) in self.plugins]
        else:
            all_plugins = list(self.plugins.values())

        # Cap FIRST (using only entry metadata, no lazy imports), then load + sort
        if len(all_plugins) > plugin_cap:
            step = len(all_plugins) / plugin_cap
            sampled = []
            for i in range(plugin_cap):
                idx = int(i * step)
                sampled.append(all_plugins[idx])
        else:
            sampled = all_plugins

        # Now load real plugins for the sampled set (triggers imports only for these)
        active_plugins = []
        for p in sampled:
            real = p._load_real() if hasattr(p, '_load_real') else p
            if real:
                active_plugins.append(real)

        # Sort loaded plugins by type: settings → remote/local/combined → summary
        TYPE_ORDER = {'settings': 0, 'remote': 1, 'local': 1, 'combined': 1, 'summary': 2}
        active_plugins.sort(key=lambda p: TYPE_ORDER.get(getattr(p, 'PLUGIN_TYPE', 'remote'), 1))

        # Expand targets into (host, port) pairs
        target_ports = []
        for target in targets:
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
                target_ports.append((host, port))

        scan_context = ScanContext()
        total_plugins = len(active_plugins)
        total_tasks = total_plugins * len(target_ports)
        completed = 0

        await self.db.update_scan(
            scan_id, status='running', started_at=t0,
            total_plugins=total_plugins,
            plugin_ids=json.dumps([p.PLUGIN_ID for p in active_plugins])
        )

        await self._emit(scan_id, {
            'type': 'scan_started',
            'scan_id': scan_id,
            'total_plugins': total_plugins,
            'total_targets': len(target_ports),
            'total_tasks': total_tasks,
        })

        await self.db.add_log(scan_id, company_id, 'info', None,
                              f'Scan started: {total_plugins} plugins, '
                              f'{len(target_ports)} target:port pairs, '
                              f'{total_tasks} tasks (cap={plugin_cap}, timeout={wall_timeout}s)')

        all_findings = []
        finding_buffer = []
        last_progress = time.time()
        timed_out = False

        async def _flush_findings():
            if finding_buffer:
                await self.db.add_findings_batch(finding_buffer)
                finding_buffer.clear()

        async def _run_one(plugin, host, port):
            """Run a single plugin against a single host:port with timeout."""
            try:
                results = await asyncio.wait_for(
                    plugin.run(host, port, scan_context),
                    timeout=PLUGIN_TIMEOUT
                )
                return plugin, host, port, results, None
            except asyncio.TimeoutError:
                return plugin, host, port, [], 'timeout'
            except Exception as e:
                return plugin, host, port, [], str(e)

        # Build all tasks
        tasks = []
        for plugin in active_plugins:
            for host, port in target_ports:
                tasks.append((plugin, host, port))

        # Execute with bounded concurrency
        semaphore = asyncio.Semaphore(MAX_CONCURRENT)
        completed_count = 0

        async def _bounded_run(plugin, host, port):
            nonlocal completed_count
            async with semaphore:
                result = await _run_one(plugin, host, port)
                completed_count += 1
                return result

        # Run all tasks concurrently (bounded by semaphore)
        try:
            coros = [_bounded_run(p, h, pt) for p, h, pt in tasks]
            for coro in asyncio.as_completed(coros):
                # Check wall-clock timeout
                elapsed = time.time() - t0
                if elapsed >= wall_timeout:
                    timed_out = True
                    cancel.set()
                    break

                if cancel.is_set():
                    break

                plugin, host, port, results, error = await coro

                if error:
                    if error == 'timeout':
                        await self.db.add_log(
                            scan_id, company_id, 'debug', plugin.PLUGIN_ID,
                            f'TIMEOUT: {plugin.NAME} on {host}:{port}'
                        )
                    continue

                # Write to KB
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
                        f'findings/{plugin.PLUGIN_ID}/sev', max_sev.severity)
                    scan_context.set_kb_item(
                        f'findings/{plugin.PLUGIN_ID}/detail', max_sev.description[:200])
                elif results:
                    scan_context.set_kb_item(
                        f'findings/{plugin.PLUGIN_ID}/sev', 'info')
                    scan_context.set_kb_item(
                        f'findings/{plugin.PLUGIN_ID}/detail', results[0].description[:200])

                for result in results:
                    all_findings.append(result)
                    severity = result.severity or plugin.severity_from_cvss(result.cvss_score)
                    status = 'fail' if result.vulnerable else 'pass'
                    finding_buffer.append((
                        scan_id, company_id, plugin.PLUGIN_ID,
                        plugin.NAME, plugin.FAMILY, result.cvss_score,
                        result.target, result.port, severity,
                        result.description, result.solution,
                        json.dumps(result.references), result.evidence, status
                    ))

                # Batch flush
                if len(finding_buffer) >= DB_BATCH_SIZE:
                    await _flush_findings()

                # Throttled progress
                now = time.time()
                if now - last_progress >= PROGRESS_INTERVAL:
                    last_progress = now
                    progress = round((completed_count / total_tasks) * 100, 1)
                    await self.db.update_scan(scan_id, progress=progress,
                                              completed_plugins=completed_count)
                    await self._emit(scan_id, {
                        'type': 'progress',
                        'scan_id': scan_id,
                        'progress': progress,
                        'completed': completed_count,
                        'total': total_tasks,
                        'current_plugin': plugin.NAME,
                    })

        except asyncio.CancelledError:
            pass

        # Final flush
        await _flush_findings()

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
            'targets_scanned': len(target_ports),
            'timed_out': timed_out,
            'completed_tasks': completed_count,
            'total_tasks': total_tasks,
        }

        status = 'completed' if not timed_out else 'partial'

        await self.db.update_scan(
            scan_id, status=status, progress=100 if not timed_out else round((completed_count / total_tasks) * 100, 1),
            completed_plugins=completed_count, finished_at=time.time()
        )

        await self._emit(scan_id, {
            'type': f'scan_{status}',
            'scan_id': scan_id,
            'elapsed': elapsed,
            'summary': summary,
        })

        await self.db.add_log(
            scan_id, company_id, 'info', None,
            f'Scan {status} in {elapsed}s: {len(all_findings)} findings '
            f'(critical={severity_counts["critical"]}, high={severity_counts["high"]}, '
            f'medium={severity_counts["medium"]}, low={severity_counts["low"]}) '
            f'[{completed_count}/{total_tasks} tasks]'
        )

        logger.info(f'Scan {scan_id} {status}: {len(all_findings)} findings in {elapsed}s')
        del self._active_scans[scan_id]

    async def cancel_scan(self, scan_id: str, company_id: str):
        cancel = self._active_scans.get(scan_id)
        if cancel:
            cancel.set()
            await self.db.add_log(scan_id, company_id, 'warning', None, 'Scan cancelled by user')

    async def _emit(self, scan_id: str, message: dict):
        message['scan_id'] = scan_id
        await self.manager.send_to_scan(scan_id, message)
