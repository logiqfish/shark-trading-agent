"""Tests for session_pnl.py — parses Alpaca portfolio-history into
{day_start_equity, session_low_equity}; soft-fails to {} on any error.
HTTP is never touched (only parse() is exercised)."""
import importlib.util
from pathlib import Path

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("session_pnl", _DIR / "session_pnl.py")
session_pnl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(session_pnl)


def test_parses_base_and_low():
    payload = {"base_value": 25000.0, "equity": [25000.0, 24600.0, 24200.0, 24900.0]}
    out = session_pnl.parse(payload)
    assert out == {"day_start_equity": 25000.0, "session_low_equity": 24200.0}


def test_skips_null_equity_points():
    payload = {"base_value": 25000.0, "equity": [25000.0, None, 24300.0, None]}
    out = session_pnl.parse(payload)
    assert out["session_low_equity"] == 24300.0


def test_empty_equity_yields_base_only_no_low():
    payload = {"base_value": 25000.0, "equity": []}
    out = session_pnl.parse(payload)
    assert out == {"day_start_equity": 25000.0}  # no session_low_equity key


def test_absent_equity_key_yields_base_only():
    payload = {"base_value": 25000.0}  # no equity key at all
    out = session_pnl.parse(payload)
    assert out == {"day_start_equity": 25000.0}


def test_malformed_payload_returns_empty():
    assert session_pnl.parse({"garbage": True}) == {}
    assert session_pnl.parse(None) == {}
    assert session_pnl.parse({"base_value": "not-a-number"}) == {}
