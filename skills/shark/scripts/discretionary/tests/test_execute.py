import discretionary as disc


def test_real_risk_runner_forces_whole_swing_v2(monkeypatch):
    # Regression: discretionary's floor-bypass only exists in risk.py's v2 path,
    # gated by SHARK_WHOLE_SWING_V2=1. The real risk runner MUST set it, or every
    # below-floor gut trade is silently rejected (caught in a live Hermes test).
    captured = {}

    class _Proc:
        returncode = 0
        stdout = '{"pass": true, "qty": 1, "stop_price": 1.0}'

    def fake_sh(*args, stdin=None, env=None):
        captured["env"] = env
        return _Proc()

    monkeypatch.setattr(disc, "_sh", fake_sh)
    disc._real_runners()["risk"]({"account": {}, "candidate": {}, "positions": []})
    assert captured["env"]["SHARK_WHOLE_SWING_V2"] == "1"


def card(ok=True):
    return {"ok": ok, "ticker": "TTWO", "qty": 8, "entry": 240.0,
            "stop": 222.0, "target": 276.0, "conviction": 25,
            "date": "2026-06-24", "thesis": "gut call on the GTA6 cycle"}


def runners(*, enter_result=None, reflect_spy=None):
    er = enter_result if enter_result is not None else {"ok": True, "stage": "live", "buy_id": "x1"}

    def enter(ticker, qty, entry, stop):
        return er

    def reflect(slip):
        if reflect_spy is not None:
            reflect_spy.append(slip)

    return {"enter": enter, "reflect": reflect}


def test_proposal_not_ok_is_refused():
    out = disc.execute(card(ok=False), runners())
    assert out["ok"] is False and out["stage"] == "precheck"


def test_happy_path_places_bracket_and_tags_source():
    spy = []
    out = disc.execute(card(), runners(reflect_spy=spy))
    assert out["ok"] is True
    assert out["source"] == "discretionary"
    assert out["ticker"] == "TTWO" and out["qty"] == 8
    # reflection slip is tagged so gut trades are distinguishable from autonomous ones.
    assert spy[0]["thesis"].startswith("[source:discretionary]")
    assert spy[0]["entry"] == 240.0 and spy[0]["stop"] == 222.0


def test_broker_reject_returns_failure_and_skips_slip():
    spy = []
    bad = {"ok": False, "stage": "kill_switch", "reason": "kill engaged"}
    out = disc.execute(card(), runners(enter_result=bad, reflect_spy=spy))
    assert out["ok"] is False and out["stage"] == "kill_switch"
    assert spy == []   # no journal slip when nothing was placed


import io
import json


def test_main_propose_reads_stdin_and_prints_card(monkeypatch):
    # Swap the real subprocess runners for fakes so main() does no network.
    monkeypatch.setattr(disc, "_real_runners", lambda: {
        "control": lambda: {"exit": 0, "mode": "paper"},
        "markov": lambda: {"exit": 0},
        "catalyst": lambda t: "news:1",
        "risk": lambda base: {"exit": 0, "verdict": {
            "pass": True, "qty": 8, "stop_price": 222.0,
            "gates_failed": [], "dire_triggers": [], "reject_reason": None}},
    })
    stdin = json.dumps({"account": {"equity": 25000.0}, "positions": [],
                        "candidate": {"ticker": "ttwo", "price": 240.0,
                                      "conviction": 25, "stop": 222.0}})
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
    out = io.StringIO()
    monkeypatch.setattr("sys.stdout", out)
    rc = disc.main(["propose"])
    assert rc == 0
    card = json.loads(out.getvalue())
    assert card["ok"] is True and card["target"] == 276.0


def test_main_bad_args_returns_usage_code(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
    assert disc.main(["bogus"]) == 2
