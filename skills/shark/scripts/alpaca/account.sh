#!/usr/bin/env bash
# Alpaca paper-account state — read-only.
# Returns raw JSON: equity, cash, buying_power, status, account_number, etc.
#
# Fail-closed account-identity guard: if ALPACA_ACCOUNT_ID is set, the live
# account_number must match it or this exits non-zero (3) and prints nothing on
# stdout — so a bad/rotated key set can't silently trade the wrong account.
# Unset ALPACA_ACCOUNT_ID -> warns on stderr and proceeds (paper-safe).
set -euo pipefail

: "${ALPACA_API_KEY:?ALPACA_API_KEY not set in environment}"
: "${ALPACA_SECRET_KEY:?ALPACA_SECRET_KEY not set in environment}"

resp="$(curl -fsS \
  -H "APCA-API-KEY-ID: ${ALPACA_API_KEY}" \
  -H "APCA-API-SECRET-KEY: ${ALPACA_SECRET_KEY}" \
  https://paper-api.alpaca.markets/v2/account)"

# jq-free guard (python3 is present on every runtime); exits 3 on mismatch.
printf '%s' "$resp" | python3 "$(dirname "$0")/account_guard.py"

printf '%s' "$resp"
