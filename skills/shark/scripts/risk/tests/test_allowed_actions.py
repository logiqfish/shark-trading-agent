"""Allowed-actions pre-gate (SHARK_WHOLE_SWING_V2) — risk skill tests.

Computes the legal action set per candidate BEFORE the brain decides, so the
model can only pick pre-validated legal moves. Pure: caller supplies
today_activity (broker truth). Mirrors gate()'s rules/constants.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import risk


ACCT = {"equity": 25000.0, "cash": 25000.0,
        "day_start_equity": 25000.0, "last_equity": 25000.0}
NO_ACT = {"traded_today": [], "stopped_today": []}


def _aa(account=None, positions=None, candidates=None, today=None):
    return risk.allowed_actions(
        account or ACCT,
        positions or [],
        candidates if candidates is not None else [{"ticker": "NVDA", "price": 200.0}],
        today or NO_ACT,
        whole_swing=True,
    )


# --- clean path --------------------------------------------------------------

def test_clean_candidate_is_buyable_with_capped_max_qty():
    out = _aa()
    assert out["new_entries_allowed"] is True
    assert out["account_blockers"] == []
    nvda = out["candidates"]["NVDA"]
    assert nvda["actions"] == ["buy"]
    assert nvda["blockers"] == []
    # pos cap 20% of 25000 = $5000 -> floor(5000/200) = 25 (binds below cash).
    assert nvda["max_qty"] == 25


def test_slots_remaining_reflects_open_positions():
    positions = [{"ticker": "AMD", "market_value": 1000.0},
                 {"ticker": "MU", "market_value": 1000.0}]
    out = _aa(positions=positions)
    assert out["slots_remaining"] == 6   # 8 - 2


# --- per-ticker blockers -----------------------------------------------------

def test_already_held_is_hold_only():
    positions = [{"ticker": "NVDA", "market_value": 1000.0}]
    out = _aa(positions=positions)
    nvda = out["candidates"]["NVDA"]
    assert nvda["actions"] == ["hold"]
    assert "already_held" in nvda["blockers"]


def test_traded_today_blocks_reentry():
    out = _aa(today={"traded_today": ["NVDA"], "stopped_today": []})
    nvda = out["candidates"]["NVDA"]
    assert nvda["actions"] == ["hold"]
    assert "traded_today" in nvda["blockers"]


def test_stopped_today_blocks_rebuy_the_loophole():
    out = _aa(today={"traded_today": ["NVDA"], "stopped_today": ["NVDA"]})
    nvda = out["candidates"]["NVDA"]
    assert nvda["actions"] == ["hold"]
    assert "stopped_today" in nvda["blockers"]


def test_cap_breach_when_one_share_exceeds_position_cap():
    # price 6000 -> floor(5000/6000) = 0 whole shares fit under the 20% cap.
    out = _aa(candidates=[{"ticker": "XPENSIVE", "price": 6000.0}])
    c = out["candidates"]["XPENSIVE"]
    assert c["actions"] == ["hold"]
    assert "would_breach_cap" in c["blockers"]
    assert c["max_qty"] == 0


# --- account-level blockers (block every candidate) --------------------------

def test_daily_loss_halt_blocks_all_new_entries():
    acct = dict(ACCT, equity=24200.0)   # -800 vs 25000 day-start; limit -750
    out = _aa(account=acct)
    assert out["new_entries_allowed"] is False
    assert "daily_loss_halt" in out["account_blockers"]
    assert out["candidates"]["NVDA"]["actions"] == ["hold"]


def test_drawdown_dire_blocks_all_new_entries():
    acct = dict(ACCT, equity=23700.0)   # -1300 vs last_equity 25000; limit -1250
    out = _aa(account=acct)
    assert out["new_entries_allowed"] is False
    assert "drawdown" in out["account_blockers"]


def test_no_open_slots_blocks_all_new_entries():
    positions = [{"ticker": f"T{i}", "market_value": 1000.0} for i in range(8)]
    out = _aa(positions=positions)
    assert out["new_entries_allowed"] is False
    assert "no_open_slots" in out["account_blockers"]
    assert out["slots_remaining"] == 0


# --- robustness --------------------------------------------------------------

def test_empty_candidates_still_reports_account_state():
    out = _aa(candidates=[])
    assert out["candidates"] == {}
    assert out["new_entries_allowed"] is True


def test_tolerates_missing_fields():
    # missing price / market_value / day_start must not raise
    out = risk.allowed_actions(
        {"equity": 25000.0, "cash": 25000.0},
        [{"ticker": "AMD"}],
        [{"ticker": "NVDA"}],
        {},
        whole_swing=True,
    )
    assert "NVDA" in out["candidates"]


# --- latching daily-loss circuit-breaker (session_low_equity) ----------------

def test_allowed_actions_latches_on_session_low():
    from risk import allowed_actions
    account = {"equity": 24_900, "day_start_equity": 25_000, "session_low_equity": 24_200}
    res = allowed_actions(account, positions=[], candidates=[{"ticker": "AAPL", "price": 100}],
                          today_activity={}, whole_swing=True)
    assert "daily_loss_halt" in res["account_blockers"]


def test_allowed_actions_fallback_no_session_low():
    from risk import allowed_actions
    account = {"equity": 24_200, "day_start_equity": 25_000}
    res = allowed_actions(account, positions=[], candidates=[{"ticker": "AAPL", "price": 100}],
                          today_activity={}, whole_swing=True)
    assert "daily_loss_halt" in res["account_blockers"]


def test_allowed_actions_cash_qty_uses_settled_buying_power():
    acct = {"equity": 10000, "cash": 5000, "buying_power": 1500}
    out = risk.allowed_actions(acct, positions=[],
                               candidates=[{"ticker": "AAA", "price": 100}],
                               today_activity={}, whole_swing=True)
    assert out["candidates"]["AAA"]["max_qty"] == 5

def test_allowed_actions_cash_qty_margin_unchanged():
    # buying_power (20000) >= cash (5000) -> _spendable=cash=5000, unchanged.
    # cap_qty = floor(20%*10000 / 100) = 20; cash_qty = floor((5000-1000)/100) = 40
    # max_qty = min(cap_qty, cash_qty) = 20 — position cap binds, same as no buying_power.
    acct = {"equity": 10000, "cash": 5000, "buying_power": 20000}
    out = risk.allowed_actions(acct, positions=[],
                               candidates=[{"ticker": "AAA", "price": 100}],
                               today_activity={}, whole_swing=True)
    assert out["candidates"]["AAA"]["max_qty"] == 20
