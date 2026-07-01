# Shark Trading Agent — Starter Kit

A skinny, **paper-only** trading bot you run on your own VPS as a **Hermes Agent profile
distribution**, with **two keys**. Unlike research/rating-only agent demos, **this one
actually trades** — with discipline:

> discover → bull/bear debate → conviction gate → bracketed entry → managed exit →
> self-grading journal → persistent thesis.

**New here?** Read the 2-minute orientation → [docs/WHAT_YOU_GET.md](docs/WHAT_YOU_GET.md).

It runs on exactly two keys and nothing else:

1. **Alpaca (paper)** — market data *and* execution. Free at
   **[alpaca.markets](https://alpaca.markets/)** (use a **paper** account).
2. **An LLM** — the single trading brain. Use **[OpenRouter](https://openrouter.ai/)** for
   this key and you can **swap brains** (DeepSeek, Claude, GPT, Gemini…) from one account by
   changing a single setting — no re-install. DeepSeek is a good, cheap default to start.

There is no hosted service, no mesh, no secrets of anyone else's — it all runs on your box,
on your paper account, at your risk. Read **[DISCLAIMER.md](DISCLAIMER.md)** before you
start, and **set a hard spending cap on your LLM account** (an always-on agent can run up
bills).

## What it does

- **Discovers** candidates from your watchlist (or Alpaca's most-actives) — Alpaca-only.
- **Debates** each candidate bull vs. bear and scores a 0–100 conviction.
- **Gates** every trade through a deterministic risk kernel (position size, cash reserve,
  R/R ≥ 2:1, −3% daily-loss halt, no averaging down, once-per-ticker).
- **Enters** with broker-side protection: primary path is a GTC bracket (stop at −1R,
  target at +2R); if the broker rejects the bracket, the fallback is a market entry + a
  separate GTC stop. Never naked — if stop protection can't be confirmed, it liquidates.
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

This is the **skinny** build on purpose. The heavier version wires the same brain into a
live **data mesh** — real-time news & catalyst detection (web search via **Brave**), deep
source reads (**Firecrawl**), paid **fundamentals / earnings / analyst** data subscriptions,
SEC-filing / 8-K monitoring, and a multi-pool **discovery engine** that surfaces market
movers instead of a static watchlist — plus the deeper evidence and verification layers
that back each thesis. It runs as a separate hosted service and is **not** part of this kit
by design. Want that? Reach out at **[logiqfish.com](https://logiqfish.com)**.

**Paper trading only. There is no live-trading path in this kit, by design.**

---

## Background: what you're standing up (Hermes + a VPS)

New here? Three pieces of jargon, explained once:

- **Hermes** is an open-source, self-hosted **AI-agent runtime** by Nous Research. It gives
  the bot a persistent home — memory, skills, a scheduler, and chat channels like Telegram —
  plus a **browser dashboard**, so you never need SSH. This kit ships *as* a Hermes profile
  you install in one line. Docs:
  **[hermes-agent.nousresearch.com](https://hermes-agent.nousresearch.com/docs/)** ·
  source: **[github.com/nousresearch/hermes-agent](https://github.com/nousresearch/hermes-agent)**.
- **A VPS** (Virtual Private Server) is a small, always-on Linux machine you rent in the
  cloud. **Why you need one:** the agent trades on a schedule (~3×/day on market days) and
  has to keep running when your laptop is closed — the VPS is that always-on box. We use
  **[Hostinger](https://www.hostinger.com/vps-hosting)** in the walkthrough because it has a
  **one-click *Hermes Agent* app** (Hermes comes pre-installed), but any provider works —
  see [SETUP.md](SETUP.md).
- **The LLM brain** is the only "smarts" you plug in. Point it at
  **[OpenRouter](https://openrouter.ai/)** and you can switch brains (DeepSeek, Claude, GPT,
  Gemini…) from one key without re-installing.

---

## Install (everything in your browser — no terminal of your own)

You stand up Hermes once, then **install the Shark profile first and configure everything
against it** — all from the **in-browser App terminal** (no SSH). **Order matters:** any
key, model, or Telegram channel you set *before* the Shark profile is active binds to
Hermes' **default** profile instead — which is the #1 setup failure (LLM key → the global
env the profile ignores → *"No LLM provider configured"*; Telegram → the wrong bot).

> **Fastest working path → [docs/FRIEND-SETUP.md](docs/FRIEND-SETUP.md).** That guide
> reflects the currently validated Hostinger / Hermes v0.17.0 setup, including two rough
> edges the steps below account for (the FILES page is download-only; the dashboard's
> "Restart Gateway" button can hang). Full step-by-step provisioning walkthrough:
> **[SETUP.md](SETUP.md)**.

1. **Stand up Hermes v0.17.0** on a small VPS — the always-on box that runs the agent:
   - **a. Provision the VPS.** On [Hostinger](https://www.hostinger.com/vps-hosting), choose
     the **one-click Hermes Agent** app so Hermes comes pre-installed. (Any provider works —
     on a plain Ubuntu box, install Hermes via the
     [Nous quickstart](https://hermes-agent.nousresearch.com/docs/).) *(SETUP.md Phase 1.)*
   - **b. Set an admin username + password** on the deploy form and **save them** — that's
     your dashboard login.
   - **c. Wait ~5 min** for provisioning; the box comes up with Hermes already running.
   - **d. Open the dashboard** (VPS Overview → **Open app**), sign in, and find the **App
     terminal** (a browser shell — no SSH). *(SETUP.md Phase 2.)*
   - **e. ⚠️ Don't set any keys or the model yet** — that comes *after* the Shark profile is
     active (step 2), or it binds to Hermes' **default** profile.

2. **Install AND activate the Shark profile — do this FIRST.** Open the Hermes app's **App
   terminal** (a browser shell — no SSH) and paste:
   ```
   hermes profile install github.com/logiqfish/shark-trading-agent -y
   hermes profile use shark-trading-agent
   ```
   Dashboard → **PROFILES** should now show `shark-trading-agent [active]`. It pulls the
   SOUL, the `shark` skill, and the cron, and generates the profile **`.env`**. **⚠️
   Everything below binds to the *active* profile — so it must come after this line.**

3. **Configure the active profile** (all of it binds to the profile you activated in step 2):
   - **a. Get your keys.** Alpaca **paper** key + secret from
     [app.alpaca.markets](https://app.alpaca.markets/) (switch to the **Paper** account);
     the LLM key from [openrouter.ai](https://openrouter.ai/) (it starts `sk-or-`).
   - **b. Put all three in the profile `.env` — via the App terminal.** The FILES page is
     **download-only**, so append them in the terminal (this *appends*, won't wipe anything):
     ```
     printf 'ALPACA_API_KEY=PKxxxx\nALPACA_SECRET_KEY=xxxx\nOPENROUTER_API_KEY=sk-or-xxxx\n' >> /opt/data/profiles/shark-trading-agent/.env
     ```
     _The LLM key goes in the profile `.env` **on purpose**: the GUI **KEYS** page can write
     it to the **global** env the profile doesn't read — the #1 cause of "No LLM provider
     configured" even though the model looks selected._
   - **c. Pick the model.** In **MODELS**, set the main model to **`deepseek/deepseek-v4-pro`**
     (or any OpenRouter model). This part *is* per-profile, so the GUI is fine here.

4. **(Optional) Telegram — for THIS profile.** In **CHANNELS**, connect Telegram (QR or bot
   token) and **enable it for the active `shark-trading-agent` profile** — not the default
   Hermes bot. Skip this if you only want headless cron.

5. **Restart to load everything.** The `.env` isn't hot-reloaded, so restart once now —
   dashboard **Restart Gateway**, or if it hangs, **Hostinger panel → Docker Manager**
   (restart the Hermes app, or Reboot VPS). One restart picks up all keys + the channel.

6. **Smoke-test it by hand.** In **CHAT** (or Telegram): *"Run the shark skill now for a
   single fire."* During market hours you'll see it read the regime, surface a candidate,
   run the debate, and — if it trades — place a broker-protected paper entry and a journal
   slip. Confirm the order in your Alpaca paper account.

7. **Enable the schedule.** The cron installs **disabled** on purpose. Turn it on in the
   **CRON** page (job `weekday-trading`, 10:00 / 13:00 / 15:00 ET, Mon–Fri). _If it isn't
   listed on the CRON page in your build, ask the bot in plain English to register it —
   "set up the weekday-trading cron"._ If you wired Telegram, send **`/sethome`** in the
   chat where you want the trade cards delivered.

8. **(Optional) Gut trades — the bot as your "second brain."** Separate from the scheduled
   scan, you can hand it a stock *you* picked and have it pressure-test your gut before any
   money moves. DM a plain directive with a **real symbol** (`TICKER` above is just a
   placeholder — use `NVDA`, `AAPL`, etc.). A sample exchange:

   > **You:** take NVDA
   >
   > **Bot:** 🦈 Shark brain on NVDA: conviction 71/100 · regime OK
   > If you override, I'd place: 12 sh @ ~$168.40 · stop $162.10 · target $181.00 (+2R) · 8%
   > Override and take it? (yes / no)
   >
   > **You:** yes

   It runs the bull/bear debate, sizes the trade through the **same risk kernel** as the
   scheduled scan, and shows exactly what it *would* place. **Nothing is bought until you
   reply `yes`** — reply `no` (or don't reply) and it places nothing. You can pin your own
   stop too: `take NVDA stop 162`.

**Updating:** `hermes profile update` re-pulls the SOUL/skill/cron. Your runtime state
(journal, theses, portfolio) is excluded from the distribution, so updates never wipe your
history.

> **Cost guard.** This is an always-on agent that calls the LLM on every fire. Set a hard
> spending cap on your LLM account first. It fires ~3×/day on weekday market hours only —
> but cap it anyway.

---

See also: [SETUP.md](SETUP.md) (full provisioning) · [DISCLAIMER.md](DISCLAIMER.md) ·
[LICENSE](LICENSE).
