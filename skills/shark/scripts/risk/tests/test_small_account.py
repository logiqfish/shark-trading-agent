"""Small Account Profile v1 (SHARK_SMALL_ACCOUNT) — risk skill tests (stdlib only).

$1,000 account: 5%/$50 position cap, max 3 positions, -$15 daily-loss halt,
no averaging down. Gated behind small_account=True; default behavior unchanged.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import risk


def test_small_account_caps_position_at_50_dollars_whole():
    # $1000 equity, $40 stock, conviction 90 (tier 0.20 -> $200 desired) but
    # small-account cap is min(0.05*1000, 50) = $50 -> floor(50/40) = 1 share.
    r = risk.size(1000.0, 40.0, 90, small_account=True)
    assert r["reject_reason"] is None
    assert r["qty"] == 1


def test_small_account_caps_fractional_notional_at_50():
    # $1000 equity, $625 stock, conviction 65 -> small cap $50 -> 0.08 shares.
    r = risk.size(1000.0, 625.0, 65, fractional=True, small_account=True)
    assert r["reject_reason"] is None
    assert abs(r["qty"] - round(50.0 / 625.0, 6)) < 1e-9


def test_default_sizing_unchanged_when_small_account_false():
    # Regression: without the flag, the existing 20% math holds.
    r = risk.size(10000.0, 100.0, 90, small_account=False)
    assert r["qty"] == 20  # floor(0.20 * 10000 / 100)


def _acct(equity=1000, cash=1000, **kw):
    a = {"equity": equity, "cash": cash}
    a.update(kw)
    return a


def test_gate_small_account_position_cap_is_50():
    # notional $60 > $50 cap -> max_position fails under small_account.
    cand = {"ticker": "AAA", "price": 60, "qty": 1}
    out = risk.gate(_acct(), cand, positions=[], small_account=True)
    assert "max_position" in out["gates_failed"]


def test_gate_max_open_positions_blocks_4th_new_symbol():
    positions = [
        {"ticker": "AAA", "market_value": 40},
        {"ticker": "BBB", "market_value": 40},
        {"ticker": "CCC", "market_value": 40},
    ]
    cand = {"ticker": "DDD", "price": 40, "qty": 1}
    out = risk.gate(_acct(), cand, positions, small_account=True)
    assert "max_open_positions" in out["gates_failed"]


def test_gate_max_open_positions_allows_adding_to_held_symbol():
    positions = [{"ticker": "AAA", "market_value": 40},
                 {"ticker": "BBB", "market_value": 40},
                 {"ticker": "CCC", "market_value": 40}]
    cand = {"ticker": "AAA", "price": 40, "qty": 1}  # already held, not a new slot
    out = risk.gate(_acct(), cand, positions, small_account=True)
    assert "max_open_positions" not in out["gates_failed"]


def test_gate_daily_loss_halt_fires_at_minus_15():
    # baseline 1000, now 985 -> -15 exactly -> halt.
    acct = _acct(equity=985, day_start_equity=1000)
    cand = {"ticker": "AAA", "price": 10, "qty": 1}
    out = risk.gate(acct, cand, positions=[], small_account=True)
    assert "daily_loss_halt" in out["gates_failed"]


def test_gate_daily_loss_halt_clear_above_minus_15():
    acct = _acct(equity=990, day_start_equity=1000)  # -10, still trading
    cand = {"ticker": "AAA", "price": 10, "qty": 1}
    out = risk.gate(acct, cand, positions=[], small_account=True)
    assert "daily_loss_halt" not in out["gates_failed"]


def test_gate_daily_loss_halt_note_when_no_baseline():
    acct = _acct(equity=985)  # no day_start_equity
    cand = {"ticker": "AAA", "price": 10, "qty": 1}
    out = risk.gate(acct, cand, positions=[], small_account=True)
    assert "daily_loss_halt" not in out["gates_failed"]
    assert out["notes"].get("daily_loss_halt") == "no_day_start_equity"


def test_gate_blocks_averaging_into_a_loser():
    positions = [{"ticker": "AAA", "market_value": 40, "unrealized_pl": -5}]
    cand = {"ticker": "AAA", "price": 10, "qty": 1}
    out = risk.gate(_acct(), cand, positions, small_account=True)
    assert "averaging_down" in out["gates_failed"]


def test_gate_allows_adding_to_a_winner():
    positions = [{"ticker": "AAA", "market_value": 40, "unrealized_pl": 5}]
    cand = {"ticker": "AAA", "price": 10, "qty": 1}
    out = risk.gate(_acct(), cand, positions, small_account=True)
    assert "averaging_down" not in out["gates_failed"]


def test_decide_reads_small_account_env(monkeypatch):
    monkeypatch.setenv("SHARK_SMALL_ACCOUNT", "1")
    payload = {
        "account": {"equity": 1000, "cash": 1000, "day_start_equity": 1000},
        "candidate": {"ticker": "AAA", "price": 60, "conviction": 90},
        "positions": [],
    }
    verdict, code = risk._decide(payload)
    assert verdict["small_account"] is True
    # $60 stock, $50 cap, whole shares -> single share $60 > $50 -> rejected.
    assert verdict["pass"] is False


def test_decide_small_account_off_by_default(monkeypatch):
    monkeypatch.delenv("SHARK_SMALL_ACCOUNT", raising=False)
    payload = {
        "account": {"equity": 10000, "cash": 10000},
        "candidate": {"ticker": "AAA", "price": 100, "conviction": 90},
        "positions": [],
    }
    verdict, code = risk._decide(payload)
    assert verdict["small_account"] is False
    assert verdict["qty"] == 20
