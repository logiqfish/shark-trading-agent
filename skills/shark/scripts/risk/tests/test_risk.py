from datetime import datetime, timedelta, timezone

import risk


def test_size_below_conviction_floor_rejects():
    out = risk.size(equity=10000, price=100, conviction=64)
    assert out["qty"] == 0
    assert out["reject_reason"] == "below conviction floor"


def test_size_tier_65_79_uses_15pct_upper_bound():
    # 15% of 10000 = 1500; floor(1500/100) = 15 shares
    out = risk.size(equity=10000, price=100, conviction=65)
    assert out["target_pct"] == 0.15
    assert out["qty"] == 15
    assert out["reject_reason"] is None
    out79 = risk.size(equity=10000, price=100, conviction=79)
    assert out79["qty"] == 15


def test_size_tier_80_89_uses_20pct():
    out = risk.size(equity=10000, price=100, conviction=80)
    assert out["target_pct"] == 0.20
    assert out["qty"] == 20


def test_size_tier_90_100_uses_20pct():
    out = risk.size(equity=10000, price=100, conviction=95)
    assert out["target_pct"] == 0.20
    assert out["qty"] == 20


def test_size_floors_to_whole_shares():
    # 15% of 10000 = 1500; price 130 -> 11.53 -> floor 11
    out = risk.size(equity=10000, price=130, conviction=70)
    assert out["qty"] == 11


def test_size_rejects_when_single_share_exceeds_cap():
    # one 2500 share vs 20% of 10000 = 2000 cap -> qty 0
    out = risk.size(equity=10000, price=2500, conviction=70)
    assert out["qty"] == 0
    assert out["reject_reason"] == "single share exceeds tier cap"


def test_size_hard_cap_backstop_never_exceeds_20pct():
    out = risk.size(equity=10000, price=100, conviction=100)
    # notional 20*100 == exactly 20% of 10000 — pin the equality boundary
    assert out["qty"] == 20
    assert out["qty"] * 100 <= 0.20 * 10000


def test_size_stop_price_is_5pct_below_entry_rounded():
    out = risk.size(equity=10000, price=100, conviction=70)
    assert out["stop_price"] == 95.0


def test_size_rejects_non_positive_inputs():
    assert risk.size(equity=0, price=100, conviction=70)["qty"] == 0
    assert risk.size(equity=10000, price=0, conviction=70)["qty"] == 0


def _account(equity=10000, cash=10000, last_equity=None):
    a = {"equity": equity, "cash": cash}
    if last_equity is not None:
        a["last_equity"] = last_equity
    return a


def test_gate_max_position_pass_at_boundary():
    # qty*price = 2000 == 20% of 10000 -> pass (not over)
    cand = {"ticker": "AAA", "price": 100, "qty": 20}
    out = risk.gate(_account(), cand, positions=[])
    assert "max_position" not in out["gates_failed"]


def test_gate_max_position_fail_over_boundary():
    cand = {"ticker": "AAA", "price": 100, "qty": 21}  # 2100 > 2000
    out = risk.gate(_account(), cand, positions=[])
    assert "max_position" in out["gates_failed"]
    assert out["pass"] is False


def test_gate_cash_reserve_fail_when_reserve_breached():
    # equity 10000 -> reserve floor 1000; cash 1500, notional 600 -> 900 < 1000
    cand = {"ticker": "AAA", "price": 100, "qty": 6}
    out = risk.gate(_account(equity=10000, cash=1500), cand, positions=[])
    assert "cash_reserve" in out["gates_failed"]


def test_gate_cash_reserve_pass_when_reserve_kept():
    cand = {"ticker": "AAA", "price": 100, "qty": 6}
    out = risk.gate(_account(equity=10000, cash=5000), cand, positions=[])
    assert "cash_reserve" not in out["gates_failed"]


def test_gate_risk_reward_pass_at_exactly_2to1():
    # price 100, stop 95 -> risk 5; target 110 -> reward 10 -> R/R 2.0
    cand = {"ticker": "AAA", "price": 100, "qty": 10, "target_price": 110}
    out = risk.gate(_account(), cand, positions=[])
    assert "risk_reward" not in out["gates_failed"]


def test_gate_risk_reward_fail_below_2to1():
    cand = {"ticker": "AAA", "price": 100, "qty": 10, "target_price": 109}
    out = risk.gate(_account(), cand, positions=[])
    assert "risk_reward" in out["gates_failed"]


def test_gate_risk_reward_no_target_is_note_not_failure():
    cand = {"ticker": "AAA", "price": 100, "qty": 10}
    out = risk.gate(_account(), cand, positions=[])
    assert "risk_reward" not in out["gates_failed"]
    assert out["notes"].get("risk_reward") == "no_target"


