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
- Task status: `curl -sf -H "X-API-Key: $JIMBO_API_KEY" "$JIMBO_API_URL/api/vault/tasks/summary"`
- Dispatch: `curl -sf -H "X-API-Key: $JIMBO_API_KEY" "$JIMBO_API_URL/api/dispatch/briefing-summary"`

## Step 2: Deliver the briefing

Walk through the data **one section at a time**. Send each as a separate Telegram message. Use your own voice — be conversational, not robotic.

**Telegram rules:**
- Each section = one message. Never combine sections into a wall of text.
- Max 4-6 lines per message. If a section needs more, cut — you're curating, not dumping.
- No bullet points for single items. Just say it.
- Email highlights: pick 3-4 max, one line each. "Wizz Air: Lisbon £32 return, ends tonight" not a paragraph.
- Skip sections with nothing to report. Don't say "no emails today" — just don't send that message.

1. **Day plan** — present today's calendar events as a timeline. Identify free gaps. Flag anything in the next 2 hours. If you have Opus analysis, use its suggestions. If working from raw calendar data, propose how to use free blocks based on priorities.
2. **Calendar-vault connections** — If `briefing-input.json` has a `calendar_links` array with entries, surface them naturally after the day plan. Don't list all matches — pick the 1-2 most useful. "Your dentist is at 2pm and you've got a vault task to ask about that jaw issue" or "You've got that Spoons meeting tomorrow and 3 open vault tasks tagged `spoons`." Skip this section entirely if `calendar_links` is empty.
3. **Email highlights** — present interesting emails with WHY each matters. If working from `briefing-input.json`, read ALL entries in the `gems` array AND the `email_insights` array (sorted by relevance_score). Present the top 3-4 by confidence/relevance score. Never skip a gem with confidence >= 0.9. Include URLs directly from the gem data — say "Check it out: [URL]" not "link in the email".
4. **Surprise** — REQUIRED: always include a surprise. Find a genuinely non-obvious connection between two different data sources (email × vault, calendar × priorities, gem × old bookmark). If nothing connects, pick the single most unexpected thing from today's data and frame it as a discovery.
5. **Task status** — Call `curl -sf -H "X-API-Key: $JIMBO_API_KEY" "$JIMBO_API_URL/api/vault/tasks/summary"` and report:
   - Done since last briefing (with titles if ≤5, count if more)
   - Currently in progress (by owner)
   - Blocked (with blocker text from `blocked_by` field)
   - Overdue (due_date passed, not done)
   - New inbox items: "6 new tasks in the inbox — 3 from Google Tasks, 2 from email, 1 from yesterday's conversation."

   Do NOT list all active tasks. Do NOT triage during the briefing. The briefing reports status; the grooming session (vault-grooming skill) makes decisions.

   If `velocity_7d > 0`: "We're closing about {velocity_7d} tasks per day this week."
   If `inbox_count >= 10`: "Inbox is getting full — want to do a quick grooming session later?"

6. **Dispatch status** — If `briefing-input.json` has a `dispatch` key with data, report agent work status. If the key is missing or empty, call the API directly as fallback: `curl -sf -H "X-API-Key: $JIMBO_API_KEY" "$JIMBO_API_URL/api/dispatch/briefing-summary"`

   Present what's relevant, skip what's empty:
   - **PRs for review:** "You've got N PRs ready for review" + one line per PR: "{task_id}: {result_summary}" with PR URL. This is your highest-priority dispatch item — these need human eyes.
   - **In progress:** "N commissions running" + one line each with task_id. Only mention if > 0.
   - **Awaiting dispatch:** "N ralph issues ready to dispatch" — only if > 0. If `null`, skip (means GitHub was unreachable).
   - **Recon landed:** "Recon on {task_id} landed — {result_summary}" for each recently completed recon task.
   - **Needs grooming:** "N tasks need grooming before dispatch" — only if > 0.

   Skip the entire section if everything is zero/empty. Don't say "no dispatch activity."

**Calendar tags:** Events in `briefing-input.json` may include a `tag` field from the calendar config:
- `tag: "options"` — this is an "options" calendar (e.g. marbar.alt). These are nudges about events that *might* be happening, not commitments. Present as "From your options calendar" and treat as lower-confidence possibilities.
- `tag: "airbnb"` — Airbnb booking/hosting events. Present with hosting context.
- `tag: null` or missing — a firm commitment. Present normally.
- Any other tag value — mention the tag for context (e.g., "from your [tag] calendar").

After delivering, ask: "Anything you'd swap or skip?"

## Step 3: Log delivery

Only log success if you actually delivered briefing content above. If the briefing failed (no data, rate limit, error), log outcome as "failed" with a description of what went wrong. Do NOT log success for a briefing you didn't deliver.

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
- **"What vault tasks are urgent?"** → `curl -sf -H "X-API-Key: $JIMBO_API_KEY" "$JIMBO_API_URL/api/vault/notes?status=active&sort=effective_priority&order=desc&has_parent=false&limit=10"`
- **"How are we getting on?"** → `curl -sf -H "X-API-Key: $JIMBO_API_KEY" "$JIMBO_API_URL/api/vault/tasks/summary"`
- **"What's blocked?"** → `curl -sf -H "X-API-Key: $JIMBO_API_KEY" "$JIMBO_API_URL/api/vault/notes?status=blocked"`
- **"Let's groom"** → invoke the `vault-grooming` skill
- **"Remind me at 3pm about X"** → `python3 /workspace/calendar-helper.py create-event --summary "Reminder: X" --start 2026-03-16T15:00:00 --end 2026-03-16T15:15:00`
