# Distributed Briefing Architecture

**Date:** 2026-03-24 (Session 15)
**Status:** Active — Phase 1 implementation
**Supersedes:** 2026-03-05-briefing-pipeline-redesign, monolithic daily-briefing skill

## Problem

The daily briefing tries to do 6+ things in one LLM pass: calendar summary, day plan, email curation, surprise game, vault tasks, editorial voice. After 14 review sessions, no single model reliably nails all of them. The system asks one prompt to be a calendar analyst, email curator, creative surprise generator, task manager, and editorial writer simultaneously.

Meanwhile:
- Jimbo is awake 24/7 but mostly silent
- OpenClaw supports isolated cron jobs with per-job models, persistent sessions, and direct delivery
- We're running 8 system cron entries (Python scripts) outside OpenClaw, then cramming output into one compose prompt
- Model swaps require 4 extra cron entries just to change the global model for briefing windows

**Core insight:** Each briefing subtask is a serious job deserving its own model, token budget, schedule, and retry policy. The platform is the pipeline — we've been working against it.

## Current Architecture (being replaced)

```
System cron:
  04:30  prioritise-tasks.py          → score vault tasks (Flash)
  05:00  tasks-helper.py sweep        → Google Tasks → vault
  06:15  briefing-prep.py morning     → runs ALL workers, assembles briefing-input.json
    ├── gmail-helper.py fetch         → Gmail API → email-digest.json
    ├── email_triage.py               → Flash triages → shortlist
    ├── newsletter_reader.py          → Haiku deep-reads → gems
    ├── calendar-helper.py            → Calendar API → events
    └── vault task selection          → top priority tasks
  06:45  model-swap-local.sh sonnet   → swap to Sonnet
  07:30  model-swap-local.sh kimi     → swap back to Kimi
  14:15  briefing-prep.py afternoon   → same as morning
  14:45  model-swap-local.sh sonnet
  15:30  model-swap-local.sh kimi
  20:00  accountability.sh
  */30   email_decision.py            → Flash email decisions

OpenClaw cron:
  07:00  "Read and follow daily-briefing SKILL.md" → monolithic compose
  15:00  same for afternoon

HEARTBEAT.md (every 30min):
  - Email check-ins 3x/day
  - Day planning nudge
  - End-of-day review + blog nudge
  - Hobby nudges
  - Afternoon briefing reference
```

**Problems with this:**
- briefing-prep.py is a Python pipeline outside OpenClaw — no retry, no model choice, no session context
- One compose prompt drops 2-3 sections every time
- Model swaps are fragile (4 cron entries, race conditions)
- HEARTBEAT.md is overloaded — mixes monitoring, nudges, composition, and review
- Jimbo does nothing between briefings except heartbeat checks

## New Architecture

### Principle

Each job is an independent OpenClaw cron task with:
- Its own **model** (right tool for the job)
- Its own **session** (isolated or persistent)
- Its own **delivery** (announce to Telegram, or voice-call for critical)
- Its own **schedule** (when it matters, not batched)
- `lightContext: true` where full bootstrap isn't needed

### Phase 1: Core Jobs

#### 1. email-scanner

| Field | Value |
|-------|-------|
| Schedule | `0 6,8,10,12,14,16,18,20 * * *` (every 2h, 06:00-20:00) |
| Model | `gemini-2.5-flash` (cheap, fast) |
| Session | `session:email` (persistent — remembers what it flagged) |
| Context | `lightContext: true` |
| Delivery | `announce` to Telegram |

**Behaviour:** Runs `gmail-helper.py fetch --hours 4`, reads the digest, checks jimbo-api for already-flagged items. Surfaces only urgent/time-sensitive items immediately. Stays silent if nothing notable.

**Replaces:** HEARTBEAT.md email check-ins (3x/day), plus adds proactive scanning.

**Skill:** `skills/email-scanner/SKILL.md` — focused prompt for email triage + surfacing.

#### 2. calendar-briefing

| Field | Value |
|-------|-------|
| Schedule | `0 7,14 * * *` (07:00 + 14:00) |
| Model | `anthropic/claude-haiku-4.5` |
| Session | `isolated` |
| Context | `lightContext: true` |
| Delivery | `announce` to Telegram |

**Behaviour:** Runs `calendar-helper.py list-events --days 1 --whitelist`, reads events with tags. Composes a short calendar summary: confirmed events, options worth noting, conflicts, time gaps. No editorial — just the facts.

**Replaces:** Calendar section of monolithic briefing.

**Skill:** `skills/calendar-briefing/SKILL.md`

#### 3. vault-manager

| Field | Value |
|-------|-------|
| Schedule | `0 8 * * *` (08:00 daily) |
| Model | `anthropic/claude-haiku-4.5` |
| Session | `session:vault` (persistent — tracks what was surfaced) |
| Context | `lightContext: true` |
| Delivery | `announce` to Telegram |

**Behaviour:** Reads vault tasks from jimbo-api (`/api/vault/tasks?sort=priority&limit=10`). Compares to previous session's surfaced items. Reports: new items, status changes, velocity, what's stale. Proposes "today's focus" from top-priority actionable items.

