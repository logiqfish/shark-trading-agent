#!/usr/bin/env bash
# Alpaca open positions — read-only. Each position is ENRICHED with a "name"
# field (company name from /v2/assets/{symbol}, legal suffix trimmed) so status
# output can render "Company Name (TICKER)" without the model having to look it up.
# Returns a JSON array (qty, avg_entry_price, current_price, market_value,
# unrealized_pl, side, name, ...). Empty array if no open positions. Stdlib only.
set -euo pipefail

: "${ALPACA_API_KEY:?ALPACA_API_KEY not set in environment}"
: "${ALPACA_SECRET_KEY:?ALPACA_SECRET_KEY not set in environment}"

exec python3 -c "$(cat <<'PY'
import os, json, ssl, urllib.request
KEY = os.environ["ALPACA_API_KEY"]; SEC = os.environ["ALPACA_SECRET_KEY"]
BASE = "https://paper-api.alpaca.markets"
CTX = ssl.create_default_context()
JUNK = (" Common Stock", " Common stock", " Ordinary Shares", " Class A",
        " Class B", ", Inc.", " Inc.", ", Ltd.", " Ltd.", ", Corporation",
        " Corporation")

def get(path):
    r = urllib.request.Request(BASE + path)
    r.add_header("APCA-API-KEY-ID", KEY); r.add_header("APCA-API-SECRET-KEY", SEC)
    with urllib.request.urlopen(r, context=CTX, timeout=20) as resp:
        return json.loads(resp.read().decode() or "null")

def short(sym):
    try:
        n = (get("/v2/assets/" + sym).get("name") or "")
        for j in JUNK:
            n = n.replace(j, "")
        return n.strip().rstrip(",")
    except Exception:
        return ""

pos = get("/v2/positions")
if isinstance(pos, list):
    for p in pos:
        p["name"] = short(p.get("symbol", ""))
print(json.dumps(pos))
PY
)"
