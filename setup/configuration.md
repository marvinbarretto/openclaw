# Configuration

## Current state (2026-03-02)

- **OpenClaw version:** v2026.3.1 (upgraded from v2026.2.12)
- **AI Providers:** Google AI (daily), OpenRouter (free/coding), Anthropic (premium)
- **Model:** `anthropic/claude-haiku-4.5` (conductor, ADR-036), auto-switches via cron (Haiku 06:45, Flash 07:30 UTC)
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
TELEGRAM_CHAT_ID=<chat-id>         # added 2026-02-28 (ADR-030, failure alerting)
ANTHROPIC_API_KEY=<api-key>
OPENROUTER_API_KEY=<api-key>
GOOGLE_AI_API_KEY=<api-key>        # added 2026-02-20
GOOGLE_CALENDAR_CLIENT_ID=<id>     # added by calendar-setup.sh
GOOGLE_CALENDAR_CLIENT_SECRET=<secret>
GOOGLE_CALENDAR_REFRESH_TOKEN=<token>
OPENROUTER_API_KEY=<api-key>       # also passed to sandbox for balance checks (ADR-031)
TWILIO_ACCOUNT_SID=AC...           # Twilio voice API for critical failure phone calls (ADR-043)
TWILIO_AUTH_TOKEN=<auth-token>     # Twilio auth token
TWILIO_FROM_NUMBER=+44...         # Twilio UK number (purchased)
TWILIO_TO_NUMBER=+44...           # Marvin's mobile number
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
| `TELEGRAM_BOT_TOKEN` | `${TELEGRAM_BOT_TOKEN}` | Telegram Bot API token. Used by `alert.py` for failure alerts. Interpolated from `/opt/openclaw.env`. |
| `TELEGRAM_CHAT_ID` | `${TELEGRAM_CHAT_ID}` | Telegram chat ID for alerts. Used by `alert.py`. Interpolated from `/opt/openclaw.env`. |
| `OPENROUTER_API_KEY` | `${OPENROUTER_API_KEY}` | OpenRouter API key for balance/usage checks. Used by `openrouter-usage.py` and `alert-check.py credits`. Interpolated from `/opt/openclaw.env`. |
| `TWILIO_ACCOUNT_SID` | `${TWILIO_ACCOUNT_SID}` | Twilio Account SID for voice API. Used by `alert-call.py`. Interpolated from `/opt/openclaw.env`. |
| `TWILIO_AUTH_TOKEN` | `${TWILIO_AUTH_TOKEN}` | Twilio Auth Token for voice API. Used by `alert-call.py`. Interpolated from `/opt/openclaw.env`. |
| `TWILIO_FROM_NUMBER` | `${TWILIO_FROM_NUMBER}` | Twilio UK phone number (purchased). Used by `alert-call.py`. Interpolated from `/opt/openclaw.env`. |
| `TWILIO_TO_NUMBER` | `${TWILIO_TO_NUMBER}` | Marvin's mobile number for critical alerts. Used by `alert-call.py`. Interpolated from `/opt/openclaw.env`. |

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
| Twilio Account SID + Auth Token | VPS `/opt/openclaw.env` | Voice API for critical failure phone calls (ADR-043) | 2026-03-12 |

## GitHub Skill (sandbox access)

The GitHub skill lets Jimbo read repos via `gh` CLI inside the Docker sandbox.

**Current state (2026-02-17):** Enabled during Claude Sonnet bootstrapping phase.

**What was needed to make it work:**
1. `gh` CLI installed into `/home/openclaw/homebrew/bin/gh` (bind-mounted into sandbox)
2. `GH_TOKEN` set in `agents.defaults.sandbox.docker.env` in `openclaw.json` (NOT just in `/opt/openclaw.env`)
3. CA certificates mounted: `/etc/ssl/certs:/etc/ssl/certs:ro` (sandbox has no certs by default)
4. Container killed and service restarted for changes to take effect

**Before switching to free model:** Disable GitHub skill by removing `GH_TOKEN` from sandbox env. See ADR-006.

## OpenClaw v2026.3.1 Native Features

