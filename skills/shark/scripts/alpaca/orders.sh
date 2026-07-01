#!/usr/bin/env bash
# Alpaca orders — read-only.
# Returns a FLAT JSON array of orders, INCLUDING bracket/OCO child legs surfaced as
# top-level entries (query uses nested=true, then legs are flattened in python). This
# mirrors the leg-aware detection broker.py's manage_position() uses. Without it, a
# status=open query rolls an active OCO's stop leg under its parent, so a stop audit
# reads "no stop" on a protected position -> false dire-gate liquidation (2026-06-22 bug).
# Default "open" surfaces WORKING + HELD orders: it queries status=all and drops
# terminal statuses (canceled/filled/expired/rejected/replaced/done_for_day). A
# protective stop can rest in Alpaca status "held", which a literal status=open query
# NEVER returns (filled bracket parent + held leg both excluded) -> a stop audit reads
# "no stop" on a protected position (2026-06-24; the deeper half of the 06-22 bug).
# Pass "closed" or "all" as $1 to get those sets RAW (unfiltered) for debugging.
# Each order: id, client_order_id, symbol, qty, filled_qty, side, type, status,
# stop_price, limit_price, submitted_at, filled_at, etc.
set -euo pipefail

: "${ALPACA_API_KEY:?ALPACA_API_KEY not set in environment}"
: "${ALPACA_SECRET_KEY:?ALPACA_SECRET_KEY not set in environment}"

STATUS="${1:-open}"
LIMIT="${2:-50}"

case "${STATUS}" in
  open|closed|all) ;;
  *) echo "Usage: $0 [open|closed|all] [limit]" >&2; exit 2 ;;
esac

# "open" -> query all + filter terminal (= working+held); closed/all -> raw passthrough
if [ "${STATUS}" = "open" ]; then QUERY="all"; FILTER_DEAD=1; else QUERY="${STATUS}"; FILTER_DEAD=0; fi

curl -fsS \
  -H "APCA-API-KEY-ID: ${ALPACA_API_KEY}" \
  -H "APCA-API-SECRET-KEY: ${ALPACA_SECRET_KEY}" \
  "https://paper-api.alpaca.markets/v2/orders?status=${QUERY}&limit=${LIMIT}&direction=desc&nested=true" \
  | FILTER_DEAD="${FILTER_DEAD}" python3 -c '
import sys, json, os
arr = json.load(sys.stdin)
if not isinstance(arr, list):
    print(json.dumps(arr)); sys.exit(0)   # pass through error objects unchanged
DEAD = {"canceled", "cancelled", "filled", "expired", "rejected", "replaced", "done_for_day"}
filt = os.environ.get("FILTER_DEAD") == "1"
out, seen = [], set()
def emit(o):
    if not isinstance(o, dict):
        return
    i = o.get("id")
    if i and i in seen:
        return
    if i:
        seen.add(i)
    c = dict(o)
    legs = c.pop("legs", None) or []       # surface child legs as top-level orders
    if not (filt and str(c.get("status", "")).lower() in DEAD):
        out.append(c)                      # drop terminal orders (e.g. the filled bracket parent)
    for leg in legs:                       # but ALWAYS recurse legs (the held stop lives here)
        emit(leg)
for o in arr:
    emit(o)
print(json.dumps(out))'
