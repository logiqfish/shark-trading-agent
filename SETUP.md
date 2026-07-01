# Shark Trading Agent — Setup Guide

A paper-trading bot you run on your own small server. Two keys, no shared infrastructure,
nothing of ours touching your box. When it's done it watches the market a few times a day,
debates each idea bull-vs-bear, and places disciplined paper trades — and you can DM it a
ticker to get its read.

## What you need before you start
- A small Linux VPS (see Phase 1 for size) — ~$5–10/mo.
- An **Alpaca paper** account → API key + secret. (app.alpaca.markets → Paper account.)
- A **DeepSeek** API key (platform.deepseek.com). **Set a hard spending cap on it** — an
  always-on agent can run up LLM bills.
- (Optional) A **Telegram** bot token (from @BotFather) if you want to chat with it / get
  trade cards on your phone. Free; not required for it to trade.
- ~30–45 minutes.

> Nothing here ever asks you to send us a key or give us access. It all runs on your box.

---

## Phase 1 — Provision the VPS

**Goal:** a fresh Ubuntu server you can SSH into.

> **Hostinger is only the example here, not a requirement.** This walkthrough uses
> **Hostinger** because its one-click *Hermes Agent* app is the fastest way to a running
> bot — but **any VPS provider works**: DigitalOcean, Hetzner, Vultr, Linode, AWS/GCP, or
> a spare box. All the kit actually needs is **an Ubuntu 24.04 server you can SSH into as
> root**. On non-Hostinger hosts you provision a plain Ubuntu box and install Hermes
> manually (the "Portable" path below); everything from Phase 3 on is identical.

**Quick reference for the box:**
- **Provider:** Hostinger KVM VPS (example — any host works).
- **Plan / size:** KVM 1 (1 vCPU / 4 GB) is enough; KVM 2 (2 vCPU / 8 GB) is a comfortable known-good config (see step 5).
- **Region:** closest to you / your market (US for US-market trading).
- **OS image:** Ubuntu 24.04 LTS — or, on Hostinger, the one-click **Hermes Agent** app.
- **Access:** root password or SSH key.

> **Two paths to a running Hermes:**
> - **Primary (easiest — used in this walkthrough):** on Hostinger, the VPS "what to
>   install" step has a one-click **Hermes Agent** Docker app — Hermes comes
>   pre-installed and running. Phases 1+2 collapse into this single choice.
> - **Portable (any provider):** a bare Ubuntu 24.04 box + a manual Hermes install
>   (follow Nous Research's Hermes quickstart), then continue from Phase 3. Works on
>   DigitalOcean / Hetzner / Vultr / any host.

### Steps

1. **Open the VPS section.** In hPanel (`hpanel.hostinger.com`), left sidebar →
   **Dev tools → VPS**. You'll see your VPS list.
   _screenshot: `docs/setup/images/p1-01-vps-list.png` (redacted)_
2. **Start a new VPS.** Click **+ Get VPS** (top right) → in the dropdown choose
   **KVM VPS** ("Purchase new VPS with KVM technology"). _(Not "Game Panel VPS.")_
   _screenshot: `docs/setup/images/p1-02-get-vps-kvm.png` (redacted)_
3. **Choose a server location.** Pick the region closest to you / your market. For
   US-market stock trading, **United States** keeps latency to Alpaca low (the picker
   shows a "best latency" estimate). Click **Next**.
   _screenshot: `docs/setup/images/p1-03-location.png` (redacted)_
4. **Choose what to install → the Hermes Agent app.** On the "Choose what to install"
   screen, search **`Hermes`** and pick the **`Hermes Agent`** Docker application
   (the autonomous agent — **not** `Hermes WebUI`, which is just a web console, and
   **not** `Hermes Workspace`). A detail modal opens ("Hermes Agent — Installed using
   Docker", by Nous Research, with **Documentation** + **Quick start** links worth
   bookmarking for Phases 3–4) → click **Select**. This installs Hermes pre-configured;
   you don't install it by hand. _(Portable alternative: choose **Plain OS → Ubuntu
   24.04 LTS** instead and install Hermes manually via the Nous Hermes quickstart.)_
   _screenshots: `docs/setup/images/p1-04a-choose-hermes-agent.png`,
   `p1-04b-hermes-agent-modal.png` (redacted)_
