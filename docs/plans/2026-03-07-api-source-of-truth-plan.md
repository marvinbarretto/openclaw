# API Source of Truth Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Eliminate sandbox SQLite databases and make jimbo-api the single source of truth for activity, costs, and experiment data — so the dashboard shows real data.

**Architecture:** Add costs and experiments endpoints to jimbo-api (Hono/Node/better-sqlite3). Rewrite three sandbox Python scripts to POST to the API instead of local SQLite. No changes to callers (briefing-prep.py, workers) — they use the same CLI interface.

**Tech Stack:** TypeScript (jimbo-api, Hono), Python 3.11 stdlib (sandbox scripts), better-sqlite3, Vitest

**Repos:**
- jimbo-api: `/Users/marvinbarretto/development/jimbo/notes-triage-api/`
- openclaw (sandbox scripts): `/Users/marvinbarretto/development/openclaw/`

**Deploy notes:**
- jimbo-api: `npm run build`, rsync `dist/` to VPS, `cp -r dist/* .` in repo root, restart `notes-triage-api` service
- Sandbox scripts: `./scripts/workspace-push.sh` from openclaw repo
- GOTCHA: Service runs `node index.js` from repo root, NOT from `dist/`. Must copy compiled files.

---

### Task 1: Add costs types and service to jimbo-api

**Files:**
- Create: `src/types/costs.ts`
- Create: `src/services/costs.ts`

**Step 1: Create types file**

```typescript
// src/types/costs.ts
export interface Cost {
  id: string;
  timestamp: string;
  provider: string;
  model: string;
  task_type: string;
  input_tokens: number;
  output_tokens: number;
  estimated_cost: number;
  notes: string | null;
}

export interface CostSummary {
  period_days: number;
  total_cost: number;
  total_interactions: number;
  by_model: { model: string; total: number; count: number; input_tokens: number; output_tokens: number }[];
  by_task_type: { task_type: string; total: number; count: number }[];
  by_day: { day: string; total: number; count: number }[];
  monthly_cost: number;
}
```

**Step 2: Create service file**

```typescript
// src/services/costs.ts
import crypto from 'node:crypto';
import { getDb } from '../db/index.js';
import type { Cost, CostSummary } from '../types/costs.js';

function generateId(): string {
  return 'cost_' + crypto.randomUUID().slice(0, 8);
}

export function logCost(data: {
  provider: string;
  model: string;
  task_type: string;
  input_tokens: number;
  output_tokens: number;
  estimated_cost: number;
  notes?: string;
}): Cost {
  const db = getDb();
  const id = generateId();
  db.prepare(
    `INSERT INTO costs (id, provider, model, task_type, input_tokens, output_tokens, estimated_cost, notes)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
  ).run(id, data.provider, data.model, data.task_type, data.input_tokens, data.output_tokens, data.estimated_cost, data.notes ?? null);
  return db.prepare('SELECT * FROM costs WHERE id = ?').get(id) as Cost;
}

export function getCostsByDays(days: number): Cost[] {
  const db = getDb();
  return db.prepare(
    `SELECT * FROM costs WHERE timestamp >= datetime('now', '-' || ? || ' days') ORDER BY timestamp DESC`
  ).all(days) as Cost[];
}

