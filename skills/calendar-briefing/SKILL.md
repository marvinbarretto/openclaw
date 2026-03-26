---
name: calendar-briefing
description: Compose a short calendar summary with confirmed events and options
user-invokable: false
---

# Calendar Briefing

You are running as an isolated cron job. Compose a brief, factual calendar summary. No editorial, no day plan — just what's on.

## Steps

### 1. Determine time window

If current time is before 12:00 Europe/London: cover **today only**.
If after 12:00: cover **rest of today + tomorrow**.

### 2. Fetch events

```bash
python3 /workspace/calendar-helper.py list-events --days 1 --whitelist
```

For afternoon runs covering tomorrow:
```bash
python3 /workspace/calendar-helper.py list-events --days 2 --whitelist
```

### 3. Classify events

Parse the JSON output. Each event has: `calendar`, `summary`, `start`, `end`, `location`, `tag`.

- **Confirmed:** Events from `marvinbarretto@gmail.com` with no tag. These are real commitments.
- **Options:** Events tagged `"options"` (from marbar.alt calendar). These are interesting possibilities, NOT commitments. Always label them clearly.
- **Ignore:** Sunrise/sunset entries. Events from tomorrow (in morning runs).

### 4. Compose summary

Start with a label:

**[Calendar]**

Then:

**Confirmed:**
- Time — Event (location if relevant)
- Time — Event

**Options calendar:**
- Event name (location/venue)

**Heads up:** [any conflicts, tight transitions, or clashes between confirmed + options]

### 5. Output discipline

If no events today (or remaining today for afternoon): **produce ZERO output.** Complete silence.

### 6. Log

```bash
python3 /workspace/activity-log.py log --type calendar-check --description "N confirmed, N options" --outcome "delivered"
```
