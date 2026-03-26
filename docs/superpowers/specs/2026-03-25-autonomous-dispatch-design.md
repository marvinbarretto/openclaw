# Autonomous Task Dispatch System

**Date:** 2026-03-25
**Status:** Design — awaiting implementation plan
**Depends on:** jimbo-api (vault, activity, experiments), M2 home station (Claude Code), Telegram bot

## Problem

Jimbo's vault has ~1,600 scored tasks, ideas, and bookmarks. The scoring pipeline (prioritise-tasks.py) runs daily, producing priority rankings and actionability assessments. The briefing pipeline surfaces top items each morning. But nothing acts on them autonomously — Marvin still has to manually pick work, open a terminal, and drive it himself.

Meanwhile, the M2 home station (MacBook Air, always-on, Tailscale-connected) has been proven as a Claude Code execution environment via `claude -p --bare`. The infrastructure exists on both ends — vault scoring on VPS, agent execution on M2 — but there's no bridge between them.

## Solution

An autonomous dispatch system that:
1. Selects prioritised work from the vault or GitHub issues
2. Proposes curated batches for Marvin's approval via Telegram
3. Dispatches approved tasks to specialised agents on M2
4. Posts results back to the source (PR, vault update, research summary)
5. Continuously proposes the next batch when the current one completes

The system operates as a scrum-like loop: tasks are groomed to meet a Definition of Ready, dispatched to the right agent type, executed autonomously, and results feed back into the vault and accountability pipeline.

## Design Decisions

| Decision | Choice | Reasoning |
|----------|--------|-----------|
| Approval model | Curated batch with continuous drip | Marvin keeps oversight without per-task friction. System stays hungry. |
| Agent types | Coder, Researcher, Drafter | Covers the three main shapes of dispatchable work. Extensible later. |
| Orchestrator location | VPS | jimbo-api is the source of truth. Telegram notifications go through VPS. Follows existing patterns. |
| Execution location | M2 via SSH + tmux | Proven pattern. Claude Code on Max plan = $0 token cost. |
| Queue state | jimbo-api SQLite | Single source of truth. Dashboard + Telegram both read from it. |
| Scheduling | Cron every 5 minutes | No daemon to babysit. Stateless. Code comments note upgrade path to persistent daemon (Approach 3). |
| Approval surface | Web-link in Telegram message (v1), dashboard later | Avoids Telegram `getUpdates` conflict with OpenClaw. Inline keyboards and dashboard are noted as future upgrades. |
| Prompt templates | Separate files in workspace/dispatch/templates/ | Prompt engineering iterates independently of dispatch code. Pushed via workspace-push.sh. |

## North Star: Full Agent Runtime (Approach 3)

This design (Approach 2) is a stepping stone toward a full agent runtime. Code comments throughout should reference this vision:

- **Worker pool:** One-at-a-time execution upgrades to concurrent agents with resource management
- **Agent daemon:** Cron-based polling upgrades to a persistent M2 daemon with heartbeat
- **Capability registration:** Hard-coded agent types upgrade to a registry where agents declare what they can do
- **Inline keyboards:** Text-based Telegram approval upgrades to interactive buttons
- **Git worktrees:** Shared repo upgrades to isolated worktrees per agent session
- **Structured output validation:** Trust-based result parsing upgrades to schema validation

Build Approach 2 first. Let it run for a month. Upgrade to Approach 3 when you hit actual scaling problems.

## Architecture

### System Overview

```
VPS (167.99.206.214)                         M2 (100.121.128.3)
┌─────────────────────────┐                  ┌──────────────────┐
│ jimbo-api               │                  │ Claude Code      │
│  ├── vault (tasks)      │                  │  ├── localshout/  │
│  ├── dispatch_queue     │   SSH + tmux     │  ├── spoons/     │
│  ├── activity log       │◄────────────────▶│  ├── openclaw/   │
│  └── experiments        │                  │  └── /tmp/dispatch│
│                         │                  │       -results    │
│ dispatch.py (cron 5min) │                  └──────────────────┘
│  ├── propose batches    │
│  ├── monitor M2 agents  │
│  └── handle completions │
│                         │
│ Telegram Bot API        │
│  ├── batch proposals    │
│  │   (with approval     │
│  │    web-links)         │
│  └── status updates     │
└─────────────────────────┘
```

