# Jimbo Capability Matrix

Quick reference for what Jimbo can and can't do. Updated as capabilities change.

## Communication

| Capability | Status | Notes |
|---|---|---|
| Telegram chat | WORKING | Via `@fourfold_openclaw_bot` |
| Morning briefing | WORKING | Cron pipeline at 06:15 → Jimbo delivers at 07:00. `briefing-prep.py` orchestrates workers. (ADR-042) |
| Afternoon briefing | WORKING | Cron pipeline at 14:15 → Jimbo delivers at ~15:00. Same pipeline, lighter format. Controllable via `afternoon_briefing_enabled` setting. (ADR-040, ADR-042) |
| Opus analysis layer | WORKING | Mac-side `claude -p` (Opus via Max plan) analyses briefing data. Optional — Jimbo self-composes if unavailable. (ADR-042) |
| Email digest summary | WORKING | Via `daily-briefing` skill (reads `briefing-input.json` + optional `briefing-analysis.json`) |

## Context

| Capability | Status | Notes |
|---|---|---|
| Context API (read/write) | WORKING | jimbo-api serves context data via `/api/context/*`. SQLite-backed. (ADR-033) |
| Structured context fields | WORKING | Context items have optional `status`, `category`, `timeframe`, `expires_at` fields. Used by priorities and goals. (ADR-041) |
| Context editor UI | WORKING | `/app/jimbo/context` on personal site. CRUD for Priorities, Interests, Goals. Structured fields (dropdowns, date pickers) for priorities/goals items. |
| Context helper script | WORKING | `context-helper.py` in sandbox. Fetches from API, formats for Jimbo's context window. Renders structured metadata inline. |
| Expiring items endpoint | WORKING | `GET /api/context/items/expiring?days=N` — items expiring within N days. |
| Priority conflict detection | WORKING | Briefing skill checks: too many active priorities, expiring items, stale priorities. Thresholds from settings API. (ADR-041) |
| Telegram notification on edit | WORKING | jimbo-api sends Telegram notification when context is updated. Debounced. |
| File fallback | BACKUP | `workspace-push.sh` still pushes context/ as backup. Files in `/workspace/context/`. TASTE.md, PREFERENCES.md, PATTERNS.md remain markdown-only. |

## Code & Files

| Capability | Status | Notes |
|---|---|---|
| Read/write workspace files | WORKING | `/workspace` in sandbox |
| Git commit & push (jimbo-workspace) | WORKING | Fixed 2026-02-18 (ADR-011) |
| Cloudflare Pages blog | WORKING | Astro-built from `blog-src/` on `gh-pages` branch, served via `jimbo.pages.dev`. Auto-generates index, tags, archive, RSS. (ADR-027) |
| Read Marvin's repos (GitHub) | DISABLED | Token exists but skill disabled for free model (ADR-006) |
| npm / Node build tools | WORKING | Fixed 2026-02-20 (ADR-016). Astro, webpack, npm install all work. Node 18. |
| Python scripts | WORKING | Python 3.11 in sandbox, stdlib only |

## Calendar

