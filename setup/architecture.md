# Architecture — What Runs Where

## The Mental Model

```
Your Laptop (MacBook Air 24GB)
  ├── Claude Code (this CLI — helps you manage everything)
  ├── Ollama (local LLM — qwen2.5:7b, qwen2.5-coder:14b)
  ├── SSH config: "ssh jimbo" → VPS
  └── openclaw/ repo (notes, decisions, docs — this folder)

VPS (DigitalOcean, Ubuntu 24.04, 2GB RAM, London)
  ├── OpenClaw service (the gateway — Node 22, runs as openclaw user)
  │     ├── Listens for Telegram messages
  │     ├── Calls Claude/OpenRouter APIs
  │     ├── Reads config from /home/openclaw/.openclaw/openclaw.json
  │     ├── Reads API keys from /opt/openclaw.env
  │     └── When Jimbo needs to run code, it executes inside ↓
  │
  ├── Docker container ("openclaw-sbx-agent-main-...")
  │     ├── Jimbo's sandbox — this is where Jimbo "lives"
  │     ├── Custom image: bookworm-slim + Python 3.11, Node 18, git
  │     ├── /workspace — Jimbo's brain files (SOUL.md, USER.md, etc.)
  │     ├── /home/openclaw/homebrew — mounted read-only (gh CLI)
  │     ├── /etc/ssl/certs — mounted read-only (CA certs for HTTPS)
  │     ├── Capabilities dropped, no-new-privileges — security hardened
  │     ├── Shell redirection to /workspace blocked (use write tool instead)
  │     └── This is where Jimbo runs commands when you ask it to
  │
  └── Host tools (not inside container)
        ├── Docker daemon
        ├── Node 22 (system — used by OpenClaw service)
        ├── Node 25 + Python 3.14 (homebrew — on host, NOT used by sandbox)
        ├── Caddy (reverse proxy, auto TLS)
        └── systemd (manages openclaw.service)
```

## Two separate things on the VPS

1. **OpenClaw service** — the brain/gateway. Handles Telegram, calls LLMs, manages sessions. Runs directly on the host as the `openclaw` user.
2. **Docker container** — the sandbox. Where Jimbo executes code. Isolated, restricted, disposable.

These are independent. The service can crash and restart without affecting the container, and vice versa.

## How to see what Jimbo sees

```bash
# SSH into VPS
ssh jimbo

# Step into Jimbo's container
docker exec -it $(docker ps -q --filter name=openclaw-sbx) bash

# Now you're in Jimbo's world — same view, same tools, same restrictions
env | grep GH          # Check tokens
python3 --version      # Check runtimes
ls /workspace/         # See brain files
```

## Config files that matter

| File | Where | Who reads it | Purpose |
|---|---|---|---|
| `/opt/openclaw.env` | VPS host | OpenClaw service | API keys, bot tokens |
| `/home/openclaw/.openclaw/openclaw.json` | VPS host | OpenClaw service | Model, sandbox config, plugins |
| `/root/.openclaw/openclaw.json` | VPS host | `openclaw config set` (root) | Layered config — avoid, edit service config directly |
| `/etc/systemd/system/openclaw.service` | VPS host | systemd | Service definition, PATH, env file |
| `/workspace/*.md` | Inside container | Jimbo | Brain files (SOUL, IDENTITY, USER, MEMORY) |

## Key gotchas

- **Layered config:** `openclaw config set` writes to root's config, not the service user's. Always edit `/home/openclaw/.openclaw/openclaw.json` directly.
- **Stale containers:** Config changes don't affect running containers. Must `docker rm -f` and restart the service.
- **PATH order:** systemd service PATH must have `/usr/bin` before `/home/openclaw/homebrew/bin` — otherwise homebrew Node overrides system Node and crashes Telegram.
- **Env vars:** `/opt/openclaw.env` is mounted into the container as a file, but that does NOT make the vars available in the environment. Use `docker.env` in openclaw.json instead.
- **`openclaw logs --follow`:** Uses root's config (missing gateway token). Use `journalctl -u openclaw -f` instead.
