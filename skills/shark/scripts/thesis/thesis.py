#!/usr/bin/env python3
"""
thesis.py — stdlib-only persistent trade-thesis store + deterministic re-score.
Part of the Shark Starter Kit.

Code computes, brain judges — mirrors risk.py / reflection.py: this module does
the deterministic checks + file I/O; the agent's own brain re-argues conviction
(the debate) only when this module says the thesis materially changed.

Thesis data lives in THESES.json (git-tracked, kit top-level) so it survives
across fires via the Step 7 commit. Closed theses prune to THESES_ARCHIVE.jsonl
(gitignored, audit-only).

Two layers:
  Layer 1  rescore(...)  — zero-LLM: score each assumption intact|weakening|violated,
                           emit deltas + an escalate? decision.            (no LLM)
  Layer 2  the heartbeat — runs the seeded debate ONLY when escalate is True.
"""
from __future__ import annotations

import json
import os
import ssl
import sys
import urllib.error
import urllib.request

PRICE_BAND = 0.015  # within 1.5% on the wrong side of a price level = "weakening"

DATA_BASE = "https://data.alpaca.markets"

STATUS_INTACT = "intact"
STATUS_WEAKENING = "weakening"
STATUS_VIOLATED = "violated"


# --- store: load / save (atomic) ---------------------------------------------

def load_theses(path):
    """Parse the thesis array. Missing/malformed -> [] (never raises)."""
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []
    return data if isinstance(data, list) else []


