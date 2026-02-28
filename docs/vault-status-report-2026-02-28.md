# Vault Status Report — 28 February 2026

## Executive Summary

6,509 scattered notes from Google Tasks and Google Keep have been processed into a structured, tagged vault. The inbox is at zero. As of the afternoon session on 28 Feb, the vault is **live and connected** — pushed to VPS, Jimbo reads it during briefings, and a daily cron sweeps new Google Tasks into the vault automatically.

## What Was Done

### The Backlog Crush (27–28 Feb 2026)

| Metric         | Before | After |
|----------------|--------|-------|
| Inbox          | 6,509  | 0     |
| Notes (active) | 62     | 1,600 |
| Archive        | 97     | 5,070 |
| Needs-context  | 4      | 4     |

**Pipeline used:**
1. `process-inbox.py` classified items via Gemini Flash with URL fetching
2. Items with confidence 8+ were auto-accepted (direct to notes) or auto-archived
3. Items older than 3 years were auto-archived as stale
4. Remaining low-confidence items were manually triaged via the web UI
5. Manual decisions were pulled from VPS and applied via `apply-decisions.py`

**Throughput:** ~1,100 items classified by Gemini, ~370 manually triaged by Marvin, ~4,100 auto-archived by age rule. Total processing time: ~6 hours (including classifier runs and manual review).

### Vault Composition

**1,600 active notes by type:**

| Type | Count | % |
|------|-------|---|
| task | 511 | 32% |
| bookmark | 175 | 11% |
| idea | 167 | 10% |
| travel | 150 | 9% |
| reference | 144 | 9% |
| media | 134 | 8% |
| finance | 57 | 4% |
| political | 55 | 3% |
| journal | 54 | 3% |
| recipe | 52 | 3% |
| event | 51 | 3% |
| health | 28 | 2% |
| person | 12 | 1% |
| checklist | 9 | 1% |
| quote | 1 | <1% |

**Top 10 tags:** ai (123), travel (121), music (89), finance (75), development (69), developer-tools (68), productivity (63), india (60), social (56), project:openclaw (56)

**Project distribution:** OpenClaw (56), LocalShout (53), Spoons (34), Film Planner (11), others (5)

**Sources:** 87% Google Tasks, 13% Google Keep, <1% manual

**Age:** Newest note is 1 day old. Median is 229 days (~8 months). Oldest is 4,080 days (~11 years).

### Infrastructure Built

- **Classifier** (`process-inbox.py`): Gemini Flash with URL fetching (oEmbed for tweets, page titles for other URLs). Confidence scoring, manifest generation, append mode.
- **Triage web UI** (site.marvinbarretto.workers.dev): Card-based review interface with accept/archive/edit/skip, keyboard shortcuts, swipe gestures, undo/history, dark mode. Project typeahead, clickable URLs, note IDs.
- **Apply pipeline**: push-manifest.sh → web review → pull-decisions.sh → apply-decisions.py → review_helper.py moves files.
- **Manual review** (`/manual-review` Claude Code command): Interactive CLI review with URL enrichment, batch processing, pattern capture.
- **Patterns database** (`context/PATTERNS.md`): 20+ learned classification patterns including project mappings, curiosity questions, confidence calibration, auto-archive rules.

## Current State

### What Works
- The vault is structured, tagged, and browsable in Obsidian (Dataview dashboard set up)
- The classification pipeline is reliable and fast
- The triage UI is good for mobile review
- Auto-accept at confidence 8+ is validated and trustworthy for type/action (not project tags)
- PATTERNS.md captures real classification knowledge that improves over time
- **Vault is on VPS** — 1,600 notes synced via `workspace-push.sh`, accessible inside sandbox at `/workspace/vault/notes/`
- **Jimbo reads the vault** — SOUL.md + HEARTBEAT.md updated with vault awareness, verified via Telegram (searched LocalShout tasks successfully)
- **Daily briefing + day planner** updated to surface vault tasks with 📋 emoji alongside calendar events
- **Google Tasks intake automated** — `tasks-helper.py` on VPS cron at 05:00 UTC, sweeps active items from "My Tasks" list only, classifies via Gemini Flash, routes to vault
- **TROUBLESHOOTING.md** runbook deployed so Jimbo self-corrects before reporting failures
- **Obsidian** set up locally with Dataview dashboard (stats, tasks, media, recipes, ideas, travel, bookmarks, finance, projects)

### What's Still Missing

