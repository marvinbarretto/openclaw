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

### Session 9 — 2026-03-19 (Jimbo Wakes Up)

Late-night review (00:57) of March 18 data. No March 19 briefing yet — pipeline didn't run this morning. The story is the transformation: session 8 found an empty activity log; March 18 had 36 entries.

**Morning briefing:** Sonnet self-composed (Opus failed with `claude -p error`). Calendar clean — no fabrication, marbar.alt correctly marked "lower confidence." 9 email highlights including genuine urgencies (Supabase security, Claude API credits expiring today). Surprise connected LocalShout alerts into a "finish this app" theme — decent but still pattern-matching.

**Inter-briefing activity (the breakthrough):** First day of sustained heartbeat execution. Gym nudge (08:33), Spanish nudge (11:36), cooking nudge (16:12). Email check-ins at 9am and 5pm with actionable items (LPO £10 tickets, CHEQ deadline, KAYTRANADA, Pisa flights). Vault connector + roulette calls (though vault-reader 401s every time). Blog draft written (git push failed). 451 censorship error from Step 3.5 Flash provider.

**Afternoon briefing:** Best surprise yet — ianVisits "Human Creativity cannot flourish in a TikTok World" debate connected to Marvin's AI work + the fact he's playing guitar and piano that evening. Calendar handled guitar/piano overlap honestly. Anthropic Dispatch flagged as competitor signal. Vault skipped.

**Accountability report (20:00):** Both pipelines ran, 34 activities, $0.07 spent. Incorrectly reports "surprise game not played" — both briefings had surprise sections. Bug in detection logic.

**Flash triage drought broken:** 13 shortlisted morning, 17 afternoon — after 9 consecutive sessions of 0.

**Marvin's reaction:** "Right direction. Nothing really landed yet, but that's OK." Loved the afternoon surprise. Wants: inline links to resources, split messages for Telegram, and ultimately Jimbo making executive decisions and spinning off sub-agents. "I will be most excited once I see Jimbo actually post blog entries, and deploys himself."

**Key insight:** Marvin recognises he needs to improve source data quality (clean up calendar, etc.) before outputs can be useful. The maturity ladder: plumbing → heartbeat → source data → useful outputs → autonomous actions → sub-agents. Currently at step 2.

### Session 10 — 2026-03-21 (The Missing Loop)

Reviewing March 20 data. Both pipelines ran. Morning had a gem drought (1 gem from 17 shortlisted — cause unknown; afternoon recovered to 27). Briefing quality steady — real calendar, good email picks, reasonable surprises.

**The Airbnb nagging problem:** Jimbo sent 10 separate reminders for the same two Airbnb items (Rajesh Kumar booking, Zsuzsanna check-in) between 08:42 and 18:48. Marvin dealt with the Airbnb thing. Jimbo kept nagging because he has no feedback loop — no shared state, no way to know it was done.

**Marvin's core insight:** "There was some good suggestions through the day but they're being lost and they're not being converted into issues that can be then completed, and then measured." Actionable items surface in Telegram and evaporate. Nothing gets written down, tracked, or closed. Vault velocity remains 0.

**The interaction gap:** Marvin revealed he hasn't been interacting with Jimbo because he wasn't sure the platform could handle conversational task management. It can — memory-core (FTS5 + vector search), workspace file write, activity logging all work. The gap is skill/prompt design, not platform capability.

**What Marvin wants:** "I'll take this on. You look at the next one." A conversational task handoff where Jimbo creates tasks from signals, tracks who's doing what, stops nagging when things are handled, and picks the next priority item when asked.

**Decision:** The vault should become the shared task system between Marvin and Jimbo. This is a new step in the maturity ladder between "heartbeat fires" and "source data quality." Design a task handoff skill.

**Updated maturity ladder:** plumbing → heartbeat → **vault as shared task system** → source data → useful outputs → autonomous actions → sub-agents. Currently between steps 2 and 3.

### Session 11 — 2026-03-21 (The Pivot)

