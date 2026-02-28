# HEARTBEAT.md

These tasks run during Jimbo's periodic heartbeat. They are intentionally few — only tasks that benefit from LLM judgment and conversational context belong here. Pure scripts and exact-timing work belong in cron (see ADR-032).

Monitoring (digest freshness, OpenRouter balance, briefing health) is handled by the hourly cron `alert-check.py status` — not repeated here.

## Day planning nudge (09:00-18:00 Europe/London)

Run `python3 /workspace/calendar-helper.py list-events --days 1` and check for a 2+ hour free gap starting within the next hour. If yes, read `/workspace/context/PRIORITIES.md` and check for overdue or stale items. If there's an actionable match, send a brief Telegram nudge like "You're free until 3pm and Spoons PR review has been on your list 4 days. Want me to block that time?" Limit: no more than 2 nudges per day, never nudge about the same item twice. Outside active hours or if the calendar script fails, skip silently.

## End-of-day review (~18:00 Europe/London)

Check the Jimbo Suggestions calendar for today's events. Briefly note what was planned vs the current state — e.g. "3 of 4 suggestions were kept, YNAB was skipped again." Don't nag, just observe. If no suggestions were created today, skip silently.

## Email check-ins (3x/day)

~09:00, ~13:00, ~17:00 Europe/London: run `python3 /workspace/gmail-helper.py fetch --hours 4` and scan for anything interesting or time-sensitive. If something is worth flagging, send a brief Telegram message (1-3 lines). If nothing notable, stay silent. Log to activity-log.py after each check. Don't repeat items already flagged in the morning briefing.

## Hobby nudges (time-appropriate, max 2-3/day)

Draw from `/workspace/context/PRIORITIES.md` recurring items: exercise, Spanish practice, pool, cooking, walking. Send brief, non-annoying nudges at appropriate times (e.g. exercise in the morning, Spanish after lunch, cooking before dinner). Vary the phrasing — don't repeat the same message. If Marvin dismisses a nudge, don't send the same one again that day. Log to activity-log.py.

## Vault surfacing (conditional)

**Tasks:** During interactions where planning or priorities come up, search the vault for matching tasks: `grep -rli 'project_name\|project-tag' /workspace/vault/notes/`. Surface 2-3 actionable vault tasks that align with current context. Don't overwhelm — pick the most actionable ones.

**Recipes:** When meals or cooking come up, search the vault: `grep -rli 'type: recipe' /workspace/vault/notes/`. Suggest from Marvin's own saved recipes before suggesting generic ones.

## Telegram status

If any of the above checks surface something that needs Marvin's attention, send it via Telegram. If nothing notable, stay silent — the hourly cron `alert-check.py` handles routine system health.