### Task Lifecycle

Every vault task follows one path through the system:

```
                    ┌─────────────────────────────────────────────┐
                    │           GROOMING SESSION                  │
                    │  (Marvin + Opus, interactive, on-demand)    │
                    │  Adds: DoD, agent_type, SMART criteria      │
                    └────────────────┬────────────────────────────┘
                                     │
                                     ▼
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌───────────┐    ┌───────────┐
│  SCORED  │───▶│  DoR     │───▶│  READY   │───▶│ PROPOSED  │───▶│ APPROVED  │
│          │    │  GATE    │    │  (vault)  │    │  (batch)  │    │  (batch)  │
└──────────┘    └────┬─────┘    └──────────┘    └───────────┘    └─────┬─────┘
  prioritise-        │                                                  │
  tasks.py      fails DoR                                          Marvin
  (existing)         │                                            approves
                     ▼                                                  │
              ┌──────────────┐                                         ▼
              │ NEEDS        │                              ┌───────────────┐
              │ GROOMING     │                              │  DISPATCHING  │
              │ (backlog)    │                              │  (SSH → M2)   │
              └──────────────┘                              └───────┬───────┘
                                                                    │
                                                                    ▼
                                                            ┌───────────────┐
                                                            │   RUNNING     │
                                                            │ (claude -p)   │
                                                            └───────┬───────┘
                                                                    │
                                                          ┌─────────┴─────────┐
                                                          ▼                   ▼
                                                   ┌───────────┐      ┌───────────┐
                                                   │ COMPLETED │      │  FAILED   │
                                                   │ (PR/report│      │ (retry or │
                                                   │  posted)  │      │  backlog) │
                                                   └───────────┘      └───────────┘
```

**Vault task fields for dispatch:**
- `dispatch_status`: none | needs_grooming | ready | (then tracked in dispatch_queue)
- `agent_type`: coder | researcher | drafter
- `definition_of_done`: concrete statement of what "done" looks like

**Relationship to existing vault `route` field:** The vault task system spec (2026-03-21) defines a `route` column with values `jimbo_vps`, `claude_code`, `marvin`, `unrouted`. The dispatch system builds on this: `route: claude_code` tasks are the primary dispatch candidates. The `agent_type` field refines what kind of Claude Code work it is (coder/researcher/drafter). During DoR evaluation, `route: claude_code` is an additional filter alongside actionability and priority. Tasks with other routes are not dispatch candidates. Auto-routing logic in prioritise-tasks.py can set `route: claude_code` for software-tagged tasks, but manual routing during grooming takes precedence.

### The Scrum Feedback Loop

```
Vault tasks scored daily (04:30, existing)
      │
      ▼
DoR gate filters → ready queue
      │
      ▼
Dispatch proposes batch → Marvin approves → agents execute
      │                                          │
      │                                    ┌─────┴──────┐
      │                                    ▼             ▼
      │                              completed       blocked/failed
      │                                    │             │
      │                                    ▼             ▼
      │                              vault updated   needs_grooming
      │                                    │             │
      ▼                                    ▼             ▼
Next grooming session ◄──── surfaces blocked tasks + new vault items
      │                     from email/calendar/conversation
      │
      ▼
Marvin + Opus refine → tasks get DoD + agent_type → back to ready
```

## Components

### 1. Definition of Ready Gate

The DoR gate runs as a filter inside jimbo-api when dispatch proposes a batch. It does not store anything — it evaluates vault tasks against criteria and only selects those that pass.

**A task is Ready when it has ALL of:**
1. `agent_type` — explicitly set (coder, researcher, or drafter)
2. `definition_of_done` — concrete, measurable completion criteria
3. `actionability: clear` — as scored by prioritise-tasks.py
4. `ai_priority >= 5` — worth dispatching

**A task is Needs Grooming when:**
- Missing `agent_type` OR `definition_of_done`
- `actionability: vague` or `needs-breakdown`
- Has been `blocked` or `failed` twice (spec problem, not agent problem)

**For GitHub issues:** Issues with `ralph` + `sandbox` labels are treated as pre-groomed. The system maps acceptance criteria to `definition_of_done` and assigns `agent_type: coder`. Issues without acceptance criteria fail DoR and get a comment posted.

