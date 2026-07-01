"""Whole-Share Swing Profile v2 (SHARK_WHOLE_SWING_V2) — risk skill tests.

$25,000 account, whole shares only, fixed-fractional risk sizing:
the agent's protective stop is an INPUT, position size = dollar_risk / (entry-stop).
Conviction maps to a risk fraction (0.50%-1.25%); the stop decides how many shares.
Gated behind whole_swing=True / SHARK_WHOLE_SWING_V2; v1 + default behavior unchanged.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import risk


# --- size_v2: fixed-fractional risk sizing ---------------------------------

def test_v2_below_conviction_floor_rejects():
    r = risk.size_v2(25000.0, 100.0, 95.0, 64)
    assert r["qty"] == 0
    assert r["reject_reason"] == "below conviction floor"


def test_v2_band_65_69_is_half_percent():
    # 0.50% of 25000 = $125 risk; (100-95)=$5/share -> floor(25) = 25 shares.
    r = risk.size_v2(25000.0, 100.0, 95.0, 67)
    assert r["reject_reason"] is None
    assert r["risk_fraction"] == 0.0050
    assert r["qty"] == 25


def test_v2_band_70_79_is_three_quarter_percent():
    # 0.75% of 25000 = $187.5 risk; $5/share -> floor(37.5) = 37 shares.
    r = risk.size_v2(25000.0, 100.0, 95.0, 75)
    assert r["risk_fraction"] == 0.0075
    assert r["qty"] == 37


def test_v2_band_80_89_is_one_percent():
    # 1.00% of 25000 = $250 risk; $5/share -> 50 shares (notional 5000 = 20% cap).
    r = risk.size_v2(25000.0, 100.0, 95.0, 85)
    assert r["risk_fraction"] == 0.0100
    assert r["qty"] == 50


def test_v2_band_90_100_is_max_125_percent():
    # 1.25% of 25000 = $312.5 risk; (100-90)=$10/share -> floor(31.25) = 31.
    r = risk.size_v2(25000.0, 100.0, 90.0, 95)
    assert r["risk_fraction"] == 0.0125
    assert r["qty"] == 31


def test_v2_stop_at_or_above_entry_rejects():
    assert risk.size_v2(25000.0, 100.0, 100.0, 85)["reject_reason"] == "stop not below entry"
    assert risk.size_v2(25000.0, 100.0, 105.0, 85)["reject_reason"] == "stop not below entry"


def test_v2_risk_budget_too_small_for_one_share_rejects():
    # $125 risk, (200-50)=$150/share -> floor(0.83) = 0 -> reject.
    r = risk.size_v2(25000.0, 200.0, 50.0, 65)
    assert r["qty"] == 0
    assert r["reject_reason"] == "risk budget below one share"


def test_v2_position_over_allocation_cap_rejects_not_trims():
    # Tight stop blows up share count: $312.5 risk / $0.50 = 625 shares,
    # 625*100 = $62,500 >> 20% cap ($5,000). Skip the trade, do NOT trim.
    r = risk.size_v2(25000.0, 100.0, 99.5, 90)
    assert r["qty"] == 0
    assert r["reject_reason"] == "position exceeds allocation cap"


def test_v2_size_adapts_to_volatility():
    # Same conviction, wider stop -> fewer shares for the same dollar risk.
    wide = risk.size_v2(25000.0, 100.0, 90.0, 85)["qty"]   # $10/share -> 25
    tight = risk.size_v2(25000.0, 100.0, 95.0, 85)["qty"]  # $5/share  -> 50
    assert wide < tight


def test_v2_nonpositive_inputs_reject():
    assert risk.size_v2(0.0, 100.0, 95.0, 85)["reject_reason"] == "non-positive equity or price"
    assert risk.size_v2(25000.0, 0.0, 0.0, 85)["reject_reason"] == "non-positive equity or price"
    assert risk.size_v2(25000.0, -100.0, -110.0, 85)["reject_reason"] == "non-positive equity or price"


# --- gate(whole_swing=True): scaled gates + agent-stop R/R ------------------

def _acct(equity=25000, cash=25000, **kw):
    a = {"equity": equity, "cash": cash}
    a.update(kw)
    return a


def test_v2_rr_uses_agent_stop_not_derived():
    # entry 100, agent stop 80 -> risk $20, target 130 -> reward $30 -> R/R 1.5 < 2.
    # (A derived 5% stop would give R/R 6 and wrongly pass; this proves agent-stop use.)
    cand = {"ticker": "AAA", "price": 100, "qty": 10, "stop_price": 80, "target_price": 130}
    out = risk.gate(_acct(), cand, positions=[], whole_swing=True)
    assert "risk_reward" in out["gates_failed"]


def test_v2_rr_passes_with_adequate_agent_stop():
    # entry 100, stop 90 -> risk $10, target 130 -> reward $30 -> R/R 3 >= 2.
    cand = {"ticker": "AAA", "price": 100, "qty": 10, "stop_price": 90, "target_price": 130}
    out = risk.gate(_acct(), cand, positions=[], whole_swing=True)
    assert "risk_reward" not in out["gates_failed"]


def test_v2_max_open_positions_blocks_9th_new_symbol():
    # Cap raised 5 -> 8 on 2026-06-16 (profit-taking + cap-bump deploy).
    positions = [{"ticker": t, "market_value": 1000}
                 for t in ("AA", "BB", "CC", "DD", "EE", "FF", "GG", "HH")]
    cand = {"ticker": "II", "price": 100, "qty": 5, "stop_price": 90}
    out = risk.gate(_acct(), cand, positions, whole_swing=True)
    assert "max_open_positions" in out["gates_failed"]


def test_v2_max_open_positions_allows_8th_new_symbol():
    positions = [{"ticker": t, "market_value": 1000}
                 for t in ("AA", "BB", "CC", "DD", "EE", "FF", "GG")]
    cand = {"ticker": "HH", "price": 100, "qty": 5, "stop_price": 90}
    out = risk.gate(_acct(), cand, positions, whole_swing=True)
    assert "max_open_positions" not in out["gates_failed"]


def test_v2_daily_loss_halt_fires_at_minus_3_percent():
    # day-start 25000, now 24250 -> -750 = -3% exactly -> halt.
    acct = _acct(equity=24250, day_start_equity=25000)
    cand = {"ticker": "AAA", "price": 100, "qty": 1, "stop_price": 90}
    out = risk.gate(acct, cand, positions=[], whole_swing=True)
    assert "daily_loss_halt" in out["gates_failed"]


def test_v2_daily_loss_halt_clear_above_minus_3_percent():
    acct = _acct(equity=24300, day_start_equity=25000)  # -700, still trading
    cand = {"ticker": "AAA", "price": 100, "qty": 1, "stop_price": 90}
    out = risk.gate(acct, cand, positions=[], whole_swing=True)
    assert "daily_loss_halt" not in out["gates_failed"]


def test_v2_blocks_averaging_into_a_loser():
    positions = [{"ticker": "AAA", "market_value": 1000, "unrealized_pl": -50}]
    cand = {"ticker": "AAA", "price": 100, "qty": 5, "stop_price": 90}
    out = risk.gate(_acct(), cand, positions, whole_swing=True)
    assert "averaging_down" in out["gates_failed"]


# --- _decide: SHARK_WHOLE_SWING_V2 routing ---------------------------------

def test_decide_v2_flag_routes_and_passes(monkeypatch):
    monkeypatch.setenv("SHARK_WHOLE_SWING_V2", "1")
    payload = {
        "account": {"equity": 25000, "cash": 25000, "day_start_equity": 25000},
        "candidate": {"ticker": "AAA", "price": 100, "conviction": 85,
                      "stop_price": 90, "target_price": 130},
        "positions": [],
    }
    verdict, code = risk._decide(payload)
    assert verdict["whole_swing"] is True
    assert verdict["qty"] == 25          # 1% * 25000 / (100-90) = 25 shares
    assert verdict["pass"] is True
    assert code == 0


def test_decide_v2_missing_stop_rejects(monkeypatch):
    monkeypatch.setenv("SHARK_WHOLE_SWING_V2", "1")
    payload = {
        "account": {"equity": 25000, "cash": 25000},
        "candidate": {"ticker": "AAA", "price": 100, "conviction": 85},  # no stop_price
        "positions": [],
    }
    verdict, code = risk._decide(payload)
    assert verdict["pass"] is False
    assert verdict["reject_reason"] == "missing protective stop"


def test_decide_v2_off_by_default_uses_legacy_sizing(monkeypatch):
    monkeypatch.delenv("SHARK_WHOLE_SWING_V2", raising=False)
    payload = {
        "account": {"equity": 10000, "cash": 10000},
        "candidate": {"ticker": "AAA", "price": 100, "conviction": 90},
        "positions": [],
    }
    verdict, code = risk._decide(payload)
    assert verdict.get("whole_swing") in (False, None)
    assert verdict["qty"] == 20          # legacy 20% conviction-tier path


# --- latching daily-loss circuit-breaker (session_low_equity) ----------------

def test_daily_loss_latches_on_session_low_even_after_recovery():
    """Session low breached -3% earlier; current equity has recovered above it.
    The breaker must STILL trip (latching) — this is the whole point."""
    from risk import gate
    account = {
        "equity": 24_900,          # recovered to only -0.4%
        "day_start_equity": 25_000,
        "session_low_equity": 24_200,  # but the low hit -3.2% earlier today
    }
    candidate = {"ticker": "AAPL", "price": 100, "conviction": 80, "stop_price": 98}
    res = gate(account, candidate, positions=[], whole_swing=True)
    assert "daily_loss_halt" in res["gates_failed"]


def test_daily_loss_does_not_trip_when_session_low_above_line():
    from risk import gate
    account = {
        "equity": 24_800,
        "day_start_equity": 25_000,
        "session_low_equity": 24_400,  # low only -2.4%, above the -3% line
    }
    candidate = {"ticker": "AAPL", "price": 100, "conviction": 80, "stop_price": 98}
    res = gate(account, candidate, positions=[], whole_swing=True)
    assert "daily_loss_halt" not in res["gates_failed"]


def test_daily_loss_falls_back_to_current_equity_when_no_session_low():
    """No session_low (fetch failed) -> point-in-time on current equity (legacy)."""
    from risk import gate
    account = {"equity": 24_200, "day_start_equity": 25_000}  # -3.2% now, no low
    candidate = {"ticker": "AAPL", "price": 100, "conviction": 80, "stop_price": 98}
    res = gate(account, candidate, positions=[], whole_swing=True)
    assert "daily_loss_halt" in res["gates_failed"]


def test_daily_loss_trips_at_exact_minus_3pct_session_low():
    """Boundary: session low exactly -3% (with equity recovered) must trip (epsilon)."""
    from risk import gate
    account = {"equity": 24_900, "day_start_equity": 25_000,
               "session_low_equity": 24_250.0}  # exactly -3% of 25_000
    candidate = {"ticker": "AAPL", "price": 100, "conviction": 80, "stop_price": 98}
    res = gate(account, candidate, positions=[], whole_swing=True)
    assert "daily_loss_halt" in res["gates_failed"]


def test_daily_loss_nonfinite_session_low_falls_back_not_noop():
    """A NaN session_low must NOT silently no-op the halt — fall back to current
    equity (itself down -3.2% here) so the gate still trips."""
    from risk import gate
    account = {"equity": 24_200, "day_start_equity": 25_000,
               "session_low_equity": float("nan")}
    candidate = {"ticker": "AAPL", "price": 100, "conviction": 80, "stop_price": 98}
    res = gate(account, candidate, positions=[], whole_swing=True)
    assert "daily_loss_halt" in res["gates_failed"]


def test_daily_loss_unparseable_session_low_falls_back_no_crash():
    """Garbage string session_low -> fall back to current equity, no exception."""
    from risk import gate
    account = {"equity": 24_900, "day_start_equity": 25_000,
               "session_low_equity": "bad"}  # equity recovered -> no trip via fallback
    candidate = {"ticker": "AAPL", "price": 100, "conviction": 80, "stop_price": 98}
    res = gate(account, candidate, positions=[], whole_swing=True)
    assert "daily_loss_halt" not in res["gates_failed"]


# --- size_v2 discretionary mode -----------------------------------------------

def test_size_v2_discretionary_bypasses_conviction_floor():
    rej = risk.size_v2(10000, 100, 95, 25)
    assert rej["qty"] == 0 and rej["reject_reason"] == "below conviction floor"
    ok = risk.size_v2(10000, 100, 95, 25, discretionary=True)
    assert ok["qty"] >= 1 and ok["reject_reason"] is None


def test_size_v2_discretionary_below_floor_uses_floor_band():
    gut = risk.size_v2(10000, 100, 95, 25, discretionary=True)
    floor = risk.size_v2(10000, 100, 95, 65)
    assert gut["qty"] == floor["qty"]
    assert gut["risk_fraction"] == floor["risk_fraction"]


def test_size_v2_discretionary_still_enforces_allocation_cap():
    # entry=100, stop=99 -> per_share_risk=$1; floor band 0.50%*10000=$50 -> qty=50
    # notional=50*100=$5000 > 20% cap ($2000) -> allocation cap fires even with discretionary.
    out = risk.size_v2(10000, 100, 99, 25, discretionary=True)
    assert out["qty"] == 0 and out["reject_reason"] == "position exceeds allocation cap"


def test_size_v2_discretionary_noop_at_or_above_floor():
    base = risk.size_v2(10000, 100, 95, 90)
    disc = risk.size_v2(10000, 100, 95, 90, discretionary=True)
    assert base == disc


# --- _decide_v2 discretionary threading ---------------------------------------

def _disc_payload(conviction=25, discretionary=True, positions=None):
    return {
        "account": {"equity": 10000, "cash": 10000},
        "candidate": {"ticker": "AAA", "price": 100, "conviction": conviction,
                      "stop_price": 95, "discretionary": discretionary},
        "positions": positions or [],
    }


def test_decide_v2_discretionary_sizes_and_passes_below_floor():
    verdict, code = risk._decide(_disc_payload(), whole_swing=True)
    assert verdict["discretionary"] is True
    assert verdict["qty"] >= 1 and verdict["reject_reason"] is None
    assert verdict["pass"] is True and code == 0


def test_decide_v2_without_discretionary_still_rejects_below_floor():
    verdict, code = risk._decide(_disc_payload(discretionary=False), whole_swing=True)
    assert verdict["qty"] == 0 and verdict["reject_reason"] == "below conviction floor"
    assert verdict["pass"] is False and code == 10


def test_decide_v2_discretionary_does_not_bypass_concentration():
    positions = [{"ticker": "AAA", "market_value": 3000}]
    verdict, code = risk._decide(_disc_payload(positions=positions), whole_swing=True)
    assert verdict["pass"] is False and code == 10
    assert "concentration" in verdict["dire_triggers"] or "max_position" in verdict["gates_failed"]


def test_decide_v2_string_false_discretionary_does_not_bypass_floor():
    p = _disc_payload(discretionary="false")
    verdict, code = risk._decide(p, whole_swing=True)
    assert verdict["discretionary"] is False
    assert verdict["reject_reason"] == "below conviction floor" and code == 10


def test_decide_v2_string_true_discretionary_bypasses_floor():
    p = _disc_payload(discretionary="true")
    verdict, code = risk._decide(p, whole_swing=True)
    assert verdict["discretionary"] is True and verdict["qty"] >= 1 and code == 0


def test_size_v2_discretionary_at_exact_floor_conviction():
    base = risk.size_v2(10000, 100, 95, 65)
    disc = risk.size_v2(10000, 100, 95, 65, discretionary=True)
    assert base == disc and base["reject_reason"] is None
