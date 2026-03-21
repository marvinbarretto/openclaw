# Design Prompt: Vault Task Management System

**Date:** 2026-03-21
**Context:** Session 11 briefing review. Marvin's verdict: "not landing yet." The briefing is structurally competent but purposeless — it narrates static data instead of reporting on shared work. The next step on the maturity ladder is transforming the vault from a 1,633-item graveyard into a living shared task system between Marvin and Jimbo.

---

## Your mission

Design a comprehensive vault task management system for Jimbo (an AI assistant running on OpenClaw, self-hosted on a DigitalOcean VPS, accessible via Telegram). This is an architecture and skill design task — read the context below, then produce a design spec with the same depth and rigour as the autonomous mind spec (`docs/superpowers/specs/2026-03-17-autonomous-mind-design.md`).

## What exists today

### The vault
- ~1,633 active items in `data/vault/` (133 on VPS at `/workspace/vault/notes/`)
- Markdown files with YAML frontmatter
- Current schema:
  ```yaml
  id: note_9be2fe66
  source: google-tasks
  type: task          # task, bookmark, recipe, idea, reference, etc.
  status: active      # only "active" or moved to archive/
  tags: ["software", "project"]
  created: 2026-03-19
  priority: 10        # 1-10, scored by prioritise-tasks.py (Gemini Flash)
  priority_reason: "Aligns with LocalShout..."
  actionability: needs-breakdown  # clear, vague, needs-breakdown
  scored: 2026-03-21
  ```
- **Missing fields:** owner, due date, subtasks, blocked-by, source-signal, last-nudged, completed-at
- **Velocity:** 0. Zero tasks completed in 30 days. No mechanism to close tasks.
- Scored daily at 04:30 by `prioritise-tasks.py` (Gemini Flash batch scorer against priorities/goals)

### Existing vault tools (Phase 1 autonomous mind)
- `vault_connector.py` — BM25 keyword search across vault. WORKING.
- `vault_roulette.py` — surfaces dormant notes >30 days. Returns "no_candidates" every time (threshold issue?).
- `vault_reader.py` — fetches and summarises bookmark URLs. BROKEN (401 Unauthorized, 3 consecutive days).
- `insights_store.py` — BM25-lite scoring, insight accumulation. Deployed with ADR-045.

### Jimbo's capabilities (OpenClaw platform)
- **Telegram:** Receives and responds to messages. Can send proactively.
- **Sandbox:** Docker container, Python 3.11 stdlib only, `/workspace` writable.
- **memory-core:** FTS5 + vector search. Can persist facts across sessions.
- **Workspace files:** Can create/modify/delete markdown files in vault.
- **Activity logging:** Already logs 18+ activities/day to jimbo-api.
- **jimbo-api:** Hono/Node API on VPS. Endpoints for activity, costs, context, vault stats, settings, experiments, email reports.
- **Skills:** SKILL.md prompt files loaded at session start. Model reads and follows them.
- **Cron:** Scheduled jobs (main-session heartbeat or isolated fresh sessions).
- **Calendar:** Read/write via Google Calendar API.
- **Models:** Sonnet during briefing windows (06:45-07:30, 14:45-15:30). Kimi K2 between briefings.

### What Marvin wants (his words)
- "I want to get to a stage where Jimbo's primary job is to be task manager"
- "He can delegate out tasks for subagents to do independently"
- "We need the vault to be the source of truth"
- "Things need to be going in there every day, from my todos, from my emails, from our conversations"
- "I want to be in a position to say 'how are we getting on?' → '6 done today, 3 new ones. 2 decisions on me. No blockers.'"
- "Tasks in the vault might need subtasks to complete"
- Wants to leverage Opus 1M context + Claude Code features (loop, Cowork)

### The Airbnb nagging problem (session 10-11)
Session 10: 10 identical Airbnb reminders in one day. Session 11: duplicate messages at same timestamp. Root cause: no shared state. Jimbo doesn't know when something's been handled. Rate-limiting is a band-aid; task state is the fix.

### Maturity ladder
1. ~~Plumbing works~~ — done
2. ~~Heartbeat fires, tools get called~~ — done
3. **Vault as shared task system** — DESIGNING NOW
4. Source data quality
5. Useful outputs
6. Autonomous actions
7. Sub-agents spin off tasks

## Design requirements

### Task lifecycle
- **Create:** From email signals, calendar events, Telegram conversations, briefing review action items, Jimbo's own observations, Google Tasks sweep (already runs at 05:00)
- **Assign:** Owner field — Marvin, Jimbo, or unassigned. Conversational protocol ("I'll take this", "you do it", "who's on this?")
- **Track:** Status progression (new → in-progress → blocked → done). Blocked-by relationships.
- **Subtasks:** Some tasks need breakdown. "Fix whatever's wrong. Display version. Ship iOS and Android. Invite people." is 4 subtasks. Does the vault schema support parent/child? Or do we flatten with tags?
- **Close:** Via Telegram conversation ("done", "handled"), via Jimbo completing work, via expiry
- **Nudge:** Rate-limited, state-aware. If a task is in-progress or was nudged <4 hours ago, don't nudge. If it's blocked, nudge about the blocker, not the task.

