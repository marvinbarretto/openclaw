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

### Session 7 — 2026-03-16 (Going With the Flow)

Opus pipeline worked for the first time (path fix from session 6). Excellent analysis sitting on VPS. Flash ignored it completely — fabricated 3 calendar events, missed CCCL #4 (most important event), stalled for 2 hours. Widest gap between available and delivered quality.

Marvin stepped back: "I'm not sure that's the point of OpenClaw." Researched showcase + awesome-usecases. Realised we'd been fighting the platform — asking a free model to do one-shot composition when OpenClaw is built for step-by-step tool use.

**Decision:** Opus publishes structured analysis to jimbo-api (not files). Jimbo fetches via API, delivers section-by-section, stays as full conversational agent. Opus owns thinking, Jimbo owns voice + actions. Design spec: `docs/superpowers/specs/2026-03-16-briefing-api-delivery-design.md`

Also: cleaned up stale memory files causing incorrect assumptions across sessions.

**Implementation:** Built and deployed API endpoint, rewrote opus-briefing.sh + skill + prompts. Live testing revealed a Docker bind mount (`/usr/lib/node_modules/openclaw/skills`) was hiding all custom skills for 7 sessions. After removing it, Flash produced the best non-Opus briefing yet — real calendar data, no fabrication, relevant email highlights. Calendar fabrication problem appears solved by making skills visible.

**Pattern:** The bind mount was the biggest single fix. Skills were never loaded — the model was always freestyling.

## Current Architecture (as of 2026-03-16)

```
VPS (always on):
  briefing-prep.py (cron 06:15 + 14:15) → briefing-input.json
    - gmail-helper.py fetch
    - email_triage.py (Flash)
    - newsletter_reader.py (Haiku)
    - calendar-helper.py
    - vault task selection
  jimbo-api → dashboard, context, settings, activity, costs, experiments, briefing analysis

Mac (optional):
  opus-briefing.sh (launchd 06:35 + 14:35)
    → pulls briefing-input.json via SSH
    → claude -p (Opus via Max plan)
    → POST /api/briefing/analysis → jimbo-api

Jimbo (OpenClaw on Telegram, Step 3.5 Flash):
  Fetches analysis from jimbo-api
  Delivers section-by-section via tool calls
  Full agent: calendar write, vault browse, email detail, follow-up Q&A
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
| Flash triage calibration | 0 shortlisted across 8 sessions. Worker runs but rejects everything. Costs $0.03/day — low priority. |
| Vault tasks stale | Same items surfaced repeatedly. Scorer may not differentiate well at top of range. |
| Opus layer Mac-dependent | If Mac is asleep, no analysis. Jimbo needs a fallback (quick scan from raw data, or say "Opus hasn't run"). |
| No mechanism to rate briefings retroactively | Experiment tracker has user_rating field but no UI or workflow to use it. |
| Skill not triggering API fetch | Model self-composes from raw data instead of fetching Opus analysis from API. Lower priority now that fabrication is solved. |
| briefing-input.json still file-based | Opus reads via SSH. Could move to jimbo-api in v2 to eliminate all file-based flow. |

## Patterns (Across All Sessions)

- **One good model > pipeline of cheap models.** Opus in one pass consistently beats Flash → Haiku → Sonnet pipeline.
- **Work with OpenClaw, not against it.** Step-by-step tool use + conversation is what the platform does well. One-shot composition from giant JSON is fighting it.
- **Email quality correlates with context, not architecture.** Adding PRIORITIES.md and EMAIL_EXAMPLES.md improved email picks more than any pipeline change.
- **Calendar is the most failure-prone section.** Seven sessions, seven different failure modes. All caused by cheap models, never by the pipeline data.
- **Personality and voice are consistent and valued.** Jimbo's editorial voice is a feature, not a bug.
- **Visibility enables improvement.** We couldn't improve what we couldn't see. The API migration unblocked real evaluation.
- **Silent failures are the worst failures.** `|| exit 0` patterns hide bugs for days/weeks. Always log errors.
- **Stale context causes stale assumptions.** Memory files and CLAUDE.md accumulated incorrect claims across sessions. Less is more — keep memory lean, derive from code.
- **Check the plumbing before blaming the model.** Seven sessions of "Flash can't follow instructions" — turns out the instructions were never visible. A bind mount hid all custom skills.
