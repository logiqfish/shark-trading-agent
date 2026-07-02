# Shark Trading Agent — Setup Runbook (validated end-to-end 2026-07-01)

A concise, **reproducible** happy-path for the skinny Hermes paper-trading agent, distilled
from a full from-scratch install on a Hostinger VPS (Hermes Agent app, **v0.17.0**). For the
verbose walkthrough with screenshots see `SETUP.md`; the friendly no-jargon version is
`FRIEND-SETUP.md`. Do the steps **in order** — most failures come from doing them out of order.

**Outcome when done:** the bot answers "what's my portfolio status" with a live Alpaca paper
account, and the `weekday-trading` cron fires the shark routine on schedule.

## What you provide
- **Alpaca paper** key + secret (app.alpaca.markets → **Paper** account → API keys).
- **One LLM key** — OpenRouter by default (`sk-or-…`), model `deepseek/deepseek-v4-pro`.
- A Hostinger VPS with the **Hermes Agent** app running (gives the dashboard + in-browser
  **App terminal** — no SSH needed).

## Steps (in order)

1. **Install AND activate the profile — FIRST.** One CLI line in the **App terminal**.
   Everything you configure after this binds to the **active** profile, so this must come
   before any keys/model/Telegram (otherwise they attach to Hermes' *default* profile):
   ```
   hermes profile install github.com/logiqfish/shark-trading-agent -y
   hermes profile use shark-trading-agent
   ```
   Confirm: dashboard → **PROFILES** shows `shark-trading-agent [active]`.

2. **Put ALL keys in the _profile_ `.env`** — one command, in the App terminal. This is the
   load-bearing step (`ALPACA_BASE_URL` included — the agent refuses to trade without it):
   ```
   printf 'ALPACA_API_KEY=PKxxxx\nALPACA_SECRET_KEY=xxxx\nALPACA_BASE_URL=https://paper-api.alpaca.markets\nOPENROUTER_API_KEY=sk-or-v1-xxxx\n' >> /opt/data/profiles/shark-trading-agent/.env
   ```
   - ⚠️ **Must be the _profile_ `.env`** (`/opt/data/profiles/shark-trading-agent/.env`),
     **not** the global `/opt/data/.env`. The dashboard **KEYS/MODELS** page writes the LLM
     key to the *global* env, which the profile does **not** read → the bot says *"No LLM
     provider configured"* even though the model is selected. The App-terminal `.env` above
     is the location that actually works.
   - The **FILES** page is **download-only** — you can't edit `.env` in-browser.
   - Re-running the `printf` just appends duplicate lines (harmless — last value wins). To
     tidy: `cd /opt/data/profiles/shark-trading-agent && cp .env .env.bak && tac .env.bak | awk -F= '!seen[$1]++' | tac > .env`.

3. **Pick the main model.** Dashboard → **MODELS** → set **MAIN MODEL** to
   `deepseek/deepseek-v4-pro` (or any OpenRouter model). Model selection *is* per-profile, so
   the GUI is fine here — it's only the *key* that must go in the `.env` (step 2).

4. **(Optional) Telegram — for THIS profile.** Dashboard → **CHANNELS** → connect Telegram
   (QR or bot token) and **enable it for the active `shark-trading-agent` profile** (not the
   default bot). Skip if you only want headless cron.

5. **Start the gateway** — nothing runs (no chat, no cron) without a running gateway. Run
   this **inside the container** — the App-terminal button drops you in (prompt reads
   `root@<id>:/opt/hermes#`). ⚠️ If your prompt shows the **host** instead (`root@srv…`),
   `hermes` and `/opt/data` don't exist there — enter the container first:
   ```
   docker exec -it $(docker ps -qf name=hermes) bash
   ```
   Then:
   ```
   nohup hermes gateway run > /opt/data/gateway.log 2>&1 &
   ```
   - ⚠️ Inside Docker `hermes gateway install` is a **no-op** ("the container is your service
     manager"), and the dashboard **"Restart Gateway" button** only runs the gateway in the
     *foreground* — it hangs at "Hermes Gateway Starting…" and the status then falsely reads
     **Stopped**. Use `hermes gateway run`, not the button.
   - `nohup … &` survives closing the terminal, but **re-run it after a full container
     restart** (Docker Manager / reboot). If a gateway is already running with stale config,
     restart the container first, then run the command.
   - Confirm **Gateway Status: Running** in the dashboard (and `hermes cron list` no longer
     warns *"Gateway is not running"*).

6. **Register the cron (CLI).** The shipped `cron/weekday-trading.json` is a **template — NOT
   auto-registered** (the CRON page starts empty; this build has no `--file`/import). Register
   it with the real prompt and a **UTC** schedule:
   ```
   hermes cron create '0 14,17,19 * * 1-5' 'Run the Shark trading routine for this fire. Follow the `shark` skill procedure exactly, in order. Emit only the final one-line status card summarizing the fire (trade or no-trade). Always emit the card and never respond with [SILENT], so every fire posts a status card.' --name weekday-trading --skill shark --deliver local
   ```
   - **No `--timezone` flag** — the schedule runs on the container clock (**UTC**).
     `0 14,17,19` = 10 AM / 1 PM / 3 PM ET during **EDT**; in **EST** use `0 15,18,20`.
     Verify: `hermes cron list` → `Next run …T14:00:00+00:00` (= 10 AM ET).
   - `--deliver local` writes cards to LOGS/SESSIONS (headless). For Telegram cards: **send
     `/sethome` in the target chat** (sets the home channel Hermes delivers cron results to),
     then recreate the job with `--deliver telegram`. **`/sethome` is the step people miss:**
     the bot still chats without it, but scheduled fires have nowhere to deliver, so no cards
     arrive on their own. The home channel is **per profile** — reinstall/rename → resend it.

7. **Verify.**
   - Dashboard **CHAT** (or Telegram, if wired): *"what's my portfolio status"* → a live
     Alpaca card (equity / cash / positions) means keys + brain + gateway all work.
   - Manual fire: `hermes cron run <job-id>` (id from `hermes cron list`) → watch **LOGS** for
     `cron.scheduler: Job '<id>': ... completed successfully`. A healthy fire runs ~8 min.

## Known issues on this Hermes v0.17.0 build (real friction, all handled above)
1. **LLM key lands in the wrong env file.** The dashboard KEYS/MODELS page writes it to the
   *global* `/opt/data/.env`, which the profile ignores → "No LLM provider configured." Fix:
   put the key in the **profile** `.env` (step 2).
2. **`ALPACA_BASE_URL` is not auto-injected.** The manifest declares a default, but a
   hand-written profile `.env` doesn't get it — set it explicitly (step 2).
3. **Gateway is not auto-started / doesn't persist.** You must `hermes gateway run` (step 5),
   and re-run it after a container restart. The dashboard button runs it in the foreground
   (hangs; status false-reads Stopped).
4. **Cron is not auto-registered and has no per-job timezone.** Register via CLI in UTC
   (step 6). The shipped JSON's `timezone` field can't be applied through `hermes cron create`.
5. **FILES page is download-only** — all `.env` edits go through the App terminal.

## Gotchas worth remembering
- Configure in order: **install+activate profile → keys/model/Telegram → gateway → cron.**
  Out of order, config binds to the default profile.
- `.env` is **not** hot-reloaded at the gateway level, but the agent reloads it per run — so
  adding a key is usually picked up on the next message; restart the gateway if not.
- Run container commands as the **`hermes`** user where possible; root-owned writes into
  `/opt/data` can break config.
