# Vault Task Management System — Design Spec

**Date:** 2026-03-21
**Context:** Session 11 briefing review. The briefing is structurally competent but purposeless — it narrates static data instead of reporting on shared work. The vault (1,633 items, velocity 0) must become a living shared task system between Marvin and Jimbo.

**Key decisions made during design:**
- **Database-first.** jimbo-api SQLite is the source of truth for task state. Markdown vault files are retired as source of truth — the database already has everything via ingest.
- **Jimbo calls the API directly and often.** Every task operation is an API call. No file-based sync, no memory-core workarounds.
- **Jimbo is a collector, not a negotiator.** Tasks flow in silently. Grooming sessions handle decisions. Jimbo never asks "want to take this?"
- **Staleness is a signal, not a death sentence.** Tasks untouched for weeks get promoted, not archived. Marvin procrastinates on hard things — the system should help unblock, not hide.
- **The API is the product.** Everything else (Telegram, briefing, grooming, sub-agents, Claude Code, future UI) is a consumer. Build it modular, rich, testable, and easy to tweak.

---

## 1. Database Schema Changes

The `vault_notes` table already has: id, title, type, status, body, ai_priority, ai_rationale, manual_priority, sort_position, actionability, source, tags, created_at, updated_at, completed_at, raw_frontmatter.

### New columns

| Column | Type | Default | Purpose |
|--------|------|---------|---------|
| `owner` | TEXT | `'unassigned'` | `marvin`, `jimbo`, `unassigned` |
| `due_date` | TEXT | NULL | ISO 8601 date (e.g. `2026-03-22`) |
| `blocked_by` | TEXT | NULL | Free text — "waiting for iOS build" or task ID |
| `parent_id` | TEXT | NULL | FK to vault_notes.id for subtasks |
| `source_signal` | TEXT | NULL | What created this — `email:<subject>`, `telegram`, `google-tasks:<id>` |
| `last_nudged_at` | TEXT | NULL | ISO 8601 timestamp for nudge rate-limiting |
| `nudge_count` | INTEGER | 0 | Total nudges sent for this task |
| `route` | TEXT | `'unrouted'` | `jimbo_vps`, `claude_code`, `marvin`, `unrouted` |

### Status values

Expand from `active` to a proper lifecycle:

| Status | Meaning |
|--------|---------|
| `inbox` | Just arrived. Not yet triaged. |
| `active` | Triaged, ready to work. Shows in briefings. |
| `in_progress` | Someone's on it (owner set). |
| `blocked` | Can't proceed. `blocked_by` says why. |
| `done` | Completed. `completed_at` auto-populated. |
| `deferred` | "Not now." Hidden from briefings, resurfaces on `due_date` or manual recall. |
| `archived` | Dead. Manually archived during grooming. |

### Subtasks

Flat rows with `parent_id`. A subtask is a `vault_notes` row whose `parent_id` points to the parent. Query `WHERE parent_id = ?` to get subtasks. No nesting beyond one level.

### Migration

One `ALTER TABLE` migration adding the 8 columns. Existing rows keep `status = 'active'`, gain `owner = 'unassigned'`, `route = 'unrouted'`. No bulk archive — existing items stay active and get scored normally.

---

## 2. Task Lifecycle & State Machine

```
                    ┌──────────┐
  Google Tasks ────►│  inbox   │
  Email signal ────►│          │
  Telegram ────────►└────┬─────┘
                         │ triage (grooming session)
                         ▼
                    ┌──────────┐
              ┌─────│  active   │◄──── un-defer / un-block
              │     └────┬─────┘
              │          │ "I'll take this" / owner assigned
              │          ▼
              │     ┌──────────┐
              │     │in_progress│
              │     └──┬───┬───┘
              │        │   │ "blocked on X"
              │        │   ▼
              │        │ ┌──────────┐
              │        │ │ blocked  │──► unblocked ──► in_progress
              │        │ └──────────┘
              │        │
              │        │ "done" / "handled"
              │        ▼
              │     ┌──────────┐
              │     │   done   │
              │     └──────────┘
              │
              │ "not now" / "later"
              ▼
         ┌──────────┐
         │ deferred  │──► due_date arrives ──► active
         └──────────┘

         archived ◄── manual decision in grooming session only
```

