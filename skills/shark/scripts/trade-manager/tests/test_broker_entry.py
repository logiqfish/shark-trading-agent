"""Whole-share bracket entry + fallback — now adapter-injectable (was untested)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import broker
from execution_adapter import LegacyAlpacaRestAdapter


def _adapter(handler):
    """handler(method, path, body) -> (status, json)."""
    def http(base, key, sec, method, path, body=None):
        return handler(method, path, body)
    return LegacyAlpacaRestAdapter("https://paper-api.alpaca.markets", "k", "s", http=http)


def test_whole_share_bracket_success_returns_order_id():
    posts = []
    def handler(method, path, body):
        if method == "POST" and path == "/v2/orders":
            posts.append(body)
            return (200, {"id": "br-1"})
        return (200, {})
    r = broker.enter("ABC", 10, 100.0, 95.0, phase=1, fractional=False,
                     adapter=_adapter(handler))
    assert r["ok"] is True and r["stage"] == "bracket"
    assert r["order_id"] == "br-1"
    assert len(posts) == 1
    assert posts[0]["order_class"] == "bracket"
    assert "stop_loss" in posts[0] and "take_profit" in posts[0]


def test_whole_share_bracket_reject_falls_back_to_market_plus_stop():
    seen = []
    def handler(method, path, body):
        if method == "POST" and path == "/v2/orders":
            seen.append(body)
            if body.get("order_class") == "bracket":
                return (422, {"message": "bracket not allowed"})
            if body.get("type") == "market":
                return (200, {"id": "buy-1"})
            if body.get("type") == "stop":
                return (200, {"id": "stop-1"})
        return (200, {})
    r = broker.enter("ABC", 10, 100.0, 95.0, phase=1, fractional=False,
                     adapter=_adapter(handler))
    assert r["stage"] == "fallback"
    assert r["buy_id"] == "buy-1" and r["stop_id"] == "stop-1"
    assert [b.get("order_class") for b in seen][0] == "bracket"
    assert any(b.get("type") == "market" for b in seen)
    assert any(b.get("type") == "stop" and b.get("time_in_force") == "gtc" for b in seen)


def test_enter_rejects_non_paper_base():
    a = LegacyAlpacaRestAdapter("https://api.alpaca.markets", "k", "s",
                                http=lambda *args, **kw: (200, {}))
    r = broker.enter("ABC", 10, 100.0, 95.0, fractional=False, adapter=a)
    assert r["ok"] is False and r["stage"] == "guard"


def test_enter_plan_rejected_short_circuits():
    called = []
    a = _adapter(lambda m, p, b: called.append((m, p)) or (200, {}))
    r = broker.enter("ABC", 10, 100.0, 105.0, fractional=False, adapter=a)
    assert r["ok"] is False and r["stage"] == "plan"
    assert called == []


def test_manage_position_reads_nested_legs_and_finds_stop():
    def handler(method, path, body):
        if path == "/v2/positions/ABC":
            return (200, {"avg_entry_price": "100", "qty": "10", "current_price": "101"})
        if path == "/v2/orders?status=open&symbols=ABC&nested=true&limit=50":
            # protective stop is a NESTED leg of the parent bracket order
            return (200, [{"id": "parent", "side": "buy", "type": "market",
                           "legs": [{"id": "stop-1", "side": "sell", "type": "stop",
                                     "stop_price": "95"},
                                    {"id": "tp-1", "side": "sell", "type": "limit"}]}])
        return (200, {})
    r = broker.manage_position("ABC", adapter=_adapter(handler), dry=True)
    # protected position -> audit() returns no alerting actions
    assert r.get("alerts") == []
    assert r.get("state")
