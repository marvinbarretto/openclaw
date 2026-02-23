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
  │     └── recommendations-helper.py — SQLite CRUD for persistent recommendations store
  └── Caddy (auto TLS)
```

Email pipeline: Gmail API runs IN the sandbox (no laptop dependency). Blacklist removes junk, Jimbo reads the rest deeply. No LLM classification step.

SSH alias: `ssh jimbo` connects to VPS.

## Repo Structure

```
context/          Marvin's personal context files (interests, priorities, taste, goals, preferences)
decisions/        ADRs (001-027) — sandbox, email triage, prompt injection, models, plugins, automation, git deployment, feedback insights, model upgrades, Node build tools, Gemini direct, MCP, calendar, day planner, multi-model routing, architecture review, Gmail API migration, notes vault, notes review queue, recommendations store, Cloudflare Pages, Astro blog migration
scripts/          sift-classify.py, sift-sample.py, sift-push.sh, skills-push.sh, workspace-push.sh, model-swap.sh, sift-cron.sh, ingest-tasks.py, ingest-keep.py, process-inbox.py, tasks-dump.py
skills/           Custom OpenClaw skills (sift-digest, daily-briefing, calendar, day-planner, blog-publisher, rss-feed, web-style-guide)
workspace/        Jimbo's brain files (SOUL.md, HEARTBEAT.md) + blog source (blog-src/). Deploy via workspace-push.sh + rsync.
setup/            Configuration docs, architecture, workspace files guide, launchd plist
security/         VPS hardening checklist
hosting/          VPS comparison, networking
sandbox/          Custom Docker image Dockerfile
data/             Email digest output + feedback files + vault (all gitignored)
notes/            Brain dumps
```

## Key Files

- `.claude/commands/manual-review.md` — Claude Code custom command for interactive review of `needs-context` vault notes. Invoke with `/manual-review 10`. Presents notes, collects triage decisions (direct/context/archive/skip), updates frontmatter, moves files.
- `workspace/recommendations-helper.py` — SQLite CRUD for persistent recommendations store. Jimbo logs finds from email/vault, tracks scores, urgency, expiry. Stdlib only, no OAuth.
- `workspace/gmail-helper.py` — Gmail API client for sandbox. Fetches email, applies blacklist, writes email-digest.json directly. No LLM classification.
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
- `skills/daily-briefing/SKILL.md` — Teaches Jimbo to give morning briefings
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
- `scripts/process-inbox.py` — LLM batch classifier: inbox → notes/needs-context/archive (uses Claude Haiku)
- `workspace/blog-src/` — Astro blog project. Posts in `src/content/posts/*.md`. Auto-generates index, tags, archive, RSS. Deployed via Cloudflare Pages (ADR-027).
- `decisions/027-astro-blog-migration.md` — ADR for blog migration from static HTML to Astro

## Security Model (Critical — Read Before Changing)

### Three-Zone Access (ADR-001)
- **Zone 1 (Sandbox):** Jimbo has full read/write to `jimbo-workspace` repo only
- **Zone 2 (Read-only):** Fine-grained token for Marvin's real repos (currently disabled)
- **Zone 3 (Blocked):** Primary GitHub, cloud creds, DNS, production — NOTHING on VPS

### Prompt Injection (ADR-003)
- **Reader/Actor split:** Untrusted text (email, issues) goes to a Reader model with NO tool access
- Reader outputs fixed-schema JSON only; Actor never sees raw untrusted text
- Email classification runs fully offline via local Ollama — content never leaves the laptop

### Email Security (ADR-002, updated ADR-022)
- Gmail API access is **read-only** (gmail.readonly scope). Agent cannot send, delete, or modify email.
- OAuth credentials on VPS (same token as Calendar — just wider scope)
- gmail-helper.py fetches email in sandbox, applies blacklist, writes digest locally
- HTML stripped, body truncated to 5000 chars
- No LLM classification step — Jimbo reads raw emails and applies own judgment

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

## Email Pipeline (ADR-022)

### How it works now

Gmail API runs IN the sandbox. No laptop dependency, no Ollama, no mbsync.

```
VPS sandbox:
  gmail-helper.py fetch --hours 24    → calls Gmail API
                                       → applies blacklist (rules, no LLM)
                                       → writes /workspace/email-digest.json

  Jimbo reads digest during briefing  → applies TASTE/PRIORITIES/GOALS/INTERESTS
                                       → deeply reads newsletters (full body, links)
                                       → presents highlights via sift-digest skill
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

### Legacy pipeline (deprecated)
The old pipeline (mbsync → sift-classify.py → sift-push.sh) is no longer used. Scripts remain in `scripts/` for reference but are marked LEGACY. The old pipeline had issues: 2.5 hour classify time, laptop dependency, broken network check, LLM-classifying-for-LLM redundancy.

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
3. Classify:   process-inbox.py → notes/ | needs-context/ | archive/
4. Review:     (ADR-024, not yet built) mobile web UI for needs-context items
```

### Key details
- All scripts are stdlib Python only (no pip). process-inbox.py calls Claude Haiku API.
- Vault lives in `data/vault/` (gitignored — contains personal notes, never commit)
- `context/PATTERNS.md` captures classification patterns learned from review sessions
- Notes use 8 types: bookmark, recipe, idea, task, reference, travel, media, checklist
- Google Tasks scope upgraded: `tasks.readonly` added to google-auth.py

## Context Files

The `context/` directory contains Marvin's personal context — pushed to VPS so Jimbo can read them. These are NOT hard rules or blocklists. They teach taste and judgment that evolves over time.

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
- `data/email-digest.json` — classified email output (contains email content, never commit)
- `data/feedback-*.json` — per-batch email feedback from Marvin (contains email content, never commit)
- `data/sample-maildir/` — test email fixtures
- `data/vault/` — notes vault (personal notes, never commit)
- `data/tasks-dump.json` — raw Google Tasks dump (personal data, never commit)
- `data/export/` — Google Takeout exports (Keep, etc.)
- `~/Mail/gmail/INBOX` — full Gmail Maildir (on laptop, not in repo)

## Conventions

- **ADRs:** Follow template in `decisions/_template.md`. Numbered sequentially (currently at 027).
- **Scripts:** Bash scripts use `set -euo pipefail`. Python scripts use stdlib only (no pip dependencies).
- **Deploy scripts:** Follow `sift-push.sh` pattern — check prerequisites, rsync to VPS via `jimbo` SSH alias.
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