**Grooming sessions** are interactive (Marvin + Opus) and happen outside the dispatch system. They produce tasks that meet DoR. This can happen via terminal (`claude -p`), Telegram conversation with Jimbo, or dashboard. The dispatch system doesn't care how tasks become ready — it just checks the gate.

### 2. Dispatch Queue (jimbo-api)

**New table:**

```sql
CREATE TABLE dispatch_queue (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id TEXT NOT NULL,
  task_source TEXT NOT NULL DEFAULT 'vault',  -- 'vault' (v1), 'github' (future)
  agent_type TEXT NOT NULL,           -- 'coder', 'researcher', 'drafter'
  batch_id TEXT,                      -- groups tasks proposed together (batch-YYYYMMDD-HHMMSS)
  status TEXT NOT NULL DEFAULT 'proposed',  -- proposed/approved/rejected/dispatching/running/completed/failed
  dispatch_prompt TEXT,               -- the full prompt sent to the agent
  dispatch_repo TEXT,                 -- repo path on M2 (for coder tasks)
  result_summary TEXT,
  result_artifacts TEXT,              -- JSON: {pr_url, branch, files_changed, ...}
  error_message TEXT,
  retry_count INTEGER DEFAULT 0,
  proposed_at TEXT,
  approved_at TEXT,
  rejected_at TEXT,                   -- for cooldown: don't re-propose within 24h
  started_at TEXT,
  completed_at TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_dispatch_status ON dispatch_queue(status);
CREATE INDEX idx_dispatch_task_id ON dispatch_queue(task_id);
CREATE INDEX idx_dispatch_batch_id ON dispatch_queue(batch_id);
```

Tasks only enter this table after passing the DoR gate. All task content (title, DoD, priority) is read from the vault at proposal time and baked into `dispatch_prompt`. The queue tracks execution state, not task content — join back to vault via `task_id` for display.

**New API endpoints:**

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `GET /api/dispatch/queue` | GET | List queue items, filterable by status |
| `POST /api/dispatch/propose` | POST | Evaluate ready tasks, create a batch proposal |
| `POST /api/dispatch/approve` | POST | Approve a batch (by batch_id) or individual items |
| `POST /api/dispatch/reject` | POST | Reject a batch — items marked `rejected` with cooldown timestamp |
| `GET /api/dispatch/next` | GET | Return next approved task for execution |
| `POST /api/dispatch/start` | POST | Mark task as dispatching/running |
| `POST /api/dispatch/complete` | POST | Agent reports completion with results |
| `POST /api/dispatch/fail` | POST | Agent reports failure with error |
| `GET /api/dispatch/history` | GET | Completed/failed items with filtering |

**Batch proposal logic** (inside `POST /api/dispatch/propose`):
1. Query vault tasks passing DoR gate (`route: claude_code`, `actionability: clear`, `ai_priority >= 5`, has `agent_type` + `definition_of_done`), ordered by `ai_priority` DESC
2. Exclude tasks already in the queue (any status) or rejected within the last 24 hours (cooldown prevents re-proposing the same tasks repeatedly)
3. Take top N tasks (batch size from request param, default 3)
4. Generate `dispatch_prompt` for each using agent type template + task content
5. Create dispatch_queue rows with `status: proposed`, same `batch_id`
6. Return the batch

**GitHub issues deferred to Phase 3.** v1 focuses on vault tasks only. The vault alone has 1,600+ items — getting dispatch working for vault tasks first is a complete product. GitHub issue integration adds API authentication complexity (which PAT? stdlib urllib for GitHub REST API) that isn't worth solving in v1.

### 3. The Orchestrator (`dispatch.py`)

Single Python script on VPS, stdlib only, runs via cron every 5 minutes.

**Lockfile:** Each invocation acquires `/tmp/dispatch.lock` via `fcntl.flock(LOCK_EX | LOCK_NB)`. If another instance is already running (e.g. previous cron overlapped), exit immediately. Prevents race conditions from slow SSH calls.

**Dry-run mode:** `dispatch.py --dry-run` goes through all steps (propose, build prompt, log decisions) but stops short of SSH-ing to M2. Follows project convention: scripts default to dry-run, `--live` flag for writes.

