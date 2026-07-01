#!/usr/bin/env bash
# Alpaca market clock — read-only.
# Returns raw JSON: is_open, next_open, next_close, timestamp.
# Use this for the closed-market gate before any scan or trade attempt.
set -euo pipefail

: "${ALPACA_API_KEY:?ALPACA_API_KEY not set in environment}"
: "${ALPACA_SECRET_KEY:?ALPACA_SECRET_KEY not set in environment}"

curl -fsS \
  -H "APCA-API-KEY-ID: ${ALPACA_API_KEY}" \
  -H "APCA-API-SECRET-KEY: ${ALPACA_SECRET_KEY}" \
  https://paper-api.alpaca.markets/v2/clock
