# Shark Starter Kit — Setup Guide

> **Status: being validated on a real install (2026-06-24).** Steps are filled in
> and confirmed as the install is actually performed, so this is a tested walkthrough,
> not a guess. Sections marked _(pending live run)_ aren't confirmed yet.

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

- Provider used here: **Hostinger** (KVM VPS).
- Plan / size: _(pending — capturing the plan you pick)_
- Region: _(pending)_
- OS image: _(pending — Ubuntu 24.04 LTS expected)_
- Access: _(pending — root password or SSH key)_

> **Two paths to a running Hermes:**
> - **Primary (easiest — used in this walkthrough):** on Hostinger, the VPS "what to
>   install" step has a one-click **Hermes Agent** Docker app — Hermes comes
>   pre-installed and running. Phases 1+2 collapse into this single choice.
> - **Portable (any provider):** a bare Ubuntu 24.04 box + a manual Hermes install.
>   For DigitalOcean / Hetzner / Vultr / etc. _(documented later — TODO.)_

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
   24.04 LTS** instead and install Hermes manually — TODO.)_
   _screenshots: `docs/setup/images/p1-04a-choose-hermes-agent.png`,
   `p1-04b-hermes-agent-modal.png` (redacted)_
5. **Pick a plan (KVM tier).** **KVM 1** (1 vCPU / 4 GB / 50 GB, ~$6.49/mo intro) is
   enough on paper: the LLM runs remotely (DeepSeek over the API — nothing heavy on the
   box), the skills are stdlib-only, and it fires just ~3×/day. **For this walkthrough we
   used KVM 2** (2 vCPU / 8 GB) — a known-good Hermes config, so infra
   isn't a variable during the first test. You can upgrade in one click anytime, so a
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

## Phase 2 — Install Hermes
_(pending live run)_

**Goal:** the base agent running on the box and reachable.

---

## Phase 3 — Configure the LLM (DeepSeek)

**Goal:** Hermes' single brain set to DeepSeek, fail-safe to no-trade if unreachable.

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
1. **KEYS → set your LLM provider key.** The KEYS page lists many providers (Anthropic,
   DeepSeek, Gemini, Kimi/Moonshot, OpenRouter, …) with an "X of 28 configured" counter.
   Expand your provider and click **Set**:
   - **DeepSeek** (platform.deepseek.com key) → the kit-faithful "Alpaca + DeepSeek,
     two keys" path, and it's the **primary brain**. _Recommended for the giveaway._
   - **OpenRouter** (your own OpenRouter key) also works, but note its field is labeled "for vision,
     web scraping helpers, and MoA" — it may be treated as **auxiliary**, so confirm in
     MODELS that an OpenRouter-routed model is actually selectable as the primary brain.
   _screenshot: `docs/setup/images/p3-03-keys.png` (redacted — keys are masked as
   `sk-…last4`, but crop anyway)_
