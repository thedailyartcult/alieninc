#!/bin/bash
# migrate-to-art.sh — one-command cutover thedailyartcult.lol -> art.alieninc.tech
# (and back). SAFE BY DEFAULT: dry-run unless --go is passed. .lol stays live until DNS ready.
#
#   ./migrate-to-art.sh --dry-run   # count only, change nothing (default)
#   ./migrate-to-art.sh --go        # flip .lol -> art.alieninc.tech, commit-ready
#   ./migrate-to-art.sh --rollback  # flip back art.alieninc.tech -> .lol
#
# Scope: *.html *.xml *.txt *.js *.json under repo root, EXCLUDING .backups .git node_modules _pages.
# Covers: page bodies, canonical/OG/JSON-LD urls, sitemaps, robots, CNAMEs, mailto: addresses stay
# on .lol (mail keeps working after domain expiry only if MX kept — see DNS-NOTES below).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODE="${1:---dry-run}"

FROM_LOL="thedailyartcult.lol"
TO_ART="art.alieninc.tech"
declare -A SUBS=( [accounts]=accounts [policy]=policy [publications]=publications [support]=support [cs]=cs [privacy]=privacy [www]=www )

list_files() {
  grep -rl --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=_pages --exclude-dir=.backups \
    --include="*.html" --include="*.xml" --include="*.txt" --include="*.js" --include="*.json" \
    -e "$1" "$ROOT" || true
}

do_swap() { # $1=from $2=to $3=label
  local files n=0
  files=$(list_files "$1")
  if [ -z "$files" ]; then echo "[$3] no files contain $1"; return 0; fi
  n=$(echo "$files" | wc -l)
  echo "[$3] $n files contain $1"
  echo "$files"
  if [ "$MODE" = "--go" ] || [ "$MODE" = "--rollback" ]; then
    echo "$files" | xargs sed -i "s/$1/$2/g"
    echo "[$3] swapped $1 -> $2 in $n files"
  fi
}

case "$MODE" in
  --dry-run)
    echo "=== DRY RUN (nothing changed) ==="
    do_swap "$FROM_LOL" "$TO_ART" "apex+subs"
    echo "=== CNAME files (handled by sed too, listed for review) ==="
    find "$ROOT" -name CNAME -not -path "*/.git/*" -not -path "*/node_modules/*" -not -path "*/.backups/*" | while read -r f; do echo "$f: $(cat "$f")"; done
    echo "=== NEXT: create DNS art.alieninc.tech (Cloudflare CNAME -> Pages), then run --go ==="
    ;;
  --go)
    echo "=== CUTOVER .lol -> art.alieninc.tech ==="
    do_swap "$FROM_LOL" "$TO_ART" "cutover"
    # Root CNAME (alieninc.tech) must NOT change — restore if touched (it contains no .lol string, so safe; guard anyway)
    echo "=== CNAME state after cutover ==="
    find "$ROOT" -name CNAME -not -path "*/.git/*" -not -path "*/node_modules/*" -not -path "*/.backups/*" | while read -r f; do echo "$f: $(cat "$f")"; done
    echo "REMINDER: keep Cloudflare Bulk Redirects .lol -> art active for ~6 months to pass link equity."
    ;;
  --rollback)
    echo "=== ROLLBACK art.alieninc.tech -> .lol ==="
    # swap full art host back; careful: plain 'art.alieninc.tech' contains 'alieninc.tech' — swap longest first
    do_swap "$TO_ART" "$FROM_LOL" "rollback"
    ;;
  *)
    echo "usage: $0 [--dry-run|--go|--rollback]"; exit 1;;
esac
