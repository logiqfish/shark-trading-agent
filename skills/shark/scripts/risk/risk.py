#!/usr/bin/env python3
"""
risk.py — stdlib-only position-sizing + pre-trade risk gates.
Part of the Shark Starter Kit.

Reads JSON from stdin, writes ONE JSON line to stdout, human logs to stderr.

CLI input (stdin JSON):
  {
    "account":   {"equity": float, "cash": float, "buying_power": float?, "last_equity": float?},
    "candidate": {"ticker": str, "price": float, "conviction": int,
                  "target_price": float?},
    "positions": [{"ticker": str, "market_value": float}, ...],
    "catalyst":  {... optional earnings packet ...}?   (optional)
  }

Exit codes:
  0   PASS    — sized and all gates pass
  10  REJECT  — sizing rejected OR a gate/dire-trigger fired (do not trade)
  3   parse failure (bad stdin JSON)
"""

from __future__ import annotations

import json
import math
import os
import sys
from datetime import datetime, timezone

# --- Constants: single source of truth (DECISION-POLICY §3, §7 #4) ----------
MAX_POSITION_PCT        = 0.20
CASH_RESERVE_PCT        = 0.10
DEFAULT_STOP_PCT        = 0.05
MIN_RR                  = 2.0
CONCENTRATION_PCT       = 0.25
DRAWDOWN_PCT            = 0.05
EARNINGS_BLACKOUT_HOURS = 48
CONVICTION_FLOOR        = 65
MIN_NOTIONAL            = 1.0    # Alpaca fractional/notional minimum ($1)

# --- Small-account profile v1 (SHARK_SMALL_ACCOUNT, default OFF) -------------
SMALL_MAX_POSITION_PCT = 0.05
SMALL_MAX_POSITION_USD = 50.0
MAX_OPEN_POSITIONS     = 3
DAILY_LOSS_HALT_USD    = 15.0

# --- Whole-share swing profile v2 (SHARK_WHOLE_SWING_V2) ---------------------
# $25k account, whole shares only, fixed-fractional risk sizing. The protective
# stop is an INPUT: shares = floor(risk_fraction * equity / (entry - stop)).
# Conviction maps to a risk fraction; the stop decides how many shares.
MAX_OPEN_POSITIONS_V2  = 8
DAILY_LOSS_HALT_PCT    = 0.03   # -3% of day-start equity halts new entries

# (lo, hi inclusive, risk_fraction) — conviction 65-69 trades at the smallest
# size so the demo stays active; capped at 1.25% so conviction scales without
# recklessness. Trade floor stays at CONVICTION_FLOOR (65).
CONVICTION_RISK_BANDS = [
    (65, 69, 0.0050),
    (70, 79, 0.0075),
    (80, 89, 0.0100),
    (90, 100, 0.0125),
]


def _risk_band(conviction):
    for lo, hi, frac in CONVICTION_RISK_BANDS:
        if lo <= conviction <= hi:
            return frac
    return None


def size_v2(equity, entry_price, stop_price, conviction, discretionary=False):
    """Fixed-fractional risk sizing for the whole-share swing profile (v2).

    The agent's protective stop is required (it is the invalidation point and
    the denominator of the size math). Returns
    {qty, risk_fraction, dollar_risk, stop_price, reject_reason}.

    discretionary=True bypasses the conviction floor (human gut-trade override)
    while keeping every other risk gate intact. A below-floor gut trade sizes at
    the conservative floor band (65-69 → 0.50%) so it is never larger than the
    minimum systematic trade.
    """
    if equity <= 0 or entry_price <= 0:
        return {"qty": 0, "risk_fraction": 0.0, "dollar_risk": 0.0,
                "stop_price": 0.0, "reject_reason": "non-positive equity or price"}
    if conviction < CONVICTION_FLOOR and not discretionary:
        return {"qty": 0, "risk_fraction": 0.0, "dollar_risk": 0.0,
                "stop_price": 0.0, "reject_reason": "below conviction floor"}
    # discretionary gut trade below the floor sizes at the conservative floor band
    frac = _risk_band(max(conviction, CONVICTION_FLOOR))
    if frac is None:
        return {"qty": 0, "risk_fraction": 0.0, "dollar_risk": 0.0,
                "stop_price": 0.0, "reject_reason": "conviction out of range"}
    if stop_price <= 0:
        return {"qty": 0, "risk_fraction": frac, "dollar_risk": 0.0,
                "stop_price": 0.0, "reject_reason": "non-positive stop"}
    if stop_price >= entry_price:
        return {"qty": 0, "risk_fraction": frac, "dollar_risk": 0.0,
                "stop_price": stop_price, "reject_reason": "stop not below entry"}

    dollar_risk = frac * equity
    per_share_risk = entry_price - stop_price
    qty = math.floor(dollar_risk / per_share_risk)
    if qty < 1:
        return {"qty": 0, "risk_fraction": frac, "dollar_risk": dollar_risk,
                "stop_price": stop_price, "reject_reason": "risk budget below one share"}
    # Whole-share allocation cap: never let the risk-sized position breach the
    # 20% cap. Skip the trade rather than silently trimming below the intended
    # risk (a trimmed position would not honor the agent's invalidation math).
    if qty * entry_price > MAX_POSITION_PCT * equity:
        return {"qty": 0, "risk_fraction": frac, "dollar_risk": dollar_risk,
                "stop_price": stop_price, "reject_reason": "position exceeds allocation cap"}
    return {"qty": qty, "risk_fraction": frac, "dollar_risk": dollar_risk,
            "stop_price": stop_price, "reject_reason": None}


