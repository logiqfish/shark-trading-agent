#!/usr/bin/env python3
"""
trade-manager broker layer (Phase 1) — orchestration engine.
Part of the Shark Starter Kit.

Turns a plan_entry() plan into real Alpaca paper orders. HTTP is delegated to
ExecutionAdapter (execution_adapter.py); broker.py never opens a socket directly.

SAFETY:
  * Paper-guarded: refuses any base URL without 'paper'. The kit is paper-only by
    construction (no live path).
  * Bracket-or-fallback: if Alpaca rejects the bracket, falls back to a known-good
    market buy + separate GTC stop so a position is NEVER left unprotected — and
    logs a WARN.
  * --dry-run prints intended payloads, places nothing.

Reads creds from env: ALPACA_API_KEY / ALPACA_SECRET_KEY
(aliases ALPACA_KEY_ID / ALPACA_SECRET), base ALPACA_BASE_URL (default paper).
"""
import json, os, sys, uuid
from datetime import datetime, timezone
import trade_manager as tm
from execution_adapter import LegacyAlpacaRestAdapter


def _entry_coid(ticker):
    """STABLE per-ticker-per-day idempotency key for an ENTRY.

    Unlike a per-call uuid, this is identical across heartbeat fires, so a retry of an
    entry that timed out *after* landing re-sends the SAME client_order_id — Alpaca
    rejects the duplicate (see _is_duplicate_coid) instead of opening a second position.
    Keyed by UTC date: an entry only ever happens during RTH (13:30–20:00 UTC), well
    clear of the UTC midnight boundary, so the date is stable for the whole session
    without needing a timezone database (absent on the minimal container/CR runtimes).
    Aligns with the strategy's own once-per-ticker-per-day rule."""
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"shark-enter-{(ticker or '').upper()}-{day}"


def _is_duplicate_coid(status, resp):
    """True iff the broker rejected because the client_order_id already exists — i.e.
    this exact write already landed (on a prior fire / a timed-out attempt). Treated
    as "already placed", never as a fresh reject (a fallback would double the position)."""
    if not isinstance(resp, dict):
        return False
    if resp.get("code") == 40010001:          # Alpaca: duplicate client_order_id
        return True
    msg = str(resp.get("message", "")).lower()
    return "client_order_id" in msg and ("uniq" in msg or "exist" in msg or "duplicate" in msg)


def _new_coid(prefix):
    """Per-call idempotency key for EXIT / repair writes (stop, scale-out, flatten,
    dire-liquidate). Unique per call, so a *within-call* duplicate submit is rejected
    by the broker. These paths are not retried fire-to-fire the way an entry is, and
    are independently guarded (held-qty re-reads + the audit loop), so a stable
    cross-fire key isn't needed here. ENTRIES use _entry_coid() instead — a stable
    per-ticker-per-day key that survives a heartbeat retry (see its docstring)."""
    return f"shark-{prefix}-{uuid.uuid4().hex[:16]}"


def _submit(adapter, order, coid):
    """Submit an order with its idempotency key stamped on. Never overwrites an
    explicit client_order_id the caller already set in the body."""
    o = dict(order)
    o.setdefault("client_order_id", coid)
    return adapter.submit_order(o)


def reconcile(coid, adapter=None):
    """Learn the TRUE broker state of a write after an ambiguous / no-answer response.

    Returns the broker's order dict iff it holds an order with this client_order_id,
    else None (not found, or the lookup itself failed). Callers use this INSTEAD of a
    blind retry — re-sending a write that doubles a real-money position is exactly the
    failure the seatbelt exists to prevent."""
    if adapter is None:
        adapter = _default_adapter()
    st, body = adapter.get_order_by_client_id(coid)
    if st and 200 <= st < 300 and isinstance(body, dict) and body.get("id"):
        return body
    return None


def _creds():
    key = os.environ.get("ALPACA_API_KEY") or os.environ.get("ALPACA_KEY_ID")
    sec = os.environ.get("ALPACA_SECRET_KEY") or os.environ.get("ALPACA_SECRET")
    base = os.environ.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets").rstrip("/")
    return key, sec, base


