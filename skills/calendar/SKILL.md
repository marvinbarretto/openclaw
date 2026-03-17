---
name: calendar
description: Manage Google Calendar — view schedule, check conflicts, create events
user-invokable: true
---

# Calendar

Jimbo owns his own Google Calendar and has read access to Marvin's shared calendars. Use the `calendar-helper.py` script in the sandbox to interact with the API.

## Before you start

Read Marvin's context to make calendar decisions intelligently:
1. Run `python3 /workspace/context-helper.py priorities` — what's active this week
2. Run `python3 /workspace/context-helper.py interests` — events and topics he cares about
3. Read `/workspace/context/TASTE.md` — how he likes information presented

**Calendar sources:** Marvin has two Google accounts on his calendar:
- **Primary (marvin@...)** — real commitments, fixed events
- **marbar.alt@gmail.com** — an "options" calendar. These are nudges about events that *might* be happening, not commitments. This calendar was off for months so some content is stale. Treat marbar.alt events as lower-confidence possibilities, not fixed schedule items.

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
Creates an event on Jimbo's primary calendar by default. Optional `--description`, `--attendee`, and `--calendar-id` flags. Use `--calendar-id` to target the suggestions calendar.

### Create calendar (one-time setup)
```bash
python3 /workspace/calendar-helper.py create-calendar --summary "Jimbo Suggestions"
```
Creates a new secondary calendar. Used once to set up the suggestions calendar.

### Share calendar (one-time setup)
```bash
python3 /workspace/calendar-helper.py share-calendar --calendar-id CALENDAR_ID --email marvin@example.com
```
Shares a calendar with another user (reader access by default). Optional `--role` flag.

## Suggestions calendar

Jimbo has a dedicated "Jimbo Suggestions" calendar for proactive day planning. This is separate from Jimbo's primary calendar.

- **Calendar ID:** `2244d4f6d61cbc9f2041405c16dea6726a34f2c895e49dce7c5e1e4f0287789c@group.calendar.google.com`
- **Purpose:** Recommendations, not commitments. Marvin sees these alongside real events but can ignore them.
- **Visual distinction:** All suggestion events use emoji prefixes (see day-planner skill for the convention).
- **Shared with Marvin:** Reader access so suggestions appear on his Google Calendar automatically.

### Event naming convention (suggestions calendar only)

Prefix with emoji category:
- `🔨` Project work — `🔨 Spoons: review open PRs`
- `📧` Email action — `📧 Chase Daniel about DisplayLink`
- `🎯` Priority item — `🎯 LocalShout: plan auth flow`
- `🎵` Event/gig — `🎵 Six Nations: England vs France`
- `💰` Finance — `💰 YNAB setup`
- `🏃` Health — `🏃 Gym session`
- `🎲` Wildcard — `🎲 Check out that Product Hunt tool`

### One-time setup commands

```bash
# Create the suggestions calendar
python3 /workspace/calendar-helper.py create-calendar --summary "Jimbo Suggestions" --description "Proactive suggestions from Jimbo"

# Share it with Marvin (reader access)
python3 /workspace/calendar-helper.py share-calendar --calendar-id CALENDAR_ID --email marvin@example.com
```

## Rules

1. **Always check for conflicts before creating an event.** Run `check-conflicts` first, tell Marvin if there's a clash, and only proceed if the slot is free or Marvin confirms.

2. **Always invite Marvin.** Use `--attendee` with Marvin's email when creating events. Jimbo owns the calendar but events are for Marvin.

3. **Never modify shared calendars.** There are no update or delete commands. This is by design.

4. **Use the right calendar.** Explicit events and reminders go on the primary calendar. Proactive suggestions go on the suggestions calendar using `--calendar-id`.

5. **Use Europe/London timezone.** All times are in `Europe/London` by default. If Marvin mentions a different timezone, convert before passing to the script.

6. **Be specific with times.** Always use ISO 8601 format: `2026-02-20T14:00:00`. Don't guess times — ask Marvin if unclear.

## When to create events

- **Time-sensitive emails:** If the email digest mentions an event, ticket sale, or deadline, offer to add it to the calendar.
- **Deadlines from PRIORITIES.md:** If something has a due date, offer to create a reminder.
- **Explicit requests:** "Remind me on Friday at 3pm to..." → create an event.
- **Day planning suggestions:** See the day-planner skill. These always go on the suggestions calendar.
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