def _position_cap(equity, small_account):
    """Dollar cap on a single position. Default = 20% of equity; small-account
    = min(5% of equity, $50)."""
    if small_account:
        return min(SMALL_MAX_POSITION_PCT * equity, SMALL_MAX_POSITION_USD)
    return MAX_POSITION_PCT * equity

# (lo, hi inclusive, target_pct) — target_pct is the tier UPPER bound,
# capped by MAX_POSITION_PCT.
CONVICTION_TIERS = [
    (65, 79, 0.15),
    (80, 89, 0.20),
    (90, 100, 0.20),
]


def _tier_pct(conviction):
    for lo, hi, pct in CONVICTION_TIERS:
        if lo <= conviction <= hi:
            return min(pct, MAX_POSITION_PCT)
    return None


def size(equity, price, conviction, fractional=False, small_account=False):
    """Deterministic sizing.

    Returns {qty, target_pct, stop_price, reject_reason}.
    reject_reason is None on success; a string (with qty=0) on rejection.

    fractional=True (SHARK_FRACTIONAL): allow a sub-share so a small account can
    take an expensive stock; dollar-sized and floored at Alpaca's $1 minimum.
    Default (whole shares) is unchanged.
    """
    if equity <= 0 or price <= 0:
        return {"qty": 0, "target_pct": 0.0, "stop_price": 0.0,
                "reject_reason": "non-positive equity or price"}
    if conviction < CONVICTION_FLOOR:
        return {"qty": 0, "target_pct": 0.0, "stop_price": 0.0,
                "reject_reason": "below conviction floor"}
    target_pct = _tier_pct(conviction)
    if target_pct is None:
        return {"qty": 0, "target_pct": 0.0, "stop_price": 0.0,
                "reject_reason": "conviction out of range"}
    stop_price = round(price * (1 - DEFAULT_STOP_PCT), 2)

    cap_usd = _position_cap(equity, small_account)

    if fractional:
        # Dollar-sized sub-share, capped at the active position cap.
        notional = min(target_pct * equity, cap_usd)
        qty = round(notional / price, 6)
        if qty * price < MIN_NOTIONAL:
            return {"qty": 0, "target_pct": target_pct, "stop_price": 0.0,
                    "reject_reason": "below minimum notional"}
        return {"qty": qty, "target_pct": target_pct, "stop_price": stop_price,
                "reject_reason": None}

    qty = math.floor(target_pct * equity / price)
    # Hard-cap backstop: never exceed the active position cap.
    qty = min(qty, math.floor(cap_usd / price))
    if qty < 1:
        return {"qty": 0, "target_pct": target_pct, "stop_price": 0.0,
                "reject_reason": "single share exceeds tier cap"}
    return {"qty": qty, "target_pct": target_pct, "stop_price": stop_price,
            "reject_reason": None}


