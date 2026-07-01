#!/usr/bin/env bash
# debate.sh — part of the Shark Starter Kit.
#
# Bull/bear/referee conviction debate helper. jq-free (python3 only) so it runs
# on a minimal runtime (curl + python3, no extra deps).
#
# The bull/bear/referee TURNS are run by the agent's own brain per DEBATE.md;
# this wrapper only validates the referee verdict and logs the transcript.
#
# Command (reads JSON on stdin):
#   record  {ticker,date,bull,bear,verdict:{conviction,stance,rationale}}
#           -> appends transcript to memory/<date>.md (SHARK_MEMORY_DIR overrides)
#              and prints the normalized {ticker,conviction,stance,rationale}.
#
# Exit codes: 0 ok | 2 usage | 3 bad stdin JSON / malformed verdict / python3 missing

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
log() { printf '[debate] %s\n' "$*" >&2; }

if ! command -v python3 >/dev/null 2>&1; then
  log "python3 not installed; cannot run debate"
  exit 3
fi

exec python3 "$SCRIPT_DIR/debate.py" "$@"
