# VPS Automation Setup & Cheatsheet

## The Big Gotcha: Running `openclaw` CLI on the VPS

The `openclaw` CLI needs three things to work on the VPS, and getting them all right is fiddly:

1. **Env vars** from `/opt/openclaw.env` (tokens, API keys)
2. **HOME** set to `/home/openclaw` (not `/root`)
3. **Run as `openclaw` user** (file permissions)

The problem: `/opt/openclaw.env` is `chmod 600 root:root`, so the `openclaw` user can't read it. And `sudo -u openclaw` doesn't set HOME correctly.

### The working command pattern

```bash
# As root on VPS — this is the magic incantation:
export $(grep -v '^#' /opt/openclaw.env | xargs) && \
sudo -E -u openclaw HOME=/home/openclaw openclaw <command>
```

**What each part does:**
- `export $(grep ...)` — loads env vars from the env file into root's shell
- `sudo -E` — preserves those env vars when switching user
- `-u openclaw` — runs as the openclaw user
- `HOME=/home/openclaw` — overrides HOME (sudo keeps /root otherwise)

### What does NOT work

```bash
# WRONG: no env vars, reads /root/.openclaw
openclaw cron list

# WRONG: can't read /opt/openclaw.env as openclaw user
sudo -u openclaw bash -c 'source /opt/openclaw.env && openclaw cron list'

# WRONG: HOME still /root, writes to wrong config dir
sudo -E -u openclaw openclaw cron list
```

---

## Cron Jobs

### Email digest fetch (VPS root crontab, done 2026-02-24)

Daily at 06:00 UTC. Sources Google OAuth env vars from `/opt/openclaw.env` and passes them into the sandbox container. Logs to `/var/log/gmail-fetch.log`.

```bash
# View: crontab -l
# Edit: crontab -e
0 6 * * * export $(grep -v "^#" /opt/openclaw.env | xargs) && docker exec -e GOOGLE_CALENDAR_CLIENT_ID=$GOOGLE_CALENDAR_CLIENT_ID -e GOOGLE_CALENDAR_CLIENT_SECRET=$GOOGLE_CALENDAR_CLIENT_SECRET -e GOOGLE_CALENDAR_REFRESH_TOKEN=$GOOGLE_CALENDAR_REFRESH_TOKEN $(docker ps -q --filter name=openclaw-sbx) python3 /workspace/gmail-helper.py fetch --hours 24 >> /var/log/gmail-fetch.log 2>&1
```

**Replaces** the old laptop launchd job (`com.openclaw.sift-cron.plist` → `sift-cron.sh`). Laptop no longer needs to be awake for email.

### Add the morning briefing (done 2026-02-18)

```bash
export $(grep -v '^#' /opt/openclaw.env | xargs) && \
sudo -E -u openclaw HOME=/home/openclaw openclaw cron add \
  --name "Morning briefing" \
  --cron "0 7 * * *" \
  --tz "Europe/London" \
  --session isolated \
  --message "Read /workspace/email-digest.json and give Marvin his morning briefing. Use the daily-briefing skill format." \
  --announce \
  --channel telegram
```

### List cron jobs

```bash
export $(grep -v '^#' /opt/openclaw.env | xargs) && \
sudo -E -u openclaw HOME=/home/openclaw openclaw cron list
```

### Remove a cron job

```bash
export $(grep -v '^#' /opt/openclaw.env | xargs) && \
sudo -E -u openclaw HOME=/home/openclaw openclaw cron remove <job-id>
```

---

## Heartbeat

### Edit HEARTBEAT.md

```bash
nano /home/openclaw/.openclaw/workspace/HEARTBEAT.md
```

Add these lines:
```markdown
- Check /workspace/email-digest.json: if generated_at is more than 24 hours old, tell Marvin the digest is stale and ask him to run the pipeline
- If email digest was updated since the last heartbeat, briefly note how many new emails are in the digest
```

No restart needed — Jimbo reads this on each heartbeat cycle.

### Configure heartbeat timing

Add to `/home/openclaw/.openclaw/openclaw.json` (if not already present):

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

---

## Common VPS Operations

### Service management
```bash
systemctl status openclaw        # check if running
systemctl restart openclaw       # restart (needed after config changes)
journalctl -u openclaw -f        # tail logs (NOT openclaw logs --follow)
```

### Config files
```bash
nano /home/openclaw/.openclaw/openclaw.json    # main config
cat /opt/openclaw.env                           # env vars (as root)
```

### Workspace files (no restart needed)
```bash
ls /home/openclaw/.openclaw/workspace/          # brain files, skills, digest
cat /home/openclaw/.openclaw/workspace/email-digest.json | python3 -m json.tool | head -20
```

### Docker sandbox
```bash
docker ps --filter name=openclaw-sbx            # check container
docker exec -it $(docker ps -q --filter name=openclaw-sbx) bash    # step inside
docker rm -f $(docker ps -q --filter name=openclaw-sbx) && systemctl restart openclaw   # nuke + restart
```

### Plugin/skill management
```bash
export $(grep -v '^#' /opt/openclaw.env | xargs) && \
sudo -E -u openclaw HOME=/home/openclaw openclaw plugins list

export $(grep -v '^#' /opt/openclaw.env | xargs) && \
sudo -E -u openclaw HOME=/home/openclaw openclaw plugins doctor
```

---

## Laptop → VPS Push Commands

These run from the laptop (this repo):

```bash
./scripts/skills-push.sh           # push custom skills
./scripts/skills-push.sh --dry-run # preview skill push
./scripts/workspace-push.sh        # push brain files + context files
```

Legacy (no longer needed — email pipeline runs on VPS):
```bash
./scripts/sift-push.sh             # RETIRED — digest written directly in sandbox
./scripts/sift-cron.sh             # RETIRED — replaced by VPS root crontab
```
