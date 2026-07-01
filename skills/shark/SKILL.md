---
name: shark
description: Run the whole-share swing paper-trading routine — market/regime gate, discovery, bull/bear/referee debate, conviction gate, risk-sized GTC bracket entry, managed exits, self-grading journal, persistent thesis. Use on each scheduled (cron) fire, and for an owner-initiated discretionary "take TICKER" gut trade.
version: 1.0.0
license: MIT
metadata:
  hermes:
    tags: [Trading, Finance, Automation, Paper-Trading]
    category: finance
    requires_toolsets: [terminal]
required_environment_variables:
  - name: ALPACA_API_KEY
    prompt: "Alpaca PAPER API key"
    help: "app.alpaca.markets → switch to the Paper account → generate keys. Paper only — never a live account."
    required_for: "market data + paper execution"
  - name: ALPACA_SECRET_KEY
    prompt: "Alpaca PAPER API secret"
    help: "The secret paired with ALPACA_API_KEY."
    required_for: "market data + paper execution"
  - name: ALPACA_BASE_URL
    prompt: "Alpaca paper endpoint (leave default)"
    help: "Defaults to https://paper-api.alpaca.markets. Do not point at a live account."
    required_for: "broker endpoint (paper)"
---

# Shark — scheduled trading routine

You are running the **Shark** whole-share swing paper-trading routine. Your persona,
risk policy, and conviction framework are in `SOUL.md` and `AGENTS.md` (loaded as your
identity). This skill is the **procedure** you execute each fire.

All scripts live under **`${HERMES_SKILL_DIR}/scripts/`** and are invoked with the
`terminal` tool. Your Alpaca keys are **already in the environment** (Hermes passes the
`required_environment_variables` above into the terminal sandbox) — **do NOT source a
`.env`, and do NOT echo or print the keys.** `SHARK_WHOLE_SWING_V2=1` is required on the
`risk` and `trade-manager` calls (whole-share sizing).

For brevity below, let `S=${HERMES_SKILL_DIR}/scripts`.

---

## ⛔ THE DATA-FENCE RULE (read first, non-negotiable)

You have **Alpaca market data and your own reasoning. That is all.** Do **not** run
`curl` to third parties, web search, `pip install`, or `execute_code` to fetch
market / news / fundamental data from anywhere else. There is **no news, earnings, or
fundamentals feed** — Shark trades on **price action + the LLM's judgment**, nothing
more. If you lack data to justify a trade, conviction stays low and you do not trade.
Reaching for a third data source only wastes the fire.

---

## Procedure (run in order each fire)

### Step 0 — Market gate
1. If today is Saturday or Sunday → final summary `CLOSED — heartbeat OK`. Stop.
2. Else run `bash $S/alpaca/clock.sh`. If Alpaca `is_open=false` (incl. holidays) →
   final summary `CLOSED — heartbeat OK`. Stop. No scan, no other calls.
3. If `ALPACA_API_KEY` is unset or a broker call returns 401 → final summary
   `NO TRADE — primary data unavailable.` Stop. (Infrastructure failure, not a decision.)

### Step 1 — Account state
Fetch from Alpaca (any failure → abort the fire, no trade, do not guess broker state):
- `bash $S/alpaca/account.sh` — equity, cash, buying power
- `bash $S/alpaca/positions.sh` — open positions
- `bash $S/alpaca/orders.sh` — open orders and stops

**Exit reconciliation (before Step 2).** Compare live positions to the portfolio state
you recorded last fire. For every ticker present last fire but **absent** now:
1. `bash $S/alpaca/orders.sh closed` → find the SELL fill (symbol + qty); capture fill
   price, filled_at, order id.
2. Compute realized P&L from the prior entry price to the fill.
3. Classify: fill within $0.05 of the prior stop → **stop hit**; else → **manual exit**
   (flag it). Note the exit in this fire's summary.
4. **Grade it into the journal** (so the lesson feeds future decisions):
   a. `bash $S/reflection/reflection.sh pending` → find the open slip for the ticker
      (match by ticker; has its original date, entry, stop).
   b. `printf '%s' '{"entry_price":ENTRY,"exit_price":FILL,"entry_date":"SLIP_DATE","exit_date":"TODAY","realized_R":R}' | bash $S/reflection/reflection.sh outcome`
      (pass the blended realized R from the trade-manager audit).
   c. Read the numbers, write a 2–3 sentence lesson **in your own words**: was the
      directional call right (cite the alpha), what held/failed, one lesson for next time.
   d. `printf '%s' '{"ticker":"TICKER","date":"SLIP_DATE","outcome":OUTCOME_JSON,"lesson":"<your lesson>"}' | bash $S/reflection/reflection.sh resolve`
   e. `printf '%s' '{"ticker":"TICKER","outcome":OUTCOME_JSON}' | bash $S/thesis/thesis.sh close`
      (flips the open thesis to closed; no open thesis → harmless no-op).
   Scale-outs grade **once**, when the last share is gone, using the blended R.
   `alpha n/a` (SPY unreachable) is fine — grade anyway.

