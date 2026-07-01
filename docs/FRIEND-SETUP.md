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
Dashboard → **PROFILES** should now show `shark-trading-agent [active]`.

**2. LLM key** — dashboard → **KEYS** page → add your **OpenRouter** key. (It writes to
the active profile's `.env`.)

**3. Model** — dashboard → **PROFILES** → the profile's **⋮** menu → **CHANGE MODEL** (or
the **MODELS** page) → pick **`openrouter / deepseek/deepseek-v4-pro`** (or any OpenRouter
model). Without this the bot has no brain.

**4. Alpaca keys** — the KEYS page **won't** take these (it only does LLM/OAuth keys), so
add them in the **App terminal** (this *appends*, it won't wipe your OpenRouter key):
```
printf 'ALPACA_API_KEY=PKxxxx\nALPACA_SECRET_KEY=xxxx\n' >> /opt/data/profiles/shark-trading-agent/.env
```

**5. Telegram for THIS profile** — dashboard → **CHANNELS** → **Telegram** row →
**CONFIGURE** (connect your bot) → flip the **toggle to enabled**. ⚠️ **This is
per-profile** — see Trap #1.

**6. Restart — NOT the dashboard button.** The dashboard's **"Restart Gateway" button
hangs** (Trap #2). Instead restart the container from the **Hostinger panel** → **Docker
Manager** → restart the Hermes Agent app (or **Reboot VPS**). This loads all your keys +
connects Telegram.

**7. Set the home channel** — in the **Telegram chat** with the bot, send **`/sethome`**.
(The gateway must be up first — that's why this is after the restart.) Cron cards will
deliver to this chat.

**8. Schedule the trading scan** — just **ask the bot in plain English** in Telegram:
> *"set up the weekday-trading cron"*

It'll register the shipped `weekday-trading` job (10am/1pm/3pm ET, weekdays). ⚠️ **`/cron`
is NOT a command** — type it as a normal request, no leading slash (Trap #3).

**9. Verify** — ask the bot **"what's my portfolio status"** → a live Alpaca card (equity,
positions) means you're done. The scan then fires on schedule and pushes cards here.

---

## The traps (read these)

**Trap #1 — Channels are per-profile.** When the box first boots, the *default* Hermes bot
answers Telegram. Your **shark-trading-agent** profile has its **own** Telegram that starts
**Disabled** (CHANNELS page). So after install the bot can go silent — you must enable
Telegram *for this profile* (step 5). The first bot working is a red herring.

**Trap #2 — The dashboard "Restart Gateway" button hangs.** In this container it sticks at
"Hermes Gateway Starting…" and never finishes. **Don't use it.** Restart from the
**Hostinger panel** (Docker Manager → restart app, or Reboot VPS) instead — that always
works.

**Trap #3 — Cron isn't in the dashboard.** The **Blueprints** tab shows Hermes' generic
templates (briefings, reminders), **not** the shark scan. And **`/cron` is not a slash
command**. To schedule it, **ask the bot in plain English** ("set up the weekday-trading
cron") — it has a cron tool and will do it.

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
