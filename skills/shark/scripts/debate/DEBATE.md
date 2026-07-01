# DEBATE.md — bull/bear/referee conviction debate (prompt spec)

The prompt spec the agent's brain runs for the conviction debate: the roles and the
output contract. Part of the Shark Starter Kit.

## What this replaces

The single-shot "Conviction Framework" pass in HEARTBEAT **Step 4**. Instead of
the brain emitting one conviction number, it runs a short structured debate and
the **Referee** emits the 0–100 conviction. That number flows into Step 5 (floor
N=65) and Step 5.5 (risk bands) **unchanged**.

## When it runs

Once per **buyable candidate carried in from Step 3.5** (already legal, already
capped to the top 3–5 by Step 3). **Single round, three turns. No re-arguing** —
that bound is what keeps cost bounded and is the only reason this is safe to run
on every fire. The full Trade Eligibility Gate (IDENTITY.md) still runs first and
the debate never overrides it: the debate produces *conviction*, the gates
produce *legality*.

## Inputs every role sees (identical, shared facts)

- The ticker's recent price action and the candidate context from Step 3
  (`skills/discovery-local/discover.sh`). No external news/catalyst/fundamentals
  data is available — argue from price action and your own reasoning.
- Past lessons for the ticker and setup: `skills/reflection/reflection.sh context TICKER`
  (Phase C). A repeated past mistake should weigh on the Bear; a confirmed edge on the Bull.
- Current account/position context from Step 1.

Debate **only** on these shared facts. Do not introduce free-form outside
sentiment/news not present in the shared feed — that would break parity.

## The three turns

1. **BULL** — Build the strongest evidence-based long case: catalyst strength,
   technical entry, why the setup works. Engage the facts; don't just list them.

2. **BEAR** — Build the strongest case *against*, directly rebutting the Bull on
   the **same** facts: what invalidates the thesis, what the catalyst misses,
   downside/risk, any past-lesson warning. Argue to win, not to hedge.

3. **REFEREE** — Weigh both sides and commit. Emit exactly ONE JSON line:

   ```json
   {"conviction": <int 0-100>, "stance": "bullish|bearish|neutral", "rationale": "<= 200 chars"}
   ```

   - `conviction` maps to our existing scale: ≥ 65 trades (Step 5); the risk band
     (65-69 / 70-79 / 80-89 / 90-100) then sizes it (Step 5.5).
   - Commit to a side when the strongest arguments warrant it; reserve a
     neutral/low score for a genuinely balanced debate. A one-sided strong bull
     case that the bear can't dent → high conviction; a bear that lands real
     damage → low. Do not anchor on a default.

## Logging the verdict (required)

Pass the verdict and the two cases through the helper so the transcript is logged
(audit trail + parity proof) and the score handed to the gate is validated
(clamped int, known stance):

```bash
printf '%s' '{"ticker":"TICKER","date":"TODAY","bull":"<bull case>","bear":"<bear case>","verdict":{"conviction":SCORE,"stance":"STANCE","rationale":"<one line>"}}' \
  | skills/debate/debate.sh record
```

Use the `conviction` from the printed JSON (not your raw number) as the Step 5
input. On a malformed verdict the helper exits non-zero and prints nothing —
treat that as "no valid conviction" and skip the candidate (do not trade on an
unscored debate).
