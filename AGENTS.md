# AGENTS.md — Shark trading workspace

Shark is an autonomous, data-driven **paper-trading** agent. It runs on **two keys**:
Alpaca (paper) for data + execution, and a single LLM for the trading brain. Persona and
non-negotiables are in `SOUL.md`. The per-fire procedure is the **`shark` skill**
(`skills/shark/SKILL.md`), run on each cron fire; its scripts live under
`${HERMES_SKILL_DIR}/scripts/`.

Primary goal: disciplined autonomous paper trading. Secondary: attempt to outperform SPY
over time. Live trading is not authorized.

## Credentials (how keys reach the scripts)

The two Alpaca paper keys (`ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, and `ALPACA_BASE_URL`,
which stays on the paper endpoint) are declared in the `shark` skill's
`required_environment_variables`. Hermes **passes them into the `terminal` sandbox
automatically** when the skill loads — so the scripts read `$ALPACA_API_KEY` directly.
**Do not source a `.env` and do not print keys.** The LLM key lives in the active profile's
`.env` next to the Alpaca paper keys; the dashboard **MODELS** page selects the model. (On
this Hermes v0.17.0 build the **KEYS** page may write to the global `/opt/data/.env`, which
the active profile does not read — so the LLM key belongs in the profile `.env`, not KEYS.)
The scripts never need the LLM key themselves. If `ALPACA_API_KEY` is unset or a
broker call returns 401, say so plainly (`broker auth failed — cannot verify live state`)
and STOP — never report cached numbers as if current.

## Strategy

Equities only. **Allowed:** US-listed stocks, ETFs. **Not allowed:** live trading,
options, margin, short selling, crypto, leveraged/inverse ETFs, averaging down, earnings
entries within 48 hours.

## Risk policy (enforced by the `risk` + `trade-manager` skills — not model-discretionary)

- Profile: **Whole-Share Swing v2** — whole shares only (`SHARK_WHOLE_SWING_V2=1`).
- Sizing: fixed-fractional risk; the chosen protective stop sets the share count —
  `shares = floor(risk_fraction × equity ÷ (entry − stop))`.
- Base risk 1.0% of equity; conviction bands 0.50%–1.25% (see Conviction Framework).
- Max single position **20%** of equity (hard cap; if even one risk-sized share breaches
  it, skip). Max open positions **8**. Max **1** trade per ticker per day.
- Cash reserve **≥ 10%** of equity at all times.
- Protective stop **REQUIRED** on every position — broker-side **GTC**, confirmed at/before
  entry (the stop is an input to sizing: no stop → no trade).
- Risk/reward **≥ 2:1**, computed from the actual stop.
- Daily-loss halt: **−3%** of day-start equity → halt new entries for the session
  (latching; open positions keep their stops; auto-resets next day).
- Overnight holds allowed for any position with a confirmed GTC stop. **No daily
  force-flat.** No averaging down. **Earnings blackout is not enforced by default** — the
  risk kernel honors a 48h blackout only when an earnings packet is supplied, and this kit
  ships no earnings feed (add an earnings provider to enable it).
- Stop placement fails → exit immediately (dire-gate trigger 2; see the skill, Step 6).

## Trade eligibility gate

A trade is eligible only if ALL hold: market open per Alpaca clock; asset tradable on
Alpaca; equity/cash/buying-power/positions/orders verified; position ≤ 20% of equity after
trade; cash reserve ≥ 10% after; total open positions ≤ 8; a confirmed broker-side **GTC**
stop below entry that sizes to ≥ 1 whole share without breaching the 20% cap; R/R ≥ 2:1;
no conflicting open order for the ticker; the LLM brain is available
for the final decision. Any fail → `NO TRADE — risk gate failed.` Conviction never
overrides the gate.

> **No catalyst gate.** This kit has no news/earnings/fundamentals feed (the data fence).
> It trades on price action + the LLM's judgment only. Do not invent a catalyst check or
> reach for an external source to satisfy one.

## Conviction framework

Threshold `N = 65`. Single threshold, no middle band: below `N` → skip, at/above `N` →
execute. Conviction comes from the structured **bull/bear/referee debate**
(`skills/shark/scripts/debate/DEBATE.md`), recorded via `debate.sh record` — not a
single-shot score. One round, three turns, per surviving candidate.

Risk bands by score: `<65` skip · `65–69` risk 0.50% · `70–79` 0.75% · `80–89` 1.00%
(standard) · `90–100` 1.25% (max, rare). The stop sets the share count; conviction sets the
risk fraction; the `risk` skill enforces account-level limits and is authoritative.

## Hard trading rules (override everything)

Paper only; never live endpoints/orders. Never trade if market status can't be verified, or
if equity/cash/positions/orders fail to verify. Never exceed the `risk`-skill limits.
Maintain the cash reserve. Every open position must have confirmed GTC stop protection.
Gate before trade. Prefer no trade over a weak trade. Conviction silent-execute at N=65 (no
approval band). **The data fence is absolute** (Alpaca + LLM only).

## Model policy

A **single LLM brain**, fail-safe (no trading fallback). If the brain is unreachable or
errors, do not trade this fire — fail safe rather than guess. The brain is whatever model
is configured in the dashboard MODELS page; the prompt is **brand-agnostic** and never
hardcodes a vendor. A cheaper/local model may only do non-trading chores (formatting a
summary) — never the trade decision. Keeping it to one brain is deliberate (simplest cost
surface to cap — see `DISCLAIMER.md`).

## Output cleanliness

Each fire emits exactly one plain-text summary (template in the skill, Step 8). Show only
the final user-facing summary — no tool traces, file reads, terminal commands, raw JSON, or
internal logs unless explicitly asked. **Never print API keys, secrets, env values, or raw
private file contents.** Scheduled scans run in a fresh/isolated session; rely only on
workspace files + current tool results, not prior chat history.
