"""
CENTRA Strix Connector
========================
Wraps the Strix AI penetration-testing CLI as a subprocess.

Strix (https://github.com/usestrix/strix) is a CLI-first autonomous AI
pentesting agent — NOT a REST service. This connector:

  1. Spawns `strix -n -t <target> -m <mode>` in a controlled working directory.
  2. Discovers the auto-generated run directory (strix_runs/<slug>_<hex>).
  3. Polls run.json for status and vulnerabilities.json for validated findings.
  4. Maps Strix finding dicts → Centra's findings table (source='strix').
  5. Emits WebSocket progress events so the dashboard updates live.

Strix requires Python >=3.12 (installed at /srv/strix/venv), Docker for its
sandbox, and an LLM API key (env: STRIX_LLM / LLM_API_KEY / LLM_API_BASE).
"""
import asyncio
import json
import os
import time
import logging
import shutil
from pathlib import Path

from database import Database
from ws_manager import ConnectionManager

logger = logging.getLogger('centra.strix')

STRIX_VENV = Path('/srv/strix/venv')
STRIX_BIN = STRIX_VENV / 'bin' / 'strix'
STRIX_RUNS_BASE = Path('/srv/strix')          # subprocess cwd → writes ./strix_runs/
STRIX_RUNS_DIR = STRIX_RUNS_BASE / 'strix_runs'

POLL_INTERVAL = 2.0          # seconds between run-dir / finding polls
FINDING_POLL_INTERVAL = 3.0  # seconds between vulnerabilities.json re-reads
PROCESS_TIMEOUT = 1800       # 30 min hard cap on a single Strix run
MIN_FREE_RAM_MB = 1024       # refuse to launch a Strix sandbox below this free RAM


