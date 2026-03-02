# ADR-036: Haiku as Conductor Model

## Status

Accepted

## Context

Jimbo's conductor model (the one that handles conversations, briefings, and skill execution) was Gemini Flash via OpenRouter (`google/gemini-2.5-flash`). Flash is fast and cheap but produced shallow briefings:

- Skipped required skill sections (calendar, day plan, vault tasks)
- Hedged on things it should have been confident about ("if politics is your thing" when INTERESTS.md explicitly lists politics)
- Listed email subject lines without explaining relevance
- Failed to follow multi-step skill instructions (ran 1-2 of 7 required setup commands)

The daily-briefing skill was tightened (explicit sandbox commands, REQUIRED section markers, minimum bar in SOUL.md) but Flash still couldn't consistently follow the full skill spec.

## Decision

Switch the conductor model from Gemini Flash to Claude Haiku 4.5 (`openrouter/anthropic/claude-haiku-4.5`).

### Rationale

- Haiku follows complex, multi-step skill instructions more reliably than Flash
- Better at synthesising context (reading priorities + interests + email and producing a coherent briefing)
- Still reasonably cheap (~$0.25/million input, $1.25/million output on OpenRouter)
- Worker models stay on Flash (email triage) and Haiku (newsletter deep-read) — this only changes the conductor

### How to switch

```bash
./scripts/model-swap.sh haiku
# Edits openclaw.json primary model, restarts service
```

### What didn't change

- Worker models unchanged (Flash for triage, Haiku for deep-read)
- Scoring model stays on Gemini Flash (direct API, not OpenRouter)
- All skills, tools, and sandbox capabilities remain the same
- `model-swap.sh` still supports switching back: `./scripts/model-swap.sh daily` (Flash) or `./scripts/model-swap.sh free`

## Consequences

### Easier
- Briefings consistently follow the full skill spec
- Better contextual reasoning (connects email items to priorities/goals)
- More confident personality (less hedging, more "you'll want to see this")

### Harder
- Higher per-message cost than Flash (~3-5x)
- Slightly slower responses
- OpenRouter credit burn increases — monitor via `alert-check.py credits`
