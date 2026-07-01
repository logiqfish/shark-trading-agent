"""broker.manage — the dispatcher: run audit() on a position snapshot and execute the
returned actions via the broker. Tested with an injected fake HTTP fn (real audit())."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import broker
from execution_adapter import LegacyAlpacaRestAdapter


def _rec(responses=None):
    responses = responses or {}
    calls = []

    def req(base, key, sec, method, path, body=None):
        calls.append((method, path, body))
        return responses.get((method, path), (200, {"id": path.rsplit("/", 1)[-1]}))
    return req, calls


def _adapter_from_rec(req):
    return LegacyAlpacaRestAdapter("https://paper-api.alpaca.markets", "k", "s", http=req)


def _snap(**over):
    # 1R = 5.00; +1R = 56.30. Non-round entry so breakeven isn't dodged.
    s = {"symbol": "MSFT", "entry": 51.30, "qty": 4, "position_qty": 4,
         "stop_price": 46.30, "stop_order": {"id": "s1", "qty": 4},
         "tp_order": {"id": "t1", "qty": 4}, "last_filled_exit": None,
         "last_price": 56.30}
    s.update(over)
    return s


def test_manage_dispatches_scale_out_at_1R():
    req, calls = _rec()
    out = broker.manage(_snap(), adapter=_adapter_from_rec(req))
    seq = [(m, p) for (m, p, b) in calls]
    assert ("DELETE", "/v2/orders/s1") in seq and ("DELETE", "/v2/orders/t1") in seq
    assert any(b.get("order_class") == "oco" for (m, p, b) in calls if m == "POST")
    assert out["alerts"] == []
    assert any(r["op"] == "scale_out" and r["result"]["ok"] for r in out["results"])


def test_manage_noop_below_1R_touches_nothing():
    req, calls = _rec()
    out = broker.manage(_snap(last_price=55.00), adapter=_adapter_from_rec(req))
    assert calls == []
    assert out["alerts"] == []


def test_manage_repairs_missing_stop():
    req, calls = _rec()
    # scaled runner (pos<qty) whose stop vanished -> audit place_stop -> broker POST stop
    broker.manage(_snap(position_qty=2, stop_order=None, last_price=70.0),
                  adapter=_adapter_from_rec(req))
    posts = [b for (m, p, b) in calls if m == "POST" and p == "/v2/orders"]
    assert any(b.get("type") == "stop" and b.get("qty") == "2" for b in posts)


def test_manage_single_share_breakeven_is_price_only_patch():
    req, calls = _rec()
    broker.manage(_snap(qty=1, position_qty=1, stop_order={"id": "s1", "qty": 1}),
                  adapter=_adapter_from_rec(req))
    patches = [(p, b) for (m, p, b) in calls if m == "PATCH"]
    assert ("/v2/orders/s1", {"stop_price": "51.3"}) in patches


def test_manage_surfaces_alert_on_reprotect_failure():
    def req(base, key, sec, method, path, body=None):
        if method == "POST" and body and body.get("order_class") == "oco":
            return (422, {"message": "oco rejected"})
        return (200, {"id": "x"})
    out = broker.manage(_snap(), adapter=_adapter_from_rec(req))
    assert out["alerts"] and out["alerts"][0]["op"] == "scale_out"


def test_manage_position_gathers_snapshot_and_dispatches_scale_out():
    # a position at +1R with a resting OCO -> helper builds the snapshot from broker
    # state and dispatches scale_out (cancel legs + sell half + rebuild OCO).
    resp = {
        ("GET", "/v2/positions/MSFT"):
            (200, {"symbol": "MSFT", "qty": "4", "avg_entry_price": "51.30",
                   "current_price": "56.30"}),
        ("GET", "/v2/orders?status=all&symbols=MSFT&nested=true&limit=50"):
            (200, [{"id": "s1", "side": "sell", "type": "stop", "stop_price": "46.30"},
                   {"id": "t1", "side": "sell", "type": "limit", "limit_price": "61.30"}]),
    }
    req, calls = _rec(resp)
    out = broker.manage_position("MSFT", adapter=_adapter_from_rec(req))
    seq = [(m, p) for (m, p, b) in calls]
    assert ("DELETE", "/v2/orders/s1") in seq and ("DELETE", "/v2/orders/t1") in seq
    assert any(b.get("order_class") == "oco" for (m, p, b) in calls if m == "POST")
    assert out["alerts"] == []


def test_manage_position_does_not_duplicate_stop_when_stop_is_held():
    # ZETA-class: the protective stop rests in Alpaca status "held" under a filled
    # bracket parent. manage_position must SEE it (status=all) and NOT place a
    # duplicate stop (the second path of the 2026-06-22 bug).
    resp = {
        ("GET", "/v2/positions/ZETA"):
            (200, {"symbol": "ZETA", "qty": "86", "avg_entry_price": "19.65",
                   "current_price": "19.72"}),
        ("GET", "/v2/orders?status=all&symbols=ZETA&nested=true&limit=50"):
            (200, [{"id": "p1", "side": "buy", "type": "market", "status": "filled",
                    "legs": [
                        {"id": "t1", "side": "sell", "type": "limit",
                         "status": "new", "limit_price": "22.52"},
                        {"id": "s1", "side": "sell", "type": "stop",
                         "status": "held", "stop_price": "18.20"}]}]),
    }
    req, calls = _rec(resp)
    broker.manage_position("ZETA", adapter=_adapter_from_rec(req))
    posts = [b for (m, p, b) in calls if m == "POST"]
    assert not any(b.get("type") == "stop" for b in posts), \
        "must NOT place a duplicate stop when one rests in 'held'"


def test_manage_position_no_position_is_safe():
    req, calls = _rec({("GET", "/v2/positions/XYZ"): (404, {"message": "position not found"})})
    out = broker.manage_position("XYZ", adapter=_adapter_from_rec(req))
    assert out["ok"] is False and out["stage"] == "no_position"


def test_cli_manage_dry_run_roundtrips_json():
    import json, subprocess
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = subprocess.run(
        [sys.executable, os.path.join(here, "broker.py"), "manage", "--dry-run"],
        input=json.dumps(_snap()), capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    j = json.loads(out.stdout)
    assert j["state"] == "ENTERED"
    assert any(r["op"] == "scale_out" for r in j["results"])
