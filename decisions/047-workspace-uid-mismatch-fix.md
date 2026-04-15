# ADR-047: Workspace UID Mismatch Fix

## Status

Accepted (2026-04-15)

## Context

Morning briefing pipeline failed on 2026-04-15 with cascading errors:

1. `gmail-helper.py` fetched 157 emails, then failed writing `email-digest.json` (Permission denied)
2. `newsletter_reader.py` failed writing `.worker-gems.json` (Permission denied)
3. `opus-briefing.sh` timed out waiting for a fresh `briefing-input.json` that never arrived

Root cause: UID mismatch between the Docker container process and legacy data files.

- Container runs as **UID 501:50** (set in OpenClaw sandbox image)
- Host `openclaw` user is **UID 1000:1000**
- All cron jobs use `docker exec` → processes run as UID 501 inside the container
- Data files (`.worker-gems.json`, `email-digest.json`, `briefing-input.json`, etc.) were originally created as UID 1000 by processes that ran on the host before everything moved to `docker exec`
- Files are `0644` (owner-write only), so UID 501 can read but not overwrite them

ADR-013 addressed permission drift with `umask 0000` in the Dockerfile, but that only prevents drift for *new* files created inside the container. It doesn't fix pre-existing files owned by a different UID.

## Decision

**One-time ownership correction.** Changed all UID 1000 data files in the workspace to 501:50 (matching the container process):

```bash
sudo chown 501:50 /home/openclaw/.openclaw/workspace/{.worker-gems.json,.worker-shortlist.json,email-digest.json,briefing-input.json,.calendar-access-token.json,.gmail-access-token.json,jimbo-status.json,briefing-analysis.json,calendar_today.json,tasks-triage-pending.json,tasks-fetch.json,.tasks-access-token.json,.tasks-last-fetch.json}
```

No ongoing mitigation needed because:
- All cron jobs already use `docker exec` (UID 501)
- `workspace-push.sh` rsync excludes data files (`.worker-*`, `*.json`)
- `jimbo-api` (host systemd, UID 1000) writes to its own SQLite DB, not workspace files
- `umask 0000` (ADR-013) ensures new files created inside the container are world-writable

## Consequences

**Fixed:**
- Briefing pipeline can write all output files
- Email fetch, newsletter reader, and opus analysis unblocked

**Watch for:**
- If the container is ever recreated with a different UID, this could recur. The container UID (501:50) is baked into the OpenClaw sandbox image.
- If any new process runs on the host as `openclaw` and writes to the workspace, those files will be UID 1000 again. Currently no such process exists.