**Classification quality is uneven.** Gemini is good at type and action, but:
- Project tags are frequently wrong (guessed project:spoons for a LocalShout URL)
- Ideas get misclassified as journal entries or tasks
- "Instructions for Jimbo" notes get classified as regular tasks
- No distinction between "curiosity" items and real tasks

**No lifecycle management.** Notes go into the vault and stay forever. There's no:
- Way to mark a task as done (Obsidian edits are local-only, no sync back)
- Periodic review of stale active notes
- Connection between vault tasks and actual project work

**No web-based vault browser.** Marvin prefers web tools over desktop apps. Obsidian is useful for local browsing but the vault needs a web UI on the personal site dashboard (like the existing triage UI) for mobile access and editing.

**No project feeds.** Vault notes tagged with projects don't push to those projects yet:
- No film-planner integration
- No LocalShout GitHub issue creation
- No calendar suggestions from event notes

## Opportunities (updated after activation session)

### Done (28 Feb afternoon)

1. ~~Open Obsidian vault~~ — Done. Dataview dashboard with stats, per-type pages, project views.
2. ~~Push vault to VPS~~ — Done. 1,600 notes synced, rsync with --delete.
3. ~~Task surfacing in HEARTBEAT~~ — Done. Vault tasks surfaced in briefings and day plans.
4. ~~Curiosity surfacing~~ — Done. Interest research slot checks vault before external research.
5. ~~Google Tasks intake~~ — Done. Daily cron at 05:00 UTC, My Tasks only, active items only.

### Next Up (days of work)

6. **Web-based vault browser** — Add vault browsing/editing to the site dashboard (`/app/jimbo/vault`). Marvin prefers web tools over Obsidian. Could reuse patterns from the triage UI.

7. **Vault lifecycle** — Add `status: done` for completed tasks. Periodic HEARTBEAT job scans for tasks older than 6 months and flags them for review. Archive or refresh.

8. **Improve classifier prompt** — Feed PATTERNS.md into the Gemini system prompt so it knows about curiosity questions, project mappings, Jimbo instructions. Re-classify the 1,600 notes with the improved prompt (cheap — ~$0.10).

9. **Film Planner HTTP API** — Add endpoint to film-planner so Jimbo can push `type: media` + `tags: film/tv` notes directly into the collection.

### Longer-Term (weeks of work)

10. **Voice-to-note app** — Capacitor app on phone, speech-to-text, outputs vault-format markdown.

11. **Vault as Jimbo's memory** — Replace or supplement Jimbo's current memory system with vault queries.

12. **Project feeds** — Automated pipelines: vault note → GitHub issue, recipe index, calendar suggestions.

## Deployment History

| Tag | Date | What |
|-----|------|------|
| `vault-activation` | 28 Feb | Initial: vault push, SOUL/HEARTBEAT, skills, tasks-helper.py |
| `vault-activation-v2` | 28 Feb | Rsync fix, TROUBLESHOOTING.md, verified Jimbo reads vault |
| `vault-activation-v3` | 28 Feb | Tasks sweep cron live, My Tasks only, OAuth re-auth |
| `vault-activation-final` | 28 Feb | Docs updated, all layers complete |

## Files Reference

| File | Purpose |
|------|---------|
| `data/vault/notes/` | 1,600 active notes |
| `data/vault/archive/` | 5,070 archived notes |
| `data/vault/needs-context/` | 4 items needing context |
| `data/vault/dashboard/` | Obsidian Dataview dashboard pages |
| `scripts/process-inbox.py` | Classifier + manifest generator |
| `scripts/apply-decisions.py` | Applies triage decisions |
| `scripts/push-manifest.sh` | Pushes manifest to VPS |
| `scripts/pull-decisions.sh` | Pulls decisions from VPS |
| `scripts/workspace-push.sh` | Pushes workspace + vault to VPS (rsync, no scp) |
| `workspace/tasks-helper.py` | VPS: Google Tasks → vault intake (05:00 UTC cron) |
| `workspace/SOUL.md` | Jimbo's vault awareness |
| `workspace/HEARTBEAT.md` | Vault task surfacing, recipe surfacing, daily plan |
| `workspace/TROUBLESHOOTING.md` | Jimbo's self-help runbook |
| `skills/day-planner/SKILL.md` | Day planning with vault tasks |
| `skills/daily-briefing/SKILL.md` | Morning briefing with vault snapshot |
| `context/PATTERNS.md` | Classification patterns (living doc) |
| `.claude/commands/manual-review.md` | CLI review command |