5. **Pick a plan (KVM tier).** **KVM 1** (1 vCPU / 4 GB / 50 GB, ~$6.49/mo intro) is
   enough on paper: the LLM runs remotely (DeepSeek over the API — nothing heavy on the
   box), the skills are stdlib-only, and it fires just ~3×/day. **KVM 2** (2 vCPU / 8 GB)
   is a comfortable known-good Hermes config if you'd rather not tune. You can upgrade in
   one click anytime, so a
   friend can safely start on KVM 1 and bump up if `free -h` / `docker stats` shows
   swapping on first run.
   _screenshot: `docs/setup/images/p1-05-plan.png` (redacted)_
6. **Pick a billing term + check out.** A "Select plan duration" modal appears: longer
   terms are much cheaper per month, but the per-month price **jumps at renewal** (e.g.
   the monthly term renews higher than the 24-month intro rate). **For a test, pick
   1 month** — don't lock into 24 months to try it out. Confirm the payment method →
   **Complete payment**.
   _screenshot: `docs/setup/images/p1-06-duration-checkout.png` (redacted)_
7. **Hermes Agent configuration (deploy template).** After checkout, Hostinger shows a
   **"Hermes Agent configuration"** form before it deploys:
   - **ADMIN_USERNAME / ADMIN_PASSWORD** (required) — your **Hermes dashboard** login.
     Set them and **save the password** (no easy recovery).
   - **Nexos API Key** (optional) — an LLM-brain key for Hostinger's built-in **Nexos**
     gateway (not DeepSeek). **Leave empty** — we configure DeepSeek as the brain in
     Phase 3 to keep the kit's "Alpaca + DeepSeek, two keys" promise. _(Fallback: if
     wiring DeepSeek post-deploy is fiddly, a Nexos key gives a quick working brain —
     the kit is brand-agnostic and runs on any model — then swap to DeepSeek later.)_
   - **Oxylabs AI Studio API Key** (optional) — web-browsing/scraping. **Leave empty.**
     The kit's data-fence forbids browsing for trades, so the bot never calls it.
   - Click **Deploy**.
   _screenshot: `docs/setup/images/p1-07-hermes-agent-config.png` (redacted)_
8. **Wait for provisioning (~5 min).** After Deploy you get a **"Setting up your VPS"**
   screen ("takes about 5 minutes… you'll get an email once it's ready"). You can leave
   the page. The box comes up with **Hermes already installed and running** (no manual
   install). Handy links shown here: _Getting started with Hermes Agent_ and the
   _Hermes Agent documentation_.
   _screenshot: `docs/setup/images/p1-08-setting-up.png`_
9. **Open the VPS Overview** (hPanel → VPS → your server). When it's ready you'll see
   **"My Applications → Hermes Agent — 1 container — Running"** and, lower down, the
   server's access details. Grab/confirm:
   - **IP** (`<your-server-ip>`), **SSH username** `root`, and the **root password**
     (use the **Change** link to set one if you'll SSH in — needed for Phase 5, unless
     you use the web **App terminal** instead).
   - The Hermes app card has **Open app** (the dashboard), **App terminal** (web shell
     into the container), and **Documentation**.
   _screenshot: `docs/setup/images/p1-09-vps-overview.png` (redacted)_

**End of Phase 1** — you have a **running Hermes** on your own VPS (the app installed it
for you; nothing to install by hand).

---

## Phase 2 — Reach Hermes

