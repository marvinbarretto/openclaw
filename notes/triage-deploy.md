# Notes Triage Pipeline — Deployment & Operations

## What This Is

A mobile-friendly web UI for triaging ~6,500 vault notes from the inbox. Three pieces work together:

1. **process-inbox.py** (this repo) — generates a `manifest.json` describing every inbox note with LLM-suggested actions
2. **notes-triage-api** (Hono/Node) — serves the manifest as a queue and stores triage decisions as JSON
3. **site** (Astro/React) — the triage UI at `/app/jimbo/notes-triage`, swipe cards to accept/archive/skip

## Architecture

```
Laptop                                VPS (167.99.206.214)
┌──────────────────┐                  ┌──────────────────────────────┐
│ process-inbox.py │                  │ notes-triage-api (port 3100) │
│   --manifest     │──push-manifest──▶│   /api/triage/queue          │
│                  │                  │   /api/triage/decisions       │
│ apply-decisions  │◀─pull-decisions──│   /api/triage/stats          │
│   .py            │                  │   /api/triage/undo           │
└──────────────────┘                  └──────────┬───────────────────┘
                                                 │ Caddy reverse proxy
                                      ┌──────────▼───────────────────┐
                                      │ site.marvinbarretto.workers   │
                                      │  /app/jimbo/notes-triage      │
                                      │  (React triage UI)            │
                                      └────────────────────────────── ┘
```

## Data Flow

1. **Generate manifest**: `python3 scripts/process-inbox.py --manifest --provider gemini --skip-fetch`
   - Reads every file in `data/vault/inbox/`
   - Calls LLM for suggested action (direct/archive/context/skip)
   - Writes `data/vault/triage/manifest.json`

2. **Push to VPS**: `./scripts/push-manifest.sh`
   - Rsyncs manifest.json to `/home/openclaw/.openclaw/workspace/triage/` on VPS

3. **Triage in browser**: Visit the triage page, swipe through cards
   - UI calls API to get queue items (manifest minus already-decided)
   - Each swipe POSTs a decision to `/api/triage/decisions`
   - Decisions stored in `decisions.json` on VPS

4. **Pull decisions back**: `./scripts/pull-decisions.sh`
   - Rsyncs decisions.json from VPS to `data/vault/triage/decisions.json`

5. **Apply decisions**: `python3 scripts/apply-decisions.py`
   - Reads decisions.json, moves files in the vault accordingly
   - `direct` → `data/vault/notes/`, `archive` → `data/vault/archive/`, etc.

## VPS Components

### notes-triage-api
- **Location**: `/home/openclaw/notes-triage-api/`
- **Service**: `systemctl {status|restart|stop} notes-triage-api`
- **Logs**: `journalctl -u notes-triage-api -f`
- **Port**: 3100
- **Data dir**: `/home/openclaw/.openclaw/workspace/triage/`
- **Auth**: API key in systemd env, validated via `X-API-Key` header

### Caddy
- Routes `/api/triage/*` to port 3100
- Everything else to OpenClaw on port 18789

## Scripts

| Script | Purpose |
|--------|---------|
| `process-inbox.py --manifest` | Generate manifest.json from vault inbox |
| `push-manifest.sh` | Push manifest to VPS |
| `pull-decisions.sh` | Pull decisions from VPS |
| `apply-decisions.py` | Apply decisions to move vault files |

## Generating a New Manifest

```bash
# Full run (~30 mins for 6,500 items with Gemini Flash)
python3 scripts/process-inbox.py --manifest --provider gemini --skip-fetch

# Test with small batch
python3 scripts/process-inbox.py --manifest --provider gemini --skip-fetch --limit 10

# Push to VPS
./scripts/push-manifest.sh
```

## Troubleshooting

- **API not responding**: `ssh jimbo "systemctl status notes-triage-api"`
- **CORS errors**: Check CORS origins in `notes-triage-api/src/index.ts`
- **Empty queue**: Check manifest.json exists in triage data dir on VPS
- **Auth failures**: Verify `X-API-Key` header matches `API_KEY` env var in systemd service