### Transition triggers

| Transition | Trigger | API call |
|---|---|---|
| → inbox | Google Tasks sweep, email signal, Jimbo observation, Telegram | `POST /api/vault/notes {status: "inbox"}` |
| inbox → active | Grooming session triage, or auto (actionability=clear + source=google-tasks) | `PATCH {status: "active"}` |
| active → in_progress | Marvin: "I'll take this" / Jimbo self-assigns | `PATCH {status: "in_progress", owner: "marvin"\|"jimbo"}` |
| in_progress → blocked | "Blocked on X" | `PATCH {status: "blocked", blocked_by: "X"}` |
| blocked → in_progress | Blocker resolved | `PATCH {status: "in_progress", blocked_by: null}` |
| in_progress → done | "Done" / "Handled" / Jimbo completes work | `PATCH {status: "done"}` — API auto-sets `completed_at` |
| active → deferred | "Not now" / "Next week" | `PATCH {status: "deferred", due_date: "2026-03-28"}` |
| deferred → active | `due_date` passes (automated) or manual recall | `PATCH {status: "active", due_date: null}` |
| any → archived | Manual decision in grooming session | `PATCH {status: "archived"}` |

### Auto-triage rule

When a task arrives in `inbox`: if `actionability = 'clear'` and `source = 'google-tasks'` (already triaged by Marvin in Google Tasks), auto-promote to `active`. Everything else stays in `inbox` for the next grooming session.

### Deferred resurfacing

Runs as part of the daily 04:30 scoring job. Any task where `status = 'deferred'` and `due_date <= today` gets moved to `active`.

---

## 3. Conversational Protocol

Natural language in, API calls out. Jimbo parses intent and hits the API.

### Creating tasks

| Marvin says | Jimbo does |
|---|---|
| "Add a task: fix the iOS build" | `POST {title: "Fix the iOS build", status: "inbox", source_signal: "telegram"}` |
| "That Airbnb thing needs handling" | Creates task + links to email signal if vault-connector finds a match |
| *(Jimbo spots email urgency)* | `POST {title: "...", status: "inbox", source_signal: "email:<gmail_id>"}`. Reports in batch: "Added 2 tasks from this morning's email." |

### Assigning & updating

| Marvin says | Jimbo does |
|---|---|
| "I'll take this" / "On it" | `PATCH {status: "in_progress", owner: "marvin"}` |
| "You do it" / "Jimbo, handle this" | `PATCH {status: "in_progress", owner: "jimbo"}` then attempts the work |
| "Done" / "Handled" / "Sorted" | `PATCH {status: "done"}` |
| "Not now" / "Next week" | `PATCH {status: "deferred", due_date: <inferred>}` |
| "This is blocked on X" | `PATCH {status: "blocked", blocked_by: "X"}` |
| "Break this down" | Creates subtasks via multiple POSTs with `parent_id` |

### Querying

| Marvin says | Jimbo does |
|---|---|
| "How are we getting on?" | `GET /api/vault/tasks/summary` → formatted status report |
| "What's next?" | `GET /api/vault/notes?status=active&sort=effective_priority&limit=3` |
| "What's blocked?" | `GET /api/vault/notes?status=blocked` |
| "What did we get done this week?" | `GET /api/vault/tasks/summary` → velocity stats |

### Jimbo-initiated behaviour

Jimbo is a **collector, not a negotiator**. When he spots something actionable, he creates a task and moves on. He does not ask Marvin whether to create it or who should own it.

