#!/usr/bin/env bash
# discretionary.sh — human "2nd brain" gut-trade entry (Shark Starter Kit).
#
# Two subcommands, both read one JSON object on stdin (mirrors risk.sh/reflection.sh):
#   propose   {account,positions,candidate:{ticker,price,conviction,stop?}}  -> card JSON
#   execute   <propose card + {date,thesis}>                                 -> fill card
#
# Orchestrates the kit's local siblings (../local-markov regime veto, ../risk,
# ../trade-manager, ../reflection). jq-free (python3 only). The bull/bear/referee
# debate that yields `conviction` is run by the agent's brain, NOT here.
# Conviction is advisory; the risk kernel is HARD.
#
# Exit: 0 ok | 2 usage | 3 bad stdin / python3 missing | 10 hard block / not ok
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if ! command -v python3 >/dev/null 2>&1; then
  echo "[discretionary] python3 not installed; cannot run" >&2
  exit 3
fi
exec python3 "$SCRIPT_DIR/discretionary.py" "$@"