export function getCostSummary(days: number): CostSummary {
  const db = getDb();
  const cutoff = days;

  const total = db.prepare(
    `SELECT COALESCE(SUM(estimated_cost), 0) as total_cost, COUNT(*) as total_interactions
     FROM costs WHERE timestamp >= datetime('now', '-' || ? || ' days')`
  ).get(cutoff) as { total_cost: number; total_interactions: number };

  const by_model = db.prepare(
    `SELECT model, ROUND(SUM(estimated_cost), 4) as total, COUNT(*) as count,
            SUM(input_tokens) as input_tokens, SUM(output_tokens) as output_tokens
     FROM costs WHERE timestamp >= datetime('now', '-' || ? || ' days')
     GROUP BY model ORDER BY total DESC`
  ).all(cutoff) as CostSummary['by_model'];

  const by_task_type = db.prepare(
    `SELECT task_type, ROUND(SUM(estimated_cost), 4) as total, COUNT(*) as count
     FROM costs WHERE timestamp >= datetime('now', '-' || ? || ' days')
     GROUP BY task_type ORDER BY total DESC`
  ).all(cutoff) as CostSummary['by_task_type'];

  const by_day = db.prepare(
    `SELECT date(timestamp) as day, ROUND(SUM(estimated_cost), 4) as total, COUNT(*) as count
     FROM costs WHERE timestamp >= datetime('now', '-' || ? || ' days')
     GROUP BY date(timestamp) ORDER BY day`
  ).all(cutoff) as CostSummary['by_day'];

  const monthStart = new Date();
  monthStart.setDate(1);
  monthStart.setHours(0, 0, 0, 0);
  const monthly = db.prepare(
    `SELECT COALESCE(SUM(estimated_cost), 0) as total FROM costs WHERE timestamp >= ?`
  ).get(monthStart.toISOString()) as { total: number };

  return {
    period_days: days,
    total_cost: Math.round(total.total_cost * 10000) / 10000,
    total_interactions: total.total_interactions,
    by_model,
    by_task_type,
    by_day,
    monthly_cost: Math.round(monthly.total * 10000) / 10000,
  };
}
```

**Step 3: Commit**

```bash
cd /Users/marvinbarretto/development/jimbo/notes-triage-api
git add src/types/costs.ts src/services/costs.ts
git commit -m "feat: add costs types and service"
```

---

### Task 2: Add costs route to jimbo-api

**Files:**
- Create: `src/routes/costs.ts`
- Modify: `src/index.ts` (add route)

**Step 1: Create route file**

```typescript
// src/routes/costs.ts
import { Hono } from 'hono';
import { logCost, getCostsByDays, getCostSummary } from '../services/costs.js';

const costs = new Hono();

costs.post('/', async (c) => {
  const body = await c.req.json<{
    provider: string;
    model: string;
    task_type: string;
    input_tokens: number;
    output_tokens: number;
    estimated_cost: number;
    notes?: string;
  }>();

  if (!body.provider || !body.model || !body.task_type) {
    return c.json({ error: 'provider, model, and task_type are required' }, 400);
  }
  if (body.input_tokens === undefined || body.output_tokens === undefined) {
    return c.json({ error: 'input_tokens and output_tokens are required' }, 400);
  }

  const created = logCost(body);
  return c.json(created, 201);
});

costs.get('/summary', (c) => {
  const days = Number(c.req.query('days') || '7');
  if (isNaN(days) || days < 1) {
    return c.json({ error: 'days must be a positive number' }, 400);
  }
  return c.json(getCostSummary(days));
});

costs.get('/', (c) => {
  const days = Number(c.req.query('days') || '7');
  if (isNaN(days) || days < 1) {
    return c.json({ error: 'days must be a positive number' }, 400);
  }
  const entries = getCostsByDays(days);
  return c.json({ days, entries });
});

export default costs;
```

**Step 2: Add route to index.ts**

Add import and route registration in `src/index.ts`:

```typescript
import costs from './routes/costs.js';
// ... after existing routes
app.route('/api/costs', costs);
```

**Step 3: Add costs table to schema in db/index.ts**

Add to the `SCHEMA` string in `src/db/index.ts`, after the `vault_notes` table:

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
CREATE INDEX IF NOT EXISTS idx_costs_ts ON costs(timestamp);
CREATE INDEX IF NOT EXISTS idx_costs_model ON costs(model);
CREATE INDEX IF NOT EXISTS idx_costs_task ON costs(task_type);
```

**Step 4: Build and verify**

```bash
npm run build
```

Expected: clean compile, no errors.

**Step 5: Commit**

```bash
git add src/routes/costs.ts src/index.ts src/db/index.ts
git commit -m "feat: add /api/costs endpoint"
```

---

### Task 3: Add experiments types and service to jimbo-api

**Files:**
- Create: `src/types/experiments.ts`
- Create: `src/services/experiments.ts`

**Step 1: Create types file**

