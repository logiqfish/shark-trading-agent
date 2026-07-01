"""broker.py small-account helpers — tested with an injected fake HTTP fn."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import broker
from execution_adapter import LegacyAlpacaRestAdapter


def _adapter(responses):
    """responses: dict mapping (method, path) -> (status, json)."""
    def http(base, key, sec, method, path, body=None):
        return responses[(method, path)]
    return LegacyAlpacaRestAdapter("https://paper-api.alpaca.markets", "k", "s", http=http)


def test_is_fractionable_true():
    assert broker.is_fractionable("ABC", _adapter({("GET", "/v2/assets/ABC"): (200, {"fractionable": True})})) is True


def test_is_fractionable_false():
    assert broker.is_fractionable("XYZ", _adapter({("GET", "/v2/assets/XYZ"): (200, {"fractionable": False})})) is False


def test_market_open_reads_clock():
    assert broker.market_open(_adapter({("GET", "/v2/clock"): (200, {"is_open": True})})) is True


def test_enter_fractional_rejected_when_not_fractionable():
    r = broker.enter("XYZ", 0.24, 100.0, 95.0, phase=1, dry=True,
                     fractional=True,
                     adapter=_adapter({("GET", "/v2/assets/XYZ"): (200, {"fractionable": False}),
                                       ("GET", "/v2/clock"): (200, {"is_open": True})}))
    assert r["ok"] is False and r["stage"] == "fractionable"


def test_enter_fractional_rejected_when_market_closed():
    r = broker.enter("ABC", 0.24, 100.0, 95.0, phase=1, dry=True,
                     fractional=True,
                     adapter=_adapter({("GET", "/v2/assets/ABC"): (200, {"fractionable": True}),
                                       ("GET", "/v2/clock"): (200, {"is_open": False})}))
    assert r["ok"] is False and r["stage"] == "rth_guard"


def test_enter_fractional_dryrun_lists_buy_and_stop_only():
    r = broker.enter("ABC", 0.24, 100.0, 95.0, phase=1, dry=True,
                     fractional=True,
                     adapter=_adapter({("GET", "/v2/assets/ABC"): (200, {"fractionable": True}),
                                       ("GET", "/v2/clock"): (200, {"is_open": True})}))
    assert r["ok"] is True and r["stage"] == "dry_run"
    assert len(r["orders"]) == 2  # buy + DAY stop only (no co-resting DAY limit)
    assert all(o.get("type") != "limit" for o in r["orders"])


def test_flatten_cancels_sells_and_verifies_zero():
    calls = []
    def req(base, key, sec, method, path, body=None):
        calls.append((method, path))
        if method == "DELETE":
            return (204, {})
        if method == "POST":
            return (200, {"id": "sell-1"})
        if path == "/v2/positions/ABC":
            # after the sell, the position is gone (qty 0)
            return (200, {"qty": "0"}) if ("POST", "/v2/orders") in calls else (200, {"qty": "0.24"})
        return (200, {})
    a = LegacyAlpacaRestAdapter("https://paper-api.alpaca.markets", "k", "s", http=req)
    r = broker.flatten("ABC", ["stop-1", "tp-1"], a)
    assert r["ok"] is True
    assert r["verified_flat"] is True
    assert ("DELETE", "/v2/orders/stop-1") in calls
    assert ("DELETE", "/v2/orders/tp-1") in calls


def test_flatten_fails_when_position_not_zero():
    def req(base, key, sec, method, path, body=None):
        if method == "DELETE":
            return (204, {})
        if method == "POST":
            return (200, {"id": "sell-1"})
        return (200, {"qty": "0.24"})   # still holding -> verification fails
    a = LegacyAlpacaRestAdapter("https://paper-api.alpaca.markets", "k", "s", http=req)
    r = broker.flatten("ABC", ["stop-1"], a)
    assert r["ok"] is False
    assert r["verified_flat"] is False
    assert r["alert"] is True


def test_cli_flatten_usage_without_symbol_returns_2():
    assert broker._main(["broker.py", "flatten"]) == 2


def test_cli_unknown_command_returns_2():
    assert broker._main(["broker.py", "bogus"]) == 2
