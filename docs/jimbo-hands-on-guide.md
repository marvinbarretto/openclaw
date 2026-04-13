# Jimbo Hands-On Guide

Quick reference for getting into the raw files and fixing things. Everything here is on the VPS at `/home/openclaw/.openclaw/workspace/` unless noted.

## How to check things

SSH in: `ssh jimbo`
Workspace: `cd /home/openclaw/.openclaw/workspace/`
Skills: `cd /home/openclaw/.openclaw/workspace/skills/`

## The files that matter most

### Brain files (control Jimbo's personality and rules)

| File | What it does | Check for |
|------|-------------|-----------|
| `SOUL.md` | Core personality, output rules, behavioral constraints | Stale references to retired features, outdated priority scales, rules the model ignores |
| `HEARTBEAT.md` | What Jimbo does on every 30-min poll | Output discipline rules, nudge timing, task references |
| `IDENTITY.md` | Name, vibe, emoji | Usually fine — Jimbo maintains this |
| `AGENTS.md` | Operating manual (injected by OpenClaw) | Not in repo — lives only on VPS |
| `USER.md` | Who Marvin is, preferences | Jimbo maintains — check it's not stale |
| `MEMORY.md` | Long-term curated memory | Jimbo maintains — check for outdated entries |
| `TOOLS.md` | Environment-specific notes | Jimbo maintains |

**These are injected into every single turn.** If they're bloated or stale, every response costs more tokens and the model gets confused.

To check freshness:
```bash
ssh jimbo 'ls -la /home/openclaw/.openclaw/workspace/{SOUL,HEARTBEAT,IDENTITY,AGENTS,USER,MEMORY,TOOLS}.md 2>/dev/null'
```

To read any of them:
```bash
ssh jimbo 'cat /home/openclaw/.openclaw/workspace/SOUL.md'
```

### Skills (what Jimbo can do)

Each skill is `skills/<name>/SKILL.md`. Skills are **lazy-loaded** — Jimbo sees a list of names + descriptions, then must choose to read the full file. Cheaper models often don't.

```bash
# List all deployed skills
ssh jimbo 'ls /home/openclaw/.openclaw/workspace/skills/'

# Read a specific skill
ssh jimbo 'cat /home/openclaw/.openclaw/workspace/skills/daily-briefing/SKILL.md'
```

**Common issues:**
- Skills reference env vars (`$JIMBO_API_KEY`, `$JIMBO_API_URL`) that may be missing or stale
- Skills reference hardcoded thresholds (priority >= 7) that no longer match the scoring system
- Retired skills still present — model wastes tokens reading the list

### Helper scripts (Python utilities Jimbo can call)

These run inside the OpenClaw sandbox. Key ones:

| Script | Purpose | Common failures |
|--------|---------|----------------|
| `briefing-prep.py` | Assembles briefing-input.json | Auth failures (401), stale API keys |
| `prioritise-tasks.py` | Scores vault tasks | Scoring rubric mismatch, API auth |
| `health-helper.py` | Self-check via /api/health | API key mismatch |
| `calendar-helper.py` | Calendar data fetch | OAuth token expiry |
| `gmail-helper.py` | Email fetch | OAuth token expiry |
| `tasks-helper.py` | Vault task management | API auth |
| `vault-triage.py` | Auto-classify and archive stale tasks | Threshold/priority issues |

To check if a helper works:
```bash
# Run inside the openclaw sandbox
ssh jimbo 'sudo -u openclaw bash -c "cd /home/openclaw/.openclaw/workspace && python3 health-helper.py status"'
```

### Worker scripts (background data processing)

In `workers/`. These run via cron, not interactively.

| Worker | Purpose | Check for |
|--------|---------|-----------|
| `email_decision.py` | Flash decides which emails to process | Cost, model config |
| `email_triage.py` | Flash shortlists emails | Shortlist rate, 0-gem sessions |
| `newsletter_reader.py` | Haiku reads shortlisted emails | Gem quality, null fields |
| `vault_connector.py` | Links vault tasks to signals | Priority threshold (currently >= 7) |
| `vault_roulette.py` | Random task surfacing | Priority weight (currently >= 7) |
| `vault_reader.py` | Reads vault tasks for context | 401 errors (historically broken) |

### Cron schedule (system cron, not OpenClaw cron)

```bash
ssh jimbo 'crontab -l -u openclaw 2>/dev/null || crontab -l'
```

