"""Phase 1 tests for the trade-manager decision core (stdlib only, no network).

Phase 1 scope: plan_entry() -> one full-size GTC bracket; audit() -> ENTERED/CLOSED
state machine with missing-stop repair and realized R-multiple logging.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import trade_manager as tm


# ---------------- plan_entry: the Phase 1 full bracket ----------------

def test_plan_entry_full_bracket_geometry():
    """+2R target from the given stop; one bracket order, whole shares, GTC."""
    p = tm.plan_entry("MSFT", entry=100.0, stop=95.0, qty=3, phase=1)
    assert p["reject_reason"] is None
    # 1R = 5; target = 100 + 2*5 = 110.00 -> dodged off the round number to 109.97
    assert p["target"] == 109.97
    assert len(p["orders"]) == 1
    o = p["orders"][0]
    assert o["symbol"] == "MSFT"
    assert o["qty"] == "3"
    assert o["side"] == "buy"
    assert o["time_in_force"] == "gtc"
    assert o["order_class"] == "bracket"
    assert o["take_profit"]["limit_price"] == "109.97"
    assert o["stop_loss"]["stop_price"] == "94.97"   # 95.00 dodged off the round number


def test_plan_entry_non_round_prices_not_dodged():
    """Prices already off .00/.50 are passed through unchanged."""
    p = tm.plan_entry("AMD", entry=123.40, stop=117.23, qty=4, phase=1)
    one_r = 123.40 - 117.23
    assert p["target"] == round(123.40 + 2 * one_r, 2)            # 135.74
    assert p["orders"][0]["stop_loss"]["stop_price"] == "117.23"


def test_plan_entry_rejects_qty_below_one():
    p = tm.plan_entry("F", entry=12.0, stop=11.4, qty=0, phase=1)
    assert p["reject_reason"] is not None
    assert p["orders"] == []


def test_plan_entry_rejects_stop_not_below_entry():
    p = tm.plan_entry("F", entry=12.0, stop=12.0, qty=3, phase=1)
    assert p["reject_reason"] is not None
    assert p["orders"] == []


def test_plan_entry_rejects_nonpositive_price():
    assert tm.plan_entry("F", entry=0.0, stop=-1.0, qty=3, phase=1)["reject_reason"] is not None


def test_plan_entry_phase1_is_single_order_even_with_large_qty():
    """Phase 1 never tranches — one bracket regardless of size (tranching is Phase 2)."""
    p = tm.plan_entry("NVDA", entry=200.0, stop=190.0, qty=42, phase=1)
    assert len(p["orders"]) == 1
    assert p["orders"][0]["qty"] == "42"


# ---------------- audit: the Phase 1 state machine ----------------

def _open_snapshot(**over):
    snap = {
        "symbol": "MSFT", "entry": 100.0, "qty": 3, "position_qty": 3,
        "stop_price": 95.0,
        "stop_order": {"id": "s1", "stop_price": 95.0, "qty": 3},
        "tp_order": {"id": "t1", "limit_price": 110.0, "qty": 3},
        "last_filled_exit": None,
    }
    snap.update(over)
    return snap


def test_audit_open_position_with_both_legs_holds():
    r = tm.audit(_open_snapshot())
    assert r["state"] == "ENTERED"
    assert r["actions"] == [{"op": "noop"}]
    assert r["realized"] == []


def test_audit_repairs_missing_stop():
    """Open position whose protective stop vanished -> place it (existing fix-missing-stop behavior)."""
    r = tm.audit(_open_snapshot(stop_order=None))
    assert r["state"] == "ENTERED"
    assert any(a["op"] == "place_stop" for a in r["actions"])
    a = next(a for a in r["actions"] if a["op"] == "place_stop")
    assert a["stop_price"] == 95.0
    assert a["qty"] == 3      # repairs for the CURRENT live qty


def test_audit_closed_on_stop_hit_logs_negative_r():
    snap = _open_snapshot(
        position_qty=0,
        last_filled_exit={"role": "stop_loss", "price": 95.0, "qty": 3},
    )
    r = tm.audit(snap)
    assert r["state"] == "CLOSED"
    assert len(r["realized"]) == 1
    real = r["realized"][0]
    assert real["pnl"] == round((95.0 - 100.0) * 3, 2)     # -15.00
    assert real["r_multiple"] == -1.0                       # exited at exactly -1R
    assert real["kind"] == "stop_hit"
    assert r["actions"] == []


def test_audit_closed_on_target_hit_logs_positive_r():
    snap = _open_snapshot(
        position_qty=0,
        last_filled_exit={"role": "take_profit", "price": 110.0, "qty": 3},
    )
    r = tm.audit(snap)
    assert r["state"] == "CLOSED"
    real = r["realized"][0]
    assert real["pnl"] == round((110.0 - 100.0) * 3, 2)     # +30.00
    assert real["r_multiple"] == 2.0                        # +2R
    assert real["kind"] == "target_hit"


def test_audit_closed_without_exit_detail_does_not_crash():
    r = tm.audit(_open_snapshot(position_qty=0, last_filled_exit=None))
    assert r["state"] == "CLOSED"
    assert r["realized"] == []        # nothing to log, but no crash


def test_audit_never_emits_breakeven_or_trailing_in_phase1():
    """Phase 1 must not move stops on winners — that is Phase 2/3."""
    snap = _open_snapshot(position_qty=3)  # in profit territory irrelevant in P1
    r = tm.audit(snap)
    for a in r["actions"]:
        assert a["op"] in ("noop", "place_stop")    # never 'patch_stop'/'trail'


# ---------------- Phase 2: scale-out + breakeven ----------------

def _scale_snapshot(**over):
    # 1R = 5.00; +1R = 56.30; +2R = 61.30. Non-round entry so breakeven isn't dodged.
    snap = {
        "symbol": "MSFT", "entry": 51.30, "qty": 4, "position_qty": 4,
        "stop_price": 46.30,
        "stop_order": {"id": "s1", "stop_price": 46.30, "qty": 4},
        "tp_order": {"id": "t1", "limit_price": 61.30, "qty": 4},
        "last_filled_exit": None,
        "last_price": 56.30,   # exactly +1R
    }
    snap.update(over)
    return snap


def test_audit_scales_out_half_at_1R():
    r = tm.audit(_scale_snapshot())
    assert r["state"] == "ENTERED"
    # one cancel-and-rebuild action carrying everything the executor needs
    scale = next((a for a in r["actions"] if a["op"] == "scale_out"), None)
    assert scale is not None, r["actions"]
    assert scale["sell_qty"] == 2 and scale["runner_qty"] == 2   # floor/remainder of 4
    assert scale["breakeven"] == 51.30                            # = entry (non-magnet)
    assert scale["target"] == 61.30                              # +2R = 51.30 + 2*5
    assert scale["cancel_ids"] == ["s1", "t1"]                   # both resting legs
    assert r["realized"] == []


def test_audit_does_not_scale_below_1R():
    r = tm.audit(_scale_snapshot(last_price=55.00))   # below +1R (56.30)
    assert not any(a["op"] == "scale_out" for a in r["actions"])
    assert r["actions"] == [{"op": "noop"}]


def test_audit_does_not_rescale_once_scaled():
    # stop already lifted to breakeven (= already scaled) => never scale again, even
    # with the runner deep in profit. Detected from the stop position, not a tracked qty.
    r = tm.audit(_scale_snapshot(stop_price=51.27, position_qty=2, last_price=70.0))
    assert not any(a["op"] == "scale_out" for a in r["actions"])
    assert r["actions"] == [{"op": "noop"}]


def test_audit_scale_out_odd_qty_floors_the_sold_half():
    r = tm.audit(_scale_snapshot(qty=7, position_qty=7,
                                 stop_order={"id": "s1", "stop_price": 46.30, "qty": 7}))
    scale = next(a for a in r["actions"] if a["op"] == "scale_out")
    assert scale["sell_qty"] == 3          # floor(7/2)
    assert scale["runner_qty"] == 4        # runner keeps the larger half


def test_audit_single_share_moves_to_breakeven_no_scale():
    # 1 share can't be halved -> breakeven via a PRICE-ONLY stop move (spike-proven:
    # qty change is rejected on advanced orders, but stop_price change is accepted).
    r = tm.audit(_scale_snapshot(qty=1, position_qty=1,
                                 stop_order={"id": "s1", "stop_price": 46.30, "qty": 1}))
    assert not any(a["op"] == "scale_out" for a in r["actions"])
    mv = next(a for a in r["actions"] if a["op"] == "move_stop_breakeven")
    assert mv["id"] == "s1" and mv["stop_price"] == 51.30


def test_audit_repairs_missing_stop_even_when_price_high():
    # stop leg vanished -> repair it (safety) before anything else, never scale naked
    r = tm.audit(_scale_snapshot(position_qty=2, last_price=70.0, stop_order=None))
    assert not any(a["op"] == "scale_out" for a in r["actions"])
    assert any(a["op"] == "place_stop" for a in r["actions"])


# ---------------- CLI smoke ----------------

def test_cli_plan_entry_roundtrips_json():
    import json, subprocess
    mod = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "trade_manager.py")
    payload = json.dumps({"ticker": "MSFT", "entry": 100.0, "stop": 95.0, "qty": 3, "phase": 1})
    out = subprocess.run([sys.executable, mod, "plan_entry"], input=payload,
                         capture_output=True, text=True)
    assert out.returncode == 0
    data = json.loads(out.stdout)
    assert data["orders"][0]["order_class"] == "bracket"