def test_gate_risk_reward_passes_at_2to1_on_cent_quantized_low_price():
    # Regression: price 1.10, stop round(1.045,2)=1.04, risk 0.06,
    # target 1.22 -> reward 0.12 -> exactly 2:1. Raw float division yields
    # 1.9999999999999962 and would spuriously fail; cross-multiply must pass.
    cand = {"ticker": "AAA", "price": 1.10, "qty": 1, "target_price": 1.22}
    out = risk.gate(_account(), cand, positions=[])
    assert "risk_reward" not in out["gates_failed"]


def test_gate_risk_reward_unparseable_target_degrades_to_note():
    cand = {"ticker": "AAA", "price": 100, "qty": 10, "target_price": "N/A"}
    out = risk.gate(_account(), cand, positions=[])
    assert "risk_reward" not in out["gates_failed"]
    assert out["notes"].get("risk_reward") == "no_target"


def test_gate_cash_reserve_passes_at_exact_floor():
    # equity 10000 -> reserve floor 1000; cash 1600, notional 600 -> 1000 == floor.
    # Strict `<` means exactly-at-floor must pass.
    cand = {"ticker": "AAA", "price": 100, "qty": 6}
    out = risk.gate(_account(equity=10000, cash=1600), cand, positions=[])
    assert "cash_reserve" not in out["gates_failed"]


def test_gate_max_position_fails_when_equity_non_positive():
    cand = {"ticker": "AAA", "price": 100, "qty": 1}
    out = risk.gate(_account(equity=0, cash=0), cand, positions=[])
    assert "max_position" in out["gates_failed"]


def test_gate_collects_all_failures_no_short_circuit():
    # Over cap (qty 30 = 3000 > 2000), reserve breached (cash 100), and R/R 1:1.
    cand = {"ticker": "AAA", "price": 100, "qty": 30, "target_price": 105}
    out = risk.gate(_account(equity=10000, cash=100), cand, positions=[])
    assert "max_position" in out["gates_failed"]
    assert "cash_reserve" in out["gates_failed"]
    assert "risk_reward" in out["gates_failed"]


NOW = datetime(2026, 6, 3, 12, 0, 0, tzinfo=timezone.utc)


def _catalyst_with_earnings_in(hours):
    when = NOW + timedelta(hours=hours)
    return {"earnings": {"next_earnings_date": when.isoformat()}}


def test_gate_concentration_fires_over_25pct():
    # existing 2000 in AAA + new 600 = 2600 > 25% of 10000 (2500)
    cand = {"ticker": "AAA", "price": 100, "qty": 6}
    positions = [{"ticker": "AAA", "market_value": 2000}]
    out = risk.gate(_account(), cand, positions, now=NOW)
    assert "concentration" in out["dire_triggers"]


def test_gate_concentration_clear_under_25pct():
    cand = {"ticker": "AAA", "price": 100, "qty": 4}  # 400 new, no existing
    out = risk.gate(_account(), cand, positions=[], now=NOW)
    assert "concentration" not in out["dire_triggers"]


def test_gate_drawdown_fires_at_5pct():
    # last_equity 10000 -> equity 9500 = exactly 5% drop
    cand = {"ticker": "AAA", "price": 100, "qty": 5}
    acct = _account(equity=9500, cash=9500, last_equity=10000)
    out = risk.gate(acct, cand, positions=[], now=NOW)
    assert "drawdown" in out["dire_triggers"]


def test_gate_drawdown_clear_under_5pct():
    cand = {"ticker": "AAA", "price": 100, "qty": 5}
    acct = _account(equity=9600, cash=9600, last_equity=10000)
    out = risk.gate(acct, cand, positions=[], now=NOW)
    assert "drawdown" not in out["dire_triggers"]
    assert "drawdown" not in out["notes"]


def test_gate_drawdown_fires_on_cent_quantized_true_5pct():
    # Regression: broker-shaped cents. 1081.00 -> 1026.95 is a true 5% drop,
    # but (le-equity)/le drifts to 0.04999999999999996 and the division form
    # would MISS the halt (the dangerous direction). Cross-multiply must fire.
    cand = {"ticker": "AAA", "price": 100, "qty": 1}
    acct = _account(equity=1026.95, cash=1026.95, last_equity=1081.00)
    out = risk.gate(acct, cand, positions=[], now=NOW)
    assert "drawdown" in out["dire_triggers"]


def test_gate_drawdown_note_when_last_equity_unparseable():
    cand = {"ticker": "AAA", "price": 100, "qty": 1}
    acct = {"equity": 9500, "cash": 9500, "last_equity": "N/A"}
    out = risk.gate(acct, cand, positions=[], now=NOW)
    assert out["notes"].get("drawdown") == "no_last_equity"
    assert "drawdown" not in out["dire_triggers"]


