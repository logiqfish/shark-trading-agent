#!/usr/bin/env python3
"""
debate.py — stdlib-only bull/bear/referee conviction debate helper.
Part of the Shark Starter Kit.

Code computes, brain judges — mirrors risk.py and reflection.py: this module
does the deterministic contract (verdict normalization + transcript logging);
the bull/bear/referee turns are LLM prose run by the agent's own brain during
the heartbeat, per DEBATE.md.

The Referee emits a 0-100 conviction; that number flows into HEARTBEAT Step 5
(floor N=65) and Step 5.5 risk bands UNCHANGED. This helper guarantees the
score handed to the gate is validated (clamped int / known stance) and that
the full debate transcript is logged for the audit trail (talk + parity proof).

CLI (reads JSON on stdin):
  record  {ticker,date,bull,bear,verdict:{conviction,stance,rationale}}
          -> normalizes the verdict, appends the transcript to the dated memory
             file, and prints the normalized {ticker,conviction,stance,rationale}.

Exit codes: 0 ok | 2 usage | 3 bad stdin JSON / malformed verdict
"""
from __future__ import annotations

import json
import os
import sys

# HTML comment delimiter: cannot appear in LLM prose, safe as a hard separator
# (same convention as reflection.py's JOURNAL entries).
SEPARATOR = "\n\n<!-- DEBATE_END -->\n\n"
VALID_STANCES = ("bullish", "bearish", "neutral")
MAX_RATIONALE = 200


def normalize_verdict(raw):
    """Validate + normalize a referee verdict dict.

    Returns {conviction: int in [0,100], stance: one of VALID_STANCES,
    rationale: str (<= MAX_RATIONALE chars)}.

    Raises ValueError if conviction is missing or non-numeric — a malformed
    score must never be silently passed to the conviction gate.
    """
    if "conviction" not in raw:
        raise ValueError("verdict missing 'conviction'")
    try:
        conviction = int(float(raw["conviction"]))
    except (TypeError, ValueError):
        raise ValueError(f"non-numeric conviction: {raw.get('conviction')!r}")
    conviction = max(0, min(100, conviction))

    stance = str(raw.get("stance", "")).strip().lower()
    if stance not in VALID_STANCES:
        stance = "neutral"

    rationale = str(raw.get("rationale", "")).strip()[:MAX_RATIONALE]

    return {"conviction": conviction, "stance": stance, "rationale": rationale}


def record_debate(path, ticker, date, bull, bear, verdict):
    """Append a debate transcript block to the dated memory file.

    Idempotent on (date, ticker). The verdict is normalized before logging so
    an out-of-range raw score is never written un-clamped.
    """
    v = normalize_verdict(verdict)
    tag = f"[{date} | {ticker} | conv {v['conviction']} | {v['stance']}]"
    if os.path.exists(path):
        marker = f"| {ticker} |"
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("[") and line.endswith("]") and marker in line:
                    return  # already recorded a debate for this ticker today
    block = (
        f"{tag}\n\n"
        f"BULL:\n{str(bull).strip()}\n\n"
        f"BEAR:\n{str(bear).strip()}\n\n"
        f"VERDICT:\nconviction {v['conviction']} | {v['stance']} | {v['rationale']}"
        f"{SEPARATOR}"
    )
    with open(path, "a", encoding="utf-8") as f:
        f.write(block)


def _memory_path(date):
    """Resolve the dated memory file. SHARK_MEMORY_DIR overrides the default."""
    base = os.environ.get("SHARK_MEMORY_DIR", "memory")
    return os.path.join(base, f"{date}.md")


def main():
    args = sys.argv[1:]
    if not args or args[0] != "record":
        print("usage: debate.sh record  (JSON on stdin)", file=sys.stderr)
        sys.exit(2)

    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        print("debate: bad stdin JSON", file=sys.stderr)
        sys.exit(3)
    if not isinstance(payload, dict):
        print("debate: stdin JSON must be an object", file=sys.stderr)
        sys.exit(3)

    ticker = str(payload.get("ticker", "")).upper()
    date = str(payload.get("date", ""))
    if not ticker or not date:
        print("debate: 'ticker' and 'date' are required", file=sys.stderr)
        sys.exit(3)

    try:
        verdict = normalize_verdict(payload.get("verdict") or {})
    except ValueError as e:
        print(f"debate: malformed verdict: {e}", file=sys.stderr)
        sys.exit(3)

    path = _memory_path(date)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    record_debate(path, ticker, date,
                  payload.get("bull", ""), payload.get("bear", ""), verdict)

    print(json.dumps({"ticker": ticker, **verdict}))
    sys.exit(0)


if __name__ == "__main__":
    main()
