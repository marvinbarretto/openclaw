# Briefing Review Process — Design

*2026-03-04*

## What This Is

A Claude Code skill (`/review-briefing`) that drives a 20-40 minute working session after each morning briefing. The goal is to discover what a good briefing actually means for Marvin, through iterative review and reflection.

## Why

Jimbo's briefings have been comprehensively poor (see `docs/plans/2026-03-03-briefing-quality-audit.md`). But we don't have a clear picture of what "good" looks like in practice — only symptoms of what's bad. The review process is how we discover the bar by iterating towards it.

## The Session

Each review session has a loose structure, not a rigid template:

**I pull in data:**
- SSH to VPS: experiment-tracker logs for today's `briefing-synthesis`, `email-triage`, `newsletter-deep-read` runs
- SSH to VPS: activity-log entries for today's briefing
- The audit document (`docs/plans/2026-03-03-briefing-quality-audit.md`) as a reference frame
- Memory of previous review sessions

**Marvin pastes the briefing** from Telegram.

**We talk about it:**
- I present my analysis: what the prompts told Jimbo to do, what the workers produced, where quality dropped
- Marvin gives his raw reaction: what helped, what was noise, what was missing
- We discuss root causes: prompt issue? context issue? model capability?
- We identify concrete actions if any are obvious

**I write it up** as a journal entry.

## Output

Journal-style markdown files:

```
docs/reviews/
  2026-03-04.md
  2026-03-05.md
  ...
```

No fixed frontmatter schema yet. Structure will emerge from the content as patterns become clear. Early entries will be free-form observations. Later entries may develop recurring sections.

The journal entries capture:
- What the briefing contained and how it was received
- Observations about what matters and what doesn't
- Root cause analysis of specific failures
- "Aha" moments about what a good briefing could be
- Action items when obvious (prompt changes, context updates)

## What This Is NOT

- Not a dashboard or rating widget
- Not a structured checklist (yet — structure may emerge)
- Not public (yet — content may eventually feed a blog or site page)
- Not automated — this is a human + AI collaborative review

## How Findings Feed Back

1. **Directly:** Action items from a session get applied to prompts/configs in the same or next session
2. **Patterns:** After several sessions, recurring observations become prompt changes or architectural decisions
3. **Context:** The review files themselves become context that the skill reads to inform future sessions ("last time we noticed X, did it improve?")

## Data Sources

| Source | Access | What It Provides |
|--------|--------|------------------|
| Telegram briefing | Marvin pastes it | The actual output to review |
| experiment-tracker.db | SSH to VPS, `python3 experiment-tracker.py runs --task briefing-synthesis --days 1` | Conductor rating, reasoning, token usage |
| experiment-tracker.db | SSH to VPS, `python3 experiment-tracker.py runs --task email-triage --days 1` | Triage stats, shortlist count |
| experiment-tracker.db | SSH to VPS, `python3 experiment-tracker.py runs --task newsletter-deep-read --days 1` | Gems count, links found, skipped count |
| activity-log.db | SSH to VPS, `python3 activity-log.py list --days 1 --type briefing` | Outcome, rationale, satisfaction if rated |
| Audit document | Local file | Reference frame of known issues |
| Previous reviews | Local files in docs/reviews/ | Continuity, pattern tracking |

## Skill Design

The `/review-briefing` skill is a Claude Code custom command. It:
1. Knows how to SSH and pull VPS data
2. Knows the audit findings and can reference specific issues (C1, C2, etc.)
3. Reads previous review files for continuity
4. Guides the conversation without forcing a rigid structure
5. Writes the journal entry at the end

The skill prompt should be conversational, not procedural. It sets up the context and lets the discussion flow.

## Evolution Path

- **Now:** Markdown journal entries, free-form
- **Week 2-3:** Patterns emerge, we add light frontmatter (date, overall impression, key theme)
- **Month 2:** Enough data to build a site page that summarises findings and tracks improvement
- **Eventually:** Findings feed into an automated prompt-improvement pipeline
