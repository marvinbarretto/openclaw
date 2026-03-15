# Briefing Review History

Living document. Updated after each review session. Replaces the March 3 audit doc as the "what we know" reference.

## The Arc

### Session 1 — 2026-03-04 (Baseline)

First review. Sonnet 4.6 briefing. Vault tasks section was the breakout — pre-scoring from `prioritise-tasks.py` worked. Email section starved (2 of 44, both junk). Calendar 403. Logging completely dead. Triage worker had no priorities/goals context.

**Key actions:** Updated PRIORITIES.md for LocalShout focus. Created EMAIL_EXAMPLES.md with 10 calibrated examples. Fixed Calendar API. Added context files to both workers.

### Session 2 — 2026-03-05 (Architecture Crisis)

Workers never spawned. Calendar mixed real and fabricated entries. Jimbo contradicted himself on monitoring. Core insight: 400+ lines of skill prompts asking 15 things — Jimbo reliably does 4-5, drops the rest.

**Decision:** Move worker orchestration to cron (Option A) + add Opus analysis layer via Mac (Option C). Cron handles plumbing, Opus handles thinking, Jimbo handles delivery.

### Session 3 — 2026-03-06 (First Cron Run)

Triple briefing due to false "morning: missing" alert. Email quality breakthrough — Wizz Air deal, travel context, artist gigs — even without worker pipeline. Calendar still broken (stale data, then fabricated). Geography context missing.

**Pattern:** Email quality improving through context files alone. Calendar consistently worst section.

### Session 4 — 2026-03-07 (Visibility Gap)

Pipeline ran on cron for the first time. Experiment tracker logged. But dashboard empty — sandbox SQLite doesn't talk to jimbo-api. Calendar had 12 real events in JSON but Jimbo said "helper returned nothing."

**Decision:** jimbo-api as single source of truth. Migrate activity, costs, experiments from sandbox SQLite to API endpoints.

### Session 5 — 2026-03-08 (Breakthrough)

No real briefing delivered. Flash shortlisted 0 emails for the 5th consecutive session. OpenRouter 403 mid-day. Experiment: pulled briefing-input.json, ran Opus via `claude -p` on Mac (free via Max plan). Best briefing in 5 sessions — YNAB trial, Watford Women, London Theatre Week, specific dev roles, Agora Debate surprise.

**Realisation:** The multi-stage pipeline was the problem. One capable model reading everything in one pass beats a pipeline of cheaper models. Disabled VPS briefing delivery, kept silent data collection, compose with Opus locally.

### Session 6 — 2026-03-15 (The Opus Pipeline Was Never Wired Up)

Flash self-compose briefing. Calendar fabrication back (F1, Premier League, Mother's Day added from general knowledge). Email bypasses pipeline's scored insights. Day plan was the best non-Opus version yet. But Marvin spotted immediately it wasn't Opus.

**Root cause:** `opus-briefing.sh` used `/workspace/` (sandbox path) instead of `/home/openclaw/.openclaw/workspace/` (host path) in SSH commands. Silent `|| exit 0` on every line meant 10 days of invisible failure. Fix applied.

**Pattern:** Silent failures are the worst failures. `|| exit 0` optimised for resilience over observability.

## Current Architecture (as of 2026-03-15)

```
VPS (always on):
  briefing-prep.py (cron 06:15 + 14:15) → briefing-input.json
    - gmail-helper.py fetch
    - email_triage.py (Flash)
    - newsletter_reader.py (Haiku)
    - calendar-helper.py
    - vault task selection
  jimbo-api → dashboard, context, settings, activity, costs, experiments

Mac (optional):
  opus-briefing.sh (launchd) → pulls briefing-input.json
    → claude -p (Opus via Max plan) → briefing-analysis.json
    → pushes back to VPS

Jimbo (Telegram):
  Reads briefing-input.json + optional briefing-analysis.json
  Two modes: Opus-assisted delivery or self-compose from raw data
  Lightweight assistant on Step 3.5 Flash (free) outside briefing windows
```

## Resolved Issues

| Issue | Resolution | Session |
|-------|-----------|---------|
| Triage worker lacks priorities/goals | Added PRIORITIES.md + GOALS.md + EMAIL_EXAMPLES.md to workers | 1 |
| No calibration examples | Created EMAIL_EXAMPLES.md | 1 |
| Calendar API 403 | Re-enabled in Google Cloud Console | 1 |
| Telegram status noise | Sandbox checks suppressed | 1 |
| Experiment tracker empty DB | Recreated with proper schema | 1 |
| Skills not deployed to VPS | Ran skills-push.sh | 1 |
| Skill too complex (400+ lines) | Cron pipeline + slim skill | 2 |
| False "morning: missing" alerts | Fixed in alert-check.py | 3 |
| Dashboard empty (SQLite island) | Migrated to jimbo-api endpoints | 4 |
| Multi-stage pipeline producing nothing | Switched to single-model Opus composition | 5 |
| OpenRouter cost burn ($10+/week) | Disabled, using free Opus via Max plan | 5 |
| Opus pipeline silently broken | Wrong SSH path (`/workspace/` vs host path). Fixed both read and write paths. | 6 |

## Open Issues

| Issue | Notes |
|-------|-------|
| Flash triage calibration | 0 shortlisted across 7 sessions. Worker runs but rejects everything. |
| Calendar fabrication in self-compose mode | Jimbo ignores structured JSON data or invents entries. Works when Opus handles it. |
| Vault tasks stale | Same items surfaced repeatedly. Scorer may not differentiate well at top of range. |
| daily-briefing skill references conductor-rating | Legacy field from the conductor era. Still in skill prompt but concept is retired. |
| Opus layer Mac-dependent | If Mac is asleep, no briefing-analysis.json. Jimbo falls back to self-compose (lower quality). |
| No mechanism to rate briefings retroactively | Experiment tracker has user_rating field but no UI or workflow to use it. |

## Patterns (Across All Sessions)

- **One good model > pipeline of cheap models.** Opus in one pass consistently beats Flash → Haiku → Sonnet pipeline.
- **Email quality correlates with context, not architecture.** Adding PRIORITIES.md and EMAIL_EXAMPLES.md improved email picks more than any pipeline change.
- **Calendar is the most failure-prone section.** Five sessions, five different failure modes.
- **Personality and voice are consistent and valued.** Jimbo's editorial voice is a feature, not a bug.
- **Visibility enables improvement.** We couldn't improve what we couldn't see. The API migration unblocked real evaluation.
- **Monitoring can make things worse.** False alerts triggered triple briefings. Heartbeat burned tokens for "no nudge needed." Sometimes less is more.
- **Silent failures are the worst failures.** `|| exit 0` patterns hide bugs for days/weeks. A single error log line would have caught the Opus path bug on day one.
- **Path confusion (sandbox vs host) is a recurring trap.** `/workspace/` means different things inside Docker vs on the VPS host.
