# reflection — self-grading trade journal

Part of the Shark Starter Kit. This skill records every entry, grades it at its
real exit on realized R **and alpha vs SPY**, has the agent's **own brain** write a
2–3 sentence lesson, and feeds recent lessons back into the next decision.

**Code computes, brain judges** — same split as `risk.py`. This module does the
deterministic math + file I/O; the heartbeat brain writes the prose lesson inline
(the agent *is* the LLM, so no separate model call).

## Storage

`JOURNAL.md` — git-tracked, kit top-level. It rides the Step 7 commit so it
survives across fires, like `IDENTITY.md`. The gitignored `memory/` directory is
wiped every run and must NOT be used.

`reflection.sh` resolves the journal at `../../JOURNAL.md` relative to this skill
dir; override with `SHARK_JOURNAL_PATH`.

## Three phases → three HEARTBEAT touchpoints

| Phase | When | HEARTBEAT step | Call |
|---|---|---|---|
| A — record | on entry | Step 6 (after bracket placed) | `append` |
| B — grade | on full exit | Step 1 (exit reconciliation) | `outcome` then `resolve` |
| C — inject | on candidate check | Step 4 | `context <TICKER>` |

## CLI (jq-free; stdin JSON except `context`)

```bash
# Phase A — pending slip
echo '{"ticker":"INTC","date":"2026-06-12","conviction":78,"entry":31.20,"stop":30.10,"thesis":"oversold bounce off fresh 8-K"}' | ./reflection.sh append

# Phase B — grading math (fetches SPY, prints outcome JSON; fail-soft alpha=null)
echo '{"entry_price":31.20,"exit_price":33.80,"entry_date":"2026-06-12","exit_date":"2026-06-18","realized_R":1.4}' | ./reflection.sh outcome
# -> {"raw_return":0.0833...,"realized_R":1.4,"alpha":0.0753...,"holding_days":6,"benchmark":"SPY"}

# ...brain reads those numbers, writes the lesson, then:
echo '{"ticker":"INTC","date":"2026-06-12","outcome":{...},"lesson":"Call correct (+1.4R). Capex thesis held."}' | ./reflection.sh resolve

# Phase C — recent lessons for the next decision prompt
./reflection.sh context INTC
```

## Behaviors

- **Scale-outs**: one slip per entry; resolves only when the *last* share is gone,
  using the blended R passed in from Step 1. The +1R partial does not grade.
- **Re-entries**: each entry is a distinct slip, keyed by entry date.
- **Idempotent** `append` (won't double-write the same date+ticker pending).
- **Atomic** `resolve` (temp-file + `os.replace` — no corruption mid-write).
- **Rotation**: keeps all pending + most-recent 50 resolved.
- **Fail-soft alpha**: if the SPY fetch fails, alpha is `null` and the tag renders
  `alpha n/a` — grading is never blocked by the benchmark.
- **Phantom-citation fix**: lessons enter a prompt only via `context`, which reads
  real resolved entries.

## SPY benchmark

`spy_return_pct()` pulls SPY daily bars from the Alpaca **data** API
(`data.alpaca.markets`, IEX feed) using the agent's existing `ALPACA_API_KEY` /
`ALPACA_SECRET_KEY`. No new service.

## Tests

`python3 -m pytest tests/ -q` — 18 tests (append idempotency, atomic resolve,
rotation, alpha math, SPY fail-soft, scale-out R pass-through, context
ordering/limits, malformed-file tolerance).
