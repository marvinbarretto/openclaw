# Briefing API Delivery — Design Spec

**Date:** 2026-03-16
**Context:** Session 7 review revealed Opus analysis is working (first time since path fix) but Jimbo (Step 3.5 Flash) ignores it entirely — fabricates calendar events, misses key emails, stalls for 2 hours. Root cause: the delivery skill asks a free model to do one-shot composition from 25KB of JSON. This is against the grain of how OpenClaw works (step-by-step tool use, conversational).

## Problem

Opus produces excellent structured analysis. Jimbo can't reliably read it from a file and compose a briefing. The skill is too complex for cheap models, and reducing Jimbo to a template relay defeats the purpose of OpenClaw (autonomous agent with tools, conversational, agentic).

## Solution

Opus publishes structured analysis to jimbo-api. Jimbo fetches from the API and delivers section-by-section using tool calls. After delivery, Jimbo stays in conversation as a full agent — answering questions, creating calendar events, browsing vault tasks, fetching email detail.

## Architecture

```
Mac (launchd 06:35 + 14:35):
  opus-briefing.sh
    → SSH pull briefing-input.json from VPS (unchanged)
    → claude -p (Opus via Max plan)
    → POST /api/briefing/analysis → jimbo-api

Jimbo (OpenClaw, scheduled 07:00 + 15:00 or on-demand):
  daily-briefing skill:
    → curl GET /api/briefing/latest
    → Deliver day plan as message
    → Deliver email highlights as messages
    → Deliver surprise if present
    → Stay in conversation for follow-ups
    → Use sandbox tools: calendar-helper.py, vault API, email reports API
```

## Components

### 1. jimbo-api: Briefing endpoint

New routes (same `apiKeyAuth` middleware as all other `/api/*` routes):
- `POST /api/briefing/analysis` — Opus publishes here
- `GET /api/briefing/latest` — Jimbo/dashboard reads latest. Optional `?session=morning|afternoon` filter.
- `GET /api/briefing/history?limit=N` — Historical access for dashboard and rating workflow.

Authentication: same API key as all other endpoints. `opus-briefing.sh` on Mac needs `JIMBO_API_KEY` env var (same value as VPS `API_KEY`).

New SQLite table `briefing_analyses`:
- `id` INTEGER PRIMARY KEY
- `session` TEXT NOT NULL (morning|afternoon)
- `model` TEXT NOT NULL
- `generated_at` TEXT NOT NULL (ISO timestamp from Opus)
- `analysis` TEXT NOT NULL (full JSON blob)
- `user_rating` INTEGER (1-10, nullable — for retroactive rating)
- `created_at` TEXT DEFAULT CURRENT_TIMESTAMP

**POST validation:**
- Required: `session`, `model`, `generated_at`, `day_plan` (array, non-empty)
- Optional: `email_highlights` (array, defaults to []), `surprise` (object, defaults to null), `vault_tasks` (array, defaults to [])
- Returns 400 with specific error if validation fails

**GET /api/briefing/latest:**
- Returns most recent analysis where `generated_at` is within the last 6 hours (UTC)
- Optional `?session=morning|afternoon` filter
- Returns 404 if nothing fresh — Jimbo knows to offer alternatives
- Response includes the full analysis JSON plus `id` (for rating) and `created_at`

**GET /api/briefing/history:**
- Returns recent analyses, default `limit=10`
- For dashboard display and quality tracking

### 2. opus-briefing.sh changes

- Replace file push with `curl POST` to jimbo-api (using `JIMBO_API_KEY` env var on Mac)
- Replace `|| exit 0` on every line with proper error logging to stderr
- Add Telegram alert on failure (direct Bot API curl using `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` env vars on Mac)
- No other logic changes — still validates JSON, checks freshness, checks session match

**Required Mac env vars** (add to `~/.zshenv` or launchd plist):
- `JIMBO_API_KEY` — same value as VPS `API_KEY`
- `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` — for failure alerts

### 3. Opus prompt changes

- Drop `editorial_voice` field — Jimbo owns the voice
- Add `vault_tasks` array to output schema:
  ```json
  "vault_tasks": [
    {
      "title": "task name from pipeline",
      "priority": 10,
      "actionability": "clear",
      "note": "one sentence on why this matters today or how it connects"
    }
  ]
  ```
- Keep: `day_plan`, `email_highlights`, `surprise`
- Keep: all rules about calendar being facts, cross-referencing, explaining WHY
- Files to modify: `opus-prompts/morning.md`, `opus-prompts/afternoon.md`

### 4. Daily briefing skill rewrite

~30 lines, structured as sequential tool calls:

```
Step 1: curl GET /api/briefing/latest
  → API unreachable? "jimbo-api is down. I can still check your calendar and email directly — want me to?"
  → 404? "Opus hasn't run yet. I can check your calendar and top vault tasks if you'd like."
  → Found? Continue.

Step 2: Send day plan (calendar + suggestions) as message

Step 3: Send email highlights as message(s). Skip section if array is empty.

Step 4: Send surprise if present. Skip if null.

Step 5: Send vault tasks if present. If triage_pending > 0, announce: "I picked up N tasks that need your input. When's good for a 15-min triage?"

Step 6: Log delivery via API:
  → POST /api/activity (task=briefing, description, outcome)
  → POST /api/experiments (task=briefing-synthesis, model, session, mode=opus-assisted)

Step 7: Available for follow-ups:
  → "Tell me more about X" → GET /api/emails/reports/:id
  → "Add that to my calendar" → calendar-helper.py create-event
  → "What vault tasks?" → GET /api/vault/notes
  → "Remind me at 3pm" → calendar-helper.py create-event
```

No mode detection. No personality instructions (SOUL.md already in OpenClaw context). No fabrication rules (nothing to fabricate from).

**Degraded mode:** When Opus analysis is unavailable (Mac asleep, API down), Jimbo doesn't attempt full self-compose (that's what broke before). Instead he offers to check specific tools on demand — calendar, email, vault. This is honest and conversational, not a bad imitation of what Opus does.

**Sandbox env vars already available:** `JIMBO_API_URL` and `JIMBO_API_KEY` are set in openclaw.env. The skill uses `curl` with these in the sandbox, same pattern as `context-helper.py`.

## What stays unchanged

- `briefing-prep.py` on cron (data collection)
- All sandbox tools (calendar-helper, gmail-helper, context-helper, etc.)
- All existing jimbo-api endpoints
- OpenClaw cron schedule (07:00 + 15:00)
- Launchd schedule on Mac (06:35 + 14:35)

## What gets removed

- `briefing-analysis.json` file on VPS (replaced by API)
- Two-mode logic in skill (Opus-assisted vs self-compose)
- `conductor-rating` references in skill
- `editorial_voice` from Opus output

## Open questions (v2)

- Move `briefing-input.json` to API too? Would eliminate all file-based data flow and SSH reads from opus-briefing.sh. Bigger change.
- Flash triage worker: 0 shortlisted across 8 sessions. Dead weight but costs $0.03/day. Remove or recalibrate?
- Model choice: Start with Flash (free). If skill simplification isn't enough, swap to Haiku ($1.80/month) or Gemini Flash paid ($0.30/month).
- Dashboard view: Show Opus analysis on the site. Natural extension once the API endpoint exists.

## Testing

- Unit: jimbo-api endpoint tests (POST validation, GET latest, session filter)
- Integration: opus-briefing.sh posts successfully, Jimbo reads successfully
- Live: First real test will be the morning after deployment
