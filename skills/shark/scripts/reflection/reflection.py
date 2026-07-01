#!/usr/bin/env python3
"""
reflection.py — stdlib-only self-grading trade journal.
Part of the Shark Starter Kit.

Code computes, brain judges — mirrors risk.py: this module does the
deterministic math + file I/O; the agent's own brain writes the prose lesson
inline during the heartbeat.

Journal data lives in JOURNAL.md (git-tracked, kit top-level) so it survives
across fires via the Step 7 commit.

Three phases:
  A. append_pending(...)  — on entry, write a pending slip          (no LLM/net)
  B. compute_outcome(...) — on exit, grade (realized R + alpha/SPY) (net for SPY)
     resolve(...)         — write the brain's lesson, flip the tag  (atomic)
  C. get_context(...)     — inject recent lessons into next decision (no LLM/net)

Entry format (append-only markdown, HTML-comment delimiter):

  [2026-06-12 | INTC | conv 78 | pending]

  DECISION:
  Long INTC @ 31.20, stop 30.10. <thesis>

  <!-- ENTRY_END -->

After resolution:

  [2026-06-12 | INTC | conv 78 | +1.4R | alpha +0.8% | 6d]

  DECISION:
  ...

  REFLECTION:
  <2-3 sentence brain-written lesson>

  <!-- ENTRY_END -->
"""
from __future__ import annotations

import json
import os
import ssl
import sys
import urllib.error
import urllib.request
from datetime import date as _date

# HTML comment: cannot appear in LLM prose output, safe as a hard delimiter.
SEPARATOR = "\n\n<!-- ENTRY_END -->\n\n"
DEFAULT_ROTATION_CAP = 50
DATA_BASE = "https://data.alpaca.markets"
BENCHMARK = "SPY"


# --- Phase A: append_pending -------------------------------------------------

def append_pending(path, ticker, date, conviction, entry, stop, thesis):
    """Append a pending slip. Idempotent on (date, ticker)."""
    if os.path.exists(path):
        prefix = f"[{date} | {ticker} | conv {int(conviction)} | pending]"
        with open(path, encoding="utf-8") as f:
            if any(line.strip() == prefix for line in f):
                return
    tag = f"[{date} | {ticker} | conv {int(conviction)} | pending]"
    decision = f"Long {ticker} @ {float(entry):.2f}, stop {float(stop):.2f}. {thesis}".rstrip()
    entry_block = f"{tag}\n\nDECISION:\n{decision}{SEPARATOR}"
    with open(path, "a", encoding="utf-8") as f:
        f.write(entry_block)


# --- parsing -----------------------------------------------------------------

def _parse_entry(raw):
    """Parse one raw block -> dict, or None if it has no valid tag line."""
    lines = raw.strip().splitlines()
    if not lines:
        return None
    tag = lines[0].strip()
    if not (tag.startswith("[") and tag.endswith("]")):
        return None
    fields = [f.strip() for f in tag[1:-1].split("|")]
    if len(fields) < 4:
        return None
    date, ticker, conv_field = fields[0], fields[1], fields[2]
    try:
        conviction = int(conv_field.replace("conv", "").strip())
    except ValueError:
        conviction = None
    pending = fields[-1] == "pending"
    body = "\n".join(lines[1:])
    decision, reflection = "", ""
    if "DECISION:" in body:
        after = body.split("DECISION:", 1)[1]
        if "REFLECTION:" in after:
            decision, reflection = after.split("REFLECTION:", 1)
        else:
            decision = after
    return {
        "date": date,
        "ticker": ticker,
        "conviction": conviction,
        "pending": pending,
        "tag": tag,
        "decision": decision.strip(),
        "reflection": reflection.strip(),
    }


def load_entries(path):
    """Parse all entries from the journal. Missing/malformed -> []/[skipped]."""
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        text = f.read()
    out = []
    for raw in text.split(SEPARATOR):
        if not raw.strip():
            continue
        parsed = _parse_entry(raw)
        if parsed:
            out.append(parsed)
    return out