**Replaces:** Task section of monolithic briefing. Eventually becomes the task handoff system (Phase 2).

**Skill:** `skills/vault-manager/SKILL.md`

#### 4. surprise-game

| Field | Value |
|-------|-------|
| Schedule | `30 9 * * *` (09:30 daily) |
| Model | `anthropic/claude-haiku-4.5` or Sonnet (evaluate) |
| Session | `isolated` |
| Context | full (needs TASTE.md, PREFERENCES.md, SOUL.md for personality) |
| Delivery | `announce` to Telegram |

**Behaviour:** Reads today's gems from briefing-input.json (or jimbo-api), cross-references with vault tasks, priorities, interests via context-helper.py. Finds one non-obvious connection. Presents it with personality and editorial voice.

**Replaces:** Surprise section of monolithic briefing.

**Skill:** `skills/surprise-game/SKILL.md` — needs proper definition of "delight" (session 8 open issue).

#### 5. morning-summary

| Field | Value |
|-------|-------|
| Schedule | `30 7 * * *` (07:30 — after calendar + email-scanner) |
| Model | `anthropic/claude-haiku-4.5` |
| Session | `isolated` |
| Context | `lightContext: true` |
| Delivery | `announce` to Telegram |

**Behaviour:** Reads jimbo-api health endpoint + today's cron run results. Composes a 5-line status:
- Calendar shape (N events, key ones)
- Email highlights (N flagged, top 1-2)
- Vault focus (today's suggested task)
- Any issues (pipeline failures, stale data)
- Day shape ("Wide open until 6pm" / "Packed — protect lunch")

This is a **report on completed work**, not where the work happens.

**Replaces:** The entire monolithic daily-briefing skill for morning.

**Skill:** `skills/morning-summary/SKILL.md`

#### 6. accountability

| Field | Value |
|-------|-------|
| Schedule | `0 20 * * *` (20:00 UTC) |
| Model | `gemini-2.5-flash` (cheap) |
| Session | `isolated` |
| Context | `lightContext: true` |
| Delivery | `announce` to Telegram |

**Behaviour:** Reads jimbo-api `/api/health`, `/api/activity?days=1`, `/api/costs/summary?days=1`. Reports: what ran, what didn't, activity count, cost, vault velocity, any patterns.

**Replaces:** `accountability.sh` + `accountability-check.py` system cron.

**Skill:** `skills/accountability/SKILL.md`

### Phase 2: Enhanced (later)

- **task-creator** — Standing order: create vault tasks from email signals, calendar events, conversation
- **blog-drafter** — Weekly cron, Opus model, reads interesting gems + vault connections, drafts posts
- **twilio-escalation** — Critical alerts (briefing failed, budget exceeded, gateway down) → phone call via voice-call plugin
- **conversational-handoff** — "I'll take this" / "you do it" / "done" protocol via Telegram
- **hobby-nudger** — Separate from heartbeat, custom session tracks what was nudged today

### System Cron Changes

**KEEP** (data fetching — these talk to external APIs, not LLM work):
- `04:30` prioritise-tasks.py (vault scoring)
- `05:00` tasks-helper.py sweep (Google Tasks intake)
- `*/30` email_decision.py (Flash email decisions — evaluate if still needed)

**KEEP but ADJUST:**
- gmail-helper.py fetch — move to run before email-scanner (05:30 + on-demand)
- email_triage.py + newsletter_reader.py — keep as data processing, but trigger less often
- calendar-helper.py — runs on-demand from calendar-briefing skill

**REMOVE:**
- `06:15` briefing-prep.py morning (replaced by individual cron jobs)
- `14:15` briefing-prep.py afternoon (same)
- `06:45` / `07:30` / `14:45` / `15:30` model-swap-local.sh (4 entries — each job picks its own model)
- `20:00` accountability.sh (replaced by OpenClaw cron)

**ADD:**
- `05:45` gmail-helper.py fetch + email_triage.py + newsletter_reader.py (early morning data prep)
- `13:45` same for afternoon

### HEARTBEAT.md Changes

**KEEP:**
- Output discipline rules (CRITICAL section)
- Day planning nudge (09:00-18:00, max 2/day)
- Hobby nudges (time-appropriate, max 2-3/day)
- Cost awareness

**REMOVE:**
- Email check-ins → replaced by email-scanner cron
- End-of-day review → replaced by accountability cron
- Blog nudge → Phase 2 blog-drafter cron
- Afternoon briefing reference → replaced by afternoon cron jobs
- Memory end-of-day → evaluate if needed

### Standing Orders (AGENTS.md additions)

```markdown
## Standing Orders

### Task Creation
Jimbo MAY create vault tasks from:
- Email signals flagged as actionable
- Calendar events that need preparation
- Conversation context when Marvin says "add this" or "track this"

Approval: none needed for creation. Marvin reviews via vault-manager daily.

### Task Completion
Jimbo MAY mark tasks as done when:
- Marvin explicitly confirms ("done", "handled", "sorted")
- Automated verification passes (e.g., deploy succeeded)

Approval: none for marking done. Never delete vault items.

### Blog Drafting
Jimbo MAY draft blog posts about:
- Interesting gems from email digest
- Vault/priority connections
- System observations and patterns

Approval: drafts only. Never publish without Marvin's review.

### Escalation Boundaries
- NEVER send external emails
- NEVER delete vault items
- NEVER modify calendar events without explicit confirmation
- NEVER spend more than $1/day without alerting
- Critical failures → Telegram alert → if unacknowledged 30min → Twilio call
```

### Voice-Call Plugin (Twilio)

Add to `openclaw.json`:
```json
{
  "plugins": {
    "entries": {
      "voice-call": {
        "enabled": true,
        "provider": "twilio",
        "twilio": {
          "accountSid": "${TWILIO_ACCOUNT_SID}",
          "authToken": "${TWILIO_AUTH_TOKEN}"
        },
        "fromNumber": "${TWILIO_FROM_NUMBER}",
        "toNumber": "${TWILIO_TO_NUMBER}",
        "inboundPolicy": "allowlist",
        "allowFrom": ["${TWILIO_TO_NUMBER}"],
        "outbound": {
          "defaultMode": "notify"
        }
      }
    }
  }
}
```

Caddy needs a route for voice-call webhooks (port TBD from `serve.port` config).

## Migration Checklist

### Pre-migration
- [x] Backup VPS state
- [x] Upgrade OpenClaw to 2026.3.23
- [x] Run doctor --fix
- [ ] Verify service healthy after upgrade

### Phase 1a: Create skills (parallel)
- [ ] Write `skills/email-scanner/SKILL.md`
- [ ] Write `skills/calendar-briefing/SKILL.md`
- [ ] Write `skills/vault-manager/SKILL.md`
- [ ] Write `skills/surprise-game/SKILL.md`
- [ ] Write `skills/morning-summary/SKILL.md`
- [ ] Write `skills/accountability/SKILL.md`
- [ ] Push skills to VPS via skills-push.sh

### Phase 1b: Add OpenClaw cron jobs (one at a time, verify each)
- [ ] Add email-scanner cron job
- [ ] Verify it runs and announces correctly
- [ ] Add calendar-briefing cron job
- [ ] Add vault-manager cron job
- [ ] Add surprise-game cron job
- [ ] Add morning-summary cron job
- [ ] Add accountability cron job

### Phase 1c: Remove old infrastructure
- [ ] Disable morning briefing OpenClaw cron (the monolithic one)
- [ ] Disable afternoon briefing OpenClaw cron
- [ ] Remove model-swap cron entries (4 lines)
- [ ] Remove accountability.sh cron entry
- [ ] Slim HEARTBEAT.md
- [ ] Update AGENTS.md with standing orders
- [ ] Keep briefing-prep.py but stop running it (data scripts still useful)

### Phase 1d: Twilio voice-call
- [ ] Add voice-call plugin config to openclaw.json
- [ ] Add Twilio env vars to /opt/openclaw.env
- [ ] Configure Caddy webhook route
- [ ] Test outbound notify call
- [ ] Wire critical alert escalation

### Post-migration monitoring
- [ ] Watch jimbo-api /health for 3 days
- [ ] Verify each cron job runs on schedule
- [ ] Check Telegram for appropriate delivery (not too noisy, not silent)
- [ ] Verify persistent sessions work (email-scanner remembers, vault-manager tracks)
- [ ] Review costs (should decrease — lightContext + cheap models)

## Cost Estimate

| Job | Model | Runs/day | Est. tokens/run | Est. cost/day |
|-----|-------|----------|-----------------|---------------|
| email-scanner | Flash | 8 | ~5K | $0.01 |
| calendar-briefing | Haiku | 2 | ~3K | $0.01 |
| vault-manager | Haiku | 1 | ~5K | $0.005 |
| surprise-game | Haiku | 1 | ~10K | $0.01 |
| morning-summary | Haiku | 1 | ~3K | $0.005 |
| accountability | Flash | 1 | ~5K | $0.005 |
| **Total** | | **14** | | **~$0.05/day** |

Current cost: ~$0.02-0.07/day. Should remain similar or decrease due to lightContext reducing token overhead.

## Open Questions

1. **Data pipeline timing:** email-scanner needs fresh data. Should gmail-helper.py fetch run as part of the cron job (sandbox exec from skill), or on a separate system cron slightly before?
2. **Afternoon scope:** Do we replicate all 6 jobs for afternoon, or just calendar + email-scanner + a shorter summary?
3. **Opus layer:** With jobs having their own models, is the Mac Opus layer still needed? Could be a weekly "deep review" cron instead.
4. **Session persistence limits:** How long do custom session contexts persist? Need to verify `cron.sessionRetention` settings.
5. **Noise control:** 6 separate Telegram messages vs 1 briefing. Is that better or worse? May need a "digest" mode later.
