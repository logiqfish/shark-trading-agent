"""Tests for the shared Alpaca account-identity guard. Pure + CLI behavior."""
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from account_guard import EXIT_MISMATCH, evaluate  # noqa: E402

GUARD = Path(__file__).resolve().parent.parent / "account_guard.py"


def _run(account_json, expected_env):
    env = {**os.environ}
    env.pop("ALPACA_ACCOUNT_ID", None)
    if expected_env is not None:
        env["ALPACA_ACCOUNT_ID"] = expected_env
    return subprocess.run(
        [sys.executable, str(GUARD)],
        input=account_json,
        capture_output=True,
        text=True,
        env=env,
    )


# --- pure evaluate() ---

def test_match_ok():
    ok, msg = evaluate({"account_number": "test-acct-self"}, "test-acct-self")
    assert ok and "OK" in msg


def test_mismatch_fails_closed():
    ok, msg = evaluate({"account_number": "test-acct-other"}, "test-acct-self")
    assert not ok and "MISMATCH" in msg


def test_unset_warns_but_passes():
    ok, msg = evaluate({"account_number": "test-acct-self"}, None)
    assert ok and "WARN" in msg


def test_unset_empty_string_warns_but_passes():
    ok, msg = evaluate({"account_number": "test-acct-self"}, "")
    assert ok and "WARN" in msg


def test_missing_account_number_with_expected_fails():
    ok, _ = evaluate({}, "test-acct-self")
    assert not ok


# --- CLI ---

def test_cli_mismatch_exit3():
    r = _run(json.dumps({"account_number": "test-acct-other"}), "test-acct-self")
    assert r.returncode == EXIT_MISMATCH
    assert "MISMATCH" in r.stderr


def test_cli_match_exit0():
    r = _run(json.dumps({"account_number": "test-acct-self"}), "test-acct-self")
    assert r.returncode == 0


def test_cli_unset_exit0_with_warning():
    r = _run(json.dumps({"account_number": "test-acct-self"}), None)
    assert r.returncode == 0
    assert "WARN" in r.stderr


def test_cli_garbage_json_fails_closed():
    r = _run("not json", "test-acct-self")
    assert r.returncode == EXIT_MISMATCH
