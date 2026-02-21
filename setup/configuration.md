# Configuration

## Current state (2026-02-20)

- **AI Providers:** Google AI (daily), OpenRouter (free/coding), Anthropic (premium)
- **Model:** `google/gemini-2.5-flash` (direct Google AI, ~$0.78/month) — upgraded from free tier (ADR-015)
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
OPENROUTER_API_KEY=<api-key>
GOOGLE_AI_API_KEY=<api-key>        # added 2026-02-20
GOOGLE_CALENDAR_CLIENT_ID=<id>     # added by calendar-setup.sh
GOOGLE_CALENDAR_CLIENT_SECRET=<secret>
GOOGLE_CALENDAR_REFRESH_TOKEN=<token>
```

## Config file: `/home/openclaw/.openclaw/openclaw.json`

This is where plugins/channels are enabled/disabled. Key sections:
- `telegram.enabled` — must be `true`
- Agent model selection
- Skills/plugins

## AI Provider Strategy (from ADR-004, updated ADR-015)

| Tier | Provider | Model | Use for | Cost |
|---|---|---|---|---|
| Daily driver | Google AI (direct) | Gemini 2.5 Flash | Telegram bot, briefings | ~$0.78/mo |
| Free fallback | OpenRouter | stepfun/step-3.5-flash:free | Testing, non-critical | $0 |
| Quality cloud | Anthropic | Claude Haiku/Sonnet | Complex tasks | £25/mo cap |
| Local (bulk work) | Ollama on laptop | Qwen 2.5 Coder 14B | Email triage | Free |

**Model switching:** `./scripts/model-swap.sh {free|cheap|daily|coding|haiku|claude|opus|status}`

**TODO:**
- [x] ~~Set up OpenRouter as primary provider~~ (done 2026-02-16)
- [x] ~~Switch default model from Claude Opus to something cheaper~~ (done — using free model)
- [x] ~~Write model-swap helper script~~ (done 2026-02-20, see ADR-005)
- [x] ~~Upgrade to paid model for daily briefings~~ (done 2026-02-20, Gemini 2.5 Flash, ADR-015)
- [ ] Set up Tailscale tunnel for laptop Ollama → VPS

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

## Adding a New LLM Provider (cheatsheet)

Follow this exact process. The `openclaw.json` schema is strict and will crash the service if anything is missing.

### 1. Add the API key to `/opt/openclaw.env`
```bash
ssh jimbo
echo 'NEW_PROVIDER_API_KEY=sk-...' >> /opt/openclaw.env
```

### 2. Add the provider block to `openclaw.json`

Edit `/home/openclaw/.openclaw/openclaw.json`. Every field below is **required** — omitting any one will crash OpenClaw:

```json
"models": {
  "providers": {
    "provider-name": {
      "baseUrl": "https://api.example.com/v1",
      "apiKey": "${NEW_PROVIDER_API_KEY}",
      "api": "openai-completions",
      "models": [
        {
          "id": "model-id-as-provider-knows-it",
          "name": "Display Name",
          "reasoning": false,
          "input": ["text", "image"],
          "cost": { "input": 0.3, "output": 2.5, "cacheRead": 0, "cacheWrite": 0 },
          "contextWindow": 128000,
          "maxTokens": 8192
        }
      ]
    }
  }
}
```

**Valid `api` types:** `openai-completions`, `openai-responses`, `anthropic-messages`, `google-generative-ai`

### 3. Set the model as primary

Either edit `openclaw.json` directly (`agents.defaults.model.primary`) or use:
```bash
./scripts/model-swap.sh <tier>
```

### 4. Restart
```bash
ssh jimbo "systemctl daemon-reload && systemctl restart openclaw"
```

### 5. Verify
```bash
ssh jimbo "journalctl -u openclaw -n 15 --no-pager"
```
Look for `[gateway] agent model: provider/model-id` and no config errors.

### Known gotchas

| Gotcha | What happens | Fix |
|--------|-------------|-----|
| Missing `baseUrl` | Config validation fails, service crash-loops | Always include the full base URL with API version path |
| `models` as string array | Config validation fails (`expected object, received string`) | Each model must be a full object with all fields |
| Missing env var | `MissingEnvVarError`, service starts but can't handle messages | Add to `/opt/openclaw.env`, then `systemctl daemon-reload && systemctl restart openclaw` |
| Google AI without `/v1beta` | 404 on every API call | baseUrl must be `https://generativelanguage.googleapis.com/v1beta` |
| Added env var but didn't restart | Service doesn't pick up new vars | `systemctl daemon-reload && systemctl restart openclaw` |
| `agents.defaults.thinking` | Not a valid config key — crashes service | Thinking level is per-session only (`--thinking` CLI flag), no persistent config in v2026.2.12 |
| Gemini `reasoning: true` | Thinking tokens leak into Telegram output | No fix in OpenClaw yet. SOUL.md "never show working" helps partially. Quality is better with reasoning on. See ADR-015. |

