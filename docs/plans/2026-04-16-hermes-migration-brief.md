# Hermes Migration Brief

> This document is a self-contained brief for producing a Hermes migration plan in a fresh LLM context. It captures everything known from the OpenClaw era, flags open questions, and defines what the plan must deliver.

## Background

Marvin has been running OpenClaw (Nous Research's AI agent platform) on a DigitalOcean VPS for ~3 months. The goal: a personal AI assistant ("Jimbo") that processes emails, manages a vault of notes/tasks, runs daily briefings, and acts as an always-on collaborator.

**What went wrong:** Over-engineered security model (reader/actor model split for untrusted text) stalled progress. Accumulated 60+ Python scripts in `workspace/` that replicate or work around platform features. The system never reached a state where it reliably helped Marvin day-to-day. Month of struggling.

**Decision:** Sunset OpenClaw. Start fresh with Hermes Agent (OpenClaw's MIT-licensed successor by Nous Research, v0.9.0, April 2026). Use the migration as a forcing function to simplify.

## Hermes Agent

- **Docs:** https://hermes-agent.nousresearch.com/docs
- **GitHub:** https://github.com/NousResearch/hermes-agent (91.5k stars, MIT)
- **Migration tool:** `hermes claw migrate` — imports settings, memories, skills, API keys from OpenClaw
- **Key features over OpenClaw:** 47 built-in tools, 6 terminal backends (Docker/SSH/Modal/Daytona/local/Singularity), 18+ messaging platforms, native subagent spawning, self-improving skills, SQLite FTS5 cross-session search, Honcho user modeling, voice mode, MCP integration, prompt caching
- **Security model:** Container isolation (Docker with capability dropping), dangerous command approval (manual/smart/off), credential filtering, SSRF protection, context file injection scanning. No reader/actor model split — container boundary is the security boundary.

## What Exists Today

### jimbo-api (KEEP — Marvin's code, mature)

Node/TS API on VPS. 95 endpoints across 20 route groups. Deployed via `git push`, systemd runs `dist/index.js`.

**Route groups (endpoint count):**

| Group | Endpoints | Purpose |
|-------|-----------|---------|
| Context | 11 | Priorities, interests, goals, sections, items — Jimbo's structured self-knowledge |
| Dispatch | 16 | Batch task proposal, approval, execution tracking, GitHub enrichment |
| Vault | 10 | Notes CRUD, task summary, stats, subtasks, batch updates, ingestion |
| Emails | 8 | Email report CRUD, triage decisions, gems, forwarding |
| Google Calendar | 4 | Calendar list, events, create event, conflict check |
| Google Mail | 4 | Profile, list messages, get message, send |
| Google Tasks | 6 | Lists, tasks, create, delete, AI refine, commit-to-vault |
| Workflows | 8 | Task records, metrics, runs, trigger, definitions |
| Briefing | 4 | Analysis records, latest, history, rating |
| Activity | 4 | Activity logging and stats |
| Costs | 3 | Cost entry logging and summaries |
| Experiments | 4 | Experiment run logging and stats |
| Fitness | 3 | Fitness record sync and summaries |
| Grooming | 5 | Vault note grooming proposals and audit |
| Health | 3 | System health checks, snapshots, trends |
| Pipeline | 4 | Pipeline run recording and retrieval |
| Settings | 3 | Key-value settings store |
| Snapshot | 1 | Composite view of priorities + goals + tasks |
| Summaries | 2 | Product metrics snapshots |
| Triage | 4 | Triage queue, decisions, stats, undo |
| Uploads | 1 | Presigned upload URLs |
| AI Models | 1 | Model tier config |
| Dispatch (public) | 3 | GitHub webhooks, approve/reject pages |

All `/api/*` routes require `X-API-Key` header. Auth key in env var `JIMBO_API_KEY`.

### jimbo-workspace (KEEP — Jimbo's space)

- **Repo:** https://github.com/marvinbarretto-labs/jimbo-workspace
- **Contains:** memory/, projects/sift/, JIMBO_DIARY.md, SIFT_DIARY.md
- **11 commits**, public, under Jimbo's GitHub account

### Blog (KEEP — needs activation)

- **Live at:** https://jimbo.pages.dev/
- **Framework:** Astro, deployed to Cloudflare Pages
- **Current content:** 5 posts from February 2026, then silence
- **Source currently in:** `openclaw/workspace/blog-src/` (needs to move to jimbo-workspace or its own repo)
- **Publish workflow:** Write .md with frontmatter → commit → push → Cloudflare auto-deploys
- **Blog-publisher skill exists** with full guidelines (first-person as Jimbo, one topic per post, etc.)

### hub (UNDEFINED — needs decision)

- **Repo:** /development/hub/ — dashboards dir, scripts dir, no public pages deployed yet
- **Admin UI also exists** at /development/site/src/admin-app/ — possibly should consolidate into hub
- **For now:** Not in scope for Hermes migration. Decision deferred.

### OpenClaw Workspace Scripts (SUNSET — audit below)

60+ Python scripts. The audit reveals four structural layers:

**Layer 1: Custom orchestration engine (REPLACE WITH HERMES) — ~20 files**

The `jimbo_runtime_*` cluster (13 files) is a hand-built orchestration engine: intake normalization, routing, execution, reporting, queue management, CLI shims. Hermes IS an orchestration engine with native subagent spawning, scheduling, and tool dispatch. This entire layer is the primary deletion candidate.

The dispatch system (7 files: `dispatch.py`, `dispatch-worker.py`, `dispatch_batch_memory.py`, `dispatch_intake.py`, `dispatch_reporting.py`, `dispatch_review.py`, `dispatch_transitions.py`, `dispatch_utils.py`) is a custom batch proposal/approval/execution pipeline. Hermes has native propose-and-approve patterns + subagent spawning.

**Layer 2: Workers with real domain logic (PORT AS HERMES SKILLS) — 6 files**

| Script | What it does |
|--------|-------------|
| `workers/email_triage.py` | Shortlists ~30 emails from full digest using cheap LLM |
| `workers/email_decision.py` | Scores email reports for relevance against priorities/interests |
| `workers/newsletter_reader.py` | Deep-reads shortlisted emails, extracts articles/links/events |
| `workers/vault_connector.py` | BM25+temporal-decay keyword match between queries and vault notes |
| `workers/vault_reader.py` | Fetches bookmark URLs, summarises via Flash, enriches vault notes |
| `workers/vault_roulette.py` | Surfaces random/decaying vault notes for review |

These contain the actual domain logic. Worth porting as Hermes skills (SKILL.md format is identical). The `workers/base_worker.py` and `workers/vault_utils.py` are shared infrastructure that Hermes replaces.

**Layer 3: Data fetchers (EVALUATE ONE BY ONE) — ~10 files**

| Script | What it does | Hermes replacement? |
|--------|-------------|---------------------|
| `gmail-helper.py` | Gmail API fetch, blacklist, writes email-digest.json | Maybe — Hermes has web/email tools, but jimbo-api already wraps Gmail |
| `calendar-helper.py` | Google Calendar API client | jimbo-api already has `/api/google-calendar/*` |
| `context-helper.py` | Fetches priorities/interests/goals from jimbo-api | Simple HTTP — Hermes can call jimbo-api directly |
| `health-helper.py` | Fetches system health from jimbo-api | Simple HTTP |
| `settings-helper.py` | Fetches settings from jimbo-api | Simple HTTP |
| `tasks-helper.py` | Google Tasks fetch, vault ingest, Gemini classify | jimbo-api has `/api/google-tasks/*` |
| `openrouter-usage.py` | OpenRouter credit/usage query | Keep as utility or port |
| `email-fetch-cron.py` | Cron wrapper for gmail-helper | Hermes native cron replaces |
| `briefing-prep.py` | Assembles briefing-input.json from multiple sources | Hermes orchestration replaces |

Most of these are thin wrappers that exist because OpenClaw couldn't call jimbo-api directly. Hermes can use HTTP tools natively.

**Layer 4: Standalone processing scripts (KEEP/PORT selectively) — ~10 files**

| Script | What it does |
|--------|-------------|
| `vault-triage.py` | Auto-classifies/archives stale vault inbox items |
| `prioritise-tasks.py` | Batch-scores vault tasks via Gemini Flash |
| `scoring_gate.py` | Pre-scoring filter thresholds |
| `decompose-epic.py` | Proposes sub-task breakdowns for analysis-pending vault tasks |
| `calendar-vault-linker.py` | Cross-references calendar events with vault |
| `alert.py` | Telegram message sender |
| `alert-call.py` | Twilio escalation call |
| `alert-check.py` | Pipeline health checker |
| `accountability-check.py` | End-of-day pipeline summary |
| `vault-orchestration-cron.py` | Cron wrapper for vault triage workflow |

**Likely dead code:**
- `activity-log.py` — superseded by `activity-helper.py`
- `cost-tracker.py` — overlaps with `experiment-tracker.py`
- `recommendations-helper.py` — no incoming references

### OpenClaw Skills (PORT selectively — 20 skills)

| Skill | Worth porting? |
|-------|---------------|
| daily-briefing | Rethink — was never reliable, may not be the right pattern |
| blog-publisher | Yes — format identical, workflow solid |
| email-scanner | Evaluate — may be replaced by Hermes native email tools |
| email-triage-worker | Yes — real domain logic |
| newsletter-reader-worker | Yes — real domain logic |
| vault-manager | Evaluate — may overlap with Hermes native tools |
| vault-grooming | Yes — domain-specific |
| calendar | Evaluate — jimbo-api handles calendar |
| calendar-briefing | Rethink — part of briefing system being redesigned |
| day-planner | Rethink |
| morning-summary | Rethink — part of briefing system |
| tasks-triage | Yes — domain logic |
| sift-digest | Evaluate |
| surprise-game | Fun — low priority port |
| accountability | Yes — valuable pattern |
| activity-log | Evaluate — may be replaced |
| cost-tracker | Evaluate — may be replaced |
| web-style-guide | Yes — blog design tokens |
| rss-feed | Evaluate |
| cron-smoke-test | Utility — low priority |

## Architecture Vision

### Core pattern: Event-driven with human-in-the-loop

Not scheduled briefings. A continuous Hermes thread throughout the day. Inbound signals (email, calendar changes, vault updates) flow through jimbo-api for classification/scoring, then route to Hermes main thread (decisions only) or subagents (autonomous work).

```
Inbound signals (Jimbo's Gmail, RSS, webhooks)
       |
   jimbo-api (classify, score, route)
       |
   +---+------------------------+
   |   Hermes main thread       |
   |   (high-signal only)       |
   |                            |
   |  Decisions, approvals,     |
   |  project accumulation      |
   +---+------------------------+
       |           |
   Subagents    Outputs
   (autonomous)  (blog posts, vault items,
                  calendar events, email drafts)
```

### Trust boundaries

| Scope | Autonomy level |
|-------|---------------|
| jimbo-workspace (memory, diary, experiments) | Full autonomy |
| Vault filing, tagging, archiving | Full autonomy |
| Blog post drafting | Full autonomy |
| Blog publishing | Propose-and-approve |
| Email sending | Propose-and-approve |
| jimbo-api code changes | Propose-and-approve |
| Outbound actions (any public-facing) | Propose-and-approve |
| Deleting data, modifying approval rules | Forbidden without explicit request |

### Security model (simplified from OpenClaw era)

- Container isolation (Hermes Docker backend) is the security boundary
- jimbo-api preprocesses untrusted input (emails, RSS) before it reaches Hermes — natural reader/actor split without model-level enforcement
- Dangerous command approval ON for local/SSH backends
- No ClawHub skills — custom SKILL.md only (carried forward)

### Repo structure

| Repo | Owner | Purpose |
|------|-------|---------|
| jimbo-api | Marvin | Data layer, API, classification, scoring. Jimbo proposes changes via PR. |
| jimbo-workspace | Jimbo | Memory, diary, blog, experiments. Hermes reads/writes directly. |
| hub | Marvin | Hermes config repo — skills, SOUL.md, AGENTS.md, hermes.yaml, Groom CLI. Version-controlled source of truth for `~/.hermes/` config. Synced via symlinks or git-tracking. |
| site | Marvin | Personal site + Jimbo admin dashboard at `/app/jimbo/dashboard/`. Astro on Cloudflare Pages, proxies to jimbo-api. Already deployed and working. |
| openclaw | Archive | Reference only. No active development. |

## Decisions Made

### Infrastructure
- **Hermes runs on VPS (Docker) for always-on gateway + M2 for local dev.** VPS keeps jimbo-api + Hermes gateway colocated, always-on for Telegram/cron/webhooks. M2 for testing, skill development, experimentation. Config pushed via hub repo.
- **Telegram is the main thread.** Twilio and other platforms to be added later.
- **Model providers: mix.** OpenRouter, Nous Portal, Anthropic — whatever fits the task. No single-provider lock-in.
- **Budget: small initially.** System must prove value before scaling spend. Start lean, expand based on demonstrated utility.

### Accounts & Auth
- **Jimbo has email, GitHub, all tokens.** Blog (jimbo.pages.dev) connected to jimbo-workspace repo. All auth is in place.

### Design
- **Kill the daily briefing.** Replace with a ~30-minute status pulse: what's coming in, what's being worked on, what needs attention. Lightweight, continuous, not a morning report.
- **Mailing list seeding: deferred.** Not in scope for initial setup.
- **Hub stays as Hermes config repo.** Admin dashboard stays in site repo (already deployed and working). No consolidation needed.

### Capabilities & Success

Marvin's goal is not a rigid feature spec. It's exploration — discovering what an always-on AI assistant can actually do. The system should surprise and delight. Many hours invested; the return should be daily utility and genuine satisfaction.

**Success criteria:** "I use it every day and it makes me happy."

This is deliberately open-ended. The plan should deliver a solid foundation (Hermes + jimbo-api + Telegram + blog pipeline) and then create space for experimentation. Not a locked-down production system — a playground that works.

**Concrete day-one capabilities to aim for (not exhaustive, discovery-oriented):**

1. **Live Telegram thread** — Jimbo is always reachable. Can answer questions about schedule, vault, priorities using jimbo-api context. Conversational, not robotic.
2. **Email processing** — Jimbo's Gmail receives email, jimbo-api classifies/scores, high-signal items surface in Telegram with proposed actions. Low-signal items filed silently.
3. **30-minute status pulse** — Hermes cron pushes a lightweight update to Telegram: what came in, what subagents are working on, anything needing attention.
4. **Blog pipeline working** — Jimbo can draft posts, commit to jimbo-workspace, Cloudflare auto-deploys. Marvin approves before publish.

**30-day aspiration:** Jimbo feels like a collaborator, not a tool. Marvin checks Telegram naturally throughout the day. Email triage is mostly handled. Blog has new posts. The vault is actively maintained. Marvin has discovered at least one capability he didn't plan for.

## Remaining Open Questions

1. **VPS resources** — is the current droplet sized for running Hermes Docker alongside jimbo-api? May need to check RAM/CPU.
2. **Twilio timeline** — when to add voice/SMS as a second channel? After Telegram is stable?
3. **Hermes model defaults** — which model for the main thread vs subagents vs cron jobs? (Can be decided during setup.)
4. **OpenClaw shutdown** — when to actually stop the OpenClaw process on VPS? After Hermes is proven, or immediately?

## What the Plan Must Deliver

1. **Hermes installation and configuration** — step-by-step, including Docker setup, messaging gateway config, model provider setup
2. **Migration checklist** — what to run `hermes claw migrate` on, what to port manually, what to delete
3. **jimbo-api integration** — how Hermes calls jimbo-api, which endpoints matter for day-one capabilities, any new endpoints needed
4. **Blog pipeline** — move blog source to jimbo-workspace, connect to Cloudflare Pages, test publish flow
5. **Skills to create** — SKILL.md files for day-one capabilities, ported from OpenClaw where applicable
6. **Cron jobs** — what runs on schedule, using Hermes native cron
7. **Trust boundary config** — Hermes command approval settings, what's auto-approved vs needs confirmation
8. **Testing criteria** — for each day-one capability, how to verify it works
9. **Rollback plan** — if Hermes doesn't work, how to get back to OpenClaw (answer: openclaw repo is archived, VPS config unchanged until Hermes is proven)
