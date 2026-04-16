# Workspace File Cleanup Plan

Audit from session 19 (Apr 14). Jimbo's workspace files have diverged from the current direction (reporter not advisor, P0-P3 priorities, tiered automation). This plan addresses every file in `/home/openclaw/.openclaw/workspace/` that Jimbo reads on startup or during heartbeat.

## Critical (do first — these cause failures)

### 1. Delete BOOTSTRAP.md
Causes Jimbo to run "Who am I? Who are you?" on every fresh session. The file says "delete this file after setup" — it's been 6 weeks.

### 2. Rewrite SOUL.md "Morning Briefing Minimum Bar"
The entire section contradicts the daily-briefing skill (session 17). SOUL.md is injected every turn and overrides skill files. Specifically:
- Remove "propose 3-5 activities for free gaps" and "This is the most important part"
- Remove "Surface 2-3 with `priority >= 7`" — old scale, wrong approach
- Replace with a brief pointer: "Follow the daily-briefing skill. Report what you know, don't advise."
- Fix blog section — remove claim that git push works (broken since session 9)

### 3. Fill in IDENTITY.md and USER.md
Both are blank templates. Jimbo doesn't know his own name or Marvin's. Fill in:
- **IDENTITY.md:** Name=Jimbo, Creature=AI assistant, Vibe=direct/opinionated/conversational, Emoji=pick one
- **USER.md:** Name=Marvin, Timezone=Europe/London, key notes about preferences (developer, direct communication, no sycophancy)

### 4. Disambiguate morning-summary vs daily-briefing
Session 18 bug: model picked `morning-summary` instead of `daily-briefing`. Options:
- **Option A:** Rename `morning-summary` to `system-status` to make it clearly different
- **Option B:** Remove `morning-summary` entirely (the daily-briefing skill covers system pulse)
- **Option C:** Make descriptions radically different so the model can't confuse them

## Important (fix the direction)

### 5. Remove day-planning nudge from HEARTBEAT.md
Lines about "propose 3-5 activities" and checking for 2+ hour free gaps contradict the reporter principle. The nudge section can stay but should be reframed: surface data ("You're free until 3pm and X has been on your list 4 days") without proposing what to do about it.

### 6. Fix priority scale everywhere
All references to `priority >= 7` or 1-10 scale need to become P0-P3. Files affected:
- SOUL.md (section 3 of minimum bar)
- HEARTBEAT.md (implicit in nudge logic)
- Any skills that reference priority thresholds

### 7. Remove or disable retired/contradictory skills
- **`sift-digest`** — explicitly marked RETIRED in its own description. Delete.
- **`day-planner`** — "suggest activities for free gaps, negotiate the plan." Contradicts reporter principle. Delete or rewrite.
- **`email-triage-worker`** and **`newsletter-reader-worker`** — sub-agent skills for the old pipeline, now handled by Python cron. Could confuse the model into trying to run them. Delete or mark clearly as "system-only, do not invoke."
- **`calendar-briefing`** — overlaps with daily-briefing calendar section. Evaluate if still needed.

### 8. Fix current-model.txt
Contains `google/gemini-2.5-flash` but actual model is `openrouter/google/gemini-2.5-flash`. SOUL.md tells Jimbo to check this file.

## Maintenance (clean up stale info)

### 9. Update MEMORY.md
Last updated Mar 22 (24 days stale). Contains:
- Outdated operational notes (vault_reader 401, blog git push status)
- Stale "Open Questions / To-Do" section
- No mention of sessions 17-18 changes (reporter principle, priority scale, configuration fracture)
Either update with current state or trim aggressively — Jimbo's memory_search tool supplements this.

### 10. Trim AGENTS.md heartbeat section
Lines 100+ have a generic "Things to check 2-4 times per day" list (email, calendar, weather, mentions) that duplicates and conflicts with the refined HEARTBEAT.md. Remove the generic list, keep the pointer to HEARTBEAT.md.

### 11. Update TROUBLESHOOTING.md
Last updated Feb 28. Missing:
- health-helper.py usage
- Vault API endpoints (`$JIMBO_API_URL/api/vault/...`)
- Priority scale change (P0-P3)
- Common API auth issues (key rotation, 401s)
- Docker container restart procedures

### 12. Populate TOOLS.md
Currently an empty template. Should contain:
- SSH alias: `ssh jimbo`
- API base: `$JIMBO_API_URL` / `jimbo.fourfoldmedia.uk`
- Key env vars in the sandbox
- Helper script inventory (health-helper.py, context-helper.py, calendar-helper.py, etc.)

### 13. Clear heartbeat-state.json
Likely stale from Apr 9. Could cause heartbeat logic to skip checks. Reset or delete so it starts fresh.

## Context from session 19

- OpenClaw updated from 2026.4.9 → 2026.4.12 (Telegram connection fixed)
- Jimbo alive again as of Apr 14 10:07
- Agent was dead Apr 9-14 (5 days) due to broken Telegram long-polling after the 2026.4.9 update
- Pipeline cron healthy — data is good, delivery was the problem
- email_insights has a new bug (`'str' object has no attribute 'get'`) — separate fix needed in briefing-prep.py
- openclaw-readonly token expires Apr 17 — renew or remove

## Deployment

All workspace file changes deploy via:
```bash
./workspace-push.sh
```
Then restart OpenClaw:
```bash
ssh jimbo 'sudo systemctl restart openclaw'
```
