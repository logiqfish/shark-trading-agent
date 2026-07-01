"""Tests for the thesis-persistence skill.

Pure functions + injected context (ctx=) so no real network calls in tests,
mirroring the reflection.py / risk.py precedent. The store is a JSON array of
thesis objects in <agent>/THESES.json; closed theses prune to a gitignored
THESES_ARCHIVE.jsonl.
"""
import json

import thesis as t


def _thesis(ticker="INTC", kind="position", status="open", **kw):
    """Minimal valid open thesis for tests."""
    base = {
        "id": f"th_{ticker}_20260623",
        "ticker": ticker,
        "kind": kind,
        "status": status,
        "direction": "long",
        "conviction": 72,
        "conviction_fire": "2026-06-23T14:30:00Z",
        "carried_fires": 0,
        "invalidation_price": 218.47,
        "created_fire": "2026-06-23T14:30:00Z",
        "created_by": "debate",
        "assumptions": [],
        "delta_log": [],
        "outcome": None,
    }
    base.update(kw)
    return base


# --- store: load / save ------------------------------------------------------

def test_load_missing_file_returns_empty_list(tmp_path):
    assert t.load_theses(str(tmp_path / "THESES.json")) == []


def test_load_malformed_file_returns_empty_list(tmp_path):
    p = tmp_path / "THESES.json"
    p.write_text("this is not json{{{")
    assert t.load_theses(str(p)) == []


def test_save_then_load_roundtrips(tmp_path):
    p = str(tmp_path / "THESES.json")
    t.save_theses(p, [_thesis()])
    loaded = t.load_theses(p)
    assert len(loaded) == 1
    assert loaded[0]["ticker"] == "INTC"


def test_save_is_atomic_no_tmp_left_behind(tmp_path):
    p = str(tmp_path / "THESES.json")
    t.save_theses(p, [_thesis()])
    assert not (tmp_path / "THESES.json.tmp").exists()


# --- store: get_open ---------------------------------------------------------

def test_get_open_filters_out_closed(tmp_path):
    theses = [_thesis(ticker="INTC"), _thesis(ticker="HPE", status="closed")]
    open_ = t.get_open(theses)
    assert [x["ticker"] for x in open_] == ["INTC"]


# --- store: upsert -----------------------------------------------------------

def test_upsert_creates_when_absent(tmp_path):
    p = str(tmp_path / "THESES.json")
    t.upsert_thesis(p, _thesis())
    assert len(t.load_theses(p)) == 1


def test_upsert_replaces_by_id_does_not_duplicate(tmp_path):
    p = str(tmp_path / "THESES.json")
    t.upsert_thesis(p, _thesis(conviction=72))
    t.upsert_thesis(p, _thesis(conviction=40))  # same id
    loaded = t.load_theses(p)
    assert len(loaded) == 1
    assert loaded[0]["conviction"] == 40


def test_find_open_by_ticker_returns_only_open_match(tmp_path):
    theses = [
        _thesis(ticker="INTC"),
        _thesis(ticker="INTC", status="closed", id="th_INTC_old"),
        _thesis(ticker="HPE"),
    ]
    found = t.find_open_by_ticker(theses, "INTC")
    assert found is not None
    assert found["status"] == "open"
    assert found["id"] == "th_INTC_20260623"


# --- check dispatch table (score_check -> (status, verifiable)) ---------------

def test_price_above_intact_when_above_level():
    assert t.score_check({"type": "price_above", "param": 215.0},
                         {"price": 220.0}) == (t.STATUS_INTACT, True)


def test_price_above_weakening_within_band_below():
    # 1.5% band: 215 * 0.985 = 211.78; 213 sits in [211.78, 215)
    assert t.score_check({"type": "price_above", "param": 215.0},
                         {"price": 213.0}) == (t.STATUS_WEAKENING, True)


def test_price_above_violated_clearly_below_band():
    assert t.score_check({"type": "price_above", "param": 215.0},
                         {"price": 205.0}) == (t.STATUS_VIOLATED, True)


def test_price_below_mirror_intact_when_below():
    assert t.score_check({"type": "price_below", "param": 50.0},
                         {"price": 45.0}) == (t.STATUS_INTACT, True)


