---
name: daily-briefing
description: Report what you know — present data, don't advise
user-invokable: true
---

# Daily Briefing

When the user says good morning, asks for a briefing, or it's a scheduled briefing session.

## Core principle

**Report what you know, not what Marvin should do.** Present data clearly and honestly. Flag what's uncertain. Don't propose day plans, suggest activities, or fill gaps with advice. Marvin decides what to do with the information.

## Step 1: Check your own status

Before anything else, know yourself:

```bash
python3 /workspace/health-helper.py status
```

This tells you: what model you're running, what the pipeline produced, your activity today, costs, vault state, dispatch queue, and any system issues. Use this to ground everything you say in reality — don't claim things you can't verify.

## Step 2: Load briefing data

```bash
cat /workspace/briefing-input.json
```

This file is assembled by `briefing-prep.py` on cron. It contains calendar events, email gems, email insights, vault tasks, and dispatch status.

Check freshness: the `generated_at` field should be within the last 12 hours. If it's stale, say so.

**Fallback — if the file is missing or stale:**
- Calendar: `python3 /workspace/calendar-helper.py list-events --days 1`
- Context: `python3 /workspace/context-helper.py priorities`
- Task status: `curl -sf -H "X-API-Key: $JIMBO_API_KEY" "$JIMBO_API_URL/api/vault/tasks/summary"`
- Dispatch: `curl -sf -H "X-API-Key: $JIMBO_API_KEY" "$JIMBO_API_URL/api/dispatch/briefing-summary"`

## Step 3: Deliver the briefing

Walk through the data **one section at a time**. Send each as a separate Telegram message. Use your own voice — be conversational, not robotic.

**Telegram rules:**
- Each section = one message. Never combine sections into a wall of text.
- Max 4-6 lines per message. If a section needs more, cut — you're curating, not dumping.
- No bullet points for single items. Just say it.
- Skip sections with nothing to report. Don't say "no emails today" — just don't send that message.

### Sections

1. **System pulse** — One line. "Running on [model], pipeline ran at [time], [N] gems from [N] emails, $[cost] today." If there are system issues from health-helper, mention them briefly.

2. **Calendar** — List today's confirmed events as a timeline. Separate confirmed from options.
   - `tag: null` or missing = confirmed. Present normally with times.
   - `tag: "options"` = options calendar. Group these separately: "Options calendar has: [list]". These are possibilities, not commitments.
   - `tag: "airbnb"` = hosting. Present with hosting context.
   - `tag: "work"` = work calendar. Present normally.
   - Any other tag — mention it.
   - Do NOT propose how to fill gaps. Do NOT suggest what to do in free time.

3. **Calendar-vault connections** — If `briefing-input.json` has a `calendar_links` array with entries, surface the 1-2 most useful. Skip entirely if empty.

4. **Email highlights** — Present the most interesting finds from `gems` and `email_insights` arrays. Pick the top 3-5 by confidence/relevance score. Never skip a gem with confidence >= 0.9. For each one: what it is, why it stood out, include URLs directly from the data. Flag time-sensitive items with their deadlines.

5. **Surprise** — REQUIRED: always include one. Find a genuinely non-obvious connection between two different data sources (email × vault, calendar × priorities, gem × old bookmark). If nothing connects, pick the single most unexpected thing from today's data.

6. **Task status** — Call `curl -sf -H "X-API-Key: $JIMBO_API_KEY" "$JIMBO_API_URL/api/vault/tasks/summary"` and report the numbers:
   - Done since last briefing, in progress, blocked, overdue, new inbox items.
   - Velocity if > 0, inbox size if >= 10.
   - Do NOT list all active tasks. Do NOT triage. Just report status.

7. **Dispatch status** — From `briefing-input.json` dispatch key, or fallback to API: `curl -sf -H "X-API-Key: $JIMBO_API_KEY" "$JIMBO_API_URL/api/dispatch/briefing-summary"`
   - PRs for review (highest priority — these need human eyes).
   - In progress, awaiting dispatch, recon completed, needs grooming.
   - Skip if everything is zero/empty.

After delivering, ask: "Anything you want to dig into?"

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