**The loop (each invocation):**

0. **Acquire lock.** Exit if another instance is running.
1. **M2 reachable?** → Quick Tailscale check (`ssh -o ConnectTimeout=5 m2 true`). If offline, set `m2_offline` flag in jimbo-api settings, send one Telegram alert (suppressed on subsequent checks), skip to step 5. On reconnection, clear flag and check for orphaned tmux sessions.
2. **Any tasks RUNNING?** → Monitor M2 tmux session (poll signal file). On complete → POST `/api/dispatch/complete`. On timeout → POST `/api/dispatch/fail`.
3. **Any tasks APPROVED?** → Pick next. SSH to M2, push prompt file, start tmux session. POST `/api/dispatch/start`.
4. **Any tasks PROPOSED?** → Wait. Marvin hasn't approved yet.
5. **Ready tasks available?** → POST `/api/dispatch/propose`. Send Telegram batch message.
6. **Queue empty** → Exit. Next cron invocation checks again in 5 minutes.

**One task at a time.** v1 constraint — no concurrency. Code comments reference Approach 3 worker pool.

**SSH connection multiplexing:** Configure `ControlMaster auto` for the VPS→M2 connection in `/root/.ssh/config` (same pattern as the existing VPS SSH config). This ensures multiple SSH commands per invocation reuse a single connection, avoiding Tailscale connection bursting. Where possible, combine multiple commands into a single SSH call.

**M2 execution pattern:**

```bash
# Push prompt file to M2
ssh m2 "cat > /tmp/dispatch-{task_id}.prompt" < prompt_content

# Start agent in tmux
ssh m2 "tmux new-session -d -s dispatch-{task_id} \
  'claude -p --bare --dangerously-skip-permissions \
   \"$(cat /tmp/dispatch-{task_id}.prompt)\" \
   > /tmp/dispatch-{task_id}.log 2>&1; \
   echo DISPATCH_DONE > /tmp/dispatch-{task_id}.signal'"

# Monitor (polled each cron invocation — combined into single SSH call)
ssh m2 "cat /tmp/dispatch-{task_id}.signal 2>/dev/null && cat /tmp/dispatch-{task_id}.result 2>/dev/null"

# Cleanup after result collection
ssh m2 "rm -f /tmp/dispatch-{task_id}.{prompt,log,signal,result}"
```

**Timeouts per agent type:** Coder: 30min. Researcher: 15min. Drafter: 20min (configurable via jimbo-api settings). On timeout, tmux session is killed, task marked failed.

**Security note:** `--dangerously-skip-permissions` grants the agent full system access on M2. This is necessary for autonomous execution but means prompt-level constraints ("do not modify unrelated files") are the only guardrail. v1 accepts this risk. Approach 3 adds git worktrees for isolation — flagged as the first upgrade when running concurrent agents.

**Telegram notifications:**

| Event | Message format |
|-------|---------------|
| Proposed | `[Dispatch] Batch #12 — 3 tasks ready: {list}. [Approve all](link) [Reject](link)` |
| Approved | `[Dispatch] Batch #12 approved. Starting first task.` |
| Running | `[Dispatch] Running: {title} ({agent_type})` |
| Completed | `[Dispatch] Done: {title} — {summary}` |
| Failed | `[Dispatch] Failed: {title} — {error}. Moved to backlog.` |
| Blocked | `[Dispatch] Blocked: {title} — {blocker}. Needs grooming.` |
| Queue empty | `[Dispatch] Batch complete. {n}/{total} succeeded. Proposing next...` |

### 4. Approval Flow

**Critical constraint:** OpenClaw already consumes Telegram messages via the bot's polling/webhook mechanism. A second consumer calling `getUpdates` would steal messages from OpenClaw. The dispatch system MUST NOT read from Telegram — it can only write (send messages via Bot API).

**Telegram + web-link (v1):**

dispatch.py sends a proposal message to Telegram containing clickable approval links:

```
[Dispatch] Batch #12 — 3 tasks ready:

1. coder — localshout-next #42: add dark mode toggle
2. researcher — vault-389: compare YNAB vs Actual Budget
3. drafter — vault-412: draft blog post on AI governance

Approve all: https://167.99.206.214/api/dispatch/approve?batch=batch-20260325-143000&token=xyz
Approve 1,3: https://167.99.206.214/api/dispatch/approve?batch=batch-20260325-143000&items=1,3&token=xyz
Reject: https://167.99.206.214/api/dispatch/reject?batch=batch-20260325-143000&token=xyz
```