| Situation | Jimbo does |
|---|---|
| Google Tasks sweep finds new items | Creates as `inbox`. One summary message: "Picked up 4 new tasks from Google Tasks." |
| Email signal looks actionable | Creates as `inbox`. Mentions in next briefing. |
| Conversation produces action item | Creates as `inbox`. "Noted — added 'fix iOS build' to the backlog." |
| Overdue task | Surfaces in briefing, not as a standalone nudge |
| Deferred task resurfaces | Moves to `active`, surfaces in next briefing |

---

## 4. API Extensions

All endpoints authenticated with `X-API-Key`. jimbo-api (Hono/Node, SQLite).

### New endpoints

**Task summary:**

```
GET /api/vault/tasks/summary
```

Returns:
```json
{
  "done_today": 3,
  "done_this_week": 12,
  "new_today": 5,
  "inbox_count": 8,
  "active_count": 15,
  "in_progress": { "marvin": 2, "jimbo": 1 },
  "blocked": 1,
  "deferred": 4,
  "velocity_7d": 1.71,
  "velocity_30d": 0.8,
  "overdue": 2
}
```

Pure SQL aggregation. No LLM needed.

**Calculations:**
- `done_today`: `COUNT(*) WHERE status='done' AND date(completed_at)=date('now')`
- `done_this_week`: `COUNT(*) WHERE status='done' AND completed_at >= date('now', '-7 days')`
- `velocity_7d`: `done_this_week / 7.0` (rounded to 2dp)
- `velocity_30d`: `COUNT(done last 30 days) / 30.0`
- `overdue`: `COUNT(*) WHERE due_date < date('now') AND status NOT IN ('done','archived','deferred')`
- `in_progress`: grouped by `owner`

**Subtask scoring:** Subtasks are scored independently by `prioritise-tasks.py`. They have their own `ai_priority` and appear in queries unless filtered with `has_parent=false`. Parent tasks should use `has_parent=false` in briefing queries to avoid clutter.

**Batch PATCH validation:** Batch operations enforce the same transition rules as individual PATCHes. Invalid transitions are skipped with errors returned per-item in the response. This is a power tool for grooming but not a bypass of the state machine.

**Grooming session resumability:** If a grooming session is interrupted (Marvin stops responding, session timeout), re-invoke the skill. It reads current state from the API, so partially-groomed items retain their updates. No session state to recover.

**Routing in Phase 1:** The `route` column is added in the Phase 1 migration (cheap). Auto-routing logic is deferred to Phase 2. In Phase 1, tasks default to `unrouted` and can be manually routed during grooming sessions.

**Subtask operations:**

```
GET  /api/vault/notes/:id/subtasks    — children ordered by sort_position
POST /api/vault/notes/:id/subtasks    — creates note with parent_id set
```

**Batch status update (for grooming sessions):**

```
PATCH /api/vault/notes/batch
Body: { ids: ["note_abc", "note_def"], patch: { status: "archived" } }
```

### Extended query parameters on GET /api/vault/notes

| Parameter | Type | Example | Purpose |
|---|---|---|---|
| `owner` | string | `?owner=jimbo` | Filter by owner |
| `route` | string | `?route=claude_code` | Filter by routing |
| `overdue` | boolean | `?overdue=true` | `due_date < today`, status not done/archived |
| `due_before` | string | `?due_before=2026-03-22` | Deferred items ready to resurface |
| `parent_id` | string | `?parent_id=note_abc` | Get subtasks of a parent |
| `has_parent` | boolean | `?has_parent=false` | Exclude subtasks from top-level lists |

**Multi-value parameters:** `status` supports multiple values via repeated query params (`?status=active&status=inbox`) or comma-separated (`?status=active,inbox`). The API handler must split and filter on all provided values. Hono does not do this by default — requires explicit handling.

### Extended PATCH fields

