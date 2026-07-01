#!/usr/bin/env python3
"""
trade-manager — deterministic exit / position-management decision core.
Part of the Shark Starter Kit.

This module is PURE: no network, no clock-of-record, no broker calls. It maps the
brain's sized buy onto a broker order plan (plan_entry) and advances a per-position
state machine each heartbeat (audit). The wrappers (manage.sh / audit.sh) hold the
only network touch and execute what these functions return.

Phase 1 scope (this file): plan_entry -> one full-size GTC bracket (stop + target);
audit -> ENTERED/CLOSED with missing-stop repair and realized R-multiple logging.
Phases 2-4 (breakeven / trailing / pyramiding) extend audit(); not implemented yet.
"""
import json
import os
import sys

# ---- constants (single source of truth; consistent with the `risk` skill) ----
TARGET_R_MULTIPLE = 2.0      # take-profit at +2R  (matches risk.MIN_RR = 2.0)
ENTRY_TYPE        = "market" # Phase 1 entry; protective legs rest GTC
TIF               = "gtc"
ROUND_NUMBER_EPS  = 0.03     # nudge stops/targets off .00/.50 stop-cluster magnets

# --- Small-account intraday windows (minutes-to-close; clock is the wrapper's) ---
NO_NEW_ENTRY_MIN = 30   # no new fractional entries at/after 3:30pm ET
FORCE_FLAT_MIN   = 15   # force-flat begins at/after 3:45pm ET

# --- Phase 3 trailing ratchet (default off; the backtest picks the method) ---
TRAIL_PCT           = 0.06   # percent-trail width
CHANDELIER_ATR_MULT = 3.0    # chandelier: HH(N) - K*ATR(N)
CHANDELIER_LOOKBACK = 22


def _percent_trail(high_water):
    if high_water is None:
        return None
    return round(high_water * (1.0 - TRAIL_PCT), 2)


def _atr(bars, period):
    """True-range mean over `period` (bars chronological, oldest first)."""
    if len(bars) < period + 1:
        return None
    trs = []
    for i in range(1, len(bars)):
        h, l, pc = bars[i]["high"], bars[i]["low"], bars[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs[-period:]) / period


def _chandelier_trail(bars, lookback=CHANDELIER_LOOKBACK, mult=CHANDELIER_ATR_MULT):
    if not bars or len(bars) < lookback + 1:
        return None
    hh = max(b["high"] for b in bars[-lookback:])
    atr = _atr(bars, lookback)
    if atr is None:
        return None
    return round(hh - mult * atr, 2)


def intraday_window(minutes_to_close):
    """Pure schedule decision for the small-account fractional sleeve.

    Returns {new_entries_allowed, force_flat}. The hard zero-by-3:55 stop is
    enforced by the broker after force_flat fires (verify qty==0)."""
    m = minutes_to_close
    return {
        "new_entries_allowed": m > NO_NEW_ENTRY_MIN,
        "force_flat": m <= FORCE_FLAT_MIN,
    }


def _dodge_round(price):
    """Nudge a price off the .00 / .50 round-number magnets (deterministic).
    Take-profit sells a few cents early; stops sit a few cents off the cluster."""
    cents = round(price * 100) % 100
    if cents in (0, 50):
        return round(price - ROUND_NUMBER_EPS, 2)
    return round(price, 2)


def _fmt_qty(qty):
    """Trim a fractional qty to a clean string (0.240000 -> '0.24')."""
    return ("%.6f" % qty).rstrip("0").rstrip(".")


def plan_entry(ticker, entry, stop, qty, phase=1, fractional=False):
    """Return the broker order plan for a sized buy.

    Returns {target, orders, fractional, reject_reason}.
    Whole (default) -> one full-size GTC bracket (Phase 1; tranching is Phase 2).
    fractional=True (SHARK_FRACTIONAL) -> market-DAY buy + DAY stop ONLY. A
    fractional position can rest only one exit (the stop reserves the shares;
    a co-resting DAY limit is rejected), and fractional has no OCO/bracket. The
    take-profit is managed by audit() each fire; shark-force-flat closes the
    position before the close.
    """
    reject = None
    if entry is None or stop is None or entry <= 0 or stop <= 0:
        reject = "nonpositive_price"
    elif stop >= entry:
        reject = "stop_not_below_entry"
    elif qty is None or qty <= 0 or (not fractional and int(qty) < 1):
        reject = "qty_below_one"
    if reject:
        return {"target": None, "orders": [], "fractional": fractional,
                "reject_reason": reject}

    one_r = entry - stop
    target = _dodge_round(round(entry + TARGET_R_MULTIPLE * one_r, 2))
    stop_emit = _dodge_round(stop)

    if fractional:
        q = _fmt_qty(qty)
        # Fractional has no OCO/bracket and can rest only ONE exit at a time:
        # the DAY stop reserves all the shares (qty_available -> 0), so a
        # co-resting DAY limit take-profit is rejected (verified live 2026-06-08,
        # MRVL). So market-DAY buy + DAY stop only; the take-profit is NOT rested
        # — audit() manages it each fire and shark-force-flat closes the position
        # before the close. `target` is still returned for that management.
        orders = [
            {"symbol": ticker, "qty": q, "side": "buy", "type": "market",
             "time_in_force": "day"},
            {"symbol": ticker, "qty": q, "side": "sell", "type": "stop",
             "stop_price": str(stop_emit), "time_in_force": "day"},
        ]
        return {"target": target, "orders": orders, "fractional": True,
                "reject_reason": None}

    order = {
        "symbol": ticker,
        "qty": str(int(qty)),
        "side": "buy",
        "type": ENTRY_TYPE,
        "time_in_force": TIF,
        "order_class": "bracket",
        "take_profit": {"limit_price": str(target)},
        "stop_loss": {"stop_price": str(stop_emit)},
    }
    return {"target": target, "orders": [order], "fractional": False,
            "reject_reason": None}


