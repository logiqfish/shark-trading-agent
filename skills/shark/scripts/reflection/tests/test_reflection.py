"""Tests for the reflection skill (self-grading trade journal).

Pure functions + injected network (req=) so no real Alpaca calls in tests,
matching the broker.py / risk.py precedent.
"""
import reflection as r


# --- Phase A: append_pending -------------------------------------------------

def test_append_pending_writes_a_pending_slip(tmp_path):
    j = tmp_path / "JOURNAL.md"
    r.append_pending(str(j), "INTC", "2026-06-12", 78, 31.20, 30.10,
                     "oversold bounce off 8-K capex guidance")
    text = j.read_text()
    assert "[2026-06-12 | INTC | conv 78 | pending]" in text
    assert "DECISION:" in text
    assert "8-K capex" in text
    assert r.SEPARATOR.strip() in text


def test_append_pending_is_idempotent_for_same_date_ticker(tmp_path):
    j = tmp_path / "JOURNAL.md"
    r.append_pending(str(j), "INTC", "2026-06-12", 78, 31.20, 30.10, "thesis A")
    r.append_pending(str(j), "INTC", "2026-06-12", 78, 31.20, 30.10, "thesis B")
    assert j.read_text().count("| INTC | conv 78 | pending]") == 1


def test_append_pending_allows_reentry_on_a_different_date(tmp_path):
    j = tmp_path / "JOURNAL.md"
    r.append_pending(str(j), "INTC", "2026-06-12", 78, 31.20, 30.10, "first")
    r.append_pending(str(j), "INTC", "2026-06-20", 71, 33.00, 32.00, "second")
    pend = r.get_pending(str(j))
    assert len(pend) == 2
    assert {p["date"] for p in pend} == {"2026-06-12", "2026-06-20"}


# --- compute_outcome (pure math) --------------------------------------------

def test_compute_outcome_alpha_is_trade_return_minus_spy(tmp_path):
    out = r.compute_outcome(entry_price=100.0, exit_price=102.0,
                            entry_date="2026-06-01", exit_date="2026-06-07",
                            realized_R=1.4, spy_return=0.012)
    assert abs(out["raw_return"] - 0.02) < 1e-9
    assert abs(out["alpha"] - (0.02 - 0.012)) < 1e-9
    assert out["realized_R"] == 1.4
    assert out["holding_days"] == 6
    assert out["benchmark"] == "SPY"


def test_compute_outcome_failsoft_when_spy_unavailable(tmp_path):
    out = r.compute_outcome(entry_price=100.0, exit_price=98.0,
                            entry_date="2026-06-01", exit_date="2026-06-03",
                            realized_R=-1.0, spy_return=None)
    assert out["alpha"] is None
    assert abs(out["raw_return"] - (-0.02)) < 1e-9
    assert out["realized_R"] == -1.0


# --- spy_return_pct (injected network) --------------------------------------

def _bars_req(payload, status=200):
    def req(base, key, sec, method, path, body=None):
        return status, payload
    return req


def test_spy_return_pct_computes_first_to_last_close():
    payload = {"bars": [{"c": 500.0}, {"c": 505.0}, {"c": 510.0}]}
    pct = r.spy_return_pct("2026-06-01", "2026-06-07", req=_bars_req(payload))
    assert abs(pct - (510.0 - 500.0) / 500.0) < 1e-9


def test_spy_return_pct_returns_none_on_http_error():
    pct = r.spy_return_pct("2026-06-01", "2026-06-07",
                           req=_bars_req({"message": "boom"}, status=500))
    assert pct is None


def test_spy_return_pct_returns_none_on_empty_bars():
    pct = r.spy_return_pct("2026-06-01", "2026-06-07",
                           req=_bars_req({"bars": []}))
    assert pct is None


# --- Phase B: resolve --------------------------------------------------------

def test_resolve_flips_tag_and_appends_reflection(tmp_path):
    j = tmp_path / "JOURNAL.md"
    r.append_pending(str(j), "INTC", "2026-06-12", 78, 31.20, 30.10, "thesis")
    out = r.compute_outcome(31.20, 33.80, "2026-06-12", "2026-06-18", 1.4, 0.008)
    r.resolve(str(j), "INTC", "2026-06-12", out, "Call correct, capex thesis held.")
    text = j.read_text()
    assert "| pending]" not in text
    assert "+1.4R" in text
    assert "alpha +7.5%" in text   # raw +8.3% (31.20->33.80) minus SPY +0.8%
    assert "6d]" in text
    assert "REFLECTION:" in text
    assert "capex thesis held" in text


def test_resolve_renders_na_alpha_when_none(tmp_path):
    j = tmp_path / "JOURNAL.md"
    r.append_pending(str(j), "AMD", "2026-06-12", 70, 100.0, 95.0, "thesis")
    out = r.compute_outcome(100.0, 96.0, "2026-06-12", "2026-06-14", -1.0, None)
    r.resolve(str(j), "AMD", "2026-06-12", out, "Stopped out; thesis failed.")
    text = j.read_text()
    assert "alpha n/a" in text
    assert "-1.0R" in text