def get_pending(path):
    """Return entries still awaiting an outcome (for Phase B)."""
    return [e for e in load_entries(path) if e["pending"]]


# --- grading math (pure) -----------------------------------------------------

def _days_between(start, end):
    y1, m1, d1 = (int(x) for x in start.split("-"))
    y2, m2, d2 = (int(x) for x in end.split("-"))
    return (_date(y2, m2, d2) - _date(y1, m1, d1)).days


def compute_outcome(entry_price, exit_price, entry_date, exit_date,
                    realized_R, spy_return=None):
    """Deterministic outcome bundle. alpha is None when SPY is unavailable."""
    raw_return = (float(exit_price) - float(entry_price)) / float(entry_price)
    alpha = None if spy_return is None else raw_return - float(spy_return)
    return {
        "raw_return": raw_return,
        "realized_R": float(realized_R),
        "alpha": alpha,
        "holding_days": _days_between(entry_date, exit_date),
        "benchmark": BENCHMARK,
    }


# --- SPY benchmark (injected network, fail-soft) -----------------------------

def _creds():
    key = os.environ.get("ALPACA_API_KEY") or os.environ.get("ALPACA_KEY_ID")
    sec = os.environ.get("ALPACA_SECRET_KEY") or os.environ.get("ALPACA_SECRET")
    return key, sec


