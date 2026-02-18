# ADR-010: Email Digest Automation Strategy

## Status

Accepted

## Context

The Sift email pipeline works end-to-end: mbsync syncs Gmail to local Maildir, sift-classify.py classifies via Ollama, sift-push.sh rsyncs the digest to the VPS, and Jimbo can present it via the sift-digest skill.

Currently every step is manual. We need to automate this so Jimbo receives a fresh digest each morning and can proactively notify Marvin.

OpenClaw provides two built-in scheduling mechanisms (see [docs](https://docs.openclaw.ai/automation/cron-vs-heartbeat)):

- **Heartbeat:** Runs periodically in the main session (default every 30 min). Agent reads `HEARTBEAT.md`, checks conditions, suppresses if nothing to report. Good for monitoring/batching.
- **Cron:** Runs at precise times, optionally in isolated sessions with per-job model overrides. Good for scheduled deliverables.

## Decision

### Split responsibilities: laptop produces, VPS consumes

```
06:00  launchd (laptop)     mbsync → classify → push digest to VPS
07:00  OpenClaw cron (VPS)  Jimbo reads digest, sends morning briefing via Telegram
~30m   Heartbeat (VPS)      Jimbo checks if digest was updated since last check
```

### Layer 1: Laptop-side pipeline (launchd)

`scripts/sift-cron.sh` runs at 06:00 via macOS launchd. It:
1. Syncs Gmail via `mbsync -a`
2. Classifies recent emails via `sift-classify.py --hours 24`
3. Pushes `email-digest.json` to VPS via `sift-push.sh`

This runs on the laptop because:
- mbsync needs Gmail IMAP credentials (never on VPS — ADR-002)
- Ollama runs locally (email content never leaves the laptop — ADR-003)
- If the laptop is asleep/off, the pipeline simply doesn't run and Jimbo's digest stays stale (heartbeat will flag this)

### Layer 2: OpenClaw cron — morning briefing

An OpenClaw cron job triggers Jimbo at 07:00 to deliver the morning briefing:

```bash
openclaw cron add \
  --name "Morning briefing" \
  --cron "0 7 * * *" \
  --tz "Europe/London" \
  --session isolated \
  --message "Read your email digest and give Marvin his morning briefing." \
  --announce \
  --channel telegram
```

**Why isolated session:** The briefing is a standalone deliverable — doesn't need conversation history. Isolated keeps it clean and allows model override if needed later.

**Why OpenClaw cron, not laptop cron:** The VPS is always on. If the laptop didn't run the pipeline, Jimbo still sends a briefing — it just notes the digest is stale. This is better than silence.

### Layer 3: Heartbeat — digest freshness monitoring

Add to `HEARTBEAT.md` on the VPS:

```md
- Check /workspace/email-digest.json: if generated_at is more than 24 hours old, mention it's stale
- If email digest was updated since the last heartbeat, briefly note how many new emails arrived
```

**Why heartbeat, not cron:** This is a monitoring check, not a scheduled deliverable. Batching it with other heartbeat checks (token expiry, workspace health) is cheaper than a separate cron job. Smart suppression means Jimbo only messages when the digest actually changed or went stale.

### What NOT to automate on the VPS

- Email sync (mbsync) — needs Gmail credentials, laptop only
- Email classification (Ollama) — needs local model, laptop only
- Anything that touches email content — stays on laptop per ADR-002/003

### Failure modes

| Failure | What happens |
|---------|-------------|
| Laptop asleep at 6am | No digest update. 7am briefing notes stale digest. Heartbeat flags it. |
| Ollama not running | sift-cron.sh exits with error, logs to data/sift-cron.log. Old digest persists. |
| VPS unreachable | sift-push.sh fails. Digest stays local. Re-run push manually later. |
| mbsync fails | sift-cron.sh logs error, continues with existing Maildir. May classify stale data. |

All failures are graceful — no data loss, no silent corruption. The worst case is Jimbo has an old digest and says so.

## Consequences

### Easier
- Marvin gets a Telegram briefing at 7am without doing anything
- Heartbeat catches stale digests throughout the day
- Each layer fails independently — no cascading failures
- OpenClaw cron is the right tool for scheduled Telegram messages (not laptop cron)

### Harder
- Laptop must be on and awake at 6am for the pipeline to run (launchd will run it when it next wakes)
- Three scheduling systems to understand (launchd, OpenClaw cron, heartbeat)
- Cron job setup requires SSH to VPS to run `openclaw cron add`

### Future improvements
- Tailscale tunnel: run Ollama on laptop, accessible from VPS — could move classification to VPS-triggered
- Wake-on-LAN: VPS could wake laptop for pipeline (complex, probably not worth it)
- Incremental push: only push if digest actually changed (add checksum comparison to sift-push.sh)
