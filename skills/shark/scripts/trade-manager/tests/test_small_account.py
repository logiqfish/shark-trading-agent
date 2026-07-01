"""Small Account v1 intraday discipline — trade-manager decision-core tests.

Pure: the clock lives in the wrapper, which passes minutes_to_close in.
3:30pm ET = 30 min to close (no new entries); 3:45pm = 15 min (force-flat).
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import trade_manager as tm


def test_intraday_window_open_midday():
    w = tm.intraday_window(120)  # 2:00pm
    assert w["new_entries_allowed"] is True
    assert w["force_flat"] is False


def test_intraday_window_no_new_entries_after_330():
    w = tm.intraday_window(30)   # exactly 3:30pm
    assert w["new_entries_allowed"] is False
    assert w["force_flat"] is False


def test_intraday_window_force_flat_at_345():
    w = tm.intraday_window(15)   # exactly 3:45pm
    assert w["new_entries_allowed"] is False
    assert w["force_flat"] is True


def test_audit_force_flat_cancels_then_sells_then_verifies():
    snap = {
        "fractional": True, "force_flat": True, "position_qty": 0.24,
        "symbol": "ABC", "stop_order": "stop-1", "tp_order": "tp-1",
    }
    r = tm.audit(snap)
    assert r["state"] == "FLATTENING"
    ops = [a["op"] for a in r["actions"]]
    # cancel both resting exits, then market-sell, then verify flat — in order.
    assert ops == ["cancel", "cancel", "sell", "verify_flat"]
    sell = next(a for a in r["actions"] if a["op"] == "sell")
    assert sell["qty"] == 0.24 and sell["type"] == "market" and sell["tif"] == "day"


def test_audit_force_flat_ignored_when_not_fractional():
    snap = {"fractional": False, "force_flat": True, "position_qty": 5,
            "stop_order": "s1"}
    r = tm.audit(snap)
    assert r["state"] != "FLATTENING"


def test_audit_close_cancels_resting_sibling_exit():
    # The DAY limit filled; the DAY stop is still resting -> cancel it.
    snap = {
        "fractional": True, "position_qty": 0, "entry": 100.0,
        "symbol": "ABC", "stop_price": 95.0, "stop_order": "stop-1",
        "last_filled_exit": {"price": 110.0, "qty": 0.24, "role": "take_profit"},
    }
    r = tm.audit(snap)
    assert r["state"] == "CLOSED"
    cancels = [a for a in r["actions"] if a["op"] == "cancel"]
    assert any(c["id"] == "stop-1" for c in cancels)
    assert r["realized"] and r["realized"][0]["kind"] == "target_hit"


def test_audit_close_no_cancel_when_no_resting_orders():
    snap = {"position_qty": 0, "entry": 100.0, "symbol": "ABC",
            "last_filled_exit": {"price": 95.0, "qty": 1, "role": "stop_loss"}}
    r = tm.audit(snap)
    assert r["actions"] == []