def _default_adapter():
    key, sec, base = _creds()
    return LegacyAlpacaRestAdapter(base, key, sec)


def is_fractionable(symbol, adapter):
    """True iff Alpaca lists the asset as fractionable. Conservative: any
    non-200 or missing field -> False (don't place a fractional order blindly)."""
    st, asset = adapter.get_asset(symbol)
    return bool(st and 200 <= st < 300 and asset.get("fractionable") is True)


def market_open(adapter):
    """True iff Alpaca's clock says the market is open (RTH guard for fractional
    market orders)."""
    st, clk = adapter.get_clock()
    return bool(st and 200 <= st < 300 and clk.get("is_open") is True)


def enter(ticker, qty, entry, stop, phase=1, dry=False, fractional=None, adapter=None,
          coid=None):
    """Place the Phase 1 protective+profit bracket; fall back to market+stop on reject.

    Every order placed carries a client_order_id derived from `coid` (auto-generated
    when omitted). On an AMBIGUOUS bracket response (no broker answer), reconcile by
    that id rather than falling back — a fallback market buy after a bracket that
    actually landed would double the position.

    Paper-only by construction: the paper-base guard below refuses any non-paper base
    URL, and the kit ships no live path. (The full system's Cloud Run entry lock is
    intentionally omitted here — with no such service to ship, gating entries on it
    would fail closed and the bot could never trade.)"""
    if fractional is None:
        fractional = os.environ.get("SHARK_FRACTIONAL") == "1"
    coid_base = coid or _entry_coid(ticker)
    plan = tm.plan_entry(ticker, float(entry), float(stop), float(qty), int(phase),
                         fractional=fractional)
    if plan["reject_reason"]:
        return {"ok": False, "stage": "plan", "reason": plan["reject_reason"]}

    _using_default = adapter is None
    if _using_default:
        adapter = _default_adapter()

    # Small-account fractional guards (run in dry mode too via injected adapter):
    if fractional:
        if not is_fractionable(ticker, adapter):
            return {"ok": False, "stage": "fractionable",
                    "reason": f"{ticker} is not fractionable"}
        if not market_open(adapter):
            return {"ok": False, "stage": "rth_guard",
                    "reason": "fractional market orders are RTH-only"}

    if dry:
        return {"ok": True, "stage": "dry_run", "fractional": fractional,
                "orders": plan["orders"], "target": plan["target"]}

    if _using_default:
        key, sec, _ = _creds()
        if not key or not sec:
            return {"ok": False, "stage": "creds", "reason": "ALPACA_API_KEY/SECRET not set"}
    if "paper" not in adapter.base:
        return {"ok": False, "stage": "guard", "reason": f"refusing non-paper base: {adapter.base}"}

    if fractional:
        ids = {}
        for role, order in zip(("buy", "stop_order"), plan["orders"]):
            st, resp = _submit(adapter, order, f"{coid_base}-{role}")
            if not (st and 200 <= st < 300):
                return {"ok": False, "stage": f"fractional_{role}",
                        "reason": f"HTTP {st}", "resp": resp, "placed": ids}
            ids[role] = resp.get("id")
        return {"ok": True, "stage": "fractional", "buy_id": ids.get("buy"),
                "stop_id": ids.get("stop_order"), "tp_id": None,
                "target": plan["target"],
                "note": "stop-only (fractional cannot co-rest a DAY limit); "
                        "take-profit managed by audit() + force-flat before close"}

    return _enter_whole(ticker, qty, plan, adapter, coid_base)