def test_price_below_violated_clearly_above_band():
    assert t.score_check({"type": "price_below", "param": 50.0},
                         {"price": 60.0}) == (t.STATUS_VIOLATED, True)


def test_regime_favorable_maps_three_ways():
    assert t.score_check({"type": "regime_favorable"},
                         {"regime": "favorable"}) == (t.STATUS_INTACT, True)
    assert t.score_check({"type": "regime_favorable"},
                         {"regime": "neutral"}) == (t.STATUS_WEAKENING, True)
    assert t.score_check({"type": "regime_favorable"},
                         {"regime": "adverse"}) == (t.STATUS_VIOLATED, True)


def test_catalyst_and_fundamentals_check_types_are_unknown_in_kit():
    # The kit fork drops the mesh-fed checks; their types now fail safe like any
    # other unknown type (weakening, unverifiable -> forced escalation).
    assert t.score_check({"type": "catalyst_live"},
                         {"catalyst": "live"}) == (t.STATUS_WEAKENING, False)
    assert t.score_check({"type": "fundamentals_stable"},
                         {"fundamentals": 1.25}) == (t.STATUS_WEAKENING, False)


def test_stop_distance_intact_when_far_else_weakening():
    chk = {"type": "stop_distance", "param": {"stop": 200.0, "min": 0.03}}
    assert t.score_check(chk, {"price": 220.0}) == (t.STATUS_INTACT, True)     # ~9% away
    assert t.score_check(chk, {"price": 203.0}) == (t.STATUS_WEAKENING, True)  # ~1.5% away


def test_manual_always_intact_and_does_not_force_escalation():
    assert t.score_check({"type": "manual"}, {}) == (t.STATUS_INTACT, True)


def test_missing_data_fails_safe_to_weakening_unverifiable():
    # fetch failed -> price absent -> weakening + verifiable False (forces escalation)
    assert t.score_check({"type": "price_above", "param": 215.0},
                         {"price": None}) == (t.STATUS_WEAKENING, False)
    assert t.score_check({"type": "regime_favorable"}, {}) == (t.STATUS_WEAKENING, False)


def test_unknown_check_type_fails_safe():
    assert t.score_check({"type": "bogus"}, {}) == (t.STATUS_WEAKENING, False)


# --- Layer 1 driver: rescore -------------------------------------------------

FIRE = "2026-06-23T15:30:00Z"


def _asm(id_, type_, param=None, weight="core", status=t.STATUS_INTACT):
    return {"id": id_, "claim": id_, "check": {"type": type_, "param": param},
            "weight": weight, "status": status, "status_fire": "2026-06-23T14:30:00Z"}


def test_rescore_all_intact_unchanged_does_not_escalate():
    th = _thesis(invalidation_price=200.0,
                 assumptions=[_asm("a1", "price_above", 215.0)])
    res = t.rescore(th, {"price": 220.0}, FIRE)
    assert res["escalate"] is False
    assert res["deltas"] == []
    assert res["thesis"]["assumptions"][0]["status"] == t.STATUS_INTACT


def test_rescore_core_violation_escalates_and_records_delta():
    th = _thesis(invalidation_price=200.0,
                 assumptions=[_asm("a1", "price_above", 215.0)])
    res = t.rescore(th, {"price": 205.0}, FIRE)  # below band -> violated
    assert res["escalate"] is True
    assert res["thesis"]["assumptions"][0]["status"] == t.STATUS_VIOLATED
    assert res["thesis"]["assumptions"][0]["status_fire"] == FIRE
    assert any("a1" in d for d in res["deltas"])


def test_rescore_supporting_weakening_this_fire_escalates():
    th = _thesis(invalidation_price=200.0,
                 assumptions=[_asm("a1", "price_above", 215.0, weight="supporting")])
    res = t.rescore(th, {"price": 213.0}, FIRE)  # within band -> weakening (changed)
    assert res["escalate"] is True


def test_rescore_steady_weakening_unchanged_does_not_escalate():
    # already weakening last fire, still weakening, nothing else moved -> skip
    th = _thesis(invalidation_price=200.0,
                 assumptions=[_asm("a1", "price_above", 215.0, weight="supporting",
                                   status=t.STATUS_WEAKENING)])
    res = t.rescore(th, {"price": 213.0}, FIRE)
    assert res["escalate"] is False
    assert res["deltas"] == []


