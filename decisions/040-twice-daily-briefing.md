# ADR-040: Twice-Daily Briefing (Morning + Afternoon)

## Status

Accepted (deployed 2026-03-04)

## Context

The current single morning briefing (07:00 UTC) tries to cover all emails from the past 24 hours in one pass. Problems observed in the 2026-03-04 review session:

1. **Email volume overwhelms triage.** ~120 daily emails in a single digest. The triage worker shortlists aggressively, losing potentially interesting items.
2. **Afternoon emails aren't surfaced until next morning.** Time-sensitive items (event RSVPs, action-required emails like Apple Developer notices) arrive during the day but aren't seen until 07:00 the next day.
3. **The digest overwrites each hourly fetch.** Only the last ~2 hours of email are in the digest at any moment. The morning briefing sees whatever the 06:00 fetch grabbed, not the full day.
4. **Day plan can't course-correct.** The morning plan is set-and-forget — no revisit.

Marvin's instinct: "There should be two digests a day instead of one, morning and afternoon, so emails can be checked twice. That way it's a more manageable chunk."

## Decision

Split the briefing into two daily sessions:

### Morning Briefing (07:00 UTC)
- **Email window:** overnight emails (~18:00 previous day to 07:00)
- **Calendar:** full day view, flag next 2 hours
- **Day plan:** propose 3-5 gap activities
- **Vault tasks:** top 2-3 by priority
- **Tone:** "Here's your day, here's what arrived overnight"

### Afternoon Briefing (~15:00 UTC)
- **Email window:** daytime emails (~07:00 to 15:00)
- **Calendar:** remainder of day, any evening events
- **Day plan revisit:** "You planned X this morning — anything to adjust?"
- **Vault tasks:** only if something changed (new tasks scored, priority shift)
- **Tone:** "Catch-up and course-correct"

### Implementation

**Email fetch:** Stays hourly. Each briefing triggers a fresh fetch with the appropriate `--hours` window before running the pipeline.

**Model swap schedule:**
```
06:45  → Sonnet (morning briefing window)
07:30  → Kimi K2 (daily driver)
14:45  → Sonnet (afternoon briefing window)
15:30  → Kimi K2 (daily driver)
```

**Cron additions (VPS root crontab):**
```bash
# 14:45 — switch to Sonnet for afternoon briefing
45 14 * * * /usr/local/bin/model-swap-local.sh sonnet >> /var/log/model-swap.log 2>&1

# 15:30 — switch back to Kimi K2
30 15 * * * /usr/local/bin/model-swap-local.sh kimi >> /var/log/model-swap.log 2>&1
```

**OpenClaw heartbeat:** Add a second briefing trigger at 15:00. The existing sift-digest + daily-briefing skills work as-is — they read whatever's in the digest and calendar at invocation time.

**gmail-helper.py change:** The `--hours` parameter should be set per-briefing:
- Morning: `--hours 13` (18:00 previous day to 07:00)
- Afternoon: `--hours 8` (07:00 to 15:00)

This could be driven by the sift-digest skill detecting the current hour and adjusting, or by the email-fetch-cron.py running a wider window before each briefing.

**daily-briefing skill changes:**
- Detect morning vs afternoon by current hour
- Afternoon skips the full day plan (already set in the morning) but adds "day plan check-in"
- Afternoon can be lighter — skip vault tasks if no changes, skip recurring nudges

**Experiment tracking:** Each run logs with a `session` field: `morning` or `afternoon`. The briefing check in alert-check.py should expect one run before 08:00 and one before 16:00.

### Cost impact

- One additional Sonnet session per day (~15 min window)
- One additional triage + reader worker run (Flash + Haiku)
- Estimated: ~$0.30-0.50/day extra, well within $15-25/month budget
- Each briefing processes ~60 emails instead of ~120, which should improve triage quality

## Consequences

**Easier:**
- Time-sensitive afternoon emails surfaced same day
- Each digest is a manageable ~60 emails instead of ~120
- Day plan gets a mid-day check-in
- Marvin gets two touchpoints with the system, building the feedback loop faster

**Harder:**
- Two model swap windows to manage in cron
- Need to decide: does the afternoon briefing use the same skill or a separate lighter one?
- alert-check.py needs to expect two briefing runs per day
- Slightly higher daily cost

**Resolved questions:**
- Afternoon uses the same full skill — no lighter version. Keep it simple.
- Surprise game moves to afternoon (better suited — morning is about setup, afternoon is about discovery).
- Afternoon briefing is a Telegram push (proactive). Jimbo should be noisy while we're building him up.
- A setting to disable the afternoon briefing exists but is off by default. Marvin rarely expects to use it.
