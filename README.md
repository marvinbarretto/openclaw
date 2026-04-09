# OpenClaw (Jimbo)

Personal AI assistant powered by [OpenClaw](https://github.com/openclaw/openclaw), self-hosted on a DigitalOcean VPS. Accessible via Telegram (`@fourfold_openclaw_bot`).

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Marvin's Laptop (MacBook Air)                                  │
│                                                                 │
│  openclaw/  ─── this repo (config, scripts, skills, decisions)  │
│  site/      ─── personal site (Astro/Cloudflare Workers)        │
│                  └── /app/jimbo/  dashboard, triage UI,         │
│                      context editor, settings                   │
│  jimbo/jimbo-api/  ─── jimbo-api source (Hono/Node)            │
│                                                                 │
│  Deploy:  workspace-push.sh ──rsync──►  VPS                    │
│           skills-push.sh   ──rsync──►  VPS                     │
└─────────────────────────────────────────────────────────────────┘
                          │ ssh jimbo
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│  VPS (DigitalOcean $12/mo, London, 167.99.206.214)              │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  OpenClaw v2026.3.1 (systemd: openclaw)                   │  │
│  │  ├── Telegram provider (@fourfold_openclaw_bot)           │  │
│  │  ├── Heartbeat (hourly, 07:00-01:00)                      │  │
│  │  ├── Native cron (morning briefing 07:00 London)          │  │
│  │  ├── Sub-agents (email-triage-worker, newsletter-reader)  │  │
│  │  └── Memory (FTS5 + vector search)                        │  │
│  └───────────────────────────────────────────────────────────┘  │
│                          │ docker exec                          │
│  ┌───────────────────────▼───────────────────────────────────┐  │
│  │  Docker Sandbox (openclaw-sbx)                            │  │
│  │  /workspace/                                              │  │
│  │  ├── SOUL.md, HEARTBEAT.md     ← brain files             │  │
│  │  ├── gmail-helper.py           ← Gmail API (read-only)   │  │
│  │  ├── calendar-helper.py        ← Calendar API             │  │
│  │  ├── context-helper.py         ← reads from jimbo-api     │  │
│  │  ├── settings-helper.py        ← reads from jimbo-api     │  │
│  │  ├── alert.py / alert-check.py ← Telegram alerts          │  │
│  │  ├── experiment-tracker.py     ← run logging (via API)    │  │
│  │  ├── cost-tracker.py           ← cost logging (via API)   │  │
│  │  ├── activity-log.py           ← activity log (via API)   │  │
│  │  ├── prioritise-tasks.py       ← Gemini Flash task scorer │  │
│  │  ├── workers/                  ← orchestrator workers     │  │
│  │  │   ├── email_triage.py       (Gemini Flash)             │  │
│  │  │   └── newsletter_reader.py  (Claude Haiku)             │  │
│  │  ├── vault/                    ← notes vault (13k notes)  │  │
│  │  ├── context/                  ← backup context files     │  │
│  │  └── blog-src/                 ← Astro blog               │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  jimbo-api (systemd: jimbo-api, port 3100)                │  │
│  │  ├── /api/triage/*       ← notes triage                   │  │
│  │  ├── /api/context/*      ← priorities, interests, goals   │  │
│  │  ├── /api/settings/*     ← key-value config store         │  │
│  │  ├── /api/activity/*     ← activity log                   │  │
│  │  ├── /api/costs/*        ← cost tracking                  │  │
│  │  ├── /api/experiments/*  ← experiment runs                │  │
│  │  ├── /api/vault/*        ← vault notes                    │  │
│  │  └── data/context.db     ← SQLite backing store           │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│  Caddy (auto TLS) ── routes /api/* → jimbo-api                  │
│  Cron (root crontab) ── email fetch, task scoring, model swap   │
└─────────────────────────────────────────────────────────────────┘
                          │
          ┌───────────────┼───────────────────┐
          ▼               ▼                   ▼
   ┌────────────┐  ┌────────────┐  ┌───────────────────┐
   │  Telegram   │  │  Gmail API │  │  Cloudflare Pages  │
   │  Bot API    │  │  (readonly)│  │  (jimbo.pages.dev) │
   └────────────┘  └────────────┘  └───────────────────┘
```

## Daily Schedule

```
UTC   What                              Model
────  ──────────────────────────────    ──────────────────
04:30 Vault task scoring (cron)         Gemini Flash (direct)
05:00 Google Tasks sweep (cron)         Gemini Flash (direct)
06:45 Model swap → Sonnet
07:00 Morning briefing (OpenClaw cron)  Sonnet (via OpenRouter)
07:30 Model swap → Kimi K2
  :00 Email fetch (hourly, cron)        —
  :30 Status check (hourly, cron)       —
14:45 Model swap → Sonnet
15:00 Afternoon briefing (heartbeat)    Sonnet (via OpenRouter)
15:30 Model swap → Kimi K2
20:00 Accountability report (cron)      —
```

## Repo Structure

```
context/       Marvin's personal context (interests, priorities, taste, goals)
decisions/     ADRs (001-042)
docs/
  plans/       Implementation plans
  reviews/     Review session notes
  reference/   Operational reference docs (VPS ops, orchestrator details)
scripts/       Deploy scripts, ingestion pipelines, model-swap
skills/        Custom OpenClaw skills (SKILL.md files)
workspace/     Jimbo's brain files + workers + helpers (deployed to VPS)
sandbox/       Docker image definition
setup/         VPS configuration docs
security/      Hardening checklist
hosting/       VPS comparison notes
data/          Email digest, vault, exports (all gitignored)
notes/         Brain dumps
```

## Key Commands

```bash
# Deploy workspace + skills to VPS
./scripts/workspace-push.sh && ./scripts/skills-push.sh

# Sync OpenClaw cron prompts to explicit /workspace skill paths
./scripts/openclaw-cron-sync.sh

# Switch VPS model
./scripts/model-swap.sh {sonnet|kimi|haiku|flash|status}

# Check VPS health
ssh jimbo "systemctl status openclaw --no-pager && docker ps --filter name=openclaw-sbx"

# Restart after config changes
ssh jimbo "systemctl restart openclaw"
```

## Docs Index

| Doc | What it covers |
|-----|----------------|
| `CLAUDE.md` | Full project context for Claude Code sessions |
| `CAPABILITIES.md` | What Jimbo can/can't do, token expiry dates |
| `docs/reference/vps-operations.md` | VPS gotchas (reboot, SSH, networking) |
| `docs/reference/orchestrator-details.md` | Worker architecture, games, deployment |
| `setup/configuration.md` | VPS config, provider setup cheatsheet |
| `notes/triage-deploy.md` | Triage pipeline architecture and ops |
| `decisions/` | All architectural decision records (001-042) |

## Skills

Custom skills deployed to VPS workspace — prompt-only SKILL.md files, no third-party code.

| Skill | What it does |
|---|---|
| `sift-digest` | Orchestrate email workers, synthesise and present the digest |
| `daily-briefing` | Morning + afternoon briefing (email + calendar + tasks + context) |
| `blog-publisher` | Write markdown posts → Astro auto-builds |
| `calendar` | Read/create calendar events via Calendar API |
| `day-planner` | Proactive day planning — suggest activities for free gaps |
| `cost-tracker` | Budget monitoring and cost visibility |
| `tasks-triage` | Interactive Telegram triage for ambiguous vault tasks |
| `web-style-guide` | Design tokens and HTML/CSS standards |
| `rss-feed` | Auto-generated RSS feed via Astro |

## Deploying to VPS

Everything we maintain lives in this repo. Edit locally, commit, then push with scripts:

```bash
./scripts/workspace-push.sh        # brain files + context + helpers → VPS
./scripts/skills-push.sh           # skills/ → VPS
```

All workspace/skill changes are picked up on Jimbo's next session (no restart needed). Model changes require a restart (`model-swap.sh` does this automatically).

### What lives where

| This repo | VPS destination | Push script | Restart? |
|-----------|----------------|-------------|----------|
| `workspace/SOUL.md` | `/workspace/SOUL.md` | `workspace-push.sh` | No |
| `workspace/HEARTBEAT.md` | `/workspace/HEARTBEAT.md` | `workspace-push.sh` | No |
| `workspace/*.py` | `/workspace/*.py` | `workspace-push.sh` | No |
| `workspace/workers/` | `/workspace/workers/` | `workspace-push.sh` | No |
| `context/*.md` | `/workspace/context/` | `workspace-push.sh` | No |
| `skills/*/SKILL.md` | `/workspace/skills/` | `skills-push.sh` | No |
| `workspace/blog-src/` | `/workspace/blog-src/` | `workspace-push.sh` | No |
| `openclaw.json` changes | edit on VPS directly | — | Yes |
| `setup/openclaw-cron-skills.json` | live cron prompts in `jobs.json` | `openclaw-cron-sync.sh` | Yes |

### Files Jimbo writes himself (NOT tracked here)

These live only on the VPS. Jimbo creates and updates them — don't overwrite:
- `IDENTITY.md` — Jimbo's personality (written during bootstrap)
- `USER.md` — What Jimbo knows about Marvin (learned from conversations)
- `MEMORY.md` — Long-term curated memory
- `JIMBO_DIARY.md` — Jimbo's daily journal
- `blog-src/src/content/posts/*.md` — Blog posts Jimbo writes

## Security

- No community skills from ClawHub (ADR-008)
- Gmail API is read-only (ADR-002)
- Prompt injection mitigation via Reader/Actor split (ADR-003)
- No production credentials on VPS (ADR-001)
- See `security/` and `CLAUDE.md` for full security model

## Quick Links

- [OpenClaw GitHub](https://github.com/openclaw/openclaw)
- [OpenClaw Docs](https://docs.openclaw.ai/)
- [Dashboard](https://167.99.206.214)
- [Jimbo's Blog](https://jimbo.pages.dev/)
- [Jimbo Dashboard](https://site.marvinbarretto.workers.dev/app/jimbo/)

---

*Last updated: 2026-03-07*



TEMP NOTES: Need to store the overall intentions and rationale somewhere centrally and iterate on this:

  Decision layer — Something on the VPS (Gemini Flash / Haiku) reads the
  undecided reports, cross-references your priorities and context from
  jimbo-api, and decides: is this relevant? does it need action? should it
  surface in your briefing? That's the decided flag.

  Briefing integration — The morning briefing pipeline should pull decided
  email insights alongside calendar, tasks, vault. "You got an email about a
  comedy night Friday at Watford Palace — matches your 'local events'
  interest."

  Feedback loop — When you mark things as useful/not useful, that tunes what
  Ralph prioritises. Right now everything gets the same treatment.

  More job types — The job architecture is there. RSS feeds, Hacker News,
  calendar prep, anything with a queue of items to read deeply.

  Scheduling — Ralph should run on a launchd timer, not manually. Probably
  every few hours while the Mac is open.

  The pattern is always the same: Ralph does the slow, thorough, free work
  locally. Smart models on the VPS make the judgment calls. You see the
  results in your briefing.
