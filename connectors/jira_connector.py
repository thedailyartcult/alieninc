"""
Panteon Jira Connector
Pulls recent tickets/issues from subsidiary Jira instances
and ingests them into the Panteon data pipeline.

Usage:
    python3 connectors/jira_connector.py --company panteon --jira-url https://panteon.atlassian.net
    python3 connectors/jira_connector.py --list-projects

Requires JIRA_EMAIL and JIRA_TOKEN env vars (or --email / --token).
Set PANTEON_API_URL (default: http://localhost:8080) for remote use.
"""

import json
import os
import sys
import urllib.request
import urllib.parse
import base64
import argparse

PANTEON_API_URL = os.environ.get('PANTEON_API_URL', 'http://localhost:8080')

COMPANY_JIRA = {
    "panteon": "",
    "kmt": "",
    "immanuel": "",
    "sp": "",
    "tdac": "",
    "alcantara": "",
}


def jira_request(url, auth_header):
    req = urllib.request.Request(url, headers={
        "Authorization": auth_header,
        "Accept": "application/json",
        "User-Agent": "Panteon-Connector/1.0",
    })
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        sys.stderr.write("[jira] HTTP %d: %s\n" % (e.code, e.read().decode()[:200]))
        return None
    except Exception as e:
        sys.stderr.write("[jira] Error: %s\n" % e)
        return None


def fetch_recent_issues(jira_url, auth_header, max_results=50):
    jql = "created >= -7d ORDER BY created DESC"
    query = urllib.parse.urlencode({"jql": jql, "maxResults": max_results, "fields": "summary,status,priority,assignee,project,labels,created"})
    return jira_request(jira_url.rstrip('/') + "/rest/api/3/search?" + query, auth_header)


def issue_to_payload(issue):
    fields = issue.get("fields", {})
    project = (fields.get("project") or {}).get("name", "unknown")
    return {
        "key": issue.get("key", "UNKNOWN"),
        "project": project,
        "summary": (fields.get("summary") or ""),
        "status": (fields.get("status") or {}).get("name", "open"),
        "priority": (fields.get("priority") or {}).get("name", "medium"),
        "assignee": (fields.get("assignee") or {}).get("displayName", "unassigned"),
        "labels": fields.get("labels", []),
        "created": fields.get("created", ""),
    }


def pull_and_ingest(jira_url, auth_header, company_id, source_id):
    data = fetch_recent_issues(jira_url, auth_header)
    if not data or "issues" not in data:
        sys.stderr.write("[jira] No issues returned for %s\n" % company_id)
        return 0

    records = [issue_to_payload(i) for i in data["issues"]]
    if not records:
        return 0

    payload = json.dumps({
        "source_id": source_id,
        "company_id": company_id,
        "data_type": "jira_ticket",
        "records": records,
    }).encode('utf-8')

    url = PANTEON_API_URL.rstrip('/') + '/api/panteon/ingest'
    req = urllib.request.Request(url, data=payload, headers={
        "Content-Type": "application/json",
        "Host": "panteon.alieninc.tech",
    })
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        result = json.loads(resp.read().decode())
        sys.stderr.write("[jira] Ingested %d issues: %s\n" % (len(records), result.get("status", "ok")))
        return len(records)
    except Exception as e:
        sys.stderr.write("[jira] Ingest failed: %s\n" % e)
        return 0


def main():
    parser = argparse.ArgumentParser(description="Panteon Jira Connector")
    parser.add_argument("--company", default="panteon", help="Company ID")
    parser.add_argument("--jira-url", help="Jira instance base URL")
    parser.add_argument("--source-id", default=None, help="Data source ID (default: {company}-jira)")
    parser.add_argument("--email", help="Jira account email (default: JIRA_EMAIL env)")
    parser.add_argument("--token", help="Jira API token (default: JIRA_TOKEN env)")
    parser.add_argument("--list-projects", action="store_true", help="Show configured Jira URLs")
    args = parser.parse_args()

    email = args.email or os.environ.get("JIRA_EMAIL")
    token = args.token or os.environ.get("JIRA_TOKEN")
    if (not email or not token) and not args.list_projects:
        sys.stderr.write("ERROR: JIRA_EMAIL and JIRA_TOKEN required.\n")
        sys.exit(1)

    if args.list_projects:
        print("Configured Jira instances:")
        for company, url in COMPANY_JIRA.items():
            print("  %s: %s" % (company, url or "(not configured)"))
        sys.exit(0)

    jira_url = args.jira_url or COMPANY_JIRA.get(args.company, "")
    if not jira_url:
        sys.stderr.write("ERROR: No Jira URL for %s. Set --jira-url or edit COMPANY_JIRA.\n" % args.company)
        sys.exit(1)

    auth = base64.b64encode(("%s:%s" % (email, token)).encode()).decode()
    auth_header = "Basic " + auth
    source_id = args.source_id or ("%s-jira" % args.company)
    pulled = pull_and_ingest(jira_url, auth_header, args.company, source_id)
    sys.stderr.write("[jira] Done. Total issues ingested: %d\n" % pulled)


if __name__ == "__main__":
    main()
