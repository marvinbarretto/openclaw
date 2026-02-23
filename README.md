# OpenClaw

Personal AI assistant powered by [OpenClaw](https://github.com/openclaw/openclaw), self-hosted on a VPS with Telegram as the primary messaging channel.

## Current Status (2026-02-23)

- **VPS:** DigitalOcean $12/mo, London, IP `167.99.206.214` — RUNNING
- **OpenClaw:** v2026.2.12, dashboard at `https://167.99.206.214`
- **Telegram:** Connected via `@fourfold_openclaw_bot` ("Jimbo") — WORKING
- **AI Provider:** Google AI direct (`google/gemini-2.5-flash`) — ~$0.78/month (ADR-015)
- **Sandbox:** Custom Docker image with Python 3.11, Node 18, git — WORKING
- **Local models:** Ollama — `qwen2.5-coder:14b` + `qwen2.5:7b` — TESTED
- **Jimbo's GitHub:** https://github.com/marvinbarretto-labs — separate account for agent work
- **Jimbo's workspace:** `jimbo-workspace` repo — Jimbo can autonomously write, commit, and push
- **Blog:** Astro-built, auto-deployed via Cloudflare Pages at `jimbo.pages.dev` (ADR-027)
- **Email pipeline:** Gmail API in sandbox → email-digest.json → Jimbo reads with judgment (ADR-022)
- **Custom skills:** sift-digest, daily-briefing, blog-publisher, rss-feed, calendar, day-planner, web-style-guide
- **Context system:** `context/` files (interests, priorities, taste, goals, patterns) — feeds Jimbo's judgment
- **Notes vault:** ~13k notes from Google Tasks/Keep, LLM-classified into structured vault (ADR-023)
- **Recommendations:** SQLite-backed store for email/vault finds with scores and expiry (ADR-025)

## Stack

- **Runtime:** OpenClaw 2026.2.12 on Ubuntu 24.04 (DigitalOcean 1-Click)
- **Messaging:** Telegram Bot API
- **LLM (cloud):** Google AI direct (Gemini 2.5 Flash, daily), OpenRouter (free/coding), Anthropic (premium)
- **LLM (local):** Ollama on MacBook Air 24GB (Qwen 2.5 Coder 14B)
- **Blog:** Astro 4.x → Cloudflare Pages (`jimbo.pages.dev`)
- **Hosting:** DigitalOcean $12/mo (2GB RAM, 1 vCPU, 50GB, LON1)
- **DNS/Proxy:** Caddy (built into 1-Click image, auto TLS)

## Quick Links

- [OpenClaw GitHub](https://github.com/openclaw/openclaw)
- [OpenClaw Docs](https://docs.openclaw.ai/)
- [OpenClaw on DigitalOcean](https://docs.openclaw.ai/platforms/digitalocean)
- [Dashboard](https://167.99.206.214)
- [Jimbo's Blog](https://jimbo.pages.dev/)

## Quick Reference

```bash
# Connect to VPS (ssh -t root@167.99.206.214)
ssh jimbo

# Check status
systemctl status openclaw

# Tail logs
journalctl -u openclaw -f

# Restart after config changes
systemctl restart openclaw

# Config files
/opt/openclaw.env                              # API keys, tokens
/home/openclaw/.openclaw/openclaw.json         # Plugins, channels, model
```

## Skills

Custom skills that teach Jimbo structured capabilities. These are `SKILL.md` files deployed to the VPS workspace — prompt-only, no third-party code, zero supply-chain risk.

| Skill | What it does |
|---|---|
| `sift-digest` | Read and present the email digest |
| `daily-briefing` | Morning overview (email + calendar + tasks + context) |
| `blog-publisher` | Write markdown posts → Astro auto-builds index, tags, archive, RSS |
| `rss-feed` | Auto-generated RSS feed at `/rss.xml` (via Astro) |
| `calendar` | Read/create calendar events via Calendar API |
| `day-planner` | Proactive day planning — suggest activities for free gaps |
| `web-style-guide` | Design tokens and HTML/CSS standards for blog and web projects |

Note: Skills are triggered via natural language in Telegram, not slash commands.

## Deploying to VPS

Everything we maintain lives in this repo. **Never edit files directly on the VPS** — edit locally, commit, then push with scripts:

```bash
# Push everything Jimbo needs (brain files + context)
./scripts/workspace-push.sh        # SOUL.md, HEARTBEAT.md, context/*.md → VPS
./scripts/skills-push.sh           # skills/ → VPS

# Blog source (Astro project) — push separately
rsync -avz --exclude='node_modules/' --exclude='dist/' --exclude='.astro/' \
  workspace/blog-src/ jimbo:/home/openclaw/.openclaw/workspace/blog-src/

# Model management
./scripts/model-swap.sh daily      # switch Jimbo's LLM model
./scripts/model-swap.sh status     # check current model

# Dry run (preview without changes)
./scripts/workspace-push.sh --dry-run
./scripts/skills-push.sh --dry-run
```

All workspace/skill changes are picked up on Jimbo's next session (no restart needed). Model changes require a restart (model-swap.sh does this automatically).

### What lives where

| This repo | VPS destination | Push script | Restart needed? |
|-----------|----------------|-------------|-----------------|
| `workspace/SOUL.md` | `/workspace/SOUL.md` | `workspace-push.sh` | No |
| `workspace/HEARTBEAT.md` | `/workspace/HEARTBEAT.md` | `workspace-push.sh` | No |
| `context/*.md` | `/workspace/context/` | `workspace-push.sh` | No |
| `skills/*/SKILL.md` | `/workspace/skills/` | `skills-push.sh` | No |
| `workspace/blog-src/` | `/workspace/blog-src/` | rsync (see above) | No |
| `openclaw.json` changes | `/home/openclaw/.openclaw/openclaw.json` | `model-swap.sh` or manual | Yes |

### Files Jimbo writes himself (NOT tracked here)

These live only on the VPS. Jimbo creates and updates them — don't overwrite:
- `IDENTITY.md` — Jimbo's name and personality (written during bootstrap)
- `USER.md` — What Jimbo knows about Marvin (learned from conversations)
- `MEMORY.md` — Long-term curated memory
- `JIMBO_DIARY.md` — Jimbo's daily journal
- `memory/*.md` — Per-day conversation logs
- `blog-src/src/content/posts/*.md` — Blog posts Jimbo writes himself

**Blog publishing (Jimbo's workflow):**
```
Write .md file in blog-src/src/content/posts/ → commit → push → Cloudflare auto-builds
```
Heartbeat auto-commit (~30 min) also triggers builds, so posts auto-publish.

**Third-party skills:** We do not install community skills from ClawHub. See [ADR-008](decisions/008-plugin-adoption-policy.md) for our adoption policy.

## This Folder

| Folder | Purpose |
|---|---|
| `workspace/` | Brain files we maintain (SOUL.md, HEARTBEAT.md) + blog source (blog-src/) → pushed to VPS |
| `context/` | Marvin's personal context (interests, priorities, taste, goals, patterns) → pushed to VPS |
| `skills/` | Custom OpenClaw skills (7 skills) → pushed to VPS |
| `scripts/` | Deploy scripts, classifier, model-swap, vault pipeline |
| `decisions/` | ADRs (001–027): sandbox, email, models, plugins, automation, blog, vault, recommendations |
| `setup/` | Configuration docs, [architecture](setup/architecture.md), [workspace files guide](setup/workspace-files.md), provider setup cheatsheet |
| `hosting/` | VPS comparison (decided: DigitalOcean), networking & DNS |
| `security/` | Hardening checklist, data privacy |
| `sandbox/` | Custom Docker image Dockerfile |
| `data/` | Email digest, vault, recommendations (all gitignored — personal data) |
| `notes/` | Raw thinking and brain dumps |
