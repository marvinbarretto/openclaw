# Activity Stream — Design Document

## Problem

Jimbo logs every activity to `activity-log.db` via CLI, but this data is locked in SQLite on the VPS. The dashboard shows a flat list of recent activities from a static JSON export (stale, no rationale, no day structure). As Jimbo becomes more autonomous, we need:

1. A way for Jimbo to write activities with **rationale** — not just "what happened" but "why I made this decision"
2. A live API so the dashboard shows today's activity in real time
3. Day-based navigation with RESTful URLs for historical browsing and future comparison

## Design

### 1. Schema change: add `rationale` to activity-log.py

Add a `rationale` TEXT column to the activities table. This captures Jimbo's reasoning — "shortlisted 12 emails because they matched travel and tech interests" vs just "triaged 38 emails".

```sql
ALTER TABLE activities ADD COLUMN rationale TEXT;
```

CLI change:
```
python3 activity-log.py log --task email-check --description "..." --rationale "..." --model ...
```

All existing `activity-log.py log` calls across skills and workers get updated to include `--rationale` where meaningful.

### 2. jimbo-api: `/api/activity` endpoints

New route file: `src/routes/activity.ts` + `src/services/activity.ts`

New SQLite table in `context.db` (same DB as context/settings — single database, simpler ops):

```sql
CREATE TABLE IF NOT EXISTS activities (
  id TEXT PRIMARY KEY,
  timestamp TEXT NOT NULL,
  task_type TEXT NOT NULL,
  description TEXT NOT NULL,
  outcome TEXT,
  rationale TEXT,
  model_used TEXT,
  cost_id TEXT,
  satisfaction INTEGER,
  notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_activities_ts ON activities(timestamp);
CREATE INDEX IF NOT EXISTS idx_activities_type ON activities(task_type);
```

**Endpoints:**

| Method | Path | Purpose |
|--------|------|---------|
| `POST /api/activity` | Log a new activity (from sandbox) | Write |
| `GET /api/activity?date=2026-03-02` | Get activities for a specific day | Read |
| `GET /api/activity?days=7` | Get activities for last N days | Read |
| `GET /api/activity/stats?days=30` | Aggregated stats | Read |
| `PUT /api/activity/:id/rate` | Rate an activity (satisfaction) | Write |

**POST body:**
```json
{
  "task_type": "email-check",
  "description": "Email fetch — 142 messages, 38 after blacklist",
  "outcome": "12 shortlisted for deep read",
  "rationale": "Prioritised newsletters over transactional emails. Flagged 3 travel deals because Buenos Aires and Scotland trips are in PRIORITIES.md.",
  "model_used": "gemini-2.5-flash",
  "cost_id": "cost_abc123"
}
```

### 3. Sandbox client: `activity-helper.py`

New stdlib-only Python script in `/workspace/`. Calls jimbo-api to log activities instead of writing to local SQLite. This means activity data lives in the API database (same as context and settings), not in a separate SQLite file that needs exporting.

```
python3 activity-helper.py log --task briefing --description "..." --rationale "..." --model haiku
python3 activity-helper.py log --task email-check --description "..." --outcome "..."
```

Reads `JIMBO_API_URL` and `JIMBO_API_KEY` from env (same as context-helper.py and settings-helper.py).

**Migration path:** Keep `activity-log.py` for now (backward compat). `activity-helper.py` is the new way. Skills and workers migrate to use the API client. Eventually deprecate the local SQLite approach.

### 4. Dashboard integration

**Dashboard card** (`/app/jimbo/index.astro`): Replace static JSON fetch with API call to `GET /api/activity?date=today`. Render the timeline we already prototyped. Link to the dedicated page.

**Dedicated page** (`/app/jimbo/activity/[...date].astro`): Astro dynamic route with a React island (`ActivityTimeline.tsx`).

- Default (no date): today
- RESTful URLs: `/app/jimbo/activity/2026-03-02`
- Prev/next day navigation
- Each entry shows: time, task type (coloured), description, outcome, rationale (expandable)
- "Now" marker on today's view
- Future: day comparison side-by-side

### 5. What gets rationale

Not every activity needs rationale. Guidelines for Jimbo:

| Task type | Rationale? | Example |
|-----------|-----------|---------|
| briefing | Yes | "Highlighted the Anjuna event because INTERESTS.md lists fabric/music. Proposed 14:00 slot for LocalShout because it's been 5 days since last work." |
| email-check | Sometimes | "Fetched 38 emails. No rationale needed for routine fetch." |
| digest | Yes | "Shortlisted 12 of 38 emails. Travel deals scored high because PRIORITIES has Buenos Aires trip. Skipped LinkedIn notifications and retail receipts." |
| tasks-triage | Yes | "Classified 'fix displaylink thing' as task/hardware — matched the standing desk context from previous conversations." |
| research | Yes | "Looked up Watford fixtures because match day is in 6 days and Marvin usually plans around it." |
| blog | Yes | "Published post about note triaging because the 13,000 note project is a good story and aligns with Jimbo's voice." |
| heartbeat | No | Routine check, no decision-making involved. |

## Implementation order

1. Add `rationale` column to `activity-log.py` schema + CLI (backward compat)
2. Add activities table to jimbo-api DB schema
3. Add `/api/activity` routes + service to jimbo-api
4. Create `activity-helper.py` sandbox client
5. Update dashboard card to fetch from API
6. Create dedicated `/app/jimbo/activity/[...date].astro` page with React island
7. Migrate skills/workers to use `activity-helper.py` with rationale

## Files to create/modify

| File | Repo | Change |
|------|------|--------|
| `workspace/activity-log.py` | openclaw | Add `rationale` column + CLI arg |
| `workspace/activity-helper.py` | openclaw | **New.** API client for sandbox → jimbo-api |
| `src/routes/activity.ts` | jimbo-api | **New.** Activity API routes |
| `src/services/activity.ts` | jimbo-api | **New.** Activity CRUD service |
| `src/db/index.ts` | jimbo-api | Add activities table to schema |
| `src/pages/app/jimbo/index.astro` | site | Fetch from API instead of static JSON |
| `src/pages/app/jimbo/activity/[...date].astro` | site | **New.** Dedicated activity page |
| `src/components/activity/ActivityTimeline.tsx` | site | **New.** React island for timeline |
| `src/components/activity/ActivityTimeline.scss` | site | **New.** Timeline styles |
| `skills/daily-briefing/SKILL.md` | openclaw | Update activity logging to use rationale |
| `skills/tasks-triage/SKILL.md` | openclaw | Update activity logging to use rationale |