### Current working provider configs (2026-02-20)

**Google AI (daily driver):**
- baseUrl: `https://generativelanguage.googleapis.com/v1beta`
- api: `google-generative-ai`
- env var: `GOOGLE_AI_API_KEY`

**OpenRouter (free/coding tiers):**
- Built-in provider, no explicit config needed
- env var: `OPENROUTER_API_KEY`

**Anthropic (premium):**
- Built-in provider, no explicit config needed
- env var: `ANTHROPIC_API_KEY`

## Sandbox Environment Variables

These are set in both the Dockerfile (`ENV`) and `openclaw.json` (`agents.defaults.sandbox.docker.env`). Both places matter — the Dockerfile bakes them into the image, and openclaw.json ensures they persist if the image is rebuilt without them.

| Variable | Value | Why |
|----------|-------|-----|
| `HOME` | `/workspace` | Root filesystem is read-only. Tools write config/cache to `$HOME`. Without this, any tool that touches `~/.config/`, `~/.cache/`, `~/.npm/` etc. crashes with EROFS. |
| `XDG_CONFIG_HOME` | `/workspace/.config` | XDG-compliant tools (Astro telemetry, etc.) write config here. Redirects to writable mount. |
| `npm_config_cache` | `/workspace/.npm-cache` | npm's package cache directory. Must be on writable mount. |
| `npm_config_unsafe_perm` | `true` | Suppresses fchown warnings. CHOWN capability is dropped so npm can't change file ownership — this tells it not to try. Packages install correctly either way. |
| `GIT_CONFIG_GLOBAL` | `/workspace/.gitconfig` | Git config can't live at `/root/.gitconfig` (read-only). Points git to the workspace copy which has `safe.directory = /workspace`. |
| `JIMBO_GH_TOKEN` | `${JIMBO_GH_TOKEN}` | GitHub PAT for jimbo-workspace repo access. Interpolated from `/opt/openclaw.env`. |
| `GOOGLE_CALENDAR_CLIENT_ID` | `${GOOGLE_CALENDAR_CLIENT_ID}` | Google Calendar OAuth client ID. Interpolated from `/opt/openclaw.env`. |
| `GOOGLE_CALENDAR_CLIENT_SECRET` | `${GOOGLE_CALENDAR_CLIENT_SECRET}` | Google Calendar OAuth client secret. Interpolated from `/opt/openclaw.env`. |
| `GOOGLE_CALENDAR_REFRESH_TOKEN` | `${GOOGLE_CALENDAR_REFRESH_TOKEN}` | Google Calendar OAuth refresh token. Interpolated from `/opt/openclaw.env`. |

**Key insight (ADR-016):** The original "uid mismatch causes fchown errors" diagnosis was misleading. The fchown warnings were always harmless. The real blocker was tools crashing when trying to write to the read-only root filesystem at `$HOME=/root/`. Setting `HOME=/workspace` fixes everything.

## API Keys

| Key | Where | Purpose | Created |
|---|---|---|---|
| Anthropic `openclaw-vps` | VPS `/opt/openclaw.env` | LLM for VPS agent (premium tier) | 2026-02-16 |
| Telegram bot token | VPS `/opt/openclaw.env` | Telegram channel | 2026-02-16 |
| OpenRouter `openclaw-vps` | VPS `/opt/openclaw.env` | Free/cheap LLM tiers | 2026-02-16 |
| Google AI `GOOGLE_AI_API_KEY` | VPS `/opt/openclaw.env` | Daily driver (Gemini 2.5 Flash) | 2026-02-20 |
| Google Calendar OAuth creds | VPS `/opt/openclaw.env` | Calendar API (Jimbo's account) | 2026-02-20 |
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

## MCP Servers (ADR-017 — Rejected)

Native MCP support is **not available** in OpenClaw v2026.2.12. The `mcpServers` config key is rejected as unrecognised. Community adapter plugins exist but violate ADR-008 (no community plugins).

**Revisit when:** OpenClaw merges PR #21530 (native MCP client support) and we upgrade.

See `decisions/017-mcp-server-integration.md` for full investigation and lessons learned.

## Notes

- Keep a local backup of env vars (encrypted, e.g. in 1Password)
- Model switched to `google/gemini-2.5-flash` (direct Google AI) — ~$0.78/month
- See `decisions/005-openrouter-models.md` for full model comparison and upgrade path
- See `decisions/015-model-upgrade-gemini-direct.md` for setup gotchas and working config
- Dedicated Anthropic API key (`openclaw-vps`) means it can be revoked independently
- See `decisions/006-github-skill-lifecycle.md` for when to enable/disable GitHub access