The update handler gains: `owner`, `due_date`, `blocked_by`, `parent_id`, `source_signal`, `last_nudged_at`, `nudge_count`, `route`.

Status transition logic: when status → `blocked`, require `blocked_by` non-null. When status leaves `blocked`, clear `blocked_by`. When status → `done`, auto-set `completed_at`. When status leaves `done`, clear `completed_at`. (The completed_at logic already exists.)

---

## 5. Nudge Protocol

Core rule: **Jimbo surfaces task information in briefings and grooming sessions, not as standalone nudges.** Standalone nudges are the exception.

### When Jimbo CAN send a standalone Telegram message about a task

1. **Truly time-sensitive** — `due_date` is today or overdue, status not done/blocked/deferred
2. **Blocker resolved** — something Jimbo was tracking unblocked
3. **Task completed by Jimbo** — reporting back on work he did

### When Jimbo CANNOT nudge

- Task was nudged in last 4 hours (`last_nudged_at` check)
- Task is `done`, `deferred`, or `archived`
- Task is `blocked` (nothing Marvin can do — wait for blocker)
- Same task was already mentioned in today's briefing
- More than 3 standalone task nudges sent today (global daily cap)

### Implementation

Before sending any task-related Telegram message, Jimbo GETs the task, checks eligibility, sends if eligible, then PATCHes `last_nudged_at`.

### The briefing is the primary task surface

Morning briefing: done since yesterday, today's in-progress, overdue, inbox count. Afternoon briefing: done since morning, new blockers, mid-day inbox arrivals. Grooming session is the primary surface for decisions.

---

## 6. Daily Intake Pipeline

Three intake channels, all writing to the database via API.

### Channel 1: Google Tasks sweep (05:00 UTC daily)

`tasks-helper.py` revised to POST to API instead of writing markdown files.

```
05:00 UTC: tasks-helper.py
  → Google Tasks API: fetch incomplete tasks from "My Tasks"
  → For each task not in DB (dedup on source_signal = "google-tasks:<task_id>"):
      POST /api/vault/notes {
        title, body, type: "task", status: "inbox",
        source: "google-tasks", source_signal: "google-tasks:<task_id>"
      }
  → For each task completed in Google since last sweep:
      Find by source_signal → PATCH {status: "done"}
  → Log: "Swept Google Tasks: 3 new, 1 completed"
```

Marvin keeps using Google Tasks as a quick capture tool (phone, voice assistant). It flows into the system overnight.

### Channel 2: Email signals (during briefing pipeline)

`briefing-prep.py` gains a step after newsletter_reader:

```
  → For each gem with actionable=true or relevance_score >= 0.8:
      POST /api/vault/notes {
        title: <derived from gem>, body: <summary>,
        type: "task", status: "inbox", source: "email",
        source_signal: "email:<gmail_id>", actionability: "vague"
      }
```

Dedup on `source_signal`: if `email:<gmail_id>` already exists in the DB, skip. This prevents duplicate tasks when the same gem appears in both morning and afternoon pipeline runs.

These arrive as `inbox` with `actionability: vague`. The briefing mentions count but doesn't force triage.

### Channel 3: Telegram conversation

Direct API calls as described in the conversational protocol. `source_signal: "telegram"`.

### Daily scoring (04:30 UTC — revised)

`prioritise-tasks.py` switches from reading/writing frontmatter to API calls:

```
04:30 UTC: prioritise-tasks.py
  → GET /api/vault/notes?status=active&status=inbox&limit=200
  → Score each against priorities + goals (Gemini Flash)
  → PATCH each: {ai_priority, ai_rationale, actionability}
  → Auto-routing: if route = 'unrouted', infer from tags (see §9)
  → Deferred resurfacing: GET ?status=deferred&due_before=<today>
      → PATCH each: {status: "active", due_date: null}
  → Staleness boost: calculate days since last update,
      apply boost to effective priority (see §8)
```

---

