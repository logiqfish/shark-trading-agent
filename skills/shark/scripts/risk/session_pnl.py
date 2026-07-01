#!/usr/bin/env python3
"""session_pnl.py — fetch today's session baseline + intraday equity LOW from
Alpaca portfolio-history, for the latching daily-loss circuit breaker.
Part of the Shark Starter Kit.

Prints {"day_start_equity": <base>, "session_low_equity": <low>} to stdout for
the agent to merge into the `account` payload it passes to risk.sh. SOFT-FAILS
to {} (or base-only) on any error so risk.py degrades to its point-in-time check
(see risk._trip_equity). Standard library only (urllib) — no extra deps.

Credentials from env (tolerant of common Alpaca naming variants):
  key:    ALPACA_API_KEY_ID | ALPACA_API_KEY | APCA_API_KEY_ID
  secret: ALPACA_SECRET_KEY | ALPACA_API_SECRET_KEY | APCA_API_SECRET_KEY
  base:   ALPACA_BASE_URL (default paper)
"""
import json
import os
import urllib.request
import urllib.error

_KEY_VARS = ("ALPACA_API_KEY_ID", "ALPACA_API_KEY", "APCA_API_KEY_ID")
_SECRET_VARS = ("ALPACA_SECRET_KEY", "ALPACA_API_SECRET_KEY", "APCA_API_SECRET_KEY")


def _env(names):
    for n in names:
        v = os.environ.get(n)
        if v:
            return v
    return None


def parse(payload):
    """portfolio-history dict -> {day_start_equity[, session_low_equity]} or {}.
    Pure; unit-tested without network."""
    if not isinstance(payload, dict):
        return {}
    base = payload.get("base_value")
    if base is None:
        return {}
    try:
        out = {"day_start_equity": float(base)}
    except (TypeError, ValueError):
        return {}
    eq = [e for e in (payload.get("equity") or []) if e is not None]
    try:
        lows = [float(e) for e in eq]
    except (TypeError, ValueError):
        lows = []
    if lows:
        out["session_low_equity"] = min(lows)
    return out


def fetch():
    """Call Alpaca portfolio-history (period=1D). Returns parse() output, or {}
    on any failure (the safe direction — caller degrades to point-in-time)."""
    key, secret = _env(_KEY_VARS), _env(_SECRET_VARS)
    base_url = os.environ.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets").rstrip("/")
    if not key or not secret:
        return {}
    url = f"{base_url}/v2/account/portfolio/history?period=1D&timeframe=5Min&extended_hours=false"
    req = urllib.request.Request(url, headers={
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": secret,
        "accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return parse(json.loads(resp.read().decode()))
    except Exception:  # noqa: BLE001 — this is a soft-fail boundary: ANY failure
        # (incl. http.client.HTTPException like IncompleteRead/BadStatusLine, which
        # are NOT OSError/URLError subclasses) must degrade to {} so the agent's
        # fire never crashes and risk.py falls back to its point-in-time check.
        return {}


def main():
    print(json.dumps(fetch()))


if __name__ == "__main__":
    main()
