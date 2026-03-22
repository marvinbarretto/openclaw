# Jimbo Capability Catalogue

> **Live status:** `GET /api/health` — this doc describes capabilities, not their current state.
> Status claims go stale within hours. The health endpoint is the source of truth.

## Communication

| Capability | Check | Notes |
|---|---|---|
| Telegram chat | manual | Via `@fourfold_openclaw_bot` |
| Morning briefing | `/api/health → pipeline.morning` | Cron pipeline at 06:15 → Jimbo delivers at 07:00. `briefing-prep.py` orchestrates. (ADR-042) |
| Afternoon briefing | `/api/health → pipeline.afternoon` | Cron pipeline at 14:15 → Jimbo delivers at ~15:00. Controllable via `afternoon_briefing_enabled` setting. (ADR-040) |
| Opus analysis layer | `/api/health → files.briefing_analysis` | Mac-side `claude -p` via launchd. POSTs to `/api/briefing/analysis`. (ADR-042) |
| Email digest summary | `/api/health → pipeline` | Via `daily-briefing` skill (reads `briefing-input.json` + optional `briefing-analysis.json`) |

## Context

| Capability | Check | Notes |
|---|---|---|
| Context API (read/write) | manual | jimbo-api `/api/context/*`. SQLite-backed. (ADR-033) |
| Structured context fields | manual | Items have `status`, `category`, `timeframe`, `expires_at` fields. (ADR-041) |
| Context editor UI | manual | `/app/jimbo/context` on site. CRUD for Priorities, Interests, Goals. |
| Context helper script | manual | `context-helper.py` in sandbox. Fetches from API, formats for context window. |
| Expiring items endpoint | manual | `GET /api/context/items/expiring?days=N` |
| Priority conflict detection | manual | Briefing skill checks: too many active, expiring, stale priorities. (ADR-041) |
| Telegram notification on edit | manual | jimbo-api sends Telegram notification when context updated. Debounced. |
| File fallback | manual | `workspace-push.sh` pushes TASTE.md, PREFERENCES.md, PATTERNS.md as backup. |

## Code & Files

| Capability | Check | Notes |
|---|---|---|
| Read/write workspace files | manual | `/workspace` in sandbox |
| Git commit & push (jimbo-workspace) | manual | (ADR-011) |
| Cloudflare Pages blog | `/api/health → activity.blog_recent` | Astro from `blog-src/` on `gh-pages` branch → `jimbo.pages.dev`. (ADR-027) |
| Read Marvin's repos (GitHub) | n/a | Token exists but disabled (ADR-006) |
| npm / Node build tools | manual | Astro, webpack, npm install. Node 18 in sandbox. (ADR-016) |
| Python scripts | manual | Python 3.11 in sandbox, stdlib only |

## Calendar

| Capability | Check | Notes |
|---|---|---|
| Read calendars | `/api/health → calendar` | Via `calendar-helper.py` in sandbox. Reads Jimbo's + shared calendars. |
| Create events | manual | Primary calendar or "Jimbo Suggestions" calendar, invites Marvin |
| Proactive day planning | manual | Morning negotiation + heartbeat nudges via day-planner skill (ADR-019) |
| Modify/delete Marvin's events | n/a | Blocked by design — no update/delete commands exist |
| Scheduling conflict check | manual | FreeBusy API across all visible calendars |

## Email

| Capability | Check | Notes |
|---|---|---|
| Fetch email via Gmail API | `/api/health → email.last_check` | `gmail-helper.py` in sandbox. Triggered by `briefing-prep.py`. (ADR-022, ADR-042) |
| Blacklist filtering | manual | Rules-based sender/subject blacklist in gmail-helper.py |
| Deep newsletter reading | `/api/health → pipeline.latest_input.reader` | Flash triage → Haiku deep-read → gems. (ADR-029, ADR-042) |
| Email insight scoring | `/api/health → email.insight_quality` | `email_decision.py` scores relevance + generates insights. |
| Briefing prep pipeline | `/api/health → pipeline` | `briefing-prep.py` — cron orchestrator. Assembles `briefing-input.json`. (ADR-042) |
| Send/delete/modify email | n/a | Blocked by design — gmail.readonly scope only (ADR-002) |
| Hourly email fetch (legacy) | n/a | Replaced by briefing-prep.py fetch step. (ADR-042) |
| Sift pipeline (legacy) | n/a | Replaced by briefing-prep.py + daily-briefing skill. (ADR-042) |

## Notes Vault

| Capability | Check | Notes |
|---|---|---|
| Vault stats | `/api/health → vault` | Active/done counts, velocity, priority buckets |
| vault_reader | `/api/health → tools.vault_reader` | Reads bookmarks and notes from vault |
| vault_roulette | `/api/health → tools.vault_roulette` | Surfaces dormant notes for rediscovery |
| vault_connector | `/api/health → tools.vault_connector` | BM25 search for cross-references between signals and vault |
| Task prioritisation | manual | `prioritise-tasks.py` — Gemini Flash batch-scores. Cron at 04:30 UTC. (ADR-034) |
| Daily ingest from Tasks API | manual | `tasks-helper.py` at 05:00 UTC. Sweeps My Tasks → vault inbox. |
| Tasks triage session | manual | `tasks-triage` skill — interactive Telegram triage. (ADR-038) |
| Mobile triage UI | manual | `/app/jimbo/notes-triage` on site. jimbo-api serves manifest. |
| Google Tasks dump | manual | `tasks-dump.py` via Tasks API |
| Keep ingest | manual | `ingest-keep.py` — Google Takeout JSON → vault inbox |
| LLM batch classification | manual | `process-inbox.py` — Haiku classifies inbox → notes/needs-context/archive |