## 7. Skill & Prompt Updates

### daily-briefing/SKILL.md — vault section rewrite

Replace the current "surface priority-9 tasks" section with a status report:

```markdown
4. **Task status** — Call GET /api/vault/tasks/summary. Report:
   - Done since last briefing (with titles if ≤5, count if more)
   - Currently in progress (by owner)
   - Blocked (with blocker text)
   - Overdue (due_date passed, not done)
   - New inbox items: "6 new tasks in the inbox — 3 from Google Tasks,
     2 from email, 1 from yesterday's conversation."

   Do NOT list all active tasks. Do NOT triage during the briefing.
   The briefing reports status; the grooming session makes decisions.

   If velocity_7d > 0: "We're closing about {velocity_7d} tasks per day
   this week."
```

### HEARTBEAT.md — task collector behaviour

Replace the "Vault surfacing (conditional)" section:

```markdown
## Task awareness (always applies)

You are a task collector, not a task negotiator. When you spot something
actionable — email, calendar event, conversation — create a task via
POST /api/vault/notes with status "inbox" and move on. Don't ask Marvin
whether to create it. Don't ask who should own it. Just log it.

Batch your reports: "Added 2 tasks to the inbox from this afternoon's
email check" — not individual messages per task.

Before sending any standalone task nudge, check eligibility:
- GET the task, check last_nudged_at (must be >4 hours ago)
- Task must be due today or overdue
- Status must be active or in_progress (not blocked/deferred/done)
- Max 3 standalone task nudges per day
If not eligible, save it for the next briefing.
```

### New skill: vault-grooming/SKILL.md

```markdown
---
name: vault-grooming
description: Interactive backlog grooming session via Telegram
user-invokable: true
---

# Vault Grooming

When Marvin says "let's groom" or "backlog review" or you have 10+
inbox items and suggest a session.

## Step 1: Prepare the summary

GET /api/vault/tasks/summary — report the numbers.
GET /api/vault/notes?status=inbox&sort=created_at&order=desc — inbox items.
GET /api/vault/notes?status=blocked — blocked items.
GET /api/vault/notes?status=active&actionability=needs-breakdown — need subtasks.

Present: "Ready to groom. 8 inbox, 2 blocked, 3 need breakdown.
Start with inbox?"

## Step 2: Walk through each category

**Inbox items** — present each with title, source, and when it arrived.
For each, Marvin says one of:
- "Active" → PATCH {status: active}
- "I'll take it" → PATCH {status: in_progress, owner: marvin}
- "Jimbo do it" → PATCH {status: in_progress, owner: jimbo}
- "Not now" / "Later" → PATCH {status: deferred} + ask for due_date
- "Archive" / "Kill it" → PATCH {status: archived}
- "Break it down" → ask for subtasks, POST each with parent_id

Move quickly. Don't explain each task — Marvin knows his own backlog.
If he says "skip", move to the next one.

**Blocked items** — for each, ask: "Still blocked on {blocked_by}?"
If resolved: PATCH {status: in_progress, blocked_by: null}

**Needs breakdown** — present the task, ask Marvin to list subtasks.
Create each as a separate POST with parent_id.

## Step 3: Wrap up

GET /api/vault/tasks/summary — report the new numbers.
"Groomed: 5 activated, 2 archived, 1 broken down into 3 subtasks.
Inbox down from 8 to 1."

Log to activity log.
```

### tasks-triage/SKILL.md — retire

The existing triage skill focused on `needs-context` vault files. The grooming skill replaces it. Mark as retired in CAPABILITIES.md.

---

## 8. The 1,633-Item Strategy

**No bulk archive. Reflect reality in priority.**

Existing items stay as `active`. No mass deletion. Staleness is a signal that a task needs help, not that it's dead.

### Staleness boost

A task untouched for weeks gets promoted, not hidden. Added to the scoring algorithm in `prioritise-tasks.py`:

