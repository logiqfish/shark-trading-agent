#!/usr/bin/env bash
# risk.sh — part of the Shark Starter Kit.
#
# Position-sizing + pre-trade risk gate. jq-free (python3 + curl only) so it
# runs on a minimal runtime (curl + python3, no extra deps).
#
# Reads base JSON {account, candidate, positions} on stdin. If an optional
# sibling skills/catalyst/fetch.sh is present (the kit ships none), it is used
# for the earnings-blackout dire-gate; otherwise that check is simply skipped.
#
# Earnings data is FAIL-OPEN: if the optional catalyst fetch is missing or
# unreachable, risk.py records earnings_check="unknown" (a warning, not a block).
#
# Exit codes (from risk.py):
#   0   PASS    — sized and all gates pass
#   10  REJECT  — sizing rejected OR a gate/dire-trigger fired
#   3   parse failure (bad stdin JSON, or python3 missing)

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log() { printf '[risk] %s\n' "$*" >&2; }

if ! command -v python3 >/dev/null 2>&1; then
  log "python3 not installed; cannot evaluate risk"
  exit 3
fi

# Pre-flight legality gate (`actions`): no catalyst fetch needed — just pass the
# {account, positions, candidates, today_activity} payload straight through.
if [[ "${1:-}" == "actions" ]]; then
  exec python3 "$SCRIPT_DIR/risk.py" actions
fi

BASE_FILE="$(mktemp -t risk_base.XXXXXX.json)"
CAT_FILE="$(mktemp -t risk_cat.XXXXXX.json)"
trap 'rm -f "$BASE_FILE" "$CAT_FILE"' EXIT
cat > "$BASE_FILE"

# Extract the candidate ticker with python (no jq on every runtime).
TICKER="$(python3 -c '
import json, sys
try:
    d = json.load(open(sys.argv[1]))
    print(((d.get("candidate") or {}).get("ticker") or "").strip())
except Exception:
    print("")
' "$BASE_FILE")"

CAT_ARGS=()
FETCH="$SCRIPT_DIR/../catalyst/fetch.sh"
if [[ -n "$TICKER" && -x "$FETCH" ]]; then
  if "$FETCH" "$TICKER" > "$CAT_FILE" 2>/dev/null && [[ -s "$CAT_FILE" ]]; then
    CAT_ARGS=(--catalyst-file "$CAT_FILE")
    log "catalyst fetched for $TICKER"
  else
    log "catalyst fetch failed for $TICKER; earnings_check will be unknown"
  fi
fi

# "${CAT_ARGS[@]+...}" guards the empty-array expansion under `set -u` on
# bash 3.2 (the macOS default) — a bare "${CAT_ARGS[@]}" throws "unbound
# variable" there. Works on bash 3.2 and 4+/5+ alike.
python3 "$SCRIPT_DIR/risk.py" "${CAT_ARGS[@]+"${CAT_ARGS[@]}"}" < "$BASE_FILE"
exit $?
