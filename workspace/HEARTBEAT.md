# HEARTBEAT.md

# Keep this file empty (or with only comments) to skip heartbeat API calls.

# Add tasks below when you want the agent to check something periodically.
- Check `/workspace/email-digest.json`: If the file exists and `generated_at` is more than 24 hours old, tell Marvin the email digest is stale and ask him to run the pipeline on his laptop.
- If email digest was updated since the last heartbeat, briefly mention how many emails are in the digest and how many are queued for reading
- Check if any token expiry dates in `/workspace/CAPABILITIES.md` are within 14 days - warn Marvin if so
- Check context file freshness: if `/workspace/context/PRIORITIES.md` is >10 days old or `/workspace/context/GOALS.md` is >45 days old, remind Marvin to update them
- Check calendar health: run `python3 /workspace/calendar-helper.py list-calendars`. If the script fails with a token error, warn Marvin that the Google Calendar token needs refreshing (re-run `calendar-auth.py` on laptop). If the script doesn't exist, skip silently.

