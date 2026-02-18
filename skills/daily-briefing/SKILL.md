---
name: daily-briefing
description: Give a concise morning briefing combining email, tasks, and context
user-invocable: true
---

# Daily Briefing

When the user says good morning, asks for a briefing, or uses `/briefing`, give a concise daily overview.

## What to include

Gather information from these sources and present a combined briefing:

### 1. Date and greeting
- Today's date and day of the week
- Brief, friendly greeting (match the tone in SOUL.md)

### 2. Email digest (if available)
- Read `/workspace/email-digest.json`
- If it exists and is fresh (< 24h old): show the quick stats from the sift-digest skill format — total emails, reading time, action breakdown
- If it exists but is stale: mention "Your email digest is from [date] — it may be outdated"
- If it doesn't exist: mention "No email digest available today"
- Do NOT show the full email breakdown here — keep it to 2-3 lines. The user can use `/email` for details.

### 3. Heartbeat tasks
- Read `/workspace/HEARTBEAT.md`
- If there are pending tasks or checks listed, mention them briefly
- If nothing is due, skip this section

### 4. Project-relevant emails
- If the email digest has any items with `project_relevance` set, call them out: "You have X emails related to [project]"
- This is a teaser — details via `/email`

## Presentation format

Keep the entire briefing under 15 lines. Example:

```
Morning, Marvin. It's Tuesday 18 Feb.

Email: 18 messages, ~12 min reading queued. 4 worth reading, 4 unsubscribe candidates. 2 related to Spoons.

Heartbeat: Token expiry check due this week (JIMBO_GH_TOKEN).

Use /email for the full digest.
```

## Rules

- Be concise — this is a glance, not a deep dive
- Don't repeat what other skills will cover in detail
- If all sources are empty/missing, just greet and say "Nothing pressing today"
- Match Jimbo's personality from SOUL.md
