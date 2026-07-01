# Shark Trading Agent — Starter Kit

A skinny, **paper-only** trading bot you run on your own VPS as a **Hermes Agent profile
distribution**, with **two keys**. Unlike research/rating-only agent demos, **this one
actually trades** — with discipline:

> discover → bull/bear debate → conviction gate → bracketed entry → managed exit →
> self-grading journal → persistent thesis.

**New here?** Read the 2-minute orientation → [docs/WHAT_YOU_GET.md](docs/WHAT_YOU_GET.md).

It runs on exactly two keys and nothing else:

1. **Alpaca (paper)** — market data *and* execution.
2. **An LLM** — the single trading brain (DeepSeek recommended).

There is no hosted service, no mesh, no secrets of anyone else's — it all runs on your box,
on your paper account, at your risk. Read **[DISCLAIMER.md](DISCLAIMER.md)** before you
start, and **set a hard spending cap on your LLM account** (an always-on agent can run up
bills).

## What it does

- **Discovers** candidates from your watchlist (or Alpaca's most-actives) — Alpaca-only.
- **Debates** each candidate bull vs. bear and scores a 0–100 conviction.
- **Gates** every trade through a deterministic risk kernel (position size, cash reserve,
  R/R ≥ 2:1, −3% daily-loss halt, no averaging down, once-per-ticker).
- **Enters** with a GTC bracket (stop at −1R, target at +2R) — never a naked position.
- **Manages** exits in code: scales half at +1R, lifts the runner's stop to breakeven,
  rides to +2R.
- **Journals** every trade and self-grades it at exit (realized R + alpha vs SPY).
- **Remembers** the *why* of each open position as a persistent thesis and flags it when
  the thesis breaks.

## What it does NOT do

It has **no news, earnings, or fundamentals feed**. It trades on **price action + the LLM's
judgment** only, fenced to Alpaca + the LLM. The shipped scripts call only Alpaca, and the
prompt instructs the agent not to fetch outside data — but because the agent has terminal
access, this fence is enforced by instruction, not a sandbox. Production-grade containment
would add network egress controls at the host/container level.

**Paper trading only. There is no live-trading path in this kit, by design.**

---

## Install (everything in your browser — no terminal of your own)

You stand up Hermes once, then install Shark with a single line in the **in-browser App
terminal**. Full provisioning walkthrough with screenshots: **[SETUP.md](SETUP.md)**.

1. **Stand up Hermes v0.17.0** on a small VPS and configure your **LLM brain** (KEYS →
   your provider key; MODELS → pick the model — DeepSeek recommended). Optionally connect
   **Telegram** (CHANNELS → QR) so you can chat with it and get trade cards. *(SETUP.md
   Phases 1–4.)*

2. **Install the Shark distribution.** Open the Hermes app's **App terminal** (a shell in
   your browser — no SSH) and paste:
   ```
   hermes profile install github.com/logiqfish/shark-trading-agent
   ```
   It pulls the SOUL, the `shark` skill, and the cron, and writes a **`.env.EXAMPLE`**
   listing exactly the two Alpaca keys.

3. **Set your two Alpaca paper keys — in the FILES page (GUI).** In **FILES**, open the
   installed profile folder, copy its **`.env.EXAMPLE` → `.env`**, and paste your values:
   - `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` — from app.alpaca.markets → switch to the
     **Paper** account → generate keys. (Leave `ALPACA_BASE_URL` on the paper endpoint.)
   Your **LLM key is already set in KEYS** (step 1) — it does **not** go in this `.env`.

4. **Restart Gateway** (bottom-left). The `.env` is read on restart (it isn't hot-reloaded),
   so the keys take effect now.

5. **Smoke-test it by hand.** In **CHAT** (or Telegram): *"Run the shark skill now for a
   single fire."* During market hours you'll see it read the regime, surface a candidate,
   run the debate, and — if it trades — place a bracketed paper entry and a journal slip.
   Confirm the order in your Alpaca paper account.

6. **Enable the schedule.** The cron installs **disabled** on purpose. Turn it on in the
   **CRON** page (job `weekday-trading`, ~10:00 / 13:00 / 15:30 ET, Mon–Fri). If you wired
   Telegram, send **`/sethome`** in the chat where you want the trade cards delivered.

7. **(Optional) Gut trades.** DM the bot **"take TICKER"** — it debates the ticker, shows
   what it *would* place, and waits for your **yes/no** before any bracketed paper entry.

**Updating:** `hermes profile update` re-pulls the SOUL/skill/cron. Your runtime state
(journal, theses, portfolio) is excluded from the distribution, so updates never wipe your
history.

> **Cost guard.** This is an always-on agent that calls the LLM on every fire. Set a hard
> spending cap on your LLM account first. It fires ~3×/day on weekday market hours only —
> but cap it anyway.

---

See also: [SETUP.md](SETUP.md) (full provisioning) · [DISCLAIMER.md](DISCLAIMER.md) ·
[LICENSE](LICENSE).
