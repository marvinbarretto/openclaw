# Configuration

## Current state (2026-02-16)

- **AI Provider:** OpenRouter (primary), Anthropic (backup)
- **Model:** `openrouter/stepfun/step-3.5-flash:free` (free tier, 256K context) — switched back from Claude Sonnet after bootstrapping
- **Telegram:** Connected, paired, working (`@fourfold_openclaw_bot` / "Jimbo")
- **Dashboard:** `https://167.99.206.214`
- **Gateway token:** `94e12e952cbf5342c1ebcdf4a6faa76812ba0f21fd04ea793d6ff2f41233afe9`

## Telegram Bot

1. Messaged [@BotFather](https://t.me/BotFather) on Telegram
2. `/newbot` — created bot named "Jimbo" (`@fourfold_openclaw_bot`)
3. Copied the bot token
4. Set token in `/opt/openclaw.env` as `TELEGRAM_BOT_TOKEN`
5. Enabled in `/home/openclaw/.openclaw/openclaw.json`
6. Paired via: `/opt/openclaw-cli.sh pairing approve telegram NAREBK6S`

## Environment file: `/opt/openclaw.env`

Key variables:
```env
TELEGRAM_BOT_TOKEN=<bot-token>
ANTHROPIC_API_KEY=<api-key>
OPENROUTER_API_KEY=<api-key>       # configured
```

## Config file: `/home/openclaw/.openclaw/openclaw.json`

This is where plugins/channels are enabled/disabled. Key sections:
- `telegram.enabled` — must be `true`
- Agent model selection
- Skills/plugins

## AI Provider Strategy (from ADR-004)

| Tier | Provider | Model | Use for | Cost |
|---|---|---|---|---|
| Cheap cloud (daily driver) | OpenRouter | Gemini Flash | Telegram bot, async tasks | Pennies |
| Quality cloud (when needed) | Anthropic | Claude Haiku/Sonnet | Complex tasks, human-triggered | £25/mo cap |
| Local (bulk work) | Ollama on laptop | Qwen 2.5 7B / Coder 14B | Email triage, coding experiments | Free |

**TODO:**
- [x] ~~Set up OpenRouter as primary provider~~ (done 2026-02-16)
- [x] ~~Switch default model from Claude Opus to something cheaper~~ (done — using free model)
- [ ] Set up Tailscale tunnel for laptop Ollama → VPS
- [ ] Write model-swap helper script (see ADR-005)

## Ollama (local — MacBook Air)

Installed and tested:
```bash
ollama list
# qwen2.5:7b          4.7 GB   — Reader (classification, triage)
# qwen2.5-coder:14b   9.0 GB   — Actor (coding tasks)
```

Smoke tests passed:
- `qwen2.5:7b` — email classification → correct JSON output
- `qwen2.5-coder:14b` — TypeScript function generation → clean, correct code

## API Keys

| Key | Where | Purpose | Created |
|---|---|---|---|
| Anthropic `openclaw-vps` | VPS `/opt/openclaw.env` | LLM for VPS agent | 2026-02-16 |
| Telegram bot token | VPS `/opt/openclaw.env` | Telegram channel | 2026-02-16 |
| OpenRouter `openclaw-vps` | VPS `/opt/openclaw.env` | Free/cheap LLM for daily use | 2026-02-16 |
| GitHub fine-grained `openclaw-readonly` | VPS sandbox `docker.env` as `GH_TOKEN` | Read-only access to LocalShout, Spoons, Pomodoro (Zone 2) | 2026-02-16, expires ~60 days |
| GitHub fine-grained `jimbo-vps` | VPS sandbox `docker.env` as `JIMBO_GH_TOKEN` | Read+write access to `jimbo-workspace` only | 2026-02-17, expires ~90 days |

## GitHub Skill (sandbox access)

The GitHub skill lets Jimbo read repos via `gh` CLI inside the Docker sandbox.

**Current state (2026-02-17):** Enabled during Claude Sonnet bootstrapping phase.

**What was needed to make it work:**
1. `gh` CLI installed into `/home/openclaw/homebrew/bin/gh` (bind-mounted into sandbox)
2. `GH_TOKEN` set in `agents.defaults.sandbox.docker.env` in `openclaw.json` (NOT just in `/opt/openclaw.env`)
3. CA certificates mounted: `/etc/ssl/certs:/etc/ssl/certs:ro` (sandbox has no certs by default)
4. Container killed and service restarted for changes to take effect

**Before switching to free model:** Disable GitHub skill by removing `GH_TOKEN` from sandbox env. See ADR-006.

## Notes

- Keep a local backup of env vars (encrypted, e.g. in 1Password)
- Model switched to `openrouter/stepfun/step-3.5-flash:free` — zero cost
- See `decisions/005-openrouter-models.md` for full model comparison and upgrade path
- Dedicated Anthropic API key (`openclaw-vps`) means it can be revoked independently
- See `decisions/006-github-skill-lifecycle.md` for when to enable/disable GitHub access