def _req(base, key, sec, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(base + path, data=data, method=method)
    if key:
        r.add_header("APCA-API-KEY-ID", key)
    if sec:
        r.add_header("APCA-API-SECRET-KEY", sec)
    try:
        with urllib.request.urlopen(
            r, context=ssl.create_default_context(), timeout=20
        ) as resp:
            txt = resp.read().decode()
            return resp.status, (json.loads(txt) if txt else {})
    except urllib.error.HTTPError as e:
        return e.code, {}
    except Exception:
        return 0, {}


def spy_return_pct(entry_date, exit_date, req=_req):
    """SPY first->last daily close over [entry_date, exit_date]. None on any
    failure (fail-soft — grading must never be blocked by the benchmark)."""
    key, sec = _creds()
    path = (
        f"/v2/stocks/{BENCHMARK}/bars?timeframe=1Day"
        f"&start={entry_date}&end={exit_date}&adjustment=raw&feed=iex"
    )
    try:
        st, payload = req(DATA_BASE, key, sec, "GET", path)
    except Exception:
        return None
    if not (st and 200 <= st < 300):
        return None
    bars = payload.get("bars") or []
    if not bars:
        return None
    first, last = bars[0].get("c"), bars[-1].get("c")
    if not first or first == 0 or last is None:
        return None
    return (last - first) / first


# --- Phase B: resolve (atomic) -----------------------------------------------

def _resolved_tag(date, ticker, conviction, outcome):
    r_mult = f"{outcome['realized_R']:+.1f}R"
    a = outcome["alpha"]
    alpha = "alpha n/a" if a is None else f"alpha {a:+.1%}"
    return (f"[{date} | {ticker} | conv {int(conviction)} | "
            f"{r_mult} | {alpha} | {outcome['holding_days']}d]")


def _apply_rotation(blocks, cap):
    """Keep all pending + the most-recent `cap` resolved, preserving order."""
    if cap is None:
        return blocks
    parsed = [(_parse_entry(b), b) for b in blocks if b.strip()]
    resolved_idx = [i for i, (p, _) in enumerate(parsed) if p and not p["pending"]]
    if len(resolved_idx) <= cap:
        return [b for _, b in parsed]
    drop = set(resolved_idx[: len(resolved_idx) - cap])
    return [b for i, (_, b) in enumerate(parsed) if i not in drop]


def resolve(path, ticker, date, outcome, lesson_text,
            rotation_cap=DEFAULT_ROTATION_CAP):
    """Flip the first matching pending slip to resolved and append the lesson.
    Atomic: temp-file + os.replace so a crash never corrupts the journal."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        blocks = f.read().split(SEPARATOR)
    pending_prefix = f"[{date} | {ticker} | conv"
    new_blocks, updated = [], False
    for block in blocks:
        stripped = block.strip()
        if not stripped:
            continue
        lines = stripped.splitlines()
        tag = lines[0].strip()
        if (not updated and tag.startswith(pending_prefix)
                and tag.endswith("| pending]")):
            conviction = _parse_entry(stripped)["conviction"]
            new_tag = _resolved_tag(date, ticker, conviction, outcome)
            rest = "\n".join(lines[1:]).strip()
            new_blocks.append(f"{new_tag}\n\n{rest}\n\nREFLECTION:\n{lesson_text.strip()}")
            updated = True
        else:
            new_blocks.append(stripped)
    if not updated:
        return
    new_blocks = _apply_rotation(new_blocks, rotation_cap)
    new_text = SEPARATOR.join(new_blocks) + SEPARATOR
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(new_text)
    os.replace(tmp, path)


# --- Phase C: get_context ----------------------------------------------------

def _fmt_full(e):
    return f"{e['tag']}\n{e['reflection']}".strip()


def _fmt_reflection(e):
    return f"{e['ticker']} ({e['date']}): {e['reflection']}".strip()


def get_context(path, ticker, n_same=5, n_cross=3):
    """Formatted recent lessons for prompt injection: most-recent same-ticker
    entries + recent cross-ticker lessons. Empty string when none resolved."""
    resolved = [e for e in load_entries(path) if not e["pending"] and e["reflection"]]
    if not resolved:
        return ""
    same, cross = [], []
    for e in reversed(resolved):  # most-recent first
        if e["ticker"] == ticker and len(same) < n_same:
            same.append(e)
        elif e["ticker"] != ticker and len(cross) < n_cross:
            cross.append(e)
        if len(same) >= n_same and len(cross) >= n_cross:
            break
    if not same and not cross:
        return ""
    parts = []
    if same:
        parts.append(f"Past {ticker} trades (most recent first):")
        parts.extend(_fmt_full(e) for e in same)
    if cross:
        parts.append("Recent cross-ticker lessons:")
        parts.extend(_fmt_reflection(e) for e in cross)
    return "\n\n".join(parts)


# --- CLI (thin glue over the tested functions, for HEARTBEAT integration) ----

def _stdin_json():
    try:
        return json.load(sys.stdin)
    except Exception:
        return None


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("usage: reflection.py {append|outcome|resolve|context} ...", file=sys.stderr)
        return 2
    cmd = argv[0]
    path = os.environ.get("SHARK_JOURNAL_PATH", "JOURNAL.md")

    if cmd == "append":
        d = _stdin_json()
        if not isinstance(d, dict):
            return 3
        append_pending(path, d["ticker"], d["date"], d["conviction"],
                       d["entry"], d["stop"], d.get("thesis", ""))
        return 0

    if cmd == "outcome":
        d = _stdin_json()
        if not isinstance(d, dict):
            return 3
        spy = spy_return_pct(d["entry_date"], d["exit_date"])
        out = compute_outcome(d["entry_price"], d["exit_price"],
                              d["entry_date"], d["exit_date"],
                              d["realized_R"], spy_return=spy)
        print(json.dumps(out))
        return 0

    if cmd == "resolve":
        d = _stdin_json()
        if not isinstance(d, dict):
            return 3
        resolve(path, d["ticker"], d["date"], d["outcome"], d["lesson"])
        return 0

    if cmd == "pending":
        # List open (pending) slips so the heartbeat can recover each closed
        # position's original entry price + entry date for grading at exit.
        print(json.dumps(get_pending(path)))
        return 0

    if cmd == "context":
        if len(argv) < 2:
            return 2
        print(get_context(path, argv[1]))
        return 0

    print(f"unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