class StrixConnector:
    """Manages Strix CLI invocations and result ingestion."""

    def __init__(self, db: Database, manager: ConnectionManager):
        self.db = db
        self.manager = manager
        self._active: dict[str, asyncio.subprocess.Process] = {}

    # ── Health / Config ──

    def _free_ram_mb(self) -> int:
        """Return available RAM in MB (best-effort, cross-platform)."""
        try:
            with open('/proc/meminfo') as f:
                for line in f:
                    if line.startswith('MemAvailable:'):
                        return int(line.split()[1]) // 1024
        except OSError:
            pass
        return 4096  # optimistic fallback if /proc unavailable

    def health(self) -> dict:
        """Report Strix CLI, Docker, LLM, and host-resource status."""
        free_ram = self._free_ram_mb()
        cli_ok = STRIX_BIN.exists() and os.access(STRIX_BIN, os.X_OK)
        docker_ok = shutil.which('docker') is not None
        llm_key = bool(os.environ.get('LLM_API_KEY') or os.environ.get('OPENAI_API_KEY')
                        or os.environ.get('HETZNER_VLLM_API_KEY'))
        llm_base = os.environ.get('LLM_API_BASE', '')
        llm_model = os.environ.get('STRIX_LLM', '')
        version = ''
        if cli_ok:
            try:
                import subprocess
                r = subprocess.run(
                    [str(STRIX_BIN), '--version'],
                    capture_output=True, text=True, timeout=10
                )
                version = r.stdout.strip().split('\n')[0]
            except Exception:
                version = ''
        ready = cli_ok and docker_ok and llm_key
        missing = []
        if not cli_ok: missing.append('Strix CLI')
        if not docker_ok: missing.append('Docker')
        if not llm_key: missing.append('LLM_API_KEY')
        if llm_key and not llm_model: missing.append('STRIX_LLM (model name)')
        if llm_key and not llm_base and not os.environ.get('OPENAI_API_KEY'):
            missing.append('LLM_API_BASE (endpoint)')
        if free_ram < MIN_FREE_RAM_MB:
            missing.append(f'{MIN_FREE_RAM_MB}MB free RAM (host has {free_ram}MB)')
        return {
            'cli_installed': cli_ok,
            'cli_version': version,
            'cli_path': str(STRIX_BIN),
            'docker_available': docker_ok,
            'llm_configured': llm_key,
            'llm_model': llm_model,
            'llm_base_url': llm_base,
            'reasoning_effort': os.environ.get('STRIX_REASONING_EFFORT', 'high'),
            'free_ram_mb': free_ram,
            'ready': ready and bool(llm_model) and (bool(llm_base) or bool(os.environ.get('OPENAI_API_KEY'))) and free_ram >= MIN_FREE_RAM_MB,
            'message': (
                'Strix is ready' if (ready and llm_model and (llm_base or os.environ.get('OPENAI_API_KEY')) and free_ram >= MIN_FREE_RAM_MB)
                else 'Configure: ' + ', '.join(missing) if missing
                else 'Strix is ready'
            ),
        }

    # ── Scan Execution ──

    async def run_scan(self, scan_id: str, company_id: str, user_id: int,
                       targets: list[str], scan_mode: str = 'standard',
                       instruction: str = ''):
        """
        Execute a Strix AI pentest run end-to-end.

        Spawns the strix CLI in non-interactive mode, discovers the run
        directory, polls for findings, and ingests them into Centra's DB.
        Emits WebSocket events to subscribers of this scan_id.
        """
        STRIX_RUNS_DIR.mkdir(parents=True, exist_ok=True)
        existing_dirs = set(p.name for p in STRIX_RUNS_DIR.iterdir()) if STRIX_RUNS_DIR.exists() else set()

        cmd = [str(STRIX_BIN), '-n', '-m', scan_mode]
        for t in targets:
            cmd += ['-t', t]
        if instruction:
            cmd += ['--instruction', instruction]

        env = os.environ.copy()
        env['PYTHONUNBUFFERED'] = '1'

        await self.db.update_strix_scan(scan_id, status='running', started_at=time.time())
        await self._emit(scan_id, company_id, {
            'type': 'redteam_scan_started', 'scan_id': scan_id,
            'targets': targets, 'scan_mode': scan_mode,
        })
        await self.db.add_log(scan_id, company_id, 'info', None,
                              f'Red Team scan started: mode={scan_mode}, targets={targets}')

        proc = None
        run_dir = None
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(STRIX_RUNS_BASE),
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            self._active[scan_id] = proc

            # Discover the run directory (appears shortly after launch)
            run_dir = await self._discover_run_dir(existing_dirs, timeout=30.0)
            if run_dir:
                run_name = run_dir.name
                await self.db.update_strix_scan(
                    scan_id, run_name=run_name, run_dir=str(run_dir)
                )
                await self._emit(scan_id, company_id, {
                    'type': 'redteam_run_discovered', 'scan_id': scan_id,
                    'run_name': run_name,
                })
                logger.info(f'Red Team scan {scan_id} → run dir {run_name}')

            # Poll for findings + status until the process exits
            await self._poll_until_complete(scan_id, company_id, proc, run_dir)

        except asyncio.CancelledError:
            await self.db.update_strix_scan(
                scan_id, status='interrupted', finished_at=time.time()
            )
            await self._emit(scan_id, company_id, {
                'type': 'redteam_scan_cancelled', 'scan_id': scan_id,
            })
            raise
        except Exception as e:
            logger.error(f'Red Team scan {scan_id} error: {e}')
            await self.db.update_strix_scan(
                scan_id, status='failed', error_message=str(e), finished_at=time.time()
            )
            await self._emit(scan_id, company_id, {
                'type': 'redteam_scan_error', 'scan_id': scan_id, 'error': str(e),
            })
        finally:
            self._active.pop(scan_id, None)

    async def cancel_scan(self, scan_id: str, company_id: str):
        proc = self._active.get(scan_id)
        if proc and proc.returncode is None:
            try:
                proc.terminate()
            except ProcessLookupError:
                pass
            await self.db.update_strix_scan(
                scan_id, status='interrupted', finished_at=time.time()
            )
            await self.db.add_log(scan_id, company_id, 'warning', None, 'Red Team scan cancelled')

    # ── Internal helpers ──

    async def _discover_run_dir(self, existing: set, timeout: float) -> Path | None:
        """Wait for a new strix_runs/<name> directory to appear."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                current = set(p.name for p in STRIX_RUNS_DIR.iterdir() if p.is_dir())
            except Exception:
                current = set()
            new = current - existing
            if new:
                # Pick the most recently modified new dir
                candidates = [STRIX_RUNS_DIR / n for n in new]
                candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                return candidates[0]
            await asyncio.sleep(0.5)
        return None

    async def _poll_until_complete(self, scan_id: str, company_id: str,
                                   proc: asyncio.subprocess.Process,
                                   run_dir: Path | None):
        seen_finding_ids: set[str] = set()
        last_progress = 0.0

        # Reader task for stdout (keeps the pipe from blocking & logs output)
        stdout_lines: list[str] = []
        read_task = asyncio.create_task(self._read_stdout(proc, stdout_lines, scan_id, company_id))

        # Polling loop
        while proc.returncode is None:
            await asyncio.sleep(FINDING_POLL_INTERVAL)
            if run_dir:
                await self._ingest_findings(scan_id, company_id, run_dir, seen_finding_ids)
                progress = self._estimate_progress(run_dir, stdout_lines)
                if progress > last_progress:
                    last_progress = progress
                    await self.db.update_strix_scan(scan_id, progress=progress)
                    await self._emit(scan_id, company_id, {
                        'type': 'redteam_progress', 'scan_id': scan_id,
                        'progress': progress,
                    })

        # Process exited — wait for stdout reader to drain
        try:
            await asyncio.wait_for(read_task, timeout=5.0)
        except asyncio.TimeoutError:
            read_task.cancel()

        # Final ingestion
        if run_dir:
            await self._ingest_findings(scan_id, company_id, run_dir, seen_finding_ids)

        exit_code = proc.returncode
        # Strix exit codes: 0=clean, 2=vulns found, 1=error
        final_status = 'completed'
        if exit_code == 1:
            final_status = 'failed'
        elif exit_code == 2:
            final_status = 'completed'  # vulns found is still a successful scan

        # Read final run.json for timing + counts
        severity_counts = await self._read_final_counts(run_dir, scan_id)

        await self.db.update_strix_scan(
            scan_id, status=final_status, progress=100.0,
            exit_code=exit_code, finished_at=time.time(),
            total_findings=len(seen_finding_ids),
            severity_critical=severity_counts.get('critical', 0),
            severity_high=severity_counts.get('high', 0),
            severity_medium=severity_counts.get('medium', 0),
            severity_low=severity_counts.get('low', 0),
            severity_info=severity_counts.get('info', 0),
        )
        await self._emit(scan_id, company_id, {
            'type': 'redteam_scan_completed', 'scan_id': scan_id,
            'status': final_status, 'exit_code': exit_code,
            'total_findings': len(seen_finding_ids),
            'severity': severity_counts,
        })
        await self.db.add_log(scan_id, company_id, 'info', None,
                              f'Red Team scan {final_status} (exit={exit_code}): '
                              f'{len(seen_finding_ids)} findings')

    async def _read_stdout(self, proc, buf: list, scan_id: str, company_id: str):
        """Drain subprocess stdout, buffer it, and emit notable lines."""
        try:
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                text = line.decode('utf-8', errors='replace').rstrip()
                buf.append(text)
                # Emit agent-activity lines to the WebSocket (throttled by line rate)
                if text and not text.startswith('Pulling'):
                    await self._emit(scan_id, company_id, {
                        'type': 'redteam_log', 'scan_id': scan_id,
                        'line': text[:500],
                    })
        except Exception:
            pass

    async def _ingest_findings(self, scan_id: str, company_id: str,
                               run_dir: Path, seen: set):
        """Read vulnerabilities.json and ingest any new findings."""
        vuln_path = run_dir / 'vulnerabilities.json'
        if not vuln_path.exists():
            return
        try:
            raw = vuln_path.read_text(encoding='utf-8')
            vulns = json.loads(raw)
        except (json.JSONDecodeError, OSError):
            return
        if not isinstance(vulns, list):
            return

        new_rows = []
        for v in vulns:
            vid = v.get('id', '')
            if vid in seen:
                continue
            seen.add(vid)
            new_rows.append(self._map_finding(scan_id, company_id, v))

        if new_rows:
            await self.db.add_strix_findings_batch(new_rows)
            await self._emit(scan_id, company_id, {
                'type': 'redteam_findings', 'scan_id': scan_id,
                'new_count': len(new_rows), 'total': len(seen),
            })

    def _map_finding(self, scan_id: str, company_id: str, v: dict) -> tuple:
        """Map a Strix finding dict → Centra findings tuple."""
        title = v.get('title', 'Untitled finding')
        severity = (v.get('severity') or 'info').lower()
        cvss = float(v.get('cvss') or 0.0)
        target = v.get('target') or ''
        endpoint = v.get('endpoint') or ''
        port = 0
        if endpoint and ':' in endpoint:
            try:
                port = int(endpoint.rsplit(':', 1)[-1].split('/')[0])
            except (ValueError, IndexError):
                pass

        # Family = CWE or finding_class (dynamic/static/dependency)
        family = v.get('cwe') or v.get('finding_class') or 'AI Pentest'

        description = v.get('description') or ''
        if v.get('impact'):
            description = (description + '\n\nImpact: ' + v['impact']).strip()

        solution = v.get('remediation_steps') or ''

        # References: CVE + CWE
        refs = []
        if v.get('cve'):
            refs.append('https://nvd.nist.gov/vuln/detail/' + v['cve'])
        if v.get('cwe'):
            refs.append('https://cwe.mitre.org/data/definitions/' +
                        v['cwe'].replace('CWE-', '') + '.html')

        # Evidence: poc + evidence + code locations
        evidence_parts = []
        if v.get('evidence'):
            evidence_parts.append('Evidence: ' + v['evidence'])
        if v.get('poc_description'):
            evidence_parts.append('PoC: ' + v['poc_description'])
        if v.get('poc_script_code'):
            evidence_parts.append('PoC code:\n' + v['poc_script_code'])
        if v.get('technical_analysis'):
            evidence_parts.append('Analysis: ' + v['technical_analysis'])
        if v.get('code_locations'):
            for cl in v['code_locations']:
                loc = f"{cl.get('file','?')}:{cl.get('start_line','?')}"
                evidence_parts.append(f"Location: {loc} — {cl.get('label','')}")
                if cl.get('snippet'):
                    evidence_parts.append('  ' + str(cl['snippet'])[:200])
        evidence = '\n'.join(evidence_parts)

        return (
            scan_id, company_id, title, family, cvss, target, port,
            severity, description, solution, refs, evidence,
        )

    def _estimate_progress(self, run_dir: Path, stdout_lines: list) -> float:
        """Heuristic progress: based on run.json status + finding count."""
        run_json = run_dir / 'run.json'
        if run_json.exists():
            try:
                rd = json.loads(run_json.read_text())
                status = rd.get('status', '')
                if status in ('completed', 'stopped', 'failed', 'interrupted'):
                    return 100.0
                if status == 'running':
                    # Use LLM usage / turns as a rough proxy if available
                    usage = rd.get('llm_usage', {})
                    turns = usage.get('total_turns', 0) or usage.get('turns', 0)
                    if turns:
                        return min(95.0, 10.0 + turns * 2.0)
            except (json.JSONDecodeError, OSError):
                pass
        # Fall back to stdout line count as a very rough proxy
        if stdout_lines:
            return min(90.0, 5.0 + len(stdout_lines) * 0.3)
        return 5.0

    async def _read_final_counts(self, run_dir: Path | None, scan_id: str) -> dict:
        if not run_dir:
            return {}
        vuln_path = run_dir / 'vulnerabilities.json'
        if not vuln_path.exists():
            return {}
        try:
            vulns = json.loads(vuln_path.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
        counts = {'critical': 0, 'high': 0, 'medium': 0, 'low': 0, 'info': 0}
        for v in vulns:
            sev = (v.get('severity') or 'info').lower()
            if sev in counts:
                counts[sev] += 1
        return counts

    async def _emit(self, scan_id: str, company_id: str, message: dict):
        message['scan_id'] = scan_id
        await self.manager.send_to_scan(scan_id, message)
