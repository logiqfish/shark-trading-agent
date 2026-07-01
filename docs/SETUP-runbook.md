# Shark Trading Agent — Setup Runbook (validated 2026-06-26)

A concise, **reproducible** setup for the skinny Hermes paper-trading agent, distilled
from a real end-to-end install on a Hostinger VPS (Hermes Agent app, v0.17.0). For the
verbose maintainer walkthrough see `SETUP.md`; this file is the "happy path" plus the
sharp edges we actually hit.

**Outcome when done:** the bot answers "what's my portfolio status" with a live Alpaca
paper account, and the `weekday-trading` cron fires the shark routine headless
(no messaging platform required).

## What the friend provides

- **2 keys:** Alpaca **paper** key + secret, and **one LLM key** (OpenRouter by default →
  `deepseek/deepseek-v4-pro`).
- A Hostinger VPS with the **Hermes Agent** app running (gives the in-browser dashboard +
  App terminal).

## Steps

1. **Install the profile** (one CLI line in the **App terminal**):
   ```
   hermes profile install github.com/logiqfish/shark-trading-agent -y
   hermes profile use shark-trading-agent
   ```
   Confirm it's active: dashboard → **PROFILES** shows `shark-trading-agent@x.y.z [active]`.

2. **Put ALL keys in the _profile_ `.env`** — this is the load-bearing step:
   `/opt/data/profiles/shark-trading-agent/.env`
   ```
   ALPACA_API_KEY=...
   ALPACA_SECRET_KEY=...
   ALPACA_BASE_URL=https://paper-api.alpaca.markets
   OPENROUTER_API_KEY=sk-or-v1-...
   ```
   - ⚠️ **Must be the _profile_ `.env`, not the global `/opt/data/env`.** Hermes reads the
     active profile's `.env` for keys; a key in the global env is silently ignored
     (`hermes doctor` will say "No API key found" even though a key exists elsewhere).
   - Edit it from the **App terminal** (e.g. `nano`/append). The dashboard **FILES** page
     is **download-only** — you cannot edit `.env` in-browser there (see Known Issues).

3. **Register the cron (CLI).** The shipped `cron/weekday-trading.json` is a **template — it
   is NOT auto-registered** (the CRON page starts empty; this build has no `--file`/import).
   Register it with the real prompt and a UTC schedule:
   ```
   hermes cron create '0 14,17,19 * * 1-5' 'Run the Shark trading routine for this fire. Follow the `shark` skill procedure exactly, in order. Emit only the final one-line status card summarizing the fire (trade or no-trade). Always emit the card and never respond with [SILENT], so every fire posts a status card.' --name weekday-trading --skill shark --deliver local
   ```
   - `--deliver local` keeps it **headless** — the gateway runs the scheduler with **zero
     messaging platforms**. For push cards use `--deliver telegram` (after `/sethome`).
   - **No `--timezone` flag** — `hermes cron create` runs the schedule on the container
     clock (**UTC**). `0 14,17,19` = 10 AM / 1 PM / 3 PM ET during **EDT**; in **EST** use
     `0 15,18,20`. Verify: `hermes cron list` → `Next run …T14:00:00+00:00` (= 10 AM ET).

4. **Load the `.env`, then RUN the gateway.** `.env` is **not** hot-reloaded, so restart the
   container (Hostinger → Docker Manager) after any key change. Then **start the gateway** —
   cron won't fire without it (`hermes cron list` warns *"Gateway is not running"*):
   ```
   nohup hermes gateway run > /opt/data/gateway.log 2>&1 &
   ```
   Inside Docker `hermes gateway install` is a no-op ("the container is your service
   manager"), and the dashboard **Restart Gateway** button only runs it in the *foreground*
   (hangs at "Hermes Gateway Starting…"; status then falsely reads **Stopped**).
   `nohup … &` survives closing the terminal — but **re-run it after a container restart**.
   Confirm **Gateway Status: Running** in the dashboard.

5. **Verify:**
   - Telegram: ask the bot **"what's my portfolio status"** → should return a live Alpaca
     card (equity / cash / positions).
   - Or a manual fire: `hermes cron run <job-id>` → expect `Ran now: succeeded` and **no**
     `request_dump_cron_*` error dump written. A healthy fire runs ~8 min (full routine).

## Known issues (kit bugs to smooth out — found 2026-06-26)

1. **Keys can land in the wrong env file.** Setting the LLM key via the dashboard MODELS
   page wrote it to the **global** `/opt/data/env`, which Hermes does **not** read for the
   profile → "Provider authentication failed." Workaround: put keys in the **profile**
   `.env` via the App terminal. *Fix: make the GUI key-setting target the active profile's
   `.env`.*
2. **FILES page is download-only.** A friend cannot edit `.env` in the dashboard, so
   "configure via GUI" is incomplete — key edits require the App terminal. *Fix: add
   in-browser editing, or document the terminal step prominently.*
3. **Cron shipped `deliver: telegram`.** Wrong for a zero-messaging kit — a friend with no
   Telegram would get delivery errors. *Fixed 2026-06-26: shipped json now `deliver: local`.*

## Gotchas worth remembering

- Run container commands as the **`hermes`** user; root-owned writes into `/opt/data`
  silently break config.
- The gateway is a dashboard-managed TUI process; restart via the dashboard **Restart
  Gateway** button, not an ad-hoc `hermes gateway restart` over SSH (no systemd in the
  container → it hangs / dies on SIGHUP). **If the dashboard button itself hangs** (seen on
  some builds), restart the container from the **Hostinger panel → Docker Manager**
  (or Reboot VPS) — that is the reliable fallback.