def test_rescore_invalidation_crossed_escalates_even_if_assumptions_unchanged():
    th = _thesis(direction="long", invalidation_price=218.47,
                 assumptions=[_asm("a1", "manual")])
    res = t.rescore(th, {"price": 210.0}, FIRE)  # below invalidation
    assert res["escalate"] is True


def test_rescore_unverifiable_fetch_escalates():
    th = _thesis(invalidation_price=200.0,
                 assumptions=[_asm("a1", "regime_favorable")])
    res = t.rescore(th, {}, FIRE)  # regime missing -> unverifiable -> weakening
    assert res["escalate"] is True
    assert res["thesis"]["assumptions"][0]["status"] == t.STATUS_WEAKENING


def test_rescore_appends_to_delta_log_on_change():
    th = _thesis(invalidation_price=200.0,
                 assumptions=[_asm("a1", "price_above", 215.0)])
    res = t.rescore(th, {"price": 205.0}, FIRE)
    assert len(res["thesis"]["delta_log"]) == 1
    assert res["thesis"]["delta_log"][0]["fire"] == FIRE


# --- exit_signal: the conservative held-position exit trigger -----------------
# Distinct from `escalate`. True ONLY on a hard core-assumption violation or a
# breached invalidation price — never on weakening, mere change, or a failed
# fetch. A thesis-driven exit must not fire on noise.

def test_exit_signal_true_on_core_violation():
    th = _thesis(invalidation_price=200.0,
                 assumptions=[_asm("a1", "price_above", 215.0, weight="core")])
    res = t.rescore(th, {"price": 205.0}, FIRE)  # violated, core
    assert res["exit_signal"] is True


def test_exit_signal_false_on_supporting_violation():
    th = _thesis(invalidation_price=200.0,
                 assumptions=[_asm("a1", "price_above", 215.0, weight="supporting")])
    res = t.rescore(th, {"price": 205.0}, FIRE)  # violated, but only supporting
    assert res["escalate"] is True
    assert res["exit_signal"] is False


def test_exit_signal_true_on_invalidation_breach():
    th = _thesis(direction="long", invalidation_price=218.47,
                 assumptions=[_asm("a1", "manual")])
    res = t.rescore(th, {"price": 210.0}, FIRE)
    assert res["exit_signal"] is True


def test_exit_signal_false_when_only_weakening():
    th = _thesis(invalidation_price=200.0,
                 assumptions=[_asm("a1", "price_above", 215.0, weight="core")])
    res = t.rescore(th, {"price": 213.0}, FIRE)  # weakening, not violated
    assert res["exit_signal"] is False


def test_exit_signal_false_on_unverifiable_fetch():
    # a failed fetch escalates (re-debate) but must NOT trigger an exit
    th = _thesis(invalidation_price=None,
                 assumptions=[_asm("a1", "regime_favorable", weight="core")])
    res = t.rescore(th, {}, FIRE)
    assert res["escalate"] is True
    assert res["exit_signal"] is False


def test_exit_signal_false_when_all_intact():
    th = _thesis(invalidation_price=200.0,
                 assumptions=[_asm("a1", "price_above", 215.0, weight="core")])
    res = t.rescore(th, {"price": 220.0}, FIRE)
    assert res["exit_signal"] is False


def test_exit_signal_false_when_invalidation_price_unconfirmable():
    # invalidation set but price fetch failed -> escalate, but NEVER exit on noise
    th = _thesis(direction="long", invalidation_price=218.47,
                 assumptions=[_asm("a1", "manual")])
    res = t.rescore(th, {"price": None}, FIRE)
    assert res["escalate"] is True
    assert res["exit_signal"] is False


def test_rescore_all_surfaces_exit_signal_per_row(tmp_path):
    p = str(tmp_path / "THESES.json")
    t.upsert_thesis(p, _thesis(ticker="INTC", invalidation_price=200.0,
                               assumptions=[_asm("a1", "price_above", 215.0, weight="core")]))
    summary = t.rescore_all(p, lambda th: {"price": 205.0}, FIRE)  # core violated
    assert summary[0]["exit_signal"] is True


# --- carry-forward / conviction apply ----------------------------------------