## Recommendations

| Capability | Check | Notes |
|---|---|---|
| Recommendations store | manual | SQLite via `recommendations-helper.py` (ADR-025) |
| Recommendation logging | manual | Briefing logs finds with scores + urgency |
| Recommendation expiry | manual | Briefing auto-expires past-due time-sensitive items |
| Recommendation review queue | n/a | Not started — ADR-024 Phase 3 |

## Cost & Activity Tracking

| Capability | Check | Notes |
|---|---|---|
| Cost tracking | `/api/health → costs` | `cost-tracker.py` — tokens + estimated USD per API call. (ADR-028) |
| Activity logging | `/api/health → activity` | `activity-log.py` — task type, description, outcome, satisfaction. (ADR-028) |
| Budget monitoring | `/api/health → costs.budget_pct` | Monthly budget with alert threshold |
| Dashboard (site) | manual | `/app/jimbo/` on site — costs, activity, emails, vault, status |
| Experiment tracking | `/api/health → experiments` | `experiment-tracker.py` — worker runs, config hashes, ratings. (ADR-029) |

## Autonomy

| Capability | Check | Notes |
|---|---|---|
| Self-publish blog posts | `/api/health → activity.blog_recent` | Astro blog at `jimbo.pages.dev`. (ADR-027) |
| Update own diary | manual | JIMBO_DIARY.md in workspace |
| Automated briefing pipeline | `/api/health → pipeline` | VPS cron → briefing-prep.py. (ADR-042) |
| Heartbeat / self-monitoring | `/api/health → activity` | HEARTBEAT.md tasks, nudges, email check-ins. (ADR-028) |
| Proactive day planning | manual | Day-planner skill for free gap suggestions. (ADR-019) |

## VPS Model

| Capability | Check | Notes |
|---|---|---|
| Current active model | `/api/health → model` | Read from openclaw.json `agents.defaults.model.primary` |
| Model switching | manual | `model-swap.sh` / `model-swap-local.sh`. Cron entries exist but may be disabled. |
| Opus analysis (Mac) | `/api/health → files.briefing_analysis` | `opus-briefing.sh` via launchd. Free with Max plan. |

## Native Features (v2026.3.1)

| Capability | Check | Notes |
|---|---|---|
| Native cron | manual | Morning briefing at 07:00 London. `openclaw cron`. (ADR-039) |
| Sub-agents | manual | `maxConcurrent: 8`. (ADR-039) |
| Memory (memory-core) | manual | FTS5 + vector search. Auto-loaded. (ADR-039) |
| OpenClaw health | manual | `openclaw health` — channel status, agents, sessions. (ADR-039) |
| Secrets management | manual | `openclaw secrets audit/configure/reload`. (ADR-039) |
| Plugins | manual | 5/38 loaded: device-pair, memory-core, phone-control, talk-voice, telegram. |

## MCP Servers

| Capability | Check | Notes |
|---|---|---|
| Native MCP support | n/a | Not available in v2026.3.1. (ADR-017) |
| Community MCP plugins | n/a | Rejected — supply chain risk (ADR-008) |

## Alerting & Monitoring

| Capability | Check | Notes |
|---|---|---|
| System health | `/api/health` | Comprehensive health endpoint with auto-snapshots. History at `/api/health/history`. |
| Telegram failure alerts | manual | `alert.py` via Bot API. Workers + cron wrappers. (ADR-030) |
| Digest volume check | manual | `alert-check.py digest` — email count + delta. |
| Briefing run check | manual | `alert-check.py briefing` — queries experiment tracker. Time-aware. (ADR-040) |
| Positive heartbeat | manual | Combined hourly status. Silence = broken checker. |
| OpenRouter usage | manual | `alert-check.py credits` / `openrouter-usage.py`. (ADR-031) |
| Gateway health check | manual | `alert-check.py openclaw` — TCP probe. (ADR-039) |
| Current model report | `/api/health → model` | Also via `alert-check.py model`. (ADR-039) |
| Daily accountability | manual | `accountability-check.py` at 20:00 UTC. 6 dimensions. (ADR-039) |
| Token expiry | `/api/health → tokens` | Warns when tokens expire within 30 days |
| Duplicate detection | `/api/health → duplicates` | Detects messages sent 3+ times in a day |
| Phone call escalation | manual | `alert-call.py` — Twilio voice for critical failures. 60-min cooldown. (ADR-043) |

## Security Boundaries

| Boundary | Status | Notes |
|---|---|---|
| Zone 1: own workspace | ENFORCED | Full read/write |
| Zone 2: Marvin's repos | DISABLED | Re-enable only with capable model |
| Zone 3: production/cloud/DNS | BLOCKED | No credentials on VPS |
| Prompt injection mitigation | ENFORCED | Reader/Actor split (ADR-003) |

## Token Expiry

> Also available live: `/api/health → tokens.warnings`

| Token | Expires | Purpose |
|---|---|---|
| `jimbo-vps` (fine-grained PAT) | 2026-05-18 | Read+write jimbo-workspace |
| `openclaw-readonly` (fine-grained PAT) | ~2026-04-17 | Read-only Marvin's repos (currently disabled) |
| Google OAuth refresh token | Non-expiring* | Calendar + Gmail read-only API access (* if app is published; 7 days if in testing mode) |
| Twilio Account SID + Auth Token | Non-expiring | Voice API for critical failure phone calls (ADR-043) |

---

*Converted to capability catalogue: 2026-03-22 (session 12)*
*Status claims removed — use `GET /api/health` for live status*
