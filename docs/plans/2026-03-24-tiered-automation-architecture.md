# Tiered Automation Architecture

**Date:** 2026-03-24 (Session 15)
**Status:** Plan — ready to implement in next session
**Supersedes:** 2026-03-24-distributed-briefing-architecture.md (same session, earlier iteration)
**Depends on:** Dedicated always-on Mac with Opus Max plan (forthcoming)

## The Journey (why this is the third architecture)

### Architecture 1: Monolithic Briefing (sessions 1-11)
One OpenClaw cron job at 07:00 reads a giant `briefing-input.json` and composes everything in one prompt: calendar, email, vault, surprise, day plan, editorial voice. After 14 review sessions, no model reliably did all 6 things. The prompt was 400+ lines asking 15 things — the model did 4-5, dropped the rest.

**Lesson:** One model doing everything = unreliable. The failure mode is silent — sections just disappear.

### Architecture 2: Cron Pipeline + Monolithic Compose (sessions 2-14)
Moved data fetching to system cron (Python scripts in Docker sandbox). `briefing-prep.py` orchestrates gmail-helper, email_triage, newsletter_reader, calendar-helper. Output assembled into `briefing-input.json`. OpenClaw cron still does one monolithic compose.

Added model swaps (4 extra cron entries to swap Kimi→Sonnet→Kimi around briefing windows). Added Opus analysis layer on Mac (broken since Mar 16 — Mac wasn't awake).

**Lesson:** Better data pipeline, same compose problem. Model swaps are fragile. Mac-dependent layers are unreliable.

### Architecture 3: Distributed OpenClaw Cron Jobs (session 15, attempt 1)
Split briefing into 6 independent OpenClaw cron jobs, each with own model, session, delivery. Email-scanner, calendar-briefing, vault-manager, surprise-game, morning-summary, accountability. Eliminated model swaps — each job specifies its own model.

**What went wrong:** First test run of email-scanner used 491K input tokens ($0.15). Second run: 2M tokens (persistent session accumulated history). Root cause: OpenClaw injects 100-150K tokens of bootstrap context (SOUL.md, AGENTS.md, HEARTBEAT.md, TOOLS.md, etc.) on every agent turn, regardless of job. Even with `lightContext: true`, the overhead is significant. Running 6+ jobs × 100K+ tokens each = cost explosion.

**Lesson:** OpenClaw agent turns have a high fixed token cost. Running many small jobs is MORE expensive than one big job because the bootstrap overhead is per-turn, not per-session. The platform is designed for rich, context-aware agent interactions — not lightweight cron scripts.

### Architecture 4: Tiered Automation (this document)
The realisation: most of these jobs DON'T NEED AN LLM. Checking if an email is urgent based on a pre-computed score? That's an `if` statement. Formatting calendar events? That's string concatenation. Only creative work (surprise game, editorial voice, cross-referencing) genuinely needs model intelligence.

**The tension we keep hitting:** We want to work with OpenClaw's capabilities, but the platform's per-turn cost model fights against frequent lightweight automation. We keep oscillating between "use OpenClaw for everything" and "bypass it with Python scripts." This plan accepts the tension and puts each job in its correct tier.

## The Tiered Model

### Tier 1: Python Scripts + Telegram Bot API (zero LLM cost)

Mechanical jobs that filter pre-processed data and format output. Run on system cron. Post directly to Telegram via Bot API (using existing `alert.py` pattern). No OpenClaw agent turn, no LLM tokens.

| Script | Schedule | What it does | Data source |
|--------|----------|-------------|-------------|
| `email-alert.py` | Every 2h (06-20) | Filters insights by urgency, posts top 2-3 | jimbo-api `/api/emails/reports` |
| `calendar-alert.py` | 07:00 + 14:00 | Formats confirmed vs options events | `calendar-helper.py` output |
| `vault-status.py` | 08:00 | One-liner: active/inbox/velocity/focus | jimbo-api `/api/vault/stats` + `/api/vault/tasks` |
| `morning-status.py` | 07:30 | 5-line health summary | jimbo-api `/api/health` |

**Pattern:** Each script is stdlib Python only (no pip). Reads from jimbo-api or sandbox tools. Formats a short message. Posts via Telegram Bot API. Logs to activity-log. Prefixes output with `[Email]`, `[Calendar]`, `[Vault]`, `[Morning]` so Marvin knows the source.

**Why not OpenClaw:** These jobs are deterministic. An LLM reading "relevance_score: 9, time_sensitive: true" and outputting "this is urgent" adds cost without adding value. Python does it for free.

**New jimbo-api endpoints needed:**
- `GET /api/alerts/email` — returns pre-formatted urgent email items (saves Python from reimplementing filter logic)
- `GET /api/alerts/calendar` — returns today's events formatted as confirmed + options
- `GET /api/alerts/vault` — returns one-liner vault status
- `GET /api/alerts/morning` — returns formatted morning summary from health data

These "smart endpoints" push formatting logic into jimbo-api, making the Python scripts trivially simple (fetch + post to Telegram).

### Tier 2: OpenClaw + Free Models (zero or near-zero cost)

Jobs that benefit from conversational context, personality, or interaction with Marvin. Run on Kimi K2 (free via OpenRouter) through OpenClaw's heartbeat or conversation.

| Job | Trigger | What it does |
|-----|---------|-------------|
| Heartbeat nudges | Every 30min | Gym, Spanish, cooking reminders (already working) |
| Conversational responses | On message | Marvin talks to Jimbo, Jimbo responds |
| Day planning | Heartbeat, 09:00-18:00 | Suggests how to use free gaps |

**Why OpenClaw:** These need personality, context awareness, and two-way interaction. The bootstrap overhead is acceptable because they're infrequent and Kimi K2 is free.

**HEARTBEAT.md slimmed to:** Output discipline + day planning nudge + hobby nudges only. Email check-ins, end-of-day review, blog nudge all removed (handled by other tiers).

### Tier 3: Opus on Dedicated Mac (free, creative work)

Jobs that need genuine intelligence — cross-referencing, pattern recognition, editorial voice, creativity. Run on always-on Mac via `claude -p` (Opus, free via Max plan). Results posted to jimbo-api for Jimbo to reference or for dashboard display.

| Job | Schedule | What it does |
|-----|----------|-------------|
| Surprise game | Daily 09:30 (or on-demand from dashboard) | Cross-references gems + vault + interests |
| Weekly accountability | Sunday 20:00 | Pattern analysis across the week |
| Blog drafting | Weekly or on-demand | Reads interesting gems, drafts posts |
| Deep briefing analysis | On-demand | Opus reads all data, produces editorial briefing |

**Why Opus:** These are the jobs where model quality actually matters. Surprise game requires genuine creativity. Accountability requires pattern recognition across days. Blog drafting requires voice and opinion. Opus on Max plan is free and extremely capable.

**Architecture:**
```
Mac (always-on, launchd):
  opus-jobs.sh → pulls data from jimbo-api
               → runs claude -p with focused prompt
               → POSTs result to jimbo-api endpoint
               → jimbo-api stores result
               → optional: jimbo-api triggers Telegram notification
```

**Dependency:** This tier requires the dedicated always-on Mac. Until then, surprise game and accountability are available as manual triggers from the site dashboard.

### Tier 4: Dashboard On-Demand (free, manual)

Actions Marvin triggers from the site dashboard (`/app/jimbo/`). No scheduled automation — Marvin decides when.

| Action | What it does |
|--------|-------------|
| Trigger surprise game | Calls Opus (Tier 3) or displays pre-computed result |
| Trigger accountability | Calls Opus (Tier 3) or shows health dashboard |
| Vault triage session | Interactive review of inbox/needs-context items |
| Briefing review | Shows today's data with Opus analysis |

**Why dashboard:** Some things don't need to be automated. Marvin checking in when he wants is better than another Telegram notification.

## System Cron (revised)

```
04:30  prioritise-tasks.py          — vault task scoring (Flash, keep)
05:00  tasks-helper.py sweep        — Google Tasks intake (keep)
05:45  email-fetch + triage + read  — data pipeline (keep, adjust timing)
06:00  email-alert.py               — Tier 1: urgent email to Telegram (NEW)
07:00  calendar-alert.py            — Tier 1: calendar summary (NEW)
07:30  morning-status.py            — Tier 1: health summary (NEW)
08:00  vault-status.py              — Tier 1: vault one-liner (NEW)
13:45  email-fetch + triage + read  — afternoon data pipeline (keep)
14:00  calendar-alert.py            — Tier 1: afternoon calendar (NEW)
*/2h   email-alert.py               — Tier 1: email scanning (NEW)
*/30   email_decision.py            — email decisions (keep)
```

Model swaps: REMOVED (no longer needed — Tier 1 has no LLM, Tier 2 uses Kimi always).
Accountability.sh: REMOVED (replaced by Tier 3 or Tier 4).
briefing-prep.py: KEEP for now (still feeds data pipeline), evaluate removing once Tier 1 scripts read jimbo-api directly.

## OpenClaw Cron Jobs (revised)

All 6 new jobs currently **disabled** (created but paused). The 2 old monolithic jobs also disabled.

When Tier 3 (Opus Mac) is available, we'll re-enable surprise-game and accountability as OpenClaw cron jobs with `--model opus` routing through the Mac, OR keep them as Opus scripts outside OpenClaw.

## What We Learned About OpenClaw

1. **Agent turns are expensive.** 100-150K tokens of bootstrap context per turn is the floor. This is by design — OpenClaw agents are context-rich. It's a feature for conversational AI, but a cost problem for lightweight cron.

2. **Persistent sessions compound cost.** Each turn's history stays in context. A persistent session running 8x/day accumulates megabytes of context.

3. **OpenClaw is best for:** Rich conversational interactions (Marvin ↔ Jimbo), personality-driven output, creative work, tool-using agents. These justify the bootstrap overhead.

4. **OpenClaw is NOT best for:** Frequent lightweight alerts, deterministic filtering, formatted status reports. These are cheaper as Python scripts.

5. **The platform is the pipeline — but not every step needs the platform.** Data processing (Python) → smart endpoints (jimbo-api) → formatted alerts (Bot API) → creative overlay (OpenClaw/Opus).

6. **We're not fighting OpenClaw.** We're using it for what it's good at (conversation, creativity, tool use) and using simpler tools for what they're good at (filtering, formatting, scheduling). This is correct architecture, not a workaround.

## Migration Checklist

### Done (this session)
- [x] Upgraded OpenClaw 2026.3.1 → 2026.3.23-2
- [x] Ran doctor --fix, added startup optimizations
- [x] Created 6 skills (email-scanner, calendar-briefing, vault-manager, surprise-game, morning-summary, accountability)
- [x] Pushed skills to VPS
- [x] Created 6 OpenClaw cron jobs (all now disabled pending Tier 1 Python replacement)
- [x] Disabled 2 old monolithic briefing cron jobs
- [x] Removed 4 model-swap + 1 accountability system cron entries
- [x] Discovered voice-call plugin has native Twilio support
- [x] Confirmed token cost problem with OpenClaw cron approach

### Next session: Tier 1 Python scripts
- [ ] Build `email-alert.py` (stdlib, reads jimbo-api, posts to Telegram)
- [ ] Build `calendar-alert.py` (stdlib, reads calendar-helper output, posts to Telegram)
- [ ] Build `vault-status.py` (stdlib, reads jimbo-api, posts to Telegram)
- [ ] Build `morning-status.py` (stdlib, reads jimbo-api health, posts to Telegram)
- [ ] Add smart endpoints to jimbo-api (`/api/alerts/*`)
- [ ] Add system cron entries for Tier 1 scripts
- [ ] Slim HEARTBEAT.md (remove email, end-of-day, blog nudge)
- [ ] Test full morning cycle

### When dedicated Mac is available: Tier 3
- [ ] Set up always-on Mac with `claude -p` access
- [ ] Build `opus-jobs.sh` (revised from broken original)
- [ ] Add jimbo-api endpoints for Opus results
- [ ] Wire surprise game + accountability through Opus
- [ ] Evaluate: re-enable OpenClaw cron jobs with Opus routing, or keep as Mac scripts?

### Future: Tier 4 Dashboard
- [ ] Add "trigger surprise game" button to site dashboard
- [ ] Add "trigger accountability" button
- [ ] Add "trigger deep briefing" button
- [ ] Wire buttons to Tier 3 (Opus) or Tier 2 (Kimi) backends

### Future: Twilio Voice
- [ ] Get Twilio phone number (US for simplicity)
- [ ] Add voice-call plugin config to openclaw.json
- [ ] Wire critical alert escalation: Telegram → 30min unacknowledged → phone call

## Open Questions

1. **briefing-prep.py:** Still running at 06:15/14:15 assembling briefing-input.json. Tier 1 scripts will read jimbo-api directly. Once all Tier 1 scripts are working, can we remove briefing-prep.py entirely, or do other things depend on briefing-input.json?

2. **Afternoon scope:** Do we replicate the full morning Tier 1 sequence in the afternoon, or just email-alert + calendar-alert?

3. **Opus routing through OpenClaw:** When the dedicated Mac is ready, should Opus jobs run as OpenClaw cron (gets skill/tool ecosystem) or as standalone `claude -p` scripts (simpler, no bootstrap overhead)? Need to test Opus token costs with `lightContext`.

4. **Dashboard trigger architecture:** Should dashboard buttons call jimbo-api which triggers Opus, or should they call OpenClaw directly via the gateway API? The gateway API approach gets tool access but has the bootstrap overhead.

5. **Kimi K2 reliability:** Kimi leaked heartbeat reasoning in session 14. The output discipline fix may not stick. Should we test with a different free model, or accept occasional leaks?

6. **Email-decision worker:** The `*/30` cron running `email_decision.py` costs ~$0.005 per run (Flash). 48 runs/day = $0.24. Is this still needed if Tier 1 email-alert.py handles urgency filtering? Evaluate overlap.
