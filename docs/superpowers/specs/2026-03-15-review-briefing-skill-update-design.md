# Review Briefing Skill Update — Design Spec

**Date:** 2026-03-15
**Scope:** Update `.claude/commands/review-briefing.md` + create `docs/reviews/HISTORY.md`

## Problem

The review-briefing skill was written when pipeline data lived in SQLite inside the Docker sandbox. It uses `docker exec` commands that now fail with 401s because the scripts were migrated to POST/GET against jimbo-api. The skill also references retired components (sift-digest skill, the original audit doc).

## Changes

### 1. `docs/reviews/HISTORY.md` — Review Arc Summary

A living document that replaces the audit doc as the "what we know" reference. Captures the evolution across 5 sessions:

- **Session 1 (Mar 4):** Baseline. Vault tasks good, email starved, calendar broken, logging dead.
- **Session 2 (Mar 5):** Architecture crisis. Workers never ran, calendar fabricated. Decision: cron pipeline + Opus layer.
- **Session 3 (Mar 6):** First cron deployment. Email quality breakthrough. Calendar still broken. Triple briefing bug.
- **Session 4 (Mar 7):** Visibility gap. Pipeline runs but dashboard empty. Decision: jimbo-api as single source of truth.
- **Session 5 (Mar 8):** Breakthrough. Multi-stage pipeline was the problem. Opus via Max plan in one pass beats everything. Radical simplification.

Includes: resolved issues, open issues, patterns, current architecture state.

Updated after each review session.

### 2. `.claude/commands/review-briefing.md` — Skill Rewrite

**Context section:**
- Reference `docs/reviews/HISTORY.md` (replaces audit doc)
- Reference `docs/reviews/*.md` (session continuity)
- Reference `skills/daily-briefing/SKILL.md` (still active)
- Reference `workspace/SOUL.md` (personality + minimum bar)
- Drop `skills/sift-digest/SKILL.md` (retired)
- Drop `docs/plans/2026-03-03-briefing-quality-audit.md`

**Phase 1 data pull — jimbo-api endpoints:**

All use `X-API-Key` header with the key from CLAUDE.md memory.

| Data | Source | Command |
|------|--------|---------|
| Experiment runs | `GET /api/experiments?task=briefing-synthesis&last=5` | curl to jimbo-api |
| Activity log | `GET /api/activity?days=1` | curl to jimbo-api |
| Cost summary | `GET /api/costs/summary?days=1` | curl to jimbo-api |
| Email reports | `GET /api/emails/reports?limit=20` | curl to jimbo-api |
| Email digest raw | `ssh jimbo cat .openclaw/workspace/email-digest.json \| python3 -c "..."` | SSH + python one-liner for count/date |
| briefing-input.json | `ssh jimbo cat .openclaw/workspace/briefing-input.json` | SSH cat, parse locally |
| briefing-analysis.json | `ssh jimbo cat .openclaw/workspace/briefing-analysis.json` | SSH cat if exists |
| Vault stats | `GET /api/vault/stats` | curl to jimbo-api |

Use `WebFetch` tool for API calls where possible. Fall back to `ssh jimbo curl` if needed. Present a structured summary of all data.

**Phase 1 analysis prompts updated:**
- Did briefing-prep.py run? (check experiment tracker for today's runs)
- How many emails fetched → shortlisted → gems produced?
- Did Opus analysis run? (check for briefing-analysis.json)
- What did it cost? (cost summary)
- Any email reports from deep-read? (email reports endpoint)
- What's the vault state? (vault stats)

**Phase 2-4:** Keep the same conversational structure. Update analysis checklist to reference current architecture (cron pipeline + optional Opus layer, not conductor model). Remove references to "conductor self-rating" — that concept is gone.

**Principles:** Add one about leveraging API data ("if the experiment tracker shows patterns, surface them").

### 3. What stays the same

- The session structure (Pull Data → Get Briefing → Discussion → Write Up)
- The conversational, discovery-oriented approach
- Writing review entries to `docs/reviews/YYYY-MM-DD.md`
- The principles section (mostly)
- Asking Marvin to paste the Telegram briefing

## Non-goals

- No changes to jimbo-api endpoints
- No changes to the pipeline itself
- No changes to other skills
