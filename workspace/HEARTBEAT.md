# HEARTBEAT.md

# Existing monitoring tasks
- Check `/workspace/email-digest.json`: If the file exists and `generated_at` is more than 24 hours old, tell Marvin the email digest is stale — the VPS cron (daily 06:00 UTC) may have failed. Check `/var/log/gmail-fetch.log` for errors.
- If email digest was updated since the last heartbeat, briefly mention how many emails are in the digest and how many are queued for reading
- Check if any token expiry dates in `/workspace/CAPABILITIES.md` are within 14 days - warn Marvin if so
- Check context file freshness: if `/workspace/context/PRIORITIES.md` is >10 days old or `/workspace/context/GOALS.md` is >45 days old, remind Marvin to update them
- Check calendar health: run `python3 /workspace/calendar-helper.py list-calendars`. If the script fails with a token error, warn Marvin that the Google Calendar token needs refreshing (re-run `calendar-auth.py` on laptop). If the script doesn't exist, skip silently.
- Proactive day planning nudge (09:00-18:00 Europe/London only): run `python3 /workspace/calendar-helper.py list-events --days 1` and check if there's a 2+ hour free gap starting within the next hour. If yes, read `/workspace/context/PRIORITIES.md` and check for overdue or stale items. If there's an actionable match, send a brief Telegram nudge like "You're free until 3pm and Spoons PR review has been on your list 4 days. Want me to block that time?" Limit: no more than 2 nudges per day, never nudge about the same item twice in a day. Outside active hours or if the calendar script fails, skip silently.
- End-of-day review (~18:00 Europe/London): check the Jimbo Suggestions calendar for today's events. Briefly note what was planned vs the current state — e.g. "3 of 4 suggestions were kept, YNAB was skipped again." Don't nag, just observe. If no suggestions were created today, skip silently.
- Auto-commit workspace changes: run `cd /workspace && git add -A && git diff --cached --quiet || (git commit -m "Auto: $(date +%Y-%m-%d\ %H:%M)" && git push)`. Silently commits and pushes any changed files (memories, diary, blog posts). If no changes, do nothing. If push fails, tell Marvin. Never show output unless it fails.

# Active daytime tasks (ADR-028)

## Email check-ins (3x/day)
- ~09:00, ~13:00, ~17:00 Europe/London: run `python3 /workspace/gmail-helper.py fetch --hours 4` and scan for anything interesting or time-sensitive. If there's something worth flagging, send a brief Telegram message (1-3 lines). If nothing notable, stay silent. Log to activity-log.py after each check. Don't repeat items already flagged in the morning briefing.

## Project reflection (daily, during morning briefing or first chat)
- Ask Marvin one or two of these questions, rotating through them. Don't ask all at once — pick whichever feels relevant to what's active:
  - "Should we build or refactor?"
  - "What should we refactor?"
  - "Now that you haven't built this yet, what would you have done differently?"
  - "Any questions for me?"
- Adapt the question to the current project context (Spoons, LocalShout, OpenClaw, etc.). Keep it brief — this is a check-in, not a planning session.

## Interest research (~11:00 daily)
- Pick ONE topic from `/workspace/context/INTERESTS.md` that hasn't been researched recently. Do a quick investigation — look for news, events, or developments. If you find something genuinely interesting, consider blogging about it or logging it to recommendations-helper.py. Log to activity-log.py with what you found (or that nothing stood out). Rotate topics — don't research the same thing two days in a row.

## Hobby nudges (time-appropriate, max 2-3/day)
- Draw from `/workspace/context/PRIORITIES.md` recurring items: exercise, Spanish practice, pool, cooking, walking. Send brief, non-annoying nudges at appropriate times (e.g. exercise in the morning, Spanish after lunch, cooking before dinner). Vary the phrasing — don't repeat the same message. If Marvin dismisses a nudge, don't send the same one again that day. Log to activity-log.py.

## Cost logging (every heartbeat)
- After every heartbeat cycle, estimate the tokens used and log to cost-tracker.py: `python3 /workspace/cost-tracker.py log --provider <provider> --model <model> --task heartbeat --input-tokens <est> --output-tokens <est>`. Do this for ALL interactions, not just heartbeats — briefings, chats, research, everything.

## End-of-day cost summary (~22:00 Europe/London)
- Run `python3 /workspace/cost-tracker.py budget --check`. If over the alert threshold, warn Marvin. Otherwise, just log the day's total silently.
- Run `python3 /workspace/cost-tracker.py summary --days 1` and note it in your diary.

## Weekly cost + activity report (Sundays ~10:00)
- Run `python3 /workspace/cost-tracker.py summary --days 7` and `python3 /workspace/activity-log.py stats --days 7`.
- Summarise the week: total cost, busiest day, most common activity type, average satisfaction (if any rated), notable outcomes.
- Consider writing a brief blog post about the week if there's anything interesting to share.

## Dashboard data export (every auto-commit cycle)
- Before the auto-commit step, export fresh data for the dashboard:
  - `python3 /workspace/cost-tracker.py export --days 30 --format json > /workspace/jimbo-costs.json`
  - `python3 /workspace/activity-log.py export --days 30 --format json > /workspace/jimbo-activities.json`
- These files get auto-committed and pushed, making them available for the dashboard.
