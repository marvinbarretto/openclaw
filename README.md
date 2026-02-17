# OpenClaw

Personal AI assistant powered by [OpenClaw](https://github.com/openclaw/openclaw), self-hosted on a VPS with Telegram as the primary messaging channel.

## Current Status (2026-02-17)

- **VPS:** DigitalOcean $12/mo, London, IP `167.99.206.214` — RUNNING
- **OpenClaw:** v2026.2.12, dashboard at `https://167.99.206.214`
- **Telegram:** Connected via `@fourfold_openclaw_bot` ("Jimbo") — WORKING
- **AI Provider:** OpenRouter free (`stepfun/step-3.5-flash:free`) — bootstrapping complete
- **Sandbox:** Custom Docker image with Python 3.11, Node 18, git — WORKING
- **Local models:** Ollama installed — `qwen2.5:7b` + `qwen2.5-coder:14b` — TESTED
- **Test monorepo:** https://github.com/marvinbarretto/openclaw-test-monorepo — PUSHED
- **Jimbo's GitHub:** https://github.com/marvinbarretto-labs — separate account for agent work
- **Jimbo's workspace:** `jimbo-workspace` repo — Jimbo can autonomously write, commit, and push
- **First project:** "Sift" — email digest/intelligence system — Jimbo writing BDD specs and prototyping

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

## This Folder

| Folder | Purpose |
|---|---|
| `hosting/` | VPS comparison (decided: DigitalOcean), networking & DNS |
| `setup/` | Installation, configuration, [architecture](setup/architecture.md), and [workspace files guide](setup/workspace-files.md) |
| `security/` | Hardening checklist, data privacy |
| `decisions/` | ADRs: sandbox architecture, email triage, prompt injection, model strategy |
| `notes/` | Raw thinking and brain dumps |

## TODO

See [`TODO.md`](TODO.md) for the full, trackable task list.
