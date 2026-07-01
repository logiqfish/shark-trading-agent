"""Tests for the debate skill (bull/bear/referee conviction debate).

Mirrors reflection.py / risk.py: the deterministic contract is unit-tested
(verdict normalization + transcript logging). The bull/bear/referee turns
themselves are LLM prose run by the agent's brain — not code, not tested here.
"""
import pytest

import debate as d


# --- normalize_verdict: conviction clamping/coercion -------------------------

def test_conviction_in_range_is_preserved():
    v = d.normalize_verdict({"conviction": 72, "stance": "bullish", "rationale": "x"})
    assert v["conviction"] == 72


def test_conviction_above_100_clamps_to_100():
    v = d.normalize_verdict({"conviction": 140, "stance": "bullish"})
    assert v["conviction"] == 100


def test_conviction_below_0_clamps_to_0():
    v = d.normalize_verdict({"conviction": -5, "stance": "bearish"})
    assert v["conviction"] == 0


def test_conviction_float_is_truncated_to_int():
    v = d.normalize_verdict({"conviction": 71.8, "stance": "neutral"})
    assert v["conviction"] == 71


def test_conviction_numeric_string_is_coerced():
    v = d.normalize_verdict({"conviction": "78", "stance": "bullish"})
    assert v["conviction"] == 78


def test_missing_conviction_is_rejected():
    with pytest.raises(ValueError):
        d.normalize_verdict({"stance": "bullish", "rationale": "x"})


def test_nonnumeric_conviction_is_rejected():
    with pytest.raises(ValueError):
        d.normalize_verdict({"conviction": "high", "stance": "bullish"})


# --- normalize_verdict: stance enum ------------------------------------------

def test_valid_stance_is_lowercased():
    v = d.normalize_verdict({"conviction": 70, "stance": "Bullish"})
    assert v["stance"] == "bullish"


def test_invalid_stance_defaults_to_neutral():
    v = d.normalize_verdict({"conviction": 70, "stance": "mega-bull"})
    assert v["stance"] == "neutral"


def test_absent_stance_defaults_to_neutral():
    v = d.normalize_verdict({"conviction": 70})
    assert v["stance"] == "neutral"


# --- normalize_verdict: rationale --------------------------------------------

def test_rationale_is_truncated_to_max():
    v = d.normalize_verdict({"conviction": 70, "stance": "neutral", "rationale": "x" * 500})
    assert len(v["rationale"]) <= d.MAX_RATIONALE


def test_rationale_absent_is_empty_string():
    v = d.normalize_verdict({"conviction": 70, "stance": "neutral"})
    assert v["rationale"] == ""


# --- record_debate: transcript logging ---------------------------------------

def test_record_debate_writes_full_transcript(tmp_path):
    mem = tmp_path / "2026-06-18.md"
    d.record_debate(str(mem), "INTC", "2026-06-18",
                    bull="strong 8-K capex guidance",
                    bear="valuation stretched into earnings",
                    verdict={"conviction": 72, "stance": "bullish", "rationale": "catalyst beats risk"})
    text = mem.read_text()
    assert "INTC" in text
    assert "BULL:" in text and "8-K capex" in text
    assert "BEAR:" in text and "valuation stretched" in text
    assert "VERDICT:" in text and "72" in text and "bullish" in text


def test_record_debate_is_idempotent_on_date_ticker(tmp_path):
    mem = tmp_path / "2026-06-18.md"
    v = {"conviction": 72, "stance": "bullish", "rationale": "r"}
    d.record_debate(str(mem), "INTC", "2026-06-18", "bull one", "bear one", v)
    d.record_debate(str(mem), "INTC", "2026-06-18", "bull two", "bear two", v)
    assert mem.read_text().count("| INTC |") == 1


def test_record_debate_allows_different_tickers_same_day(tmp_path):
    mem = tmp_path / "2026-06-18.md"
    v = {"conviction": 72, "stance": "bullish", "rationale": "r"}
    d.record_debate(str(mem), "INTC", "2026-06-18", "b", "be", v)
    d.record_debate(str(mem), "AMD", "2026-06-18", "b", "be", v)
    text = mem.read_text()
    assert "| INTC |" in text and "| AMD |" in text


def test_record_debate_clamps_verdict_before_logging(tmp_path):
    """A raw out-of-range verdict must never be logged un-normalized."""
    mem = tmp_path / "2026-06-18.md"
    d.record_debate(str(mem), "INTC", "2026-06-18", "b", "be",
                    {"conviction": 140, "stance": "BULLISH", "rationale": "x"})
    text = mem.read_text()
    assert "100" in text and "140" not in text
    assert "bullish" in text