def flatten(symbol, exit_order_ids, adapter):
    """Force-flat a fractional position before close: cancel resting exits,
    market-DAY sell the whole position, then VERIFY qty==0.
    On any failure, return alert=True so the caller surfaces it and blocks new entries."""
    if "paper" not in adapter.base:
        return {"ok": False, "stage": "guard", "alert": True,
                "verified_flat": False, "reason": f"refusing non-paper base: {adapter.base}"}

    for oid in exit_order_ids or []:
        adapter.cancel_order(oid)

    st_p, pos = adapter.get_position(symbol)
    held = float(pos.get("qty", 0) or 0) if st_p and 200 <= st_p < 300 else 0.0
    if held > 0:
        sell = {"symbol": symbol, "qty": ("%.6f" % held).rstrip("0").rstrip("."),
                "side": "sell", "type": "market", "time_in_force": "day"}
        st_s, _ = _submit(adapter, sell, _new_coid("flatten"))
        if not (st_s and 200 <= st_s < 300):
            return {"ok": False, "stage": "sell", "alert": True,
                    "verified_flat": False, "reason": f"sell HTTP {st_s}"}

    st_v, pos2 = adapter.get_position(symbol)
    remaining = float(pos2.get("qty", 0) or 0) if st_v and 200 <= st_v < 300 else 0.0
    flat = remaining == 0.0
    return {"ok": flat, "stage": "flatten", "verified_flat": flat,
            "alert": not flat, "remaining_qty": remaining}


def scale_out(symbol, sell_qty, runner_qty, breakeven_stop, target_price, cancel_ids,
              adapter=None, dry=False):
    """Phase 2 scale-out executor — CANCEL-AND-REBUILD (per-leg OCO qty replace is 422)."""
    if adapter is None:
        adapter = _default_adapter()

    if dry:
        return {"ok": True, "stage": "dry_run", "symbol": symbol,
                "plan": {
                    "cancel_ids": cancel_ids,
                    "sell": {"qty": sell_qty, "type": "market", "tif": "day"},
                    "reprotect": {"stop": breakeven_stop, "target": target_price,
                                  "qty": runner_qty}}}

    if "paper" not in adapter.base:
        return {"ok": False, "stage": "guard", "alert": True,
                "reason": f"refusing non-paper base: {adapter.base}"}

    for oid in cancel_ids or []:
        adapter.cancel_order(oid)

    so_base = _new_coid("scaleout")
    sts, sl = _submit(adapter,
        {"symbol": symbol, "qty": str(int(sell_qty)), "side": "sell",
         "type": "market", "time_in_force": "day"}, f"{so_base}-sell")
    if not (sts and 200 <= sts < 300):
        return {"ok": False, "stage": "sell", "alert": True,
                "reason": f"HTTP {sts}", "resp": sl, "naked": True}

    oco = {"symbol": symbol, "qty": str(int(runner_qty)), "side": "sell",
           "type": "limit", "limit_price": str(target_price), "time_in_force": "gtc",
           "order_class": "oco",
           "take_profit": {"limit_price": str(target_price)},
           "stop_loss": {"stop_price": str(breakeven_stop)}}
    sto, oresp = _submit(adapter, oco, f"{so_base}-oco")
    if not (sto and 200 <= sto < 300):
        return {"ok": False, "stage": "reprotect", "alert": True,
                "reason": f"HTTP {sto}", "resp": oresp, "naked": True,
                "sell_id": sl.get("id")}

    return {"ok": True, "stage": "scale_out", "symbol": symbol,
            "sold_qty": sell_qty, "runner_qty": runner_qty,
            "breakeven_stop": breakeven_stop, "target_price": target_price,
            "sell_id": sl.get("id"), "oco_id": oresp.get("id")}


def place_stop(symbol, qty, stop_price, adapter=None, dry=False):
    """Place a protective GTC sell stop (Phase-1 repair of a vanished stop leg)."""
    if adapter is None:
        adapter = _default_adapter()
    if dry:
        return {"ok": True, "stage": "dry_run",
                "plan": {"stop": symbol, "qty": qty, "stop_price": stop_price}}
    if "paper" not in adapter.base:
        return {"ok": False, "stage": "guard", "alert": True, "reason": f"non-paper: {adapter.base}"}
    st, resp = _submit(adapter,
        {"symbol": symbol, "qty": str(int(qty)), "side": "sell", "type": "stop",
         "stop_price": str(stop_price), "time_in_force": "gtc"}, _new_coid("stop"))
    if not (st and 200 <= st < 300):
        return {"ok": False, "stage": "place_stop", "alert": True,
                "reason": f"HTTP {st}", "resp": resp}
    return {"ok": True, "stage": "place_stop", "stop_id": resp.get("id")}


