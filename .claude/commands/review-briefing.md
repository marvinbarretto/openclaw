---
description: Review today's briefing quality — pull pipeline data, discuss what worked, capture findings
argument-hint: "[YYYY-MM-DD] (default: today)"
---

# Briefing Review Session

You are running a collaborative review of Jimbo's morning briefing with Marvin. This is a 20-40 minute working session to understand what the briefing did well, what failed, and why.

## Context

Read these before starting:
1. `docs/plans/2026-03-03-briefing-quality-audit.md` — the full audit of known issues (C1-C4, H1-H7, M1-M7, L1-L3)
2. Any previous review files in `docs/reviews/` — read all of them for continuity
3. The current skill prompts that drive the briefing:
   - `skills/sift-digest/SKILL.md` — orchestration + presentation
   - `skills/daily-briefing/SKILL.md` — briefing structure
4. `workspace/SOUL.md` — Jimbo's personality and minimum bar

## Phase 1: Pull Data

Parse the date from `$ARGUMENTS` (default: today, format YYYY-MM-DD).

SSH to the VPS and pull today's pipeline data. Run these commands via `ssh jimbo`:

```bash
# Experiment tracker: all runs for this date
docker exec $(docker ps -q --filter name=openclaw-sbx) python3 /workspace/experiment-tracker.py runs --days 1

# Activity log: briefing entries
docker exec $(docker ps -q --filter name=openclaw-sbx) python3 /workspace/activity-log.py list --days 1 --type briefing

# Email digest metadata (date, count)
docker exec $(docker ps -q --filter name=openclaw-sbx) python3 -c "import json; d=json.load(open('/workspace/email-digest.json')); print(f'Date: {d[\"date\"]}'); print(f'Emails: {len(d.get(\"items\",[]))}')"
```

If any command fails, note it and move on. Partial data is fine.

Present a brief summary of what the pipeline produced:
- Did the triage worker run? How many emails → how many shortlisted?
- Did the newsletter reader run? How many gems?
- Did the conductor log a briefing-synthesis run? What was its self-rating?
- Any failures or fallbacks?

## Phase 2: Get the Briefing

Ask Marvin to paste the actual Telegram briefing output. If he's already pasted it, use that.

Once you have it, read it carefully. Compare what Jimbo produced against:
- The daily-briefing skill's required sections (calendar, day plan, vault tasks, email highlights, surprise game)
- The audit's known issues — did any of the C1-C4 critical issues manifest?
- SOUL.md's "Morning Briefing Minimum Bar"

Present your analysis. Be specific:
- "He proposed a day plan — good, this was missing last week"
- "Email section is just subject lines again — this is issue C2, no examples in the prompt"
- "No vault tasks surfaced — the grep command probably failed"
- "Surprise game was skipped entirely"

Don't be exhaustive. Hit the 3-4 most important observations, then let Marvin react.

## Phase 3: Discussion

This is the core of the session. Let it flow naturally. Marvin will share what landed, what was useless, what he wished was there.

Your job:
- Listen and reflect back what you hear
- Connect his feedback to specific root causes (prompt issues, context gaps, model limitations, architectural problems)
- Reference the audit when relevant ("this connects to issue H5 — the reader prompt doesn't prioritise time-sensitive items")
- Note when something contradicts previous assumptions
- Capture "aha" moments — things that change our understanding of what a good briefing is

Don't rush to solutions. Understanding the problem is the point.

## Phase 4: Write It Up

At the end of the session, write a journal entry to `docs/reviews/YYYY-MM-DD.md`.

The format is free-form. Let the content determine the structure. But typically include:
- What the briefing contained (brief summary)
- What Marvin's reaction was (his words, not your interpretation)
- What we learned (observations, patterns, surprises)
- Root causes identified (linked to audit issues where relevant)
- Action items if any emerged (concrete changes to make)
- Questions for next time (things to watch for)

**Do not force a template.** If the session was all about one thing (e.g., "the day plan is the whole point"), the entry should reflect that depth rather than covering every section shallowly.

After writing, show Marvin the entry and ask if it captures the session accurately. Edit based on his feedback, then commit.

## Principles

- **This is discovery, not measurement.** We're learning what "good" means, not scoring against a fixed rubric.
- **Marvin's raw reaction is the most valuable data.** Capture his words, not just your analysis.
- **Connect feedback to causes.** "The email section was bad" is a symptom. "The triage worker doesn't see PRIORITIES.md" is a cause.
- **Look for patterns across sessions.** If the same complaint appears twice, it's a pattern worth capturing.
- **Don't propose solutions unless asked.** Sometimes understanding is enough for one session.
- **Be honest about what you don't know.** "I'm not sure if this is a prompt issue or a model capability issue — we'd need to see the LangFuse trace" is fine.
