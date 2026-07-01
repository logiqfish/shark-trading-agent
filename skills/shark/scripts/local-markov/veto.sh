#!/usr/bin/env bash
# On-box regime veto for the skinny kit. Same exit contract as the mesh veto.sh:
#   0  PASS         regime is Bull/Sideways -> may proceed to scan
#   10 VETO         regime is Bear -> skip new entries this fire
#   20 PASS-THROUGH could not determine (no data / error) -> fail-open, never block
set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TICKER="${1:-SPY}"
command -v python3 >/dev/null 2>&1 || exit 20
REGIME="$(python3 "$DIR/local_markov.py" "$TICKER" \
          | python3 -c 'import sys,json; print((json.load(sys.stdin) or {}).get("current_regime",""))' 2>/dev/null)"
case "$REGIME" in
  Bull|Sideways) exit 0 ;;
  Bear)          echo "regime risk-off ($TICKER=Bear)" >&2; exit 10 ;;
  *)             echo "regime undetermined ($TICKER) — fail-open" >&2; exit 20 ;;
esac