```typescript
// src/types/experiments.ts
export interface Run {
  run_id: string;
  task_id: string;
  parent_run_id: string | null;
  timestamp: string;
  model: string;
  config_hash: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  cost_usd: number | null;
  duration_ms: number | null;
  input_summary: string | null;
  output_summary: string | null;
  quality_scores: string | null;
  conductor_rating: number | null;
  user_rating: number | null;
  user_notes: string | null;
  conductor_reasoning: string | null;
  session: string | null;
}

export interface ExperimentStats {
  period_days: number;
  total_runs: number;
  total_cost: number;
  avg_conductor_rating: number | null;
  avg_user_rating: number | null;
  by_task: { task_id: string; runs: number; cost: number; avg_quality: number | null }[];
  by_model: { model: string; runs: number; cost: number; avg_quality: number | null }[];
}
```

**Step 2: Create service file**

```typescript
// src/services/experiments.ts
import crypto from 'node:crypto';
import { getDb } from '../db/index.js';
import type { Run, ExperimentStats } from '../types/experiments.js';

function generateId(): string {
  return 'run_' + crypto.randomUUID().slice(0, 8);
}

export function logRun(data: {
  task_id: string;
  model: string;
  parent_run_id?: string;
  config_hash?: string;
  input_tokens?: number;
  output_tokens?: number;
  cost_usd?: number;
  duration_ms?: number;
  input_summary?: string;
  output_summary?: string;
  quality_scores?: string;
  conductor_rating?: number;
  conductor_reasoning?: string;
  session?: string;
}): Run {
  const db = getDb();
  const run_id = generateId();
  db.prepare(
    `INSERT INTO runs (run_id, task_id, parent_run_id, model, config_hash,
      input_tokens, output_tokens, cost_usd, duration_ms,
      input_summary, output_summary, quality_scores,
      conductor_rating, conductor_reasoning, session)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
  ).run(
    run_id, data.task_id, data.parent_run_id ?? null, data.model, data.config_hash ?? null,
    data.input_tokens ?? null, data.output_tokens ?? null, data.cost_usd ?? null, data.duration_ms ?? null,
    data.input_summary ?? null, data.output_summary ?? null, data.quality_scores ?? null,
    data.conductor_rating ?? null, data.conductor_reasoning ?? null, data.session ?? null,
  );
  return db.prepare('SELECT * FROM runs WHERE run_id = ?').get(run_id) as Run;
}

export function getRuns(task_id: string | undefined, last: number): Run[] {
  const db = getDb();
  if (task_id) {
    return db.prepare(
      'SELECT * FROM runs WHERE task_id = ? ORDER BY timestamp DESC LIMIT ?'
    ).all(task_id, last) as Run[];
  }
  return db.prepare(
    'SELECT * FROM runs ORDER BY timestamp DESC LIMIT ?'
  ).all(last) as Run[];
}

export function rateRun(run_id: string, user_rating: number, user_notes?: string): Run | null {
  const db = getDb();
  const existing = db.prepare('SELECT * FROM runs WHERE run_id = ?').get(run_id) as Run | undefined;
  if (!existing) return null;
  db.prepare(
    'UPDATE runs SET user_rating = ?, user_notes = ?, timestamp = timestamp WHERE run_id = ?'
  ).run(user_rating, user_notes ?? existing.user_notes, run_id);
  return db.prepare('SELECT * FROM runs WHERE run_id = ?').get(run_id) as Run;
}

