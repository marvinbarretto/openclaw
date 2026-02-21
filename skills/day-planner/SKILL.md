---
name: day-planner
description: Proactively plan Marvin's day — suggest activities for free gaps, negotiate the plan, create events on the suggestions calendar
user-invokable: true
---

# Day Planner

Jimbo proactively fills Marvin's day with useful suggestions, using the "Jimbo Suggestions" calendar as the coordination layer. Suggestions are recommendations, not commitments — Marvin can ignore, dismiss, or accept them.

## Before you start

Read ALL of these before making any suggestions:
1. Today's calendar: `python3 /workspace/calendar-helper.py list-events --days 1`
2. This week's calendar (for broader context): `python3 /workspace/calendar-helper.py list-events --days 7`
3. `/workspace/email-digest.json` — time-sensitive items from email
4. `/workspace/context/PRIORITIES.md` — active tasks and projects
5. `/workspace/context/GOALS.md` — longer-term ambitions
6. `/workspace/context/INTERESTS.md` — event scouting, hobbies, communities
7. `/workspace/context/TASTE.md` — judgment on what's worth surfacing

## How to identify free gaps

- Look at today's events, find gaps of 30+ minutes
- Weight morning gaps for deep work (coding, writing, focused tasks)
- Weight afternoon gaps for admin, errands, chasing people
- Respect existing events — NEVER double-book
- Always run `check-conflicts` before creating any event

## What to suggest (priority order)

1. **Time-sensitive items from email** — events, deadlines, expiring deals, ticket sales
2. **Overdue items from PRIORITIES.md** — stuff that's been sitting there for days
3. **Active project work blocks** — Spoons, LocalShout, Jimbo/OpenClaw dev time
4. **Goal-aligned activities from GOALS.md** — YNAB, travel research, long-term items
5. **Interest-based suggestions** — gigs, matches, meetups spotted in email or calendar
6. **One wildcard** — something surprising from email or interests that Marvin might not expect

## Event naming convention

Prefix suggestions with an emoji category so they're visually distinct:

- `🔨` Project work (Spoons, LocalShout, OpenClaw)
- `📧` Email action (chase someone, reply, book something)
- `🎯` Priority item (from PRIORITIES.md)
- `🎵` Event/gig/match (entertainment, sport, culture)
- `💰` Finance (YNAB, bills, deals)
- `🏃` Health/exercise
- `🎲` Wildcard (surprising or serendipitous)

Keep titles short and actionable:
- Good: `🔨 Spoons: review open PRs`
- Bad: `Consider reviewing the open pull requests for Spoons`

## Rules

1. **Never create more than 5 suggestions per day.** Quality over quantity.
2. **Always check conflicts before creating.** Run `check-conflicts` for each proposed slot.
3. **Always create on the suggestions calendar.** Use `--calendar-id` with the Jimbo Suggestions calendar ID (see calendar skill for the ID). NEVER create suggestions on the primary calendar.
4. **Morning negotiation is a conversation.** Wait for Marvin's response before creating ANY events.
5. **If Marvin says "looks good"** — create all suggested events.
6. **If Marvin modifies** — adjust and confirm before creating.
7. **If Marvin says "skip X"** — create everything except X, no need to re-confirm.
8. **End of day** — don't move unfinished items automatically. Ask first.
9. **Always invite Marvin** as attendee on suggestion events so they appear on his calendar.

## Morning negotiation

This is the core interaction. When Marvin says good morning or asks for a briefing, the daily-briefing skill handles the overview. The day-planner kicks in for the schedule section.

### Format

```
Morning, Marvin. Here's your day:

Fixed: Dentist at 10:30, Spoons standup at 16:00.

I'd suggest:
  🔨 09:00-10:00 — Spoons PR review (4 days overdue)
  📧 11:30-12:00 — Chase Daniel about DisplayLink (from your priorities)
  🎯 14:00-15:30 — LocalShout: plan auth flow (you haven't touched it this week)
  💰 15:30-16:00 — YNAB setup (keeps slipping)

Anything you'd swap or skip?
```

### Key principles

- **Show the fixed events first** so Marvin sees the constraints
- **Explain WHY** each suggestion exists (overdue, from email, keeps slipping)
- **Keep it to 3-5 suggestions** — don't overwhelm
- **End with an invitation to negotiate** — this is collaborative, not prescriptive
- **Respect "no"** — if Marvin rejects something, don't push back or re-suggest it the same day

## Proactive nudges (via heartbeat)

During active hours (09:00-18:00 Europe/London), if the heartbeat detects:
- A 2+ hour free gap starting within the next hour
- AND there are overdue items in PRIORITIES.md

Then send a brief Telegram nudge:
```
You're free until 3pm and Spoons PR review has been on your list 4 days. Want me to block that time?
```

Don't nudge more than twice per day. Don't nudge about the same item twice.

## Creating events after negotiation

Once Marvin agrees to the plan (or a modified version):

```bash
python3 /workspace/calendar-helper.py create-event \
  --summary "🔨 Spoons: review open PRs" \
  --start 2026-02-21T09:00:00 \
  --end 2026-02-21T10:00:00 \
  --calendar-id 2244d4f6d61cbc9f2041405c16dea6726a34f2c895e49dce7c5e1e4f0287789c@group.calendar.google.com \
  --attendee marvin@example.com \
  --description "Suggested by Jimbo — 4 days overdue from PRIORITIES"
```

Use `--description` to note why the event was suggested. This helps Marvin understand the reasoning when he sees it on his calendar.
