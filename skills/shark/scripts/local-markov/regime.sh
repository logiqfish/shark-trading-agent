#!/usr/bin/env bash
# local-markov regime for a ticker -> {"current_regime":"Bull|Sideways|Bear"} or {}.
set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
command -v python3 >/dev/null 2>&1 || { echo '{}'; exit 3; }
exec python3 "$DIR/local_markov.py" "${1:-SPY}"