| Capability | Status | Notes |
|---|---|---|
| Read Jimbo's own calendar | READY | Via `calendar-helper.py` in sandbox. Needs setup first. |
| Read Marvin's shared calendars | READY | Marvin must share calendars with Jimbo's Google account |
| Create events (Jimbo's calendar) | READY | Primary calendar or suggestions calendar, invites Marvin |
| Suggestions calendar | READY | "Jimbo Suggestions" — proactive day planning events. Needs one-time setup. |
| Proactive day planning | READY | Morning negotiation + heartbeat nudges via day-planner skill (ADR-019) |
| Modify/delete Marvin's events | BLOCKED | By design — no update/delete commands exist |
| Check scheduling conflicts | READY | FreeBusy API across all visible calendars |
| Calendar in morning briefing | READY | daily-briefing skill includes today's schedule + day plan proposal |

## Email

| Capability | Status | Notes |
|---|---|---|
| Fetch email via Gmail API | WORKING | `gmail-helper.py` in sandbox. Triggered by `briefing-prep.py` before each briefing. No laptop dependency. (ADR-022, ADR-042) |
| Read email digest | WORKING | JSON written directly in sandbox by gmail-helper.py |
| Blacklist filtering | WORKING | Rules-based sender/subject blacklist in gmail-helper.py |
| Deep newsletter reading | WORKING | Two-pass pipeline: Flash triages → Haiku deep-reads. Cron-orchestrated via `briefing-prep.py`. (ADR-029, ADR-042) |
| Briefing prep pipeline | WORKING | `briefing-prep.py` — cron-driven orchestrator. Runs email fetch, triage, reader, calendar, vault tasks. Assembles `briefing-input.json`. Per-pipeline Telegram alerts. (ADR-042) |
| Opus briefing analysis | WORKING | `opus-briefing.sh` — Mac-side script. Pulls briefing-input.json, runs Opus via `claude -p`, pushes analysis back to VPS. Launchd-scheduled. (ADR-042) |
| Send/delete/modify email | BLOCKED | By design — gmail.readonly scope only (ADR-002) |
| Hourly email fetch | RETIRED | `email-fetch-cron.py` replaced by briefing-prep.py fetch step. (ADR-042) |
| Hourly status check | RETIRED | `alert-check.py status` replaced by per-pipeline alerts from briefing-prep.py. (ADR-042) |
| Sift-digest skill | RETIRED | Replaced by briefing-prep.py + daily-briefing skill. (ADR-042) |
| Old Sift pipeline (laptop) | RETIRED | mbsync + Ollama + sift-push.sh removed. launchd job unloaded. |

## Notes Vault

| Capability | Status | Notes |
|---|---|---|
| Google Tasks dump | WORKING | `tasks-dump.py` — fetches all tasks via Tasks API |
| Tasks ingest to vault | WORKING | `ingest-tasks.py` — tasks-dump.json → vault inbox markdown |
| Keep ingest to vault | WORKING | `ingest-keep.py` — Google Takeout JSON → vault inbox markdown |
| LLM batch classification | WORKING | `process-inbox.py` — Claude Haiku classifies inbox → notes/needs-context/archive |
| Vault browsing (Obsidian) | WORKING | Point Obsidian at `data/vault/`, frontmatter compatible |
| Classification patterns | WORKING | `context/PATTERNS.md` — learned from review sessions, improves classification |
| Mobile review queue | NOT STARTED | ADR-024 — needs personal website (Vercel/Cloudflare TBD) |
| Task prioritisation | WORKING | `prioritise-tasks.py` — Gemini Flash batch-scores active tasks against priorities + goals (from context API, file fallback). Writes `priority`, `actionability`, `scored` into frontmatter. Cron at 04:30 UTC. |
| Daily ingest from Tasks API | WORKING | `tasks-helper.py` runs at 05:00 UTC via cron. Sweeps My Tasks → vault inbox → Gemini Flash classification. |
| Tasks triage session | WORKING | `tasks-triage` skill — interactive Telegram session for ambiguous items. Announced in morning briefing. Calendar invite via `calendar-helper.py`. (ADR-038) |
| Triage pending output | WORKING | `tasks-triage-pending.json` written after classification with needs-context items for Jimbo to announce. |
| Tasks read-write scope | READY | `google-auth.py` updated with `tasks.readonly`. Upgrade to `tasks` for mark-complete. |

## Recommendations

| Capability | Status | Notes |
|---|---|---|
| Recommendations store | WORKING | SQLite-backed via `recommendations-helper.py` (ADR-025) |
| Recommendation logging (email) | WORKING | Sift-digest skill logs findings with scores + urgency |
| Recommendation expiry tracking | WORKING | Briefing auto-expires past-due time-sensitive items |
| Recommendation review queue | NOT STARTED | ADR-024 Phase 3 — mobile UI alongside vault review |

## Cost & Activity Tracking

| Capability | Status | Notes |
|---|---|---|
| Cost tracking | WORKING | `cost-tracker.py` — logs every API interaction with token counts + estimated USD (ADR-028) |
| Activity logging | WORKING | `activity-log.py` — logs every task with description, outcome, satisfaction scores (ADR-028) |
| Budget monitoring | WORKING | Monthly budget with alert threshold. `cost-tracker.py budget --check` |
| Dashboard (personal site) | WORKING | `/app/jimbo/` on `site.marvinbarretto.workers.dev` — costs, activity feed (ADR-028) |
| Dashboard data export | WORKING | JSON exports via heartbeat auto-commit, consumed by dashboard at build time |
| Experiment tracking | WORKING | `experiment-tracker.py` — logs worker runs, config hashes, conductor ratings. SQLite. (ADR-029) |

## Autonomy

| Capability | Status | Notes |
|---|---|---|
| Self-publish blog posts | WORKING | Write `.md` in `blog-src/src/content/posts/`, commit + push → Cloudflare auto-builds (ADR-027) |
| Update own diary | WORKING | JIMBO_DIARY.md in workspace |
| Automated briefing pipeline | WORKING | VPS root cron → briefing-prep.py at 06:15 + 14:15 UTC. Mac launchd → opus-briefing.sh. No manual dependency. (ADR-042) |
| Heartbeat / self-monitoring | WORKING | HEARTBEAT.md with monitoring + active daytime tasks (ADR-028) |
| Proactive day planning | READY | Suggests activities for free gaps, morning negotiation, heartbeat nudges (ADR-019) |
| Install packages (npm/pip) | WORKING | Fixed 2026-02-20 (ADR-016). npm install works; pip needs venv in /workspace |

## VPS Model

| Model | Status | Notes |
|---|---|---|
| `stepfun/step-3.5-flash:free` | RETIRED | Can't follow curation instructions (ADR-005) |
| `moonshotai/kimi-k2` | ACTIVE | Daily driver outside briefing windows. Cron auto-switches. |
| `anthropic/claude-sonnet-4.6` | ACTIVE | Briefing window model. Morning: 06:45-07:30, Afternoon: 14:45-15:30 UTC. (ADR-040) |
| Opus 4.6 (Mac, via Max plan) | ACTIVE | Briefing analysis layer. Runs via `claude -p` on Mac. Free with Max subscription. (ADR-042) |
| Automated model switching | WORKING | `model-swap-local.sh` on VPS. Cron: Sonnet at 06:45+14:45, Kimi at 07:30+15:30 UTC. (ADR-040) |
| Experiment tracking | WORKING | `experiment-tracker.py` — logs worker runs, config hashes, conductor ratings. (ADR-029) |

## Native Features (v2026.3.1)

| Feature | Status | Notes |
|---|---|---|
| Native cron | WORKING | Morning briefing at 07:00 London. Managed via `openclaw cron`. (ADR-039) |
| Sub-agents | WORKING | `maxConcurrent: 8`. Used by sift-digest for email triage + newsletter reading. (ADR-039) |
| Memory (memory-core) | WORKING | FTS5 + vector search. Auto-loaded. Wired into SOUL.md, daily-briefing, HEARTBEAT.md. (ADR-039) |
| Health endpoint | WORKING | `openclaw health` — shows channel status, agents, sessions. TCP probe from sandbox via alert-check.py. (ADR-039) |
| Secrets management | AVAILABLE | `openclaw secrets audit/configure/reload`. 1 plaintext key found. Not yet migrated. (ADR-039) |
| Plugins | WORKING | 5/38 loaded: device-pair, memory-core, phone-control, talk-voice, telegram. |

## MCP Servers

| Server | Status | Notes |
|---|---|---|
| Native MCP support | BLOCKED | Still not available in v2026.3.1. No CLI command, no config key. (ADR-017) |
| Community MCP plugins | REJECTED | Violates ADR-008 (no community plugins, supply chain risk) |

## Alerting & Monitoring

| Capability | Status | Notes |
|---|---|---|
| Telegram failure alerts | WORKING | `alert.py` sends via Bot API. Workers catch exceptions. Cron wrappers alert on exit code. (ADR-030) |
| Digest volume check | WORKING | `alert-check.py digest` — reports email count and new emails since last fetch. Hourly at :30. |
| Briefing run check | WORKING | `alert-check.py briefing` — queries experiment-tracker.db with `session` column. Reports morning + afternoon separately. Time-aware grace windows: morning before 08:00, afternoon before 16:00. (ADR-040) |
| Positive heartbeat | WORKING | All checks send combined status hourly. Silence = broken checker. |
| OpenRouter usage report | WORKING | `alert-check.py credits` — reports usage (not balance, as OpenRouter API returns stale limits). Hourly at :30. (ADR-031) |
| Gateway health check | WORKING | `alert-check.py openclaw` — TCP probe to gateway port from sandbox. Included in hourly status. (ADR-039) |
| Current model report | WORKING | `alert-check.py model` — reads openclaw.json, reports active model. Included in hourly status. (ADR-039) |
| Daily accountability | WORKING | `accountability-check.py` — checks 6 dimensions at 20:00 UTC, sends Telegram summary. (ADR-039) |
| Settings API | WORKING | jimbo-api serves `/api/settings/*`. Key-value store for config (e.g. email fetch interval). |
| Settings UI | WORKING | `/app/jimbo/settings` on personal site. Configurable email fetch interval. |
| OpenRouter usage checker | WORKING | `openrouter-usage.py` — balance + usage queries. Available to Jimbo in heartbeat + briefing. (ADR-031) |
| Model identification | WORKING | SOUL.md instructs Jimbo to tag first message with [Flash]/[Haiku]/etc. (ADR-031) |
| Docker/host-level alerts | COVERED | Gateway TCP probe from sandbox detects service crash. (ADR-039) |
| OpenClaw service crash | COVERED | `alert-check.py openclaw` detects gateway down. Hourly at :30. (ADR-039) |

## Security Boundaries

| Boundary | Status | Notes |
|---|---|---|
| Zone 1: own workspace | ENFORCED | Full read/write |
| Zone 2: Marvin's repos | DISABLED | Re-enable only with capable model |
| Zone 3: production/cloud/DNS | BLOCKED | No credentials on VPS |
| Prompt injection mitigation | ENFORCED | Reader/Actor split (ADR-003) |

## Token Expiry

| Token | Expires | Purpose |
|---|---|---|
| `jimbo-vps` (fine-grained PAT) | 2026-05-18 | Read+write jimbo-workspace |
| `openclaw-readonly` (fine-grained PAT) | ~2026-04-17 | Read-only Marvin's repos (currently disabled) |
| Google OAuth refresh token | Non-expiring* | Calendar + Gmail read-only API access (* if app is published; 7 days if in testing mode) |

---

*Last updated: 2026-03-06*
*Context structured fields (ADR-041): 2026-03-06*
*Briefing pipeline redesign (ADR-042): 2026-03-05*
*Twice-daily briefing (ADR-040): 2026-03-04*
*OpenClaw v2026.3.1 upgrade + native features (ADR-039): 2026-03-02*
*Tasks triage session (ADR-038): 2026-03-02*
*Vault task prioritisation (ADR-034): 2026-03-02*
*VPS vault source of truth (ADR-035): 2026-03-02*
*Haiku conductor model (ADR-036): 2026-03-02*
*Context API + editor (ADR-033): 2026-03-01*
