# ADR-035: VPS as Vault Source of Truth

## Status

Accepted

## Context

`workspace-push.sh` previously synced vault notes from laptop to VPS using `rsync --delete`. This made sense when the vault was first populated — notes were ingested and classified on the laptop, then pushed to VPS for Jimbo to read.

With ADR-034 (vault task prioritisation), `prioritise-tasks.py` runs on VPS and writes scoring fields (`priority`, `priority_reason`, `actionability`, `scored`) directly into vault note frontmatter. The laptop copies don't have these scores. Every `workspace-push.sh` run would overwrite all scored notes with unscored laptop copies, destroying the scoring data.

Additionally, `tasks-helper.py` (05:00 UTC cron) ingests new Google Tasks directly into the VPS vault. These notes don't exist on the laptop at all.

## Decision

Remove vault sync from `workspace-push.sh`. VPS is now the sole source of truth for vault data.

### What changed

- Removed the vault notes rsync block from `workspace-push.sh` (was: `rsync -avz --delete "$VAULT_NOTES_DIR/" "$REMOTE_BASE/vault/notes/"`)
- Removed `VAULT_NOTES_DIR` variable and vault file counting logic
- `data/vault/` on laptop is now a stale historical copy — not authoritative

### What still syncs

`workspace-push.sh` still pushes:
- Brain files (SOUL.md, HEARTBEAT.md, TROUBLESHOOTING.md)
- Helper scripts (*.py)
- Worker directories (workers/, tasks/, tests/)
- Context files (context/*.md — backup, primary is now context API per ADR-033)

### Vault management paths

| Action | Where it happens |
|--------|-----------------|
| New tasks from Google Tasks | VPS — `tasks-helper.py pipeline` (05:00 cron) |
| Task scoring | VPS — `prioritise-tasks.py` (04:30 cron) |
| Vault browsing | VPS — Jimbo reads in sandbox, or future site UI |
| Bulk ingest (Keep, historical) | Laptop → push once, then stop |
| Manual triage | Site UI at `/app/jimbo/notes-triage` |

## Consequences

### Easier
- Scores are never accidentally overwritten
- VPS-created notes (tasks sweep) are never accidentally deleted
- One clear authority for vault state
- `workspace-push.sh` is faster (skips ~1,600 files)

### Harder
- Laptop vault copy will drift out of date over time
- If VPS vault is lost, recovery needs backup (not currently automated)
- Bulk operations (re-ingest, mass reclassify) need to happen on VPS or be pushed carefully