def save_theses(path, theses):
    """Write the thesis array atomically (tmp + os.replace — no corruption)."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(theses, f, indent=2)
    os.replace(tmp, path)


# --- store: queries (pure) ---------------------------------------------------

def get_open(theses):
    """Open theses only (the heartbeat hot path; closed live in the archive)."""
    return [x for x in theses if x.get("status") == "open"]


def find_open_by_ticker(theses, ticker):
    """First open thesis for a ticker, or None."""
    for x in get_open(theses):
        if x.get("ticker") == ticker:
            return x
    return None


# --- store: upsert -----------------------------------------------------------

def upsert_thesis(path, thesis):
    """Create or replace a thesis by id (idempotent — never duplicates)."""
    theses = load_theses(path)
    out, replaced = [], False
    for x in theses:
        if x.get("id") == thesis.get("id"):
            out.append(thesis)
            replaced = True
        else:
            out.append(x)
    if not replaced:
        out.append(thesis)
    save_theses(path, out)


# --- Layer 1: the check dispatch table (deterministic, zero-LLM) -------------
#
# Each function takes (param, ctx) and returns (status, verifiable). `verifiable`
# is False only when the data needed to score was missing (a failed fetch) — the
# caller treats that as a forced escalation. A closed set keeps Layer 1 parity-
# identical across brains; new types are reviewed code, never free-form.

_UNVERIFIABLE = (STATUS_WEAKENING, False)


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _check_price_above(param, ctx):
    price, level = _num(ctx.get("price")), _num(param)
    if price is None or level is None:
        return _UNVERIFIABLE
    if price >= level:
        return STATUS_INTACT, True
    if price >= level * (1 - PRICE_BAND):
        return STATUS_WEAKENING, True
    return STATUS_VIOLATED, True


def _check_price_below(param, ctx):
    price, level = _num(ctx.get("price")), _num(param)
    if price is None or level is None:
        return _UNVERIFIABLE
    if price <= level:
        return STATUS_INTACT, True
    if price <= level * (1 + PRICE_BAND):
        return STATUS_WEAKENING, True
    return STATUS_VIOLATED, True


def _check_regime_favorable(param, ctx):
    regime = ctx.get("regime")
    if regime is None:
        return _UNVERIFIABLE
    if regime == "favorable":
        return STATUS_INTACT, True
    if regime == "neutral":
        return STATUS_WEAKENING, True
    return STATUS_VIOLATED, True  # adverse / unfavorable / anything else


def _check_stop_distance(param, ctx):
    price = _num(ctx.get("price"))
    param = param or {}
    stop, minimum = _num(param.get("stop")), _num(param.get("min"))
    if price is None or stop is None or minimum is None or price == 0:
        return _UNVERIFIABLE
    dist = abs(price - stop) / price
    # Proximity warning only — never escalates to "violated" on its own.
    return (STATUS_INTACT, True) if dist >= minimum else (STATUS_WEAKENING, True)


def _check_manual(param, ctx):
    # Honest escape hatch: soft claims with no machine check stay intact and do
    # NOT force escalation. Surfaced to the brain as "unverifiable" elsewhere.
    return STATUS_INTACT, True


CHECKS = {
    "price_above": _check_price_above,
    "price_below": _check_price_below,
    "regime_favorable": _check_regime_favorable,
    "stop_distance": _check_stop_distance,
    "manual": _check_manual,
}


def score_check(check, ctx):
    """Score one check against fetched ctx -> (status, verifiable).
    Unknown type fails safe to (weakening, False) so the bug surfaces."""
    fn = CHECKS.get((check or {}).get("type"))
    if fn is None:
        return _UNVERIFIABLE
    return fn(check.get("param"), ctx or {})


# --- Layer 1 driver: rescore one thesis --------------------------------------

DELTA_LOG_CAP = 20


def _invalidation_status(thesis, ctx):
    """'breached' | 'safe' | 'unknown' for the thesis-level kill line.
    'unknown' (no price) escalates (re-debate) but must NOT force an exit."""
    inval = _num(thesis.get("invalidation_price"))
    if inval is None:
        return "safe"
    price = _num(ctx.get("price"))
    if price is None:
        return "unknown"  # can't confirm we're safe -> escalate, but don't exit
    breached = price < inval if thesis.get("direction") == "long" else price > inval
    return "breached" if breached else "safe"


def rescore(thesis, ctx, fire):
    """Score every assumption against fetched ctx; update statuses + delta_log;
    return {thesis, escalate, deltas}. Deterministic, zero-LLM (Layer 1).

    Escalate (run the seeded debate) when the thesis materially moved:
      - any core assumption is violated, OR
      - any assumption changed status this fire, OR
      - any assumption could not be verified this fire (failed fetch), OR
      - the invalidation price was breached.
    Otherwise the caller skips the debate and carries conviction forward.
    """
    deltas, escalate, any_core_violated = [], False, False
    for a in thesis.get("assumptions", []):
        old = a.get("status")
        status, verifiable = score_check(a.get("check"), ctx)
        if status != old:
            a["status"] = status
            a["status_fire"] = fire
            deltas.append(f"{a.get('id')} {old}->{status}")
            escalate = True
        if not verifiable:
            escalate = True
        if status == STATUS_VIOLATED and a.get("weight") == "core":
            any_core_violated = True

    inval_status = _invalidation_status(thesis, ctx)
    if any_core_violated:
        escalate = True
    if inval_status == "breached":
        deltas.append("invalidation breached")
        escalate = True
    elif inval_status == "unknown":
        escalate = True  # can't confirm safety -> re-debate, but not an exit

    if deltas:
        log = thesis.get("delta_log", [])
        log.append({"fire": fire, "change": "; ".join(deltas)})
        thesis["delta_log"] = log[-DELTA_LOG_CAP:]

    # exit_signal is the CONSERVATIVE held-position exit trigger: only a hard
    # core violation or a CONFIRMED breached invalidation. Deliberately narrower
    # than `escalate` — weakening, mere change, and failed fetches (including an
    # unconfirmable invalidation) never force an exit. A thesis-driven exit must
    # not fire on noise.
    exit_signal = bool(any_core_violated or inval_status == "breached")
    return {"thesis": thesis, "escalate": escalate,
            "exit_signal": exit_signal, "deltas": deltas}


def carry_forward(thesis):
    """No material change this fire: bump the carry counter, keep conviction."""
    thesis["carried_fires"] = int(thesis.get("carried_fires", 0)) + 1
    return thesis


def apply_conviction(thesis, conviction, fire):
    """A seeded debate re-derived conviction: record it, reset the carry counter."""
    thesis["conviction"] = conviction
    thesis["conviction_fire"] = fire
    thesis["carried_fires"] = 0
    return thesis


# --- exit hook: close + prune to archive -------------------------------------

def close_thesis(path, thesis_id, outcome, archive_path=None):
    """Flip a thesis to closed, attach its graded outcome, prune it from the hot
    file, and append it to the gitignored archive. Returns False if not found.

    Called at the same moment reflection.py resolves the trade's journal slip,
    so the thesis and the reflection lesson grade together. Keeping only open
    theses in THESES.json bounds the per-fire context cost."""
    theses = load_theses(path)
    closed, remaining = None, []
    for x in theses:
        if closed is None and x.get("id") == thesis_id:
            x["status"] = "closed"
            x["outcome"] = outcome
            closed = x
        else:
            remaining.append(x)
    if closed is None:
        return False
    if archive_path:
        with open(archive_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(closed) + "\n")
    save_theses(path, remaining)
    return True


# --- constructor (the debate calls this at entry) ----------------------------

def build_thesis(ticker, direction, conviction, invalidation_price, fire,
                 assumptions, kind="position"):
    """Assemble a well-formed open thesis from debate output. Seeds every
    assumption `intact`/`status_fire=fire` and derives a stable id from
    ticker + the fire's date (YYYYMMDD)."""
    day = "".join(fire[:10].split("-")) if fire else "00000000"
    seeded = []
    for a in assumptions:
        a = dict(a)
        a.setdefault("status", STATUS_INTACT)
        a.setdefault("status_fire", fire)
        a.setdefault("weight", "supporting")
        seeded.append(a)
    return {
        "id": f"th_{ticker}_{day}",
        "ticker": ticker,
        "kind": kind,                      # "position" | "candidate" (B, dormant in v1)
        "status": "open",
        "direction": direction,
        "conviction": conviction,
        "conviction_fire": fire,
        "carried_fires": 0,
        "invalidation_price": invalidation_price,
        "created_fire": fire,
        "created_by": "debate",
        "assumptions": seeded,
        "delta_log": [],
        "outcome": None,
    }


