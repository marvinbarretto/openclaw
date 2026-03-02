# CLAUDE.md — Project Context for Claude Code

## What This Is

Configuration, documentation, and tooling repo for a personal OpenClaw AI assistant instance ("Jimbo") self-hosted on a DigitalOcean VPS. This repo does NOT contain the OpenClaw software itself — it contains our setup, decisions, scripts, and custom skills.

Jimbo is accessible via Telegram (`@fourfold_openclaw_bot`).

## Owner

Marvin Barretto. Projects: Spoons (pub check-in app, Angular/Firebase/Capacitor), LocalShout (community platform, Next.js), Pomodoro (productivity timer). Based in Watford/South Oxhey area, UK.

## Architecture

```
Laptop (MacBook Air 24GB)
  ├── This repo (openclaw/)
  ├── Ollama (qwen2.5:7b, qwen2.5-coder:14b)
  ├── google-auth.py — one-time OAuth for Calendar + Gmail + Tasks scopes
  └── Notes vault pipeline (ingest → process → review)

VPS (DigitalOcean $12/mo, London, 167.99.206.214)
  ├── OpenClaw v2026.2.12 (Node 22, systemd, openclaw user)
  ├── Docker sandbox (Python 3.11, Node 18, git, hardened)
  │     ├── /workspace — Jimbo's brain files + skills + blog-src (Astro) + email digest + recommendations.db
  │     ├── gmail-helper.py — fetches email via Gmail API, writes digest directly
  │     ├── calendar-helper.py — Calendar API client
  │     ├── recommendations-helper.py — SQLite CRUD for persistent recommendations store
  │     ├── experiment-tracker.py — SQLite run logging for worker experiments
  │     ├── alert.py — Telegram alert sender (stdlib only, Bot API)
  │     ├── alert-check.py — Pipeline health checker with positive heartbeat (digest, briefing, credits)
  │     ├── openrouter-usage.py — OpenRouter balance/usage checker (stdlib only)
  │     ├── prioritise-tasks.py — Gemini Flash batch scorer for vault tasks (priority, actionability)
  │     ├── workers/ — orchestrator workers (email_triage.py, newsletter_reader.py — call Flash/Haiku APIs directly)
  │     ├── tasks/ — task registry JSON configs (email-triage, newsletter-deep-read, briefing-synthesis, heartbeat)
  │     └── tests/ — worker test suite
  ├── jimbo-api (Hono/Node, port 3100, systemd, formerly notes-triage-api)
  │     ├── /home/openclaw/.openclaw/workspace/triage/ — manifest.json + decisions.json
  │     └── data/context.db — SQLite context store (ADR-033)
  └── Caddy (auto TLS, routes /api/triage/* + /api/context/* → jimbo-api)
```

Email pipeline: Gmail API runs IN the sandbox (no laptop dependency). Blacklist removes junk, then the orchestrator pipeline (Flash triage + Haiku deep-read) processes the digest before Jimbo synthesises the briefing.

SSH alias: `ssh jimbo` connects to VPS. SSH connection multiplexing is configured (`ControlMaster auto`) for `workspace-push.sh` reliability when running multiple rsync commands over the same connection.

**SSH rate-limiting (learned the hard way):** The VPS drops SSH connections after ~5 rapid connections. Individual `scp` calls per file will fail mid-push. Always use `rsync` to batch files into a single SSH connection. The `workspace-push.sh` script was rewritten to use rsync for everything (brain files, helpers, directories, vault notes) — never go back to per-file `scp`.

## Repo Structure

