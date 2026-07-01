# Discretionary Entry ("2nd brain" gut trade) — agent hook

Part of the Shark Starter Kit. **Out of band** — human-initiated only; never runs
on the scheduled scan. Trigger: the **account owner** messages a trade directive
("take TTWO", "buy TTWO stop 222"). A non-owner asking about a stock gets analysis
only — never an execution.

## The ~6-line HEARTBEAT step

1. **Recognize** the owner's trade directive in chat. Extract ticker, current
   price, and an optional operator stop.
2. **Conviction (advisory):** run the bull/bear/referee **debate** for the ticker
   to produce a 0–100 conviction score. (This is the only LLM step; everything
   below is the skill.)
3. **Propose:** pipe the payload to the skill —
   `echo '{"account":{...},"positions":[...],"candidate":{"ticker":"TTWO","price":PRICE,"conviction":SCORE,"stop":STOP_OR_OMIT}}' | skills/discretionary/discretionary.sh propose`
   - `ok:false` → a HARD block. Refuse and quote `hard_block`/`reason` (regime or
     a risk gate). Stop — do not trade.
   - `ok:true` → you get `{qty, entry, stop, target, equity_pct, conviction, catalyst}`
     (`catalyst` is always empty in this kit — no news/fundamentals layer ships).
4. **Present & ask (do not trade yet):**
   `🦈 Shark brain on TTWO: conviction {conviction}/100 · regime OK`
   `If you override, I'd place: {qty} sh @ ~${entry} · stop ${stop} · target ${target} (+2R) · {equity_pct:.0%} ✅`
   `Override and take it? (yes / no)`
5. **On the owner's explicit "yes" only:** add `date` (today) + `thesis` (the
   owner's rationale) to the proposal and pipe it to
   `skills/discretionary/discretionary.sh execute`. Report the returned fill card.
   On "no" / no reply → place nothing.

**The split that keeps it safe:** conviction is ADVISORY — the owner's "yes"
overrides a low score. The risk kernel (sizing, never-naked, the +2R bracket,
concentration, cash, drawdown, daily-loss, account guard, and the on-box regime
veto) is HARD and cannot be overridden. Nothing executes without BOTH a human
"yes" AND a passing `propose`. Fills are tagged `source:discretionary` in the
journal so they are easy to tell apart from the scheduled-scan trades.
