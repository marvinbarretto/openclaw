# jimbo-api as Single Source of Truth

*2026-03-07 — Eliminate sandbox SQLite, POST everything to jimbo-api*

## Problem

Three sandbox scripts write to local SQLite DBs inside Docker:
- `activity-log.py` → `activity-log.db`
- `cost-tracker.py` → `cost-tracker.db`
- `experiment-tracker.py` → `experiment-tracker.db`

The dashboard reads from jimbo-api, which has its own SQLite DB. Data never flows from sandbox to API. All dashboard pages (activity, costs) are empty. No visibility into what Jimbo does.

## Decision

Rewrite sandbox scripts to POST to jimbo-api. Add missing API endpoints. Delete all local SQLite code from sandbox scripts.

## Part 1: jimbo-api — new endpoints

### `/api/costs`

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/costs` | Log a cost entry |
| GET | `/api/costs` | List entries (`?days=N`) |
| GET | `/api/costs/summary` | Summary by model/task/day (`?days=N`) |

Schema (new `costs` table):
```sql
CREATE TABLE IF NOT EXISTS costs (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    task_type TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    estimated_cost REAL NOT NULL,
    notes TEXT
);
```

### `/api/experiments`

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/experiments` | Log a worker run |
| GET | `/api/experiments` | List runs (`?task=X&last=N`) |
| GET | `/api/experiments/stats` | Summary stats (`?days=N`) |
| PUT | `/api/experiments/:id/rate` | User rating on a run |

Schema (new `runs` table):
```sql
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    parent_run_id TEXT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    model TEXT NOT NULL,
    config_hash TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cost_usd REAL,
    duration_ms INTEGER,
    input_summary TEXT,
    output_summary TEXT,
    quality_scores TEXT,
    conductor_rating INTEGER,
    user_rating INTEGER,
    user_notes TEXT,
    conductor_reasoning TEXT,
    session TEXT
);
```

### `/api/activity` — no changes needed

Already has POST, GET, PUT /rate. Just needs callers.

## Part 2: Sandbox scripts — rewrite to HTTP

Each script keeps its CLI interface so callers (`briefing-prep.py`, workers, cron) don't change. Internally replaces SQLite with HTTP.

### `activity-log.py`
- `log` → POST `/api/activity`
- `list` → GET `/api/activity?days=N`
- `stats` → GET `/api/activity/stats?days=N`
- `rate` → PUT `/api/activity/:id/rate`
- `export` → GET `/api/activity?days=N` (same as list)
- Delete: `get_db()`, `DB_PATH`, `SCHEMA`, all sqlite3 imports

### `cost-tracker.py`
- `log` → POST `/api/costs`
- `summary` → GET `/api/costs/summary?days=N`
- `export` → GET `/api/costs?days=N`
- `budget` → GET `/api/costs/summary` + settings API for budget limit
- Delete: `get_db()`, `DB_PATH`, `SCHEMA`, `budgets` table, all sqlite3 imports
- Keep: `estimate_cost()` — still needed to calculate cost before POSTing

### `experiment-tracker.py`
- `log` → POST `/api/experiments`
- `runs` → GET `/api/experiments?task=X&last=N`
- `compare` → GET `/api/experiments/stats?task=X&days=N`
- `rate` → PUT `/api/experiments/:id/rate`
- `stats` → GET `/api/experiments/stats?days=N`
- `export` → GET `/api/experiments?days=N`
- Delete: `get_db()`, `DB_PATH`, `SCHEMA`, all sqlite3 imports
- Keep: `estimate_cost()`, `config_hash()`

## Part 3: Calendar (separate issue)

The pipeline produced 12 events in briefing-input.json. Jimbo said "the helper returned nothing." This is the LLM ignoring structured data it was given, not a pipeline bug. Needs investigation in the briefing skill prompt, not in this work.

## Not doing

- No migration of existing sandbox DB data (sparse, recent)
- No changes to `briefing-prep.py` (calls scripts by CLI — same interface)
- No dashboard frontend changes (already reads from API)
- No changes to workers (they log via experiment-tracker CLI)
- No Caddy changes needed (existing `/api/*` glob should match)

## Deployment

1. Build and deploy jimbo-api with new endpoints
2. Push rewritten sandbox scripts via workspace-push.sh
3. Verify by running `briefing-prep.py morning --dry-run` and checking dashboard
4. Delete sandbox `.db` files after confirming API is receiving data
