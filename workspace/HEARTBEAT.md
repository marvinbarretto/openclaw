# HEARTBEAT.md

# Keep this file empty (or with only comments) to skip heartbeat API calls.

# Add tasks below when you want the agent to check something periodically.
- Check `/workspace/email-digest.json`: If the file exists and `generated_at` is more than 24 hours old, tell Marvin the email digest is stale and ask him to run the pipeline on his laptop.
- If email digest was updated since the last heartbeat, briefly mention how many emails are in the digest and how many are queued for reading
- Check if any token expiry dates in `/workspace/CAPABILITIES.md` are within 14 days - warn Marvin if so
- Check context file freshness: if `/workspace/context/PRIORITIES.md` is >10 days old or `/workspace/context/GOALS.md` is >45 days old, remind Marvin to update them
- Check calendar health: run `python3 /workspace/calendar-helper.py list-calendars`. If the script fails with a token error, warn Marvin that the Google Calendar token needs refreshing (re-run `calendar-auth.py` on laptop). If the script doesn't exist, skip silently.
- Proactive day planning nudge (09:00-18:00 Europe/London only): run `python3 /workspace/calendar-helper.py list-events --days 1` and check if there's a 2+ hour free gap starting within the next hour. If yes, read `/workspace/context/PRIORITIES.md` and check for overdue or stale items. If there's an actionable match, send a brief Telegram nudge like "You're free until 3pm and Spoons PR review has been on your list 4 days. Want me to block that time?" Limit: no more than 2 nudges per day, never nudge about the same item twice in a day. Outside active hours or if the calendar script fails, skip silently.
- End-of-day review (~18:00 Europe/London): check the Jimbo Suggestions calendar for today's events. Briefly note what was planned vs the current state — e.g. "3 of 4 suggestions were kept, YNAB was skipped again." Don't nag, just observe. If no suggestions were created today, skip silently.