def _earnings_check(catalyst, now):
    """Return 'blackout' | 'clear' | 'unknown' from an optional earnings packet.

    The packet is authoritative for earnings and computes the blackout
    window server-side, so prefer its `within_48h` boolean. Fall back to
    parsing a next-report date (`next_report_date`, or the legacy
    `next_earnings_date`) as an ISO 8601 string. Absent/unreachable/
    unparseable -> 'unknown' (a warning, never a block).
    """
    if not catalyst:
        return "unknown"
    earnings = catalyst.get("earnings")
    if not earnings:
        return "unknown"
    # 1. Trust the service's own 48h computation when present.
    within = earnings.get("within_48h")
    if isinstance(within, bool):
        return "blackout" if within else "clear"
    # 2. Fall back to a next-report date field.
    date_str = earnings.get("next_report_date") or earnings.get("next_earnings_date")
    if not date_str:
        return "unknown"
    try:
        # Python 3.9 fromisoformat doesn't accept a trailing 'Z'; normalize it.
        dt = datetime.fromisoformat(str(date_str).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return "unknown"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    hours = (dt - now).total_seconds() / 3600.0
    if 0 <= hours <= EARNINGS_BLACKOUT_HOURS:
        return "blackout"
    return "clear"


def _trip_equity(account, equity):
    """Equity to test the daily-loss halt against. Uses the broker-derived
    session LOW when present (latching — a low can't un-happen, so the halt
    stays tripped for the session even if equity recovers), else falls back to
    current equity (point-in-time, the legacy behavior, used when the
    portfolio-history fetch was unavailable). See session_pnl.py."""
    low = account.get("session_low_equity")
    if low is None:
        return equity
    try:
        v = float(low)
    except (TypeError, ValueError):
        return equity
    # Ignore non-finite (NaN/inf) or non-positive lows from a glitchy payload.
    # A NaN would otherwise silently NO-OP the halt (NaN comparisons are always
    # False) — the dangerous direction for a safety gate — and a spurious 0 would
    # falsely trip. Fall back to current equity so the gate still applies.
    if not math.isfinite(v) or v <= 0:
        return equity
    return v


def _spendable(account):
    """Settled cash usable right now. min(cash, buying_power) when buying_power is
    supplied (cash account: buying_power=settled tightens; margin: buying_power>=cash
    so unchanged); falls back to cash when buying_power is absent/unparseable
    (backward-compatible — payloads that don't carry buying_power behave as before)."""
    cash = float(account.get("cash", 0) or 0)
    bp = account.get("buying_power")
    # bool is an int subclass (float(True)==1.0), so route True/False to the safe
    # cash fallback rather than a spurious $1 spendable. None = no buying_power.
    if bp is None or isinstance(bp, bool):
        return cash
    try:
        return max(0.0, min(cash, float(bp)))
    except (TypeError, ValueError):
        return cash


def gate(account, candidate, positions, catalyst=None, now=None,
         small_account=False, whole_swing=False):
    """Pre-trade eligibility + computable dire-gates.

    candidate must carry `qty` (the sized quantity). The CLI injects it from
    size(); a standalone caller must supply it.

    whole_swing=True (SHARK_WHOLE_SWING_V2): R/R uses the agent's input
    `stop_price` (not a derived 5% stop), the open-position cap is 5, the
    daily-loss halt is -3% of day-start equity, and no-averaging-down applies.

    Returns {pass, gates_failed, dire_triggers, earnings_check, notes}.
    """
    gates_failed = []
    dire_triggers = []
    notes = {}

    equity = float(account.get("equity", 0) or 0)
    spendable = _spendable(account)
    price = float(candidate.get("price", 0) or 0)
    qty = float(candidate.get("qty", 0) or 0)   # float: a fractional qty must not truncate
    notional = qty * price

    # Eligibility: max position (cap depends on profile).
    pos_cap = _position_cap(equity, small_account)
    if equity <= 0 or notional > pos_cap:
        gates_failed.append("max_position")

    # Eligibility: cash reserve must survive the trade.
    if spendable - notional < CASH_RESERVE_PCT * equity:
        gates_failed.append("cash_reserve")

    # Eligibility: risk/reward. v2 uses the agent's input stop (the real
    # invalidation point); legacy/v1 derives a 5%-below-entry stop.
    if whole_swing:
        try:
            stop_price = float(candidate.get("stop_price"))
        except (TypeError, ValueError):
            stop_price = round(price * (1 - DEFAULT_STOP_PCT), 2)
    else:
        stop_price = round(price * (1 - DEFAULT_STOP_PCT), 2)
    target_price = candidate.get("target_price")
    try:
        target_val = None if target_price is None else float(target_price)
    except (TypeError, ValueError):
        target_val = None  # unparseable target degrades to "no target"
    if target_val is None:
        notes["risk_reward"] = "no_target"
    else:
        risk_amt = price - stop_price
        reward = target_val - price
        # Cross-multiply (avoid float division) with a tiny epsilon so a trade
        # that is mathematically exactly MIN_RR isn't spuriously rejected by
        # binary-float drift (e.g. reward/risk == 1.9999999999999962).
        if risk_amt <= 0 or reward < MIN_RR * risk_amt - 1e-9:
            gates_failed.append("risk_reward")

    ticker = (candidate.get("ticker") or "").upper()

    # Cap the number of concurrent open positions (3 in v1, 5 in v2).
    if small_account or whole_swing:
        open_cap = MAX_OPEN_POSITIONS_V2 if whole_swing else MAX_OPEN_POSITIONS
        held_tickers = {
            (p.get("ticker") or "").upper()
            for p in positions
            if float(p.get("market_value", 0) or 0) != 0
        }
        if ticker not in held_tickers and len(held_tickers) >= open_cap:
            gates_failed.append("max_open_positions")

    # Never add to a position currently held at a loss.
    if small_account or whole_swing:
        for p in positions:
            if (p.get("ticker") or "").upper() == ticker:
                try:
                    upl = float(p.get("unrealized_pl", 0) or 0)
                except (TypeError, ValueError):
                    upl = 0.0
                if upl < 0:
                    gates_failed.append("averaging_down")
                    break

    # Dire-gate §3.1: concentration. Existing holding in this ticker + new.
    existing = sum(
        float(p.get("market_value", 0) or 0)
        for p in positions
        if (p.get("ticker") or "").upper() == ticker
    )
    if equity <= 0 or (existing + notional) > CONCENTRATION_PCT * equity:
        dire_triggers.append("concentration")

    # Dire-gate §3.3: single-session drawdown. Cross-multiply (not float
    # division) with a tiny epsilon so a true threshold drop on cent-quantized
    # broker equity isn't missed by binary-float drift — a missed halt is the
    # dangerous direction for a safety gate.
    last_equity = account.get("last_equity")
    try:
        le = None if last_equity is None else float(last_equity)
    except (TypeError, ValueError):
        le = None  # unparseable last_equity degrades to "no last equity"
    if le is None:
        notes["drawdown"] = "no_last_equity"
    elif le > 0 and (le - equity) >= DRAWDOWN_PCT * le - 1e-9:
        dire_triggers.append("drawdown")

    # Daily-loss halt. Trips when session P&L crosses the limit and STAYS
    # tripped (the caller persists the halt for the session). Epsilon biases
    # toward tripping — a missed halt is the dangerous direction. v1 uses a flat
    # -$15; v2 uses -3% of day-start equity.
    if small_account or whole_swing:
        day_start = account.get("day_start_equity")
        try:
            ds = None if day_start is None else float(day_start)
        except (TypeError, ValueError):
            ds = None
        if ds is None:
            notes["daily_loss_halt"] = "no_day_start_equity"
        else:
            limit = DAILY_LOSS_HALT_PCT * ds if whole_swing else DAILY_LOSS_HALT_USD
            if (_trip_equity(account, equity) - ds) <= -limit + 1e-9:
                gates_failed.append("daily_loss_halt")

    # Dire-gate §3.4: earnings blackout (fail-open to 'unknown').
    if now is None:
        now = datetime.now(timezone.utc)
    earnings_check = _earnings_check(catalyst, now)
    if earnings_check == "blackout":
        dire_triggers.append("earnings_blackout")

    passed = not gates_failed and not dire_triggers
    return {"pass": passed, "gates_failed": gates_failed,
            "dire_triggers": dire_triggers, "earnings_check": earnings_check,
            "notes": notes}


def _decide(payload, now=None, fractional=None, small_account=None, whole_swing=None):
    """Run size() then gate() (with the sized qty injected) and merge into one
    verdict. Returns (verdict_dict, exit_code)."""
    if now is None:
        now = datetime.now(timezone.utc)
    if fractional is None:
        fractional = os.environ.get("SHARK_FRACTIONAL") == "1"
    if small_account is None:
        small_account = os.environ.get("SHARK_SMALL_ACCOUNT") == "1"
    if whole_swing is None:
        whole_swing = os.environ.get("SHARK_WHOLE_SWING_V2") == "1"
    account = payload.get("account") or {}
    candidate = dict(payload.get("candidate") or {})
    positions = payload.get("positions") or []
    catalyst = payload.get("catalyst")

    if whole_swing:
        return _decide_v2(account, candidate, positions, catalyst, now)

    sized = size(
        float(account.get("equity", 0) or 0),
        float(candidate.get("price", 0) or 0),
        int(candidate.get("conviction", 0) or 0),
        fractional=fractional,
        small_account=small_account,
    )
    candidate["qty"] = sized["qty"]  # inject sized qty for gate's notional checks
    gated = gate(account, candidate, positions, catalyst, now=now,
                 small_account=small_account)

    rejected = sized["reject_reason"] is not None
    passed = (not rejected) and gated["pass"]
    verdict = {
        "ticker": (candidate.get("ticker") or "").upper(),
        "qty": sized["qty"],
        "fractional": fractional,
        "small_account": small_account,
        "target_pct": sized["target_pct"],
        "stop_price": sized["stop_price"],
        "reject_reason": sized["reject_reason"],
        "pass": passed,
        "gates_failed": gated["gates_failed"],
        "dire_triggers": gated["dire_triggers"],
        "earnings_check": gated["earnings_check"],
        "notes": gated["notes"],
    }
    return verdict, (0 if passed else 10)


def _decide_v2(account, candidate, positions, catalyst, now):
    """Whole-share swing v2 path: fixed-fractional risk sizing off the agent's
    required protective stop, then the v2 gates.

    Passes the candidate's `discretionary` flag through to size_v2, coerced
    safely here (risk.sh round-trips through shell, so the JSON string "false"
    must NOT bypass the conviction floor — bool("false") is True)."""
    equity = float(account.get("equity", 0) or 0)
    entry = float(candidate.get("price", 0) or 0)
    conviction = int(candidate.get("conviction", 0) or 0)
    _disc = candidate.get("discretionary")
    discretionary = (_disc.strip().lower() in ("true", "1", "yes")
                     if isinstance(_disc, str) else bool(_disc))
    raw_stop = candidate.get("stop_price")
    ticker = (candidate.get("ticker") or "").upper()

    base = {
        "ticker": ticker, "qty": 0, "whole_swing": True, "fractional": False,
        "discretionary": discretionary,
        "risk_fraction": 0.0, "dollar_risk": 0.0, "stop_price": 0.0,
        "gates_failed": [], "dire_triggers": [], "earnings_check": "unknown",
        "notes": {},
    }
    # v2 cannot size without a stop — it is the denominator of the risk math.
    stop = None
    if raw_stop is not None and str(raw_stop).strip() != "":
        try:
            stop = float(raw_stop)
        except (TypeError, ValueError):
            stop = None
    if stop is None:
        base["pass"] = False
        base["reject_reason"] = "missing protective stop"
        return base, 10

    sized = size_v2(equity, entry, stop, conviction, discretionary=discretionary)
    candidate = dict(candidate)
    candidate["qty"] = sized["qty"]
    gated = gate(account, candidate, positions, catalyst, now=now, whole_swing=True)

    rejected = sized["reject_reason"] is not None
    passed = (not rejected) and gated["pass"]
    verdict = {
        "ticker": ticker,
        "qty": sized["qty"],
        "whole_swing": True,
        "fractional": False,
        "discretionary": discretionary,
        "risk_fraction": sized["risk_fraction"],
        "dollar_risk": sized["dollar_risk"],
        "stop_price": sized["stop_price"],
        "reject_reason": sized["reject_reason"],
        "pass": passed,
        "gates_failed": gated["gates_failed"],
        "dire_triggers": gated["dire_triggers"],
        "earnings_check": gated["earnings_check"],
        "notes": gated["notes"],
    }
    return verdict, (0 if passed else 10)


def allowed_actions(account, positions, candidates, today_activity, *,
                    whole_swing=False, now=None):
    """Compute the legal action set per candidate BEFORE the brain decides.

    A pre-flight projection of gate()'s rules so the model can only pick
    pre-validated legal moves ("a menu, not a rulebook"), and so the prose-only
    rules (once-per-ticker-per-day, no-re-buy-after-stop-out) become enforced.

    Pure: the caller supplies today's broker activity. The authoritative
    post-check (gate(), Step 5.5) is unchanged — this is the pre-filter; the two
    share constants so they always agree.

    today_activity: {"traded_today": [tickers], "stopped_today": [tickers]}.
    Returns {new_entries_allowed, account_blockers, slots_remaining, candidates}.
    """
    equity = float(account.get("equity", 0) or 0)
    spendable = _spendable(account)

    ta = today_activity or {}
    traded = {(t or "").upper() for t in (ta.get("traded_today") or [])}
    stopped = {(t or "").upper() for t in (ta.get("stopped_today") or [])}

    held = {
        (p.get("ticker") or "").upper()
        for p in positions
        if float(p.get("market_value", 0) or 0) != 0
    }

    open_cap = MAX_OPEN_POSITIONS_V2 if whole_swing else MAX_OPEN_POSITIONS
    slots_remaining = max(0, open_cap - len(held))

    # --- account-level blockers (any one blocks every candidate) -------------
    account_blockers = []

    day_start = account.get("day_start_equity")
    try:
        ds = None if day_start is None else float(day_start)
    except (TypeError, ValueError):
        ds = None
    # Epsilon biases toward tripping — a missed halt is the dangerous direction.
    # Latching: use session_low_equity when available so a mid-session breach
    # stays tripped even if equity later recovers. Falls back to current equity.
    if ds is not None and (_trip_equity(account, equity) - ds) <= -DAILY_LOSS_HALT_PCT * ds + 1e-9:
        account_blockers.append("daily_loss_halt")

    last_equity = account.get("last_equity")
    try:
        le = None if last_equity is None else float(last_equity)
    except (TypeError, ValueError):
        le = None
    if le is not None and le > 0 and (le - equity) >= DRAWDOWN_PCT * le - 1e-9:
        account_blockers.append("drawdown")

    if slots_remaining <= 0:
        account_blockers.append("no_open_slots")

    new_entries_allowed = not account_blockers

    pos_cap = _position_cap(equity, small_account=False)
    cash_floor = CASH_RESERVE_PCT * equity

    out = {}
    for c in candidates:
        ticker = (c.get("ticker") or "").upper()
        if not ticker:
            continue
        try:
            price = float(c.get("price", 0) or 0)
        except (TypeError, ValueError):
            price = 0.0

        blockers = []
        if ticker in held:
            blockers.append("already_held")
        if ticker in traded:
            blockers.append("traded_today")
        if ticker in stopped:
            blockers.append("stopped_today")

        # Cap-implied whole-share ceiling (informational; size_v2 still binds).
        if price > 0:
            cap_qty = int(pos_cap // price)
            cash_qty = int(max(0.0, spendable - cash_floor) // price)
            max_qty = max(0, min(cap_qty, cash_qty))
        else:
            max_qty = 0
        if max_qty < 1:
            blockers.append("would_breach_cap")

        buyable = new_entries_allowed and not blockers
        out[ticker] = {
            "actions": ["buy"] if buyable else ["hold"],
            "max_qty": max_qty if buyable else 0,
            "blockers": blockers,
        }

    return {
        "new_entries_allowed": new_entries_allowed,
        "account_blockers": account_blockers,
        "slots_remaining": slots_remaining,
        "candidates": out,
    }


def _load_catalyst_file(path):
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def main():
    catalyst_override = None
    args = sys.argv[1:]
    mode = "actions" if "actions" in args else "decide"
    if "--catalyst-file" in args:
        i = args.index("--catalyst-file")
        if i + 1 < len(args):
            catalyst_override = _load_catalyst_file(args[i + 1])

    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        print("risk: bad stdin JSON", file=sys.stderr)
        sys.exit(3)

    # The payload is hand-assembled by an LLM in the HEARTBEAT prompt; a stray
    # array/scalar is valid JSON but not a usable payload. Treat it as a parse
    # failure (exit 3) rather than crashing with an undefined exit code.
    if not isinstance(payload, dict):
        print("risk: stdin JSON must be an object", file=sys.stderr)
        sys.exit(3)

    # Pre-flight legality gate: which candidates may the brain even consider?
    # Advisory (always exit 0 on a parsed payload) — gate() is the authoritative
    # post-check. Honors SHARK_WHOLE_SWING_V2 like the decide path.
    if mode == "actions":
        whole_swing = os.environ.get("SHARK_WHOLE_SWING_V2") == "1"
        result = allowed_actions(
            payload.get("account") or {},
            payload.get("positions") or [],
            payload.get("candidates") or [],
            payload.get("today_activity") or {},
            whole_swing=whole_swing,
            now=datetime.now(timezone.utc),
        )
        print(json.dumps(result))
        sys.exit(0)

    if catalyst_override is not None:
        payload["catalyst"] = catalyst_override

    verdict, code = _decide(payload, now=datetime.now(timezone.utc))
    print(json.dumps(verdict))
    sys.exit(code)


if __name__ == "__main__":
    main()
