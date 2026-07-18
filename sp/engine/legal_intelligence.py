#!/usr/bin/env python3
"""
Statute & Precedent — Compliance Scanner
Audit-driven engine. Reads .audit.json policy files and targets.json.
Each audit item executes via a check engine. Zero hardcoded rules.
"""

import json
import sqlite3
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path
from scanners.audit_loader import get_all_items, compute_framework_scores, compute_weighted_security_score, get_framework_map, list_audit_ids
from scanners.target_loader import load_targets
from scanners.check_engines import execute

ENGINE_DIR = Path(__file__).parent
BASE_DIR = ENGINE_DIR.parent.parent
DB_PATH = ENGINE_DIR / "compliance.db"


def init_db():
    c = sqlite3.connect(str(DB_PATH))
    c.executescript("""
        CREATE TABLE IF NOT EXISTS scans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_date TEXT NOT NULL, company_id TEXT NOT NULL,
            rule_id TEXT NOT NULL, check_id TEXT, audit_id TEXT,
            status TEXT NOT NULL, details TEXT, severity TEXT, score INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS audit_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_date TEXT NOT NULL, company_id TEXT NOT NULL,
            audit_id TEXT NOT NULL, audit_name TEXT NOT NULL, framework_id TEXT,
            check_count INTEGER DEFAULT 0, passed_count INTEGER DEFAULT 0,
            failed_count INTEGER DEFAULT 0, score INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_date TEXT NOT NULL, company_id TEXT NOT NULL,
            severity TEXT NOT NULL, message TEXT NOT NULL, resolved INTEGER DEFAULT 0
        );
    """)
    c.commit()
    return c


def scan_target(target, audit_items, c, now):
    base_path = target["base_path"]
    exclude_dirs = set(target.get("exclude", []))
    audit_totals = {}

    for item in audit_items:
        result = execute(base_path, exclude_dirs, item)
        aid = item.get("_audit_id", "unknown")
        fid = item.get("_framework_id", aid)

        c.execute("""INSERT INTO scans (scan_date, company_id, rule_id, check_id, audit_id, status, details, severity, score)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (now, target["id"], item["id"] + "-" + aid, item["id"], aid,
             result["status"], result["detail"], item.get("severity", "high"), result["score"]))

        # Track per-audit
        if aid not in audit_totals:
            audit_totals[aid] = {"name": item.get("_audit_name", aid), "framework_id": fid, "checks": 0, "passed": 0, "failed": 0}
        audit_totals[aid]["checks"] += 1
        if result["status"] == "pass":
            audit_totals[aid]["passed"] += 1
        else:
            audit_totals[aid]["failed"] += 1

        # Alerts
        if result["status"] == "fail" and item.get("severity", "high") in ("critical", "high"):
            reg = item.get("regulation", "")
            c.execute("""INSERT INTO alerts (alert_date, company_id, severity, message)
                VALUES (?,?,?,?)""", (now, target["id"], item["severity"],
                f"{target['name']}: {item.get('description', item['id'])} — {result['detail']} [{reg}]"))

    for aid, stats in audit_totals.items():
        total = stats["checks"]
        pct = int((stats["passed"] / total * 100)) if total > 0 else 0
        c.execute("""INSERT INTO audit_files (scan_date, company_id, audit_id, audit_name, framework_id, check_count, passed_count, failed_count, score)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (now, target["id"], aid, stats["name"], stats["framework_id"], total, stats["passed"], stats["failed"], pct))