export function getExperimentStats(days: number): ExperimentStats {
  const db = getDb();
  const cutoff = days;

  const totals = db.prepare(
    `SELECT COUNT(*) as total_runs, COALESCE(ROUND(SUM(cost_usd), 4), 0) as total_cost,
            ROUND(AVG(conductor_rating), 1) as avg_conductor_rating,
            ROUND(AVG(user_rating), 1) as avg_user_rating
     FROM runs WHERE timestamp >= datetime('now', '-' || ? || ' days')`
  ).get(cutoff) as { total_runs: number; total_cost: number; avg_conductor_rating: number | null; avg_user_rating: number | null };

  const by_task = db.prepare(
    `SELECT task_id, COUNT(*) as runs, COALESCE(ROUND(SUM(cost_usd), 4), 0) as cost,
            ROUND(AVG(conductor_rating), 1) as avg_quality
     FROM runs WHERE timestamp >= datetime('now', '-' || ? || ' days')
     GROUP BY task_id ORDER BY runs DESC`
  ).all(cutoff) as ExperimentStats['by_task'];

  const by_model = db.prepare(
    `SELECT model, COUNT(*) as runs, COALESCE(ROUND(SUM(cost_usd), 4), 0) as cost,
            ROUND(AVG(conductor_rating), 1) as avg_quality
     FROM runs WHERE timestamp >= datetime('now', '-' || ? || ' days')
     GROUP BY model ORDER BY cost DESC`
  ).all(cutoff) as ExperimentStats['by_model'];

  return {
    period_days: days,
    total_runs: totals.total_runs,
    total_cost: totals.total_cost,
    avg_conductor_rating: totals.avg_conductor_rating,
    avg_user_rating: totals.avg_user_rating,
    by_task,
    by_model,
  };
}
```

**Step 3: Commit**

```bash
git add src/types/experiments.ts src/services/experiments.ts
git commit -m "feat: add experiments types and service"
```

---

### Task 4: Add experiments route to jimbo-api

**Files:**
- Create: `src/routes/experiments.ts`
- Modify: `src/index.ts` (add route)
- Modify: `src/db/index.ts` (add runs table)

**Step 1: Create route file**

```typescript
// src/routes/experiments.ts
import { Hono } from 'hono';
import { logRun, getRuns, rateRun, getExperimentStats } from '../services/experiments.js';

const experiments = new Hono();

experiments.post('/', async (c) => {
  const body = await c.req.json<{
    task_id: string;
    model: string;
    parent_run_id?: string;
    config_hash?: string;
    input_tokens?: number;
    output_tokens?: number;
    cost_usd?: number;
    duration_ms?: number;
    input_summary?: string;
    output_summary?: string;
    quality_scores?: string;
    conductor_rating?: number;
    conductor_reasoning?: string;
    session?: string;
  }>();

  if (!body.task_id || !body.model) {
    return c.json({ error: 'task_id and model are required' }, 400);
  }

  const run = logRun(body);
  return c.json(run, 201);
});

experiments.get('/stats', (c) => {
  const days = Number(c.req.query('days') || '7');
  if (isNaN(days) || days < 1) {
    return c.json({ error: 'days must be a positive number' }, 400);
  }
  return c.json(getExperimentStats(days));
});

experiments.get('/', (c) => {
  const task = c.req.query('task') || undefined;
  const last = Number(c.req.query('last') || '20');
  if (isNaN(last) || last < 1) {
    return c.json({ error: 'last must be a positive number' }, 400);
  }
  const runs = getRuns(task, last);
  return c.json({ task: task ?? 'all', runs });
});

experiments.put('/:id/rate', async (c) => {
  const { user_rating, user_notes } = await c.req.json<{ user_rating: number; user_notes?: string }>();
  if (user_rating === undefined || user_rating === null) {
    return c.json({ error: 'user_rating is required' }, 400);
  }
  if (!Number.isInteger(user_rating) || user_rating < 1 || user_rating > 10) {
    return c.json({ error: 'user_rating must be an integer between 1 and 10' }, 400);
  }
  const run = rateRun(c.req.param('id'), user_rating, user_notes);
  if (!run) {
    return c.json({ error: 'Run not found' }, 404);
  }
  return c.json(run);
});

export default experiments;
```

**Step 2: Add route and table**

In `src/index.ts`, add:
```typescript
import experiments from './routes/experiments.js';
// ... after existing routes
app.route('/api/experiments', experiments);
```

In `src/db/index.ts`, add to `SCHEMA` string:
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
CREATE INDEX IF NOT EXISTS idx_runs_ts ON runs(timestamp);
CREATE INDEX IF NOT EXISTS idx_runs_task ON runs(task_id);
CREATE INDEX IF NOT EXISTS idx_runs_model ON runs(model);
```

**Step 3: Build and verify**

```bash
npm run build
```

Expected: clean compile, no errors.

**Step 4: Commit**

```bash
git add src/routes/experiments.ts src/index.ts src/db/index.ts
git commit -m "feat: add /api/experiments endpoint"
```

---

### Task 5: Deploy jimbo-api to VPS

**Step 1: Build**

```bash
cd /Users/marvinbarretto/development/jimbo/notes-triage-api
npm run build
```

**Step 2: Rsync to VPS**

```bash
rsync -avz --delete dist/ jimbo:/home/openclaw/notes-triage-api/dist/
```