def move_stop_breakeven(stop_id, breakeven, adapter=None, dry=False):
    """Lift a resting stop to breakeven via a PRICE-ONLY replace.
    (spike-proven: qty changes are rejected on advanced orders, but stop_price changes are accepted)."""
    if adapter is None:
        adapter = _default_adapter()
    if dry:
        return {"ok": True, "stage": "dry_run",
                "plan": {"patch": stop_id, "stop_price": breakeven}}
    if "paper" not in adapter.base:
        return {"ok": False, "stage": "guard", "alert": True, "reason": f"non-paper: {adapter.base}"}
    st, resp = adapter.replace_order(stop_id, {"stop_price": str(breakeven)})
    if not (st and 200 <= st < 300):
        return {"ok": False, "stage": "move_stop", "alert": True,
                "reason": f"HTTP {st}", "resp": resp}
    return {"ok": True, "stage": "move_stop_breakeven", "stop_id": resp.get("id")}


def manage(snapshot, adapter=None, dry=False):
    """Dispatcher: run trade_manager.audit() and EXECUTE each action via the adapter."""
    if adapter is None:
        adapter = _default_adapter()
    out = tm.audit(snapshot)
    sym = snapshot.get("symbol")
    results, alerts = [], []
    for a in out.get("actions", []):
        op = a.get("op")
        if op == "noop":
            continue
        if op == "scale_out":
            r = scale_out(sym, a["sell_qty"], a["runner_qty"], a["breakeven"],
                          a["target"], a["cancel_ids"], adapter=adapter, dry=dry)
        elif op == "move_stop_breakeven":
            r = move_stop_breakeven(a["id"], a["stop_price"], adapter=adapter, dry=dry)
        elif op == "place_stop":
            r = place_stop(sym, a["qty"], a["stop_price"], adapter=adapter, dry=dry)
        else:
            r = {"ok": False, "stage": "unknown_op", "op": op, "alert": True}
        results.append({"op": op, "result": r})
        if r.get("alert"):
            alerts.append({"op": op, "reason": r.get("reason")})
    return {"state": out.get("state"), "realized": out.get("realized", []),
            "results": results, "alerts": alerts}


# Order statuses that mean a leg is gone / not protecting (everything else —
# held, new, accepted, pending_*, partially_filled, calculated — counts as resting).
_DEAD_ORDER_STATUS = {"canceled", "cancelled", "filled", "expired", "rejected",
                      "replaced", "done_for_day"}


def _sell_legs(orders):
    """Yield every resting sell leg (top-level orders + nested OCO/bracket legs).
    Mirrors the 2026-06-22 nested=true flatten so the protective stop leg is visible."""
    for o in orders if isinstance(orders, list) else []:
        for leg in [o] + (o.get("legs") or []):
            if leg.get("side") == "sell":
                yield leg


def _find_stop_leg(orders):
    """Return (stop_id, stop_price, stop_qty) of the first resting sell-stop leg,
    or (None, None, None). The authoritative 'is this position protected?' read.
    A leg in a dead/terminal status (canceled/filled/expired/...) does NOT count."""
    for leg in _sell_legs(orders):
        if (leg.get("status") or "").lower() in _DEAD_ORDER_STATUS:
            continue
        if "stop" in (leg.get("type") or ""):
            try:
                price = float(leg.get("stop_price"))
            except (TypeError, ValueError):
                price = None
            try:
                q = leg.get("qty")
                qty = int(float(q)) if q is not None else None
            except (TypeError, ValueError):
                qty = None
            return leg.get("id"), price, qty
    return None, None, None


def _find_tp_id(orders):
    """Return the id of the first resting sell-limit (take-profit) leg, or None.
    A leg in a dead/terminal status does NOT count."""
    for leg in _sell_legs(orders):
        if (leg.get("status") or "").lower() in _DEAD_ORDER_STATUS:
            continue
        if "limit" in (leg.get("type") or ""):
            return leg.get("id")
    return None


def _held_qty(symbol, adapter):
    """Whole-share qty currently held, 0 if no position / unreadable."""
    st, pos = adapter.get_position(symbol)
    if not (st and 200 <= st < 300) or not isinstance(pos, dict):
        return 0
    try:
        return int(float(pos.get("qty", 0) or 0))
    except (TypeError, ValueError):
        return 0


