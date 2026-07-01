#!/usr/bin/env python3
"""Discretionary ("2nd brain" gut-trade) entry orchestrator. jq-free; stdlib only.

Part of the Shark Starter Kit. Glues the kit's local skills (on-box regime veto
via local-markov, risk, trade-manager, reflection). The kit is paper-only, so
there is no kill-switch/control service (the control runner is an always-pass
no-op) and no catalyst/news/fundamentals layer (catalyst is always empty). The
bull/bear/referee debate that yields `conviction` is run by the agent's brain
(debate.sh only records verdicts) and passed in. Only the conviction floor is
advisory; every risk gate stays HARD.
"""
import json
import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_STOP_PCT = 0.95  # 5% below entry when the operator gives no stop


def _round2(x):
    return round(float(x), 2)


def _int_or(x, default=0):
    """Tolerant int coercion: a JSON string like "72.5" -> 72; junk -> default."""
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return default


def propose(payload, runners):
    """payload: {account, positions, candidate:{ticker, price, conviction, stop?}}.
    runners: {control(), markov(), catalyst(ticker)->str, risk(base)->{exit,verdict}}.
    Returns a card dict: {ok:true, ...} or {ok:false, hard_block, reason}."""
    cand = payload.get("candidate") or {}
    ticker = (cand.get("ticker") or "").upper()
    if not ticker:
        return {"ok": False, "hard_block": "input", "reason": "no ticker"}
    try:
        price = float(cand.get("price"))
    except (TypeError, ValueError):
        return {"ok": False, "hard_block": "input", "reason": "no price"}
    conviction = _int_or(cand.get("conviction"))

    # 1. Control gate — fail-closed (anything but exit 0 halts).
    if runners["control"]()["exit"] != 0:
        return {"ok": False, "hard_block": "control",
                "reason": "trading halted (kill engaged / control unreachable)"}

    # 2. Markov regime veto — exit 10 = risk-off VETO (hard); 0/20 proceed.
    if runners["markov"]()["exit"] == 10:
        return {"ok": False, "hard_block": "regime",
                "reason": "regime is risk-off (markov veto)"}

    # 3. Catalyst — advisory only; never blocks.
    catalyst = runners["catalyst"](ticker)

    # 4. Stop: operator's if given+parseable, else 5% below entry (we ALWAYS
    #    bracket; a non-numeric operator stop degrades to the default, never naked).
    default_stop = _round2(price * DEFAULT_STOP_PCT)
    raw_stop = cand.get("stop")
    if raw_stop in (None, ""):
        stop = default_stop
    else:
        try:
            stop = _round2(raw_stop)
        except (TypeError, ValueError):
            stop = default_stop

    # 5. Risk sizing + ALL gates. discretionary:true bypasses ONLY the floor.
    base = {
        "account": payload.get("account") or {},
        "candidate": {"ticker": ticker, "price": price, "conviction": conviction,
                      "stop_price": stop, "discretionary": True},
        "positions": payload.get("positions") or [],
    }
    rk = runners["risk"](base)
    verdict = rk.get("verdict") or {}
    if rk.get("exit") != 0 or not verdict.get("pass"):
        gates = verdict.get("gates_failed") or verdict.get("dire_triggers") or []
        block = gates[0] if gates else (verdict.get("reject_reason") or "risk")
        reason = (verdict.get("reject_reason")
                  or ", ".join(gates) or "risk gate failed")
        return {"ok": False, "hard_block": block, "reason": reason}

    qty = int(verdict.get("qty") or 0)
    sp = verdict.get("stop_price")
    rstop = _round2(sp if sp is not None else stop)
    target = _round2(price + 2 * (price - rstop))  # +2R
    equity = float((payload.get("account") or {}).get("equity") or 0) or 0.0
    equity_pct = round(qty * price / equity, 4) if equity else 0.0

    return {
        "ok": True, "ticker": ticker, "qty": qty, "entry": _round2(price),
        "stop": rstop, "target": target, "equity_pct": equity_pct,
        "conviction": conviction, "catalyst": catalyst, "regime": "ok",
    }