```
staleness_days = (today - last_updated).days
staleness_boost = min(staleness_days / 15, 3.0)
effective_priority = ai_priority + staleness_boost
```

A priority-5 task untouched for 60 days becomes effectively priority-8. It surfaces in briefings and grooming sessions with context: "This has been sitting 60 days. What's blocking it? Can I help break it down?"

`effective_priority` is computed at query time by the API, not stored. The `/api/vault/notes` endpoint calculates `COALESCE(manual_priority, ai_priority) + MIN(CAST((julianday('now') - julianday(updated_at)) / 15 AS INTEGER), 3)` and supports `sort=effective_priority`. This avoids storing a derived value that would need recomputing daily.

### Jimbo's role with stale tasks

During heartbeat or briefing, when a stale task surfaces, Jimbo's job is to help unblock — not nag. "This task has been sitting 45 days: 'Fix iOS build and ship.' Want me to break it down into smaller steps?"

### The only automatic status change

`deferred` tasks with a `due_date` that arrives get moved to `active`. Everything else requires a human decision in a grooming session. Jimbo never auto-archives.

### Cleanup mechanism

Regular grooming sessions. Marvin decides what to archive. If something is truly dead weight, he says "archive it" during grooming. Over time, the backlog shrinks through grooming, not automation.

---

## 9. Sub-Agent Delegation & Task Routing

Design now, build in Phase 2. The vault task system is the foundation; sub-agents are consumers.

### Routing rules

| Task characteristics | Route to | Why |
|---|---|---|
| Tags contain `bookmark`, `reading`, `research` | `jimbo_vps` | vault_reader.py, vault_connector.py |
| Tags contain `blog`, `writing` | `jimbo_vps` | blog_drafter.py |
| Tags contain `code`, `software`, `deploy`, project names | `claude_code` | Needs repo access, real tooling |
| Tags contain `email`, `respond`, `contact` | `marvin` | External communication |
| Tags contain `finance`, `admin`, `personal` | `marvin` | Requires external accounts/actions |
| `actionability: needs-breakdown` | `unrouted` | Can't route until broken down |
| `actionability: vague` | `unrouted` | Needs clarification first |
| No matching rule | `unrouted` | Surfaces in grooming |

Auto-routing runs during the daily 04:30 scoring job. Only sets route if currently `unrouted`. Manual routing during grooming overrides.

### What a sub-agent needs

```json
{
  "task_id": "note_abc123",
  "title": "Summarise the 3 bookmarks tagged 'ai-agents'",
  "body": "Full task description and context",
  "success_criteria": "Each bookmark has a 2-paragraph summary",
  "tools_available": ["vault_reader.py", "vault_connector.py"],
  "write_back": "PATCH /api/vault/notes/:id",
  "model": "gemini-2.5-flash"
}
```

### Jimbo as coordinator (Phase 2)

```
Jimbo (heartbeat):
  → GET /api/vault/notes?owner=jimbo&status=in_progress&actionability=clear
  → For each delegable task:
      Pick worker based on task type/tags
      Run worker in sandbox
      If success: PATCH {status: done} + log result
      If failure: PATCH {blocked_by: "worker failed: <reason>"}
      Report in next briefing
```

### Handoff protocol

The database is the communication channel between agents. When Jimbo can't complete a task:

```
Jimbo → PATCH {status: blocked, blocked_by: "Needs code review", route: "claude_code"}
Claude Code → GET /api/vault/notes?route=claude_code&status=blocked
           → picks up task, does work
           → PATCH {status: done}
Jimbo → sees done in next heartbeat
```

### Opus 1M + Claude Code integration (Phase 3)

Marvin opens Claude Code, queries the task API, spins up parallel agents per task. Each agent has full repo context via Opus 1M. This layer consumes the API — the vault task system doesn't need to know about it.

