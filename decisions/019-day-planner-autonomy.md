# ADR-019: Day Planner — Proactive Autonomy via Suggestions Calendar

## Status

Accepted

## Context

Calendar integration is working (ADR-018). Jimbo can read 6 calendars and create events on his own. The next step is giving Jimbo more autonomy — letting him proactively fill Marvin's day with useful suggestions rather than just reporting the schedule.

The challenge: how to give an AI assistant proactive scheduling power without it becoming annoying, presumptuous, or hard to undo. We need a pattern where Jimbo can suggest freely but Marvin stays in control.

## Decision

### 1. Suggestions calendar (separate calendar = low risk)

Create a dedicated Google Calendar called "Jimbo Suggestions" owned by Jimbo's service account and shared with Marvin as reader. Suggestions appear alongside real events but are visually distinct (emoji prefixes like `🔨`, `📧`, `🎯`).

This is deliberately low-stakes: Marvin can hide the calendar with one click, ignore individual events, or just not look. It's the calendar equivalent of a sticky note — helpful but dismissible.

### 2. Morning negotiation (conversation before creation)

The daily briefing skill now proposes a day plan instead of just reporting the schedule. The flow:

1. Jimbo reads today's calendar, email digest, PRIORITIES, GOALS, INTERESTS
2. Identifies free gaps in the schedule
3. Proposes 3-5 activities for those gaps
4. Marvin says "yes", "no", "swap X for Y"
5. Jimbo creates agreed events on the suggestions calendar

Crucially, Jimbo does NOT create events until Marvin approves. The negotiation is a conversation, not a fait accompli.

### 3. Heartbeat-driven proactive nudges

During active hours (09:00-18:00), the heartbeat checks for 2+ hour free gaps starting within the next hour. If there's an overdue PRIORITIES item that fits, Jimbo sends a brief Telegram nudge. Limited to 2 nudges per day to avoid nagging.

### Guardrails

- Maximum 5 suggestions per day
- Never double-book — always check conflicts before creating
- Morning negotiation requires explicit approval before creating events
- No auto-moving unfinished items — ask first
- Nudge limit: 2 per day, never the same item twice
- Suggestions calendar only — never create proactive events on primary calendar

## Consequences

**What becomes easier:**
- Marvin gets a structured day without having to plan it himself
- Overdue items get surfaced in context (free time + priority = nudge)
- Email-derived events (tickets, deadlines) get automatically proposed
- The suggestions calendar provides a record of what was planned vs what happened

**What becomes harder:**
- More context reading on every briefing (6-7 files + calendar + email digest)
- The negotiation flow means briefings take longer — it's now a conversation, not a monologue
- Token usage increases with all the cross-referencing

**Risks:**
- Suggestions could feel nagging if not calibrated well — the emoji prefixes and "swap or skip?" language are designed to feel casual
- Gemini's ability to reason across 7 context files simultaneously is unproven — may need to upgrade model for this skill
- If the suggestions calendar isn't shared properly, Marvin won't see the events

**New files:**
- `skills/day-planner/SKILL.md` — core day planning skill
- `calendar-helper.py` gains `create-calendar` and `share-calendar` commands

**Modified files:**
- `skills/calendar/SKILL.md` — suggestions calendar docs, new commands, `--calendar-id` on create-event
- `skills/daily-briefing/SKILL.md` — morning negotiation replaces passive schedule reporting
- `workspace/HEARTBEAT.md` — proactive gap-checking and end-of-day review
- `CAPABILITIES.md` — updated capability matrix
