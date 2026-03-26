# ADR-046: OpenClaw is Jimbo, Not Airflow

## Status

Accepted

## Context

Over 15 briefing review sessions (Mar 4 – Mar 24, 2026), we've oscillated four times between "use OpenClaw for everything" and "bypass OpenClaw with Python scripts":

1. **Monolithic briefing** (sessions 1-11): One OpenClaw cron job composing 6+ sections. Unreliable — model drops sections silently.
2. **Pipeline + monolithic compose** (sessions 2-14): Python data pipeline + one OpenClaw compose. Better data, same compose problem. Model swaps (4 cron entries) added fragility.
3. **Distributed OpenClaw cron** (session 15a): 6 independent OpenClaw cron jobs. First test: 491K input tokens ($0.15/run). Second: 2M tokens. Bootstrap overhead of 100-150K tokens per agent turn makes frequent lightweight jobs economically wrong.
4. **Tiered automation** (session 15b): Accept the tension. Python for mechanical work, OpenClaw for conversation, Opus for creative work.

Each oscillation taught us where the boundary is. This ADR locks in the answer.

### The decisive evidence

- OpenClaw injects 100-150K tokens of bootstrap context (SOUL.md, AGENTS.md, HEARTBEAT.md, TOOLS.md, etc.) on every agent turn. This is by design — rich context is the product.
- A "check email urgency" job that reads a 5K API response still costs 100K+ tokens because of bootstrap. An `if` statement in Python costs zero.
- Running 6+ cron jobs × 100K+ tokens each × multiple times daily = cost explosion (projected $1-5/day vs $0.02-0.07 baseline).
- Persistent sessions compound: 2M tokens on second run because history accumulates.

### The core insight

OpenClaw is a conversational AI platform. It's excellent at: personality, context-aware responses, tool use, two-way interaction with humans, creative work. It is not: a lightweight task scheduler, a cron orchestrator, a message formatter, or a data filter.

## Decision

**One architectural rule: OpenClaw is the conversational shell, not the scheduler for micro-jobs.**

### What OpenClaw owns

- **Jimbo's personality and voice** — the conversational agent Marvin talks to on Telegram
- **Heartbeat nudges** — gym, Spanish, cooking, day-planning (infrequent, context-aware, free model)
- **Interactive sessions** — when Marvin messages Jimbo, Jimbo responds with full context
- **Skill execution on demand** — Marvin asks for a briefing, triage, or review; Jimbo delivers

### What OpenClaw does NOT own

- **Scheduled alerts** — Python scripts + Telegram Bot API. Zero LLM tokens.
- **Data processing** — Python workers in sandbox (email triage, newsletter reading, vault scoring). Cheap Flash API calls where needed.
- **Status formatting** — jimbo-api smart endpoints return pre-formatted messages. Python posts them.
- **Monitoring** — jimbo-api /health endpoint. Python checks and alerts.

### What Opus owns (enhancement tier only)

- **Creative work** — surprise game, blog drafting, deep analysis, weekly review
- **Runs on dedicated Mac** when available. Never a dependency for core daily operation.
- **Results posted to jimbo-api** for Jimbo to reference or dashboard to display.

### The shared state loop is the real product

Not the briefing. Not the surprise game. The system that: detects signals → creates tasks → tracks ownership → acknowledges completion → stops nagging → surfaces status. This loop runs through jimbo-api as shared state, with Python scripts and OpenClaw both reading/writing to it.

## Consequences

### Retired plans and overlapping architecture

- `docs/plans/2026-03-05-briefing-pipeline-redesign-*` — superseded
- `docs/plans/2026-03-24-distributed-briefing-architecture.md` — superseded (same session, early iteration)
- `docs/plans/2026-03-24-tiered-automation-architecture.md` — current reference plan, consistent with this ADR
- `skills/daily-briefing/SKILL.md` — keep but only for on-demand use ("give me a briefing"), not scheduled cron
- OpenClaw cron jobs for email-scanner, calendar-briefing, vault-manager, morning-summary, surprise-game, accountability — all disabled. Skills kept on VPS for potential Opus-routed re-enablement.
- Model-swap cron entries — permanently removed
- Old monolithic briefing cron jobs — permanently disabled

### What becomes easier

- Cost stays near $0.02-0.07/day baseline
- Each job runs on the right tool (Python for filtering, LLM for creativity)
- No model-swap choreography
- No bootstrap overhead for mechanical tasks
- Clear ownership: one place for each rule, not split across skills + Python + plans

### What becomes harder

- Tier 1 Python scripts need building (4 scripts, stdlib only)
- jimbo-api needs smart endpoints for pre-formatted alerts
- Personality is concentrated in OpenClaw conversation, not spread across every alert
- Opus tier depends on always-on Mac (enhancement only, not blocking)

### Expensive anti-patterns to avoid going forward

- Persistent OpenClaw cron sessions for frequent scans
- Many isolated jobs that each pay the bootstrap tax
- Global model-swap choreography
- Asking the briefing prompt to decide, compose, log, monitor, and manage tasks in one turn
- Treating OpenClaw as Airflow/cron when it's a conversational agent

### Cost targets

- Tier 1 (Python + Bot API): $0.00/day
- Tier 2 (OpenClaw heartbeat, Kimi K2): $0.00/day (free model)
- Data pipeline (Flash triage, Haiku reading): $0.02-0.05/day
- email_decision.py: evaluate reducing from */30 to match fetch windows ($0.24/day → less)
- Opus (Max plan): $0.00/day
- **Total target: under $0.10/day**
