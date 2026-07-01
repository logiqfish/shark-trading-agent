#!/usr/bin/env python3
"""Alpaca account-identity guard — jq-free, stdlib-only. Part of the Shark Starter Kit.

Why this exists: a bad or rotated key set can silently authenticate to the
WRONG paper account (and a future real-money key set, to the wrong real
account). This guard reads the live `account_number` and FAILS CLOSED unless it
matches the pinned `ALPACA_ACCOUNT_ID`. Wire it into the per-fire account fetch
so the wrong-account case can never place an order.

Policy:
  - mismatch (live != expected)  -> fail closed (exit 3). The dangerous case;
                                    this is the wrong-account / bad-rotation guard.
  - expected unset / empty       -> loud WARN on stderr, proceed. Keeps an
                                    as-yet-unconfigured runtime trading on paper
                                    rather than bricking it mid-day. Set
                                    ALPACA_ACCOUNT_ID in your env to arm it.
  - match                        -> ok.

No jq (it isn't present on every runtime); python3 stdlib only.
"""
from __future__ import annotations

import json
import os
import sys

EXIT_MISMATCH = 3


def evaluate(account, expected):
    """Pure decision — no I/O. Returns (ok: bool, message: str).

    account  : dict parsed from Alpaca /v2/account (anything with 'account_number').
    expected : the pinned ALPACA_ACCOUNT_ID, or None/'' if unset.
    """
    live = ""
    if isinstance(account, dict):
        live = str(account.get("account_number", "") or "")
    if not expected:
        return True, (
            "WARN: ALPACA_ACCOUNT_ID not set — account-identity assertion SKIPPED "
            f"(live account={live or 'unknown'}). Set it in this runtime's env to arm the guard."
        )
    if live != expected:
        return False, (
            f"ACCOUNT MISMATCH — keys authenticate as '{live or 'unknown'}' but "
            f"ALPACA_ACCOUNT_ID='{expected}'. Refusing to proceed "
            "(wrong account or bad key rotation)."
        )
    return True, f"OK: account {live} matches ALPACA_ACCOUNT_ID."


def main():
    """Read account JSON from stdin, compare against $ALPACA_ACCOUNT_ID, exit 3 on mismatch."""
    raw = sys.stdin.read()
    try:
        account = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        print("ACCOUNT GUARD: could not parse account JSON from stdin.", file=sys.stderr)
        sys.exit(EXIT_MISMATCH)
    ok, message = evaluate(account, os.environ.get("ALPACA_ACCOUNT_ID") or None)
    print(message, file=sys.stderr)
    if not ok:
        sys.exit(EXIT_MISMATCH)


if __name__ == "__main__":
    main()