```
context/          Marvin's personal context files (interests, priorities, taste, goals, preferences)
decisions/        ADRs (001-036) — sandbox, email triage, prompt injection, models, plugins, automation, git deployment, feedback insights, model upgrades, Node build tools, Gemini direct, MCP, calendar, day planner, multi-model routing, architecture review, Gmail API migration, notes vault, notes review queue, recommendations store, Cloudflare Pages, Astro blog migration, active heartbeat + cost tracking, orchestrator-conductor pattern, failure alerting, cost visibility + model fallback, heartbeat rationalisation, context API, vault task prioritisation, VPS vault source of truth, Haiku conductor model
docs/             Design docs and implementation plans
scripts/          sift-classify.py, sift-sample.py, sift-push.sh, skills-push.sh, workspace-push.sh, model-swap.sh, sift-cron.sh, ingest-tasks.py, ingest-keep.py, process-inbox.py, tasks-dump.py, push-manifest.sh, pull-decisions.sh, apply-decisions.py
skills/           Custom OpenClaw skills (sift-digest, daily-briefing, calendar, day-planner, blog-publisher, rss-feed, web-style-guide, cost-tracker, activity-log)
workspace/        Jimbo's brain files (SOUL.md, HEARTBEAT.md) + blog source (blog-src/) + workers/ + tasks/ + tests/. Deploy via workspace-push.sh + rsync.
setup/            Configuration docs, architecture, workspace files guide
security/         VPS hardening checklist
hosting/          VPS comparison, networking
sandbox/          Custom Docker image Dockerfile
data/             Email digest output + feedback files + vault (all gitignored)
notes/            Brain dumps
```

## Key Files

