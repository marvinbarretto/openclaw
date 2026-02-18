# OpenClaw

Personal AI assistant powered by [OpenClaw](https://github.com/openclaw/openclaw), self-hosted on a VPS with Telegram as the primary messaging channel.

## Current Status (2026-02-18)

- **VPS:** DigitalOcean $12/mo, London, IP `167.99.206.214` — RUNNING
- **OpenClaw:** v2026.2.12, dashboard at `https://167.99.206.214`
- **Telegram:** Connected via `@fourfold_openclaw_bot` ("Jimbo") — WORKING
- **AI Provider:** OpenRouter free (`stepfun/step-3.5-flash:free`) — bootstrapping complete
- **Sandbox:** Custom Docker image with Python 3.11, Node 18, git — WORKING
- **Local models:** Ollama installed — `qwen2.5:7b` + `qwen2.5-coder:14b` — TESTED
- **Jimbo's GitHub:** https://github.com/marvinbarretto-labs — separate account for agent work
- **Jimbo's workspace:** `jimbo-workspace` repo — Jimbo can autonomously write, commit, and push
- **Sift pipeline:** mbsync → sift-classify.py (Ollama) → email-digest.json → sift-push.sh → VPS — END-TO-END WORKING
- **Custom skills:** `sift-digest` + `daily-briefing` deployed to VPS — WORKING
- **Gmail sync:** mbsync configured, 28,799 emails synced to local Maildir — WORKING

## Stack

- **Runtime:** OpenClaw 2026.2.12 on Ubuntu 24.04 (DigitalOcean 1-Click)
- **Messaging:** Telegram Bot API
- **LLM (cloud):** Anthropic (backup), OpenRouter/Gemini Flash (daily driver — TODO)
- **LLM (local):** Ollama on MacBook Air 24GB (Qwen 2.5 7B + Coder 14B)
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

**Deploy to VPS:**
```bash
./scripts/skills-push.sh           # push skills to Jimbo
./scripts/skills-push.sh --dry-run  # preview without changes
```

Skills are picked up on Jimbo's next session (no restart needed).

**Sift pipeline (email → Jimbo):**
```bash
# Manual run
mbsync -a                                                    # sync Gmail → local Maildir
python3 scripts/sift-classify.py --input ~/Mail/gmail/INBOX  # classify recent emails
./scripts/sift-push.sh                                       # push digest to Jimbo

# Automated (see ADR-010)
# 06:00 launchd (laptop): sift-cron.sh → mbsync + classify + push
# 07:00 OpenClaw cron (VPS): Jimbo sends morning briefing via Telegram
# ~30m  Heartbeat (VPS): Jimbo checks for fresh/stale digest

# Backlog processing (see ADR-009)
python3 scripts/sift-classify.py --input ~/Mail/gmail/INBOX --all --limit 200
```

**Third-party skills:** We do not install community skills from ClawHub. See [ADR-008](decisions/008-plugin-adoption-policy.md) for our adoption policy.

## This Folder

| Folder | Purpose |
|---|---|
| `hosting/` | VPS comparison (decided: DigitalOcean), networking & DNS |
| `setup/` | Installation, configuration, [architecture](setup/architecture.md), and [workspace files guide](setup/workspace-files.md) |
| `security/` | Hardening checklist, data privacy |
| `decisions/` | ADRs: sandbox architecture, email triage, prompt injection, model strategy |
| `skills/` | Custom OpenClaw skills for Jimbo (sift-digest, daily-briefing) |
| `notes/` | Raw thinking and brain dumps |

## TODO

See [`TODO.md`](TODO.md) for the full, trackable task list.
