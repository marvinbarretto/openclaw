---
name: calendar
description: Manage Google Calendar — view schedule, check conflicts, create events
user-invokable: true
---

# Calendar

Jimbo owns his own Google Calendar and has read access to Marvin's shared calendars. Use the `calendar-helper.py` script in the sandbox to interact with the API.

## Before you start

Read Marvin's context to make calendar decisions intelligently:
1. `/workspace/context/PRIORITIES.md` — what's active this week
2. `/workspace/context/INTERESTS.md` — events and topics he cares about
3. `/workspace/context/TASTE.md` — how he likes information presented

## Available commands

Run these in the sandbox with `python3 /workspace/calendar-helper.py <command>`.

### List calendars
```bash
python3 /workspace/calendar-helper.py list-calendars
```
Shows all visible calendars (Jimbo's own + shared). Use this to discover calendar IDs.

### List events
```bash
python3 /workspace/calendar-helper.py list-events --days 7
python3 /workspace/calendar-helper.py list-events --days 1
python3 /workspace/calendar-helper.py list-events --days 3 --calendar-id someone@gmail.com
```
Shows upcoming events across all calendars (or a specific one), merged and sorted by start time.

### Check conflicts
```bash
python3 /workspace/calendar-helper.py check-conflicts --start 2026-02-20T14:00:00 --end 2026-02-20T15:00:00
```
Checks all calendars for clashes in a proposed time window. Returns `has_conflicts: true/false` with details.

### Create event
```bash
python3 /workspace/calendar-helper.py create-event \
  --summary "Review Spoons PRs" \
  --start 2026-02-21T15:00:00 \
  --end 2026-02-21T15:30:00 \
  --attendee marvin@example.com
```
Creates an event on Jimbo's primary calendar only. Optional `--description` and `--attendee` flags.

## Rules

1. **Always check for conflicts before creating an event.** Run `check-conflicts` first, tell Marvin if there's a clash, and only proceed if the slot is free or Marvin confirms.

2. **Always invite Marvin.** Use `--attendee` with Marvin's email when creating events. Jimbo owns the calendar but events are for Marvin.

3. **Never modify shared calendars.** The `create-event` command only writes to Jimbo's primary calendar. There are no update or delete commands. This is by design.

4. **Use Europe/London timezone.** All times are in `Europe/London` by default. If Marvin mentions a different timezone, convert before passing to the script.

5. **Be specific with times.** Always use ISO 8601 format: `2026-02-20T14:00:00`. Don't guess times — ask Marvin if unclear.

## When to create events

- **Time-sensitive emails:** If the email digest mentions an event, ticket sale, or deadline, offer to add it to the calendar.
- **Deadlines from PRIORITIES.md:** If something has a due date, offer to create a reminder.
- **Explicit requests:** "Remind me on Friday at 3pm to..." → create an event.
- **Don't auto-create** unless asked. Always suggest first, let Marvin confirm.

## Presenting calendar information

- **Chronological order** — earliest first
- **Flag imminent events** — anything in the next 2 hours gets a heads-up
- **Suppress routine** — if Marvin has recurring work meetings, don't list them all. Mention "3 work meetings today" and only detail the unusual ones.
- **Merge across calendars** — present as one unified timeline, don't separate by calendar
- **Keep it scannable** — date, time, title. Location only if relevant. Links only if asked.

## In morning briefings

When the daily-briefing skill runs, it includes a "Today's schedule" section. See the daily-briefing SKILL.md for details. The calendar skill provides the data; the briefing skill formats it.

## Error handling

- If the script exits with an error about token refresh, tell Marvin: "Your Google Calendar token seems to have expired. Run `python3 scripts/calendar-auth.py` on your laptop to re-authenticate."
- If the script isn't found at `/workspace/calendar-helper.py`, tell Marvin: "Calendar helper isn't deployed. Run `./scripts/calendar-setup.sh` from the openclaw repo."
- If no calendars are returned, the account may not have any shared calendars yet.