def is_protected(symbol, adapter=None):
    """Authoritative dire-gate read: does a resting protective stop exist?
    Any resting sell-stop leg => protected. A FAILED orders read => protected
    (fail-safe): a transient API error must never read as 'naked' and re-enable a
    false liquidation. Only a SUCCESSFUL read with no stop leg yields protected=False."""
    if adapter is None:
        adapter = _default_adapter()
    position_qty = _held_qty(symbol, adapter)
    # status="all" so a protective stop resting in Alpaca status "held" is visible
    # (a status=open query excludes the filled bracket parent AND the held stop leg).
    ost, orders = adapter.get_open_orders(symbol, status="all")
    if not (ost and 200 <= ost < 300) or not isinstance(orders, list):
        return {"protected": True, "reason": "orders_read_failed",
                "stop_id": None, "stop_price": None, "stop_qty": None,
                "position_qty": position_qty}
    stop_id, stop_price, stop_qty = _find_stop_leg(orders)
    return {"protected": stop_id is not None, "reason": None, "stop_id": stop_id,
            "stop_price": stop_price, "stop_qty": stop_qty, "position_qty": position_qty}


def dire_liquidate(symbol, qty=None, adapter=None, dry=False):
    """Dire-gate trigger-2 guarded liquidation. REFUSES to sell when a protective
    stop already rests (prevents the 2026-06-22 false self-liquidation). The passed
    QTY is accepted for HEARTBEAT-call compatibility but IGNORED — the sell qty is the
    live held qty (like flatten()). Paper-guarded."""
    if adapter is None:
        adapter = _default_adapter()
    if "paper" not in adapter.base:
        return {"ok": False, "stage": "guard", "alert": True,
                "reason": f"refusing non-paper base: {adapter.base}"}

    prot = is_protected(symbol, adapter)
    if prot["protected"]:
        print(f"BLOCKED — {symbol} protected by resting stop @ "
              f"{prot.get('stop_price')}; holding", file=sys.stderr)
        return {"ok": False, "stage": "blocked_protected", "alert": True,
                "holding": True, "symbol": symbol, "reason": prot.get("reason"),
                "stop_id": prot.get("stop_id"), "stop_price": prot.get("stop_price"),
                "stop_qty": prot.get("stop_qty"), "position_qty": prot.get("position_qty")}

    held = _held_qty(symbol, adapter)
    if held <= 0:
        return {"ok": True, "stage": "already_flat", "symbol": symbol, "sold_qty": 0}
    if dry:
        return {"ok": True, "stage": "dry_run", "symbol": symbol,
                "plan": {"sell": held, "type": "market", "tif": "day"}}
    st, resp = _submit(adapter,
        {"symbol": symbol, "qty": str(held), "side": "sell",
         "type": "market", "time_in_force": "day"}, _new_coid("direliq"))
    if not (st and 200 <= st < 300):
        return {"ok": False, "stage": "sell", "alert": True, "symbol": symbol,
                "reason": f"sell HTTP {st}", "resp": resp}
    remaining = _held_qty(symbol, adapter)
    return {"ok": True, "stage": "liquidated", "symbol": symbol, "sold_qty": held,
            "verified_flat": remaining == 0,
            "sell_id": resp.get("id") if isinstance(resp, dict) else None}


def manage_position(symbol, adapter=None, dry=False):
    """Gather a position's snapshot from Alpaca (entry, qty, last price, resting stop +
    target legs) and run manage() on it. One call per open position from the HEARTBEAT."""
    if adapter is None:
        adapter = _default_adapter()

    pst, pos = adapter.get_position(symbol)
    if not (pst and 200 <= pst < 300) or not isinstance(pos, dict):
        return {"ok": False, "stage": "no_position", "symbol": symbol}
    try:
        entry = float(pos.get("avg_entry_price"))
        qty = int(float(pos.get("qty", 0)))
        last = float(pos.get("current_price"))
    except (TypeError, ValueError):
        return {"ok": False, "stage": "bad_position_data", "symbol": symbol}

    # status="all" so a stop leg resting in Alpaca status "held" is visible — a
    # status=open read misses it and would place a DUPLICATE stop (2026-06-22 bug,
    # second path). _find_stop_leg/_find_tp_id ignore dead-status legs.
    _, orders = adapter.get_open_orders(symbol, status="all")
    stop_id, stop_price, _stop_qty = _find_stop_leg(orders)
    tp_id = _find_tp_id(orders)

    snap = {"symbol": symbol, "entry": entry, "qty": qty, "position_qty": qty,
            "stop_price": stop_price, "last_price": last,
            "stop_order": {"id": stop_id} if stop_id else None,
            "tp_order": {"id": tp_id} if tp_id else None, "last_filled_exit": None}
    return manage(snap, adapter=adapter, dry=dry)