```
Claude Code (Marvin's laptop):
  → GET /api/vault/notes?route=claude_code&status=in_progress
  → Spawn agent per task with full context
  → On completion: PATCH {status: done}
  → Marvin reviews results
```

---

## 10. Model Considerations

| Operation | Model | Why |
|---|---|---|
| Task creation (POST) | Any — Kimi K2 fine | Structured API call |
| Status updates (PATCH) | Any — Kimi K2 fine | Simple keyword → API |
| "How are we getting on?" | Any — Kimi K2 fine | Reads summary, formats text |
| Grooming session | Sonnet preferred | Ambiguous response parsing, breakdown suggestions |
| Task creation from email | Sonnet (briefing window) | Judgment about actionability |
| Auto-routing from tags | Gemini Flash (scoring job) | Batch, cheap, rule-following |
| Sub-agent execution | Flash for reading, Sonnet for synthesis | Match model to complexity |
| Claude Code pickup | Opus 4.6 (1M context) | Full repo context |

Key principle: the API doesn't care which model calls it. Keep the protocol simple enough that Kimi K2 handles 80% of interactions.

---

## 11. Implementation Phases

### Phase 1 — Core lifecycle (build first)

1. Database migration — add 8 new columns to `vault_notes`
2. API extensions — `GET /api/vault/tasks/summary`, `PATCH /api/vault/notes/batch`, subtask routes, new query params (`owner`, `route`, `overdue`, `due_before`, `parent_id`, `has_parent`)
3. Extend `PATCH /api/vault/notes/:id` — accept new fields, status transition logic
4. Revise `tasks-helper.py` — POST to API instead of writing markdown
5. Revise `prioritise-tasks.py` — score via API, staleness boost, deferred resurfacing
6. New `vault-grooming` skill (SKILL.md)
7. Update `daily-briefing` skill — status report section
8. Update `HEARTBEAT.md` — task collector behaviour, nudge rules
9. Tests for all new endpoints

### Phase 2 — Sub-agent delegation

1. Auto-routing logic in `prioritise-tasks.py` (infer `route` from tags)
2. Jimbo picks up `route: jimbo_vps` tasks during heartbeat
3. Worker dispatch based on task type/tags
4. Handoff protocol (route changes, `blocked_by` signalling)
5. Claude Code integration (query API, pick up `route: claude_code` tasks)

### Phase 3 — Enrichment & UI

1. Grooming UI (web, not just Telegram)
2. Task board / kanban view on personal site
3. Velocity charts, burndown

Each phase is independently useful. Phase 1 gives "how are we getting on?" and grooming sessions. Phase 2 gives delegation. Phase 3 gives visibility.

---

## 12. Success Criteria

- Vault velocity > 0 within first week
- "How are we getting on?" returns real numbers
- Google Tasks sweep creates DB tasks (not markdown files)
- At least one grooming session per week
- Nudge spam eliminated (max 3 standalone/day)
- Briefing vault section is a status report, not a static list
- Stale tasks surface with higher urgency, not lower
- Grooming is the cleanup mechanism, not automated decay

---

## What Stays Unchanged

- `briefing-prep.py` (data collection pipeline) — gains one step for email-to-task
- `email_triage.py`, `newsletter_reader.py` (email pipeline)
- `calendar-helper.py`, `context-helper.py` (existing tools)
- SOUL.md (personality)
- Security model (Zone 1 sandbox, readonly email, no external sends)
- Existing autonomous mind modules (vault_reader, vault_connector, vault_roulette) — these become tools that sub-agents use in Phase 2

## What Gets Retired

- Vault markdown files as source of truth — database replaces them
- `tasks-triage` skill — replaced by broader `vault-grooming` skill
- `tasks-triage-pending.json` — no longer needed once `tasks-helper.py` writes to API
- `POST /api/vault/ingest` — keep for now, retire after migration confirmed
- `prioritise-tasks.py` frontmatter reading/writing — replaced by API calls
