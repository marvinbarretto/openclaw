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

**Afternoon follow-up (15:00):** First cron-triggered afternoon briefing. 22 real calendar events, no fabrication, CCCL #4 prominent, conversational tone, proper sections. Day-of-week confusion ("Monday" on a Sunday). Pipeline gaps: 0 emails, 0 vault tasks, stale Opus. Marvin: "Not useful yet but the data seems better." Confirms bind mount fix + explicit cron prompt = model reads and follows the skill.

### Session 8 — 2026-03-17 (Best Briefing, Worst Infrastructure)

Best briefing yet: real calendar (19 events, no fabrication), 7 decent email picks, all 5 vault tasks surfaced with reasoning, conversational tone, agent-like closer. Self-composed by Sonnet — no Opus (API returned 404).

But the session became about everything *around* the briefing:

- **marbar.alt calendar is an "options" calendar** — nudges about possible events, not commitments. Most content stale (calendar was off for months). Reframes the entire "calendar fabrication" story from sessions 1-7: those were real entries from a stale maybe-calendar, not hallucinations.
- **Jimbo is mostly asleep.** HEARTBEAT.md describes nudges, email check-ins, blog posts, end-of-day reviews. Activity log: empty. Blog: last post Feb 23. Kimi K2 (daily driver) doesn't follow heartbeat tasks.
- **Email scoring broken.** All 27 insights scored 0. Worker runs, actions assigned, but no meaningful signal.
- **Briefing API returns 404.** Opus can't POST analysis. Route either never deployed or path mismatch.
- **Stale info everywhere.** HEARTBEAT.md references retired skills and moved files. Skills directory has 4-5 retired entries. TODO.md mostly outdated. CAPABILITIES.md claims things work that don't.
- **Surprise game needs definition.** First real attempt but not delightful. Marvin wants: "deep into vault + newsletters + external URLs, match with priorities/goals/hobbies, pick out weird and wonderful things."
- **Calendar write access wanted.** Jimbo should propose and create schedules, not just narrate.

**Key realisation:** "We may need to go backwards in order to go forwards." Should be working with OpenClaw's actual docs (features, CLI reference, concepts) rather than assumptions. The current architecture may be too complex for what the platform actually supports.

## Current Architecture (as of 2026-03-17)

```
VPS (always on):
  briefing-prep.py (cron 06:15 + 14:15) → briefing-input.json
    - gmail-helper.py fetch
    - email_triage.py (Flash) — 0 shortlisted for 9 sessions
    - newsletter_reader.py (Haiku) — 0 gems (nothing shortlisted to read)
    - email_decision.py (Flash) — 27 insights but all scored 0
    - calendar-helper.py — WORKING (19 events today)
    - vault task selection — WORKING (5 tasks)
  jimbo-api → dashboard, context, settings, activity, costs, experiments
    ⚠ POST /api/briefing/analysis returns 404 — Opus can't post

Mac (optional):
  opus-briefing.sh (launchd 06:35 + 14:35)
    → pulls briefing-input.json via SSH
    → claude -p (Opus via Max plan)
    → POST /api/briefing/analysis → jimbo-api ← BROKEN (404)

Jimbo (OpenClaw on Telegram, Sonnet in briefing window, Kimi K2 otherwise):
  Self-composes from briefing-input.json (doesn't fetch from API)
  HEARTBEAT.md tasks: NOT EXECUTING (agent inactive between briefings)
  Blog: last post Feb 23
  Calendar write: available but not used
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
| Email insight scores all 0 | **BROKEN.** email_decision.py produces insights but all scored 0. No signal for briefing. Session 8. |
| Briefing API 404 | **BROKEN.** POST /api/briefing/analysis returns 404. Opus can't post. Session 8. |
| Jimbo inactive between briefings | **BROKEN.** HEARTBEAT.md tasks not executing. Activity log empty. Blog silent 3 weeks. Session 8. |
| Stale files throughout repo | HEARTBEAT.md refs retired skills, skills/ has 4-5 retired entries, TODO.md outdated, CAPABILITIES.md inaccurate. Session 8. |
| No surprise game definition | Only a vague "non-obvious connection" instruction. Needs proper doc defining what delight means. Session 8. |
| marbar.alt calendar = options | Model doesn't know this calendar is "maybe" events. Treats as commitments. Session 8. |
| Calendar write not used | Jimbo has write access but only narrates, never proposes+creates. Session 8. |
| Flash triage calibration | 0 shortlisted across 9 sessions. Worker runs but rejects everything. Costs $0.03/day. |
| Vault tasks stale | Same 5 priority-9 items surfaced repeatedly. Scorer may not differentiate well at top of range. |
| Opus layer Mac-dependent | If Mac is asleep, no analysis. Plus API is broken anyway (404). |
| No mechanism to rate briefings | Experiment tracker has user_rating field but no UI or workflow. |
| Skill not triggering API fetch | Model self-composes instead of fetching Opus analysis from API. |
| Need to align with OpenClaw docs | Should be working with platform features as documented, not assumptions. Key refs: docs.openclaw.ai/concepts/features, /start/wizard-cli-reference, /start/openclaw |

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
- **Calendar "fabrication" was real data from a stale source.** The marbar.alt calendar contained real entries from a "maybe" events calendar that had been off for months. Not hallucination — wrong trust level.
- **A good briefing doesn't mean the system is healthy.** Session 8 had the best briefing yet while email scoring, Opus posting, activity logging, and heartbeat tasks were all broken.
- **Stale info compounds.** HEARTBEAT.md, skills/, TODO.md, CAPABILITIES.md all accumulated incorrect claims. Regular audits needed — or derive from code, not docs.
