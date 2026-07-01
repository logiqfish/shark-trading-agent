# discretionary — Shark Trading Agent skill

Human "2nd brain" gut-trade entry. Lets the account owner hand the bot a ticker
("take TTWO") and get a gated, bracketed proposal back — never a raw buy.

## What it is
A jq-free `propose`/`execute` orchestrator that glues the kit's local skills:
the on-box regime veto (`local-markov`), `risk` (with `discretionary:true`), the
`trade-manager` bracket, and a `reflection` slip. The conviction-producing debate
is run by the agent's brain and passed in (see `DISCRETIONARY.md`). All risk gates
stay HARD; only the conviction floor is advisory.

Because the kit is paper-only there is no kill-switch/control service (the control
gate is an always-pass no-op) and no catalyst/news/fundamentals layer (the catalyst
advisory is always empty) — trades rest on price action + the LLM's judgment.

## Files
- `discretionary.sh` — entrypoint: `propose` | `execute` (JSON on stdin)
- `discretionary.py` — orchestration + math + CLI
- `DISCRETIONARY.md` — the HEARTBEAT hook for the discretionary flow
- `tests/` — TDD, no network (siblings injected)

## Runtime requirement
Lives next to its siblings: `skills/discretionary/` resolves `../local-markov`,
`../risk`, `../trade-manager`, `../reflection`. It is inert unless the HEARTBEAT's
Discretionary Entry hook calls it.

## Test
```
cd skills/discretionary && python3 -m pytest tests/ -q
```
