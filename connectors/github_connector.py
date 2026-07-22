"""
Panteon GitHub Connector
Pulls recent commits from subsidiary GitHub organizations/accounts
and ingests them into the Panteon data pipeline.

Usage:
    python3 connectors/github_connector.py [--company panteon] [--source-id panteon-github]
    python3 connectors/github_connector.py --list-repos

Requires GITHUB_TOKEN env var or --token argument.
Set PANTEON_API_URL (default: http://localhost:8080) for remote use.
"""

import json
import os
import sys
import urllib.request
import urllib.parse
import argparse
from datetime import datetime, timezone

PANTEON_API_URL = os.environ.get('PANTEON_API_URL', 'http://localhost:8080')

# Map company IDs to their GitHub orgs or known account names
COMPANY_REPOS = {
    "panteon": [],
    "kmt": [],
    "immanuel": [],
    "sp": [],
    "tdac": [],
    "immanuel": [],
    "alcantara": [],
}


def fetch_repo_commits(token, repo_full_name, since=None):
    """Fetch recent commits from a GitHub repo."""
    url = "https://api.github.com/repos/%s/commits?per_page=25" % repo_full_name
    if since:
        url += "&since=" + urllib.parse.quote(since)
    req = urllib.request.Request(url, headers={
        "Authorization": "token " + token,
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Panteon-Connector/1.0",
    })
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        sys.stderr.write("[github] HTTP %d for %s: %s\n" % (e.code, repo_full_name, e.read().decode()[:200]))
        return []
    except Exception as e:
        sys.stderr.write("[github] Error fetching %s: %s\n" % (repo_full_name, e))
        return []


def commit_to_payload(commit, repo_name):
    """Convert a GitHub API commit to Panteon ingest format."""
    author = commit.get("commit", {}).get("author", {}).get("name", "unknown")
    sha = commit.get("sha", "")
    message = commit.get("commit", {}).get("message", "")
    timestamp = commit.get("commit", {}).get("author", {}).get("date", "")
    files = [f.get("filename", f.get("name", "unknown")) for f in commit.get("files", [])]

    return {
        "repo": repo_name,
        "author": author,
        "branch": "main",
        "sha": sha,
        "commit_message": message[:500],
        "timestamp": timestamp,
        "files": files[:10],
    }


def pull_and_ingest(token, company_id, source_id, since=None):
    """Pull commits for a company's repos and ingest into Panteon."""
    repos = COMPANY_REPOS.get(company_id, [])
    if not repos:
        sys.stderr.write("[github] No repos configured for %s. Edit COMPANY_REPOS in the connector.\n" % company_id)
        return 0

    all_records = []
    for repo in repos:
        commits = fetch_repo_commits(token, repo, since)
        for c in commits:
            all_records.append(commit_to_payload(c, repo))
        sys.stderr.write("[github] %s: fetched %d commits from %s\n" % (company_id, len(commits), repo))

    if not all_records:
        return 0

    # Ingest via Panteon API
    payload = json.dumps({
        "source_id": source_id,
        "company_id": company_id,
        "data_type": "github_commit",
        "records": all_records,
    }).encode('utf-8')

    url = PANTEON_API_URL.rstrip('/') + '/api/panteon/ingest'
    req = urllib.request.Request(url, data=payload, headers={
        "Content-Type": "application/json",
        "Host": "panteon.alieninc.tech",
    })
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        result = json.loads(resp.read().decode())
        sys.stderr.write("[github] Ingested %d commits: %s\n" % (len(all_records), result.get("status", "ok")))
        return len(all_records)
    except Exception as e:
        sys.stderr.write("[github] Ingest failed: %s\n" % e)
        return 0


def main():
    parser = argparse.ArgumentParser(description="Panteon GitHub Connector")
    parser.add_argument("--company", default="panteon", help="Company ID to pull repos for")
    parser.add_argument("--source-id", default=None, help="Data source ID (default: {company}-github)")
    parser.add_argument("--since", help="ISO datetime to fetch commits since")
    parser.add_argument("--token", help="GitHub personal access token (default: GITHUB_TOKEN env)")
    parser.add_argument("--list-repos", action="store_true", help="List configured repos and exit")
    args = parser.parse_args()

    token = args.token or os.environ.get("GITHUB_TOKEN")
    if not token and not args.list_repos:
        sys.stderr.write("ERROR: GITHUB_TOKEN required. Set env var or pass --token.\n")
        sys.exit(1)

    if args.list_repos:
        print("Configured repositories:")
        for company, repos in COMPANY_REPOS.items():
            if repos:
                print("  %s:" % company)
                for r in repos:
                    print("    - %s" % r)
            else:
                print("  %s: (none configured)" % company)
        sys.exit(0)

    source_id = args.source_id or ("%s-github" % args.company)
    pulled = pull_and_ingest(token, args.company, source_id, since=args.since)
    sys.stderr.write("[github] Done. Total commits ingested: %d\n" % pulled)


if __name__ == "__main__":
    main()