### Step 2 — Audit stops
For each open position confirm: a stop exists; distance to stop; position % of equity; no
conflicting open order. Flag missing stops, stop buffer < 3%, position over the 20% /
$5,000 cap, or cash reserve < 10%. Fix a missing stop with
`bash $S/alpaca/place_stop.sh` before scanning. If a position is unprotected and a stop
placement fails on retry → follow the Step 6 dire-gate exit path.

### Step 2a — Position management (trade-manager, in code)
For **each** open position, run the dispatcher once (it reads entry/qty/last/legs from
Alpaca itself — you pass only the symbol):
```
SHARK_WHOLE_SWING_V2=1 bash $S/trade-manager/manage.sh manage-position SYMBOL
```
In code it: repairs a missing stop; at **+1R** (and not already at breakeven) **scales out
half at market**, lifts the runner's stop to **breakeven**, and re-places the **+2R**
target (cancel-and-rebuild OCO); a single-share position only lifts the stop to breakeven.
From the JSON: a `{"op":"scale_out",...,"ok":true}` → note `Scaled SYMBOL — sold N @ +1R,
stop→breakeven, runner +2R`. Non-empty `alerts` → flag urgently and **block new entries**
this fire.

### Step 2b — Close-protection audit (no liquidation)
Whole-share swing positions hold overnight behind their GTC brackets — **no daily
force-flat.** Confirm each open position has a resting broker-side **GTC stop**; if missing
/ rejected / DAY-only, re-place a GTC stop via `bash $S/alpaca/place_stop.sh`. If an order
is stuck in a dangerous state or a position violates risk policy, flag it and **block new
entries** for the fire. Otherwise **HOLD** — never liquidate a healthy, protected position.

### Step 2c — Thesis exit check (held positions, advisory)
`bash $S/thesis/thesis.sh rescore "<this fire's ISO timestamp>"` → one row per held thesis
(regime comes from the on-box `local-markov`, no external service). For any row with
**`exit_signal:true`** (a **core** assumption violated, or `invalidation_price` confirmed
breached) → note an advisory `{SYMBOL} thesis broken — {deltas}; weigh exit` and factor it
into management. **Advisory only:** it NEVER cancels brackets, force-sells, or overrides
Steps 2/2a/2b. Rows with `exit_signal:false` need no action. If `rescore` errors, skip
silently (fail-open).

### Step 2.5 — Regime gate (local-markov)
One SPY-mood check per fire (computed on-box from Alpaca daily bars; no external service):
```
bash $S/local-markov/veto.sh SPY
```
Exit `0` PASS (Bull/Sideways) → proceed. Exit `10` VETO (Bear) → **skip new entries this
fire** (Steps 3–6); Step 7 still runs; summary reason `regime risk-off (Bear)`. Exit `20`
→ undetermined; treat as PASS. Never block trading on a data hiccup. The veto applies to
**new long entries only** — stop adjustments, dire-gate exits, and existing-position
management are never blocked.

### Step 3 — Discovery
```
bash $S/discovery-local/discover.sh
```
Returns candidate tickers per `DISCOVERY_MODE` (`watchlist` default, or `alpaca_movers`).
This finds **what's moving, not why** — no catalyst/news/fundamentals layer. Limit
consideration to the top **3–5** candidates; do not scan broadly to manufacture activity.

### Step 3.4 — Session P&L (daily-loss circuit breaker)
`python3 $S/risk/session_pnl.py` → broker-derived `{day_start_equity, session_low_equity}`.
Use its `day_start_equity` (authoritative) and include BOTH fields in the `account` object
of EVERY `risk.sh` call this fire. They make the −3% daily-loss halt **latching** (trips on
the session low, stays tripped, auto-resets next day). If it prints `{}`, omit
`session_low_equity`. Also include `buying_power` (from `account.sh`) in both risk calls.

