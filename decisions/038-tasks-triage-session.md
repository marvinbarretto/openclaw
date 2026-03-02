# ADR-038: Interactive Tasks Triage Session

## Status

Accepted

## Context

Google Tasks is Marvin's daily scratchpad. `tasks-helper.py` sweeps them into the vault at 05:00 UTC and classifies via Gemini Flash, but many items are cryptic notes-to-self ("fix displaylink thing", "ask dan about X") that Flash can't confidently classify. These land in `vault/needs-context/` and sit there indefinitely with no feedback loop.

The vault already has `prioritise-tasks.py` scoring active tasks (ADR-034) and the triage UI for batch review (ADR-024), but neither addresses the daily trickle of ambiguous items from the tasks sweep.

## Decision

Add an interactive tasks triage session that Jimbo announces in the morning briefing and walks through via Telegram:

1. **Pipeline output:** After classification, `tasks-helper.py` writes `tasks-triage-pending.json` with metadata about items routed to `needs-context/` during this run (filename, raw title, suggested type/tags, confidence score).

2. **Briefing integration:** Section 3.5 in the daily-briefing skill reads the pending file. If items exist, Jimbo announces the count and asks Marvin for a convenient time, then creates a calendar invite via `calendar-helper.py`.

3. **Triage skill:** New `tasks-triage` skill (user-invokable) walks through each item one at a time: presents Jimbo's best guess, waits for Marvin's response, updates frontmatter, and moves the file to `notes/` or `archive/`. Logs the session via `activity-log.py` and cleans up the pending file.

No new scripts or dependencies — the skill uses existing sandbox tools (cat, file writes, activity-log.py, calendar-helper.py).

## Consequences

**Easier:**
- Ambiguous tasks get resolved the same day they're swept, not weeks later
- Jimbo learns from Marvin's corrections (context for future classifications)
- The briefing becomes more interactive — Marvin can schedule the session for a convenient gap
- `needs-context/` stays clean rather than accumulating indefinitely

**Harder:**
- Adds a new required interaction loop — Marvin must respond to triage items (though "skip" is always an option)
- Calendar invite creation adds a step to the briefing flow

**Trade-offs:**
- Triage is interactive via Telegram, not the web UI — this is intentional (quick 15-min session vs. batch review)
- The pending file is ephemeral (deleted after triage) — no historical tracking of triage sessions beyond activity-log.py