def _enter_whole(ticker, qty, plan, adapter, coid_base):
    """Whole-share path: one GTC bracket; fall back to market+GTC-stop on a DEFINITIVE
    reject. On an AMBIGUOUS response (no answer) reconcile by client_order_id — never
    fall back, or a market buy could double a bracket that actually landed."""
    payload = plan["orders"][0]
    st, resp = _submit(adapter, payload, coid_base)
    if st and 200 <= st < 300:
        return {"ok": True, "stage": "bracket", "order_id": resp.get("id"),
                "target": plan["target"], "stop": payload["stop_loss"]["stop_price"]}

    # --- The bracket may ALREADY exist: either no answer reached us (timed out after
    # landing), or the broker rejected this client_order_id as a DUPLICATE (a prior
    # fire's bracket is live). In BOTH cases, reconcile by the idempotency key before
    # doing anything that could open a second position. NEVER blind-fall-back here. ---
    duplicate = _is_duplicate_coid(st, resp)
    if st is None or duplicate:
        found = reconcile(coid_base, adapter)
        if found:
            print(f"WARN entry for {ticker} reconciled — bracket already live "
                  f"({found.get('id')}); not re-placing", file=sys.stderr)
            return {"ok": True, "stage": "bracket", "order_id": found.get("id"),
                    "target": plan["target"], "stop": payload["stop_loss"]["stop_price"],
                    "reconciled": True}
        if duplicate:
            # Broker says this coid exists but we can't fetch it -> a position is
            # almost certainly live. Placing a fallback buy would double it.
            print(f"WARN entry for {ticker}: broker reports duplicate client_order_id "
                  f"{coid_base} but order is unreadable — placed nothing further",
                  file=sys.stderr)
            return {"ok": False, "stage": "duplicate_unresolved", "alert": True,
                    "reason": "broker rejected the entry as a duplicate client_order_id "
                              "(a prior bracket is live) but the order could not be read "
                              "— placed nothing further (no blind retry)",
                    "client_order_id": coid_base, "resp": resp}
        # st is None and nothing found: we could NOT confirm whether the bracket landed.
        print(f"WARN entry for {ticker}: no response received and no order found for "
              f"client_order_id {coid_base} — could not confirm; placed nothing further",
              file=sys.stderr)
        return {"ok": False, "stage": "ambiguous", "alert": True,
                "reason": "entry response was not received and the order could not be "
                          "confirmed either way — placed nothing further (no blind retry)",
                "client_order_id": coid_base, "resp": resp}

    # --- FALLBACK: bracket DEFINITIVELY rejected (a real, non-duplicate status) ->
    # market buy + separate GTC stop (never naked). Safe: the bracket did not place. ---
    warn = f"bracket rejected (HTTP {st}: {str(resp.get('message',''))[:100]}); falling back to market+stop"
    print("WARN " + warn, file=sys.stderr)
    st1, buy = _submit(adapter,
        {"symbol": ticker, "qty": str(int(qty)), "side": "buy",
         "type": "market", "time_in_force": "day"}, f"{coid_base}-fbuy")
    if not (st1 and 200 <= st1 < 300):
        return {"ok": False, "stage": "fallback_buy", "reason": f"HTTP {st1}", "resp": buy}
    st2, stp = _submit(adapter,
        {"symbol": ticker, "qty": str(int(qty)), "side": "sell",
         "type": "stop", "stop_price": payload["stop_loss"]["stop_price"],
         "time_in_force": "gtc"}, f"{coid_base}-fstop")
    return {"ok": st2 and 200 <= st2 < 300, "stage": "fallback",
            "warn": warn, "buy_id": buy.get("id"), "stop_id": stp.get("id"),
            "stop": payload["stop_loss"]["stop_price"], "target_unplaced": plan["target"]}