def test_carry_forward_increments_and_preserves_conviction():
    th = _thesis(conviction=72, carried_fires=2)
    out = t.carry_forward(th)
    assert out["carried_fires"] == 3
    assert out["conviction"] == 72


def test_apply_conviction_resets_carried_and_stamps_fire():
    th = _thesis(conviction=72, carried_fires=5)
    out = t.apply_conviction(th, 61, FIRE)
    assert out["conviction"] == 61
    assert out["carried_fires"] == 0
    assert out["conviction_fire"] == FIRE


# --- close + prune to archive (the exit hook) --------------------------------

def test_close_removes_from_live_and_writes_outcome(tmp_path):
    p = str(tmp_path / "THESES.json")
    arc = str(tmp_path / "THESES_ARCHIVE.jsonl")
    t.upsert_thesis(p, _thesis(ticker="INTC"))
    outcome = {"realized_R": 1.4, "alpha_vs_spy": 0.008,
               "failed_assumptions": [], "lesson": "catalyst played out"}
    assert t.close_thesis(p, "th_INTC_20260623", outcome, arc) is True
    assert t.load_theses(p) == []  # pruned from the hot file


def test_close_appends_closed_thesis_to_archive(tmp_path):
    p = str(tmp_path / "THESES.json")
    arc = str(tmp_path / "THESES_ARCHIVE.jsonl")
    t.upsert_thesis(p, _thesis(ticker="INTC"))
    t.close_thesis(p, "th_INTC_20260623", {"realized_R": 1.4}, arc)
    lines = [l for l in open(arc).read().splitlines() if l.strip()]
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["status"] == "closed"
    assert rec["ticker"] == "INTC"
    assert rec["outcome"]["realized_R"] == 1.4


def test_close_keeps_other_open_theses(tmp_path):
    p = str(tmp_path / "THESES.json")
    arc = str(tmp_path / "THESES_ARCHIVE.jsonl")
    t.upsert_thesis(p, _thesis(ticker="INTC"))
    t.upsert_thesis(p, _thesis(ticker="HPE", id="th_HPE_20260623"))
    t.close_thesis(p, "th_INTC_20260623", {"realized_R": -1.0}, arc)
    remaining = t.load_theses(p)
    assert [x["ticker"] for x in remaining] == ["HPE"]


def test_close_unknown_id_returns_false_and_leaves_file(tmp_path):
    p = str(tmp_path / "THESES.json")
    t.upsert_thesis(p, _thesis(ticker="INTC"))
    assert t.close_thesis(p, "th_NOPE", {"realized_R": 0.0}) is False
    assert len(t.load_theses(p)) == 1


# --- constructor: build_thesis (used by the debate at entry) ------------------

def test_build_thesis_sets_open_defaults():
    th = t.build_thesis(
        ticker="INTC", direction="long", conviction=78, invalidation_price=218.47,
        fire=FIRE,
        assumptions=[{"id": "a1", "claim": "holds breakout",
                      "check": {"type": "price_above", "param": 215.0},
                      "weight": "core"}],
    )
    assert th["status"] == "open"
    assert th["kind"] == "position"
    assert th["carried_fires"] == 0
    assert th["conviction"] == 78
    assert th["conviction_fire"] == FIRE
    assert th["outcome"] is None
    assert th["id"] == "th_INTC_20260623"          # derived from ticker + fire date
    assert th["assumptions"][0]["status"] == "intact"  # seeded intact
    assert th["assumptions"][0]["status_fire"] == FIRE


# --- orchestration: rescore_all (HEARTBEAT Step 3.6 entry) --------------------

def test_rescore_all_escalates_one_carries_other_and_persists(tmp_path):
    p = str(tmp_path / "THESES.json")
    t.upsert_thesis(p, _thesis(ticker="INTC", invalidation_price=200.0, carried_fires=1,
                               assumptions=[_asm("a1", "price_above", 215.0)]))
    t.upsert_thesis(p, _thesis(ticker="HPE", id="th_HPE_20260623", invalidation_price=10.0,
                               assumptions=[_asm("h1", "price_above", 15.0)]))

    def ctx_for(th):
        return {"INTC": {"price": 220.0},   # intact -> stable -> carry
                "HPE": {"price": 12.0}}[th["ticker"]]  # below band -> violated -> escalate

    summary = t.rescore_all(p, ctx_for, FIRE)
    by = {s["ticker"]: s for s in summary}
    assert by["INTC"]["escalate"] is False
    assert by["HPE"]["escalate"] is True

    persisted = {x["ticker"]: x for x in t.load_theses(p)}
    assert persisted["INTC"]["carried_fires"] == 2          # carried (no debate)
    assert persisted["HPE"]["assumptions"][0]["status"] == "violated"  # status persisted


