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
   OPENROUTER_API_KEY=sk-or-v1-...
   ```
   - ⚠️ **Must be the _profile_ `.env`, not the global `/opt/data/env`.** Hermes reads the
     active profile's `.env` for keys; a key in the global env is silently ignored
     (`hermes doctor` will say "No API key found" even though a key exists elsewhere).
   - Edit it from the **App terminal** (e.g. `nano`/append). The dashboard **FILES** page
     is **download-only** — you cannot edit `.env` in-browser there (see Known Issues).

3. **Enable the cron.** The kit ships `cron/weekday-trading.json` (disabled by default,
   `deliver: local`, schedule `0 10,13,15 * * 1-5` America/New_York). Enable it on the
   dashboard **CRON** page, or via CLI:
   ```
   hermes cron create '0 10,13,15 * * 1-5' '<prompt from weekday-trading.json>' \
     --name weekday-trading --skill shark --deliver local
   ```
   - `--deliver local` keeps it **headless** — the gateway runs the scheduler with **zero
     messaging platforms** (confirmed; the "No messaging platforms enabled" log line is a
     non-fatal warning, the gateway continues for cron). Telegram is optional, for push.
   - The CLI has **no `--timezone` flag**; if creating via CLI, convert to UTC
     (10/13/15 ET → `0 14,17,19` UTC in EDT). The shipped **JSON keeps the tz field**, so
     enabling the shipped job is the DST-safe path.

4. **Restart to load the `.env`** — `.env` is **not** hot-reloaded, so a restart is
   required after any key change. Use the dashboard **Restart Gateway** button (bottom-left);
   **if it hangs**, restart the container from the **Hostinger panel → Docker Manager**
   (or Reboot VPS) instead — that always works (see Gotchas).

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
