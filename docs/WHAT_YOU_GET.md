# What You Get — Shark Trading Agent

> **Shark is a paper-only autonomous trading agent that uses an LLM for judgment but forces
> every trade through deterministic risk and execution code. The model can debate, score,
> and explain — it cannot override the risk kernel.**

A 2-minute orientation for anyone who just scanned the QR code. For the full install, see
[SETUP.md](../SETUP.md).

---

## What this is

- A self-hosted **Hermes profile distribution** — persona + procedure + execution scripts +
  a scheduled cron, installed with one command. Not just a Python script.
- Runs on **two keys**: **Alpaca paper** (market data *and* execution) and **one LLM** (the
  reasoning brain — any provider; DeepSeek recommended).
- The loop: **market/regime gate → discovery → bull/bear/referee debate → conviction gate →
  risk-sized bracket entry → managed exits → self-grading journal → persistent thesis.**

## What this is NOT

- **Not live trading.** Paper-only by design — there is no live endpoint and no live order path.
- **Not a stock-picking oracle.** The point isn't alpha; it's the architecture.
- **Not financial advice.** Educational only — see [DISCLAIMER.md](../DISCLAIMER.md).
- **No news / earnings / fundamentals feed.** It trades on price action + the LLM's judgment,
  fenced to Alpaca.

## The one idea: the model is boxed in

The LLM decides *"is this setup worth taking?"* The **code** decides *"is this trade legal,
sized, protected, and paper-only?"* Conviction is **advisory**; the risk kernel is **hard**
and cannot be overridden by the model.

## Safety layers (all deterministic code, not prompts)

| Layer | Rule |
|---|---|
| Conviction gate | Score must clear the floor (**65**) — else `NO TRADE` |
| Position size | Fixed-fractional off the *required* stop; ≤ **20%** of equity |
| Cash reserve | ≥ **10%** cash after the trade |
| Open positions | ≤ **8** concurrent |
| Reward / risk | ≥ **2:1** |
| Protection | Every entry **broker-protected** — GTC bracket, or fallback market + GTC stop (**never naked**) |
| Daily-loss halt | **−3%** of day-start equity → no new entries (latching, auto-resets next day) |
| Discipline | No averaging down; max **1** trade per ticker per day |

Any gate fails → `NO TRADE — risk gate failed.` The model never gets a veto over this.

## Where the risk kernel lives

| Path | What it owns |
|---|---|
| `skills/shark/scripts/risk/` | Conviction floor, sizing, and the eligibility gate — the guardrail |
| `skills/shark/scripts/trade-manager/` | Bracket/fallback execution, managed exits, reconciliation |
| `skills/shark/SKILL.md` | The per-fire procedure the agent follows, in order |
| `AGENTS.md` / `SOUL.md` | Policy + persona — what the model may and may not do |

## Run a paper-only dry demo

1. Provision a Hermes box.
2. **Install *and activate* the Shark profile first** —
   `hermes profile install -y github.com/logiqfish/shark-trading-agent` then
   `hermes profile use shark-trading-agent`. Do this **before** any keys, or your config
   binds to Hermes' *default* profile (the #1 setup mistake).
3. Add your **LLM key and Alpaca paper keys** to the profile `.env` (App terminal), and pick
   the model on the **MODELS** page.
4. **Start the gateway**, then run the `weekday-trading` cron once by hand
   (`hermes cron run <id>`) and watch it: market gate → (maybe) bull/bear debate → risk gate
   → a paper order **or** a `NO TRADE` card.

*(Full no-SSH walkthrough: [docs/FRIEND-SETUP.md](FRIEND-SETUP.md); screenshots + per-provider
detail: [SETUP.md](../SETUP.md).)*

Everything is observable in the dashboard **LOGS** / **SESSIONS** and (if you wire Telegram)
a one-line status card per fire.

## Known limitations (by design + honest caveats)

- **The data fence is behavioral.** The shipped scripts only call Alpaca and the prompt
  forbids outside data — but the agent has terminal access, so the fence is enforced by
  instruction, not a sandbox. Production-grade containment adds host/container egress controls.
- **No earnings feed ships.** The risk kernel honors a 48h earnings blackout *only* if you add
  an earnings-data provider; it is **not enforced by default**.
- **Single brain, fail-safe.** No fallback model — if the LLM is unreachable, the fire fails
  safe to `NO TRADE`.
- **Paper only.** Going live is deliberately not wired.

---

*The real lesson isn't the trades — it's that agent autonomy is context, tools, state, gates,
and failure handling. The LLM is not the guardrail; the code is.*