def test_gate_drawdown_note_when_no_last_equity():
    cand = {"ticker": "AAA", "price": 100, "qty": 5}
    out = risk.gate(_account(), cand, positions=[], now=NOW)
    assert out["notes"].get("drawdown") == "no_last_equity"


def test_gate_earnings_blackout_within_48h():
    cand = {"ticker": "AAA", "price": 100, "qty": 5}
    cat = _catalyst_with_earnings_in(24)
    out = risk.gate(_account(), cand, positions=[], catalyst=cat, now=NOW)
    assert out["earnings_check"] == "blackout"
    assert "earnings_blackout" in out["dire_triggers"]


def test_gate_earnings_clear_outside_48h():
    cand = {"ticker": "AAA", "price": 100, "qty": 5}
    cat = _catalyst_with_earnings_in(72)
    out = risk.gate(_account(), cand, positions=[], catalyst=cat, now=NOW)
    assert out["earnings_check"] == "clear"
    assert "earnings_blackout" not in out["dire_triggers"]


def test_gate_earnings_unknown_when_no_catalyst():
    cand = {"ticker": "AAA", "price": 100, "qty": 5}
    out = risk.gate(_account(), cand, positions=[], catalyst=None, now=NOW)
    assert out["earnings_check"] == "unknown"
    assert "earnings_blackout" not in out["dire_triggers"]


def test_gate_earnings_unknown_when_catalyst_has_no_earnings():
    cand = {"ticker": "AAA", "price": 100, "qty": 5}
    out = risk.gate(_account(), cand, positions=[], catalyst={"news": []}, now=NOW)
    assert out["earnings_check"] == "unknown"


def test_gate_earnings_trusts_service_within_48h_true():
    # Earnings-packet shape: precomputed within_48h=True drives blackout,
    # regardless of `now` (the packet already did the date math).
    cand = {"ticker": "AAA", "price": 100, "qty": 5}
    cat = {"earnings": {"within_48h": True, "next_report_date": "2026-07-30"}}
    out = risk.gate(_account(), cand, positions=[], catalyst=cat, now=NOW)
    assert out["earnings_check"] == "blackout"
    assert "earnings_blackout" in out["dire_triggers"]


def test_gate_earnings_trusts_service_within_48h_false():
    cand = {"ticker": "AAA", "price": 100, "qty": 5}
    cat = {"earnings": {"within_48h": False, "next_report_date": "2026-07-30"}}
    out = risk.gate(_account(), cand, positions=[], catalyst=cat, now=NOW)
    assert out["earnings_check"] == "clear"
    assert "earnings_blackout" not in out["dire_triggers"]


def test_gate_earnings_next_report_date_fallback_outside_48h():
    # No within_48h flag -> parse next_report_date (the real catalyst field).
    cand = {"ticker": "AAA", "price": 100, "qty": 5}
    cat = {"earnings": {"next_report_date": "2026-07-30"}}  # ~57d out from NOW
    out = risk.gate(_account(), cand, positions=[], catalyst=cat, now=NOW)
    assert out["earnings_check"] == "clear"


def test_decide_clean_pass_exit_0():
    payload = {
        "account": {"equity": 10000, "cash": 10000, "last_equity": 10000},
        "candidate": {"ticker": "AAA", "price": 100, "conviction": 70,
                      "target_price": 130},
        "positions": [],
    }
    verdict, code = risk._decide(payload, now=NOW)
    assert code == 0
    assert verdict["pass"] is True
    assert verdict["qty"] == 15            # 15% tier
    assert verdict["stop_price"] == 95.0
    assert verdict["ticker"] == "AAA"


def test_decide_sizing_reject_exit_10():
    payload = {
        "account": {"equity": 10000, "cash": 10000},
        "candidate": {"ticker": "AAA", "price": 100, "conviction": 50},
        "positions": [],
    }
    verdict, code = risk._decide(payload, now=NOW)
    assert code == 10
    assert verdict["pass"] is False
    assert verdict["reject_reason"] == "below conviction floor"


def test_decide_gate_fail_exit_10():
    # Sized fine but R/R below 2:1 -> gate fails.
    payload = {
        "account": {"equity": 10000, "cash": 10000, "last_equity": 10000},
        "candidate": {"ticker": "AAA", "price": 100, "conviction": 70,
                      "target_price": 105},
        "positions": [],
    }
    verdict, code = risk._decide(payload, now=NOW)
    assert code == 10
    assert "risk_reward" in verdict["gates_failed"]