### Step 3.5 — Allowed-actions pre-gate
Before any conviction work, run the legality pre-gate (enforces once-per-ticker-per-day and
no-re-buy-after-stop-out **in code**). Assemble `today_activity` from today's Alpaca fills
(BUY today → `traded_today`; stop-classified SELL today → `stopped_today`):
```
printf '%s' '{"account":{"equity":EQUITY,"cash":CASH,"buying_power":BUYING_POWER,"day_start_equity":DAY_START,"session_low_equity":SESSION_LOW,"last_equity":LAST_EQUITY},"positions":[{"ticker":"...","market_value":...}],"candidates":[{"ticker":"...","price":...}],"today_activity":{"traded_today":[...],"stopped_today":[...]}}' \
  | SHARK_WHOLE_SWING_V2=1 bash $S/risk/risk.sh actions
```
`new_entries_allowed:false` → **score no candidates**; note `account_blockers` and stop.
Else carry into Step 4 **only** candidates whose `actions` include `"buy"`; drop hold-only
ones (their `blockers` say why).

### Step 4 — Candidate check + conviction debate
For each surviving candidate apply the **Trade Eligibility Gate** and **Conviction
Framework** from `AGENTS.md`/`SOUL.md`. Pull past lessons:
`bash $S/reflection/reflection.sh context TICKER` — weigh same-ticker / cross-ticker
lessons (they inform conviction, never override the gate; empty is normal).

Produce conviction via the **bull/bear/referee debate** (`$S/debate/DEBATE.md`), not a
single-shot score: one Bull turn, one Bear turn on the **same** facts + the lessons, then a
Referee turn emitting 0–100. Record and read back the validated score:
```
printf '%s' '{"ticker":"TICKER","date":"TODAY","bull":"<bull case>","bear":"<bear case>","verdict":{"conviction":SCORE,"stance":"STANCE","rationale":"<one line>"}}' | bash $S/debate/debate.sh record
```
Single round, three turns, per candidate. If the helper exits non-zero, fall back to a
single-shot conviction for that candidate. Price movement without a clear reason is not
permission to trade. The brain DECIDES the protective stop (invalidation point) and passes
it to the `risk` skill; sizing is `shares = floor(risk_fraction × equity ÷ (entry − stop))`,
whole shares only.

### Step 5 — Decide
Conviction threshold `N = 65`. Gate fail → no trade (`risk gate failed`). Gate pass +
score `< N` → no trade (`conviction {score} < {N}`). Gate pass + score `≥ N` → execute.
Brain unavailable → no trade (fail-safe). Regime veto → already skipped
(`regime risk-off (Bear)`). Conviction never overrides the eligibility gate.

### Step 5.5 — Size + risk-gate (authoritative)
Only when Step 5 decided to trade. `SHARK_WHOLE_SWING_V2=1`; the brain's `stop_price` is
required (no stop → no trade):
```
printf '%s' '{"account":{"equity":EQUITY,"cash":CASH,"buying_power":BUYING_POWER,"last_equity":LAST_EQUITY,"day_start_equity":DAY_START_EQUITY,"session_low_equity":SESSION_LOW},"candidate":{"ticker":"TICKER","price":ENTRY,"conviction":SCORE,"stop_price":STOP,"target_price":TARGET},"positions":[{"ticker":"...","market_value":...,"unrealized_pl":...}]}' \
  | SHARK_WHOLE_SWING_V2=1 bash $S/risk/risk.sh
```
Exit `0` PASS → use the returned `qty` and `stop_price` **exactly**. Exit `10` REJECT → do
not trade (log `reject_reason`/`gates_failed`/`dire_triggers`). Exit `3` input error → fix
the payload; never trade on a parse failure. Treat `max_open_positions`, `daily_loss_halt`,
`averaging_down` like any other gate failure.

### Step 6 — Execute (GTC bracket, in code)
`QTY` and `STOP` are the Step 5.5 outputs (exact); `ENTRY` is the candidate price. Never
hand-place orders or build curl.
```
SHARK_WHOLE_SWING_V2=1 bash $S/trade-manager/manage.sh enter TICKER QTY ENTRY STOP
```
`stage:"bracket"` → accepted (stop + +2R target both GTC). `stage:"rth_guard"` → market not
open; skip. `stage:"fallback",ok:true` → broker rejected the bracket; fell back to market
buy + GTC stop (no target) — report, mark target unplaced. `ok:false` → **dire-gate trigger
2**: if a position opened unprotected, exit it now with
`bash $S/trade-manager/manage.sh dire-liquidate TICKER QTY` (it refuses to sell if a stop
already rests → `stage:"blocked_protected"` means hold + report, do not retry;
`stage:"liquidated"` → report the reason). Never leave a naked position.

