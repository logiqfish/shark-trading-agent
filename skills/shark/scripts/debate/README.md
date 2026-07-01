# debate — bull/bear/referee conviction debate

Part of the Shark Trading Agent. Replaces single-shot conviction with a bounded
Bull → Bear → Referee debate. The Referee emits the 0–100 conviction that feeds
HEARTBEAT Step 5 (floor 65) and Step 5.5 (risk bands) unchanged.

Code computes, brain judges (same split as `risk/` and `reflection/`):
- **`DEBATE.md`** — the prompt spec (roles + output contract); the bull/bear/referee
  turns are LLM prose run by the agent's own brain.
- **`debate.py` / `debate.sh`** — stdlib-only, jq-free helper. One verb, `record`:
  validates the referee verdict (conviction clamped to int [0,100]; stance ∈
  {bullish,bearish,neutral}; rationale ≤ 200 chars), appends the transcript to
  `memory/<date>.md` (`SHARK_MEMORY_DIR` overrides), prints the normalized
  `{ticker,conviction,stance,rationale}`. Malformed verdict → exit 3, no stdout.

## Rollout

HEARTBEAT Step 4 routes conviction through the debate, with the single-shot
Conviction Framework as an **automatic fallback** if the helper errors or is
unavailable (fail-safe — a broken debate never blocks a fire). Watch LLM cost: one
extra bull+bear+referee exchange per buyable candidate (≤3–5 per fire).

## Tests

```bash
cd skills/debate && python3 -m pytest tests/ -q
```
