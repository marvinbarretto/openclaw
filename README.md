# OpenClaw

Personal AI assistant powered by [OpenClaw](https://github.com/openclaw/openclaw), self-hosted on a VPS with Telegram as the primary messaging channel.

## Current Status (2026-02-20)

- **VPS:** DigitalOcean $12/mo, London, IP `167.99.206.214` — RUNNING
- **OpenClaw:** v2026.2.12, dashboard at `https://167.99.206.214`
- **Telegram:** Connected via `@fourfold_openclaw_bot` ("Jimbo") — WORKING
- **AI Provider:** Google AI direct (`google/gemini-2.5-flash`) — ~$0.78/month (ADR-015)
- **Sandbox:** Custom Docker image with Python 3.11, Node 18, git — WORKING
- **Local models:** Ollama — `qwen2.5-coder:14b` (classifier default) + `qwen2.5:7b` — TESTED
- **Jimbo's GitHub:** https://github.com/marvinbarretto-labs — separate account for agent work
- **Jimbo's workspace:** `jimbo-workspace` repo — Jimbo can autonomously write, commit, and push
- **Sift pipeline:** mbsync → sift-classify.py (Ollama) → email-digest.json → sift-push.sh → VPS — END-TO-END WORKING
- **Custom skills:** `sift-digest` + `daily-briefing` deployed to VPS — WORKING
- **Gmail sync:** mbsync configured, ~28k emails synced to local Maildir — WORKING
- **Automation:** launchd (4am classify) → OpenClaw cron (7am briefing) → heartbeat (digest freshness) — RUNNING
- **Context system:** `context/` files (interests, priorities, taste, goals) — feeds Jimbo's judgment
- **First feedback cycle:** 158 emails reviewed, classifier prompt retuned (ADR-012) — DONE

## Stack

- **Runtime:** OpenClaw 2026.2.12 on Ubuntu 24.04 (DigitalOcean 1-Click)
- **Messaging:** Telegram Bot API
- **LLM (cloud):** Google AI direct (Gemini 2.5 Flash, daily), OpenRouter (free/coding), Anthropic (premium)
- **LLM (local):** Ollama on MacBook Air 24GB (Qwen 2.5 Coder 14B for classification)
- **Hosting:** DigitalOcean $12/mo (2GB RAM, 1 vCPU, 50GB, LON1)
- **DNS/Proxy:** Caddy (built into 1-Click image, auto TLS)

## Quick Links

- [OpenClaw GitHub](https://github.com/openclaw/openclaw)
- [OpenClaw Docs](https://docs.openclaw.ai/)
- [OpenClaw on DigitalOcean](https://docs.openclaw.ai/platforms/digitalocean)
- [Dashboard](https://167.99.206.214)
- [Test Monorepo](https://github.com/marvinbarretto/openclaw-test-monorepo)

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

| Skill | Trigger | What it does |
|---|---|---|
| `sift-digest` | "check my email" | Read and present the Sift email digest |
| `daily-briefing` | "give me a briefing" | Concise morning overview (email + tasks + context) |

Note: Skills are triggered via natural language in Telegram, not slash commands.

## Deploying to VPS

Everything we maintain lives in this repo. **Never edit files directly on the VPS** — edit locally, commit, then push with scripts:

```bash
# Push everything Jimbo needs (brain files + context + email digest)
./scripts/workspace-push.sh        # SOUL.md, HEARTBEAT.md, context/*.md → VPS
./scripts/skills-push.sh           # skills/ → VPS
./scripts/sift-push.sh             # email-digest.json → VPS

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
| `data/email-digest.json` | `/workspace/email-digest.json` | `sift-push.sh` | No |
| `openclaw.json` changes | `/home/openclaw/.openclaw/openclaw.json` | `model-swap.sh` or manual | Yes |

### Files Jimbo writes himself (NOT tracked here)

These live only on the VPS. Jimbo creates and updates them — don't overwrite:
- `IDENTITY.md` — Jimbo's name and personality (written during bootstrap)
- `USER.md` — What Jimbo knows about Marvin (learned from conversations)
- `MEMORY.md` — Long-term curated memory
- `JIMBO_DIARY.md` — Jimbo's daily journal
- `memory/*.md` — Per-day conversation logs

**Sift pipeline (email → Jimbo):**
```bash
# Manual run
mbsync -a                                                    # sync Gmail → local Maildir
python3 scripts/sift-classify.py --input ~/Mail/gmail/INBOX  # classify recent emails
./scripts/sift-push.sh                                       # push digest to Jimbo

# Automated (see ADR-010)
# 04:00 launchd (laptop): sift-cron.sh → mbsync + classify + push
# 07:00 OpenClaw cron (VPS): Jimbo sends morning briefing via Telegram
# ~30m  Heartbeat (VPS): Jimbo checks for fresh/stale digest

# Backlog processing (see ADR-009)
python3 scripts/sift-classify.py --input ~/Mail/gmail/INBOX --all --limit 200
```

**Third-party skills:** We do not install community skills from ClawHub. See [ADR-008](decisions/008-plugin-adoption-policy.md) for our adoption policy.

## This Folder

| Folder | Purpose |
|---|---|
| `workspace/` | Brain files we maintain (SOUL.md, HEARTBEAT.md) → pushed to VPS |
| `context/` | Marvin's personal context (interests, priorities, taste, goals) → pushed to VPS |
| `skills/` | Custom OpenClaw skills (sift-digest, daily-briefing) → pushed to VPS |
| `scripts/` | Deploy scripts, classifier, model-swap, automation |
| `decisions/` | ADRs (001–015): sandbox, email, models, plugins, automation |
| `setup/` | Configuration docs, [architecture](setup/architecture.md), [workspace files guide](setup/workspace-files.md), provider setup cheatsheet |
| `hosting/` | VPS comparison (decided: DigitalOcean), networking & DNS |
| `security/` | Hardening checklist, data privacy |
| `notes/` | Raw thinking and brain dumps |

## TODO

See [`TODO.md`](TODO.md) for the full, trackable task list.
