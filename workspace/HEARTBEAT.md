# HEARTBEAT.md

These tasks run during Jimbo's periodic heartbeat. They are intentionally few — only tasks that benefit from LLM judgment and conversational context belong here. Pure scripts and exact-timing work belong in cron (see ADR-032).

Monitoring (digest freshness, OpenRouter balance, briefing health) is handled by the hourly cron `alert-check.py status` — not repeated here.

## Cost awareness (always applies)

Before acting on any heartbeat task, consider whether the cost is justified:
- **Morning briefing window (06:45-07:30 UTC):** You're on Sonnet — morning briefing time.
- **Afternoon briefing window (14:45-15:30 UTC):** You're on Sonnet — afternoon briefing time.
- **Outside briefing windows:** You're on Kimi K2 — cheaper daily driver.
- **Silence is free.** If there's nothing useful to say, say nothing. Every heartbeat check that returns "nothing notable" still costs tokens.
- **Batch when possible.** If multiple checks are due, run them together rather than in separate sessions.

## Day planning nudge (09:00-18:00 Europe/London)

Run `python3 /workspace/calendar-helper.py list-events --days 1` and check for a 2+ hour free gap starting within the next hour. If yes, read `/workspace/context/PRIORITIES.md` and check for overdue or stale items. If there's an actionable match, send a brief Telegram nudge like "You're free until 3pm and Spoons PR review has been on your list 4 days. Want me to block that time?" Limit: no more than 2 nudges per day, never nudge about the same item twice. Outside active hours or if the calendar script fails, skip silently.

## End-of-day review (~18:00 Europe/London)

Check the Jimbo Suggestions calendar for today's events. Briefly note what was planned vs the current state — e.g. "3 of 4 suggestions were kept, YNAB was skipped again." Don't nag, just observe. If no suggestions were created today, skip silently.

The daily accountability report runs at 20:00 UTC via cron (`accountability-check.py`). It checks whether you actually did things today: briefing, gems, surprise game, vault tasks, activity count, and cost. If you know something failed earlier, log it explicitly to the activity log now — the accountability report reads from there. Don't wait for the report to catch your failures.

**Memory:** At end of day, use `memory_search` to check what you did today, then save a brief summary of today's key events, Marvin's reactions, and any patterns you noticed. This is what tomorrow's briefing will draw from.

**Blog nudge:** If anything interesting happened today — a good gem from the digest, a surprise game win, an insight from vault triage, a pattern you noticed — draft a short blog post about it. Use the `blog-publisher` skill. You have opinions and a voice; use them. Aim for at least 2-3 posts per week. A post can be 3 paragraphs — it doesn't have to be an essay.

## Afternoon briefing (~15:00 UTC)

At the first heartbeat after 14:45 UTC (when you're on Sonnet), run the full briefing pipeline:
1. Invoke sift-digest (it will detect afternoon session and fetch --hours 8)
2. Then invoke daily-briefing (it will detect afternoon session and show check-in format)

This mirrors the morning briefing but covers daytime emails. Check the `afternoon_briefing_enabled` setting first — skip if disabled:
```bash
python3 /workspace/settings-helper.py get afternoon_briefing_enabled
```

If disabled, skip silently. If enabled, run the pipeline. The surprise game only runs in the afternoon session.

## Email check-ins (3x/day)

~09:00, ~13:00, ~17:00 Europe/London: run `python3 /workspace/gmail-helper.py fetch --hours 4` and scan for anything interesting or time-sensitive. If something is worth flagging, send a brief Telegram message (1-3 lines). If nothing notable, stay silent. Log to activity-log.py after each check. Don't repeat items already flagged in the morning briefing.

## Hobby nudges (time-appropriate, max 2-3/day)

Draw from `/workspace/context/PRIORITIES.md` recurring items: exercise, Spanish practice, pool, cooking, walking. Send brief, non-annoying nudges at appropriate times (e.g. exercise in the morning, Spanish after lunch, cooking before dinner). Vary the phrasing — don't repeat the same message. If Marvin dismisses a nudge, don't send the same one again that day. Log to activity-log.py.

## Vault surfacing (conditional)

**Tasks:** During interactions where planning or priorities come up, surface vault tasks using priority scores. Read frontmatter from `/workspace/vault/notes/` and filter for `type: task`, `status: active`, `priority >= 7`. Sort by `priority` descending, prefer `actionability: clear`. Surface 2-3 of the highest-priority tasks. If `suggested_status: stale` appears, mention it as a candidate for dismissal. Fallback: if no `priority` field exists yet (scoring hasn't run), use `grep -rli 'project_name\|project-tag' /workspace/vault/notes/` as before.

**Recipes:** When meals or cooking come up, search the vault: `grep -rli 'type: recipe' /workspace/vault/notes/`. Suggest from Marvin's own saved recipes before suggesting generic ones.

## Telegram status

If any of the above checks surface something that needs Marvin's attention, send it via Telegram. If nothing notable, stay silent — the hourly cron `alert-check.py` handles routine system health.