def audit(snapshot):
    """Advance the Phase 1 state machine for one position.

    snapshot keys: entry, qty, position_qty, stop_price, stop_order, tp_order,
                   last_filled_exit, last_price, symbol(optional).
    Returns {state, actions: [...], realized: [...]}.
    Phase 1 (HOLD when protected / repair a missing stop / log realized P&L on close)
    + Phase 2 (scale half at +1R, runner stop->breakeven, re-place +2R target) — both
    LIVE. Phase 3 trailing ratchet is present but default-OFF (`trail_method`="none")
    and PARKED pending the backtest; it never fires unless the caller sets trail_method.
    """
    entry = snapshot.get("entry")
    pos_qty = snapshot.get("position_qty", 0)

    # Force-flat (small-account, before close): cancel resting exits so the
    # close-out can't collide with a stale order, then market-sell, then verify.
    if snapshot.get("fractional") and snapshot.get("force_flat") and pos_qty != 0:
        actions = []
        for key in ("stop_order", "tp_order"):
            if snapshot.get(key):
                actions.append({"op": "cancel", "order": key, "id": snapshot[key]})
        actions.append({"op": "sell", "qty": pos_qty, "reason": "force_flat",
                        "type": "market", "tif": "day"})
        actions.append({"op": "verify_flat", "symbol": snapshot.get("symbol")})
        return {"state": "FLATTENING", "actions": actions, "realized": []}

    # CLOSED: the broker filled an exit between fires.
    if pos_qty == 0:
        realized = []
        ex = snapshot.get("last_filled_exit")
        if ex and entry:
            price = ex["price"]
            q = ex.get("qty", snapshot.get("qty", 0))
            pnl = round((price - entry) * q, 2)
            stop_price = snapshot.get("stop_price")
            r_multiple = None
            if stop_price and (entry - stop_price) != 0:
                r_multiple = round((price - entry) / (entry - stop_price), 2)
            kind = "target_hit" if ex.get("role") == "take_profit" else \
                   "stop_hit" if ex.get("role") == "stop_loss" else "closed"
            realized.append({
                "symbol": snapshot.get("symbol"),
                "exit_price": price, "qty": q, "pnl": pnl,
                "r_multiple": r_multiple, "kind": kind,
            })
        # Reconcile (fractional only): the two DAY exits are independent (not an
        # OCO bracket), so a filled leg leaves its sibling resting -> cancel it.
        # Whole-share uses a real bracket; the broker auto-cancels the sibling.
        actions = []
        if snapshot.get("fractional"):
            for key in ("stop_order", "tp_order"):
                if snapshot.get(key):
                    actions.append({"op": "cancel", "order": key, "id": snapshot[key]})
        return {"state": "CLOSED", "actions": actions, "realized": realized}

    # OPEN (fractional): managed exits — the take-profit isn't rested and DAY
    # stops expire at close, so each fire: take profit if hit, else re-place a
    # missing/expired stop, else hold.
    if snapshot.get("fractional"):
        last_price = snapshot.get("last_price")
        target = snapshot.get("target")
        if last_price is not None and target is not None and last_price >= target:
            return {"state": "ENTERED",
                    "actions": [{"op": "sell", "qty": pos_qty, "reason": "target_hit"}],
                    "realized": []}
        if not snapshot.get("stop_order"):
            return {"state": "ENTERED",
                    "actions": [{"op": "place_stop", "stop_price": snapshot.get("stop_price"),
                                 "qty": pos_qty, "tif": "day"}],
                    "realized": []}
        return {"state": "ENTERED", "actions": [{"op": "noop"}], "realized": []}

    # OPEN (whole): Phase 2 scale-out + breakeven, else repair a missing stop, else hold.
    entry = snapshot.get("entry")
    stop_price = snapshot.get("stop_price")
    last_price = snapshot.get("last_price")
    one_r = (entry - stop_price) if (entry and stop_price and entry > stop_price) else None
    # "Already scaled / at breakeven" = the stop has been lifted to ~entry. A robust
    # signal from CURRENT broker state (the original below-entry stop is far below this),
    # so the agent need not track the original entry qty (which it can't reliably supply).
    # The 0.05 tolerance covers the round-number dodge on the breakeven stop.
    scaled = (entry is not None and stop_price is not None and stop_price >= entry - 0.05)

    # Scale-out / breakeven fires only with a price signal, a valid 1R, an un-scaled
    # position, and an EXISTING stop leg (no stop -> repair path below).
    if (last_price is not None and one_r is not None and not scaled
            and snapshot.get("stop_order")):
        if last_price >= entry + one_r:                  # reached +1R
            be = _dodge_round(entry)                      # breakeven, nudged off magnets
            so, tpo = snapshot.get("stop_order"), snapshot.get("tp_order")
            stop_id = so.get("id") if isinstance(so, dict) else so
            tp_id = tpo.get("id") if isinstance(tpo, dict) else tpo
            if pos_qty >= 2:
                sell_qty = pos_qty // 2                   # sell the floor half
                runner = pos_qty - sell_qty               # runner keeps the rest
                _trailing = snapshot.get("trail_method", "none") != "none"
                target = None if _trailing else _dodge_round(
                    round(entry + TARGET_R_MULTIPLE * one_r, 2))
                # CANCEL-AND-REBUILD: per-leg OCO qty replacement is rejected by Alpaca
                # (spike 2026-06-17), so the executor cancels both legs, sells the half,
                # and re-places a fresh OCO (breakeven stop + 2R target) on the runner.
                # Re-placing the target also restores it if the book had gone stop-only.
                return {"state": "ENTERED", "realized": [], "actions": [
                    {"op": "scale_out", "sell_qty": sell_qty, "runner_qty": runner,
                     "breakeven": be, "target": target,
                     "cancel_ids": [i for i in (stop_id, tp_id) if i]},
                ]}
            # single share: can't halve -> lift the stop to breakeven via a PRICE-ONLY
            # move (qty change is rejected on advanced orders; price change is accepted).
            return {"state": "ENTERED", "realized": [], "actions": [
                {"op": "move_stop_breakeven", "id": stop_id, "stop_price": be},
            ]}

    # Phase 3 — trailing ratchet on the scaled runner (replaces the fixed +2R target).
    # arm_after_2r: don't trail until the peak clears +2R, then lock +2R as a floor —
    # banks the cap's certainty and only ever gives back ABOVE +2R.
    trail_method = snapshot.get("trail_method", "none")
    if scaled and trail_method != "none" and snapshot.get("stop_order"):
        hw = snapshot.get("high_water")
        floor = None
        armed = True
        if snapshot.get("arm_after_2r", False):
            orig_one_r = snapshot.get("one_r")    # original 1R (entry - original stop)
            if hw is None or not orig_one_r:
                armed = False                     # can't arm without the peak + 1R
            else:
                floor = round(entry + TARGET_R_MULTIPLE * orig_one_r, 2)
                armed = hw >= floor               # arm only once the peak hits +2R
        if armed:
            if trail_method == "percent":
                trail = _percent_trail(hw)
            elif trail_method == "chandelier":
                trail = _chandelier_trail(snapshot.get("recent_bars") or [])
            else:
                trail = None
            if trail is not None and floor is not None:
                trail = max(trail, floor)         # never below the locked +2R floor
            if trail is not None and trail > stop_price:      # ratchet UP only (monotonic)
                so = snapshot.get("stop_order")
                stop_id = so.get("id") if isinstance(so, dict) else so
                return {"state": "ENTERED", "realized": [],
                        "actions": [{"op": "move_stop", "id": stop_id,
                                     "stop_price": _dodge_round(trail)}]}

    # repair a missing protective stop, else hold.
    actions = []
    if not snapshot.get("stop_order"):
        actions.append({
            "op": "place_stop",
            "stop_price": snapshot.get("stop_price"),
            "qty": pos_qty,
        })
    if not actions:
        actions.append({"op": "noop"})
    return {"state": "ENTERED", "actions": actions, "realized": []}


# ---------------------------- CLI ----------------------------

def _main(argv):
    if len(argv) < 2 or argv[1] not in ("plan_entry", "audit"):
        print("usage: trade_manager.py {plan_entry|audit}  (JSON on stdin)", file=sys.stderr)
        return 2
    try:
        data = json.loads(sys.stdin.read())
    except Exception as e:
        print(f"bad stdin JSON: {e}", file=sys.stderr)
        return 3

    if argv[1] == "plan_entry":
        frac = data.get("fractional", os.environ.get("SHARK_FRACTIONAL") == "1")
        out = plan_entry(data["ticker"], data["entry"], data["stop"],
                         data["qty"], data.get("phase", 1), fractional=frac)
        print(json.dumps(out))
        return 0 if out["reject_reason"] is None else 10

    out = audit(data)
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
