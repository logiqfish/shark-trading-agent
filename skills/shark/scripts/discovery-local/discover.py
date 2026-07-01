#!/usr/bin/env python3
"""Candidate discovery for the skinny kit: watchlist (default) or alpaca_movers.
Alpaca-only, no Yahoo, no mesh. Fail-soft to the watchlist on any movers error."""
import json
import os
import ssl
import sys
import urllib.request

DATA_BASE = "https://data.alpaca.markets"


def _watchlist():
    raw = os.environ.get("WATCHLIST", "")
    return [t.strip().upper() for t in raw.split(",") if t.strip()]


def _creds():
    return (os.environ.get("ALPACA_API_KEY"), os.environ.get("ALPACA_SECRET_KEY"))


def fetch_movers():
    """Alpaca most-actives by volume -> [{symbol, price?, volume}]. [] on any error."""
    key, sec = _creds()
    if not key or not sec:
        return []
    req = urllib.request.Request(
        DATA_BASE + "/v1beta1/screener/stocks/most-actives?by=volume&top=50",
        method="GET")
    req.add_header("APCA-API-KEY-ID", key)
    req.add_header("APCA-API-SECRET-KEY", sec)
    try:
        with urllib.request.urlopen(req, context=ssl.create_default_context(),
                                    timeout=20) as resp:
            payload = json.loads(resp.read().decode() or "{}")
    except Exception:
        return []
    out = []
    for m in payload.get("most_actives", []) or []:
        out.append({"symbol": m.get("symbol"),
                    "price": m.get("price"),          # may be absent in screener
                    "volume": m.get("volume", 0)})
    return out


def candidates(fetch_movers=fetch_movers):
    mode = os.environ.get("DISCOVERY_MODE", "watchlist").strip().lower()
    if mode != "alpaca_movers":
        return _watchlist()
    min_price = float(os.environ.get("MOVERS_MIN_PRICE", 5))
    min_vol = float(os.environ.get("MOVERS_MIN_VOLUME", 1_000_000))
    top_n = int(os.environ.get("MOVERS_TOP_N", 10))
    picked = []
    for m in fetch_movers():
        sym = (m.get("symbol") or "").upper()
        price = m.get("price")
        vol = float(m.get("volume") or 0)
        if not sym or vol < min_vol:
            continue
        if price is not None and float(price) < min_price:
            continue
        picked.append(sym)
        if len(picked) >= top_n:
            break
    return picked or _watchlist()   # fail-soft: never return nothing


def main(argv=None):
    print(json.dumps(candidates()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