**Step 3: Copy compiled files to repo root (GOTCHA)**

```bash
ssh jimbo 'cd /home/openclaw/notes-triage-api && cp -r dist/* .'
```

**Step 4: Restart service**

```bash
ssh jimbo 'sudo systemctl restart notes-triage-api'
```

**Step 5: Verify endpoints**

```bash
# Check costs endpoint
ssh jimbo 'curl -s -H "X-API-Key: $(grep API_KEY /home/openclaw/notes-triage-api/.env | cut -d= -f2)" http://localhost:3100/api/costs'

# Check experiments endpoint
ssh jimbo 'curl -s -H "X-API-Key: $(grep API_KEY /home/openclaw/notes-triage-api/.env | cut -d= -f2)" http://localhost:3100/api/experiments'
```

Expected: `{"days":7,"entries":[]}` and `{"task":"all","runs":[]}` respectively.

---

### Task 6: Rewrite activity-log.py to use API

**Files:**
- Modify: `workspace/activity-log.py`

Replace the entire file. Keep CLI interface identical. Replace SQLite with HTTP POSTs/GETs to jimbo-api.

Key patterns:
- Use `JIMBO_API_URL` and `JIMBO_API_KEY` env vars (already in sandbox)
- HTTP via `urllib.request` (stdlib only)
- Fail gracefully with error message to stderr, non-zero exit

**Step 1: Rewrite activity-log.py**

Replace contents with API-backed version. The file must:
- Keep all subcommands: `log`, `rate`, `list`, `export`, `stats`
- `log` → POST to `/api/activity`
- `rate` → PUT to `/api/activity/{id}/rate`
- `list` → GET from `/api/activity?days=N`
- `stats` → GET from `/api/activity/stats?days=N`
- `export` → GET from `/api/activity?days=N` (same as list, format as export)
- Remove: `sqlite3` import, `DB_PATH`, `SCHEMA`, `get_db()`, all direct DB access
- Keep: `VALID_TASK_TYPES` for client-side validation, argparse CLI

Helper function for API calls:
```python
def api_request(method, path, body=None):
    api_url = os.environ.get("JIMBO_API_URL", "http://localhost:3100")
    api_key = os.environ.get("JIMBO_API_KEY", "")
    url = f"{api_url}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("X-API-Key", api_key)
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())
```

**Step 2: Verify locally** (optional — can test after deploy)

```bash
python3 workspace/activity-log.py log --task briefing --description "test entry" --outcome "success"
```

Expected: prints `{"status": "ok", "id": "act_...", "action": "logged"}` (will fail locally without API access, but verifies no import errors).

**Step 3: Commit**

```bash
cd /Users/marvinbarretto/development/openclaw
git add workspace/activity-log.py
git commit -m "feat: rewrite activity-log.py to POST to jimbo-api"
```

---

### Task 7: Rewrite cost-tracker.py to use API

**Files:**
- Modify: `workspace/cost-tracker.py`

Same pattern as Task 6. Keep CLI, replace SQLite with HTTP.

Key differences:
- `log` → POST to `/api/costs` (must calculate `estimated_cost` client-side before POSTing)
- `summary` → GET from `/api/costs/summary?days=N`
- `export` → GET from `/api/costs?days=N`
- `budget` → GET from `/api/costs/summary` + GET from `/api/settings/monthly_budget_usd`
- Keep: `estimate_cost()` function, `COST_RATES` dict, `get_setting()` function
- Remove: `sqlite3`, `DB_PATH`, `SCHEMA`, `get_db()`, `budgets` table code

**Step 1: Rewrite cost-tracker.py**

Replace SQLite with API calls. Use same `api_request()` helper pattern.

**Step 2: Commit**

```bash
git add workspace/cost-tracker.py
git commit -m "feat: rewrite cost-tracker.py to POST to jimbo-api"
```

---

### Task 8: Rewrite experiment-tracker.py to use API

**Files:**
- Modify: `workspace/experiment-tracker.py`

Same pattern. Keep CLI, replace SQLite with HTTP.

