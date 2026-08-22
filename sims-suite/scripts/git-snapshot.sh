#!/bin/bash
# Nightly checkpoint of high-churn sims-suite runtime state files.
#
# These files mutate every few seconds while simulations run, so they carry
# the git skip-worktree flag: routine "git add -A" commits ignore them. This
# job lifts the flag once per day, records exactly one checkpoint commit,
# restores the flag, and pushes — giving clean daily history without churn.
set -euo pipefail
exec 9>/run/sims-state-snapshot.lock
flock -n 9 || exit 0
cd /home/alieninc

FILES=(
  sims-suite/api/.sim_count.json
  sims-suite/api/.sim_events.jsonl
  sims-suite/engines/kriegspiel/analytics_data/research_log.jsonl
  sims-suite/engines/kriegspiel/analytics_data/research_state.json
)

git update-index --no-skip-worktree -- "${FILES[@]}"
trap 'git update-index --skip-worktree -- "${FILES[@]}"' EXIT

git add -- "${FILES[@]}"
git diff --cached --quiet && exit 0

git commit -m "snapshot(sims-suite): nightly state checkpoint $(date '+%F')"
git push origin master || echo "[snapshot] WARN: push failed; commit kept local"
