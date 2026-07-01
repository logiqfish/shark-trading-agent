#!/usr/bin/env python3
"""On-box market-regime proxy: Bull / Sideways / Bear from daily closes.
Part of the Shark Starter Kit.

Pure standard library — no heavy scientific-python or scraping dependencies.
Daily bars come from the friend's Alpaca keys (data.alpaca.markets IEX feed).
Fail-soft: insufficient data / fetch error -> None -> caller treats as no-trade /
escalation (a wrong label can never be confidently emitted)."""
import json
import os
import ssl
import sys
import urllib.error
import urllib.request

DATA_BASE = "https://data.alpaca.markets"

SMA_FAST = int(os.environ.get("MARKOV_SMA_FAST", 20))
SMA_SLOW = int(os.environ.get("MARKOV_SMA_SLOW", 50))
VOL_LOOKBACK = int(os.environ.get("MARKOV_VOL_LOOKBACK", 20))
DD_LOOKBACK = int(os.environ.get("MARKOV_DD_LOOKBACK", 60))
DD_BEAR = 0.10          # drawdown from the trailing high past this -> risk-off Bear
VOL_BEAR = 0.04         # daily-return stdev past this -> risk-off Bear


def _sma(xs, n):
    return sum(xs[-n:]) / n if len(xs) >= n else None


def _stdev(xs):
    if len(xs) < 2:
        return 0.0
    m = sum(xs) / len(xs)
    return (sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5


def classify(closes):
    """closes: chronological list of daily closes. -> 'Bull'|'Sideways'|'Bear'|None."""
    closes = [float(c) for c in closes if c is not None]
    if len(closes) < SMA_SLOW:
        return None
    price = closes[-1]
    fast, slow = _sma(closes, SMA_FAST), _sma(closes, SMA_SLOW)
    if fast is None or slow is None:
        return None
    rets = [(closes[i] - closes[i - 1]) / closes[i - 1]
            for i in range(1, len(closes)) if closes[i - 1]]
    vol = _stdev(rets[-VOL_LOOKBACK:])
    hi = max(closes[-DD_LOOKBACK:])
    dd = (hi - price) / hi if hi else 0.0

    # Risk-off override: a vol or drawdown spike is Bear regardless of trend.
    if dd >= DD_BEAR or vol >= VOL_BEAR:
        return "Bear"
    if price > slow and fast > slow:
        return "Bull"
    if price < slow and fast < slow:
        return "Bear"
    return "Sideways"


def current_regime_from_closes(closes):
    r = classify(closes)
    return {"current_regime": r} if r else {}


# --- Alpaca daily-bars fetch (mirrors reflection.spy_return_pct) --------------
def _creds():
    return (os.environ.get("ALPACA_API_KEY") or os.environ.get("ALPACA_KEY_ID"),
            os.environ.get("ALPACA_SECRET_KEY") or os.environ.get("ALPACA_SECRET"))


def fetch_daily_closes(ticker, limit=120):
    key, sec = _creds()
    if not key or not sec:
        return None
    path = (f"/v2/stocks/{ticker}/bars?timeframe=1Day&limit={limit}"
            f"&adjustment=raw&feed=iex")
    req = urllib.request.Request(DATA_BASE + path, method="GET")
    req.add_header("APCA-API-KEY-ID", key)
    req.add_header("APCA-API-SECRET-KEY", sec)
    try:
        with urllib.request.urlopen(req, context=ssl.create_default_context(),
                                    timeout=20) as resp:
            payload = json.loads(resp.read().decode() or "{}")
    except Exception:
        return None
    bars = payload.get("bars") or []
    closes = [b.get("c") for b in bars if isinstance(b, dict) and b.get("c") is not None]
    return closes or None


def current_regime(ticker):
    closes = fetch_daily_closes(ticker)
    return current_regime_from_closes(closes) if closes else {}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    ticker = (argv[0] if argv else "SPY").upper()
    print(json.dumps(current_regime(ticker)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
