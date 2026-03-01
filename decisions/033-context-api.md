# ADR-033: Context API — Web-editable context files

## Status

Accepted

## Context

Jimbo reads context files (PRIORITIES.md, GOALS.md, INTERESTS.md) to make decisions during briefings and day planning. These files live as markdown in the openclaw git repo and get rsync'd to the VPS. Editing means opening a text editor, committing, and running `workspace-push.sh` — too much friction for something that should change weekly (priorities) or monthly (goals).

We need a web UI to edit context data directly, with changes taking effect immediately.

## Decision

Move context data to a SQLite database served by an API, with a web editor on the personal site.

### Architecture

- **jimbo-api** (evolved from notes-triage-api): Hono/Node API on VPS port 3100. Added `better-sqlite3` for context storage. Schema: `context_files` → `context_sections` → `context_items` (three-level hierarchy).
- **Context editor UI**: React island at `/app/jimbo/context` on the personal site. Tab-based file selection, inline editing, section reordering.
- **context-helper.py**: Stdlib Python script in sandbox. Fetches context from the API via HTTP, formats as readable text for Jimbo's context window.
- **Skill updates**: daily-briefing and day-planner skills updated to call `context-helper.py` instead of reading local files.
- **Telegram notification**: Write operations to the context API trigger a debounced Telegram notification.

### API endpoints

- `GET /api/context/files` — list files with counts
- `GET /api/context/files/:slug` — full nested file data
- CRUD for sections and items, plus reorder endpoints

### V1 scope

- PRIORITIES, INTERESTS, GOALS (seeded from existing markdown)
- TASTE, PREFERENCES, PATTERNS deferred (less frequently edited, more complex format)

### What didn't change

- `workspace-push.sh` still pushes context files as a backup
- TASTE.md remains a local file (skills still reference it directly)
- Security model unchanged — same API key auth, same CORS origins

## Consequences

### Easier
- Edit context from any device (mobile, laptop) via the web UI
- Changes take effect immediately — no git commit, no rsync
- Telegram confirms edits, so Jimbo can reference them in conversation
- Structured data enables future features (search, analytics, staleness tracking)

### Harder
- Two sources of truth during transition (files as backup, API as primary)
- API must be available for Jimbo to read context (fallback to files if API is down)
- SQLite on VPS needs to be backed up (add to heartbeat)

### New dependencies
- `better-sqlite3` in jimbo-api
- `JIMBO_API_URL` and `JIMBO_API_KEY` env vars in sandbox
