---
name: daily-briefing
description: Give a concise morning briefing combining email, tasks, and context
user-invokable: true
---

# Daily Briefing

When the user says good morning, asks for a briefing, or it's a scheduled morning session, give a concise daily overview.

## Before you start

Read Marvin's context to understand what matters today:
1. `/workspace/context/PRIORITIES.md` — what's active this week
2. `/workspace/context/GOALS.md` — longer-term ambitions
3. `/workspace/context/TASTE.md` — how he likes information presented (concise, scannable, timely)

## What to include

### 1. Date and greeting
- Today's date and day of the week
- Brief, friendly greeting (match the tone in SOUL.md)

### 2. Anything time-sensitive from email
- Read `/workspace/email-digest.json`
- If fresh (< 24h): scan for events, tickets, deadlines, personal replies needing action. Call these out first — even before the stats.
- If stale: "Your email digest is from [date] — might be outdated"
- If missing: "No email digest today"

### 3. Email quick stats
- Total emails, reading time, how many queued vs skipped
- Mention any standout emails: "There's a good Product Hunt issue and an Anjuna event worth looking at"
- Keep to 2-3 lines. Say "ask me about email for the full rundown" for details.

### 4. Priority reminders
- Check PRIORITIES.md for anything due or active
- "You mentioned chasing Daniel about the DisplayLink fix" or "YNAB setup is on your list"
- Only mention 1-2 things, not the whole list

### 5. Heartbeat tasks
- Read `/workspace/HEARTBEAT.md`
- If there are pending checks, mention briefly
- If nothing due, skip this section

## Presentation format

Keep the entire briefing under 15 lines. Scannable in 30 seconds. Example:

```
Morning, Marvin. It's Thursday 20 Feb.

Heads up: There's an Anjuna fabric event — tickets might go fast.

Email: 145 messages overnight, ~25 min of reading queued. Standouts: strong UnHerd piece, Product Hunt daily, and a Watford FC ticket alert.

Priorities: DisplayLink fix still has an action on you. YNAB setup ongoing.

Heartbeat: All clear — digest is fresh, tokens valid.

Ask me about email for the full rundown.
```

## Rules

- Be concise — this is a glance, not a deep dive
- Lead with anything time-sensitive or actionable
- Don't list every queued email — pick the 2-3 best based on his context
- If all sources are empty/missing, just greet and say "Nothing pressing today"
- Match Jimbo's personality from SOUL.md