Upgraded 2026-03-02. These features were not available in v2026.2.12.

### Native cron (`openclaw cron`)

Gateway-managed scheduled jobs. Persistent, retry-aware, integrated with sessions.

```bash
# Key commands (run as openclaw user with env vars)
openclaw cron list                    # list all jobs
openclaw cron add                     # add a new job (interactive)
openclaw cron run <job-id>            # trigger manually for debugging
openclaw cron runs                    # show run history
openclaw cron status                  # scheduler status
openclaw cron disable <job-id>        # pause a job
```

**Current jobs:** Morning briefing (07:00 Europe/London, daily). ID: `24798750-40b4-4fc6-9640-6a1d8b81e6d1`.

**When to use native cron vs VPS crontab:**
- **Native cron:** Tasks that need an LLM session (briefings, conversations, anything that calls skills)
- **VPS crontab:** Pure scripts that don't need OpenClaw (email fetch, task scoring, model swap, accountability report, status checks)

### Health endpoint (`openclaw health`)

Shows channel status, agent sessions, heartbeat interval. Use for monitoring.

```bash
openclaw health    # shows Telegram status, active agents, session store
```

Output includes: channel health (Telegram OK/down + latency), agent list, heartbeat interval, recent sessions.

### Memory system (`openclaw memory`, plugin: `memory-core`)

File-backed memory with FTS5 keyword search. Auto-loaded on upgrade.

```bash
openclaw memory status                # index stats, provider, store path
openclaw memory index --force         # full reindex
openclaw memory search --query "..."  # search indexed memory
```

**Architecture:**
- Store: `~/.openclaw/memory/main.sqlite`
- Embedding: `gemini-embedding-001` (auto-detected)
- Sources: memory files in `~/.openclaw/workspace`
- Tools exposed to Jimbo: `memory_search`, `memory_get`
- Vector search (sqlite-vec) + FTS5 keyword search

**Current state (2026-03-02):** Loaded but empty (0 files indexed). Needs memory files in `~/.openclaw/workspace` to be useful.

### Secrets management (`openclaw secrets`)

Runtime secret resolution with audit trail.

```bash
openclaw secrets audit                # find plaintext secrets, unresolved refs, drift
openclaw secrets configure            # interactive setup (provider mapping + preflight)
openclaw secrets reload               # re-resolve refs and swap runtime snapshot
openclaw secrets apply                # apply a previously generated plan
```

**Current state (2026-03-02):** Audit shows 1 plaintext key (Google AI apiKey in openclaw.json). Other keys use `${ENV_VAR}` interpolation which is fine. Low priority to migrate — existing approach works.

### Plugins (`openclaw plugins`)

Stock plugin management. 38 available, 5 loaded.

```bash
openclaw plugins list                 # all plugins with status
openclaw plugins enable <id>          # enable a plugin
openclaw plugins disable <id>         # disable a plugin
openclaw plugins info <id>            # show details
openclaw plugins doctor               # report load issues
```

**Loaded plugins (2026-03-02):** device-pair, memory-core, phone-control, talk-voice, telegram.

**Interesting disabled plugins:**
- `llm-task` — Generic JSON-only LLM tool for structured tasks (potential sub-agent alternative)
- `lobster` — Typed workflow tool with resumable approvals
- `diffs` — Read-only diff viewer for agents

## MCP Servers (ADR-017 — Status TBD after upgrade)

Still blocked in v2026.3.1. No `mcp` CLI command, no `mcpServers` config key. The `llm-task` and `lobster` stock plugins may provide similar functionality natively.

See `decisions/017-mcp-server-integration.md` for original investigation.

## Notes

- Keep a local backup of env vars (encrypted, e.g. in 1Password)
- Model switched to `google/gemini-2.5-flash` (direct Google AI) — ~$0.78/month
- See `decisions/005-openrouter-models.md` for full model comparison and upgrade path
- See `decisions/015-model-upgrade-gemini-direct.md` for setup gotchas and working config
- Dedicated Anthropic API key (`openclaw-vps`) means it can be revoked independently
- See `decisions/006-github-skill-lifecycle.md` for when to enable/disable GitHub access
