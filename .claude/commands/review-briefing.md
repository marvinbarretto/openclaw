---
description: Review today's briefing quality — pull pipeline data, discuss what worked, capture findings
argument-hint: "[YYYY-MM-DD] (default: today)"
---

# Briefing Review Session

A 20-40 minute collaborative review of Jimbo's briefing with Marvin. Understand what worked, what failed, and why.

## Context

Read these before starting:
1. `docs/reviews/HISTORY.md` — the review arc, resolved/open issues, patterns
2. Recent files in `docs/reviews/` — read the last 2-3 for continuity
3. `skills/daily-briefing/SKILL.md` — briefing structure and rules
4. `workspace/SOUL.md` — personality and "Morning Briefing Minimum Bar"

## Phase 1: Pull Data

Parse the date from `$ARGUMENTS` (default: today, format YYYY-MM-DD).

Pull data from three sources. Read the API key from project memory (MEMORY.md).

### 1. Health endpoint (primary — one call gets everything)

```bash
API_KEY="<read from MEMORY.md>"
BASE="https://167.99.206.214/api"

# This single call returns: overall status, issues, pipeline stats, tool health,
# email quality, vault stats, costs, activity, experiments, file ages, model, tokens, duplicates
curl -sk -H "X-API-Key: $API_KEY" "$BASE/health"

# Trends — shows streaks and recurring issues across days
curl -sk -H "X-API-Key: $API_KEY" "$BASE/health/trends?days=7"
```

### 2. VPS files (content not available via API — only file ages are in health)

```bash
# Pipeline assembly — the detailed gem/calendar/vault data
ssh jimbo 'cat /home/openclaw/.openclaw/workspace/briefing-input.json'

# Opus analysis (optional — missing is normal, means Mac was asleep)
ssh jimbo 'cat /home/openclaw/.openclaw/workspace/briefing-analysis.json 2>/dev/null'
```

### 3. Fallback (only if health endpoint fails)

```bash
curl -sk -H "X-API-Key: $API_KEY" "$BASE/activity?days=1"
curl -sk -H "X-API-Key: $API_KEY" "$BASE/costs/summary?days=1"
curl -sk -H "X-API-Key: $API_KEY" "$BASE/emails/reports?limit=20"
curl -sk -H "X-API-Key: $API_KEY" "$BASE/vault/stats"
curl -sk -H "X-API-Key: $API_KEY" "$BASE/settings"
curl -sk -H "X-API-Key: $API_KEY" "$BASE/context/files"
```

If any call fails, note it and move on. Partial data is fine.

**Present a structured summary (mapped to health endpoint fields):**
- **Overall:** `health.overall` + `health.issues[]` — start with what's broken
- **Pipeline:** `health.pipeline.morning/afternoon` — ran?, delivered?, email/gem/insight/calendar/vault counts
- **Email:** `health.email` — reports today, insight quality (how many have actual content vs null fields)
- **Tools:** `health.tools` — vault_reader/roulette/connector success rates and last outcomes
- **Vault:** `health.vault` — active/done/velocity/priority buckets
- **Opus:** `health.files.briefing_analysis` — age + stale flag
- **Costs:** `health.costs` — today, month, budget %
- **Model:** `health.model` — what model is running right now
- **Tokens:** `health.tokens.warnings` — any expiring soon?
- **Duplicates:** `health.duplicates` — any repeated messages today?
- **Trends:** `trends.streaks` — how many days has vault_reader been critical? Top recurring issues?
- **Context:** Check `$BASE/context/files` for priorities/interests if needed for briefing evaluation

## Phase 2: Get the Briefing

Ask Marvin to paste the actual Telegram briefing output. If he's already pasted it, use that.

Read it carefully. Compare against:
- The daily-briefing skill's required sections (calendar, day plan, vault tasks, email highlights, surprise game)
- SOUL.md's "Morning Briefing Minimum Bar"
- The open issues in HISTORY.md — did any manifest today?
- The current priorities from the context API — did the briefing connect to what matters?

Present your analysis. Be specific:
- "He proposed a day plan with exposed reasoning — this was missing in sessions 1-3"
- "Email section highlights 3 items with WHY explanations — quality is improving"
- "Calendar said 'no events' but briefing-input.json has 12 — this is the session 4 bug recurring"
- "No vault tasks surfaced"
- "Surprise game was skipped"

Hit the 3-4 most important observations, then let Marvin react.

## Phase 3: Discussion

The core of the session. Let it flow naturally. Marvin shares what landed, what was useless, what he wished was there.

Your job:
- Listen and reflect back what you hear
- Connect feedback to specific root causes (prompt issues, context gaps, model limitations, architecture)
- Reference HISTORY.md patterns when relevant ("this is the same calendar issue from session 4")
- Cross-reference with API data ("the experiment tracker shows Flash shortlisted 0 again — that's 6 sessions running")
- Note when something contradicts previous assumptions
- Capture "aha" moments — things that change our understanding of what a good briefing is

Don't rush to solutions. Understanding the problem is the point.

## Phase 4: Write It Up

At the end of the session, write two things:

### 1. Session entry: `docs/reviews/YYYY-MM-DD.md`

Free-form. Let the content determine the structure. Typically includes:
- What the briefing contained (brief summary)
- What Marvin's reaction was (his words, not your interpretation)
- What we learned (observations, patterns, surprises)
- Root causes identified (linked to HISTORY.md open issues where relevant)
- Action items if any emerged
- Questions for next session

**Do not force a template.** If the session was all about one thing, the entry should reflect that depth.

### 2. Update `docs/reviews/HISTORY.md`

- Add a session summary to "The Arc" section
- Move any resolved issues from "Open Issues" to "Resolved Issues"
- Add any new open issues
- Update "Current Architecture" if the architecture changed
- Add any new patterns to "Patterns"

After writing both, show Marvin the session entry and ask if it captures the session accurately. Edit based on his feedback, then commit both files.

## Principles

- **This is discovery, not measurement.** We're learning what "good" means, not scoring against a fixed rubric.
- **Marvin's raw reaction is the most valuable data.** Capture his words, not just your analysis.
- **Connect feedback to causes.** "The email section was bad" is a symptom. "Flash shortlists 0 every time" is a cause.
- **Look for patterns across sessions.** If the same complaint appears in HISTORY.md and today, it's entrenched.
- **Use the API data.** If the experiment tracker shows a pattern, surface it. If costs spiked, mention it. The data is there — use it.
- **Don't propose solutions unless asked.** Sometimes understanding is enough for one session.
- **Be honest about what you don't know.** "I'm not sure if this is a prompt issue or a model issue — we'd need to see the LangFuse trace" is fine.
- **Missing Opus analysis is expected.** It depends on the Mac being awake. Not a failure — just means Jimbo self-composed.