def test_decide_injects_sized_qty_into_gate():
    # 90 conviction -> 20 shares @100 = 2000 == 20% cap, passes max_position.
    payload = {
        "account": {"equity": 10000, "cash": 10000, "last_equity": 10000},
        "candidate": {"ticker": "AAA", "price": 100, "conviction": 90,
                      "target_price": 130},
        "positions": [],
    }
    verdict, code = risk._decide(payload, now=NOW)
    assert verdict["qty"] == 20
    assert "max_position" not in verdict["gates_failed"]


import subprocess
from pathlib import Path

RISK_PY = str(Path(__file__).resolve().parent.parent / "risk.py")


def _run_cli(stdin_text):
    return subprocess.run(
        ["python3", RISK_PY], input=stdin_text,
        capture_output=True, text=True,
    )


def test_cli_bad_json_exits_3():
    r = _run_cli("not json{")
    assert r.returncode == 3


def test_cli_clean_pass_exits_0_and_emits_json():
    import json as _json
    payload = _json.dumps({
        "account": {"equity": 10000, "cash": 10000, "last_equity": 10000},
        "candidate": {"ticker": "AAA", "price": 100, "conviction": 70,
                      "target_price": 130},
        "positions": [],
    })
    r = _run_cli(payload)
    assert r.returncode == 0
    out = _json.loads(r.stdout)
    assert out["qty"] == 15


def test_cli_reject_exits_10():
    import json as _json
    payload = _json.dumps({
        "account": {"equity": 10000, "cash": 10000},
        "candidate": {"ticker": "AAA", "price": 100, "conviction": 10},
        "positions": [],
    })
    r = _run_cli(payload)
    assert r.returncode == 10


def test_cli_non_dict_json_exits_3():
    # Valid JSON but not an object (LLM could emit a stray array/scalar) must
    # be treated as a parse failure (exit 3), never an uncaught traceback.
    for stray in ("[]", '"hi"', "5", "null"):
        r = _run_cli(stray)
        assert r.returncode == 3, f"{stray!r} -> {r.returncode}"


def test_cli_catalyst_file_override_drives_earnings_blackout(tmp_path):
    import json as _json
    # next earnings 24h out (relative to real now) -> within the 48h blackout.
    soon = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    cat = tmp_path / "cat.json"
    cat.write_text(_json.dumps({"earnings": {"next_earnings_date": soon}}))
    payload = _json.dumps({
        "account": {"equity": 10000, "cash": 10000, "last_equity": 10000},
        "candidate": {"ticker": "AAA", "price": 100, "conviction": 70,
                      "target_price": 130},
        "positions": [],
    })
    r = subprocess.run(
        ["python3", RISK_PY, "--catalyst-file", str(cat)],
        input=payload, capture_output=True, text=True,
    )
    out = _json.loads(r.stdout)
    assert out["earnings_check"] == "blackout"
    assert "earnings_blackout" in out["dire_triggers"]
    assert r.returncode == 10  # blackout is a dire-trigger -> do not trade


def test_spendable_uses_min_when_buying_power_present():
    assert risk._spendable({"cash": 1000, "buying_power": 400}) == 400.0

def test_spendable_margin_unchanged_when_buying_power_ge_cash():
    assert risk._spendable({"cash": 1000, "buying_power": 4000}) == 1000.0

def test_spendable_falls_back_to_cash_when_buying_power_absent():
    assert risk._spendable({"cash": 1000}) == 1000.0

def test_spendable_falls_back_to_cash_when_buying_power_unparseable():
    assert risk._spendable({"cash": 1000, "buying_power": "n/a"}) == 1000.0

def test_spendable_zero_buying_power_is_zero():
    # fully-unsettled cash account: nothing spendable -> blocks new trades
    assert risk._spendable({"cash": 1000, "buying_power": 0}) == 0.0

def test_gate_cash_reserve_blocks_when_buying_power_zero():
    cand = {"ticker": "AAA", "price": 100, "qty": 1}
    out = risk.gate({"equity": 10000, "cash": 5000, "buying_power": 0}, cand, positions=[])
    assert "cash_reserve" in out["gates_failed"]

def test_spendable_boolean_buying_power_falls_back_to_cash():
    assert risk._spendable({"cash": 1000, "buying_power": True}) == 1000.0


def test_gate_cash_reserve_uses_settled_buying_power():
    cand = {"ticker": "AAA", "price": 100, "qty": 6}
    acct = {"equity": 10000, "cash": 5000, "buying_power": 1200}
    out = risk.gate(acct, cand, positions=[])
    assert "cash_reserve" in out["gates_failed"]

def test_gate_cash_reserve_margin_unchanged_buying_power_ge_cash():
    cand = {"ticker": "AAA", "price": 100, "qty": 6}
    acct = {"equity": 10000, "cash": 5000, "buying_power": 20000}
    out = risk.gate(acct, cand, positions=[])
    assert "cash_reserve" not in out["gates_failed"]
