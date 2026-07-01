# `trade-manager` — deterministic exit / position-management skill

Part of the Shark Starter Kit. Owns a position's lifecycle after the brain decides
to buy. **"LLM as quant analyst, code as the execution desk."**

## Status

| Phase | Scope | State |
|---|---|---|
| **1** | one full-size GTC **bracket** at entry (stop −1R + take-profit +2R) | ✅ built + tested |
| **2** | scale half at **+1R**, runner stop → **breakeven**, re-place **+2R** target | ✅ built + tested (HEARTBEAT Step 2a; cancel-and-rebuild OCO) |
| 3 | trailing-stop ratchet (percent / chandelier) | 🅿️ built, `trail_method` default-off; **PARKED** |
| 4 | pyramiding | ⏳ not built |

## Files

```
trade_manager.py      pure decision core (no network): plan_entry() + audit() + CLI
broker.py             the ONLY network touch: places the bracket, falls back to market+stop;
                      stamps a client_order_id on every write + reconciles ambiguous entries
execution_adapter.py  broker-neutral ExecutionAdapter interface + LegacyAlpacaRestAdapter
                      (the single HTTP touch; default rail = Alpaca paper REST). Fail-closed:
                      a transport failure with no broker answer returns (None, ...)
manage.sh             thin jq-free wrapper -> broker.py
tests/                pytest, stdlib only, pure-core (no network)
```

## Decision core (`trade_manager.py`, pure & tested)

- `plan_entry(ticker, entry, stop, qty, phase=1) -> {target, orders, reject_reason}`
  Phase 1 → exactly one full-size bracket. `target = entry + 2·(entry−stop)`; target
  and stop nudged off `.00`/`.50` round-number magnets. Rejects `qty<1`,
  `stop≥entry`, non-positive prices.
- `audit(snapshot) -> {state, actions, realized}`
  Phase 1 state machine: HOLD when protected, **repair a missing stop**, and on close
  log realized **P&L + R-multiple** classified `stop_hit` / `target_hit`. (Breakeven /
  trailing are Phase 2/3 — `audit()` never moves a winner's stop in Phase 1.)

## Execution (`broker.py` / `manage.sh`)

```bash
manage.sh enter TICKER QTY ENTRY STOP [PHASE] [--dry-run]
```

- Places a protective+profit **GTC bracket** for whole shares.
- **Bracket-or-fallback safety:** if Alpaca rejects the bracket, it falls back to the
  rig's known-good behavior (market buy + separate GTC stop) and logs a `WARN` — a
  position is **never** left unprotected. This is what makes "verify on the next real
  trade" safe without first running the Phase 0 spike.
- **Paper-guarded:** refuses any base URL without `paper`. The kit is paper-only by
  construction — there is no live path, so the full system's Cloud Run entry lock is
  intentionally omitted (with no such service to ship, gating entries on it would fail
  closed and the bot could never trade). All bracket/scale/exit logic is unchanged.
- **Fail-closed networking (Phase 2):** the adapter's single HTTP touch returns
  `(None, {"error": ...})` on any transport failure with no broker answer (DNS,
  connection refused, read/connect timeout, TLS). `None` is falsy in every caller's
  `st and 200 <= st < 300` guard, so an unreachable broker reads as "did not happen"
  — never as success, and never raises into the heartbeat.
- **Idempotency + reconciliation (Phase 2):** every order-creating write carries a
  `client_order_id`. **Entries** use a *stable* `shark-enter-{TICKER}-{UTCdate}` key
  (`_entry_coid`) that survives a heartbeat-to-heartbeat retry, so a re-entry of an
  order that timed out after landing re-sends the same id and Alpaca rejects the
  duplicate instead of opening a second position. `enter()` resolves uncertainty by
  reconciling that key, never by blind-falling-back:
  - bracket accepted → done;
  - **no answer** (transport timeout) → `reconcile()` (`GET /v2/orders:by_client_order_id`);
    found → report placed; not found → `stage:"ambiguous"`, place nothing;
  - **duplicate-coid reject** (a prior fire's bracket is live) → reconcile → report
    placed, or `stage:"duplicate_unresolved"` if unreadable — **never** a fallback buy;
  - **genuine reject** (e.g. bracket not allowed) → the market+stop fallback runs.
  Exit/repair writes (stop, scale-out, flatten, dire-liquidate) carry per-call keys
  (`_new_coid`); they aren't fire-to-fire retried and are guarded by held-qty re-reads
  + the audit loop. (Cross-fire entry dedup also composes with the `risk` skill's
  `already_held`/`traded_today` pre-gate.)
- Env: `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` (aliases `ALPACA_KEY_ID` / `ALPACA_SECRET`),
  `ALPACA_BASE_URL` (default paper).

## SHARK_FRACTIONAL — Small Account Profile v1 (default OFF)

`SHARK_FRACTIONAL=1` switches sizing + execution to fractional shares so a small
account can take an expensive stock (e.g. $1k account → 0.08 of a $625 stock).
Fractional positions are **intraday-only** — they can't carry a durable overnight
stop (Alpaca rejects non-DAY orders on fractional qty), so v1 force-flats them
before the close instead of relying on an overnight audit loop:

- `risk.py` sizes to a **dollar notional** (no whole-share floor; $1 minimum),
  capped by the small-account `$50` position cap when `SHARK_SMALL_ACCOUNT=1`.
- `plan_entry` (fractional) rests three independent DAY orders — **market buy,
  DAY stop, DAY limit at target** (not an OCO bracket; the system reconciles).
- `intraday_window(minutes_to_close)` — no new entries at/after **3:30 PM ET**,
  force-flat at/after **3:45 PM ET**.
- `audit()` **force-flat** (when `force_flat` set) → cancel both exits → market
  sell → `verify_flat`. Hard stop: **no fractional position by 3:55 PM ET**.
- `audit()` **close reconciliation (fractional only)** → a filled DAY leg leaves
  its sibling resting → cancel it. Whole-share uses a real bracket (broker OCO).
- `broker.is_fractionable` / `market_open` guards before any fractional order;
  `broker.flatten()` cancels → sells → verifies qty==0, returning `alert=True`
  on any residual so the caller surfaces it and blocks new entries.
- ⚠️ **Test on a dedicated PAPER account only.** Two open items verify on paper:
  Alpaca accepts a DAY limit sell + DAY stop on a fractional long, and
  `daytrade_count` populates (see spec).

## How it wires into the HEARTBEAT

In `HEARTBEAT.md`, the execution step replaces "market buy + place_stop" with a
single call:

```bash
bash skills/trade-manager/manage.sh enter "$TICKER" "$QTY" "$ENTRY" "$STOP"
```

`QTY` / `STOP` come from the `risk` skill (Step 5.5); `ENTRY` is the intended/last price.
The bracket then rests on Alpaca and exits fire **between** fires.

## Test

```bash
python3 -m pytest tests/ -q     # 119 passed
```
