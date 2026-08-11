#!/bin/bash
# Panteon Connectors — cron entry point
# Run this from cron every 6 hours to auto-ingest subsidiary data.
#
# Usage:
#   ./connectors/pull_all.sh
#
# Make sure GITHUB_TOKEN, JIRA_EMAIL, JIRA_TOKEN are set in the environment
# (or in a .env sourced before this script).

set -e
cd "$(dirname "$0")/.."
DIR="$(dirname "$0")"
LOG="/tmp/panteon-connector.log"

echo "[$(date)] Panteon Connector Run" >> "$LOG"

# GitHub — for each company that has repos configured
if [ -n "$GITHUB_TOKEN" ]; then
  for company in panteon kmt immanuel sp tdac; do
    python3 "$DIR/github_connector.py" --company "$company" 2>&1 | tee -a "$LOG"
  done
else
  echo "[pull_all] GITHUB_TOKEN not set, skipping GitHub" >> "$LOG"
fi

# Jira — for each company that has a Jira URL configured
if [ -n "$JIRA_EMAIL" ] && [ -n "$JIRA_TOKEN" ]; then
  for company in panteon kmt immanuel sp tdac; do
    python3 "$DIR/jira_connector.py" --company "$company" 2>&1 | tee -a "$LOG"
  done
else
  echo "[pull_all] JIRA_EMAIL/JIRA_TOKEN not set, skipping Jira" >> "$LOG"
fi

echo "[$(date)] Panteon Connector Run Complete" >> "$LOG"
