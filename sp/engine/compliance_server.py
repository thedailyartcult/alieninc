"""
Centra — Compliance API Server
============================================
Serves the Legal Intelligence Dashboard and provides API endpoints
for running compliance scans and retrieving reports.

Usage:
    python3 compliance_server.py [--port 8722]
"""

import json
import sys
import sqlite3
import threading
from http.server import SimpleHTTPRequestHandler
from socketserver import ThreadingTCPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ENGINE_DIR = Path(__file__).resolve().parent
BASE_DIR = ENGINE_DIR.parent.parent

sys.path.insert(0, str(ENGINE_DIR))
from legal_intelligence import run_full_scan
from wat_runner import run_wat_scan
from scanners.audit_loader import list_audit_ids
from scanners.target_loader import load_targets, list_profiles, load_profile

# ── Scan state ─────────────────────────────────────────────────────────────────
scan_lock = threading.Lock()
scan_state = {
    "file_scan": {"running": False, "last_result": None, "last_error": None},
    "web_audit": {"running": False, "last_result": None, "last_error": None},
}


def run_scan_background(scan_type, profile="full_scan"):
    """Run a scan in a background thread so the API returns immediately."""
    with scan_lock:
        if scan_state[scan_type]["running"]:
            return False
        scan_state[scan_type]["running"] = True
        scan_state[scan_type]["last_error"] = None

    def _worker():
        try:
            if scan_type == "file_scan":
                result = run_full_scan(profile=profile)
            else:
                result = run_wat_scan()
            with scan_lock:
                scan_state[scan_type]["last_result"] = result
        except Exception as e:
            with scan_lock:
                scan_state[scan_type]["last_error"] = str(e)
                scan_state[scan_type]["last_result"] = {"error": str(e)}
        finally:
            with scan_lock:
                scan_state[scan_type]["running"] = False

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return True


class ReusableThreadingTCPServer(ThreadingTCPServer):
    allow_reuse_address = True