def test_rescore_all_ignores_and_preserves_closed(tmp_path):
    p = str(tmp_path / "THESES.json")
    t.upsert_thesis(p, _thesis(ticker="OLD", id="th_OLD", status="closed"))
    t.upsert_thesis(p, _thesis(ticker="INTC", invalidation_price=200.0,
                               assumptions=[_asm("a1", "manual")]))
    summary = t.rescore_all(p, lambda th: {"price": 250.0}, FIRE)
    assert [s["ticker"] for s in summary] == ["INTC"]       # closed not scored
    assert any(x["ticker"] == "OLD" for x in t.load_theses(p))  # closed preserved


# --- mesh mapping helpers (pure) ---------------------------------------------

def test_regime_to_status_is_direction_aware():
    assert t.regime_to_status("Bull", "long") == "favorable"
    assert t.regime_to_status("Sideways", "long") == "neutral"
    assert t.regime_to_status("Bear", "long") == "adverse"
    # short inverts the trend ends
    assert t.regime_to_status("Bear", "short") == "favorable"
    assert t.regime_to_status("Bull", "short") == "adverse"


def test_regime_to_status_unknown_is_none():
    assert t.regime_to_status("Wat", "long") is None
    assert t.regime_to_status(None, "long") is None


def test_parse_latest_price_extracts_trade_price():
    assert t.parse_latest_price({"trade": {"p": 214.10}}) == 214.10


def test_parse_latest_price_missing_is_none():
    assert t.parse_latest_price({}) is None
    assert t.parse_latest_price({"trade": {}}) is None


# --- fetchers with injected req (fail-soft) -----------------------------------

def test_fetch_price_maps_ok_response():
    req = lambda base, method, path, headers=None, body=None: (200, {"trade": {"p": 214.1}})
    assert t.fetch_price("INTC", req=req) == 214.1


def test_fetch_price_non_2xx_is_none():
    req = lambda base, method, path, headers=None, body=None: (500, {})
    assert t.fetch_price("INTC", req=req) is None


def test_fetch_regime_maps_direction_aware(monkeypatch):
    # Kit fork: regime comes from the on-box local-markov label, mapped per direction.
    monkeypatch.setattr(t, "_local_regime_label", lambda ticker: "Bull")
    assert t.fetch_regime("INTC", "long") == "favorable"
    assert t.fetch_regime("INTC", "short") == "adverse"


def test_fetch_regime_undetermined_label_is_none(monkeypatch):
    # local-markov fail-soft -> None label -> None status (unverifiable -> escalate).
    monkeypatch.setattr(t, "_local_regime_label", lambda ticker: None)
    assert t.fetch_regime("INTC", "long") is None


# --- build_ctx fetches only what the assumptions need -------------------------

def test_build_ctx_fetches_price_only_when_needed():
    calls = {"price": 0, "regime": 0}

    def fp(ticker):
        calls["price"] += 1
        return 214.1

    def fr(ticker, direction):
        calls["regime"] += 1
        return "favorable"

    th = _thesis(invalidation_price=None,
                 assumptions=[_asm("a1", "regime_favorable")])
    ctx = t.build_ctx(th, fetch_price=fp, fetch_regime=fr)
    assert ctx == {"regime": "favorable"}
    assert calls == {"price": 0, "regime": 1}   # no price fetch when nothing needs it


def test_build_ctx_fetches_price_for_invalidation_even_without_price_check():
    th = _thesis(invalidation_price=200.0,
                 assumptions=[_asm("a1", "manual")])
    ctx = t.build_ctx(th, fetch_price=lambda tk: 210.0, fetch_regime=lambda tk, d: None)
    assert ctx["price"] == 210.0