- `.claude/commands/manual-review.md` — Claude Code custom command for interactive review of `needs-context` vault notes. Invoke with `/manual-review 10`. Presents notes, collects triage decisions (direct/context/archive/skip), updates frontmatter, moves files.
- `workspace/cost-tracker.py` — SQLite cost tracking for every API interaction. Logs provider, model, task type, tokens, estimated USD. Supports budgets + alerts. Stdlib only.
- `workspace/activity-log.py` — SQLite activity log for everything Jimbo does. Logs task type, description, outcome, satisfaction scores. Stdlib only.
- `workspace/recommendations-helper.py` — SQLite CRUD for persistent recommendations store. Jimbo logs finds from email/vault, tracks scores, urgency, expiry. Stdlib only, no OAuth.
- `workspace/gmail-helper.py` — Gmail API client for sandbox. Fetches email, applies blacklist, writes email-digest.json directly. No LLM classification.
- `workspace/tasks-helper.py` — Google Tasks API client for sandbox. Sweeps active tasks from "My Tasks" list, ingests into vault as markdown, classifies via Gemini Flash. Writes `tasks-triage-pending.json` for items routed to needs-context. Runs daily at 05:00 UTC via cron.
- `scripts/google-auth.py` — One-time OAuth flow for Calendar + Gmail + Tasks scopes (replaces calendar-auth.py)
- `scripts/sift-classify.py` — **LEGACY** Sift pipeline. Replaced by gmail-helper.py (ADR-022).
- `scripts/sift-cron.sh` — **LEGACY** Automated pipeline. No longer needed — gmail-helper.py runs in sandbox.
- `scripts/sift-push.sh` — **LEGACY** Rsyncs email-digest.json to VPS. No longer needed.
- `scripts/skills-push.sh` — Rsyncs custom skills to VPS workspace
- `scripts/workspace-push.sh` — Pushes brain files + context files to VPS workspace (one command for everything we maintain)
- `workspace/SOUL.md` — Jimbo's personality, behaviour rules, output rules
- `workspace/HEARTBEAT.md` — Periodic self-check tasks for Jimbo
- `context/*.md` — Marvin's interests, priorities, taste, goals, preferences
- `scripts/model-swap.sh` — SSH helper to switch LLM model on VPS
- `skills/sift-digest/SKILL.md` — Teaches Jimbo to present email digests
- `skills/daily-briefing/SKILL.md` — Teaches Jimbo to give morning briefings (includes tasks triage announcement, section 3.5)
- `skills/tasks-triage/SKILL.md` — Interactive Telegram triage session for ambiguous vault tasks (ADR-038)
- `sandbox/Dockerfile` — Custom sandbox image definition
- `setup/configuration.md` — VPS config state, API keys, **provider setup cheatsheet** (how to add new LLM providers/models to openclaw.json)
- `CAPABILITIES.md` — Quick-reference matrix of what Jimbo can/can't do, token expiry dates, current VPS model
- `context/INTERESTS.md` — What Marvin cares about (changes slowly)
- `context/PRIORITIES.md` — What matters right now (changes weekly)
- `context/TASTE.md` — What "good" looks like, what bores him
- `context/GOALS.md` — Longer-term ambitions (changes monthly)
- `context/PREFERENCES.md` — How to combine context files for decision-making
- `context/PATTERNS.md` — Learned patterns from note review sessions (living document)
- `scripts/tasks-dump.py` — Dumps all Google Tasks to JSON via Tasks API
- `scripts/ingest-tasks.py` — Converts tasks-dump.json → vault inbox markdown files
- `scripts/ingest-keep.py` — Converts Google Keep JSON export → vault inbox markdown files
- `scripts/process-inbox.py` — LLM batch classifier + manifest generator: inbox → notes/needs-context/archive, or `--manifest` mode for triage UI
- `scripts/push-manifest.sh` — Rsyncs triage manifest to VPS for the triage API
- `scripts/pull-decisions.sh` — Pulls triage decisions from VPS after mobile review
- `scripts/apply-decisions.py` — Applies triage decisions to move vault files to notes/archive/needs-context
- `notes/triage-deploy.md` — Full triage pipeline architecture, deployment, and operations guide
- `workspace/blog-src/` — Astro blog project. Posts in `src/content/posts/*.md`. Auto-generates index, tags, archive, RSS. Deployed via Cloudflare Pages (ADR-027).
- `decisions/027-astro-blog-migration.md` — ADR for blog migration from static HTML to Astro
- `decisions/028-active-heartbeat-cost-tracking.md` — ADR for active heartbeat, cost tracking, activity logging, and dashboard
- `decisions/029-orchestrator-conductor-pattern.md` — ADR for multi-model orchestrator-conductor pattern
- `decisions/030-failure-alerting.md` — ADR for Telegram failure alerting and positive heartbeat
- `decisions/031-cost-visibility-model-fallback.md` — ADR for cost visibility, credit alerts, model identification
- `decisions/032-heartbeat-rationalisation.md` — ADR for slimming heartbeat from ~20 to ~6 contextual tasks, moving scripts to cron
- `decisions/033-context-api.md` — ADR for context API, web editor, SQLite-backed context store
- `decisions/034-vault-task-prioritisation.md` — ADR for Gemini Flash batch-scoring vault tasks against priorities/goals
- `decisions/035-vps-vault-source-of-truth.md` — ADR for removing vault sync from laptop, VPS owns vault data
- `decisions/036-haiku-conductor-model.md` — ADR for switching conductor from Flash to Haiku 4.5
- `decisions/038-tasks-triage-session.md` — ADR for interactive tasks triage via Telegram (briefing announcement + triage skill)
- `docs/plans/2026-02-24-orchestrator-design.md` — Full orchestrator design doc
- `docs/plans/2026-02-24-orchestrator-plan.md` — Implementation plan
- `workspace/experiment-tracker.py` — SQLite experiment tracking for worker runs. Logs model, tokens, config hash per run. Stdlib only.
- `workspace/context-helper.py` — Context API client for sandbox. Fetches context (priorities, interests, goals) from jimbo-api, formats as readable text. Replaces file reads in skills. Stdlib only. (ADR-033)
- `workspace/alert.py` — Telegram alert sender. Sends via Bot API, exits silently if env vars missing. Stdlib only. (ADR-030)
- `workspace/alert-check.py` — Pipeline health checker. Subcommands: `digest` (reports email volume), `briefing` (checks experiment-tracker.db, time-aware), `credits` (reports OpenRouter usage), `model` (reports current VPS model from openclaw.json), `status` (combined). Positive heartbeat on success. Stdlib only. (ADR-030, ADR-031)
- `workspace/accountability-check.py` — Daily accountability checker. Queries activity-log.db + experiment-tracker.db for today. Checks: briefing ran, gems produced, surprise game played, vault tasks surfaced, activity count, cost. Sends Telegram summary. Runs at 20:00 UTC via cron. Stdlib only.
- `scripts/model-swap-local.sh` — VPS-local model swap (runs directly on VPS, unlike model-swap.sh which SSHes in). Used by cron for automated Haiku/Flash switching around the briefing window.
- `workspace/email-fetch-cron.py` — Interval-aware email fetch wrapper. Reads `email_fetch_interval_hours` from settings API, checks digest age, runs gmail-helper.py if stale. Injects `previous_count` for delta tracking. Stdlib only.
- `workspace/openrouter-usage.py` — OpenRouter API balance/usage checker. Subcommands: `balance`, `usage --days N`. Uses `OPENROUTER_API_KEY` env var. Stdlib only. (ADR-031)
- `workspace/prioritise-tasks.py` — Gemini Flash batch scorer for vault tasks. Reads PRIORITIES.md + GOALS.md, scores all active tasks with `priority` (1-10), `actionability` (clear/vague/needs-breakdown), writes back into frontmatter. Runs daily at 04:30 UTC. Subcommands: `score` (default), `stats`. Flags: `--dry-run`, `--force`, `--limit N`. Stdlib only.
- `workspace/workers/base_worker.py` — Base worker class with API clients for Google AI (Flash) + Anthropic (Haiku)
- `workspace/workers/email_triage.py` — Flash-powered email triage worker. Reads digest, scores/triages emails, outputs shortlist.
- `workspace/workers/newsletter_reader.py` — Haiku-powered newsletter deep-reader. Extracts gems, links, events from shortlisted emails.
- `workspace/tasks/*.json` — Task registry configs (email-triage, newsletter-deep-read, briefing-synthesis, heartbeat)