def compliance_summary(cursor, fw_metadata):
    summary = {}
    for target in load_targets():
        tid = target["id"]
        cursor.execute("""SELECT check_id, status, severity, score, audit_id, rule_id
            FROM scans WHERE company_id = ? AND scan_date = (SELECT MAX(scan_date) FROM scans WHERE company_id = ?)""",
            (tid, tid))
        rows = cursor.fetchall()
        if not rows:
            continue

        total = len(rows)
        passed = sum(1 for r in rows if r[1] == "pass")

        # Framework scores
        fw_results = []
        fw_totals = {}
        for r in rows:
            aid = r[4]
            fid = "gdpr" if "gdpr" in aid or aid == "ip_trademark" else ("ip" if aid == "ip_trademark" else aid.replace("_nginx", "").replace("_stig_web", "").replace("_v4", "").replace("_asvs_l1", "").replace("_observatory", ""))
            fw_results.append({"_framework_id": fid, "status": r[1], "score": r[3]})
            if fid not in fw_totals:
                fw_totals[fid] = {"passed": 0, "failed": 0, "total": 0}
            fw_totals[fid]["total"] += 1
            if r[1] == "pass":
                fw_totals[fid]["passed"] += 1
            else:
                fw_totals[fid]["failed"] += 1

        framework_scores = {}
        for fid, data in fw_totals.items():
            t = data["total"]
            pct = int((data["passed"] / t * 100)) if t > 0 else 0
            meta = fw_metadata.get(fid, {})
            framework_scores[fid] = {"name": meta.get("name", fid), "version": meta.get("version", ""),
                "score": pct, "passed": data["passed"], "failed": data["failed"],
                "total": t, "weight": meta.get("weight", 0.2)}

        security_score = compute_weighted_security_score(framework_scores, fw_metadata)
        realistic_score = int(security_score * 0.40 + (int((passed / total * 100)) if total > 0 else 0) * 0.60)

        # Risk
        severity_weight = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}
        actual_risk = sum(severity_weight.get(r[2], 1) for r in rows if r[1] == "fail")
        theoretical_max = total * 4
        risk_score = min(100, int((actual_risk / theoretical_max) * 100)) if theoretical_max > 0 else 0

        active_risks = list({(r[5].split("-" + aid)[0] if "-" + aid in r[5] else r[5], r[2], r[2]) for r in rows if r[1] == "fail"})
        active_risks = [{"rule": a[0] if len(a) > 0 else "unknown", "severity": a[1] if len(a) > 1 else "high", "detail": ""} for a in active_risks[:5]]

        summary[tid] = {
            "name": target["name"], "type": target["type"],
            "total_checks": total, "passed": passed, "failed": total - passed,
            "baseline_score": int((passed / total * 100)) if total > 0 else 0,
            "realistic_score": realistic_score,
            "art13_score": framework_scores.get("gdpr", {}).get("score", 0),
            "depth_score": framework_scores.get("gdpr", {}).get("score", 0),
            "security_score": security_score,
            "framework_scores": framework_scores,
            "risk_score": risk_score,
            "active_risks": active_risks,
        }
    return summary