def execute(proposal, runners):
    """proposal: a `propose` card (ok:true) plus {date, thesis}.
    runners: {enter(ticker,qty,entry,stop)->{ok,stage,...}, reflect(slip)->None}.
    Places the +2R bracket via trade-manager, then writes a discretionary-tagged
    reflection slip. Returns a fill card or a failure with the broker stage."""
    if not proposal.get("ok"):
        return {"ok": False, "stage": "precheck", "reason": "proposal not ok"}

    ticker = proposal["ticker"]
    qty = int(proposal["qty"])
    entry = float(proposal["entry"])
    stop = float(proposal["stop"])

    res = runners["enter"](ticker, qty, entry, stop)
    if not res.get("ok"):
        return {"ok": False, "stage": res.get("stage", "enter"),
                "reason": res.get("reason", "broker rejected"), "broker": res}

    # Tag the journal slip so human-initiated (gut) fills are distinguishable
    # from autonomous ones (reflection.py has no `source` field, so we mark it
    # in the thesis text).
    thesis = (proposal.get("thesis") or "").strip()
    slip = {
        "ticker": ticker, "date": proposal.get("date", ""),
        "conviction": int(proposal.get("conviction") or 0),
        "entry": entry, "stop": stop,
        "thesis": f"[source:discretionary] {thesis}".strip(),
    }
    runners["reflect"](slip)  # best-effort; the bracket is already placed

    return {"ok": True, "ticker": ticker, "qty": qty, "entry": entry,
            "stop": stop, "target": proposal.get("target"),
            "source": "discretionary", "broker": res}


def _sib(*parts):
    return os.path.join(SCRIPT_DIR, "..", *parts)


def _sh(*args, stdin=None, env=None):
    return subprocess.run(list(args), input=stdin, capture_output=True, text=True, env=env)


def _real_runners():
    """Subprocess-backed siblings, resolved relative to this skill dir via the
    `../<skill>/` convention. In this kit: regime via local-markov, risk,
    trade-manager, reflection. Control + catalyst are no-ops (paper-only kit)."""
    def control():
        # The kit is paper-only by construction — no kill-switch / control
        # service ships (same posture as trade-manager). Always-pass no-op so
        # propose()'s control gate can never fail-closed for lack of a service.
        return {"exit": 0, "mode": "paper"}

    def markov():
        # On-box regime from local-markov (the kit's Alpaca-bars trend/vol
        # proxy) — same 0/10/20 veto exit contract as the mesh veto.sh.
        p = _sh("bash", _sib("local-markov", "veto.sh"), "SPY")
        return {"exit": p.returncode}

    def catalyst(ticker):
        # The kit ships no catalyst/news/fundamentals layer (data-fence:
        # price action + LLM judgment only). No advisory catalyst line.
        return ""

    def risk(base):
        # Discretionary REQUIRES the v2 (whole-share-swing) risk profile: the
        # conviction-floor bypass that lets a below-floor gut trade size at all
        # lives ONLY in risk.py's v2 path (SHARK_WHOLE_SWING_V2=1). Without it,
        # risk.sh runs v1 and hard-rejects every below-floor discretionary entry
        # — silently defeating the feature. v2 is the current paper profile, so
        # forcing it also keeps discretionary at parity with the autonomous gate
        # (agent-stop R/R, open-cap 5, -3% daily-loss). Force it for this call.
        p = _sh("bash", _sib("risk", "risk.sh"), stdin=json.dumps(base),
                env={**os.environ, "SHARK_WHOLE_SWING_V2": "1"})
        try:
            verdict = json.loads(p.stdout or "{}")
        except json.JSONDecodeError:
            verdict = {}
        return {"exit": p.returncode, "verdict": verdict}

    def enter(ticker, qty, entry, stop):
        p = _sh("bash", _sib("trade-manager", "manage.sh"), "enter",
                ticker, str(qty), str(entry), str(stop))
        lines = (p.stdout or "").strip().splitlines()
        try:
            return json.loads(lines[-1])
        except (json.JSONDecodeError, IndexError):
            return {"ok": p.returncode == 0, "stage": "enter", "raw": p.stdout}

    def reflect(slip):
        _sh("bash", _sib("reflection", "reflection.sh"), "append",
            stdin=json.dumps(slip))

    return {"control": control, "markov": markov, "catalyst": catalyst,
            "risk": risk, "enter": enter, "reflect": reflect}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] not in ("propose", "execute"):
        print("usage: discretionary.py {propose|execute}  (reads JSON on stdin)",
              file=sys.stderr)
        return 2
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        print("[discretionary] bad stdin JSON", file=sys.stderr)
        return 3
    runners = _real_runners()
    out = (propose(payload, runners) if argv[0] == "propose"
           else execute(payload, runners))
    print(json.dumps(out))
    return 0 if out.get("ok") else 10


if __name__ == "__main__":
    sys.exit(main())