## Security Model (Critical — Read Before Changing)

### Three-Zone Access (ADR-001)
- **Zone 1 (Sandbox):** Jimbo has full read/write to `jimbo-workspace` repo only
- **Zone 2 (Read-only):** Fine-grained token for Marvin's real repos (currently disabled)
- **Zone 3 (Blocked):** Primary GitHub, cloud creds, DNS, production — NOTHING on VPS

### Prompt Injection (ADR-003)
- **Reader/Actor split:** Untrusted text (email, issues) goes to a Reader model with NO tool access
- Reader outputs fixed-schema JSON only; Actor never sees raw untrusted text
- Email fetched via Gmail API on VPS (read-only). No local processing — content stays on VPS.

### Email Security (ADR-002, updated ADR-022)
- Gmail API access is **read-only** (gmail.readonly scope). Agent cannot send, delete, or modify email.
- OAuth credentials on VPS (same token as Calendar — just wider scope)
- gmail-helper.py fetches email in sandbox, applies blacklist, writes digest locally
- HTML stripped, body truncated to 5000 chars
- Orchestrator workers (Flash triage, Haiku deep-read) process email in sandbox — raw content never leaves VPS

### Plugin Policy (ADR-008)
- No ClawHub community skills — supply chain risk (ClawHavoc incident, 7%+ flawed)
- Custom skills only (SKILL.md prompt files, no executable code)
- Bundled plugins evaluated individually (memory-core recommended, LanceDB deferred)

### Sandbox Git & Permissions (ADR-011)
- Container runs as `root` (uid 0) but workspace files are owned by `openclaw` (uid 1000)
- `GIT_CONFIG_GLOBAL=/workspace/.gitconfig` must be set so git finds safe.directory config
- If git fails with "dubious ownership" or "permission denied", fix with: `chmod -R a+rw /home/openclaw/.openclaw/workspace/.git/`
- npm/Node build tools work in sandbox (ADR-016). Astro, webpack, npm install all functional.
- Blog is Astro-built, deployed via Cloudflare Pages from `blog-src/` on `gh-pages` branch. Live at `jimbo.pages.dev`. PAT is in the git remote URL. (ADR-027)
- `jimbo-vps` token expires ~May 2026 — check `CAPABILITIES.md` for all token dates.

## Email Pipeline (ADR-022, ADR-029)

### How it works now

Gmail API runs IN the sandbox. No laptop dependency, no Ollama, no mbsync. The orchestrator-conductor pattern (ADR-029) adds a two-pass worker pipeline before Jimbo synthesises the briefing.

```
VPS sandbox:
  gmail-helper.py fetch --hours 24    → calls Gmail API
                                       → applies blacklist (rules, no LLM)
                                       → writes /workspace/email-digest.json

  Orchestrator pipeline (triggered by sift-digest skill):
    email_triage.py                   → Flash triages digest → shortlist (~30 emails)
    newsletter_reader.py              → Haiku deep-reads shortlist → gems JSON
    Jimbo (conductor)                 → reviews worker output, rates quality, synthesises briefing

  experiment-tracker.py               → logs every run with model, tokens, config hash
```

