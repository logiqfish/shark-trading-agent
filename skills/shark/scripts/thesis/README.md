# thesis — persistent trade-thesis store + zero-LLM re-score

Part of the Shark Trading Agent. **Code computes, brain judges** — this module does
the deterministic checks + file I/O; the agent's own brain re-argues conviction
(the debate) **only when this module says the thesis materially moved.**

## Why

Every fire re-derives conviction from zero; the debate re-argues each held
position and throws the result away. This skill gives the agent a **persistent,
structured thesis** it can re-score cheaply and skip re-debating when nothing
changed — built native (jq-free, fail-soft).

## Storage

| What | Where | Persistence |
|---|---|---|
| Logic | `thesis.py` (+ `thesis.sh`) | in git |
| Live theses | `THESES.json` (kit top-level, sibling to `JOURNAL.md`) | **git-tracked**, rides Step 7 commit |
| Closed (archive) | `THESES_ARCHIVE.jsonl` | **gitignored**, audit-only |

**Hard rule:** the store is a git-tracked file, **never** `memory/` (the gitignored
vector store is wiped per fire) — so `THESES.json` survives across fires exactly
like `JOURNAL.md`/`AGENTS.md`. Writes are atomic (`tmp + os.replace`). Paths
override with `SHARK_THESES_PATH` / `SHARK_THESES_ARCHIVE_PATH`.

## Schema (one thesis)

```jsonc
{
  "id": "th_INTC_20260623",          // ticker + fire date (YYYYMMDD)
  "ticker": "INTC",
  "kind": "position",                // "position" | "candidate" (scope B — dormant in v1)
  "status": "open",                  // "open" | "closed" (closed -> pruned to archive)
  "direction": "long",
  "conviction": 72,                  // last referee score; carried forward between debates
  "conviction_fire": "...Z",         // when conviction was last *re-derived* by a debate
  "carried_fires": 3,                // consecutive fires carried without re-debate
  "invalidation_price": 218.47,      // thesis-level hard kill (usually the stop)
  "assumptions": [
    { "id": "a1", "claim": "holds the breakout on the foundry catalyst",
      "check": { "type": "price_above", "param": 215.0 },
      "weight": "core",              // "core" | "supporting" — a core violation escalates
      "status": "intact",            // intact | weakening | violated (set by Layer 1)
      "status_fire": "...Z" }
  ],
  "delta_log": [ { "fire": "...Z", "change": "a1 intact->weakening" } ],  // bounded (last 20)
  "outcome": null                    // grade-at-exit: {realized_R, alpha_vs_spy, failed_assumptions, lesson}
}
```

### Check dispatch table (closed set — new types are reviewed code, never free-form)

| `check.type` | `param` | Source | intact / weakening / violated |
|---|---|---|---|
| `price_above` | level | Alpaca quote | `≥level` / within 1.5% below / clearly below |
| `price_below` | level | Alpaca quote | `≤level` / within 1.5% above / clearly above |
| `regime_favorable` | — | on-box `local-markov` | Bull / Sideways / Bear (inverted for `short`) |
| `stop_distance` | `{stop,min}` | Alpaca quote | `≥min` away / closer / (never violated) |
| `manual` | — | none | **always intact** — honest escape hatch for soft claims (surfaced "unverifiable"); never forces escalation |

A **failed fetch** → that check is `(weakening, unverifiable)` → **forced escalation**.
So a wrong/missing mapping can only cause an *extra debate*, never a silently
skipped one. `manual` is distinct: an *accepted* unverifiable that stays intact.

## Two-layer re-evaluation

- **Layer 1 — `rescore_all` (HEARTBEAT Step 3.6, zero-LLM).** Score every open
  thesis's assumptions, update statuses + `delta_log`, decide **escalate?**.
  Escalate when: any `core` assumption violated, **or** any assumption changed
  this fire, **or** any check unverifiable (failed fetch), **or**
  `invalidation_price` breached. Otherwise carry conviction forward
  (`carried_fires++`).
- **Layer 2 — the heartbeat.** Runs the seeded bull/bear/referee debate **only**
  for escalated theses (and to create a thesis at a new entry). Intact theses
  skip the debate.

**The skip is safe:** the risk gate, allowed-actions pre-gate, and trade-manager
run **every fire, untouched**. Layer 2 gates only the LLM debate that re-derives
conviction — never position protection/management.

## CLI

```bash
# debate creates a thesis at entry
echo '{"ticker":"INTC","direction":"long","conviction":78,"invalidation_price":218.47,
       "fire":"<ISO>","assumptions":[{"id":"a1","claim":"...","check":{"type":"price_above","param":215.0},"weight":"core"}]}' \
  | ./thesis.sh create                      # -> {"id":"th_INTC_<date>"}

./thesis.sh rescore "<ISO fire>"            # Layer 1: prints [{ticker,id,escalate,deltas,...}]
echo '{"id":"th_INTC_...","conviction":61,"fire":"<ISO>"}' | ./thesis.sh set-conviction
echo '{"id":"th_INTC_...","outcome":{...}}' | ./thesis.sh close   # grade-at-exit: close + archive
./thesis.sh list                            # open theses JSON
```

Exit codes: `0` ok · `2` usage · `3` bad stdin JSON / python3 missing.

## HEARTBEAT integration (3 touch points; corrected model)

> The debate (Step 4) is **entry-only**; held positions are managed mechanically
> (Steps 1–2), never re-debated. So in **scope A** the re-score drives a
> **held-position exit signal**, not a debate-skip. The escalate/skip machinery is
> retained in code for **scope B** (candidate-thesis persistence), which is deferred.

1. **Entry (Step 6, beside the reflection slip)** — `thesis.sh create` once the
   entry fills, alongside `reflection.sh append`.
2. **Held positions (new Step 2c, between 2b and 2.5)** — `thesis.sh rescore
   "<fire>"`; any row with **`exit_signal:true`** → narrate a thesis-invalidation
   exit **advisory**. Advisory only: never cancels brackets, never force-sells,
   never overrides Step 2 close-protection. Resting GTC stops protect regardless.
3. **Exit (Step 1 reconciliation, beside reflection resolve)** — `thesis.sh close`
   (writes `outcome`, prunes to archive). Thesis + reflection grade together.

**`exit_signal` vs `escalate`:** `exit_signal` is True **only** on a hard *core*
violation or a *confirmed* invalidation breach — never on weakening, mere change,
or a failed fetch (incl. an unconfirmable invalidation). `escalate` is broader and,
in scope A, ignored. This keeps a thesis-driven exit from firing on noise (honors
the 2026-06-22 no-healthy-liquidation rule).

## Data sources (kit fork)

This is the skinny-kit fork: re-score data is **on-box only** — no Cloud Run mesh.
`fetch_price` reads the latest trade from the friend's own Alpaca keys; `fetch_regime`
shells the sibling `local-markov` skill for the Bull/Sideways/Bear label. The
`catalyst_live` / `fundamentals_stable` checks of the full system are **not** part of
this fork (no paid-data dependency); their types now fail safe like any unknown type.

## Install

1. `THESES.json` lives at the kit's top level (`[]` on a fresh install) and is
   git-tracked so it survives across fires.
2. `THESES_ARCHIVE.jsonl` (and `THESES_ARCHIVE.*`) is gitignored, audit-only.
3. Only `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` are needed (regime is on-box).
4. Wire the HEARTBEAT touch points above.

Run tests: `python3 -m pytest tests/ -q` (stdlib-only, no network).
