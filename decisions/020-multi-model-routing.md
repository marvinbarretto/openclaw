# ADR-020: Multi-Model Routing — Right Model for the Right Job

## Status

Accepted

## Context

We've been running Gemini 2.5 Flash as a single model for everything Jimbo does — casual chat, morning briefings, day planning, and heartbeat tasks. After a week of daily use (scores averaging 2-3/10), Flash is clearly struggling with complex multi-file reasoning:

- Goes off-script during briefings (writes blog posts instead of following the skill)
- Calendar suggestions lack judgment (suggested fixing its own tooling)
- Can't reliably cross-reference 7+ context files for day planning
- Simple chat and Q&A are fine

Meanwhile, the email classification pipeline runs locally on Ollama (qwen2.5-coder:14b) and works well for bulk classification. This confirms the principle: match model capability to task complexity.

We now have OpenClaw credits (Anthropic) so we can experiment with better models for high-value tasks without cost being a hard blocker.

## Decision

Route different tasks to different models based on complexity and value.

### Routing table

| Task | Complexity | Model | Why |
|---|---|---|---|
| Email classification | Bulk, structured output | Ollama qwen2.5-coder:14b (local) | High volume, fixed schema, runs offline. Works well. |
| Casual Telegram chat | Low | Gemini 2.5 Flash | Quick responses, low stakes. Flash is fine here. |
| Morning briefing | High | Claude Haiku 4.5 | Must follow complex skill instructions, cross-reference 7 files, exercise judgment. |
| Day planning | High | Claude Haiku 4.5 | Requires synthesizing priorities, goals, calendar, email into useful suggestions. |
| Heartbeat tasks | Medium | Gemini 2.5 Flash | Structured checks, simple rules. Flash can handle this. |
| Blog publishing | Medium | Gemini 2.5 Flash | Template-driven, low judgment needed. |

### Implementation approach

**Phase 1 (now):** Switch the daily driver to Haiku. This means everything uses Haiku. Simple but gives us an immediate quality baseline to compare against Flash.

**Phase 2 (later):** Per-skill model routing if OpenClaw supports it, or time-based switching (Haiku during briefing hours, Flash for afternoon chat). This is only worth doing if Haiku proves significantly better and cost is a concern.

### Cost impact

| Model | Estimated monthly cost | Quality (observed) |
|---|---|---|
| Gemini 2.5 Flash | ~$0.78 | 2-3/10 for complex tasks |
| Claude Haiku 4.5 | ~$2.49 | TBD — expected 5-7/10 |
| Claude Sonnet 4.5 | ~$15-25 | Reserved for manual use |

The difference is $1.71/month. If Haiku delivers even marginally better briefings, it's worth it. The morning briefing is the single highest-value interaction — getting it right matters more than saving $1.71.

### What we're measuring

Track in `DIARY.md`:
- Daily satisfaction score (1-10)
- Which model was running
- Whether the briefing followed instructions
- Whether suggestions were useful
- Pipeline reliability (did the digest arrive fresh?)

After 5 days on Haiku, compare average scores to the Flash baseline.

## Consequences

**What becomes easier:**
- Briefings should follow skill instructions more reliably
- Day planning suggestions should show better judgment
- We have a structured way to compare models over time

**What becomes harder:**
- Slightly higher monthly cost (~$2.49 vs ~$0.78)
- Need to track which model produced which results in the diary

**Risks:**
- Haiku may not be significantly better than Flash for this specific use case
- OpenClaw may not support per-skill model routing, limiting Phase 2
- Cost could escalate if we keep upgrading to Sonnet/Opus

**New files:**
- `DIARY.md` — daily tracking of satisfaction, model, and pipeline status
