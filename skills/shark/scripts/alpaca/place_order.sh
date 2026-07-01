#!/usr/bin/env bash
# Alpaca paper-trade order — WRITE.
# Places a single market or limit order on the paper account.
# Returns raw JSON for the created order; non-zero exit on failure.
#
# Usage:
#   place_order.sh SYMBOL QTY SIDE [LIMIT_PRICE] [TIF]
#     SYMBOL       e.g. AAPL
#     QTY          shares (fractional allowed, e.g. 0.5)
#     SIDE         buy | sell
#     LIMIT_PRICE  optional; omit for market order
#     TIF          time-in-force: day (default) | gtc | ioc | fok
#
# Examples:
#   place_order.sh AAPL 1 buy
#   place_order.sh AAPL 1 sell 150.50
#   place_order.sh AAPL 0.5 buy "" gtc
#
# Safety: hits paper endpoint only. Caller is responsible for eligibility
# gates (cash, position size, stop plan, conviction) per IDENTITY.md.
set -euo pipefail

: "${ALPACA_API_KEY:?ALPACA_API_KEY not set in environment}"
: "${ALPACA_SECRET_KEY:?ALPACA_SECRET_KEY not set in environment}"

if [ "$#" -lt 3 ]; then
  echo "Usage: $0 SYMBOL QTY SIDE [LIMIT_PRICE] [TIF]" >&2
  exit 2
fi

SYMBOL="$1"
QTY="$2"
SIDE="$(echo "$3" | tr '[:upper:]' '[:lower:]')"
LIMIT_PRICE="${4:-}"
TIF="${5:-day}"

case "${SIDE}" in
  buy|sell) ;;
  *) echo "side must be buy or sell" >&2; exit 2 ;;
esac

if [ -n "${LIMIT_PRICE}" ]; then
  BODY=$(printf '{"symbol":"%s","qty":"%s","side":"%s","type":"limit","time_in_force":"%s","limit_price":"%s"}' \
    "${SYMBOL}" "${QTY}" "${SIDE}" "${TIF}" "${LIMIT_PRICE}")
else
  BODY=$(printf '{"symbol":"%s","qty":"%s","side":"%s","type":"market","time_in_force":"%s"}' \
    "${SYMBOL}" "${QTY}" "${SIDE}" "${TIF}")
fi

curl -fsS \
  -H "APCA-API-KEY-ID: ${ALPACA_API_KEY}" \
  -H "APCA-API-SECRET-KEY: ${ALPACA_SECRET_KEY}" \
  -H "Content-Type: application/json" \
  -X POST \
  --data "${BODY}" \
  https://paper-api.alpaca.markets/v2/orders