### gmail-helper.py commands
```
python3 /workspace/gmail-helper.py fetch --hours 24              # fetch + filter, write digest
python3 /workspace/gmail-helper.py fetch --hours 48 --no-filter  # bypass blacklist
python3 /workspace/gmail-helper.py fetch --hours 24 --limit 50   # limit email count
```

### Blacklist design

A simple rules-based filter in gmail-helper.py. Two types:
- **Sender blacklist:** match by email or domain (e.g. `noreply@uber.com`, `@linkedin.com`)
- **Subject blacklist:** match by phrase (e.g. "your order", "delivery update")

Newsletters are NOT blacklisted. Jimbo reads them deeply — extracts links, meaning, events, deals. The blacklist only removes obvious junk (receipts, retail spam, loyalty schemes, social media notifications).

To grow the blacklist: edit the `SENDER_BLACKLIST` and `SUBJECT_BLACKLIST` lists in `workspace/gmail-helper.py`.

### Scheduling

VPS root crontab runs the daily pipeline, with failure alerting (ADR-030):
```
# 04:30 — vault task scoring (Gemini Flash)
30 4 * * * export $(grep -v "^#" /opt/openclaw.env | xargs) && \
  docker exec -e GOOGLE_AI_API_KEY=$GOOGLE_AI_API_KEY \
  $(docker ps -q --filter name=openclaw-sbx) \
  python3 /workspace/prioritise-tasks.py \
  >> /var/log/task-scoring.log 2>&1

# 05:00 — Google Tasks sweep (vault intake)
0 5 * * * export $(grep -v "^#" /opt/openclaw.env | xargs) && \
  docker exec -e GOOGLE_CALENDAR_CLIENT_ID=$GOOGLE_CALENDAR_CLIENT_ID \
              -e GOOGLE_CALENDAR_CLIENT_SECRET=$GOOGLE_CALENDAR_CLIENT_SECRET \
              -e GOOGLE_CALENDAR_REFRESH_TOKEN=$GOOGLE_CALENDAR_REFRESH_TOKEN \
              -e GOOGLE_AI_API_KEY=$GOOGLE_AI_API_KEY \
              -e TELEGRAM_BOT_TOKEN=$TELEGRAM_BOT_TOKEN \
              -e TELEGRAM_CHAT_ID=$TELEGRAM_CHAT_ID \
  $(docker ps -q --filter name=openclaw-sbx) \
  sh -c 'python3 /workspace/tasks-helper.py pipeline || \
         python3 /workspace/alert.py "05:00 tasks sweep FAILED"' \
  >> /var/log/tasks-sweep.log 2>&1

# Hourly — email fetch (interval-aware, reads setting from API)
0 * * * * export $(grep -v "^#" /opt/openclaw.env | xargs) && \
  docker exec -e GOOGLE_CALENDAR_CLIENT_ID=$GOOGLE_CALENDAR_CLIENT_ID \
              -e GOOGLE_CALENDAR_CLIENT_SECRET=$GOOGLE_CALENDAR_CLIENT_SECRET \
              -e GOOGLE_CALENDAR_REFRESH_TOKEN=$GOOGLE_CALENDAR_REFRESH_TOKEN \
              -e JIMBO_API_URL=$JIMBO_API_URL \
              -e JIMBO_API_KEY=$JIMBO_API_KEY \
              -e TELEGRAM_BOT_TOKEN=$TELEGRAM_BOT_TOKEN \
              -e TELEGRAM_CHAT_ID=$TELEGRAM_CHAT_ID \
  $(docker ps -q --filter name=openclaw-sbx) \
  python3 /workspace/email-fetch-cron.py \
  >> /var/log/email-fetch.log 2>&1

# Hourly (offset) — combined Telegram status (digest + briefing + credits + model)
30 * * * * export $(grep -v "^#" /opt/openclaw.env | xargs) && \
  docker exec -e OPENROUTER_API_KEY=$OPENROUTER_API_KEY \
              -e TELEGRAM_BOT_TOKEN=$TELEGRAM_BOT_TOKEN \
              -e TELEGRAM_CHAT_ID=$TELEGRAM_CHAT_ID \
  $(docker ps -q --filter name=openclaw-sbx) \
  python3 /workspace/alert-check.py status \
  >> /var/log/alert-check.log 2>&1

# 06:45 — switch to Haiku for morning briefing window
45 6 * * * /usr/local/bin/model-swap-local.sh haiku >> /var/log/model-swap.log 2>&1

# 07:30 — switch back to Flash after briefing
30 7 * * * /usr/local/bin/model-swap-local.sh daily >> /var/log/model-swap.log 2>&1

# 20:00 — daily accountability report via Telegram
0 20 * * * export $(grep -v "^#" /opt/openclaw.env | xargs) && \
  docker exec -e TELEGRAM_BOT_TOKEN=$TELEGRAM_BOT_TOKEN \
              -e TELEGRAM_CHAT_ID=$TELEGRAM_CHAT_ID \
  $(docker ps -q --filter name=openclaw-sbx) \
  python3 /workspace/accountability-check.py \
  >> /var/log/accountability.log 2>&1
```

