# Observability & Briefing Quality — Design Doc

**Date:** 2026-03-03
**Status:** Draft
**Goal:** Add full-pipeline observability via LangFuse, upgrade the briefing model to Sonnet 4.6, add Kimi K2 as the daily driver, and establish a daily review ritual for prompt/output quality.

## Problem

Jimbo's morning briefings are comprehensively poor — shallow output, wrong priorities, frequent worker fallbacks. We have logging infrastructure (experiment-tracker, activity-log, cost-tracker) but no visibility into **what the LLM actually receives and returns**. We're tweaking prompts in the dark.

## Design

### 1. OpenRouter Broadcast to LangFuse (zero code)

Enable OpenRouter's built-in broadcast feature. Every call Jimbo makes through OpenRouter automatically gets traced in LangFuse — full system prompts, completions, token counts, costs, latency.

**Setup (manual, one-time):**
1. Create LangFuse account (free Hobby tier — 50k observations/month, Jimbo uses <500)
2. In LangFuse: create project "Jimbo", get Public Key + Secret Key
3. In OpenRouter settings: enable Broadcast → LangFuse, paste keys
4. Verify with a test message to Jimbo

**What this captures:** The full assembled prompt OpenClaw sends to the LLM — SOUL.md, skills, context files, conversation history, tool calls and responses. This is the most valuable piece — seeing what the conductor actually works with.

**Limitation:** Only covers calls through OpenRouter. Direct API calls (workers) need separate instrumentation (Section 2).

### 2. Worker Instrumentation via `call_model()` wrapper

Add LangFuse tracing at the `call_model()` routing layer in `base_worker.py`. This is the single dispatch point for all worker API calls — wrapping here covers Google AI, Anthropic, and any future provider.

**Implementation:**
- After `call_model()` gets a response, POST the trace to LangFuse's ingestion API via `urllib` (stdlib, no pip)
- ~30-40 lines added to `base_worker.py`
- Fire-and-forget: if LangFuse is down, workers still work. Trace failure logged to stderr.
- LangFuse credentials via env vars: `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`
- If env vars missing, tracing silently disabled (same pattern as `alert.py`)

**Trace structure:**
- One **trace** per worker run (e.g. `email-triage/run_abc123`)
- One **generation** per API call within that trace
- Batched workers (triage does 50-email batches) show multiple generations under one trace

**What you see in LangFuse:** The exact prompt Flash received for email triage, its JSON response, and why it shortlisted or skipped specific emails. Same for the newsletter reader.

### 3. Model Upgrade

**New model lineup:**

| Role | Current | New | Cost |
|------|---------|-----|------|
| Briefing conductor (06:45-07:30) | Haiku 4.5 | **Sonnet 4.6** via OpenRouter | ~$0.13/briefing |
| Rest of day | Flash | **Kimi K2 0711** via OpenRouter | ~$0.01-0.03/day |
| Triage worker | Flash (direct Google AI) | No change | ~$0.02/run |
| Deep-read worker | Haiku (direct Anthropic) | No change | ~$0.08/run |

**Estimated monthly cost:** ~$4-5/month for conductor (up from ~$2.50 Haiku-only), workers unchanged.

**Changes required:**
- `model-swap-local.sh`: add `kimi` tier (`openrouter/moonshotai/kimi-k2`), update `sonnet` tier to `openrouter/anthropic/claude-sonnet-4-6`
- VPS cron: 06:45 → `sonnet`, 07:30 → `kimi`
- `briefing-synthesis.json`: update `default_model` for tracking accuracy
- `model-swap.sh`: mirror the same tier additions for laptop use

**Why Sonnet 4.6:** Massive quality jump over Haiku for reasoning, instruction-following, and synthesis. The briefing task requires reading 9+ data sources, applying judgment, and producing structured output — this is exactly where Sonnet excels over Haiku.

**Why Kimi K2:** 1T params (32B active MoE), 131k context, $0.55/MTok input — great value for general chat, heartbeats, and non-briefing tasks. Cheaper than Flash via OpenRouter, more capable for conversational work.

### 4. Prompt Improvements (LangFuse-informed, iterative)

Rather than guessing at prompt fixes, the plan is:
1. Deploy LangFuse + model upgrades (Sections 1-3)
2. Run for 3-5 days with Sonnet as conductor
3. Review traces in LangFuse daily
4. Iterate on prompts with evidence

**Known issues to validate with traces:**
- `daily-briefing/SKILL.md` is 167 lines with 11 sections — may be competing for attention
- `sift-digest/SKILL.md` is 213 lines — conductor juggles orchestration + presentation + logging + surprise game
- Triage worker only gets INTERESTS.md + TASTE.md, not PRIORITIES.md or GOALS.md
- No examples of good output in any prompt — models benefit from concrete examples

### 5. Daily Review Process (follow-on design)

A daily review ritual where Marvin examines LangFuse traces, rates briefing quality, and captures findings. This will be designed and built as a separate feature after the observability infrastructure lands. Key elements:
- Structured review of that day's briefing trace in LangFuse
- Rating system (quality, relevance, completeness)
- Findings captured and fed back into prompt improvements
- Potentially a review page on the site dashboard

## Env Vars (new)

Added to `/opt/openclaw.env` and passed into sandbox via `docker exec -e`:

```
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com
```

## Files Changed

| File | Change |
|------|--------|
| `workspace/workers/base_worker.py` | Add LangFuse tracing wrapper around `call_model()` |
| `scripts/model-swap-local.sh` | Add `kimi` and `sonnet` tiers, update model IDs |
| `scripts/model-swap.sh` | Mirror tier additions |
| `workspace/tasks/briefing-synthesis.json` | Update `default_model` to `claude-sonnet-4-6` |

## VPS Manual Steps

- [ ] Create LangFuse account + project
- [ ] Enable OpenRouter Broadcast → LangFuse in OpenRouter settings
- [ ] Add `LANGFUSE_*` env vars to `/opt/openclaw.env`
- [ ] Update VPS cron: 06:45 → `sonnet`, 07:30 → `kimi`
- [ ] Restart OpenClaw after cron changes

## Success Criteria

- LangFuse shows full traces for both conductor and worker calls
- Briefing quality visibly improves with Sonnet 4.6 (assessed via daily review)
- Kimi K2 handles general tasks without issues
- Daily cost stays under $0.50 ($15/month)
- Within 1 week, at least 2 concrete prompt improvements identified from trace review
