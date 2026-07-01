"""broker.scale_out — Phase 2 scale-out executor, tested with an injected fake HTTP fn.

CANCEL-AND-REBUILD sequence (the spike proved per-leg OCO qty replacement is rejected
by Alpaca: HTTP 422 "qty cannot be changed for advanced orders", 2026-06-17):
  1. CANCEL the resting OCO legs (frees all shares)
  2. market-DAY SELL the freed half
  3. place a fresh OCO (stop=breakeven + target=+2R) on the runner qty
These verify the CALL SEQUENCE/payloads; the spike validates Alpaca accepts them.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import broker
from execution_adapter import LegacyAlpacaRestAdapter


def _rec(responses=None):
    """Recording fake req. responses maps (method, path) -> (status, json);
    anything unspecified returns (200, {"id": <last path segment>})."""
    responses = responses or {}
    calls = []

    def req(base, key, sec, method, path, body=None):
        calls.append((method, path, body))
        return responses.get((method, path), (200, {"id": path.rsplit("/", 1)[-1]}))
    return req, calls


def _adapter_from_rec(req):
    return LegacyAlpacaRestAdapter("https://paper-api.alpaca.markets", "k", "s", http=req)


def test_scale_out_cancels_legs_sells_then_replaces_oco():
    req, calls = _rec()
    a = _adapter_from_rec(req)
    r = broker.scale_out("MSFT", sell_qty=2, runner_qty=2, breakeven_stop=51.30,
                         target_price=61.30, cancel_ids=["s1", "t1"],
                         adapter=a)
    assert r["ok"] is True, r
    seq = [(m, p) for (m, p, b) in calls]
    # 1. both resting legs cancelled
    assert ("DELETE", "/v2/orders/s1") in seq and ("DELETE", "/v2/orders/t1") in seq
    # 2. freed half market-sold DAY
    sell = next(b for (m, p, b) in calls if (m, p) == ("POST", "/v2/orders") and b.get("type") == "market")
    assert sell["side"] == "sell" and sell["qty"] == "2"
    # 3. fresh OCO on the runner: stop=breakeven + target, qty=runner
    oco = next(b for (m, p, b) in calls
               if (m, p) == ("POST", "/v2/orders") and b.get("order_class") == "oco")
    assert oco["side"] == "sell" and oco["qty"] == "2"
    assert oco["stop_loss"]["stop_price"] == "51.3"
    assert oco["take_profit"]["limit_price"] == "61.3"
    # ordering: cancel BEFORE sell BEFORE re-protect
    assert seq.index(("DELETE", "/v2/orders/s1")) < seq.index(("POST", "/v2/orders"))


def test_scale_out_refuses_non_paper_base():
    req, calls = _rec()
    a = LegacyAlpacaRestAdapter("https://live.example", "k", "s", http=req)
    r = broker.scale_out("MSFT", 2, 2, 51.30, 61.30, ["s1", "t1"],
                         adapter=a)
    assert r["ok"] is False and r["stage"] == "guard"
    assert calls == []      # nothing touched


def test_scale_out_aborts_and_alerts_if_sell_fails():
    # cancels succeed, but the market sell is rejected -> abort + alert (position now
    # unprotected: legs cancelled, sell failed) so the caller raises an urgent alert.
    req, calls = _rec({("POST", "/v2/orders"): (403, {"message": "sell rejected"})})
    a = _adapter_from_rec(req)
    r = broker.scale_out("MSFT", 2, 2, 51.30, 61.30, ["s1", "t1"],
                         adapter=a)
    assert r["ok"] is False and r["stage"] == "sell" and r["alert"] is True


def test_scale_out_alerts_if_reprotect_fails_leaving_runner_naked():
    # cancel + sell ok, but the new OCO is rejected -> runner is NAKED -> loud alert.
    def req(base, key, sec, method, path, body=None):
        if method == "POST" and body and body.get("order_class") == "oco":
            return (422, {"message": "oco rejected"})
        return (200, {"id": "x"})
    a = _adapter_from_rec(req)
    r = broker.scale_out("MSFT", 2, 2, 51.30, 61.30, ["s1", "t1"],
                         adapter=a)
    assert r["ok"] is False and r["stage"] == "reprotect" and r["alert"] is True


def test_scale_out_dry_run_places_nothing():
    req, calls = _rec()
    a = _adapter_from_rec(req)
    r = broker.scale_out("MSFT", 2, 2, 51.30, 61.30, ["s1", "t1"],
                         adapter=a, dry=True)
    assert r["ok"] is True and r["stage"] == "dry_run"
    assert calls == []


def test_cli_scale_out_dry_run_roundtrips_json():
    import json, subprocess
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = subprocess.run(
        [sys.executable, os.path.join(here, "broker.py"),
         "scale_out", "MSFT", "2", "2", "51.30", "61.30", "s1", "t1", "--dry-run"],
        capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    j = json.loads(out.stdout)
    assert j["ok"] is True and j["stage"] == "dry_run"
    assert j["plan"]["sell"]["qty"] == 2 and j["plan"]["cancel_ids"] == ["s1", "t1"]
    assert j["plan"]["reprotect"]["stop"] == 51.30 and j["plan"]["reprotect"]["target"] == 61.30