Reviewing March 21 morning data. Pipeline healthy — 28 gems from 16 shortlisted (drought didn't recur). Briefing structurally competent but flat. Marvin: "No it's not landing yet."

**Duplicate message bug (NEW):** Airbnb, HowTheLightGetsIn, and neighbour petition all sent as duplicate messages at the same timestamp. Different from session 10's nagging — looks like a tool double-fire bug.

**Briefing regressions:** No surprise section (present in sessions 8-10). marbar.alt items not marked as options calendar. Email cherry-picking poor — 4 items from 28 gems, Claude Code 1M context update (0.95 confidence) missed entirely.

**vault_reader still dead:** 5 x 401 failures today, 3rd consecutive day. vault_roulette returns "no_candidates" every time.

**The pivot:** Marvin articulated the full vision: vault as shared task system, Jimbo as task manager not news curator, sub-agent delegation, status dashboard ("6 done, 3 new, 2 on you, no blockers"). Wants to leverage Opus 1M context + Claude Code features (loop, Cowork). "It's absolutely time for the next design piece."

**Key reframe:** The briefing isn't the product — the vault-as-task-system is. The briefing is one interface to it. We've been optimising output quality for 11 sessions when the real problem is purpose.

**Decision:** Design the vault task management system. Comprehensive design prompt prepared for a dedicated session.

**Updated maturity ladder:** plumbing → heartbeat → **vault as shared task system** (designing now) → source data → useful outputs → autonomous actions → sub-agents.

### Session 12 — 2026-03-22 (Rate Limit, Then Planning)

Pipeline ran fine but Sonnet hit an API rate limit at compose time. No briefing delivered. Activity log falsely recorded success. No alert fired. Marvin: "today's output was pretty bad, nothing of value." One useful nudge (Outdooraholics Snowdonia trip) slipped through via heartbeat mode.

New failure mode: silent briefing failure with false success reporting. No mechanism to detect externally that the briefing wasn't composed.

Gem count dropped from 28 (Mar 21) to 5 — heavily operational (3x Sentry, 1x Airbnb, 1x NZ job). Email insights have scores but all other fields null. vault_reader 401 on 4th consecutive day.

Session pivoted to planning: (1) `/health` endpoint for comprehensive monitoring, (2) vault-as-task-system design for Jimbo autonomy.

**Pattern:** False success reporting is worse than no reporting. The system should never claim a briefing was delivered when the model hit a rate limit.

### Session 13 — 2026-03-23 (Calendar Pollution, Then Building)

Second consecutive morning delivery failure — Marvin had to prompt at 08:56. When briefing came, calendar was polluted with events from shared/subscribed calendars (Quiet Waters, Breaky, Zoom Prayer, Cookin!). Root cause: `--primary-only` still includes 16 owner calendars, many belonging to other people's schedules. Best gem missed — a podcast explicitly discussing OpenClaw at 0.95 confidence. No surprise section (3rd consecutive). Email insight null fields (3rd consecutive).

Marvin: "It was a disaster." Session pivoted immediately to infrastructure fixes. Identified calendar pollution as highest-impact issue. Designed a calendar configuration system: whitelist + tags stored in settings API, new admin page at `/app/jimbo/calendar` with checkboxes and tag dropdowns (e.g., marbar.alt tagged "options"). Tags are freeform — briefing skill uses them for presentation context. Spec written.

**Pattern:** Source data quality gates output quality — again. No amount of model intelligence compensates for feeding 36 calendars when only 5 are wanted. Config UIs are infrastructure, not features.

**Updated maturity ladder:** plumbing → heartbeat → **source data quality** (calendar config being built) → vault as shared task system → useful outputs → autonomous actions → sub-agents.

## Current Architecture (as of 2026-03-23)

```
VPS (always on):
  briefing-prep.py (cron 06:15 + 14:15) → briefing-input.json
    - gmail-helper.py fetch — WORKING
    - email_triage.py (Flash) — WORKING (16-18 shortlisted, drought broken)
    - newsletter_reader.py (Haiku) — WORKING (28 gems Mar 21 morning, 1 gem anomaly on Mar 20 was transient)
    - email_decision.py (Flash) — running, costs $0.04/day
    - calendar-helper.py — WORKING but POLLUTED (18 events from 36 calendars, needs whitelist)
    - vault task selection — WORKING morning, skipped afternoon
  jimbo-api → dashboard, context, settings, activity, costs, experiments, health
    POST /api/briefing/analysis — deployed but unused (Opus broken)
    GET /api/health — comprehensive monitoring (deployed session 12)
  Autonomous mind tools (Phase 1):
    - vault_connector.py — WORKING (BM25 search, found Airbnb match)
    - vault_roulette.py — NO CANDIDATES (every call, 30d threshold issue?)
    - vault_reader.py — BROKEN (401 Unauthorized, 3 consecutive days)

Mac (optional):
  opus-briefing.sh (launchd 06:35 + 14:35)
    → pulls briefing-input.json via SSH
    → claude -p (Opus via Max plan) ← BROKEN (stale since Mar 16)
    → POST /api/briefing/analysis → jimbo-api
  NEW OPPORTUNITY: Opus 1M context, Claude Code loop/Cowork features

Jimbo (OpenClaw on Telegram):
  Briefing window: Sonnet (model swap via cron 06:45-07:30, 14:45-15:30)
  Between briefings: Kimi K2 (via OpenRouter)
  HEARTBEAT.md tasks: EXECUTING (18+ activities today)
  Nudges: gym, Spanish, cooking — WORKING (but duplicate message bug)
  Email check-ins: throughout the day — WORKING
  Blog: git push still BROKEN
  Calendar write: available but not used
  Vault task system: NOT BUILT — DESIGNING NOW
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
| Briefing API 404 | Built routes in jimbo-api (POST /analysis, GET /latest, GET /history). Fixed in session 9 implementation. | 8→9 |
| Jimbo inactive between briefings | Phase 1 autonomous mind tools deployed + HEARTBEAT.md updated. 36 activities on Mar 18. | 8→9 |
| Flash triage calibration | Drought broken — 13 shortlisted morning, 17 afternoon on Mar 18. | 8→9 |
| marbar.alt calendar = options | Jimbo now marks marbar.alt entries as "lower confidence." Working as of Mar 18. | 8→9 |

## Open Issues

| Issue | Notes |
|-------|-------|
| vault_reader.py 401 | **BROKEN.** Every call fails with Unauthorized. Most-called tool, never succeeds. Session 9. |
| Opus `claude -p` error | **BROKEN.** Morning analysis failed. File on VPS stale (Mar 16). Session 9. |
| Accountability surprise detection | **BUG.** Reports "surprise game not played" when both briefings had surprise sections. Session 9. |
| 451 censorship error | **BUG.** Step 3.5 Flash hit provider content filter mid-day. Unknown trigger. Session 9. |
| Blog git push broken | **BROKEN.** Draft written but push fails: "no repository initialized at host workspace." Session 9. |
| ~~March 19 pipeline missing~~ | Resolved — pipelines ran on both Mar 19 and Mar 20. Transient issue. | 9→10 |
| No inline links in briefing | Gem data has URLs but briefing says "link in the email" instead of including them. Skill fix needed. Session 9. |
| Message format (wall of text) | Briefing sent as one long message. Should split by section for Telegram UX. Skill fix needed. Session 9. |
| Calendar pollution | **DESIGNING FIX.** 36 calendars fetched, only ~5 wanted. `--primary-only` insufficient (16 owner calendars). Config UI spec written. Session 13. |
| Briefing auto-delivery broken | **BROKEN.** 2 consecutive mornings failed to auto-deliver. Session 12 was rate limit; session 13 cause unknown. |
| Email insight fields null | **BUG.** Insights have relevance scores but category/action/reason/insight all null. 3rd consecutive session. Replaces "scores all 0" (session 8). |
| Stale files throughout repo | HEARTBEAT.md refs retired skills, skills/ has 4-5 retired entries, TODO.md outdated, CAPABILITIES.md inaccurate. Session 8. |
| No surprise game definition | Only a vague "non-obvious connection" instruction. Needs proper doc defining what delight means. Session 8. |
| Calendar write not used | Jimbo has write access but only narrates, never proposes+creates. Session 8. |
| Vault tasks stale | Same 5 priority-9 items surfaced repeatedly. Scorer may not differentiate well at top of range. Session 8. |
| Opus layer Mac-dependent | If Mac is asleep, no analysis. Plus claude -p is erroring anyway. Session 8. |
| No mechanism to rate briefings | Experiment tracker has user_rating field but no UI or workflow. Session 8. |
| Need to align with OpenClaw docs | Should be working with platform features as documented, not assumptions. Session 8. |
| No task creation from signals | **DESIGN GAP.** Jimbo surfaces actionable items but doesn't create trackable tasks. Session 10. |
| No conversational task handoff | **DESIGN GAP.** No protocol for "I'll take this" / "you do it" / "done." Vault velocity 0. Session 10. |
| Nudge rate-limiting missing | **DESIGN GAP.** 10 Airbnb reminders in one day. No awareness of whether item was actioned. Session 10. |
| ~~Morning gem drought~~ | Resolved — transient. 28 gems from 16 shortlisted on Mar 21. Session 10→11. |
| Duplicate messages | **NEW BUG.** Airbnb, HowTheLightGetsIn, petition all double-sent at same timestamp. Tool double-fire? Session 11. |
| False success on rate limit | **NEW BUG.** Model hit rate limit, no briefing composed, but activity log recorded "briefing delivered: success." No alert. Session 12. |
| Email insight fields null | **BUG.** 27 insights have relevance scores (7-10) but category, action, reason, insight all null. Scoring runs, content doesn't. Session 12. |
| No surprise section (regression) | Missing from Mar 21 briefing. Was present in sessions 8-10. Session 11. |
| marbar.alt not labelled (regression) | Salsa, Football, Parkrun from options calendar not marked lower-confidence. Session 11. |
| Email cherry-picking poor | 4 items surfaced from 28 gems. Claude Code 1M update (0.95 confidence) missed entirely. Session 11. |
| vault_roulette always empty | Returns "no_candidates" on every call (4x today). 30-day dormancy threshold or data issue. Session 11. |

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
- **Activity ≠ value.** 36 activities in a day is progress, but "nothing really landed yet." The gap between tool invocations and useful outcomes is the next frontier.
- **Source data quality gates output quality.** Stale calendar, stagnant vault, missing links — no amount of model intelligence compensates for bad inputs. Marvin recognises this: "I need to make the source data better."
- **The maturity ladder is real.** Plumbing → heartbeat → **vault as shared task system** → source data → useful outputs → autonomous actions → sub-agents. Each step depends on the previous one being solid. Skipping steps creates the illusion of progress.
- **Broadcasting ≠ collaboration.** Telegram messages scroll past. Without shared state (task created, assigned, tracked, closed), Jimbo is a news feed, not a collaborator. The vault is the natural shared state.
- **No feedback loop = spam.** Without knowing whether an item was actioned, Jimbo defaults to repeating himself. Rate-limiting is a band-aid; shared task state is the fix.
- **The user won't engage until they trust the system can respond.** Marvin didn't interact with Jimbo because he wasn't sure the platform supported it. Trust gates adoption.
- **The briefing isn't the product.** After 11 sessions optimising briefing output, the real problem is purpose. The vault-as-task-system is the product; the briefing is one interface to it. Optimising output without operational context has a ceiling.
- **Purpose > polish.** A structurally competent briefing that doesn't connect to shared task state feels flat. "Not landing" isn't about quality — it's about relevance to what's actually happening.
- **False success is worse than visible failure.** A rate limit that logs "briefing delivered: success" is worse than an error that triggers an alert. Self-reported success without verification is unreliable.
