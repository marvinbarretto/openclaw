# ADR-028: Active Heartbeat with Cost and Activity Tracking

## Status

Accepted

## Context

Jimbo runs on a ~30 minute heartbeat but is mostly passive — checking for stale files, token expiry, and nudging occasionally. Marvin wants Jimbo to become an active daytime companion: checking email multiple times per day, researching interests, nudging on habits, pursuing his own projects. But more activity means more cost, so we need visibility into what Jimbo is doing and how much it costs.

We need:
1. **Cost tracking** — log every API interaction with token counts and estimated cost
2. **Activity logging** — record what Jimbo does, outcomes, and satisfaction scores
3. **Budget controls** — monthly limits with alerts so costs don't spiral
4. **Dashboard** — a web UI on Marvin's personal site to monitor costs and activity
5. **Expanded heartbeat** — more tasks throughout the day (email 3x, research, nudges)

## Decision

### SQLite helpers (same pattern as recommendations-helper.py)

Two new workspace scripts:
- `cost-tracker.py` — logs provider, model, task type, token counts, estimated USD cost. Supports budgets with alert thresholds.
- `activity-log.py` — logs task type, description, outcome, model used, optional satisfaction rating (1-5, set by Marvin).

Both follow the established pattern: stdlib-only Python, SQLite DB next to the script, CLI interface with subcommands, JSON output.

### Cost rates hardcoded

Rather than fetching live pricing, we hardcode rates per model (per 1M tokens). This is simpler, works offline, and rates change rarely. Current rates:
- Gemini 2.5 Flash: $0.15 input, $0.60 output
- Claude Haiku 4.5: $0.80 input, $4.00 output

### Expanded heartbeat

HEARTBEAT.md gains new tasks:
- Email check-ins 3x/day (~09:00, ~13:00, ~17:00)
- Interest research (~11:00 daily)
- Hobby nudges (2-3/day, time-appropriate)
- Cost logging after every heartbeat
- End-of-day cost summary (~22:00)
- Weekly cost + activity report (Sundays ~10:00)

### Dashboard on personal site

Static Astro pages at `/app/jimbo/` on `site.marvinbarretto.workers.dev`, protected by Cloudflare Access. For the first slice, pages load data from a static JSON export that Jimbo generates during his heartbeat auto-commit. A proper API can come later.

### Skills

Two new skills teach Jimbo when and how to use the trackers:
- `cost-tracker/SKILL.md` — log costs after every API interaction
- `activity-log/SKILL.md` — log activities after every meaningful task

## Consequences

**What becomes easier:**
- Full visibility into what Jimbo does and what it costs
- Budget controls prevent cost surprises
- Satisfaction scoring creates a feedback loop to improve Jimbo's behaviour
- Dashboard gives Marvin a single place to monitor everything
- Pattern is extensible — any new data source follows the same SQLite → JSON export → dashboard flow

**What becomes harder:**
- More heartbeat tasks means more API calls (but we're tracking that now)
- Token count estimation is imprecise — but direction is more important than precision
- Two more SQLite databases to manage in the workspace
- Dashboard data is slightly stale (exported on heartbeat cycle, not real-time) — acceptable for now

**Risks:**
- Jimbo might become chatty or annoying with 3x email checks + nudges. Mitigated by: nudge limits in HEARTBEAT.md, satisfaction scoring feedback.
- Cost tracking adds overhead to every interaction. Mitigated by: it's a single CLI call, ~50ms.