Marvin taps a link on his phone. jimbo-api processes the request, updates the queue, returns a simple confirmation page. dispatch.py picks up the approved tasks on its next cron cycle.

**Approval tokens:** Each batch gets a short-lived token (SHA-256 of batch_id + secret + expiry). Links expire after 24 hours. This prevents replay attacks without requiring a login flow.

**Batch ID format:** `batch-YYYYMMDD-HHMMSS` (e.g. `batch-20260325-143000`) for readability in Telegram messages and logs.

**Approval expiry:** Batches not approved within 24 hours are automatically rejected. Tasks return to the ready pool.

**Dashboard (v2):** `/app/jimbo/dispatch` on the site with approve/reject buttons calling the same API. Not required for v1 — Telegram web-links are sufficient.

### 5. Agent Prompt Templates

Templates live in `workspace/dispatch/templates/`, pushed to VPS via `workspace-push.sh`. Prompt engineering iterates independently of dispatch code.

Each template receives task-specific variables (title, definition_of_done, repo path, task_id) and produces a self-contained prompt for `claude -p`.

**Three templates:**
- `coder.md` — Clone/branch, implement, test, commit, push, open PR
- `researcher.md` — Search, compare, write structured summary
- `drafter.md` — Research topic, write content, save to specified path

**Result contract:** Every agent writes JSON to `/tmp/dispatch-{task_id}.result`:

```json
{
  "status": "completed | blocked",
  "summary": "one paragraph of what was done",
  "pr_url": "..." ,
  "output_path": "...",
  "files_changed": [],
  "blockers": "..."
}
```

**Result parsing:** dispatch.py attempts `json.loads()` on the result file. If parsing fails (markdown fences, malformed output, partial write), it falls back to treating the raw file content as a plaintext summary and marks the task as `completed` with a warning flag — not `failed`. The agent did work; the structured output just didn't parse. If the result file is missing entirely (crash, timeout), the task is marked `failed`.

The `blocked` status means the agent tried but the task wasn't actually ready — it goes to `needs_grooming`, not `failed`.

