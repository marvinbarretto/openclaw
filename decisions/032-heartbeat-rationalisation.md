# ADR-032: Heartbeat Rationalisation

## Status

Accepted

## Context

HEARTBEAT.md has grown to ~20 tasks. OpenClaw docs recommend 3-6 focused checks that benefit from conversational context. The current heartbeat has three problems:

1. **Most tasks don't need LLM context.** Pure script work (auto-commit, balance check, data export, cost logging) runs identically every time — no judgment required. These are better as cron jobs.

2. **Some tasks need exact timing, not heartbeat cadence.** Daily plan at 08:30, interest research at 11:00, and weekly reports need specific scheduling, not "whenever the heartbeat fires." These should be cron-triggered isolated sessions or part of the morning briefing skill.

3. **Hourly cost with no visible signal.** Marvin has been paying for hourly heartbeats processing 20 tasks but getting zero Telegram messages — either `HEARTBEAT_OK` is suppressed or tasks fail silently. Meanwhile, the cron-based `alert-check.py` (ADR-030, ADR-031) already sends hourly Telegram status messages covering digest freshness, briefing health, and OpenRouter credits.

The hourly cron status check (`alert-check.py status`) was deployed in late February 2026 but not formally documented in an ADR. This decision captures both the heartbeat slimming and the cron status formalisation.

## Decision

### Slim heartbeat to 6 contextual tasks

Keep only tasks that genuinely benefit from LLM judgment, conversational context, and Jimbo's personality:

1. **Day planning nudge** (09:00-18:00) — reads calendar + priorities, decides if worth nudging about a free gap
2. **End-of-day review** (~18:00) — reviews what was planned vs done, observes patterns
3. **Email check-ins** (3x/day) — scans recent inbox, judges what's interesting or time-sensitive
4. **Hobby nudges** (time-appropriate, max 2-3/day) — light, contextual, varied phrasing
5. **Vault task/recipe surfacing** — conditional, uses context awareness to match priorities
6. **Attention-worthy alerts** — if anything from the above checks needs Marvin's attention, send a Telegram message

### Move to cron (scripts, no LLM needed)

These are pure scripts that produce identical output regardless of context:

- Auto-commit workspace changes
- Dashboard data export
- End-of-day cost summary
- Weekly cost + activity report

### Move to cron or briefing skill (need exact timing or heavy processing)

- Daily plan at ~08:30 → cron-triggered isolated session (day-planner skill)
- Interest research at ~11:00 → cron-triggered isolated session
- Project reflection questions → morning briefing skill
- Token expiry check → add to `alert-check.py` (future)
- Context file freshness check → add to `alert-check.py` (future)
- Calendar health check → add to `alert-check.py` (future)

### Drop entirely (already covered by hourly cron)

These are now handled by `alert-check.py status` running hourly via cron:

- Digest staleness check
- Digest update count mention
- OpenRouter balance check
- Cost logging per heartbeat

### Formalise hourly cron status

The existing hourly cron job (`alert-check.py status`) is the primary monitoring system:

```
0 * * * * ... python3 /workspace/alert-check.py status
```

This checks digest freshness, briefing health, and OpenRouter credits. It sends a Telegram message on success (positive heartbeat) and on failure. This replaces the LLM-based equivalents in HEARTBEAT.md.

## Consequences

### What gets better

- **Lower cost:** ~6 focused tasks vs ~20 means significantly fewer input tokens per heartbeat tick
- **Visible signal:** Cron-based alerts actually send Telegram messages; heartbeat was producing nothing visible
- **Clear separation:** LLM does judgment work, cron does script work — each system plays to its strengths
- **Faster heartbeats:** Smaller prompt = faster processing = more responsive to real-time context

### What gets harder

- Cron jobs for auto-commit, dashboard export, cost summary, and weekly report still need to be set up on VPS (future work — not done in this change)
- Daily plan and interest research sessions need cron-triggered openclaw invocations (future work)
- Three additional checks (token expiry, context freshness, calendar health) should be added to `alert-check.py` (future work)

### Follow-up items

1. Add auto-commit cron job to VPS
2. Add dashboard data export cron job
3. Add end-of-day cost summary cron job
4. Add weekly cost + activity report cron job (Sundays)
5. Set up cron-triggered isolated sessions for daily plan (~08:30) and interest research (~11:00)
6. Add token expiry, context file freshness, and calendar health checks to `alert-check.py`
7. Move project reflection questions into the daily-briefing skill
