#!/usr/bin/env bash
# trade-manager — entry wrapper (Phase 1). Thin, jq-free; all logic is in python.
#   manage.sh enter TICKER QTY ENTRY STOP [PHASE] [--dry-run]
# Places a protective+profit GTC bracket; falls back to market+stop if the broker
# rejects the bracket (never leaves a position unprotected). Prints one JSON line.
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
exec python3 "$DIR/broker.py" "$@"
