# Shark Trading Agent — Friend Setup (no SSH, no operator)

A from-scratch setup a **non-technical friend can do entirely themselves** — using only:
the **Hostinger panel**, the **in-browser App terminal**, the **Hermes dashboard**, and
the **Telegram chat**. **No SSH. No operator.** Validated end-to-end on a clean box
2026-06-26.

> Read the **two traps** at the bottom first — they're the only things that will stump
> you, and they're easy once you know them.

## What you need
- A Hostinger VPS with the **Hermes Agent** app deployed (gives you the dashboard + an
  in-browser App terminal — you never need real SSH).
- **2 keys:** Alpaca **paper** key + secret (app.alpaca.markets → Paper account → API
  Keys), and **one LLM key** (OpenRouter by default).

## Setup — in order

Do **all** of steps 1–6 before the single restart, so one restart loads everything.

**1. Install the profile** — open the **App terminal** (Hostinger app card → "App
terminal", or dashboard) and run **one line**:
```
hermes profile install github.com/logiqfish/shark-trading-agent -y
hermes profile use shark-trading-agent
```
Dashboard → **PROFILES** should now show `shark-trading-agent [active]`. **Do this first**
— every key, model, and Telegram channel you set below binds to whichever profile is
**active**, so if you configure them before this the bot uses Hermes' default profile
instead (LLM key in the wrong env, Telegram on the wrong bot).

**2. LLM key** — add your **OpenRouter** key (starts `sk-or-`) to the profile `.env` in the
**App terminal** — *not* the KEYS page:
```
printf 'OPENROUTER_API_KEY=sk-or-xxxx\n' >> /opt/data/profiles/shark-trading-agent/.env
```
⚠️ The dashboard **KEYS** page can write the key to the **global** `/opt/data/.env`, which
the profile does **not** read — so the bot says *"No LLM provider configured"* even though
you set it and can pick the model. The profile `.env` is the location that actually works.

**3. Model** — dashboard → **PROFILES** → the profile's **⋮** menu → **CHANGE MODEL** (or
the **MODELS** page) → pick **`openrouter / deepseek/deepseek-v4-pro`** (or any OpenRouter
model). Without this the bot has no brain.

**4. Alpaca keys** — the KEYS page **won't** take these (it only does LLM/OAuth keys), so
add them in the **App terminal** (this *appends*, it won't wipe your OpenRouter key):
```
printf 'ALPACA_API_KEY=PKxxxx\nALPACA_SECRET_KEY=xxxx\nALPACA_BASE_URL=https://paper-api.alpaca.markets\n' >> /opt/data/profiles/shark-trading-agent/.env
```

**5. Telegram for THIS profile** — dashboard → **CHANNELS** → **Telegram** row →
**CONFIGURE** (connect your bot) → flip the **toggle to enabled**. ⚠️ **This is
per-profile** — see Trap #1.

**6. Restart the container, then START the gateway.** Restart the container from the
**Hostinger panel** → **Docker Manager** → restart the Hermes Agent app (loads your keys).
Then, in the **App terminal**, start the gateway — **nothing runs without it** (no chat, no
cron):
```
nohup hermes gateway run > /opt/data/gateway.log 2>&1 &
```
⚠️ Don't use the dashboard's "Restart Gateway" button (Trap #2). After this, the dashboard
should read **Gateway Status: Running**.

**7. Set the home channel — `/sethome` (don't skip).** In the **Telegram chat** with the
bot, send **`/sethome`**. (The gateway must be up first — that's why this is after step 6.)
This is where cron cards deliver. **Without it the bot still chats but scheduled fires have
nowhere to go, so no cards ever arrive on their own** — the #1 reason a working bot looks
dead. Reinstalled or renamed the profile? Send `/sethome` again — it doesn't carry over.

**8. Schedule the trading scan (App terminal).** The CRON page starts **empty** — the
shipped job isn't auto-registered. Register it with the right hours (UTC — there's no
timezone flag, so `0 14,17,19` = 10am/1pm/3pm ET during EDT; winter/EST = `0 15,18,20`):
```
hermes cron create '0 14,17,19 * * 1-5' 'Run the Shark trading routine for this fire. Follow the `shark` skill procedure exactly, in order. Emit only the final one-line status card summarizing the fire (trade or no-trade). Always emit the card and never respond with [SILENT], so every fire posts a status card.' --name weekday-trading --skill shark --deliver local
```
Verify: `hermes cron list` → `Next run …T14:00:00+00:00`. _(Easier but less precise: ask the
bot "set up the weekday-trading cron" — but it may pick the wrong timezone; the CLI is
reliable. `/cron` is not a slash command — Trap #3.)_

**9. Verify** — ask the bot **"what's my portfolio status"** → a live Alpaca card (equity,
positions) means you're done. The scan then fires on schedule and pushes cards here.

---

## The traps (read these)

**Trap #1 — Channels are per-profile.** When the box first boots, the *default* Hermes bot
answers Telegram. Your **shark-trading-agent** profile has its **own** Telegram that starts
**Disabled** (CHANNELS page). So after install the bot can go silent — you must enable
Telegram *for this profile* (step 5). The first bot working is a red herring.

**Trap #2 — the dashboard "Restart Gateway" button doesn't persist.** It runs the gateway
in the *foreground*, sticks at "Hermes Gateway Starting…", and dies when you leave the page
— so the status falsely reads **Stopped** and cron never fires. **Start the gateway from the
App terminal instead:** `nohup hermes gateway run > /opt/data/gateway.log 2>&1 &` (inside
Docker `hermes gateway install` is a no-op — the container is the service manager). This
persists across closing the terminal, but **re-run it after any container restart**.

**Trap #3 — the shipped cron may not show up where you expect.** It lives on the **CRON**
page (enable it there if it's listed) — but the **Blueprints** tab shows only Hermes'
generic templates (briefings, reminders), **not** the shark scan, and **`/cron` is not a
slash command**. If you don't see the `weekday-trading` job on the CRON page, the reliable
non-technical path is to **ask the bot in plain English** ("set up the weekday-trading
cron") — it has a cron tool and will register it.

**Also good to know:**
- The bot is **brainless until steps 2+3 are done** — before that it replies *"Provider
  authentication failed."* That's expected, not broken.
- The **FILES** page is **download-only** — you can't edit `.env` there; use the App
  terminal.
- Keys live in `/opt/data/profiles/shark-trading-agent/.env`.

## Known rough edges (kit / Nous fixes that would remove the traps)
These are the changes that would make this truly one-click for a friend:
1. **Fix the dashboard gateway-restart** so it doesn't hang (removes Trap #2 — the worst).
2. **Surface the shipped cron as an enable-able Blueprint** (removes Trap #3).
3. **Let the KEYS page accept Alpaca** (custom env vars), so no App terminal for keys.
4. **A first-run message** in chat pointing to per-profile Telegram + the key/model steps.

Until those land, this runbook is the reliable path — and it needs **no SSH**.
