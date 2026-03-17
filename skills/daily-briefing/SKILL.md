---
name: daily-briefing
description: Deliver the morning or afternoon briefing from pre-assembled pipeline data
user-invokable: true
---

# Daily Briefing

When the user says good morning, asks for a briefing, or it's a scheduled briefing session.

## Step 1: Load briefing data

Try these sources in order. Use the first one that works:

**Option A — Opus analysis from API:**
```bash
curl -sf -H "X-API-Key: $JIMBO_API_KEY" "$JIMBO_API_URL/api/briefing/latest"
```
If this returns data, use it — Opus has already analyzed everything.

**Option B — Pipeline data file (fallback):**
```bash
cat /workspace/briefing-input.json
```
If the API fails (404, timeout, down), read this file directly. It's assembled by `briefing-prep.py` and contains calendar, email insights, vault tasks, gems, and context summary. This is good data — you just need to synthesize it yourself instead of relaying Opus.

Check freshness: the `generated_at` field should be within the last 12 hours. If it's stale, tell Marvin and offer to check live data.

**Option C — Live data (last resort):**
If neither source has fresh data, gather it yourself:
- Calendar: `python3 /workspace/calendar-helper.py list-events --days 1`
- Context: `python3 /workspace/context-helper.py priorities`
- Vault tasks: read frontmatter from `/workspace/vault/notes/`, filter `type: task`, `status: active`, `priority >= 7`

## Step 2: Deliver the briefing

Walk through the data **one section at a time**. Send each as a separate message. Use your own voice — be conversational, not robotic.

1. **Day plan** — present today's calendar events as a timeline. Identify free gaps. Flag anything in the next 2 hours. If you have Opus analysis, use its suggestions. If working from raw calendar data, propose how to use free blocks based on priorities.
2. **Email highlights** — present interesting emails with WHY each matters. If working from `briefing-input.json`, use the `email_insights` array (sorted by relevance_score) and the `gems` array. Skip if both are empty.
3. **Surprise** — present a genuinely non-obvious connection or find. Skip if you can't find one worth sharing.
4. **Vault tasks** — present priority tasks with notes on why they matter today. If `triage_pending > 0` in the data, announce: "I picked up N tasks that need your input. When's good for a 15-min triage?"

**Calendar note:** Marvin has two Google accounts on his calendar. Events from `marbar.alt@gmail.com` are an "options" calendar — nudges about events that *might* be happening, not commitments. Treat them as lower-confidence possibilities, not fixed schedule items.

After delivering, ask: "Anything you'd swap or skip?"

## Step 3: Log delivery

Run both in the sandbox:

```bash
curl -sf -X POST -H "X-API-Key: $JIMBO_API_KEY" -H "Content-Type: application/json" \
  -d '{"task_type":"briefing","description":"<Morning|Afternoon> briefing delivered","outcome":"success"}' \
  "$JIMBO_API_URL/api/activity"

curl -sf -X POST -H "X-API-Key: $JIMBO_API_KEY" -H "Content-Type: application/json" \
  -d '{"task":"briefing-synthesis","model":"<your-model>","input_tokens":0,"output_tokens":0,"config_hash":"self-composed","notes":"{\"mode\":\"self-composed\",\"session\":\"<morning|afternoon>\"}"}' \
  "$JIMBO_API_URL/api/experiments"
```

## Step 4: Stay available

You are now in conversation. Marvin may ask follow-ups. Use your sandbox tools:

- **"Tell me more about [email]"** → `curl -sf -H "X-API-Key: $JIMBO_API_KEY" "$JIMBO_API_URL/api/emails/reports"` and find the relevant report
- **"Add that to my calendar"** → `python3 /workspace/calendar-helper.py create-event --summary "..." --start ... --end ...`
- **"Check conflicts at 3pm"** → `python3 /workspace/calendar-helper.py check-conflicts --start ... --end ...`
- **"What vault tasks are urgent?"** → `curl -sf -H "X-API-Key: $JIMBO_API_KEY" "$JIMBO_API_URL/api/vault/notes?status=active&sort=priority&limit=10"`
- **"Remind me at 3pm about X"** → `python3 /workspace/calendar-helper.py create-event --summary "Reminder: X" --start 2026-03-16T15:00:00 --end 2026-03-16T15:15:00`
