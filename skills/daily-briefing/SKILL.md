---
name: daily-briefing
description: Deliver the morning or afternoon briefing from Opus analysis via jimbo-api
user-invokable: true
---

# Daily Briefing

When the user says good morning, asks for a briefing, or it's a scheduled briefing session.

## Step 1: Fetch today's briefing

Run in the sandbox:

```bash
curl -sf -H "X-API-Key: $JIMBO_API_KEY" "$JIMBO_API_URL/api/briefing/latest"
```

- If the curl fails entirely (connection refused, timeout): say "jimbo-api is down. I can still check your calendar and email directly — want me to?"
- If it returns 404: say "Opus hasn't run yet today. I can check your calendar and top vault tasks if you'd like."
- If it returns data: parse the JSON and continue.

## Step 2: Deliver the briefing

Walk through the analysis **one section at a time**. Send each as a separate message. Use your own voice — be conversational, not robotic.

1. **Day plan** — present the time blocks with suggestions and reasoning. Flag anything in the next 2 hours.
2. **Email highlights** — present each pick with WHY it matters. Skip if the array is empty.
3. **Surprise** — present the connection/find. Skip if null.
4. **Vault tasks** — present priority tasks with notes on why they matter today. If triage_pending > 0 in briefing-input.json, announce: "I picked up N tasks that need your input. When's good for a 15-min triage?"

After delivering, ask: "Anything you'd swap or skip?"

## Step 3: Log delivery

Run both in the sandbox:

```bash
curl -sf -X POST -H "X-API-Key: $JIMBO_API_KEY" -H "Content-Type: application/json" \
  -d '{"task_type":"briefing","description":"<Morning|Afternoon> briefing delivered (opus-assisted)","outcome":"success"}' \
  "$JIMBO_API_URL/api/activity"

curl -sf -X POST -H "X-API-Key: $JIMBO_API_KEY" -H "Content-Type: application/json" \
  -d '{"task":"briefing-synthesis","model":"<your-model>","input_tokens":0,"output_tokens":0,"config_hash":"opus-assisted","notes":"{\"mode\":\"opus-assisted\",\"session\":\"<morning|afternoon>\"}"}' \
  "$JIMBO_API_URL/api/experiments"
```

## Step 4: Stay available

You are now in conversation. Marvin may ask follow-ups. Use your sandbox tools:

- **"Tell me more about [email]"** → `curl -sf -H "X-API-Key: $JIMBO_API_KEY" "$JIMBO_API_URL/api/emails/reports"` and find the relevant report
- **"Add that to my calendar"** → `python3 /workspace/calendar-helper.py create-event --summary "..." --start ... --end ...`
- **"Check conflicts at 3pm"** → `python3 /workspace/calendar-helper.py check-conflicts --start ... --end ...`
- **"What vault tasks are urgent?"** → `curl -sf -H "X-API-Key: $JIMBO_API_KEY" "$JIMBO_API_URL/api/vault/notes?status=active&sort=priority&limit=10"`
- **"Remind me at 3pm about X"** → `python3 /workspace/calendar-helper.py create-event --summary "Reminder: X" --start 2026-03-16T15:00:00 --end 2026-03-16T15:15:00`