- `log` → POST to `/api/experiments` (must calculate `cost_usd` client-side before POSTing)
- `runs` → GET from `/api/experiments?task=X&last=N`
- `compare` → GET from `/api/experiments/stats?task=X&days=N`
- `rate` → PUT to `/api/experiments/{id}/rate`
- `stats` → GET from `/api/experiments/stats?days=N`
- `export` → GET from `/api/experiments?days=N`
- Keep: `estimate_cost()`, `config_hash()`, `COST_RATES`, `get_setting()`
- Remove: `sqlite3`, `DB_PATH`, `SCHEMA`, `get_db()`, `games`/`game_rounds` tables

**Step 1: Rewrite experiment-tracker.py**

Replace SQLite with API calls.

**Step 2: Commit**

```bash
git add workspace/experiment-tracker.py
git commit -m "feat: rewrite experiment-tracker.py to POST to jimbo-api"
```

---

### Task 9: Deploy sandbox scripts and verify end-to-end

**Step 1: Push scripts to VPS**

```bash
cd /Users/marvinbarretto/development/openclaw
./scripts/workspace-push.sh
```

**Step 2: Test activity logging from sandbox**

```bash
ssh jimbo "docker exec -e JIMBO_API_URL=\$(grep JIMBO_API_URL /opt/openclaw.env | cut -d= -f2) -e JIMBO_API_KEY=\$(grep JIMBO_API_KEY /opt/openclaw.env | cut -d= -f2) \$(docker ps -q --filter name=openclaw-sbx) python3 /workspace/activity-log.py log --task briefing --description 'API integration test' --outcome success"
```

Expected: `{"status": "ok", "id": "act_...", ...}`

**Step 3: Test cost logging from sandbox**

```bash
ssh jimbo "docker exec -e JIMBO_API_URL=\$(grep JIMBO_API_URL /opt/openclaw.env | cut -d= -f2) -e JIMBO_API_KEY=\$(grep JIMBO_API_KEY /opt/openclaw.env | cut -d= -f2) \$(docker ps -q --filter name=openclaw-sbx) python3 /workspace/cost-tracker.py log --provider google --model gemini-2.5-flash --task briefing --input-tokens 1000 --output-tokens 200"
```

Expected: `{"status": "ok", "id": "cost_...", "estimated_cost": ...}`

**Step 4: Test experiment logging from sandbox**

```bash
ssh jimbo "docker exec -e JIMBO_API_URL=\$(grep JIMBO_API_URL /opt/openclaw.env | cut -d= -f2) -e JIMBO_API_KEY=\$(grep JIMBO_API_KEY /opt/openclaw.env | cut -d= -f2) \$(docker ps -q --filter name=openclaw-sbx) python3 /workspace/experiment-tracker.py log --task email-triage --model gemini-2.5-flash --input-tokens 5000 --output-tokens 500"
```

Expected: `{"status": "ok", "run_id": "run_...", "cost_usd": ...}`

**Step 5: Verify dashboard shows data**

Check these URLs in browser:
- `https://site.marvinbarretto.workers.dev/app/jimbo/activity/` — should show test entries
- `https://site.marvinbarretto.workers.dev/app/jimbo/costs/` — should show test cost entry

**Step 6: Run briefing-prep dry-run to verify callers still work**

```bash
ssh jimbo "docker exec -e JIMBO_API_URL=\$(grep JIMBO_API_URL /opt/openclaw.env | cut -d= -f2) -e JIMBO_API_KEY=\$(grep JIMBO_API_KEY /opt/openclaw.env | cut -d= -f2) \$(docker ps -q --filter name=openclaw-sbx) python3 /workspace/briefing-prep.py morning --dry-run"
```

Expected: completes without errors, logs activity via API.

---

### Task 10: Clean up sandbox SQLite files

**Step 1: Delete old DB files from VPS sandbox**

```bash
ssh jimbo "docker exec \$(docker ps -q --filter name=openclaw-sbx) rm -f /workspace/activity-log.db /workspace/cost-tracker.db /workspace/experiment-tracker.db"
```

**Step 2: Verify nothing references the old DB paths**

Search workspace scripts for `.db` references:
```bash
grep -r 'activity-log.db\|cost-tracker.db\|experiment-tracker.db' workspace/
```

Expected: no matches (all references removed in Tasks 6-8).

**Step 3: Commit any remaining changes**

```bash
git add -A
git commit -m "chore: clean up references to removed sandbox SQLite databases"
```