2. **MODELS → set the MAIN MODEL.** The MODELS page has **MODEL SETTINGS** with a
   **MAIN MODEL** (starts `(unset)`) and **AUXILIARY TASKS** (11 helper tasks). Click
   **CHANGE** on MAIN MODEL and pick a **DeepSeek** model — that's the agent's brain.
   **Leave AUXILIARY TASKS on "all auto"** (they're vision/compression/web-extract
   helpers; the kit's data-fence means it never uses them). If the picker offers no
   working DeepSeek brain from your key, set the **DeepSeek** provider key in KEYS and
   retry. _screenshot: `docs/setup/images/p3-04-models.png`_

   In the **SET MAIN MODEL** picker, the provider with your key (e.g. **OpenRouter**)
   lists its models. Pick a DeepSeek one and click **Switch** (saves to `config.yaml`):
   - **`deepseek/deepseek-v4-pro`** — strongest reasoning; recommended for real trading
     decisions.
   - **`deepseek/deepseek-v4-flash`** — cheaper/faster; a good cost default given the
     spending-cap warning. _(The kit is brand-agnostic — any capable model works.)_
   _screenshot: `docs/setup/images/p3-05-set-main-model.png`_
   After **Switch**, the MODELS page shows e.g. `MAIN MODEL: openrouter ·
   deepseek/deepseek-v4-pro`.
3. **Restart Gateway + smoke-test the brain.** Hit **Restart Gateway** (bottom-left;
   gateway starts **Off**) — the "agent init failed / Setup Required" clears and
   **Gateway Status → On**. Then in **CHAT**, send a quick "hi" and confirm the model
   replies. That verifies the brain is wired end-to-end before configuring trading.
   _screenshot: `docs/setup/images/p3-06-gateway-on-chat.png`_

**End of Phase 3** — Hermes has a working DeepSeek brain.

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
4. **Set the home channel: `/sethome`.** In the bot chat, the agent notes *"No home
   channel is set — a home channel is where Hermes delivers cron job results and
   cross-platform messages."* Send **`/sethome`** in the chat where you want the bot to
   post — **this is where the scheduled heartbeat's trade cards will land** (Phase 6).
   _Note: a fresh bot talks as the **default Hermes persona** ("I can help with coding,
   research, file management…"); installing the kit (Phase 5) is what makes it the Shark
   trading bot._
3. **Restart Gateway, then Test.** The gateway is **Off** by default ("Configure channels
   here, then start the gateway"). After enabling Telegram, hit **Restart Gateway**
   (bottom-left) — it connects each enabled channel on restart — then **Test**.

**End of Phase 4** — Telegram is live; you can DM the agent.

> ✅ **Milestone (2026-06-24):** the full runtime stack is validated on a fresh box —
> VPS → Hermes Agent **v0.17.0** → DeepSeek-v4-pro brain → Telegram, all working. What
> remains is Phase 5 (install the kit), which is the real work because v0.17.0 differs
> from the Hermes environment the kit was originally built against.

---

## Phase 5 — Install the Shark Starter Kit
_(in progress — the install mechanism depends on the Hermes version)_

**Goal:** the kit's identity + heartbeat + skills run on the agent, with your two keys set.

> **⚠️ Runtime note (discovered live 2026-06-24):** the Hostinger **Hermes Agent is
> v0.17.0** — a richer framework than the older lab Hermes the kit was first built
> against. It has its own **SKILLS / PLUGINS / CRON / CONFIG / FILES** subsystems, a
> **plugin manifest** format, user content under **`~/.hermes/plugins`**, and a
> **PLUGINS → "Install from GitHub / Git URL"** one-click installer (`owner/repo` →
> Install). The kit (a lab-Hermes *workspace* of `IDENTITY.md` + `HEARTBEAT.md` +
> `skills/*.sh`) is **not yet a v0.17.0 plugin**, so it doesn't drop in as-is.

**Two roads (decide per goal):**
- **A — Repackage the kit as a native v0.17.0 plugin/skill bundle** (manifest + skills +
  a cron-driven heartbeat + identity as system-prompt/config). Yields the
  friend-friendly **one-click `owner/repo → Install`** experience. The right giveaway
  end-state; requires learning Hermes' plugin/skill manifest format first (study this
  PLUGINS page, the docs, and a bundled plugin e.g. `browser-browser-use`).
- **B — Manual placement for the smoke test** (put files on disk via FILES/App terminal,
  wire a CRON job to run the heartbeat, set the identity). Faster path just to validate
  the *trading* logic on this runtime; not the final shape.

**v0.17.0 recon (so Phase 5 has the map):**
- Config is one big YAML at **`/opt/data/config.yaml`**, edited via **CONFIG** (sections:
  General, **Agent [44 fields]**, Memory, Gateway, channels [Discord/Matrix/Mattermost/…],
  Secrets, …). The **Agent** section is where the **persona / system prompt** lives → the
  kit's `IDENTITY`/`SOUL` map here.
- Model is set in General: `deepseek/deepseek-v4-pro`; toolset `hermes-cli`.
- Custom code installs as **plugins** under `~/.hermes/plugins` (PLUGINS → Install from
  GitHub); **CRON** schedules; **CHANNELS** wires Telegram/etc.
- **Data root = `/opt/data`** (FILES page), containing `skills/`, `plugins/`, `cron/`,
  `hooks/`, `memories/`, `sessions/`, **`.env`** (93 B), and `config.yaml`. **FILES has
  UPLOAD / CREATE — so the kit can be placed straight from the dashboard, no SSH.**

**Placement map (kit → v0.17.0):**
| Kit piece | Maps to |
|---|---|
| `IDENTITY.md`/`SOUL.md` (persona) | `CONFIG → Agent` section of `/opt/data/config.yaml` |
| `skills/*.sh` | `/opt/data/skills/` (FILES upload) |
| Alpaca keys | `/opt/data/.env` (DeepSeek already via KEYS/OpenRouter) |
| `HEARTBEAT.md` (3×/day loop) | a **CRON** job running the heartbeat prompt |
| one-click giveaway install | **PLUGINS → Install from GitHub** (once repackaged) |

### Phase 5 DECISION (researched 2026-06-24): repackage the kit as a Hermes **Profile Distribution**

Hermes v0.17.0 has a purpose-built feature for shipping "personality + skills + cron +
config" as one git-installable, updatable agent: **`hermes profile install
github.com/<you>/<repo>`**. That's the kit's native install path — *not* a Python plugin
(plugins are for new LLM-callable tools/hooks in Python; we'd be rewriting working bash
for nothing). Key fact: a Hermes **skill** bundles a `scripts/` dir and its `SKILL.md`
tells the agent to run those bash/python scripts via the **`terminal`** tool, with
declared **env vars auto-injected** — exactly the kit's "orchestration-prompt → calls
deterministic scripts" shape. And `HERMES_HOME=/opt/data` here, so docs' `~/.hermes/…` =
`/opt/data/…`.

**Target distribution layout (the kit, re-architected):**
```
shark-starter-kit/                 (as a Hermes Profile Distribution)
├── distribution.yaml              # manifest: name, version, env_requires (ALPACA_*)
├── SOUL.md                        # ← kit IDENTITY/SOUL (system-prompt slot #1)
├── AGENTS.md                      # ← kit rules/paths (context file)
├── config.yaml                   # model/provider defaults (deepseek-v4-pro via OpenRouter)
├── skills/
│   └── shark/
│       ├── SKILL.md               # ← kit HEARTBEAT, rewritten as the per-fire procedure
│       └── scripts/               # ← all kit bash/python: local-markov, discovery-local,
│                                  #    risk, trade-manager, reflection, thesis, alpaca,
│                                  #    debate, discretionary (called via ${HERMES_SKILL_DIR})
├── cron/
│   └── weekday-trading.json       # 3×/day weekday job: --skill shark --deliver local (see Phase 6 to switch to telegram)
├── .gitignore                     # MUST exclude .env, auth.json, memories/, sessions/, *.db
└── README.md
```
- **Cron:** `hermes cron create "0 10,13,15 * * 1-5" "<heartbeat prompt>" --skill shark
  --deliver local --name weekday-trading` (ships `local` for headless safety; switch to
  `--deliver telegram` once a home channel is set — see Phase 6). **Pin provider/model**
  (unattended cost guard). Distribution cron jobs install **disabled** → enable by hand
  after install.
- **Identity:** `SOUL.md` in HERMES_HOME (`/opt/data/SOUL.md`), injected verbatim;
  truncated if too large (exact cap unknown — keep persona here, workflow/paths in AGENTS.md).
- **Secrets:** Alpaca keys declared in `distribution.yaml` `env_requires` → auto-injected
  into the `terminal` sandbox; DeepSeek already configured via KEYS/MODELS.

**✅ Pre-check PASSED (verified live 2026-06-24): terminal-sandbox egress to Alpaca works.**
Asked the bot (via Telegram) to run `curl -s -o /dev/null -w '%{http_code}'
https://paper-api.alpaca.markets/v2/clock` → it returned **`401`** (reached Alpaca, just
no creds). So the agent's `terminal`/`execute_code` sandbox has outbound internet to
Alpaca — the kit's scripts can curl `data.alpaca.markets`/`paper-api` from there. The
distribution approach is green-lit.

> **Side check (validates the data-fence):** the same test against Yahoo Finance
> (`query1.finance.yahoo.com/v8/finance/chart/AAPL`) returned **`429` Too Many Requests**
> — egress reaches Yahoo, but it **rate-limits/blocks this datacenter IP** (the saved
> `AAPL.json` was Yahoo's error body, not data). Confirmed live why the kit is
> **Alpaca-only**: a friend can't rely on Yahoo from a VPS. A browser `User-Agent` might
> sneak through occasionally, but that fragile cat-and-mouse is exactly what the data-fence
> avoids.

**Other unknowns to verify on the box:** SOUL.md size cap; the `hermes` CLI path inside
the Hostinger container (for `hermes profile install`).

**Next:** (1) run the egress pre-check; (2) write the repackaging implementation plan
(kit → Profile Distribution), reusing the existing tested scripts; (3) build + `hermes
profile install` from the (private) repo; (4) enable the cron; (5) live paper smoke test.

---

## Phase 6 — First run + schedule

**Goal:** drive one heartbeat by hand and watch it work end-to-end, then schedule the
~3×/day cadence.

1. **Find the job.** The kit ships a `weekday-trading` cron job (**CRON** page), disabled
   by default: `0 10,13,15 * * 1-5` America/New_York, `--skill shark`.
2. **Run it once by hand.** Hit the ⚡ **run-now** on the job card (or CLI
   `hermes cron run <id>`). Watch **LOGS** — you should see
   `cron.scheduler: Job '<id>': ... completed successfully`. The full report is saved as a
   dated file under the profile's `cron/output/<id>/` regardless of delivery.
3. **Enable** the job (toggle on the CRON card) so the 3×/day schedule fires.

### Where do the cards go? (delivery)

The shipped job uses **`deliver: local`** — a headless-safe default so the kit works even
without Telegram. With `local`, each fire's summary card is written to the job's
`cron/output/` file and visible in **LOGS / SESSIONS**, but **is NOT sent to Telegram**.

**To get the trade cards in Telegram** you need all three:

1. **Bot connected** — Phase 4 (CHANNELS → Telegram, token in `.env`, toggle enabled).
2. **Home channel set** — send **`/sethome`** in the chat you want the cards in. This
   writes `TELEGRAM_HOME_CHANNEL` to your profile `.env`; **without it the bot is
   connected but cron has nowhere to deliver.**
3. **Switch the job to telegram** — edit the `weekday-trading` job's **delivery** from
   `local` to `telegram` (CRON → edit, or `hermes cron edit <id> --deliver telegram`),
   then **Restart Gateway**.

> **Heads-up — every fire posts a card.** The job prompt intentionally emits a one-line
> status card on *every* fire (trade, no-trade, or market-closed), like the reference
> lab agents. Earlier kit builds prefixed no-action fires with `[SILENT]`, which silently
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