def test_resolve_only_touches_the_matching_pending(tmp_path):
    j = tmp_path / "JOURNAL.md"
    r.append_pending(str(j), "INTC", "2026-06-12", 78, 31.20, 30.10, "intc")
    r.append_pending(str(j), "AMD", "2026-06-12", 70, 100.0, 95.0, "amd")
    out = r.compute_outcome(31.20, 33.80, "2026-06-12", "2026-06-18", 1.4, 0.008)
    r.resolve(str(j), "INTC", "2026-06-12", out, "intc lesson")
    pend = r.get_pending(str(j))
    assert len(pend) == 1 and pend[0]["ticker"] == "AMD"


def test_resolve_is_atomic_no_tmp_left_behind(tmp_path):
    j = tmp_path / "JOURNAL.md"
    r.append_pending(str(j), "INTC", "2026-06-12", 78, 31.20, 30.10, "thesis")
    out = r.compute_outcome(31.20, 33.80, "2026-06-12", "2026-06-18", 1.4, 0.008)
    r.resolve(str(j), "INTC", "2026-06-12", out, "lesson")
    leftovers = list(tmp_path.glob("*.tmp"))
    assert leftovers == []


# --- rotation ----------------------------------------------------------------

def test_rotation_caps_resolved_but_keeps_all_pending(tmp_path):
    j = tmp_path / "JOURNAL.md"
    # 3 resolved + 2 still-pending, cap of 2 resolved
    for i in range(3):
        d = f"2026-06-{10+i:02d}"
        r.append_pending(str(j), "AAA", d, 70, 10.0, 9.0, f"r{i}")
        out = r.compute_outcome(10.0, 11.0, d, d, 1.0, 0.0)
        r.resolve(str(j), "AAA", d, out, f"lesson {i}", rotation_cap=2)
    r.append_pending(str(j), "BBB", "2026-06-20", 70, 10.0, 9.0, "pending1")
    r.append_pending(str(j), "CCC", "2026-06-21", 70, 10.0, 9.0, "pending2")
    entries = r.load_entries(str(j))
    resolved = [e for e in entries if not e["pending"]]
    pending = [e for e in entries if e["pending"]]
    assert len(resolved) == 2          # capped
    assert len(pending) == 2           # all pending kept
    # most-recent resolved retained (lesson 0 dropped)
    assert "lesson 0" not in j.read_text()
    assert "lesson 2" in j.read_text()


# --- Phase C: get_context ----------------------------------------------------

def test_get_context_empty_when_nothing_resolved(tmp_path):
    j = tmp_path / "JOURNAL.md"
    r.append_pending(str(j), "INTC", "2026-06-12", 78, 31.20, 30.10, "thesis")
    assert r.get_context(str(j), "INTC") == ""


def test_get_context_splits_same_and_cross_ticker(tmp_path):
    j = tmp_path / "JOURNAL.md"
    def add_resolved(ticker, date, lesson):
        r.append_pending(str(j), ticker, date, 70, 10.0, 9.0, f"{ticker} thesis")
        out = r.compute_outcome(10.0, 11.0, date, date, 1.0, 0.0)
        r.resolve(str(j), ticker, date, out, lesson)
    add_resolved("INTC", "2026-06-10", "intc lesson one")
    add_resolved("AMD", "2026-06-11", "amd lesson")
    add_resolved("INTC", "2026-06-12", "intc lesson two")
    ctx = r.get_context(str(j), "INTC", n_same=5, n_cross=3)
    assert "INTC" in ctx and "intc lesson two" in ctx and "intc lesson one" in ctx
    assert "amd lesson" in ctx           # cross-ticker lesson included
    # same-ticker section lists most-recent first
    assert ctx.index("intc lesson two") < ctx.index("intc lesson one")


def test_get_context_respects_n_same_limit(tmp_path):
    j = tmp_path / "JOURNAL.md"
    for i in range(6):
        d = f"2026-06-{10+i:02d}"
        r.append_pending(str(j), "INTC", d, 70, 10.0, 9.0, "t")
        out = r.compute_outcome(10.0, 11.0, d, d, 1.0, 0.0)
        r.resolve(str(j), "INTC", d, out, f"lesson{i}")
    ctx = r.get_context(str(j), "INTC", n_same=3, n_cross=3)
    included = [f"lesson{i}" for i in range(6) if f"lesson{i}" in ctx]
    assert len(included) == 3            # only 3 most-recent same-ticker


# --- robustness --------------------------------------------------------------

def test_load_entries_missing_file_returns_empty(tmp_path):
    assert r.load_entries(str(tmp_path / "nope.md")) == []


def test_load_entries_tolerates_malformed_block(tmp_path):
    j = tmp_path / "JOURNAL.md"
    j.write_text("garbage with no tag line\n\nstill garbage")
    # must not raise
    assert isinstance(r.load_entries(str(j)), list)
