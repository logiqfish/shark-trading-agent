"""SHARK_FRACTIONAL — fractional execution tests for trade-manager (stdlib only).

Fractional orders on Alpaca must be DAY (no GTC) and can't use bracket/OCO, so
fractional mode: market-DAY buy + a DAY stop (protection), with the take-profit
MANAGED by audit() each fire (can't rest beside the stop). DAY stops expire at
close, so audit() must re-place them each session.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import trade_manager as tm


def test_plan_entry_fractional_is_day_orders_no_bracket():
    p = tm.plan_entry("META", entry=625.0, stop=593.75, qty=0.24, phase=1, fractional=True)
    assert p["reject_reason"] is None
    assert p["fractional"] is True
    # target = 625 + 2*(625-593.75) = 687.50 -> dodged off the .50 magnet -> 687.47
    assert p["target"] == 687.47
    orders = p["orders"]
    assert len(orders) == 2                     # buy + DAY stop ONLY (no co-resting limit)
    buy, stop = orders
    assert buy["side"] == "buy" and buy["type"] == "market" and buy["time_in_force"] == "day"
    assert "order_class" not in buy            # NO bracket on fractional
    assert buy["qty"] == "0.24"
    assert stop["side"] == "sell" and stop["type"] == "stop" and stop["time_in_force"] == "day"
    assert stop["stop_price"] == "593.75"      # already off a round number
    # No resting take-profit limit — fractional can't co-rest one; audit()/force-flat manage it.
    assert all(o.get("type") != "limit" for o in orders)
    assert all(o.get("order_class") != "bracket" for o in orders)
    assert p["target"] == 687.47               # target still returned for audit-managed TP


def test_plan_entry_fractional_rejects_nonpositive_qty():
    assert tm.plan_entry("X", 10.0, 9.0, 0, phase=1, fractional=True)["reject_reason"] is not None


def test_plan_entry_whole_unchanged_when_not_fractional():
    p = tm.plan_entry("MSFT", entry=100.0, stop=95.0, qty=3, phase=1)  # fractional defaults False
    assert p["orders"][0]["order_class"] == "bracket"
    assert p["orders"][0]["time_in_force"] == "gtc"


def _frac_snap(**over):
    snap = {"symbol": "META", "entry": 625.0, "qty": 0.24, "position_qty": 0.24,
            "fractional": True, "target": 687.47, "last_price": 640.0,
            "stop_price": 593.75, "stop_order": {"id": "s", "stop_price": 593.75}}
    snap.update(over)
    return snap


def test_audit_fractional_sells_when_target_hit():
    r = tm.audit(_frac_snap(last_price=690.0))     # above target -> managed take-profit
    assert any(a["op"] == "sell" for a in r["actions"])


def test_audit_fractional_replaces_expired_day_stop():
    r = tm.audit(_frac_snap(stop_order=None))      # DAY stop expired at close
    a = next(a for a in r["actions"] if a["op"] == "place_stop")
    assert a["tif"] == "day"
    assert a["qty"] == 0.24
    assert a["stop_price"] == 593.75


def test_audit_fractional_holds_when_protected_and_below_target():
    r = tm.audit(_frac_snap())                     # protected, price < target
    assert r["actions"] == [{"op": "noop"}]


def test_audit_fractional_target_takes_priority_over_stop_replace():
    # if both target is hit AND stop is missing, exit (sell) — don't bother re-stopping
    r = tm.audit(_frac_snap(last_price=690.0, stop_order=None))
    ops = [a["op"] for a in r["actions"]]
    assert "sell" in ops and "place_stop" not in ops
