# ADR-034: Vault Task Prioritisation

## Status

Accepted

## Context

The vault has ~511 active tasks but no way to distinguish "Subdomain Watford events" (active project, clear action) from "Get a wash on" (trivial, probably stale) or "Gregory" (just a name). Jimbo surfaced tasks via raw `grep` — no scoring, no staleness detection, no lifecycle. Morning briefings either skipped vault tasks entirely or picked random ones with no relevance to current priorities.

We needed an algorithm-driven scoring system that ranks tasks against PRIORITIES.md and GOALS.md so Jimbo surfaces the right 2-3 each morning.

## Decision

A `prioritise-tasks.py` script runs daily on VPS at 04:30 UTC via cron. Gemini Flash batch-scores all active tasks against context files. Scores are written back into each note's YAML frontmatter. Jimbo reads pre-scored tasks at briefing time instead of grep-and-guessing.

### How it works

- **Input:** All vault notes with `type: task` and `status: active` (~511 notes)
- **Scoring model:** Gemini Flash via Google AI API (cheap, fast, good enough for scoring)
- **Batching:** 5 tasks per API call (~102 calls per full run). System prompt includes full PRIORITIES.md + GOALS.md once per call. 1-second sleep between batches to avoid rate limits.
- **Skip-if-fresh:** Notes scored after the latest context file change are skipped. `--force` bypasses this.
- **Cost:** ~$0.02 per full run

### Frontmatter fields written

| Field | Type | Meaning |
|-------|------|---------|
| `priority` | 1-10 int | 9-10: urgent + goal-aligned. 7-8: clearly relevant. 5-6: vaguely relevant. 3-4: low relevance. 1-2: stale/trivial |
| `priority_reason` | string | One-line explanation |
| `actionability` | enum | `clear` / `vague` / `needs-breakdown` |
| `suggested_status` | optional | `stale` only — advisory, never auto-applied |
| `scored` | date | Set by script, not by Flash |

### CLI

```
python3 prioritise-tasks.py                    # score tasks, skip fresh
python3 prioritise-tasks.py --dry-run          # preview without writing
python3 prioritise-tasks.py --force            # re-score everything
python3 prioritise-tasks.py --limit 50         # process first N tasks
python3 prioritise-tasks.py --stats            # show scoring distribution
```

### Pipeline integration

Daily sequence: **04:30 score** → 05:00 tasks sweep → 06:00 email → 07:00 briefing

Skills updated to use scored fields:
- `daily-briefing` — filters `priority >= 7`, `actionability: clear`, weaves into day plan
- `day-planner` — same filter, sorts by priority descending
- `HEARTBEAT.md` — vault surfacing uses priority scores, falls back to grep

### Key design choices

- Batch size 5 (not 10) — Flash sometimes returned single objects instead of arrays with larger batches
- `suggested_status: stale` is advisory only — the script never moves or archives notes
- `key_order` updated in `tasks-helper.py` and `process-inbox.py` so new fields survive future frontmatter rewrites

## Consequences

### Easier
- Briefings surface genuinely relevant tasks instead of random grep hits
- Staleness detection flags tasks that should probably be dismissed
- Scoring is transparent — `priority_reason` explains every score
- `--stats` gives a quick distribution view

### Harder
- Depends on Gemini Flash API availability (free tier, rate limits)
- Full re-score takes ~3 minutes and ~102 API calls
- Scores go stale when context changes (mitigated by skip-if-fresh logic)
