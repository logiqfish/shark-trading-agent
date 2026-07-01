"""SHARK_FRACTIONAL — fractional sizing tests for the risk skill (stdlib only).

Fractional mode lets a small account buy a sub-share of an expensive stock
(e.g. $1000 acct, $625 stock). It is gated behind the SHARK_FRACTIONAL flag;
default (whole-shares) behavior is unchanged.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import risk


def test_size_fractional_allows_subshare_of_expensive_stock():
    # $1000 equity, $625 stock, conviction 65 -> tier 0.15 -> $150 notional -> 0.24 shares
    r = risk.size(1000.0, 625.0, 65, fractional=True)
    assert r["reject_reason"] is None
    assert abs(r["qty"] - round(0.15 * 1000 / 625, 6)) < 1e-9     # ~0.24
    assert r["stop_price"] == round(625.0 * 0.95, 2)


def test_size_whole_still_rejects_subshare_by_default():
    # Same trade WITHOUT fractional -> floor(150/625)=0 -> rejected (current behavior)
    r = risk.size(1000.0, 625.0, 65, fractional=False)
    assert r["reject_reason"] is not None
    assert r["qty"] == 0


def test_size_fractional_rejects_below_min_notional():
    # tiny equity -> 0.15 * $5 = $0.75 notional, below Alpaca's $1 minimum
    r = risk.size(5.0, 625.0, 65, fractional=True)
    assert r["reject_reason"] is not None
    assert r["qty"] == 0


def test_size_fractional_respects_max_position_cap():
    r = risk.size(1000.0, 100.0, 90, fractional=True)   # tier 0.20
    assert r["reject_reason"] is None
    assert r["qty"] * 100.0 <= 0.20 * 1000 + 1e-6


def test_gate_accepts_fractional_qty():
    # gate must not truncate a fractional qty to int (0.24 -> 0 would break notional)
    acct = {"equity": 1000.0, "cash": 1000.0}
    cand = {"ticker": "META", "price": 625.0, "qty": 0.24, "target_price": 687.5}
    r = risk.gate(acct, cand, [])
    assert "max_position" not in r["gates_failed"]      # notional 150 <= 200
    assert "cash_reserve" not in r["gates_failed"]      # 1000-150 >= 100