**Constraints baked into every template:**
- Do not modify files unrelated to the task
- Do not add dependencies without justification
- If stuck, write blockers to result file and stop (don't spin)

### 6. Result Handling

On agent completion:

1. dispatch.py reads `/tmp/dispatch-{task_id}.result` from M2
2. Parses JSON, extracts status/summary/artifacts
3. Posts to `POST /api/dispatch/complete`
4. Updates vault task based on outcome:

| Agent result | Vault update | Next step |
|---|---|---|
| `completed` (coder) | `status: done`, PR URL attached | Telegram notification, next task |
| `completed` (researcher) | `status: done`, summary attached | Telegram notification, next task |
| `completed` (drafter) | `status: done`, output path attached | Telegram notification, next task |
| `blocked` | `dispatch_status: needs_grooming` | Telegram notification, surfaces in next grooming |
| `failed` (retry < 2) | `retry_count += 1`, back to approved | Retry immediately |
| `failed` (retry >= 2) | `dispatch_status: needs_grooming` | Telegram notification, needs human |

5. Logs to activity-log via jimbo-api
6. Logs to experiment-tracker (model, duration, task type)
7. If more approved tasks → dispatch next. If none → propose next batch.

### 7. Accountability Integration

The existing `accountability-check.py` (20:00 UTC) gets a new check: `check_dispatch_today()`.

Reports: tasks dispatched, completed, failed, blocked, total agent time. Shows up in evening Telegram summary alongside existing briefing/gems/activity metrics.

Cost tracking: Claude Code on M2 via Max plan = $0 tokens, but duration and task count are tracked for velocity metrics.

## New Infrastructure Summary

| Component | Where | What's new |
|-----------|-------|-----------|
| `dispatch_queue` table | jimbo-api | New SQLite table + 9 API endpoints |
| `dispatch.py` | VPS `/workspace/` | New orchestrator script (stdlib Python) |
| Prompt templates | VPS `/workspace/dispatch/templates/` | 3 template files (coder, researcher, drafter) |
| Vault task fields | jimbo-api | New fields: `dispatch_status`, `agent_type`, `definition_of_done` |
| Cron entry | VPS root crontab | `*/5 * * * *` dispatch.py |
| SSH key | VPS → M2 | Passwordless SSH from VPS to M2 via Tailscale |
| accountability check | VPS `accountability-check.py` | New `check_dispatch_today()` function |
| Dashboard page | site `/app/jimbo/dispatch` | v2 — not required for v1 |

## What This Does NOT Change

- Vault scoring pipeline (prioritise-tasks.py) — untouched
- Briefing pipeline (Tier 1 scripts) — untouched
- OpenClaw/Jimbo conversation — untouched
- HEARTBEAT.md — untouched
- Email pipeline — untouched
- Security model — M2 has its own repo clones, no VPS credentials

## Phased Rollout

### Phase 1: Queue infrastructure (jimbo-api)
- Add dispatch_queue table and migration
- Add vault task fields (dispatch_status, agent_type, definition_of_done) if not already present from vault task system spec
- Implement 9 API endpoints + approval web-link handler
- Add approval token generation/validation
- Test with curl

### Phase 2: Orchestrator (VPS)
- Build dispatch.py following briefing-prep.py patterns (lockfile, dry-run, graceful degradation)
- Configure SSH ControlMaster for VPS→M2 connection
- Implement Tailscale connectivity detection with offline handling
- Implement SSH + tmux execution on M2 with cleanup
- Implement Telegram notification via existing alert.py pattern (send only, no read)
- Add cron entry
- Update workspace-push.sh to include `workspace/dispatch/templates/`
- Test with one manually-groomed vault task

### Phase 3: Prompt templates
- Write coder.md, researcher.md, drafter.md templates
- Test each with a real task end-to-end
- Iterate on prompt quality and result contract reliability

### Phase 4: Integration
- Wire accountability-check.py dispatch reporting
- Groom 5-10 vault tasks to ready state (first grooming session)
- Run first real batch
- Monitor for a week

### Phase 5: GitHub issues (v2)
- Add GitHub API integration for reading `ralph` + `sandbox` issues
- Map acceptance criteria to definition_of_done
- Test with a localshout-next issue

### Phase 6: Dashboard (v2)
- Build `/app/jimbo/dispatch` on site
- Approve/reject from browser
- Dispatch history and metrics

## Open Questions

1. ~~**M2 repo state:**~~ Confirmed — M2 has all repos cloned and up to date. Pre-flight check in dispatch.py should still verify clean branch state before dispatching coder tasks.

2. **Prompt length limits:** `claude -p` reads from stdin or a quoted argument. Very long prompts may need file-based input. Test the limits during Phase 3.

3. **Grooming session UX:** The spec deliberately leaves grooming sessions undefined — they're outside the dispatch system. But the first grooming session will reveal what fields are awkward to set and what the workflow actually feels like. Build the dispatch system first, then let grooming emerge from use.

4. **Vault task system spec overlap:** The 2026-03-21 vault task system spec defines fields and auto-routing logic that this spec builds on. Need to verify which parts of that spec were actually implemented in jimbo-api before adding dispatch-specific fields. Avoid creating duplicate columns.

## Resolved (from spec review)

- **Telegram `getUpdates` conflict:** Resolved — approval via web-links in Telegram messages, not polling. OpenClaw owns the bot's message stream.
- **SSH rate limiting:** Resolved — ControlMaster for VPS→M2, combined SSH commands where possible.
- **Tailscale offline handling:** Resolved — connectivity check at step 0, single alert, flag in jimbo-api settings.
- **Cron race condition:** Resolved — lockfile via `fcntl.flock`.
- **Result parsing:** Resolved — JSON fallback to plaintext summary, missing file = failed.
- **`/tmp` cleanup:** Resolved — cleanup after result collection.
- **Batch deduplication:** Resolved — rejected items tracked with cooldown, excluded from next proposal.
- **GitHub integration scope:** Deferred to Phase 5 — vault-only for v1.
- **Security (`--dangerously-skip-permissions`):** Acknowledged — prompt-level guardrails for v1, git worktrees in Approach 3.