class ComplianceHandler(SimpleHTTPRequestHandler):
    """Handle API requests and serve static files."""

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # API: Get latest report
        if path == '/api/compliance/report':
            self.send_api_response(self.get_report())
            return

        # API: Get scan history
        if path == '/api/compliance/history':
            self.send_api_response(self.get_history())
            return

        # API: Get web audit report
        if path == '/api/compliance/web-audit/report':
            self.send_api_response(self.get_web_audit_report())
            return

        # API: Scan status
        if path == '/api/compliance/status':
            self.send_api_response(self.get_status())
            return

        # API: List available audits
        if path == '/api/compliance/audits':
            self.send_api_response(self.get_audits())
            return

        # API: List targets
        if path == '/api/compliance/targets':
            self.send_api_response(self.get_targets())
            return

        # API: List scan profiles
        if path == '/api/compliance/profiles':
            self.send_api_response(self.get_profiles())
            return

        # Serve static files
        if path == '/' or path == '/index.html':
            self.serve_file(ENGINE_DIR.parent.parent / 'trust' / 'index.html', 'text/html')
        elif path.startswith('/../') or path.startswith('/sp/'):
            rel = path.lstrip('/')
            full = BASE_DIR / rel
            if full.exists() and full.is_file():
                self.serve_file(full)
            else:
                self.send_error(404)
        else:
            local = ENGINE_DIR / path.lstrip('/')
            if local.exists() and local.is_file():
                self.serve_file(local)
            else:
                base = BASE_DIR / path.lstrip('/')
                if base.exists() and base.is_file():
                    self.serve_file(base)
                else:
                    self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # Parse query string for profile parameter
        qs = {}
        if parsed.query:
            from urllib.parse import parse_qs
            qs = {k: v[0] for k, v in parse_qs(parsed.query).items()}

        # API: Run file-based scan (non-blocking)
        if path == '/api/compliance/scan':
            profile = qs.get('profile', 'full_scan')
            started = run_scan_background("file_scan", profile)
            if started:
                self.send_api_response({"status": "started", "message": f"Scan started with profile '{profile}'"})
            else:
                self.send_api_response({"status": "already_running", "message": "Scan already in progress"})
            return

        # API: Run web audit (non-blocking)
        if path == '/api/compliance/web-audit':
            started = run_scan_background("web_audit")
            if started:
                self.send_api_response({"status": "started", "message": "Web audit started in background"})
            else:
                self.send_api_response({"status": "already_running", "message": "Web audit already in progress"})
            return

        self.send_error(404)

    def send_api_response(self, data, status=200):
        try:
            body = json.dumps(data, indent=2).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', len(body))
            self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass  # Client disconnected, nothing we can do

    def serve_file(self, filepath, content_type=None):
        if not filepath.exists():
            self.send_error(404)
            return

        if content_type is None:
            ext = filepath.suffix.lower()
            content_type = {
                '.html': 'text/html',
                '.css': 'text/css',
                '.js': 'application/javascript',
                '.json': 'application/json',
                '.png': 'image/png',
                '.jpg': 'image/jpeg',
                '.svg': 'image/svg+xml',
                '.ico': 'image/x-icon',
            }.get(ext, 'application/octet-stream')

        try:
            content = filepath.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', len(content))
            self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
            self.end_headers()
            self.wfile.write(content)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def get_report(self):
        try:
            report_path = ENGINE_DIR / 'latest_report.json'
            if report_path.exists():
                with open(report_path) as f:
                    return json.load(f)
            return {"error": "No report available. Run a scan first."}
        except Exception as e:
            return {"error": str(e)}

    def get_history(self):
        try:
            conn = sqlite3.connect(str(ENGINE_DIR / "compliance.db"))
            rows = conn.execute("""
                SELECT scan_date, company_id, rule_id, status, severity
                FROM scans ORDER BY scan_date DESC LIMIT 500
            """).fetchall()
            conn.close()
            return {"history": [{"date": r[0], "company": r[1], "rule": r[2], "status": r[3], "severity": r[4]} for r in rows]}
        except Exception as e:
            return {"error": str(e)}

    def get_web_audit_report(self):
        return {"web_audits": [], "message": "Web audit engine not loaded."}

    def get_status(self):
        with scan_lock:
            return {
                "file_scan": {
                    "running": scan_state["file_scan"]["running"],
                    "has_error": scan_state["file_scan"]["last_error"] is not None,
                    "last_error": scan_state["file_scan"]["last_error"],
                },
                "web_audit": {
                    "running": scan_state["web_audit"]["running"],
                    "has_error": scan_state["web_audit"]["last_error"] is not None,
                    "last_error": scan_state["web_audit"]["last_error"],
                },
            }

    def get_audits(self):
        try:
            audits = list_audit_ids()
            return {"audits": audits}
        except Exception as e:
            return {"error": str(e)}

    def get_targets(self):
        try:
            targets = load_targets()
            return {
                "targets": [
                    {"id": t["id"], "name": t["name"], "type": t["type"], "path": t["path"]}
                    for t in targets
                ]
            }
        except Exception as e:
            return {"error": str(e)}

    def get_profiles(self):
        try:
            profiles = list_profiles()
            return {"profiles": profiles}
        except Exception as e:
            return {"error": str(e)}

    def log_message(self, format, *args):
        pass  # Quiet logging — use stderr for errors only


def main():
    port = 8722
    if '--port' in sys.argv:
        idx = sys.argv.index('--port')
        port = int(sys.argv[idx + 1])

    server = ReusableThreadingTCPServer(('0.0.0.0', port), ComplianceHandler)
    server.daemon_threads = True

    print(f"Centra — Compliance API")
    print(f"Listening on http://0.0.0.0:{port}")
    print(f"Dashboard: http://localhost:{port}/")
    print(f"API: http://localhost:{port}/api/compliance/report")
    print(f"Threading: enabled (non-blocking scans)")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()


if __name__ == "__main__":
    main()
