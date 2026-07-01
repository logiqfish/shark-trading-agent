#!/usr/bin/env bash
# Alpaca paper-trade stop-loss — WRITE.
# Places a stop order to close an open long position.
# Returns raw JSON for the created order; non-zero exit on failure.
#
# Usage:
#   place_stop.sh SYMBOL QTY STOP_PRICE [SIDE]
#     SYMBOL      e.g. AAPL
#     QTY         shares to protect (must match an existing position)
#     STOP_PRICE  trigger price
#     SIDE        sell (default; for long positions) | buy (for shorts; not allowed here)
#
# Examples:
#   place_stop.sh AAPL 5 145.00
#
# Safety: hits paper endpoint only. Refuses to place a buy-side stop
# because the kit's strategy is long-only (no short positions).
# Caller is responsible for confirming the stop is active afterward via
# orders.sh open.
set -euo pipefail

: "${ALPACA_API_KEY:?ALPACA_API_KEY not set in environment}"
: "${ALPACA_SECRET_KEY:?ALPACA_SECRET_KEY not set in environment}"

if [ "$#" -lt 3 ]; then
  echo "Usage: $0 SYMBOL QTY STOP_PRICE [SIDE]" >&2
  exit 2
fi

SYMBOL="$1"
QTY="$2"
STOP_PRICE="$3"
SIDE="$(echo "${4:-sell}" | tr '[:upper:]' '[:lower:]')"

if [ "${SIDE}" != "sell" ]; then
  echo "place_stop.sh only supports side=sell (no shorts per IDENTITY.md)" >&2
  exit 2
fi

BODY=$(printf '{"symbol":"%s","qty":"%s","side":"%s","type":"stop","time_in_force":"gtc","stop_price":"%s"}' \
  "${SYMBOL}" "${QTY}" "${SIDE}" "${STOP_PRICE}")

curl -fsS \
  -H "APCA-API-KEY-ID: ${ALPACA_API_KEY}" \
  -H "APCA-API-SECRET-KEY: ${ALPACA_SECRET_KEY}" \
  -H "Content-Type: application/json" \
  -X POST \
  --data "${BODY}" \
  https://paper-api.alpaca.markets/v2/orders
