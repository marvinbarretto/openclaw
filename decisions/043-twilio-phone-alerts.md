# ADR-043: Twilio Phone Call Alerts for Critical Failures

## Status

Accepted

## Context

Jimbo sends Telegram text alerts for pipeline status, health checks, and accountability reports (ADR-030). But Telegram notifications can be missed — especially overnight or when the phone is on silent. For truly critical failures (entire day broken, service down, budget blown), we need an escalation path that actually rings the phone.

Twilio's REST API can make voice calls with TTS using stdlib `urllib` — no SDK, no pip dependencies. Cost is minimal: ~$1/mo for a UK number + ~$0.01/min per call (expect <5 calls/month).

## Decision

Add a phone call escalation tier using Twilio voice API:

### Escalation tiers

| Tier | Channel | Triggers |
|------|---------|----------|
| Info | Telegram | Pipeline status, positive heartbeat, daily accountability summary |
| Warning | Telegram | Individual step failures (email fetch, calendar error) |
| Critical | Telegram + Phone call | Both briefings failed, gateway down, budget exceeded |

### Implementation

- **`alert-call.py`** — mirrors `alert.py` pattern. Stdlib only, exits silently if env vars missing.
- **60-minute cooldown** via `/tmp/.alert-call-last` timestamp file. Prevents repeated calls if a checker runs in a loop.
- **TwiML inline** — `<Response><Say voice="alice">{message}</Say></Response>`. No hosted TwiML bins needed.
- **Basic Auth** via `urllib.request` — Account SID + Auth Token, base64-encoded.

### Trigger conditions

| Trigger | Detected by | When |
|---------|------------|------|
| Both briefing pipelines failed | `accountability-check.py` | 20:00 UTC daily |
| Gateway/service down | `alert-check.py openclaw` | On-demand |
| Budget exceeded | `alert-check.py credits` | On-demand |

### Env vars

```
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_FROM_NUMBER=+44...
TWILIO_TO_NUMBER=+44...
```

Added to `/opt/openclaw.env` and passed to sandbox via `openclaw.json` docker.env (same `${VAR}` interpolation as Telegram vars).

## Consequences

- **Better:** Critical failures now ring the phone — can't be missed even on silent/DND (most phones let repeated calls through).
- **Better:** Graceful degradation — if Twilio env vars are missing, scripts exit silently. No cascading failures.
- **Better:** Cooldown prevents alert storms.
- **Trade-off:** ~$1/mo additional cost for Twilio number + per-call charges (~$0.01/min).
- **Trade-off:** Twilio trial accounts require verified recipient numbers. Must verify Marvin's mobile before first use.
- **Harder:** One more set of credentials to manage and rotate.