# --- orchestration: HEARTBEAT Step 3.6 entry ---------------------------------

def rescore_all(path, ctx_for, fire):
    """Re-score every OPEN thesis against live data and persist. `ctx_for(thesis)`
    returns the fetched ctx dict for that thesis (injected so this is testable and
    fail-soft). Carries conviction forward on any thesis that did not escalate;
    leaves escalated theses for the heartbeat to re-debate. Closed theses are
    untouched. Returns one summary row per open thesis."""
    theses = load_theses(path)
    summary = []
    for th in theses:
        if th.get("status") != "open":
            continue
        res = rescore(th, ctx_for(th) or {}, fire)
        if not res["escalate"]:
            carry_forward(th)
        summary.append({
            "ticker": th.get("ticker"),
            "id": th.get("id"),
            "escalate": res["escalate"],
            "exit_signal": res["exit_signal"],
            "deltas": res["deltas"],
            "conviction": th.get("conviction"),
            "carried_fires": th.get("carried_fires"),
        })
    save_theses(path, theses)
    return summary


# --- mesh mapping helpers (pure) ---------------------------------------------

_REGIME_LONG = {"Bull": "favorable", "Sideways": "neutral", "Bear": "adverse"}
_REGIME_SHORT = {"Bear": "favorable", "Sideways": "neutral", "Bull": "adverse"}


def regime_to_status(current_regime, direction):
    """Map markov `current_regime` (Bull/Sideways/Bear) to the favorable/neutral/
    adverse vocabulary the regime_favorable check expects, relative to direction.
    Unknown -> None (the fetcher then omits the key -> unverifiable -> escalate)."""
    table = _REGIME_SHORT if direction == "short" else _REGIME_LONG
    return table.get(current_regime)


def parse_latest_price(payload):
    """Extract last trade price from an Alpaca latest-trade payload, else None."""
    return _num((payload or {}).get("trade", {}).get("p"))


# --- fail-soft HTTP fetchers (injected req; never raise) ----------------------
#
# Each returns None on any failure so the matching check fails safe to
# (weakening, unverifiable) -> forced escalation. A wrong/missing mapping can
# therefore only cause an *extra debate*, never a silently-skipped one.

def _creds():
    key = os.environ.get("ALPACA_API_KEY") or os.environ.get("ALPACA_KEY_ID")
    sec = os.environ.get("ALPACA_SECRET_KEY") or os.environ.get("ALPACA_SECRET")
    return key, sec


