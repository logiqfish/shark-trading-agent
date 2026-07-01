---
name: alpaca
description: Alpaca paper-trading account access (read + write). Use for account state, positions, orders, market clock, AND paper order/stop placement. Paper account only. Part of the Shark Trading Agent kit.
---

# Alpaca Paper-Trading Skill

Read and write access to the Alpaca paper-trading API. This is the **only** authorized way to interact with the broker — never construct Alpaca curl calls inline. Always go through this skill.

## Why this skill exists

Without it, the agent has to assemble curl commands by hand, which:
- Wastes tokens reasoning about HTTP headers and endpoints every call
- Fails silently when credentials are present in env but the model can't see them in the prompt
- Mixes formatting concerns (the LLM building requests) with execution concerns (actually calling Alpaca)

This skill is a thin wrapper: each script does one Alpaca call, returns raw JSON, uses env-injected credentials. The model picks WHICH script; the script handles HOW.

## Available scripts

All scripts live under `${HERMES_SKILL_DIR}/scripts/alpaca/`. They read `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` from the environment.

**Env is auto-injected — do not source a `.env`.** The two Alpaca keys are declared in `distribution.yaml` (`env_requires`); Hermes passes them into the `terminal` sandbox automatically when the skill loads, so the scripts read `$ALPACA_API_KEY` directly. If a script returns `ALPACA_API_KEY not set`, the keys are missing from the profile `.env` — add them via the App terminal (`printf 'ALPACA_API_KEY=…\nALPACA_SECRET_KEY=…\n' >> /opt/data/profiles/shark-trading-agent/.env`) and restart. Never hand-source a file, and never print keys.

**Read scripts:**

| Script | Returns | When to use |
|---|---|---|
| `account.sh` | JSON: equity, cash, buying power, status, account number | "Portfolio status", "What's my P&L?", account health checks |
| `clock.sh` | JSON: `is_open`, `next_open`, `next_close`, `timestamp` | Market-gate decisions, "Is the market open?", weekend/holiday checks |
| `positions.sh` | JSON array: open positions with `qty`, `avg_entry_price`, `current_price`, `unrealized_pl`, `unrealized_plpc` | "Show positions", "What do I own?", risk audits |
| `orders.sh [status]` | JSON array: recent orders (default `status=open`, can pass `closed` or `all`) | "Show open orders", "Recent fills", stop-loss audits |

**Write scripts** (paper account only — see Safety below):

| Script | Returns | When to use |
|---|---|---|
| `place_order.sh SYMBOL QTY SIDE [LIMIT_PRICE] [TIF]` | JSON: created order with `id`, `status`, `filled_qty`, etc. | Shark-procedure entry; emergency exit (side=sell of position qty) when a stop fails. |
| `place_stop.sh SYMBOL QTY STOP_PRICE` | JSON: created stop order with `id`, `status`, `stop_price` | Shark-procedure stop placement; stop re-placement after audit reveals missing/loose stops. |

## Invocation pattern

Use the bash/exec tool. Scripts live under `${HERMES_SKILL_DIR}/scripts/alpaca/`; below, let `S=${HERMES_SKILL_DIR}/scripts`:

```bash
$S/alpaca/account.sh
$S/alpaca/clock.sh
$S/alpaca/positions.sh
$S/alpaca/orders.sh
$S/alpaca/orders.sh closed
$S/alpaca/place_order.sh AAPL 1 buy
$S/alpaca/place_stop.sh AAPL 1 145.00
```

## Example flows

**"What's my portfolio status?"**:
1. `clock.sh` — confirm market state (informs whether prices are live or last-close)
2. `account.sh` — equity, cash, buying power
3. `positions.sh` — open positions with P&L
4. Compose a human-readable reply. Don't dump raw JSON.

**Market-gate decision** (heartbeat):
1. `clock.sh` — read `is_open`
2. If `false` → respond per the shark procedure (`SKILL.md`) Step 0 closed-market template and stop. No further calls.
3. If `true` → continue with the shark procedure Step 1+

**"Are my stops still in?"**:
1. `positions.sh` — list open positions
2. `orders.sh` — list open stop orders
3. Cross-reference: every position should have a corresponding stop. If any missing → `place_stop.sh` to fix.

**Entry execution (shark-procedure fallback path)**:
1. `place_order.sh TICKER QTY buy` — entry (market) or with `LIMIT_PRICE` for limit
2. `orders.sh closed` — confirm fill (check `filled_qty` matches `qty`)
3. `place_stop.sh TICKER QTY STOP_PRICE` — stop-loss
4. `orders.sh` — confirm stop is active (status=`new` or `accepted`)
5. If step 3 or 4 fails → retry once. If still failing → `place_order.sh TICKER QTY sell` to exit, then escalate (dire-gate).

## Output

Scripts return **raw JSON from Alpaca**. Parse the fields you need; format human-readable rather than echoing raw JSON.

## Errors

Scripts use `set -euo pipefail` and `curl -fsS`. Non-zero exit = the call failed. The stderr explains why:
- `ALPACA_API_KEY not set` → credentials missing (escalate, do not trade)
- HTTP 401 / 403 → credentials invalid (escalate, do not trade)
- HTTP 4xx / 5xx → API problem (retry once, then escalate)
- Network failure → infrastructure problem (retry once, then escalate)

**Report the actual error.** Never claim "auth failed" without checking the exit code and stderr.

## Safety

- **Paper account ONLY.** Every script hardcodes `https://paper-api.alpaca.markets` — never live endpoints. Do not edit a script to point elsewhere.
- **Write scripts do not enforce policy.** `place_order.sh` and `place_stop.sh` are thin POST wrappers. They will accept any size, any symbol, any price. The eligibility gates (cash reserve, position-size cap, conviction floor, R/R, etc.) are enforced by the caller per `AGENTS.md` and the `risk` skill. **Do not invoke a write script unless all gates have passed.**
- **Conviction threshold.** Execute only at or above the conviction floor (see `AGENTS.md`). Below it → skip; do not call `place_order.sh`.
- **Stop-loss is required.** A `place_order.sh` for a new long position must be followed by `place_stop.sh` before the run ends. An unprotected position after one failed-then-retried stop placement is a dire-gate condition: exit the position with `place_order.sh side=sell`, then escalate.
- Per the shark procedure: if any read fails, return `NO TRADE — primary data unavailable`. Do not trade on partial information.
