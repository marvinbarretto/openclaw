# ADR-041: Vault Tasks UI

## Status

Proposed

## Context

The vault contains 1,635 notes (528 typed as tasks, 44 at priority 9). Currently:

1. **No visibility.** Marvin can't see what's in the vault. When Jimbo surfaces "Reconsider Angular for Spoons" as priority 9, there's no way to check if that's correct, mark it done, or reprioritise.
2. **PRIORITIES.md goes stale.** The vault scorer runs against PRIORITIES.md, but that file requires manual updates. If it says "Spoons" when the focus is "LocalShout", all scores are miscalibrated. Having a UI to manage tasks directly would reduce dependence on the markdown file staying current.
3. **528 tasks, 298 "vague."** Over half the tasks have vague actionability. Many are probably stale, done, or duplicates. Only a human can clean this up, and they need a UI to do it efficiently.
4. **Existing infrastructure.** The site already has a Jimbo dashboard at `/app/jimbo/` with notes triage, context editor, and settings. The jimbo-api serves data from VPS. Adding a vault browser is a natural extension.

From the 2026-03-04 review session:
> "We need to show the vault tasks in a UI, and then I can manage it, sort it, check things off, mark them as done."

## Decision

Build a vault tasks browser at `/app/jimbo/vault` on the personal site, backed by a new API endpoint in jimbo-api.

### API (jimbo-api)

**New endpoints:**

```
GET    /api/vault/tasks              # list tasks with filters
GET    /api/vault/tasks/:id          # get single task
PATCH  /api/vault/tasks/:id          # update task fields
GET    /api/vault/stats              # summary statistics
```

**Query parameters for list:**
- `status` — filter by status (active, done, archived). Default: active
- `priority_min` / `priority_max` — filter by priority score
- `actionability` — filter by actionability (clear, vague, needs-breakdown)
- `type` — filter by note type (task, idea, bookmark, etc.)
- `sort` — sort field (priority, created, updated). Default: priority desc
- `q` — full-text search across title and body
- `limit` / `offset` — pagination

**PATCH fields:**
- `status` — change to done/archived/active
- `priority` — manual override (locks score from auto-scorer)
- `title` — rename
- `tags` — add/remove tags

**Data source:** SQLite database backing the vault. On initial setup, ingest all markdown files from `/workspace/vault/notes/` into the database (frontmatter fields become columns, body stored as text). The database becomes the source of truth — Jimbo reads/writes via API, the scorer updates via API, and the markdown files are kept in sync as a fallback.

**Why SQLite, not files:** Files were fine for a static vault, but we now need:
- Fast filtered queries (priority range, actionability, text search)
- Two sort modes (Marvin's manual sort vs Jimbo's AI-scored sort)
- Status tracking with timestamps (when was it marked done? velocity metrics)
- Concurrent read/write from API, scorer, and Jimbo's skills
- Aggregation queries (stats, velocity, completion rates)

**Schema:** See implementation plan for full schema. Key addition beyond frontmatter fields: `manual_priority` (Marvin's override), `ai_priority` (scorer's assessment), `ai_rationale` (why the scorer ranked it there), `completed_at` (timestamp for velocity tracking), `sort_position` (for manual drag ordering).

### UI (site repo)

**Page: `/app/jimbo/vault`**

Core views:
1. **Task list** — card-based, showing title, priority, actionability, status. Two sort modes toggle.
2. **Filters bar** — priority range, actionability chips, text search.
3. **Task detail** — click to expand. Full body, all metadata, edit controls.
4. **Bulk actions** — multi-select to mark done, archive, or reprioritise.

**Two sort modes (toggle at top):**
1. **"My Sort"** — Marvin's manual priority ordering. Drag to reorder, or set priority numbers. This is Marvin's view of what matters.
2. **"Jimbo's Sort"** — AI-scored priority with rationale visible. Each task shows Jimbo's score and a one-line explanation of why. Default view.

Comparing these two views exposes knowledge gaps — where Jimbo and Marvin disagree reveals what context is missing from PRIORITIES.md, GOALS.md, or the scorer prompt.

Key interactions:
- **Mark done** — one click. Timestamps the completion for velocity tracking.
- **Reprioritise** — inline priority edit. Sets `manual_priority`, doesn't overwrite AI score.
- **Quick archive** — button for "this is stale, get rid of it."
- **Search** — instant filter as you type.

Stats bar at top:
- Total active, completed this week, completion velocity, priority distribution
- Jimbo can query these stats via API for briefings ("you completed 12 tasks this week")

### Dual Priority System

Each task has two priority scores:
- `ai_priority` — set by `prioritise-tasks.py` (Gemini Flash), with `ai_rationale` explaining why
- `manual_priority` — set by Marvin in the UI (null until manually set)

The briefing reads `manual_priority` when set, falls back to `ai_priority`. The scorer always updates `ai_priority` but never overwrites `manual_priority`.

### Mobile-first

The vault UI should work well on mobile (Marvin reviews via phone). Card-based layout, large tap targets, swipe gestures for quick actions.

## Consequences

**Easier:**
- Marvin can see and manage all 528 tasks
- Stale tasks can be bulk-archived (probably half of them)
- Manual priority overrides prevent miscalibration
- Reduces dependence on PRIORITIES.md staying current
- Jimbo's briefing surfaces tasks Marvin has actually verified

**Harder:**
- New API endpoints to build and maintain in jimbo-api
- In-memory index needs to handle 1,635 files efficiently
- Frontmatter writes need to preserve existing content (not just overwrite)
- Need to decide on conflict handling if Jimbo and Marvin edit the same task

**Implementation estimate:**
- API: ~4 new endpoints, file-based CRUD, in-memory index. Medium effort.
- UI: new page in site repo, reuse existing dashboard patterns. Medium effort.
- Both repos need coordinated deployment.

**Resolved questions:**
- The `/app/jimbo/vault` page shows only tasks (type: task). Other note types get separate pages at different URL endpoints (e.g., `/app/jimbo/vault/bookmarks`, `/app/jimbo/vault/ideas`) — kept very simple, just for visibility.
- Review queue mode is a nice-to-have for later. Start with browse/filter mode.
- Completed tasks visible in a "done" tab (not hidden) — useful for seeing what's been cleared and tracking velocity.
- Refresh-on-load is fine. No real-time sync needed.
- SQLite database, not file-based. DB is source of truth, markdown files kept in sync as fallback.
- Two sort modes: "My Sort" (Marvin's manual) vs "Jimbo's Sort" (AI-scored with rationale). Comparing them exposes knowledge gaps.
- Jimbo queries vault status via API — completion velocity, active count, priority distribution. Feeds into briefings.