def _req(base, method, path, headers=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(base + path, data=data, method=method)
    for k, v in (headers or {}).items():
        if v:
            r.add_header(k, v)
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


def fetch_price(ticker, req=_req):
    key, sec = _creds()
    headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec}
    try:
        st, payload = req(DATA_BASE, "GET",
                          f"/v2/stocks/{ticker}/trades/latest?feed=iex", headers)
    except Exception:
        return None
    return parse_latest_price(payload) if st and 200 <= st < 300 else None


def _local_regime_label(ticker):
    """Regime from on-box local-markov (../local-markov/local_markov.py).
    Returns 'Bull'|'Sideways'|'Bear' or None on any failure (fail-soft)."""
    import subprocess
    sib = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "..", "local-markov", "local_markov.py")
    try:
        out = subprocess.run(["python3", sib, ticker], capture_output=True,
                             text=True, timeout=25)
        return (json.loads(out.stdout or "{}") or {}).get("current_regime")
    except Exception:
        return None


def fetch_regime(ticker, direction, req=None):
    label = _local_regime_label(ticker)        # Bull/Sideways/Bear or None
    return regime_to_status(label, direction)  # -> favorable/neutral/adverse or None


def build_ctx(thesis, fetch_price=fetch_price, fetch_regime=fetch_regime):
    """Assemble the ctx for one thesis, fetching ONLY what its assumptions need.
    Fail-soft: a failed fetch leaves the key absent -> the check is unverifiable
    -> escalation. Regime comes from the on-box local-markov proxy (no mesh)."""
    types = {(a.get("check") or {}).get("type") for a in thesis.get("assumptions", [])}
    ctx = {}
    if {"price_above", "price_below", "stop_distance"} & types or thesis.get("invalidation_price") is not None:
        ctx["price"] = fetch_price(thesis.get("ticker"))
    if "regime_favorable" in types:
        ctx["regime"] = fetch_regime(thesis.get("ticker"), thesis.get("direction"))
    return ctx


# --- CLI (thin glue over the tested functions, for HEARTBEAT integration) ----

def _paths():
    base = os.path.dirname(os.path.abspath(__file__))
    path = os.environ.get("SHARK_THESES_PATH", os.path.join(base, "..", "..", "THESES.json"))
    arc = os.environ.get("SHARK_THESES_ARCHIVE_PATH",
                         os.path.join(base, "..", "..", "THESES_ARCHIVE.jsonl"))
    return path, arc


def _stdin_json():
    try:
        return json.load(sys.stdin)
    except Exception:
        return None


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("usage: thesis.py {create|rescore|set-conviction|close|list} ...",
              file=sys.stderr)
        return 2
    cmd = argv[0]
    path, arc = _paths()

    if cmd == "create":
        d = _stdin_json()
        if not isinstance(d, dict):
            return 3
        th = build_thesis(d["ticker"], d["direction"], d["conviction"],
                          d["invalidation_price"], d["fire"], d["assumptions"],
                          kind=d.get("kind", "position"))
        upsert_thesis(path, th)
        print(json.dumps({"id": th["id"]}))
        return 0

    if cmd == "rescore":
        # fire passed as argv[1]; the heartbeat supplies its own timestamp.
        fire = argv[1] if len(argv) > 1 else ""
        summary = rescore_all(path, build_ctx, fire)
        print(json.dumps(summary))
        return 0

    if cmd == "set-conviction":
        d = _stdin_json()
        if not isinstance(d, dict):
            return 3
        theses = load_theses(path)
        for th in theses:
            if th.get("id") == d["id"]:
                apply_conviction(th, d["conviction"], d["fire"])
        save_theses(path, theses)
        return 0

    if cmd == "close":
        d = _stdin_json()
        if not isinstance(d, dict):
            return 3
        tid = d.get("id")
        if not tid and d.get("ticker"):
            # close by ticker (what the heartbeat knows at reconciliation):
            # resolve to the open thesis's id via the tested lookup.
            match = find_open_by_ticker(load_theses(path), d["ticker"])
            tid = match["id"] if match else None
        ok = close_thesis(path, tid, d.get("outcome", {}), arc) if tid else False
        print(json.dumps({"closed": ok}))
        return 0

    if cmd == "list":
        print(json.dumps(get_open(load_theses(path))))
        return 0

    print(f"unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
