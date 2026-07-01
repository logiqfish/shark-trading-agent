#!/usr/bin/env bash
# thesis.sh — part of the Shark Starter Kit.
#
# Persistent trade-thesis store + zero-LLM Layer-1 re-score. jq-free (python3
# only) so it runs on a minimal runtime (curl + python3, no extra deps).
#
# Thesis data persists in THESES.json (git-tracked, kit top-level) so it
# survives across fires via the Step 7 commit. Closed theses prune to
# THESES_ARCHIVE.jsonl (gitignored, audit-only). Paths resolve relative to this
# skill dir: ../../THESES.json and ../../THESES_ARCHIVE.jsonl. Override with
# SHARK_THESES_PATH / SHARK_THESES_ARCHIVE_PATH.
#
# Commands (JSON on stdin except `rescore`/`list`):
#   create          {ticker,direction,conviction,invalidation_price,fire,      -> debate creates a thesis
#                    assumptions[],kind?}                                          (prints {"id":...})
#   rescore <fire>  (no stdin)                                                  -> Layer 1: re-score all open
#                                                                                  theses; prints summary JSON
#                                                                                  (one row/thesis, escalate?)
#   set-conviction  {id,conviction,fire}                                        -> seeded debate result
#   close           {id,outcome}                                               -> grade-at-exit: close+archive
#   list            (no stdin)                                                  -> open theses JSON (stdout)
#
# Re-score data is on-box only: price from the friend's ALPACA_API_KEY/SECRET_KEY,
# regime from the sibling local-markov skill (../local-markov/local_markov.py).
# Any missing cred / undetermined regime -> that check fails safe to escalation
# (never a silent skip).
#
# Exit codes: 0 ok | 2 usage | 3 bad stdin JSON / python3 missing
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
log() { printf '[thesis] %s\n' "$*" >&2; }

if ! command -v python3 >/dev/null 2>&1; then
  log "python3 not installed; cannot run thesis skill"
  exit 3
fi

: "${SHARK_THESES_PATH:="$SCRIPT_DIR/../../THESES.json"}"
: "${SHARK_THESES_ARCHIVE_PATH:="$SCRIPT_DIR/../../THESES_ARCHIVE.jsonl"}"
export SHARK_THESES_PATH SHARK_THESES_ARCHIVE_PATH

exec python3 "$SCRIPT_DIR/thesis.py" "$@"