Expected schedule:
- `04:15` — vault-triage.py
- `04:30` — prioritise-tasks.py
- `05:00` — tasks-helper.py sweep
- `06:15` — briefing-prep.py morning
- `14:15` — briefing-prep.py afternoon
- `*/30` — email_decision.py
- `20:00` — accountability-check.py

### Config and env vars

OpenClaw config (controls model, heartbeat, session behavior):
```bash
ssh jimbo 'cat /home/openclaw/.openclaw/openclaw.json'
```

Environment variables (API keys, tokens):
```bash
ssh jimbo 'cat /home/openclaw/.openclaw/openclaw.env'
```

Key env vars to verify:
- `JIMBO_API_KEY` — must match jimbo-api's expected key
- `JIMBO_API_URL` — should be `https://jimbo.fourfoldmedia.uk`
- `GOOGLE_OAUTH_*` — calendar + gmail access
- OpenRouter key (if using paid models)

## Deploying changes

**From your local repo:**

```bash
# Push workspace files (brain + helpers + workers)
./scripts/workspace-push.sh          # dry-run by default
./scripts/workspace-push.sh --live   # actually push

# Push skills only
./scripts/skills-push.sh             # dry-run
./scripts/skills-push.sh --live      # push

# Push triage manifest
./scripts/push-manifest.sh --live
```

**After pushing:** Skills hot-reload on next message. Brain files (SOUL, HEARTBEAT) hot-reload too. No restart needed for most changes.

**For jimbo-api changes:** That's a separate repo (`jimbo-api`). Deploy via `git push` to VPS — systemd runs from repo root.

## Health checks

```bash
# Quick health check via API
curl -sk -H "X-API-Key: $JIMBO_API_KEY" "https://jimbo.fourfoldmedia.uk/api/health" | python3 -m json.tool

# Check if Jimbo is alive (recent activity)
curl -sk -H "X-API-Key: $JIMBO_API_KEY" "https://jimbo.fourfoldmedia.uk/api/activity?days=1"

# Check pipeline output
ssh jimbo 'cat /home/openclaw/.openclaw/workspace/briefing-input.json | python3 -m json.tool | head -50'

# Check cron logs
ssh jimbo 'journalctl --user -u openclaw --since "today" --no-pager | tail -50'
```

## Common problems and where to look

| Symptom | Check first |
|---------|------------|
| Briefing not delivered | `briefing-input.json` exists? Model alive? Skill loaded? |
| Reasoning leaked to Telegram | HEARTBEAT.md output discipline section. Model may just ignore it. |
| "I can't do that" refusal | Skill not loaded (check skills list). Helper script missing or erroring. |
| Hallucinated data | Model didn't read briefing-input.json. Skill instructions unclear. |
| 401 errors in pipeline | API key mismatch — check `openclaw.env` vs jimbo-api expected key |
| Calendar wrong | Check calendar whitelist in settings API. OAuth token expiry. |
| Vault tasks stale | Same 5 items? Priority scorer not differentiating. Check `prioritise-tasks.py` rubric. |
| Token expiring | `curl .../api/health` shows token warnings. Renew in GitHub/Google. |
| No activity at all | OpenClaw process dead? `ssh jimbo 'systemctl status openclaw'` |

## Priority scale migration checklist

Old scale: 1-10 (numeric). New scale: P0-P3.

Files that need updating (code — affects behavior):
- [ ] `workspace/prioritise-tasks.py` — scoring rubric, defaults, distribution buckets
- [ ] `workspace/briefing-prep.py` — `if priority < 7:` filter (line ~374)
- [ ] `workspace/workers/vault_connector.py` — `if priority >= 7:` boost (line ~142)
- [ ] `workspace/workers/vault_roulette.py` — `if priority >= 7:` weight (line ~88)
- [ ] `workspace/SOUL.md` — `priority >= 7` reference
- [ ] `skills/day-planner/SKILL.md` — `priority >= 7` filter
- [ ] `skills/vault-manager/SKILL.md` — example output shows `priority 9`
- [ ] `decisions/034-vault-task-prioritisation.md` — scale definition

## Files Jimbo maintains (don't overwrite blindly)

These live on the VPS only and Jimbo updates them over time:
- `AGENTS.md`, `IDENTITY.md`, `USER.md`, `TOOLS.md`, `MEMORY.md`

Read them before editing. If you push a blank one you'll wipe Jimbo's memory.
