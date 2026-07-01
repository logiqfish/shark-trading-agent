# `risk` — position-sizing + pre-trade risk gate

Part of the Shark Starter Kit. Stdlib-only, jq-free. A guardrail that lives
in-process — it cannot fail-open on a network outage.

## What it does

- `size(equity, price, conviction)` → `{qty, target_pct, stop_price, reject_reason}`
  Deterministic: conviction tier (upper bound, capped at 20%), whole-share
  `floor()`, 5%-below stop.
- `gate(account, candidate, positions, catalyst?, now?)` →
  `{pass, gates_failed, dire_triggers, earnings_check, notes}`
  Eligibility (max position 20%, cash reserve 10%, R/R ≥ 2:1) + the three
  computable dire-gates (concentration 25%, single-session drawdown 5%,
  earnings blackout 48h).

All constants live at the top of `risk.py` — the single source for
DECISION-POLICY.md §3 / §7 #4.

## CLI

```bash
printf '%s' '{"account":{"equity":10000,"cash":10000,"last_equity":10000},
"candidate":{"ticker":"NVDA","price":100,"conviction":70,"target_price":130},
"positions":[]}' | ./risk.sh
```

Exit codes: `0` pass · `10` reject/gated (do not trade) · `3` bad input.
The wrapper optionally fetches `../catalyst/fetch.sh` for earnings; if that's
absent or fails, `earnings_check` is `"unknown"` (warning, not a block).

## Tests

```bash
python3 -m pytest tests/test_risk.py -v
```

## Small Account Profile v1 (`SHARK_SMALL_ACCOUNT`)

Default OFF. When `SHARK_SMALL_ACCOUNT=1`, the $1,000 live-like profile applies
(threaded through `size()` / `gate()` / `_decide()`):

- **Position cap: `min(5% of equity, $50)`** — replaces the default 20% cap.
- **`max_open_positions` gate** — rejects a new symbol once 3 positions are held.
- **`daily_loss_halt` gate** — fails new entries when `equity − day_start_equity ≤ −$15`
  (pass `account.day_start_equity`; absent → a `notes` warning, never a silent block).
  Stays tripped for the session (the caller persists it; no replacement trade).
- **`averaging_down` gate** — rejects adding to a symbol held at an unrealized loss
  (pass `unrealized_pl` on each position).

With the flag OFF every constant and code path is byte-identical to before
(the existing 49 tests prove no regression). Pairs with `trade-manager`'s
`SHARK_FRACTIONAL` for the intraday execution side.

## Whole-Share Swing Profile v2 (`SHARK_WHOLE_SWING_V2`) — current default profile

**Supersedes Small Account v1** (which stays as a dormant flag for reproducibility).

$25,000 account, whole shares only, **fixed-fractional risk sizing**: the agent's
protective stop is a *required input* and decides the share count.

- `size_v2(equity, entry_price, stop_price, conviction)` →
  `{qty, risk_fraction, dollar_risk, stop_price, reject_reason}`
  `shares = floor(risk_fraction × equity ÷ (entry − stop))`. Conviction maps to a
  risk fraction (65–69 → 0.50%, 70–79 → 0.75%, 80–89 → 1.00%, 90–100 → 1.25%).
  Rejects: below conviction floor (65), stop ≥ entry, qty < 1, or one share over
  the 20% allocation cap (skip — never trim below the intended risk).
- `gate(..., whole_swing=True)` — R/R uses the **agent's input stop** (not a derived
  5% stop), open-position cap **8**, daily-loss halt **−3% of day-start equity**,
  no-averaging-down.
- `_decide` routes to the v2 path when `SHARK_WHOLE_SWING_V2=1`; the candidate JSON
  must carry `stop_price` (no stop → reject `"missing protective stop"`).

The model:
> **Conviction decides *whether* to trade; the stop decides *how many* shares;
> the `risk` skill enforces the account-level limits.**

20 v2 tests in `tests/test_whole_swing_v2.py`; the v1 + default suites stay green
(62 → 82 total). With the flag OFF, behavior is byte-identical to before.
