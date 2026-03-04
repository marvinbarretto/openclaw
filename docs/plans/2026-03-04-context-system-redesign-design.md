# Context System Redesign — Design Doc

*2026-03-04*

## Problem

The context system is half-migrated. The context API (ADR-033) serves priorities, interests, and goals via SQLite, but `prioritise-tasks.py` still reads raw markdown files. Two sources of truth. The data model (files → sections → items) doesn't capture timeframes, urgency, or status — so Jimbo can't reason about conflicts, expiring priorities, or stale goals.

## Trigger

Triage session revealed "dating" needed to move from a recurring nudge to a 3-month active priority with a deadline. The flat markdown structure can't express this. Meanwhile, triage sessions keep revealing that context files are stale or misaligned — the system should help catch that, not wait for humans to notice.

## Approach

Extend the existing context_items table with optional structured fields. No new tables, no rewrite. Priorities and goals get richer metadata; interests, taste, preferences, and patterns stay as they are.

## Design Principles

- **Structured enough to reason, flexible enough to live with.** Not everything needs a schema. Priorities and goals benefit from structure. Taste and preferences are prose — judgment, not data.
- **No numerical ranking.** Life doesn't work that way. Timeframe and status matter more than priority 1 vs priority 2.
- **Single source of truth.** Everything reads from the API. Markdown files become historical reference only.
- **Not a chore.** The UI should make editing feel quick. Triage sessions are the primary input mechanism for tuning the system.

## Data Model

Extend `context_items` with four nullable columns:

| Field | Type | Values / Examples |
|---|---|---|
| `timeframe` | text | "3 months from March 2026", "ongoing", "this week" |
| `status` | text | active, paused, completed, deferred |
| `category` | text | project, life-area, habit, one-off |
| `expires_at` | text (ISO date) | "2026-06-04" |

All nullable. Existing items (interests, generic items) don't need them. Only priorities and goals items use these fields.

Migration: single ALTER TABLE. No data loss, no backfill needed.

## API Changes

Existing endpoints extended to pass through new fields:
- `PUT /api/context/items/:id` — accepts timeframe, status, category, expires_at
- `POST /api/context/sections/:id/items` — same

New endpoint:
- `GET /api/context/items/expiring?days=30` — items with expires_at within N days

### context-helper.py output format

Items with structured fields append metadata inline:

```
- **Hinge X** — actively dating, needs scheduled time
  [active | 3 months from March 2026 | expires 2026-06-04]
```

Jimbo sees metadata in context without separate API calls. Briefing skill doesn't need changes.

### prioritise-tasks.py migration

Switch from reading `/workspace/context/PRIORITIES.md` and `/workspace/context/GOALS.md` to calling context-helper.py or the API directly. This is the key "single source of truth" fix.

## UI Changes

Extend existing ItemRow component in the context editor. When editing items in priorities or goals files, show additional fields:

- **Status** — dropdown: active / paused / completed / deferred
- **Category** — dropdown: project / life-area / habit / one-off
- **Timeframe** — free text input
- **Expires** — date picker (optional)

Fields only appear for items in structured files (priorities, goals). Interest items keep simple label + content editing.

Visual indicators:
- Status chip (green active, grey paused/deferred, strikethrough completed)
- Expiry warning badge if within 14 days (amber)

No new pages or tabs.

## Conflict Detection

Rules Jimbo applies during briefings with the new structured data:

- **Too many active priorities** — >5 active items flagged: "You've got 7 active priorities. Something should be paused."
- **Expiring soon** — items with expires_at within 14 days surfaced proactively
- **Stale active items** — active priority not mentioned in vault tasks or activity logs for 2+ weeks gets questioned
- **Time conflicts** — multiple active projects with overlapping timeframes flagged as competing for hours

Logic lives in the daily-briefing skill prompt, not in code. Jimbo reads structured context and reasons about it. Thresholds configurable via settings API:
- `max_active_priorities: 5`
- `expiry_warning_days: 14`
- `stale_priority_days: 14`

## What Stays as Markdown

- `TASTE.md` — judgment instructions, not queryable data
- `PREFERENCES.md` — glue between context files, prose
- `PATTERNS.md` — classification patterns, written by Claude Code during triage

These stay in the repo, pushed via workspace-push.sh, read directly by skills.

## Rollout

### Phase 1 — Database + API (jimbo-api)
- ALTER TABLE adding four columns
- Extend CRUD endpoints for new fields
- Add /api/context/items/expiring endpoint

### Phase 2 — UI (site)
- Extend ItemRow with structured fields for priorities/goals
- Status chips and expiry warnings

### Phase 3 — Consumers (sandbox scripts)
- Update context-helper.py to include structured fields
- Migrate prioritise-tasks.py to read from API
- Update daily-briefing skill with conflict detection
- Add threshold settings to settings API

### Phase 4 — Backfill & cleanup
- Triage session to set status/timeframe/category on existing items
- Remove markdown fallback from context-helper.py
- Remove context file push from workspace-push.sh (keep files as historical reference)
- Write ADR

Each phase is independently deployable.
