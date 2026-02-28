# ADR-030: Failure Alerting via Telegram

## Status

Accepted

## Context

Jimbo's daily pipeline (06:00 email fetch, 07:00 morning briefing) can fail silently. Errors go to stderr and log files nobody watches. On 2026-02-28 the briefing cron failed and Marvin only found out when he asked at 08:25. There is no proactive alerting mechanism.

The alerting must work independently of Jimbo/OpenClaw — if the agent is down, the alerting must still function. It must also be stdlib-only Python (consistent with all sandbox scripts) and use the existing Telegram bot token.

## Decision

Two new standalone scripts plus cron wrappers:

**`alert.py`** — Sends a message via Telegram Bot API (`urllib.request` POST). CLI: `python3 alert.py "message"`. Exits silently if env vars missing (no cascading failures).

**`alert-check.py`** — Subcommands `digest` and `briefing`. Checks pipeline health and sends positive heartbeat when all is well, or failure alert when something is wrong.

- `digest`: Checks `email-digest.json` exists and `generated_at` < 25h old
- `briefing`: Queries `experiment-tracker.db` for runs with today's date

**Cron wrappers**: 06:00 email fetch wrapped with `|| alert.py "FAILED"`. Two new cron entries at 06:15 and 07:30 run `alert-check.py` for positive heartbeat.

**Worker try/except**: `email_triage.py` and `newsletter_reader.py` wrap `main()` in try/except that calls `alert.py` before re-raising.

**Env vars**: `TELEGRAM_BOT_TOKEN` (already exists) and `TELEGRAM_CHAT_ID` (new, added to `/opt/openclaw.env` and `openclaw.json` docker.env).

## Consequences

**Positive:**
- Works independently of Jimbo/OpenClaw — pure Python + Telegram Bot API
- Stdlib only, follows all project conventions
- Positive heartbeat means silence itself is a signal (broken checker = no message = investigate)
- Minimal blast radius — exits silently if env vars missing

**Negative:**
- Requires one-time `TELEGRAM_CHAT_ID` setup (send message to bot, read getUpdates)
- Briefing check at 07:30 is heuristic — could false-alarm if briefing runs late
- Does not cover Docker/host-level failures (future work)
- Does not cover OpenClaw service crashes (systemd can email but not Telegram natively)
