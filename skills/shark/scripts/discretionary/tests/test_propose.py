import discretionary as disc


def runners(*, control_exit=0, markov_exit=0, catalyst="news:2",
            risk_exit=0, risk_verdict=None, risk_spy=None):
    """Fake injected siblings. risk_spy: a list to capture the base payload
    handed to risk (so tests can assert the derived stop / discretionary flag)."""
    rv = risk_verdict if risk_verdict is not None else {
        "pass": True, "qty": 8, "stop_price": 222.0,
        "gates_failed": [], "dire_triggers": [], "reject_reason": None,
    }

    def risk(base):
        if risk_spy is not None:
            risk_spy.append(base)
        return {"exit": risk_exit, "verdict": rv}

    return {
        "control": lambda: {"exit": control_exit, "mode": "paper"},
        "markov": lambda: {"exit": markov_exit},
        "catalyst": lambda t: catalyst,
        "risk": risk,
    }


def payload(stop=None, conviction=25, equity=25000.0):
    cand = {"ticker": "ttwo", "price": 240.0, "conviction": conviction}
    if stop is not None:
        cand["stop"] = stop
    return {"account": {"equity": equity}, "positions": [], "candidate": cand}


def test_control_halt_hard_blocks():
    out = disc.propose(payload(), runners(control_exit=10))
    assert out["ok"] is False and out["hard_block"] == "control"


def test_markov_veto_hard_blocks():
    out = disc.propose(payload(), runners(markov_exit=10))
    assert out["ok"] is False and out["hard_block"] == "regime"


def test_markov_passthrough_does_not_block():
    # exit 20 is fail-open by veto.sh contract -> proceed.
    out = disc.propose(payload(stop=222.0), runners(markov_exit=20))
    assert out["ok"] is True


def test_risk_gate_fail_hard_blocks_with_gate_name():
    rv = {"pass": False, "qty": 0, "stop_price": 0.0,
          "gates_failed": ["concentration"], "dire_triggers": [],
          "reject_reason": None}
    out = disc.propose(payload(stop=222.0), runners(risk_exit=10, risk_verdict=rv))
    assert out["ok"] is False and out["hard_block"] == "concentration"


def test_happy_path_builds_card():
    out = disc.propose(payload(stop=222.0), runners())
    assert out["ok"] is True
    assert out["ticker"] == "TTWO"
    assert out["qty"] == 8
    assert out["stop"] == 222.0
    assert out["target"] == 276.0          # 240 + 2*(240-222)
    assert out["equity_pct"] == 0.0768     # 8*240/25000
    assert out["conviction"] == 25
    assert out["catalyst"] == "news:2"


def test_missing_stop_auto_derives_5pct_below():
    spy = []
    disc.propose(payload(stop=None), runners(risk_spy=spy))
    assert spy[0]["candidate"]["stop_price"] == 228.0   # round(240*0.95, 2)
    assert spy[0]["candidate"]["discretionary"] is True


def test_string_conviction_coerces_not_crashes():
    # A JSON string like "72.5" must not raise; coerce to int 72.
    spy = []
    out = disc.propose(payload(stop=222.0, conviction="72.5"), runners(risk_spy=spy))
    assert out["ok"] is True
    assert out["conviction"] == 72
    assert spy[0]["candidate"]["conviction"] == 72


def test_non_numeric_operator_stop_falls_back_to_5pct():
    # A bad operator stop ("false") must degrade to the 5%-below default,
    # never crash and never go naked.
    spy = []
    out = disc.propose(payload(stop="false"), runners(risk_spy=spy))
    assert out["ok"] is True
    assert spy[0]["candidate"]["stop_price"] == 228.0   # round(240*0.95, 2)
