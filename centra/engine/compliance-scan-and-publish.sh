#!/usr/bin/env bash
#
# compliance-scan-and-publish.sh
# ------------------------------
# Runs the Centra compliance scan and publishes the refreshed public posture so
# the alieninc.tech dashboard (GitHub Pages, static) shows a current scan date.
#
# The dashboard reads /data/compliance/latest_report.json from Pages, so the
# regenerated file must be committed and pushed — regenerating locally alone
# would not update the live site. This script does both.
#
# Invoked by the user systemd timer centra-compliance.timer (every 6h).
set -euo pipefail

REPO="/home/tablet/alieninc"
ENGINE="$REPO/centra/engine"
REPORT="data/compliance/latest_report.json"

export GIT_TERMINAL_PROMPT=0

# Serialise runs so a slow scan can't overlap the next tick.
exec 9>"$REPO/.compliance-scan.lock"
if ! flock -n 9; then
    echo "Another compliance scan is already running; skipping."
    exit 0
fi

cd "$ENGINE"
echo "[$(date -u +%FT%TZ)] Running Centra compliance scan..."
python3 compliance_report.py

cd "$REPO"
if git diff --quiet -- "$REPORT"; then
    echo "[$(date -u +%FT%TZ)] Compliance report unchanged; nothing to publish."
    exit 0
fi

git add -- "$REPORT"
git commit -q -m "chore(compliance): refresh scan posture $(date -u +%FT%TZ)" -- "$REPORT"

# Integrate any commits pushed meanwhile, then publish.
git fetch -q origin master
if ! git merge-base --is-ancestor origin/master HEAD; then
    git -c rebase.autostash=true rebase -q origin/master
fi
git push -q origin master

echo "[$(date -u +%FT%TZ)] Published compliance posture."
