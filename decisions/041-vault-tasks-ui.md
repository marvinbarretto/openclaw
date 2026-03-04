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

**Data source:** The vault lives on VPS at `/workspace/vault/notes/` as markdown files with YAML frontmatter. The API reads/writes these files directly — no separate database. This keeps the vault as the single source of truth.

**Indexing:** On startup (and periodically), jimbo-api scans the vault directory and builds an in-memory index of frontmatter fields. File reads happen on demand for full content. This avoids needing SQLite for what's essentially a file browser.

### UI (site repo)

**Page: `/app/jimbo/vault`**

Core views:
1. **Task list** — sortable table/cards showing title, priority, actionability, type, status. Default: active tasks sorted by priority descending.
2. **Filters sidebar** — priority range slider, actionability chips, type dropdown, text search.
3. **Task detail** — click to expand. Shows full note body, all frontmatter, edit controls.
4. **Bulk actions** — multi-select to mark done, archive, or reprioritise.

Key interactions:
- **Mark done** — one click. Updates frontmatter `status: done`, moves to archive.
- **Reprioritise** — inline priority number edit or up/down buttons.
- **Quick archive** — swipe or button for "this is stale, get rid of it."
- **Search** — instant filter as you type.

Stats bar at top:
- Total active tasks, breakdown by priority tier, vague count, "scored today" count

### Priority Override

When Marvin manually sets a priority via the UI, the frontmatter gets a `priority_locked: true` flag. The daily `prioritise-tasks.py` scorer skips locked tasks. This prevents the auto-scorer from overwriting human judgment.

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
- Completed tasks visible in a "done" tab (not hidden) — useful for seeing what's been cleared.
- Refresh-on-load is fine. No real-time sync needed.
