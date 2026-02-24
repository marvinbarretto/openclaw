# Jimbo Capability Matrix

Quick reference for what Jimbo can and can't do. Updated as capabilities change.

## Communication

| Capability | Status | Notes |
|---|---|---|
| Telegram chat | WORKING | Via `@fourfold_openclaw_bot` |
| Morning briefing | READY | Needs OpenClaw cron config (ADR-010) |
| Email digest summary | WORKING | Via `sift-digest` skill |

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
| Fetch email via Gmail API | WORKING | `gmail-helper.py` in sandbox. No laptop dependency. (ADR-022) |
| Read email digest | WORKING | JSON written directly in sandbox by gmail-helper.py |
| Blacklist filtering | WORKING | Rules-based sender/subject blacklist in gmail-helper.py |
| Deep newsletter reading | WORKING | Full body (5000 chars), links extracted. Jimbo applies judgment. |
| Send/delete/modify email | BLOCKED | By design — gmail.readonly scope only (ADR-002) |
| LLM email classification | REMOVED | Redundant — Jimbo reads raw emails directly (ADR-022) |
| Old Sift pipeline (laptop) | DEPRECATED | mbsync + Ollama + sift-push.sh no longer needed |

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
| Daily ingest from Tasks API | NOT STARTED | ADR-023 Phase C — `tasks-helper.py` on VPS |
| Jimbo vault skill | NOT STARTED | ADR-023 Phase C — vault queries + triage via Telegram |
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

## Autonomy

| Capability | Status | Notes |
|---|---|---|
| Self-publish blog posts | WORKING | Write `.md` in `blog-src/src/content/posts/`, commit + push → Cloudflare auto-builds (ADR-027) |
| Update own diary | WORKING | JIMBO_DIARY.md in workspace |
| Automated daily pipeline | NOT STARTED | Laptop launchd + VPS cron (ADR-010) |
| Heartbeat / self-monitoring | WORKING | HEARTBEAT.md with monitoring + active daytime tasks (ADR-028) |
| Proactive day planning | READY | Suggests activities for free gaps, morning negotiation, heartbeat nudges (ADR-019) |
| Install packages (npm/pip) | WORKING | Fixed 2026-02-20 (ADR-016). npm install works; pip needs venv in /workspace |

## VPS Model

| Model | Status | Notes |
|---|---|---|
| `stepfun/step-3.5-flash:free` | RETIRED | Can't follow curation instructions (ADR-005) |
| `google/gemini-2.5-flash` | WORKING | Daily driver (~$0.78/month). Direct Google AI API. See ADR-015 for setup. |
| `anthropic/claude-haiku-4.5` | AVAILABLE | Fallback if Gemini quality disappoints (~$2.49/month) |

## MCP Servers

| Server | Status | Notes |
|---|---|---|
| Native MCP support | BLOCKED | Not available in OpenClaw v2026.2.12. PR #21530 pending. Revisit on upgrade. (ADR-017) |
| Community MCP plugins | REJECTED | Violates ADR-008 (no community plugins, supply chain risk) |

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

*Last updated: 2026-02-24*
*Active heartbeat + cost tracking (ADR-028): 2026-02-24*