### Status dashboard
- "How are we getting on?" → structured summary: done today, new today, waiting on Marvin, waiting on Jimbo, blocked, velocity trend
- Should work mid-conversation via Telegram
- Should inform the morning/afternoon briefing (briefing becomes a status report, not a news broadcast)

### Integration with existing systems
- **Briefing:** Vault task section becomes a status report, not a static list of priority-9 items
- **Email pipeline:** When gems have actionable items, Jimbo should create vault tasks (not just mention them)
- **Calendar:** Time-sensitive tasks should have due dates; overdue tasks surface in briefings
- **Heartbeat:** Task checking replaces blind nagging
- **Activity log:** Task completions logged
- **Accountability report:** Velocity metrics instead of "surprise game played: no"

### Sub-agent delegation (future but design for it)
- Jimbo as coordinator, not sole executor
- Tasks with `owner: jimbo` that are `actionability: clear` could be dispatched to sub-agents
- Think about: what does a sub-agent need? Task description, context, tools, success criteria, reporting back
- Opus 1M context + Claude Code loop/Cowork could power this layer

### The 1,633-item elephant
- Most existing items are stale Google Tasks/Keep imports
- Need a strategy: bulk archive? Triage sprint? Gradual decay?
- New tasks created by the system should feel qualitatively different from the old backlog

## Constraints

- **Python 3.11 stdlib only** in sandbox (no pip)
- **Skills are prompt files** (SKILL.md), not executable code. Workers are Python scripts.
- **Kimi K2 is the daily driver** between briefings. Any conversational protocol must work with cheaper models, or we need to rethink model allocation.
- **No breaking changes** to existing pipeline. The briefing-prep.py → briefing-input.json → daily-briefing skill chain should continue working.
- **Vault files are the source of truth.** Not a database. Frontmatter YAML + markdown body. Atomic writes (tmp + rename).
- **jimbo-api can be extended** — new endpoints are fine (Hono/Node, deployed via rsync + systemd restart).

## Reference files to read

Before designing, read these files in the repo:

1. `docs/reviews/HISTORY.md` — full arc of 11 briefing review sessions, open issues, patterns
2. `docs/reviews/2026-03-21-session11.md` — today's session, Marvin's exact words
3. `docs/reviews/2026-03-21.md` — session 10 (the missing feedback loop)
4. `docs/superpowers/specs/2026-03-17-autonomous-mind-design.md` — Phase 1 module design (vault-reader, connector, roulette, insights). Follow this spec's structure and depth.
5. `workspace/HEARTBEAT.md` — current heartbeat tasks
6. `workspace/SOUL.md` — personality, boundaries, working style
7. `skills/daily-briefing/SKILL.md` — current briefing structure
8. `CAPABILITIES.md` — what works and what's broken
9. `CLAUDE.md` — full project context, architecture, conventions
10. Sample vault tasks on VPS: `ssh jimbo 'cat /home/openclaw/.openclaw/workspace/vault/notes/fix-whatevers-wrong-display-version-ship-ios-and-android--note_9be2fe6.md'`

## Deliverable

A design spec at `docs/superpowers/specs/2026-03-21-vault-task-system-design.md` covering:

1. **Vault schema changes** — new/modified frontmatter fields, subtask representation, migration strategy for existing items
2. **Task lifecycle** — state machine, transitions, who/what triggers each
3. **Conversational protocol** — how Marvin and Jimbo interact about tasks via Telegram (create, assign, update, close, query)
4. **New workers/scripts** — what needs to be built (vault_task_manager.py? task_status.py?), following the module contract from the autonomous mind spec
5. **Skill updates** — changes to daily-briefing, HEARTBEAT.md, new task-manager skill
6. **jimbo-api extensions** — new endpoints for task operations and status dashboard
7. **Nudge protocol** — rate-limiting, state-awareness, de-duplication
8. **Sub-agent delegation design** — how tasks get dispatched, monitored, completed (even if implementation is Phase 2)
9. **Opus 1M + Claude Code integration** — how loop, Cowork, and the Max plan Opus fits into the architecture
10. **The 1,633-item strategy** — what to do with the existing backlog
11. **Model considerations** — what works with Kimi K2 vs needs Sonnet vs needs Opus
12. **Implementation phases** — what to build first, what can wait

Don't over-engineer. The vault is markdown files. The tools are Python scripts. The interface is Telegram. Keep it simple, keep it working, keep it auditable.
