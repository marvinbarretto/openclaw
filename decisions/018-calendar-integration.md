# ADR-018: Google Calendar Integration

## Status

Accepted (2026-02-21)

## Context

Jimbo had no calendar access. We wanted him to:
- **Own** his calendar — create events, invite Marvin
- **Read** Marvin's shared calendars to check for clashes
- **Include** schedule in morning briefings

ADR-017 ruled out MCP for this. Instead we built a Python stdlib-only script that runs in the sandbox and talks directly to the Google Calendar API using OAuth 2.0 credentials.

### Security model

Unlike the Sift email pipeline (laptop-only, read-only, Marvin's credentials), calendar is **bidirectional and real-time** using **Jimbo's own Google account** (`marvinbarretto.labs@gmail.com`). This is acceptable per our security model because:
- The credentials are Jimbo's, not Marvin's
- Jimbo can only create events on his own primary calendar
- No update/delete commands exist
- Marvin shares calendars with Jimbo (read-only) via standard Google Calendar sharing

## Decision

### Architecture

```
Laptop (one-time setup)
  └── calendar-auth.py  →  OAuth flow  →  data/.calendar-tokens.json
  └── calendar-setup.sh →  deploys creds + script to VPS

VPS (ongoing)
  └── /workspace/calendar-helper.py (Python 3.11, stdlib only)
      ├── list-calendars
      ├── list-events --days N [--calendar-id ID]
      ├── check-conflicts --start ISO --end ISO
      ├── create-event --summary "..." --start ISO --end ISO [--attendee email]
      └── subscribe --calendar-id ID
```

Credentials flow: `calendar-auth.py` (laptop) → `data/.calendar-tokens.json` → `calendar-setup.sh` → `/opt/openclaw.env` → `openclaw.json` docker.env interpolation → sandbox env vars.

### What we built

| File | Purpose |
|------|---------|
| `scripts/calendar-auth.py` | One-time OAuth flow (laptop). Localhost:8090 callback, saves refresh token. |
| `scripts/calendar-setup.sh` | Deploys credentials to VPS, copies helper script, prints manual config steps. |
| `workspace/calendar-helper.py` | Core API client (sandbox). Handles token refresh, caching, all subcommands. |
| `skills/calendar/SKILL.md` | Teaches Jimbo calendar behaviour, rules, and error handling. |

### What we updated

- `skills/daily-briefing/SKILL.md` — added "Today's schedule" section
- `workspace/HEARTBEAT.md` — added calendar health check (token expiry detection)
- `CAPABILITIES.md` — added Calendar section + token expiry entry
- `setup/configuration.md` — added three new env vars to docs
- `.gitignore` — added `data/.calendar-tokens.json`

## Setup cheatsheet

### Google Cloud setup (on Jimbo's Google account)

1. Create project, enable Google Calendar API
2. Create OAuth 2.0 Client ID (type: Desktop app)
3. **Publish the app** — move from "Testing" to "In production" (unverified OK). Without this, refresh tokens expire after 7 days.
4. Share Marvin's calendars with Jimbo's Google account (read-only)

### OAuth flow

```bash
python3 scripts/calendar-auth.py --client-id "ID" --client-secret "SECRET"
# Opens browser → Google consent → saves to data/.calendar-tokens.json
```

Google shows a scary "unverified app" warning — click Advanced → Go to Jimbo Calendar (unsafe).

### Subscribing to shared calendars

Sharing gives permission, but Jimbo must also **subscribe** to see calendars in his list:

```bash
# Export creds first, then:
python3 workspace/calendar-helper.py subscribe --calendar-id "calendar-id@group.calendar.google.com"
```

Custom calendars have generated IDs (find them in Google Calendar → Settings → Integrate calendar).

### Deploy to VPS

```bash
./scripts/calendar-setup.sh
# Then manually add docker.env entries to openclaw.json (printed by script)
# Then: ssh jimbo "systemctl daemon-reload && systemctl restart openclaw"
```

### Env vars (three, all in /opt/openclaw.env + openclaw.json docker.env)

```
GOOGLE_CALENDAR_CLIENT_ID
GOOGLE_CALENDAR_CLIENT_SECRET
GOOGLE_CALENDAR_REFRESH_TOKEN
```

## Consequences

- Jimbo can read 6 calendars (own + Marvin's personal, Airbnb, Birthdays, Fourfold Media, UK holidays)
- Jimbo can create events on his own calendar and invite Marvin
- Morning briefings now include today's schedule
- Heartbeat checks calendar token health
- No update/delete capability by design — safe against prompt injection

## Gotchas discovered

| Gotcha | What happened | Fix |
|--------|--------------|-----|
| Sharing ≠ subscribing | Sharing a calendar gives permission, but it doesn't appear in `list-calendars` until subscribed | Added `subscribe` command to calendar-helper.py |
| Workspace bloat → Gemini rate limits | 337MB workspace (node_modules, npm cache) caused ~950K input tokens per heartbeat, hitting Gemini's 1M TPM limit | Deleted node_modules + npm-cache (337MB → 43MB), added .gitignore to workspace |
| Free model too small | stepfun/step-3.5-flash:free context window can't fit even the trimmed workspace | Use Gemini Flash (1M context) or Haiku |
| Terminal line-wrap in env vars | Client ID got split across lines when pasting in terminal, causing "invalid_client" | Paste on one line or use the setup script |
| Google consent screen in Testing mode | Refresh tokens expire after 7 days | Publish the app (unverified is fine for single-user) |

## Lessons learned

- **Workspace size matters more than heartbeat content.** Our HEARTBEAT.md was 5 lines. The workspace was 337MB. Every heartbeat/conversation loads the entire workspace context.
- **node_modules in workspace is toxic for LLM costs.** 166MB of Astro dependencies was being tokenised on every API call.
- **ADR-017 was right:** a Python script in the sandbox is simpler and more reliable than MCP for this use case.
- **Write the ADR last** (lesson from ADR-017): document what actually worked, not what we planned to build.
