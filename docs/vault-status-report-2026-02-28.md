# Vault Status Report — 28 February 2026

## Executive Summary

6,509 scattered notes from Google Tasks and Google Keep have been processed into a structured, tagged Obsidian vault in a single session. The inbox is at zero. The vault is ready to be used — but it's not being used yet. The next step is connecting it to the tools and workflows that make it valuable.

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
- The vault is structured, tagged, and ready for Obsidian
- The classification pipeline is reliable and fast
- The triage UI is good for mobile review
- Auto-accept at confidence 8+ is validated and trustworthy for type/action (not project tags)
- PATTERNS.md captures real classification knowledge that improves over time

### What's Missing

**The vault is isolated.** It lives on the laptop in `data/vault/`. Nothing reads it:
- Jimbo doesn't know it exists (not on VPS)
- Obsidian isn't set up to use it yet
- No project feeds into film-planner, LocalShout, etc.
- No search or query interface beyond file browsing

**511 tasks sitting idle.** A third of the vault is tasks — things to do, research, contact people. There's no system to surface, prioritise, or complete them. They're just files.

**Classification quality is uneven.** Gemini is good at type and action, but:
- Project tags are frequently wrong (guessed project:spoons for a LocalShout URL)
- Ideas get misclassified as journal entries or tasks
- "Instructions for Jimbo" notes get classified as regular tasks
- No distinction between "curiosity" items and real tasks

**No lifecycle management.** Notes go into the vault and stay forever. There's no:
- Way to mark a task as done
- Periodic review of stale active notes
- Connection between vault tasks and actual project work

## Opportunities

### Quick Wins (hours of work)

1. **Open Obsidian vault** — Create vault at `data/vault/`, install Dataview plugin. Immediate visibility into 1,600 notes. Zero code needed.

2. **Push vault to VPS** — Add `data/vault/notes/` to `workspace-push.sh`. Jimbo can then reference notes during briefings, surface curiosity questions during free time, and recommend recipes before dinner.

3. **Task surfacing in HEARTBEAT** — Jimbo already has free-time detection. Add: scan vault tasks tagged with the current active project, surface 1-2 actionable ones during nudges.

4. **Curiosity surfacing** — Notes tagged `curiosity` get surfaced during Jimbo's interest research slot (~11:00 daily). "You wondered why bamboo isn't used in construction — want to look into it?"

### Medium-Term (days of work)

5. **Film Planner HTTP API** — Add endpoint to film-planner so Jimbo can push `type: media` + `tags: film/tv` notes directly into the collection. Same pattern extends to other "to-X" lists.

6. **Vault lifecycle** — Add `status: done` for completed tasks. Periodic HEARTBEAT job scans for tasks older than 6 months and flags them for review. Archive or refresh.

7. **Improve classifier prompt** — Feed PATTERNS.md into the Gemini system prompt so it knows about curiosity questions, project mappings, Jimbo instructions. Re-classify the 1,600 notes with the improved prompt (cheap — ~$0.10).

8. **Obsidian templates + Dataview** — Dashboards for: tasks by project, media watchlist, travel knowledge by country, recent ideas, curiosity backlog.

### Longer-Term (weeks of work)

9. **Voice-to-note app** — Capacitor app on phone, speech-to-text, outputs vault-format markdown. Quick capture throughout the day without typing.

10. **Vault as Jimbo's memory** — Replace or supplement Jimbo's current memory system with vault queries. "What restaurants did I save in Hong Kong?" becomes a vault search, not a memory recall.

11. **Project feeds** — Automated pipelines: vault note created with `project:localshout` → Jimbo creates a GitHub issue. `type: recipe` → added to a recipe index. `type: event` → added to calendar suggestions.

## Recommendations

**Do now:**
- Open Obsidian vault and browse. See if the structure feels right. This informs everything else.
- Push vault to VPS so Jimbo starts using it in briefings.

**Do this week:**
- Run one Obsidian session to set up Dataview queries for tasks-by-project and media watchlist.
- Add curiosity surfacing to HEARTBEAT.

**Do this month:**
- Film Planner HTTP API (weekend project, shared with cousin).
- Voice-to-note app (weekend project, Capacitor).
- Re-classify vault with improved prompt.

## Files Reference

| File | Purpose |
|------|---------|
| `data/vault/notes/` | 1,600 active notes |
| `data/vault/archive/` | 5,070 archived notes |
| `data/vault/needs-context/` | 4 items needing context |
| `scripts/process-inbox.py` | Classifier + manifest generator |
| `scripts/apply-decisions.py` | Applies triage decisions |
| `scripts/review_helper.py` | Moves files + updates frontmatter |
| `scripts/push-manifest.sh` | Pushes manifest to VPS |
| `scripts/pull-decisions.sh` | Pulls decisions from VPS |
| `context/PATTERNS.md` | Classification patterns (living doc) |
| `context/GOALS.md` | Longer-term goals (updated this session) |
| `workspace/HEARTBEAT.md` | Jimbo's periodic tasks (updated this session) |
| `.claude/commands/manual-review.md` | CLI review command |