**Goal:** confirm Hermes is up and get into it. _(With the Hostinger Hermes Agent app this
is already done — it's "Running" on the Overview. Three ways in:)_
- **Open app** → the **Hermes dashboard** (web UI; log in with the admin username/password
  from Phase 1 step 7). This is where the brain + Telegram get configured.
- **App terminal** → a web shell straight into the Hermes container (no SSH setup needed).
- **SSH** → `ssh root@<your-server-ip>` to the host, then `docker exec` into the container
  (used in Phase 5 to place the kit workspace).

---

## Phase 3 — Configure the LLM (use any provider you like)

> **⚠️ ORDER MATTERS — install the Shark profile (Phase 5) FIRST, then do this phase and
> Phase 4 against the *active* profile.** Keys, model, and Telegram all bind to whichever
> profile is **active**; set them before `hermes profile use shark-trading-agent` and they
> attach to Hermes' **default** profile instead — the #1 setup failure. Concretely:
> - **Put the LLM key in the profile `.env` via the App terminal**, *not* the KEYS page:
>   `printf 'OPENROUTER_API_KEY=sk-or-xxxx\n' >> /opt/data/profiles/shark-trading-agent/.env`.
>   The KEYS/MODELS GUI can write it to the **global** `/opt/data/.env`, which the profile
>   does **not** read → the bot reports *"No LLM provider configured"* even though the model
>   is selected. (You can still use MODELS to *pick* the model — that part is per-profile.)
> - Then set Alpaca keys (Phase 5) and Telegram (Phase 4) the same way, and do **one**
>   restart after everything. The KEYS-page steps below still work for providers whose keys
>   land in the profile env, but the terminal method is the reliable path.

**Goal:** give Hermes a single brain. **Any LLM works** — the KEYS page supports ~28
providers (Anthropic/Claude, DeepSeek, Gemini, Kimi/Moonshot, OpenAI, OpenRouter, and
more). The kit **hardcodes no model**, so pick whichever you have a key for and can
afford. **DeepSeek is only our suggested default** (strong reasoning, low cost) — not a
requirement. Whatever you choose, the risk gate stays fail-safe to no-trade if the model
is unreachable.

**Reaching the dashboard:** click **Open app** on the VPS Overview → the Hermes Agent
sign-in (Nous Research) → log in with the **admin username/password** from Phase 1
step 7. The dashboard (this guide is written against **v0.17.0**) has a left nav with
`CHAT · SESSIONS · FILES · MODELS · LOGS · CRON · SKILLS · PLUGINS · MCP · CHANNELS ·
WEBHOOKS · PAIRING · PROFILES · CONFIG · KEYS`, and a **Gateway Status** indicator at
the bottom-left (it starts **Off** — we turn it on after configuring).
_screenshots: `docs/setup/images/p3-01-signin.png`, `p3-02-dashboard.png`_

Until a brain is configured, **CHAT** shows **"Setup Required — Hermes needs a model
provider"** and the right panel reads **"agent init failed: No inference provider
configured."** Two things fix it: a **provider key** (KEYS) **and** a **selected model**
(MODELS).

**Steps:**
1. **KEYS → set the provider key for whichever LLM you chose.** The KEYS page lists ~28
   providers (Anthropic, DeepSeek, Gemini, Kimi/Moonshot, OpenAI, OpenRouter, …) with an
   "X of 28 configured" counter. Expand **your** provider and click **Set**. Common picks:
   - **DeepSeek** (platform.deepseek.com key) → the "Alpaca + an LLM = two keys" default;
     strong reasoning, low cost. _Recommended if you have no preference._
   - **Anthropic / OpenAI / Gemini** — any works; set your own provider key here, then pick
     the model in MODELS (step 2).
   - **OpenRouter** (your own OpenRouter key) → one key, hundreds of models. Note its field
     is labeled "for vision, web scraping helpers, and MoA," so after setting it, confirm in
     MODELS that an OpenRouter-routed model is actually selectable as the **main** brain.
   _screenshot: `docs/setup/images/p3-03-keys.png` (redacted — keys are masked as
   `sk-…last4`, but crop anyway)_
2. **MODELS → set the MAIN MODEL.** The MODELS page has **MODEL SETTINGS** with a
   **MAIN MODEL** (starts `(unset)`) and **AUXILIARY TASKS** (11 helper tasks). Click
   **CHANGE** on MAIN MODEL and pick **your** model — that's the agent's brain.
   **Leave AUXILIARY TASKS on "all auto"** (they're vision/compression/web-extract
   helpers; the kit's data-fence means it never uses them). If the picker shows no
   working model, make sure that provider's key is set in KEYS and retry.
   _screenshot: `docs/setup/images/p3-04-models.png`_

   In the **SET MAIN MODEL** picker, the provider with your key lists its models. Pick the
   one you want and click **Switch** (saves to `config.yaml`). **Any capable model works;**
   as a cost/quality guide, the DeepSeek family is a solid default:
   - **`deepseek/deepseek-v4-pro`** — strongest reasoning; good for real trading decisions.
   - **`deepseek/deepseek-v4-flash`** — cheaper/faster; a good cost default given the
     spending-cap warning.
   - Prefer **Claude, Gemini, GPT, Kimi**, etc.? Pick that instead — the kit hardcodes no model.
   _screenshot: `docs/setup/images/p3-05-set-main-model.png`_
   After **Switch**, the MODELS page shows e.g. `MAIN MODEL: openrouter ·
   deepseek/deepseek-v4-pro`.
3. **Restart Gateway + smoke-test the brain.** Hit **Restart Gateway** (bottom-left;
   gateway starts **Off**) — the "agent init failed / Setup Required" clears and
   **Gateway Status → On**. Then in **CHAT**, send a quick "hi" and confirm the model
   replies. That verifies the brain is wired end-to-end before configuring trading.
   _screenshot: `docs/setup/images/p3-06-gateway-on-chat.png`_

**End of Phase 3** — Hermes has a working brain (whichever model you picked).

---

## Phase 4 — Configure Telegram (optional)

**Goal:** chat with the bot / receive its output on your phone. Also enables the
**discretionary "take TICKER"** gut-trade flow (you DM the bot a ticker).

**Steps:**
1. **Create a fresh Telegram bot.** In Telegram, message **@BotFather** → `/newbot` →
   name it → get the **bot token**. **Use a NEW bot — do not reuse another agent's bot
   token:** a token can only be polled by one instance at a time, so two agents on one
   bot fight over updates and both break.
2. **CHANNELS → Telegram.** The CHANNELS page lists Telegram (and Discord/Slack/Matrix/
   WhatsApp/Signal…), each Disabled by default; creds are written to **`/opt/data/.env`**.
   Two ways to connect Telegram — pick one:
   - **SET UP WITH QR (recommended — quickest *and* gives a real bot):** scan the QR with
     your phone's Telegram. It hands off to Nous's **`NousHostedHermesBot`**, which
     creates a **brand-new, dedicated Telegram bot for you** (e.g.
     `@hermes_…_bot`, named "Hermes Agent") via BotFather automation — a clean `@bot`
     identity, **not** your personal account. Tap **Start** in the new bot chat.
   - **CONFIGURE → bot token:** paste a fresh **@BotFather** token manually (don't reuse
     another agent's token — one bot can only be polled by one instance).
   Then flip the channel **toggle to enabled**. _(Verified live 2026-06-24: the QR path
   created the bot and connected on the first scan; the bot replied via deepseek-v4-pro.)_
3. **Restart Gateway, then Test.** The gateway is **Off** by default ("Configure channels
   here, then start the gateway"). After enabling Telegram, hit **Restart Gateway**
   (bottom-left) — it connects each enabled channel on restart — then **Test**. _(If the
   dashboard button hangs, restart the container from the Hostinger panel → Docker Manager
   instead — see Phase 5.)_
4. **Set the home channel: `/sethome`.** The gateway must be up first — that's why this is
   after the restart. In the bot chat, the agent notes *"No home channel is set — a home
   channel is where Hermes delivers cron job results and cross-platform messages."* Send
   **`/sethome`** in the chat where you want the bot to post — **this is where the
   scheduled heartbeat's trade cards will land** (Phase 6). _Note: a fresh bot talks as the
   **default Hermes persona** ("I can help with coding, research, file management…");
   installing the kit (Phase 5) is what makes it the Shark trading bot._

**End of Phase 4** — Telegram is live; you can DM the agent.

---

## Phase 5 — Install the Shark Trading Agent

**Goal:** the kit's identity + heartbeat + skills running on the agent, with your two keys set.

The kit ships as a **Hermes Profile Distribution** — a git repo that bundles the persona,
skills, cron job, and config as one installable agent. Installing it is a single command.

1. **Install the profile.** In the dashboard's **App terminal** (or over SSH into the
   container), run:
   ```
   hermes profile install github.com/logiqfish/shark-trading-agent -y
   hermes profile use shark-trading-agent
   ```
   This pulls the `shark` skill (all trading scripts), `SOUL.md` (persona), `AGENTS.md`
   (rules), and the disabled `weekday-trading` cron job onto the box, and makes it the
   active profile (dashboard → **PROFILES** shows `shark-trading-agent [active]`).
2. **Set your Alpaca paper keys — in the App terminal.** The install generates a profile
   `.env` from the manifest's `env_requires`. The **FILES** page is **download-only**, so
   append the keys from the App terminal (paper keys from app.alpaca.markets -> the
   **Paper** account — never a live account):
   ```
   printf 'ALPACA_API_KEY=PKxxxx\nALPACA_SECRET_KEY=xxxx\nALPACA_BASE_URL=https://paper-api.alpaca.markets\n' >> /opt/data/profiles/shark-trading-agent/.env
   ```
   Your LLM key is already set from Phase 3.
3. **Restart** so the new profile + env load (`.env` is not hot-reloaded). If the
   dashboard's **Restart Gateway** button hangs, restart from the **Hostinger panel ->
   Docker Manager** (restart the Hermes app, or Reboot VPS) instead.

That's the whole install — Phase 6 drives the first run and turns on the schedule.

**How the pieces map** (for the curious):

| Kit piece | On the box |
|---|---|
| Persona (`SOUL.md`) | system prompt, injected verbatim |
| Rules / paths (`AGENTS.md`) | agent context file |
| Trading logic (`skills/shark/scripts/...`) | run via the `terminal` tool, keys auto-injected |
| Heartbeat (`SKILL.md` procedure) | the `weekday-trading` CRON job |
| Alpaca keys | profile `.env` (declared in the manifest, auto-injected into the sandbox) |

> **Data-fence (why Alpaca-only):** the kit never fetches market data from the open web —
> only Alpaca. From a datacenter IP, free sources like Yahoo Finance rate-limit or block
> requests (HTTP 429), so they're unreliable from a VPS; Alpaca is the single dependable
> source for both data and execution. The shipped prompt forbids ad-hoc `curl`/web/`pip`
> for data.

---

## Phase 6 — First run + schedule

**Goal:** drive one heartbeat by hand and watch it work end-to-end, then schedule the
~3×/day cadence.

1. **Make sure the gateway is running.** Cron only fires while the gateway runs. In the App
   terminal, start it and confirm the dashboard reads **Gateway Status: Running**:
   ```
   nohup hermes gateway run > /opt/data/gateway.log 2>&1 &
   hermes cron list          # must NOT warn "Gateway is not running"
   ```
   Inside Docker `hermes gateway install` is a no-op, and the dashboard **Restart Gateway**
   button only runs the gateway in the *foreground* (hangs at "Hermes Gateway Starting…";
   status then falsely reads Stopped). `nohup … &` persists past closing the terminal, but
   **re-run it after any container restart**.
2. **Register the job (CLI).** The shipped `cron/weekday-trading.json` is a **template — not
   auto-registered** (the CRON page starts empty; this build has no `--file`/import).
   Register it with the real prompt and a UTC schedule — `hermes cron create` has **no
   `--timezone` flag**, so the schedule runs on the container clock (UTC): `0 14,17,19` =
   10 AM / 1 PM / 3 PM ET during **EDT** (`0 15,18,20` in EST):
   ```
   hermes cron create '0 14,17,19 * * 1-5' 'Run the Shark trading routine for this fire. Follow the `shark` skill procedure exactly, in order. Emit only the final one-line status card summarizing the fire (trade or no-trade). Always emit the card and never respond with [SILENT], so every fire posts a status card.' --name weekday-trading --skill shark --deliver local
   ```
   Verify: `hermes cron list` → `Next run …T14:00:00+00:00` (= 10 AM ET).
3. **Run it once by hand.** `hermes cron run <id>` (id from `hermes cron list`). Watch
   **LOGS** for `cron.scheduler: Job '<id>': ... completed successfully`. The full report is
   saved under `cron/output/<id>/` regardless of delivery. The job then fires on schedule.

### Where do the cards go? (delivery)

The shipped job uses **`deliver: local`** — a headless-safe default so the kit works even
without Telegram. With `local`, each fire's summary card is written to the job's
`cron/output/` file and visible in **LOGS / SESSIONS**, but **is NOT sent to Telegram**.

**To get the trade cards in Telegram** you need all three:

1. **Bot connected** — Phase 4 (CHANNELS → Telegram, token in `.env`, toggle enabled).
2. **Home channel set** — send **`/sethome`** in the chat you want the cards in. This
   writes `TELEGRAM_HOME_CHANNEL` to your profile `.env`; **without it the bot is
   connected but cron has nowhere to deliver.**
3. **Switch the job to telegram** — recreate it with `--deliver telegram` (delete +
   `hermes cron create … --deliver telegram`, or `hermes cron edit <id> --deliver telegram`
   if your build supports it), then make sure the gateway is running
   (`nohup hermes gateway run > /opt/data/gateway.log 2>&1 &`).

> **Heads-up — every fire posts a card.** The job prompt intentionally emits a one-line
> status card on *every* fire (trade, no-trade, or market-closed), so a healthy bot is
> always visibly alive. Earlier kit builds prefixed no-action fires with `[SILENT]`, which silently
> suppressed delivery and made a correctly-running bot look dead ("did it even fire?").
> If you'd rather stay quiet on no-action, re-add `[SILENT]` to the prompt — but expect
> long stretches of silence on slow days.

---

## Troubleshooting / gotchas
_(collected as we hit them)_
- **Changes need Save → Restart Gateway.** In the v0.17.0 dashboard, config/channel/model
  edits don't apply until you **Save** and then **Restart Gateway** (bottom-left). The
  gateway connects channels and reloads config on restart. If something "didn't take,"
  restart the gateway first.
- The **gateway starts Off** on a fresh box — chat works without it, but scheduled
  heartbeats and channels (Telegram) need it **On**.
- **`.env` is not hot-reloaded** (confirmed live 2026-06-24). The gateway + agent sessions
  read env at start, so an edited/re-uploaded `/opt/data/.env` does nothing until you
  **Restart Gateway** AND start a **New chat** (a live session keeps its old env). Also
  check the setting actually lives in `.env` (keys/channel creds) vs `config.yaml`
  (model/agent/tools) vs `SOUL.md` (persona).
- **Scripts don't auto-see `.env` vars.** The `terminal`/`execute_code` sandbox only gets
  env vars that are **passed through** (skill `required_environment_variables` or
  `terminal.env_passthrough`) — so the kit declares Alpaca keys in its distribution
  manifest, not just in `.env`.
- Skill scripts use `#!/usr/bin/env bash` + `${BASH_SOURCE[0]}` — they must be invoked
  directly (shebang → bash), not via `sh script.sh` (dash → "Bad substitution").