Then:
1. `bash $S/alpaca/orders.sh` — confirm the entry filled and the stop (and target) are active.
2. Capture order IDs + the returned `target`.
3. **Reflection slip:** `printf '%s' '{"ticker":"TICKER","date":"TODAY","conviction":SCORE,"entry":ENTRY,"stop":STOP,"thesis":"<one-line thesis>"}' | bash $S/reflection/reflection.sh append`
4. **Thesis (entry):** decompose the long case into 2–4 **falsifiable** assumptions, each
   bound to one allowed machine-check — `price_above`/`price_below` (param: level),
   `regime_favorable`, `stop_distance` (param `{stop,min}`), or `manual`. Mark load-bearing
   ones `core`; set `invalidation_price` to the protective STOP:
   `printf '%s' '{"ticker":"TICKER","direction":"long","conviction":SCORE,"invalidation_price":STOP,"fire":"<fire ISO>","assumptions":[{"id":"a1","claim":"<why this holds>","check":{"type":"price_above","param":LEVEL},"weight":"core"}]}' | bash $S/thesis/thesis.sh create`
   (Only `core` assumptions and a confirmed `invalidation_price` breach can later trigger an
   exit advisory. There is no catalyst/fundamentals check — do not invent one.)

### Step 7 — State
Record this fire's live portfolio state (equity, day P&L, position count, each position's
entry/stop) so the next fire's exit-reconciliation has a baseline. Persist it via the
journal/thesis stores the scripts above already write. Do not append portfolio history;
keep only the latest snapshot.

### Step 8 — Summary (the delivered message)
Emit **exactly one plain-text summary** — this is the cron's delivered card. No markdown
tables, no tool traces, no raw JSON, no keys.
```
SHARK — {HH:MM ET}
{NO TRADE — short reason | BUY TICKER × QTY @ $PRICE, stop $STOP, conv N}
Equity ${X.XX} | Day {±}${X.XX} | Positions {N}
{stop status / any scale-out / thesis advisory / stop-hit lines}
```
`{short reason}` ∈ `risk gate failed` | `conviction {score} < {N}` | `regime risk-off
(Bear)`. `{stop status}` = `stops OK` when every position has a stop with buffer ≥ 3%, else
a short flag (`ZETA buffer 2.9% ⚠️`, `1 missing stop`); zero positions → `Positions 0`.

**Quiet on no-action fires:** if the fire took **no action** (closed market, no trade, no
management change), **prefix the summary with `[SILENT]`** so the cron delivery stays quiet
and doesn't spam the channel on every idle fire.

---

## Discretionary entry — "take TICKER" (out of band, owner-only)

**Not part of the scheduled scan.** Triggered only when the **account owner** messages a
trade directive in chat ("take TTWO", "buy TTWO stop 222"). A non-owner asking about a
stock gets **analysis only — never an execution.**

1. **Recognize** the owner's directive → ticker, current price, optional operator stop.
2. **Conviction (advisory):** run the bull/bear/referee **debate** for the ticker (the only
   LLM step here).
3. **Propose** (the skill sizes + gates it):
   ```
   echo '{"account":{...},"positions":[...],"candidate":{"ticker":"TTWO","price":PRICE,"conviction":SCORE,"stop":STOP_OR_OMIT}}' | SHARK_WHOLE_SWING_V2=1 bash $S/discretionary/discretionary.sh propose
   ```
   `ok:false` → HARD block; refuse, quote `hard_block`/`reason`, stop. `ok:true` → you get
   `{qty, entry, stop, target, equity_pct, conviction, catalyst}` (`catalyst` always empty —
   no news layer).
4. **Present & ask (do not trade yet):**
   ```
   🦈 Shark brain on TTWO: conviction {conviction}/100 · regime OK
   If you override, I'd place: {qty} sh @ ~${entry} · stop ${stop} · target ${target} (+2R) · {equity_pct:.0%}
   Override and take it? (yes / no)
   ```
5. **On the owner's explicit "yes" only:** add `date` (today) + `thesis` (owner's
   rationale) and pipe to `bash $S/discretionary/discretionary.sh execute`. Report the fill
   card. On "no" / no reply → place nothing.

**The split that keeps it safe:** conviction is ADVISORY (the owner's "yes" overrides a low
score); the risk kernel (sizing, never-naked, +2R bracket, concentration, cash, drawdown,
daily-loss, account guard, regime veto) is HARD and cannot be overridden. Nothing executes
without BOTH a human "yes" AND a passing `propose`.
