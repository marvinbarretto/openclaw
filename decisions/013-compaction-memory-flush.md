# ADR-013: Compaction Tuning and Memory Flush

## Status

Accepted

## Context

Jimbo hit context limit errors during normal Telegram conversations, triggering a hard reset with total context loss. Investigation revealed three compounding issues:

1. **`reserveTokensFloor` set to 5000** — far below the 20,000 default. Compaction triggers too late, leaving insufficient room for the summarization API call itself to succeed. This matches OpenClaw issue #7477 (safeguard mode silently fails on large contexts) and #8077 (/compact deadlocks on overflow).

2. **No `memoryFlush` configured** — when compaction does fire, Jimbo has no prompt to persist important context to disk before the conversation gets summarized. Result: total amnesia after every compaction or reset.

3. **Single memory file in 3 days** — only `memory/2026-02-16.md` (bootstrap day) existed. Jimbo described a memory-writing workflow in conversation but never actually executed it, because nothing triggered him to do so.

The model (`openrouter/stepfun/step-3.5-flash:free`) has a 256K context window, but the free OpenRouter tier may impose lower effective limits. Either way, the compaction config was inadequate.

## Decision

Update `agents.defaults.compaction` in `openclaw.json` to:

```json
{
  "reserveTokensFloor": 20000,
  "memoryFlush": {
    "enabled": true,
    "softThresholdTokens": 4000,
    "systemPrompt": "Session nearing compaction. Store durable memories now.",
    "prompt": "Write any lasting notes to memory/YYYY-MM-DD.md; reply with NO_REPLY if nothing to store."
  }
}
```

**`reserveTokensFloor: 20000`** — matches OpenClaw's default. Ensures compaction fires with enough headroom for the summarization call to succeed. 4x the previous value (5000).

**`memoryFlush.enabled: true`** — triggers a silent agentic turn when context approaches `contextWindow - reserveTokensFloor - softThresholdTokens`. Jimbo gets prompted to write durable notes before compaction summarizes the conversation.

**`softThresholdTokens: 4000`** — the buffer before the hard threshold. On a 256K window, memory flush triggers at ~232K tokens. On a smaller effective window (e.g. 128K free tier), it triggers proportionally earlier.

## Consequences

**Easier:**
- Jimbo persists important context across compaction events automatically
- Compaction succeeds instead of crashing — graceful degradation
- Memory files accumulate over time, giving Jimbo richer context on restart
- Debugging is easier — memory files show what Jimbo thought was important

**Harder:**
- Memory flush adds a silent API call near compaction threshold — slight latency/cost
- `reserveTokensFloor` at 20K means ~20K fewer tokens available for conversation before compaction fires — shorter effective sessions
- Memory files need occasional curation (could grow stale or noisy)

**Watch for:**
- If the free-tier model has a much smaller effective window (e.g. 32K), even 20K reserve may be too aggressive. Monitor whether Jimbo compacts too frequently.
- If memory files get noisy, consider adding a weekly curation prompt or size cap.
- `jimbo-vps` token expires ~May 2026 — if OpenRouter free tier changes limits, revisit this.
