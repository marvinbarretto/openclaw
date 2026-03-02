# ADR-039: OpenClaw v2026.3.1 Upgrade and Native Feature Adoption

## Status

Accepted

## Context

Jimbo was running on OpenClaw v2026.2.12 with several custom solutions for problems the platform now solves natively:

1. **Worker pipeline wrote to `/tmp/`** — which doesn't persist between Docker exec calls, silently breaking the entire email triage → gems → briefing pipeline
2. **No model delegation** — Haiku ran 24/7 with no time-based switching
3. **No accountability loop** — no automated check of whether Jimbo actually did things each day
4. **Custom Python workers** called external APIs (Flash, Haiku) directly from the sandbox, requiring API keys inside the container
5. **No memory** — every session started from scratch with no recall of past interactions
6. **No native health monitoring** — couldn't detect if the OpenClaw gateway itself was down

v2026.3.1 introduces native cron, sub-agents, memory-core plugin, health endpoints, and secrets management.

## Decision

### Phase 1: Fix root failures (no upgrade needed)

- Change worker output paths from `/tmp/` to `/workspace/.worker-*.json` (persistent Docker volume)
- Make experiment-tracker logging mandatory in sift-digest (even in fallback mode)
- Replace silent fallback with explicit failure reporting

### Phase 2: Model delegation

- Create `model-swap-local.sh` for VPS crontab use (the existing script SSHes from laptop)
- Cron switches to Haiku at 06:45 UTC (briefing window), Flash at 07:30 UTC
- Add cost-awareness guidance to HEARTBEAT.md
- Add `model` subcommand to `alert-check.py` (reports current model in hourly status)

### Phase 3: Accountability loop

- New `accountability-check.py` runs at 20:00 UTC via cron
- Checks 6 dimensions: briefing ran, gems produced, surprise game played, vault tasks surfaced, activity count, cost
- Sends Telegram summary
- Daily briefing now logs structured `--outcome` and `--rationale` to activity-log for the accountability checker to read

### Phase 4: Upgrade to v2026.3.1

- Upgrade via `openclaw update`
- Run `openclaw doctor` — applied config repairs, tightened permissions
- Add `openclaw` health check to `alert-check.py` (TCP probe to gateway port from sandbox)

### Phase 5: Adopt native sub-agents

- Sub-agents already configured in openclaw.json (`subagents.maxConcurrent: 8`)
- Created `email-triage-worker` and `newsletter-reader-worker` skills (SKILL.md format)
- Updated `sift-digest` to spawn sub-agents first, fall back to Python workers if spawn fails
- Python workers remain in repo as fallback — not deleted

### Phase 6: Enable memory system

- `memory-core` plugin auto-loaded on upgrade (FTS5 + vector search, SQLite-backed)
- Memory compaction already configured (flushes to memory files before context window compacts)
- Wired memory search into SOUL.md, daily-briefing, and HEARTBEAT.md
- Added blog nudge to end-of-day review

## Consequences

### What gets better

- Worker pipeline actually works (persistent output files)
- Hourly status messages include gateway health and current model
- Daily accountability report creates feedback pressure
- Model costs drop ~$3-4/month (Flash outside briefing window)
- Sub-agents route through OpenClaw's model management (no direct API calls needed from sandbox for worker tasks)
- Memory builds across sessions — briefings improve over time
- Jimbo blogs more (end-of-day nudge)

### What gets harder / riskier

- Sub-agent worker pipeline uses LLM tokens through OpenClaw instead of direct API calls — potentially different cost profile (needs monitoring)
- Python workers are now fallback, not primary — two code paths to maintain
- Memory system needs time to accumulate useful data
- Model-swap cron adds complexity — if cron fails, Jimbo stays on wrong model

### What we chose NOT to do

- Did not migrate secrets (existing `${ENV_VAR}` interpolation works fine)
- Did not delete Python workers (kept as fallback)
- Did not set up MCP servers (worth re-evaluating now that v2026.3.1 may support them)
- Did not remove worker API keys from sandbox yet (wait for sub-agent pipeline to prove reliable)

### Future work

- Monitor sub-agent vs Python worker cost comparison over 2 weeks
- Once sub-agents are proven reliable, retire `GOOGLE_AI_API_KEY` and `ANTHROPIC_API_KEY` from sandbox docker.env
- Populate memory with seed data from past briefings
- Re-evaluate MCP support in v2026.3.1