def generate_report(cursor):
    fw_metadata = get_framework_map(list_audit_ids())
    summary = compliance_summary(cursor, fw_metadata)

    cursor.execute("""SELECT alert_date, company_id, severity, message, resolved FROM alerts
        WHERE resolved = 0 ORDER BY alert_date DESC LIMIT 50""")
    alerts = [{"date": r[0], "company": r[1], "severity": r[2], "message": r[3], "resolved": r[4]} for r in cursor.fetchall()]

    critical_count = sum(1 for a in alerts if a["severity"] == "critical")
    high_count = sum(1 for a in alerts if a["severity"] == "high")

    total = len(summary)
    baseline_compliant = sum(1 for s in summary.values() if s["baseline_score"] >= 80)
    realistic_compliant = sum(1 for s in summary.values() if s["realistic_score"] >= 60)

    # Aggregate frameworks
    all_fw = {}
    for cdata in summary.values():
        for fid, fdata in cdata.get("framework_scores", {}).items():
            if fid not in all_fw:
                all_fw[fid] = {"name": fdata["name"], "total_score": 0, "count": 0}
            all_fw[fid]["total_score"] += fdata["score"]
            all_fw[fid]["count"] += 1
    agg_fw = {fid: {"name": d["name"], "score": int(d["total_score"] / d["count"]) if d["count"] > 0 else 0} for fid, d in all_fw.items()}

    # Audit breakdown
    cursor.execute("""SELECT af.company_id, af.audit_id, af.audit_name, af.framework_id, af.check_count, af.passed_count, af.failed_count, af.score
        FROM audit_files af INNER JOIN (SELECT company_id, MAX(scan_date) as max_date FROM audit_files GROUP BY company_id) latest
        ON af.company_id = latest.company_id AND af.scan_date = latest.max_date ORDER BY af.company_id, af.audit_id""")
    audit_breakdown = {}
    for row in cursor:
        cid = row[0]
        audit_breakdown.setdefault(cid, []).append({"audit_id": row[1], "audit_name": row[2], "framework_id": row[3],
            "check_count": row[4], "passed_count": row[5], "failed_count": row[6], "score": row[7]})

    return {
        "report_date": datetime.now().isoformat(),
        "overall": {
            "total_companies": total, "baseline_compliant": baseline_compliant,
            "baseline_rate": int(baseline_compliant / total * 100) if total > 0 else 0,
            "realistic_compliant": realistic_compliant,
            "realistic_rate": int(realistic_compliant / total * 100) if total > 0 else 0,
            "critical_alerts": critical_count, "high_alerts": high_count,
            "security_frameworks": agg_fw,
        },
        "companies": summary,
        "audits": audit_breakdown,
        "alerts": alerts,
    }


