#!/usr/bin/env bash
# reflection.sh — part of the Shark Starter Kit.
#
# Self-grading trade journal. jq-free (python3 only) so it runs on a minimal
# runtime (curl + python3, no extra deps).
#
# Journal data persists in JOURNAL.md (git-tracked, kit top-level) so it
# survives across fires via the Step 7 commit. Resolved here relative to this
# skill dir: ../../JOURNAL.md. Override with SHARK_JOURNAL_PATH.
#
# Commands (all read JSON on stdin except `context`):
#   append   {ticker,date,conviction,entry,stop,thesis}   -> Phase A pending slip
#   outcome  {ticker?,entry_price,exit_price,entry_date,   -> Phase B grading math
#             exit_date,realized_R}                           (prints outcome JSON)
#   resolve  {ticker,date,outcome,lesson}                  -> Phase B write (atomic)
#   context  <TICKER>                                       -> Phase C lessons (stdout)
#
# Exit codes: 0 ok | 2 usage | 3 bad stdin JSON / python3 missing

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
log() { printf '[reflection] %s\n' "$*" >&2; }

if ! command -v python3 >/dev/null 2>&1; then
  log "python3 not installed; cannot run reflection"
  exit 3
fi

: "${SHARK_JOURNAL_PATH:="$SCRIPT_DIR/../../JOURNAL.md"}"
export SHARK_JOURNAL_PATH

exec python3 "$SCRIPT_DIR/reflection.py" "$@"
