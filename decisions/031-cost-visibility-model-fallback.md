# ADR-031: Cost Visibility, Model Fallback & Identification

## Status

Accepted

## Context

Jimbo burned $30.1 on OpenRouter in one month — almost entirely from heartbeats. OpenClaw's built-in heartbeat (every 30 min, 07:00-01:00) sends the full conversation context (~100K tokens) to whichever model is set as `primary` in openclaw.json. When that was Haiku via OpenRouter ($0.80/M input), each heartbeat cost ~$0.12 = ~$4.30/day.

Our custom workers (email_triage, newsletter_reader) have their own model configs with fallback — they're fine. The problem is OpenClaw's native model usage has no fallback, no budget awareness, and no visibility.

OpenRouter stays — it's useful for model variety, free models, and easy switching. But we need:
1. Visibility into what's costing what
2. Alerts when credits run low (manual switching, not auto-downgrade)
3. Model identification in responses so Marvin knows what he's talking to

## Decision

### 1. Reduce heartbeat frequency
Change openclaw.json `agents.defaults.heartbeat.every` from `"30m"` to `"2h"`. Cuts heartbeats from 36/day to 9/day — immediate ~75% reduction.

### 2. OpenRouter usage checker
New script `workspace/openrouter-usage.py` — stdlib Python, calls OpenRouter `/api/v1/auth/key`:
- `balance` — credit balance + warnings if low
- `usage --days N` — usage summary (totals; per-model breakdown requires dashboard)

### 3. Credit alerts via alert-check.py
New `credits` subcommand in `alert-check.py`:
- Checks OpenRouter balance via API
- Below $1: sends Telegram alert with balance + suggested switch command
- Healthy: positive heartbeat with balance
- Runs every 6 hours via crontab

### 4. Balance in heartbeat + briefing
- HEARTBEAT.md: check balance every heartbeat, warn if below $2, alert if below $0.50
- daily-briefing SKILL.md: include balance if below $5 or burn rate exceeds $1/day

### 5. Model identification
SOUL.md output rule: tag first message of each session with [Flash], [Haiku], [Sonnet], [Opus], [Free]. Zero code changes — prompt instruction only.

### 6. Per-key credit limit
Set credit limit on OpenRouter API key via dashboard (e.g. $5/month). Prevents runaway spend. When limit is hit, requests return 402.

### What we chose NOT to do
- **Auto-downgrade:** Too risky. Marvin switches manually via `model-swap.sh`. Alerts give time to decide.
- **Direct Anthropic Haiku:** No cost benefit right now vs OpenRouter. Revisit if pricing changes.
- **Complex per-model routing:** Workers already handle this. OpenClaw's single-model design means the primary model handles everything native.

## Consequences

**Easier:**
- Marvin sees spend before it becomes a problem
- Credit exhaustion is caught proactively (6-hourly checks + every heartbeat)
- Model identification removes guesswork about which model is responding
- Heartbeat frequency reduction immediately saves ~$3/day at Haiku rates

**Harder:**
- One more env var to manage (OPENROUTER_API_KEY in sandbox docker.env)
- One more crontab entry (6-hourly credit check)
- OpenRouter API only provides totals, not per-model breakdown — dashboard still needed for detail

**New files:**
- `workspace/openrouter-usage.py` — balance/usage checker
- `decisions/031-cost-visibility-model-fallback.md` — this ADR

**Modified files:**
- `workspace/alert-check.py` — `credits` subcommand
- `workspace/SOUL.md` — model identification tag
- `workspace/HEARTBEAT.md` — balance check instruction
- `skills/daily-briefing/SKILL.md` — balance in briefing

**VPS manual changes:**
- openclaw.json: heartbeat `"30m"` → `"2h"`
- openclaw.json docker.env: add `OPENROUTER_API_KEY`
- openrouter.ai: set per-key credit limit
- Crontab: add 6-hourly `alert-check.py credits`
