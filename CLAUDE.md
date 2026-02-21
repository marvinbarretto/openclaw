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
  ├── mbsync → Gmail Maildir at ~/Mail/gmail/INBOX (~28k emails)
  └── Sift pipeline: sift-classify.py (Ollama) → email-digest.json → sift-push.sh → VPS

VPS (DigitalOcean $12/mo, London, 167.99.206.214)
  ├── OpenClaw v2026.2.12 (Node 22, systemd, openclaw user)
  ├── Docker sandbox (Python 3.11, Node 18, git, hardened)
  │     └── /workspace — Jimbo's brain files + skills + email digest
  └── Caddy (auto TLS)
```

SSH alias: `ssh jimbo` connects to VPS.

## Repo Structure

```
context/          Marvin's personal context files (interests, priorities, taste, goals, preferences)
decisions/        ADRs (001-022) — sandbox, email triage, prompt injection, models, plugins, automation, git deployment, feedback insights, model upgrades, Node build tools, Gemini direct, MCP, calendar, day planner, multi-model routing, architecture review, Gmail API migration
scripts/          sift-classify.py, sift-sample.py, sift-push.sh, skills-push.sh, workspace-push.sh, model-swap.sh, sift-cron.sh
skills/           Custom OpenClaw skills (sift-digest, daily-briefing, calendar, day-planner, blog-publisher, rss-feed, web-style-guide)
workspace/        Jimbo's brain files that WE maintain (SOUL.md, HEARTBEAT.md). Deploy via workspace-push.sh.
setup/            Configuration docs, architecture, workspace files guide, launchd plist
security/         VPS hardening checklist
hosting/          VPS comparison, networking
sandbox/          Custom Docker image Dockerfile
data/             Email digest output + feedback files (gitignored)
notes/            Brain dumps
```

## Key Files

- `scripts/sift-classify.py` — Core Sift pipeline. Reads Maildir, classifies via Ollama, outputs email-digest.json
- `scripts/sift-cron.sh` — Automated pipeline: mbsync → classify → push. Runs via launchd at 4am.
- `scripts/sift-push.sh` — Rsyncs email-digest.json to VPS workspace
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

## Security Model (Critical — Read Before Changing)

### Three-Zone Access (ADR-001)
- **Zone 1 (Sandbox):** Jimbo has full read/write to `jimbo-workspace` repo only
- **Zone 2 (Read-only):** Fine-grained token for Marvin's real repos (currently disabled)
- **Zone 3 (Blocked):** Primary GitHub, cloud creds, DNS, production — NOTHING on VPS

### Prompt Injection (ADR-003)
- **Reader/Actor split:** Untrusted text (email, issues) goes to a Reader model with NO tool access
- Reader outputs fixed-schema JSON only; Actor never sees raw untrusted text
- Email classification runs fully offline via local Ollama — content never leaves the laptop

### Email Security (ADR-002)
- No Gmail credentials on VPS — ever
- Email classified locally (Ollama), only the digest JSON is pushed to VPS
- HTML stripped, body truncated to 2000 chars, strict schema validation
- Agent cannot send, delete, or modify email

### Plugin Policy (ADR-008)
- No ClawHub community skills — supply chain risk (ClawHavoc incident, 7%+ flawed)
- Custom skills only (SKILL.md prompt files, no executable code)
- Bundled plugins evaluated individually (memory-core recommended, LanceDB deferred)

### Sandbox Git & Permissions (ADR-011)
- Container runs as `root` (uid 0) but workspace files are owned by `openclaw` (uid 1000)
- `GIT_CONFIG_GLOBAL=/workspace/.gitconfig` must be set so git finds safe.directory config
- If git fails with "dubious ownership" or "permission denied", fix with: `chmod -R a+rw /home/openclaw/.openclaw/workspace/.git/`
- npm/Node build tools (Astro, webpack) don't work — uid mismatch causes fchown errors. Static files only.
- Blog deploys to GitHub Pages via `gh-pages` branch. PAT is in the git remote URL.
- `jimbo-vps` token expires ~May 2026 — check `CAPABILITIES.md` for all token dates.

## Sift Email Pipeline

### Manual workflow
```
mbsync -a                                                     # sync Gmail → ~/Mail/gmail/INBOX
python3 scripts/sift-classify.py --input ~/Mail/gmail/INBOX   # classify via Ollama (local)
./scripts/sift-push.sh                                        # push digest to VPS
```

### Automated workflow (ADR-010)
```
04:00  launchd (laptop)     sift-cron.sh: mbsync → classify → push
07:00  OpenClaw cron (VPS)  Jimbo sends morning briefing via Telegram
~30m   Heartbeat (VPS)      Jimbo checks for fresh/stale digest
```

Laptop produces (needs Gmail creds + local Ollama). VPS consumes (always on, sends Telegram).
Use OpenClaw's built-in cron/heartbeat for VPS-side scheduling, NOT laptop cron.
See: https://docs.openclaw.ai/automation/cron-vs-heartbeat

### sift-classify.py flags
- `--hours N` — look back N hours (default 24)
- `--all` — ignore date filters, process all emails
- `--limit N` — max emails to classify
- `--model MODEL` — Ollama model (default qwen2.5:7b)

### Classifier design (important)

The classifier (Ollama) does the **grunt work** — rough sort into queue/skip. It should NOT apply taste or nuanced judgment. Its job:
- Always queue: personal replies, events, travel deals, booking updates
- Always skip: order confirmations, brand marketing, loyalty schemes, spam
- Use judgment for newsletters: when unsure, queue it and let Jimbo decide

Jimbo does the **thinking** — reads `context/` files (interests, priorities, taste, goals) and applies judgment to decide what to highlight, mention, or skip in the briefing. A weak issue of a normally-good newsletter should still get dropped. A surprisingly good email from an unknown sender should surface.

### Known Issues
- **mbsync mtime:** mbsync sets file mtime to sync time, not email receive time. The mtime pre-filter uses a 7-day buffer to compensate but first syncs may need `--all`.
- **Laptop must be awake at 4am:** macOS Power Nap should handle this if plugged in. If on battery, the launchd job may not fire and the 7am briefing will use stale data. The heartbeat catches this.

## Context Files

The `context/` directory contains Marvin's personal context — pushed to VPS so Jimbo can read them, and used locally by sift-classify.py. These are NOT hard rules or blocklists. They teach taste and judgment that evolves over time.

- `INTERESTS.md` — topics, hobbies, communities (changes slowly)
- `PRIORITIES.md` — active projects, this week's focus (changes weekly)
- `TASTE.md` — what "good" looks like, what bores him, how he consumes content
- `GOALS.md` — longer-term ambitions (changes monthly)
- `PREFERENCES.md` — the glue: how Jimbo should combine the above for decisions

**How context flows:**
- `sift-classify.py` reads INTERESTS + PRIORITIES locally to build the Ollama prompt (classifier sorts)
- Context files are pushed to VPS workspace so Jimbo can read ALL of them (Jimbo curates with taste + judgment)

**Deploy:** `./scripts/workspace-push.sh` pushes both context files and workspace brain files (SOUL.md, HEARTBEAT.md) to the VPS in one command.

## Data Files (Gitignored)

- `data/email-digest.json` — classified email output (contains email content, never commit)
- `data/feedback-*.json` — per-batch email feedback from Marvin (contains email content, never commit)
- `data/sample-maildir/` — test email fixtures
- `~/Mail/gmail/INBOX` — full Gmail Maildir (on laptop, not in repo)

## Conventions

- **ADRs:** Follow template in `decisions/_template.md`. Numbered sequentially (currently at 019).
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

- Don't commit email content or API keys
- Don't install ClawHub community skills without full source review (see ADR-008)
- Don't put Gmail credentials on the VPS
- Don't use `openclaw config set` (writes to wrong config path — edit openclaw.json directly)
- Don't use `openclaw logs --follow` (uses root's config, missing gateway token — use journalctl)
- Don't run `openclaw` CLI as root without the env var + HOME workaround (see above)