def _main(argv):
    if len(argv) >= 2 and argv[1] == "enter":
        dry = "--dry-run" in argv
        args = [a for a in argv[2:] if not a.startswith("--")]
        if len(args) < 4:
            print("usage: broker.py enter TICKER QTY ENTRY STOP [PHASE] [--dry-run]", file=sys.stderr)
            return 2
        ticker, qty, entry, stop = args[0], args[1], args[2], args[3]
        phase = args[4] if len(args) > 4 else 1
        out = enter(ticker, qty, entry, stop, phase, dry)
        print(json.dumps(out))
        return 0 if out.get("ok") else 1
    if len(argv) >= 2 and argv[1] == "manage-position":
        dry = "--dry-run" in argv
        a = [x for x in argv[2:] if not x.startswith("--")]
        if len(a) < 1:
            print("usage: broker.py manage-position SYMBOL [--dry-run]", file=sys.stderr)
            return 2
        out = manage_position(a[0], dry=dry)
        print(json.dumps(out))
        return 1 if out.get("alerts") else 0
    if len(argv) >= 2 and argv[1] == "manage":
        dry = "--dry-run" in argv
        try:
            snap = json.loads(sys.stdin.read())
        except Exception as e:
            print(f"bad stdin JSON: {e}", file=sys.stderr)
            return 3
        out = manage(snap, dry=dry)
        print(json.dumps(out))
        return 1 if out.get("alerts") else 0
    if len(argv) >= 2 and argv[1] == "scale_out":
        dry = "--dry-run" in argv
        a = [x for x in argv[2:] if not x.startswith("--")]
        if len(a) < 6:
            print("usage: broker.py scale_out SYMBOL SELL_QTY RUNNER_QTY BREAKEVEN "
                  "TARGET CANCEL_ID [CANCEL_ID ...] [--dry-run]", file=sys.stderr)
            return 2
        symbol, sell_qty, runner_qty = a[0], int(a[1]), int(a[2])
        be, target, cancel_ids = float(a[3]), float(a[4]), a[5:]
        out = scale_out(symbol, sell_qty, runner_qty, be, target, cancel_ids, dry=dry)
        print(json.dumps(out))
        return 0 if out.get("ok") else 1
    if len(argv) >= 2 and argv[1] == "is-protected":
        a = [x for x in argv[2:] if not x.startswith("--")]
        if len(a) < 1:
            print("usage: broker.py is-protected SYMBOL", file=sys.stderr)
            return 2
        out = is_protected(a[0])
        print(json.dumps(out))
        return 0 if out.get("protected") else 1
    if len(argv) >= 2 and argv[1] == "dire-liquidate":
        dry = "--dry-run" in argv
        a = [x for x in argv[2:] if not x.startswith("--")]
        if len(a) < 1:
            print("usage: broker.py dire-liquidate SYMBOL [QTY] [--dry-run]", file=sys.stderr)
            return 2
        out = dire_liquidate(a[0], qty=(a[1] if len(a) > 1 else None), dry=dry)
        print(json.dumps(out))
        return 0 if out.get("ok") else 1
    if len(argv) >= 2 and argv[1] == "flatten":
        args = [a for a in argv[2:] if not a.startswith("--")]
        if len(args) < 1:
            print("usage: broker.py flatten SYMBOL [EXIT_ORDER_ID ...]", file=sys.stderr)
            return 2
        symbol, exit_ids = args[0], args[1:]
        key, sec, base = _creds()
        if not key or not sec:
            print(json.dumps({"ok": False, "stage": "creds", "alert": True,
                              "verified_flat": False,
                              "reason": "ALPACA_API_KEY/SECRET not set"}))
            return 1
        out = flatten(symbol, exit_ids, _default_adapter())
        print(json.dumps(out))
        return 0 if out.get("ok") else 1
    print("usage: broker.py {enter|manage-position|manage|scale_out|flatten|"
          "is-protected|dire-liquidate} ...", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