### Sandbox API keys

The Docker sandbox receives these env vars (set in `/opt/openclaw.env`, passed via `docker exec -e` or openclaw.json sandbox config):
- `GOOGLE_CALENDAR_CLIENT_ID`, `GOOGLE_CALENDAR_CLIENT_SECRET`, `GOOGLE_CALENDAR_REFRESH_TOKEN` — Gmail + Calendar OAuth
- `GOOGLE_AI_API_KEY` — Google AI (Gemini Flash) for email triage worker
- `ANTHROPIC_API_KEY` — Anthropic (Claude Haiku) for newsletter reader worker
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` — Telegram alerts for pipeline failures (ADR-030)
- `OPENROUTER_API_KEY` — OpenRouter balance/usage checks from sandbox (ADR-031)
- `JIMBO_API_URL` — jimbo-api base URL for context-helper.py (ADR-033)
- `JIMBO_API_KEY` — API key for jimbo-api (same as `API_KEY` on the server) (ADR-033)

Daily sequence: task scoring (04:30) → tasks sweep (05:00) → model swap to Haiku (06:45) → email fetch (hourly, interval-aware via settings API) → Jimbo's morning briefing (07:00, OpenClaw cron) → model swap back to Flash (07:30) → status check (hourly at :30) → accountability report (20:00). Tasks are scored against PRIORITIES.md + GOALS.md before the sweep, so newly vaulted tasks from the previous day have priority scores ready for the briefing.

No laptop dependency. The old launchd-triggered pipeline (mbsync → sift-classify.py → sift-push.sh) has been fully retired.

## Notes Vault Pipeline (ADR-023, ADR-024)

### How it works

~13,000 scattered notes from Google Tasks and Google Keep, processed into a structured vault.

```
data/vault/
  ├── notes/          — processed notes (markdown + YAML frontmatter)
  ├── inbox/          — raw unprocessed items awaiting triage
  ├── needs-context/  — items the LLM couldn't classify
  └── archive/        — stale, done, or discarded items
