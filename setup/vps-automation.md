# VPS Automation Setup

## OpenClaw Cron: Morning Briefing

Run this on the VPS to add the 7am briefing cron job:

```bash
ssh jimbo

openclaw cron add \
  --name "Morning briefing" \
  --cron "0 7 * * *" \
  --tz "Europe/London" \
  --session isolated \
  --message "Read /workspace/email-digest.json and give Marvin his morning briefing. Use the daily-briefing skill format." \
  --announce \
  --channel telegram
```

### Verify

```bash
openclaw cron list
```

### Remove if needed

```bash
openclaw cron remove "Morning briefing"
```

## Heartbeat: Digest Freshness

Add this to `/home/openclaw/.openclaw/workspace/HEARTBEAT.md` on the VPS:

```markdown
- Check /workspace/email-digest.json: if generated_at is more than 24 hours old, tell Marvin the digest is stale and ask him to run the pipeline
- If email digest was updated since the last heartbeat, briefly note how many new emails are in the digest
```

### Edit directly

```bash
ssh jimbo
nano /home/openclaw/.openclaw/workspace/HEARTBEAT.md
```

## Heartbeat Config

If heartbeat isn't already configured, add to `/home/openclaw/.openclaw/openclaw.json`:

```json
{
  "agents": {
    "defaults": {
      "heartbeat": {
        "every": "30m",
        "target": "last",
        "activeHours": { "start": "08:00", "end": "22:00" }
      }
    }
  }
}
```

Then restart: `systemctl restart openclaw`
