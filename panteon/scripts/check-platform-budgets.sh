#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
SHELL_MAX=6000
PLATFORM_MAX=900
PAGE_MAX_TOKENS=50000
fail=0
admin_lines=$(wc -l < "$ROOT/admin.html")
echo "Shell admin.html: $admin_lines lines (budget $SHELL_MAX — currently over, will shrink as extraction continues)"
if [ "$admin_lines" -gt 26200 ]; then echo "  FAIL: shell grew beyond original 26088"; fail=1; fi
for mod in "$ROOT"/platforms/*/module.js; do
  lines=$(wc -l < "$mod")
  plat=$(basename $(dirname "$mod"))
  if [ "$lines" -gt "$PLATFORM_MAX" ]; then echo "  FAIL: $plat/module.js $lines > $PLATFORM_MAX"; fail=1; else echo "  OK: $plat/module.js $lines lines"; fi
done
for pg in "$ROOT"/platforms/*/pages/*.html; do
  chars=$(wc -c < "$pg"); tokens=$((chars/4))
  if [ "$tokens" -gt "$PAGE_MAX_TOKENS" ]; then echo "  FAIL: $pg ~$tokens tokens > $PAGE_MAX_TOKENS"; fail=1; fi
done
echo "Budget check done (fail=$fail). Note: shell budget enforcement becomes strict (fail) after Phase 3."
exit $fail