def run_full_scan(profile="full_scan"):
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS scans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_date TEXT NOT NULL, company_id TEXT NOT NULL,
            rule_id TEXT NOT NULL, check_id TEXT, audit_id TEXT,
            status TEXT NOT NULL, details TEXT, severity TEXT, score INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS audit_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_date TEXT NOT NULL, company_id TEXT NOT NULL,
            audit_id TEXT NOT NULL, audit_name TEXT NOT NULL, framework_id TEXT,
            check_count INTEGER DEFAULT 0, passed_count INTEGER DEFAULT 0,
            failed_count INTEGER DEFAULT 0, score INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_date TEXT NOT NULL, company_id TEXT NOT NULL,
            severity TEXT NOT NULL, message TEXT NOT NULL, resolved INTEGER DEFAULT 0
        );
    """)
    c.connection.commit()

    from scanners.target_loader import load_profile
    audit_ids = load_profile(profile)
    items = get_all_items(audit_ids)
    targets = load_targets()
    now = datetime.now().isoformat()

    for target in targets:
        print(f"Scanning {target['name']}...")
        scan_target(target, items, c, now)

    # ── Inline HTTP checks (CIS) — fetch headers via urllib, no WAT dependency ─
    from scanners.check_engines.http_verify import HTTP_CHECKS, run as run_http_check
    for target in targets:
        http_items = []
        try:
            req = urllib.request.Request(target['url'], headers={
                'User-Agent': 'AlienInc-Compliance/1.0',
                'X-AlienInc-Audit': 'statute',
            })
            resp = urllib.request.urlopen(req, timeout=10)
            resp_headers = {k.lower(): v for k, v in dict(resp.headers).items()}
            https_info = {'https_support': target['url'].startswith('https')}
        except Exception as e:
            resp_headers = {}
            https_info = {'https_support': False}

        for check_id in HTTP_CHECKS:
            try:
                result = run_http_check(resp_headers, https_info, check_id)
            except Exception as e:
                result = {"status": "error", "detail": str(e), "score": 50}

            c.execute("""INSERT INTO scans (scan_date, company_id, rule_id, check_id, audit_id, status, details, severity, score)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (now, target['id'], check_id + "-cis_nginx_v3_0", check_id, "cis_nginx_v3_0",
                 result['status'], result['detail'], "high", result['score']))

            if result['status'] == 'pass':
                http_items.append((check_id, True))
            else:
                http_items.append((check_id, False))

        # Store CIS HTTP audit summary
        passed = sum(1 for _, ok in http_items if ok)
        total = len(http_items)
        pct = int((passed / total * 100)) if total > 0 else 0
        c.execute("""INSERT INTO audit_files (scan_date, company_id, audit_id, audit_name, framework_id, check_count, passed_count, failed_count, score)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (now, target['id'], "cis_nginx_v3_0", "CIS NGINX Benchmark v3.0.0", "cis", total, passed, total - passed, pct))
        print(f"  CIS HTTP: {passed}/{total} passed ({pct}%)")

    # ── NIST 800-53 + CSF 2.0 cross-referencing (Nessus-style reporting layer) ─
    from scanners.audit_loader import load_audit
    for audit_id in ["nist_800_53_moderate", "nist_csf_2_0"]:
        try:
            nist_audit = load_audit(audit_id)
        except Exception:
            continue
        nist_name = nist_audit.get("name", audit_id)
        fw_id = nist_audit.get("framework", {}).get("id", audit_id)

        for target in targets:
            nist_passed = 0
            nist_failed = 0
            for group in nist_audit.get("group_policies", []):
                for item in group.get("items", []):
                    children = item.get("covered_by", [])
                    if not children:
                        c.execute("""INSERT INTO scans (scan_date, company_id, rule_id, check_id, audit_id, status, details, severity, score)
                            VALUES (?,?,?,?,?,?,?,?,?)""",
                            (now, target['id'], item['id'] + "-" + audit_id, item['id'], audit_id,
                             "warn", "Not assessed — no parent benchmark data available", item.get('severity', 'medium'), 0))
                        nist_failed += 1
                        continue

                    pass_count = 0
                    for child in children:
                        c.execute("""SELECT status FROM scans WHERE company_id=? AND check_id=?
                            AND scan_date=(SELECT MAX(scan_date) FROM scans WHERE company_id=? AND check_id=?)""",
                            (target['id'], child['check'], target['id'], child['check']))
                        row = c.fetchone()
                        if row and row[0] == 'pass':
                            pass_count += 1

                    total_children = len(children)
                    pct = int((pass_count / total_children * 100)) if total_children > 0 else 0
                    status = "pass" if pct >= 70 else ("warn" if pct >= 40 else "fail")
                    detail = "{} / {} parent checks passing ({}%)".format(pass_count, total_children, pct)

                    c.execute("""INSERT INTO scans (scan_date, company_id, rule_id, check_id, audit_id, status, details, severity, score)
                        VALUES (?,?,?,?,?,?,?,?,?)""",
                        (now, target['id'], item['id'] + "-" + audit_id, item['id'], audit_id,
                         status, detail, item.get('severity', 'medium'), pct))

                    if status == "pass":
                        nist_passed += 1
                    else:
                        nist_failed += 1

            nist_total = nist_passed + nist_failed
            nist_pct = int((nist_passed / nist_total * 100)) if nist_total > 0 else 0
            c.execute("""INSERT INTO audit_files (scan_date, company_id, audit_id, audit_name, framework_id, check_count, passed_count, failed_count, score)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (now, target['id'], audit_id, nist_name, fw_id, nist_total, nist_passed, nist_failed, nist_pct))

    c.connection.commit()
    report = generate_report(c)
    c.connection.close()

    report_path = ENGINE_DIR / "latest_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    print(f"\nScan complete — {report_path}")
    print(f"Compliance: {report['overall']['baseline_rate']}% baseline / {report['overall']['realistic_rate']}% realistic")
    print(f"Alerts: {report['overall']['critical_alerts']} critical / {report['overall']['high_alerts']} high")
    return report


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--profile", default="full_scan", choices=["full_scan", "security_only", "gdpr_only"])
    run_full_scan(profile=p.parse_args().profile)