```

### Pipeline

```
1. Export:     tasks-dump.py → data/tasks-dump.json
2. Ingest:     ingest-tasks.py / ingest-keep.py → data/vault/inbox/
3. Classify:   process-inbox.py --manifest → data/triage-manifest.json (LLM suggests actions)
4. Push:       push-manifest.sh → VPS triage data dir
5. Review:     Mobile web UI at site.marvinbarretto.workers.dev/app/jimbo/notes-triage
6. Pull:       pull-decisions.sh → data/triage-decisions.json
7. Apply:      apply-decisions.py → moves vault files to notes/archive/needs-context
```

### Triage UI stack
- **jimbo-api** — Hono/Node API on VPS (port 3100, systemd). Repo: github.com/marvinbarretto/notes-triage-api (private)
- **site** — React triage UI at `/app/jimbo/notes-triage`. Deployed to Cloudflare Workers.
- **Caddy** routes `/api/triage/*` to the API, everything else to OpenClaw.
- See `notes/triage-deploy.md` for full deployment and operations guide.

### Key details
- All scripts are stdlib Python only (no pip). process-inbox.py calls Gemini Flash or Claude Haiku API.
- Vault lives in `data/vault/` (gitignored — contains personal notes, never commit)
- `context/PATTERNS.md` captures classification patterns learned from review sessions
- Notes use 15 types: bookmark, recipe, idea, task, reference, travel, media, checklist, person, finance, health, quote, journal, political, event
- Google Tasks scope upgraded: `tasks.readonly` added to google-auth.py

## Context Files

The `context/` directory contains Marvin's personal context files — pushed to VPS as a backup. The **primary source** for context data (Priorities, Interests, Goals) is now the context API (ADR-033), edited via the web UI at `/app/jimbo/context`. Jimbo reads context via `context-helper.py` which calls the API. Files are NOT hard rules or blocklists — they teach taste and judgment that evolves over time.

- `INTERESTS.md` — topics, hobbies, communities (changes slowly)
- `PRIORITIES.md` — active projects, this week's focus (changes weekly)
- `TASTE.md` — what "good" looks like, what bores him, how he consumes content
- `GOALS.md` — longer-term ambitions (changes monthly)
- `PREFERENCES.md` — the glue: how Jimbo should combine the above for decisions

**How context flows:**
- Context files are pushed to VPS workspace so Jimbo can read them during briefings
- Jimbo reads ALL context files and applies judgment to decide what to highlight from the email digest

**Deploy:** `./scripts/workspace-push.sh` pushes both context files and workspace brain files (SOUL.md, HEARTBEAT.md) to the VPS in one command.

## Data Files (Gitignored)

- `data/recommendations.db` — SQLite recommendations store (personal data, never commit)
- `workspace/cost-tracker.db` — SQLite cost tracking data (on VPS, never commit)
- `workspace/activity-log.db` — SQLite activity log data (on VPS, never commit)
- `data/email-digest.json` — classified email output (contains email content, never commit)
- `data/feedback-*.json` — per-batch email feedback from Marvin (contains email content, never commit)
- `data/sample-maildir/` — test email fixtures
- `data/vault/` — notes vault (personal notes, never commit)
- `data/tasks-dump.json` — raw Google Tasks dump (personal data, never commit)
- `data/export/` — Google Takeout exports (Keep, etc.)
- `~/Mail/gmail/INBOX` — full Gmail Maildir (on laptop, not in repo)

## Conventions

- **ADRs:** Follow template in `decisions/_template.md`. Numbered sequentially (currently at 038).
- **Scripts:** Bash scripts use `set -euo pipefail`. Python scripts use stdlib only (no pip dependencies).
- **Deploy scripts:** Follow `sift-push.sh` pattern — check prerequisites, rsync to VPS via `jimbo` SSH alias. **Never use per-file `scp` loops** — use rsync to batch into a single SSH connection (VPS rate-limits after ~5 connections).
- **Skills:** AgentSkills-compatible `SKILL.md` with YAML frontmatter. Deploy via `skills-push.sh`.
- **No secrets in repo:** All credentials in `/opt/openclaw.env` on VPS. Use `${VAR_NAME}` interpolation in openclaw.json.

## VPS Quick Reference

```bash
ssh jimbo                              # connect to VPS
systemctl status openclaw              # check service
journalctl -u openclaw -f              # tail logs
systemctl restart openclaw             # restart after config changes
nano /home/openclaw/.openclaw/openclaw.json  # edit config
```

Config changes require service restart. Workspace file changes (skills, brain files, digest) take effect on next Jimbo session — no restart needed.

**Switching models:** `./scripts/model-swap.sh {free|cheap|daily|coding|haiku|claude|opus|status}`

**Adding a new LLM provider:** See `setup/configuration.md` for the full cheatsheet — the `openclaw.json` schema is strict and will crash the service if any field is missing (ADR-015).

### Running `openclaw` CLI on VPS (important!)

The CLI needs env vars + correct HOME + correct user. This is the working pattern:

```bash
export $(grep -v '^#' /opt/openclaw.env | xargs) && \
sudo -E -u openclaw HOME=/home/openclaw openclaw <command>
```

See `setup/vps-automation.md` for full cheatsheet and explanation of why simpler approaches don't work.

## What NOT to Do

- Don't commit email content, vault notes, or API keys
- Don't install ClawHub community skills without full source review (see ADR-008)
- Don't put Gmail credentials on the VPS
- Don't use `openclaw config set` (writes to wrong config path — edit openclaw.json directly)
- Don't use `openclaw logs --follow` (uses root's config, missing gateway token — use journalctl)
- Don't run `openclaw` CLI as root without the env var + HOME workaround (see above)
