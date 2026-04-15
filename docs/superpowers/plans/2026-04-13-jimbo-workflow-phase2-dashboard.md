# Jimbo Workflow Phase 2: Dashboard + Metrics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add workflow visibility — metrics endpoint, config versioning, and dashboard UI — so Marvin can see what vault-triage is doing and compare workflow variants.

**Architecture:** Backend-first. Add `config_hash` column to jimbo-api's `workflow_task_records` table, build a SQL-aggregated metrics endpoint, then add a "workflows" context tab to the existing React admin-app dashboard. Python runtime computes SHA-256 of workflow JSON at load time and passes it through the task creation API.

**Tech Stack:** jimbo-api (Hono/TypeScript/better-sqlite3), site (Astro 5/React islands/SCSS), workspace (Python 3 stdlib)

**Repos involved:**
- `~/development/jimbo/jimbo-api` — API + DB
- `~/development/site` — Dashboard frontend
- `~/development/openclaw` — Python runtime + workflow JSON

---

## File Structure

### jimbo-api (`~/development/jimbo/jimbo-api`)

| File | Action | Responsibility |
|------|--------|---------------|
| `src/db/index.ts` | Modify (~line 410) | Add `config_hash` column migration |
| `src/schemas/workflows.ts` | Modify | Add `config_hash` to schemas, add `MetricsQuerySchema` + `MetricsResponseSchema` |
| `src/services/workflows.ts` | Modify | Add `getWorkflowMetrics()` function, accept `config_hash` in create |
| `src/routes/workflows.ts` | Modify | Add `GET /metrics` route |

### site (`~/development/site`)

| File | Action | Responsibility |
|------|--------|---------------|
| `src/pages/api/jimbo/workflows/[...path].ts` | Create | Proxy `/api/jimbo/workflows/*` → jimbo-api `/api/workflows/*` |
| `src/admin-app/dashboard/url-state.ts` | Modify | Add `'workflows'` to `Context` type and `SUB_NAVS` |
| `src/admin-app/views/workflows/WorkflowRunsView.tsx` | Create | List view: workflow runs with metrics |
| `src/admin-app/views/workflows/WorkflowTasksView.tsx` | Create | Detail view: tasks within a run |
| `src/admin-app/views/workflows/WorkflowCompareView.tsx` | Create | Compare view: side-by-side run metrics |
| `src/admin-app/App.tsx` | Modify | Wire up workflows context with views |
| `src/components/admin/DashboardPage.astro` | Modify (if needed) | Add workflow-specific global styles |

### openclaw/workspace (`~/development/openclaw/workspace`)

| File | Action | Responsibility |
|------|--------|---------------|
| `jimbo_runtime.py` | Modify | Compute `config_hash` in `WorkflowLoader.load()`, pass to `TaskRecordAPI.create()` |
| `tests/test_jimbo_workflow_orchestration.py` | Modify | Add tests for config_hash computation and propagation |

---

## Task 1: Add `config_hash` Column to Database

**Files:**
- Modify: `~/development/jimbo/jimbo-api/src/db/index.ts` (~line 410, after index creation)

- [ ] **Step 1: Add column migration**

After the existing `idx_workflow_tasks_created` index creation (around line 410), add:

```typescript
// Migration: add config_hash column (Phase 2)
try {
  db.exec(`ALTER TABLE workflow_task_records ADD COLUMN config_hash TEXT DEFAULT NULL`);
} catch { /* column already exists */ }

try {
  db.exec(`CREATE INDEX IF NOT EXISTS idx_workflow_tasks_config_hash ON workflow_task_records(config_hash)`);
} catch { /* index already exists */ }
```

- [ ] **Step 2: Verify jimbo-api starts cleanly**

Run: `cd ~/development/jimbo/jimbo-api && npm run build`
Expected: No errors. Column migration is additive and idempotent.

- [ ] **Step 3: Commit**

```bash
cd ~/development/jimbo/jimbo-api
git add src/db/index.ts
git commit -m "feat: add config_hash column to workflow_task_records"
```

---

## Task 2: Add `config_hash` to Schemas

**Files:**
- Modify: `~/development/jimbo/jimbo-api/src/schemas/workflows.ts`

- [ ] **Step 1: Add config_hash to WorkflowTaskRecordSchema**

Add `config_hash: z.string().nullable().optional()` to the `WorkflowTaskRecordSchema` object, after the `completed_at` field.

- [ ] **Step 2: Add config_hash to CreateTaskRecordBody**

Add `config_hash: z.string().nullable().optional()` to the `CreateTaskRecordBody` schema.

- [ ] **Step 3: Add MetricsQuerySchema and MetricsResponseSchema**

Append to the file:

```typescript
export const MetricsQuerySchema = z.object({
  workflow: z.string().optional(),
  period: z.string().default('7d'),
  config_hash: z.string().optional(),
});

export const MetricsResponseSchema = z.object({
  total_tasks: z.number(),
  completed: z.number(),
  failed: z.number(),
  awaiting_human: z.number(),
  success_rate: z.number(),
  avg_cost: z.number(),
  human_override_rate: z.number(),
  by_config_hash: z.array(z.object({
    config_hash: z.string().nullable(),
    total_tasks: z.number(),
    success_rate: z.number(),
    avg_cost: z.number(),
    human_override_rate: z.number(),
  })).optional(),
});
```

- [ ] **Step 4: Build to check for type errors**

Run: `cd ~/development/jimbo/jimbo-api && npm run build`
Expected: Clean build.

- [ ] **Step 5: Commit**

```bash
cd ~/development/jimbo/jimbo-api
git add src/schemas/workflows.ts
git commit -m "feat: add config_hash and metrics schemas"
```

---

## Task 3: Add `config_hash` to Service Layer

**Files:**
- Modify: `~/development/jimbo/jimbo-api/src/services/workflows.ts`

- [ ] **Step 1: Accept config_hash in createTaskRecord**

Add `configHash: string | null = null` parameter to `createTaskRecord()`. Include it in the INSERT statement:

In the existing `createTaskRecord` function, add `config_hash` to the column list and values:

```typescript
// Add configHash parameter to function signature
export function createTaskRecord(
  workflowId: string,
  sourceTaskId: string,
  runId: string,
  currentStep = '',
  state = 'pending',
  assignedTo = 'jimbo',
  configHash: string | null = null,
): WorkflowTaskRecord {
```

Update the SQL INSERT to include `config_hash`:
- Add `, config_hash` to the column list
- Add `, ?` to the VALUES
- Add `configHash` to the bound parameters array

- [ ] **Step 2: Include config_hash in parseTaskRecord**

In the `parseTaskRecord` helper, add:

```typescript
config_hash: row.config_hash ?? null,
```

- [ ] **Step 3: Build to verify**

Run: `cd ~/development/jimbo/jimbo-api && npm run build`
Expected: Clean build.

- [ ] **Step 4: Commit**

```bash
cd ~/development/jimbo/jimbo-api
git add src/services/workflows.ts
git commit -m "feat: accept config_hash in task record creation"
```

---

## Task 4: Add Metrics Query Service

**Files:**
- Modify: `~/development/jimbo/jimbo-api/src/services/workflows.ts`

- [ ] **Step 1: Add parsePeriod helper**

Append to the service file:

```typescript
function parsePeriodDays(period: string): number {
  const match = period.match(/^(\d+)d$/);
  return match ? parseInt(match[1], 10) : 7;
}
```

- [ ] **Step 2: Add getWorkflowMetrics function**

```typescript
export function getWorkflowMetrics(
  filters: { workflow?: string; period?: string; config_hash?: string } = {},
): {
  total_tasks: number;
  completed: number;
  failed: number;
  awaiting_human: number;
  success_rate: number;
  avg_cost: number;
  human_override_rate: number;
  by_config_hash?: Array<{
    config_hash: string | null;
    total_tasks: number;
    success_rate: number;
    avg_cost: number;
    human_override_rate: number;
  }>;
} {
  const db = getDb();
  const days = parsePeriodDays(filters.period ?? '7d');
  const cutoff = new Date(Date.now() - days * 86400000).toISOString();

  const conditions: string[] = [`created_at >= ?`];
  const params: (string | number)[] = [cutoff];

  if (filters.workflow) {
    conditions.push(`workflow_id = ?`);
    params.push(filters.workflow);
  }
  if (filters.config_hash) {
    conditions.push(`config_hash = ?`);
    params.push(filters.config_hash);
  }

  const where = conditions.join(' AND ');

  // Aggregate metrics
  const row = db.prepare(`
    SELECT
      COUNT(*) as total_tasks,
      SUM(CASE WHEN state = 'completed' THEN 1 ELSE 0 END) as completed,
      SUM(CASE WHEN state = 'failed' THEN 1 ELSE 0 END) as failed,
      SUM(CASE WHEN state = 'awaiting_human' THEN 1 ELSE 0 END) as awaiting_human,
      SUM(CASE WHEN assigned_to = 'marvin' THEN 1 ELSE 0 END) as human_assigned
    FROM workflow_task_records
    WHERE ${where}
  `).get(...params) as any;

  const total = row.total_tasks || 0;
  const completed = row.completed || 0;
  const failed = row.failed || 0;
  const awaitingHuman = row.awaiting_human || 0;
  const humanAssigned = row.human_assigned || 0;

  // Average cost from decisions JSON
  const costRows = db.prepare(`
    SELECT decisions FROM workflow_task_records WHERE ${where}
  `).all(...params) as any[];

  let totalCost = 0;
  let costCount = 0;
  for (const r of costRows) {
    try {
      const decisions = JSON.parse(r.decisions || '[]');
      for (const d of decisions) {
        if (d.cost && d.cost > 0) {
          totalCost += d.cost;
          costCount++;
        }
      }
    } catch { /* skip malformed */ }
  }

  const result: any = {
    total_tasks: total,
    completed,
    failed,
    awaiting_human: awaitingHuman,
    success_rate: total > 0 ? completed / total : 0,
    avg_cost: costCount > 0 ? totalCost / costCount : 0,
    human_override_rate: total > 0 ? humanAssigned / total : 0,
  };

  // Breakdown by config_hash if not filtering by specific hash
  if (!filters.config_hash) {
    const hashRows = db.prepare(`
      SELECT
        config_hash,
        COUNT(*) as total_tasks,
        SUM(CASE WHEN state = 'completed' THEN 1 ELSE 0 END) as completed,
        SUM(CASE WHEN assigned_to = 'marvin' THEN 1 ELSE 0 END) as human_assigned
      FROM workflow_task_records
      WHERE ${where}
      GROUP BY config_hash
    `).all(...params) as any[];

    result.by_config_hash = hashRows.map((hr: any) => ({
      config_hash: hr.config_hash,
      total_tasks: hr.total_tasks,
      success_rate: hr.total_tasks > 0 ? hr.completed / hr.total_tasks : 0,
      avg_cost: 0, // would need per-hash cost aggregation — skip for v1
      human_override_rate: hr.total_tasks > 0 ? hr.human_assigned / hr.total_tasks : 0,
    }));
  }

  return result;
}
```

- [ ] **Step 3: Build to verify**

Run: `cd ~/development/jimbo/jimbo-api && npm run build`
Expected: Clean build.

- [ ] **Step 4: Commit**

```bash
cd ~/development/jimbo/jimbo-api
git add src/services/workflows.ts
git commit -m "feat: add getWorkflowMetrics SQL aggregation"
```

---

## Task 5: Add Metrics Route

**Files:**
- Modify: `~/development/jimbo/jimbo-api/src/routes/workflows.ts`

- [ ] **Step 1: Add GET /metrics route**

Add a new route before the existing `GET /tasks/:id` route (route order matters — `/metrics` must be matched before `/:id`):

```typescript
// Import the new schemas
import { MetricsQuerySchema, MetricsResponseSchema } from '../schemas/workflows.js';
import { getWorkflowMetrics } from '../services/workflows.js';

const metricsRoute = createRoute({
  method: 'get',
  path: '/metrics',
  request: {
    query: MetricsQuerySchema,
  },
  responses: {
    200: {
      content: { 'application/json': { schema: MetricsResponseSchema } },
      description: 'Workflow metrics',
    },
  },
});

workflows.openapi(metricsRoute, (c) => {
  const { workflow, period, config_hash } = c.req.valid('query');
  const metrics = getWorkflowMetrics({ workflow, period, config_hash });
  return c.json(metrics, 200);
});
```

- [ ] **Step 2: Update route also for config_hash in POST /tasks**

In the existing POST `/tasks` route handler, extract `config_hash` from the validated body and pass it to `createTaskRecord()`:

```typescript
const { workflow_id, source_task_id, run_id, current_step, state, assigned_to, config_hash } = c.req.valid('json');
const task = createTaskRecord(workflow_id, source_task_id, run_id, current_step, state, assigned_to, config_hash ?? null);
```

- [ ] **Step 3: Build and verify**

Run: `cd ~/development/jimbo/jimbo-api && npm run build`
Expected: Clean build.

- [ ] **Step 4: Commit**

```bash
cd ~/development/jimbo/jimbo-api
git add src/routes/workflows.ts
git commit -m "feat: add GET /metrics endpoint and config_hash to task creation"
```

---

## Task 6: Add Workflow List Endpoint (for dashboard)

The existing `GET /tasks` lists individual task records. The dashboard also needs runs-level grouping.

**Files:**
- Modify: `~/development/jimbo/jimbo-api/src/services/workflows.ts`
- Modify: `~/development/jimbo/jimbo-api/src/routes/workflows.ts`
- Modify: `~/development/jimbo/jimbo-api/src/schemas/workflows.ts`

- [ ] **Step 1: Add WorkflowRunSchema**

In `schemas/workflows.ts`, add:

```typescript
export const WorkflowRunSchema = z.object({
  run_id: z.string(),
  workflow_id: z.string(),
  config_hash: z.string().nullable(),
  started_at: z.string(),
  completed_at: z.string().nullable(),
  total_tasks: z.number(),
  completed_tasks: z.number(),
  failed_tasks: z.number(),
  human_tasks: z.number(),
  total_cost: z.number(),
});

export const WorkflowRunListSchema = z.array(WorkflowRunSchema);
```

- [ ] **Step 2: Add listWorkflowRuns service**

In `services/workflows.ts`, add:

```typescript
export function listWorkflowRuns(
  filters: { workflow_id?: string; limit?: number; offset?: number } = {},
): Array<{
  run_id: string;
  workflow_id: string;
  config_hash: string | null;
  started_at: string;
  completed_at: string | null;
  total_tasks: number;
  completed_tasks: number;
  failed_tasks: number;
  human_tasks: number;
  total_cost: number;
}> {
  const db = getDb();
  const conditions: string[] = [];
  const params: (string | number)[] = [];

  if (filters.workflow_id) {
    conditions.push(`workflow_id = ?`);
    params.push(filters.workflow_id);
  }

  const where = conditions.length > 0 ? `WHERE ${conditions.join(' AND ')}` : '';
  const limit = filters.limit ?? 50;
  const offset = filters.offset ?? 0;

  const rows = db.prepare(`
    SELECT
      run_id,
      workflow_id,
      config_hash,
      MIN(created_at) as started_at,
      MAX(completed_at) as completed_at,
      COUNT(*) as total_tasks,
      SUM(CASE WHEN state = 'completed' THEN 1 ELSE 0 END) as completed_tasks,
      SUM(CASE WHEN state = 'failed' THEN 1 ELSE 0 END) as failed_tasks,
      SUM(CASE WHEN assigned_to = 'marvin' THEN 1 ELSE 0 END) as human_tasks,
      decisions
    FROM workflow_task_records
    ${where}
    GROUP BY run_id
    ORDER BY started_at DESC
    LIMIT ? OFFSET ?
  `).all(...params, limit, offset) as any[];

  return rows.map((row: any) => {
    let totalCost = 0;
    try {
      const decisions = JSON.parse(row.decisions || '[]');
      for (const d of decisions) {
        if (d.cost) totalCost += d.cost;
      }
    } catch { /* skip */ }

    return {
      run_id: row.run_id,
      workflow_id: row.workflow_id,
      config_hash: row.config_hash,
      started_at: row.started_at,
      completed_at: row.completed_at,
      total_tasks: row.total_tasks,
      completed_tasks: row.completed_tasks,
      failed_tasks: row.failed_tasks,
      human_tasks: row.human_tasks,
      total_cost: totalCost,
    };
  });
}
```

Note: The `decisions` column in the GROUP BY query returns one arbitrary row's decisions — cost aggregation per-run needs a subquery for accuracy. For v1, this approximation is acceptable. If it matters, a follow-up can compute costs via a window function.

- [ ] **Step 3: Add GET /runs route**

In `routes/workflows.ts`, add before the `/tasks` routes:

```typescript
const listRunsRoute = createRoute({
  method: 'get',
  path: '/runs',
  request: {
    query: z.object({
      workflow_id: z.string().optional(),
      limit: z.string().default('50'),
      offset: z.string().default('0'),
    }),
  },
  responses: {
    200: {
      content: { 'application/json': { schema: WorkflowRunListSchema } },
      description: 'Workflow runs',
    },
  },
});

workflows.openapi(listRunsRoute, (c) => {
  const { workflow_id, limit, offset } = c.req.valid('query');
  const runs = listWorkflowRuns({
    workflow_id,
    limit: parseInt(limit, 10),
    offset: parseInt(offset, 10),
  });
  return c.json(runs, 200);
});
```

- [ ] **Step 4: Build and verify**

Run: `cd ~/development/jimbo/jimbo-api && npm run build`

- [ ] **Step 5: Commit**

```bash
cd ~/development/jimbo/jimbo-api
git add src/schemas/workflows.ts src/services/workflows.ts src/routes/workflows.ts
git commit -m "feat: add workflow runs listing endpoint"
```

---

## Task 7: Compute config_hash in Python Runtime

**Files:**
- Modify: `~/development/openclaw/workspace/jimbo_runtime.py`
- Modify: `~/development/openclaw/workspace/tests/test_jimbo_workflow_orchestration.py`

- [ ] **Step 1: Write failing test for config_hash computation**

Add to `tests/test_jimbo_workflow_orchestration.py`:

```python
class TestConfigHash(unittest.TestCase):
    """Test workflow config_hash computation."""

    def test_loader_computes_config_hash(self):
        """WorkflowLoader.load() returns workflow with config_hash field."""
        with tempfile.TemporaryDirectory() as td:
            workflows_dir = Path(td) / 'workflows'
            workflows_dir.mkdir()
            workflow = {
                "id": "test-wf", "enabled": True, "schedule": "* * * * *",
                "intake": {"source": "vault-api"}, "steps": []
            }
            (workflows_dir / 'test-wf.json').write_text(json.dumps(workflow))

            loader = jimbo_runtime.WorkflowLoader(Path(td))
            result = loader.load('test-wf')

            self.assertIsNotNone(result)
            self.assertIn('config_hash', result)
            self.assertEqual(len(result['config_hash']), 64)  # SHA-256 hex

    def test_same_content_same_hash(self):
        """Identical workflow content produces identical hash."""
        with tempfile.TemporaryDirectory() as td:
            workflows_dir = Path(td) / 'workflows'
            workflows_dir.mkdir()
            workflow = {
                "id": "test-wf", "enabled": True, "schedule": "* * * * *",
                "intake": {"source": "vault-api"}, "steps": []
            }
            (workflows_dir / 'test-wf.json').write_text(json.dumps(workflow))

            loader = jimbo_runtime.WorkflowLoader(Path(td))
            h1 = loader.load('test-wf')['config_hash']
            h2 = loader.load('test-wf')['config_hash']
            self.assertEqual(h1, h2)

    def test_different_content_different_hash(self):
        """Different workflow content produces different hash."""
        with tempfile.TemporaryDirectory() as td:
            workflows_dir = Path(td) / 'workflows'
            workflows_dir.mkdir()

            wf1 = {"id": "wf", "enabled": True, "schedule": "* * * * *",
                    "intake": {"source": "vault-api"}, "steps": []}
            wf2 = {"id": "wf", "enabled": True, "schedule": "0 9 * * *",
                    "intake": {"source": "vault-api"}, "steps": []}

            (workflows_dir / 'wf.json').write_text(json.dumps(wf1))
            loader = jimbo_runtime.WorkflowLoader(Path(td))
            h1 = loader.load('wf')['config_hash']

            (workflows_dir / 'wf.json').write_text(json.dumps(wf2))
            loader2 = jimbo_runtime.WorkflowLoader(Path(td))
            h2 = loader2.load('wf')['config_hash']

            self.assertNotEqual(h1, h2)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/development/openclaw/workspace && python3 -m pytest tests/test_jimbo_workflow_orchestration.py::TestConfigHash -v`
Expected: FAIL — `config_hash` not in result.

- [ ] **Step 3: Implement config_hash in WorkflowLoader**

Add `import hashlib` to the imports at top of `jimbo_runtime.py`.

Modify `WorkflowLoader.load()` — after loading and validating the JSON, before returning:

```python
def load(self, workflow_id: str) -> Optional[Dict[str, Any]]:
    """Load workflow JSON by ID."""
    workflow_path = self.workflows_dir / f"{workflow_id}.json"

    if not workflow_path.exists():
        print(f"ERROR: Workflow not found: {workflow_path}")
        return None

    with open(workflow_path, 'r') as f:
        raw = f.read()
        workflow = json.loads(raw)

    required = ['id', 'enabled', 'schedule', 'intake', 'steps']
    for req in required:
        if req not in workflow:
            print(f"ERROR: Missing required field '{req}'")
            return None

    # Compute config_hash from canonical JSON (sorted keys, no whitespace)
    canonical = json.dumps(workflow, sort_keys=True, separators=(',', ':'))
    workflow['config_hash'] = hashlib.sha256(canonical.encode('utf-8')).hexdigest()

    return workflow
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/development/openclaw/workspace && python3 -m pytest tests/test_jimbo_workflow_orchestration.py::TestConfigHash -v`
Expected: 3 PASS.

- [ ] **Step 5: Run all tests to check for regressions**

Run: `cd ~/development/openclaw/workspace && python3 -m pytest tests/test_jimbo_workflow_orchestration.py -v`
Expected: All 22+ tests pass.

- [ ] **Step 6: Commit**

```bash
cd ~/development/openclaw
git add workspace/jimbo_runtime.py workspace/tests/test_jimbo_workflow_orchestration.py
git commit -m "feat: compute config_hash in WorkflowLoader"
```

---

## Task 8: Pass config_hash Through API Client

**Files:**
- Modify: `~/development/openclaw/workspace/jimbo_runtime.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_jimbo_workflow_orchestration.py`:

```python
class TestConfigHashPropagation(unittest.TestCase):
    """Test config_hash flows through to API calls."""

    @mock.patch('jimbo_runtime.urlopen')
    def test_create_sends_config_hash(self, mock_urlopen):
        """TaskRecordAPI.create() includes config_hash in payload."""
        mock_response = mock.MagicMock()
        mock_response.read.return_value = json.dumps({"id": "test-id"}).encode()
        mock_response.status = 201
        mock_response.__enter__ = mock.MagicMock(return_value=mock_response)
        mock_response.__exit__ = mock.MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        api = jimbo_runtime.TaskRecordAPI(base_url="http://localhost:3100/api/workflows", api_key="test")
        api.create(
            workflow_id="vault-triage",
            source_task_id="task-1",
            run_id="run-1",
            current_step="",
            state="pending",
            assigned_to="jimbo",
            config_hash="abc123hash",
        )

        call_args = mock_urlopen.call_args
        request_obj = call_args[0][0]
        body = json.loads(request_obj.data.decode())
        self.assertEqual(body.get('config_hash'), 'abc123hash')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/development/openclaw/workspace && python3 -m pytest tests/test_jimbo_workflow_orchestration.py::TestConfigHashPropagation -v`
Expected: FAIL — `create()` doesn't accept `config_hash`.

- [ ] **Step 3: Add config_hash parameter to TaskRecordAPI.create()**

In the `TaskRecordAPI.create()` method, add `config_hash: Optional[str] = None` parameter. Include it in the payload dict:

```python
def create(self, workflow_id: str, source_task_id: str, run_id: str,
           current_step: str, state: str, assigned_to: str,
           config_hash: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Create a task record."""
    url = f"{self.base_url}/tasks"
    payload = {
        'workflow_id': workflow_id,
        'source_task_id': source_task_id,
        'run_id': run_id,
        'current_step': current_step,
        'state': state,
        'assigned_to': assigned_to,
    }
    if config_hash:
        payload['config_hash'] = config_hash
    # ... rest of method unchanged
```

- [ ] **Step 4: Pass config_hash in WorkflowRunner.run()**

In `WorkflowRunner.run()`, after loading the workflow, extract config_hash and pass to API:

```python
workflow = self.loader.load(workflow_id)
if not workflow:
    return False

config_hash = workflow.get('config_hash')

# ... in the task creation call:
api_task = self.api.create(
    workflow_id=workflow_id,
    source_task_id=tr.source_task_id,
    run_id=run_id,
    current_step='',
    state='pending',
    assigned_to='jimbo',
    config_hash=config_hash,
)
```

- [ ] **Step 5: Run tests**

Run: `cd ~/development/openclaw/workspace && python3 -m pytest tests/test_jimbo_workflow_orchestration.py -v`
Expected: All pass.

- [ ] **Step 6: Commit**

```bash
cd ~/development/openclaw
git add workspace/jimbo_runtime.py workspace/tests/test_jimbo_workflow_orchestration.py
git commit -m "feat: propagate config_hash through API client"
```

---

## Task 9: Add Proxy Route for Workflows in Site

**Files:**
- Create: `~/development/site/src/pages/api/jimbo/workflows/[...path].ts`

- [ ] **Step 1: Create the proxy route**

Follow the exact pattern from existing proxy routes (e.g., `vault/[...path].ts`):

```typescript
import type { APIRoute } from 'astro';
import { proxyRequest } from '@/lib/server/jimbo-proxy';

const proxy = (method: string): APIRoute => (ctx) =>
  proxyRequest(ctx.request, `/api/workflows/${ctx.params.path ?? ''}`, method);

export const GET = proxy('GET');
export const POST = proxy('POST');
export const PATCH = proxy('PATCH');
```

- [ ] **Step 2: Verify dev server starts**

Run: `cd ~/development/site && npm run dev`
Expected: No errors. Route registered.

- [ ] **Step 3: Commit**

```bash
cd ~/development/site
git add src/pages/api/jimbo/workflows/
git commit -m "feat: add workflows proxy route"
```

---

## Task 10: Add Workflows Navigation to URL State

**Files:**
- Modify: `~/development/site/src/admin-app/dashboard/url-state.ts`

- [ ] **Step 1: Add 'workflows' to SUB_NAVS and Context**

In `url-state.ts`, add `workflows` to the `SUB_NAVS` object:

```typescript
workflows: ['runs', 'compare'],
```

Add `'workflows'` to the `Context` type union.

- [ ] **Step 2: Add workflow-specific state to DashboardViewState**

Add these fields to `DashboardViewState`:

```typescript
workflowsPage: number;
workflowsRunId: string | null; // selected run for drill-down
```

Add defaults in the initial state:

```typescript
workflowsPage: 0,
workflowsRunId: null,
```

Add URL param encoding/decoding for `wfPage` and `wfRun` in `getDashboardViewStateFromUrl` and `buildDashboardUrl`.

- [ ] **Step 3: Build to verify**

Run: `cd ~/development/site && npm run build`
Expected: Build may show type errors in `App.tsx` — that's expected since we haven't wired up the views yet. The `url-state.ts` itself should have no errors.

- [ ] **Step 4: Commit**

```bash
cd ~/development/site
git add src/admin-app/dashboard/url-state.ts
git commit -m "feat: add workflows context to dashboard URL state"
```

---

## Task 11: Build WorkflowRunsView

**Files:**
- Create: `~/development/site/src/admin-app/views/workflows/WorkflowRunsView.tsx`

- [ ] **Step 1: Create the runs list view**

```tsx
import { useCallback, useEffect, useState } from 'react';
import { jimboOperatorFetch } from '@/lib/jimbo-operator-fetch';

const API = '/api/jimbo/workflows';

interface WorkflowRun {
  run_id: string;
  workflow_id: string;
  config_hash: string | null;
  started_at: string;
  completed_at: string | null;
  total_tasks: number;
  completed_tasks: number;
  failed_tasks: number;
  human_tasks: number;
  total_cost: number;
}

interface WorkflowTask {
  id: string;
  workflow_id: string;
  source_task_id: string;
  run_id: string;
  current_step: string;
  state: string;
  assigned_to: string;
  decisions: Array<{
    step: string;
    decision: Record<string, unknown>;
    model?: string;
    cost: number;
    timestamp: string;
  }>;
  final_decision: string | null;
  config_hash: string | null;
  created_at: string;
}

interface Props {
  page: number;
  selectedRunId: string | null;
  onSelectRun: (runId: string | null) => void;
  onPrevPage: () => void;
  onNextPage: () => void;
  formatAge: (ts: string) => string;
}

export function WorkflowRunsView({
  page, selectedRunId, onSelectRun, onPrevPage, onNextPage, formatAge,
}: Props) {
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [tasks, setTasks] = useState<WorkflowTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    jimboOperatorFetch(`${API}/runs?limit=20&offset=${page * 20}`)
      .then(r => r.ok ? r.json() : Promise.reject('Failed to load runs'))
      .then(data => { setRuns(data); setError(null); })
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false));
  }, [page]);

  useEffect(() => {
    if (!selectedRunId) { setTasks([]); return; }
    jimboOperatorFetch(`${API}/tasks?limit=100&offset=0`)
      .then(r => r.ok ? r.json() : Promise.reject('Failed to load tasks'))
      .then((data: WorkflowTask[]) => {
        setTasks(data.filter(t => t.run_id === selectedRunId));
      })
      .catch(() => setTasks([]));
  }, [selectedRunId]);

  if (loading) return <div className="db-loading">loading runs...</div>;
  if (error) return <div className="db-error">{error}</div>;

  return (
    <div className="db-page">
      {selectedRunId ? (
        <RunDetail
          runId={selectedRunId}
          run={runs.find(r => r.run_id === selectedRunId)}
          tasks={tasks}
          onBack={() => onSelectRun(null)}
          formatAge={formatAge}
        />
      ) : (
        <>
          <table className="db-tbl">
            <thead>
              <tr>
                <th>run</th>
                <th>workflow</th>
                <th>age</th>
                <th>tasks</th>
                <th>ok</th>
                <th>fail</th>
                <th>human</th>
                <th>cost</th>
                <th>hash</th>
              </tr>
            </thead>
            <tbody>
              {runs.map(run => (
                <tr key={run.run_id} onClick={() => onSelectRun(run.run_id)} style={{ cursor: 'pointer' }}>
                  <td className="db-mono">{run.run_id.slice(0, 12)}</td>
                  <td>{run.workflow_id}</td>
                  <td>{formatAge(run.started_at)}</td>
                  <td>{run.total_tasks}</td>
                  <td className="db-green">{run.completed_tasks}</td>
                  <td className={run.failed_tasks > 0 ? 'db-red' : ''}>{run.failed_tasks}</td>
                  <td className={run.human_tasks > 0 ? 'db-amber' : ''}>{run.human_tasks}</td>
                  <td>${run.total_cost.toFixed(4)}</td>
                  <td className="db-mono">{run.config_hash?.slice(0, 8) ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="db-pager">
            <button onClick={onPrevPage} disabled={page === 0}>← prev</button>
            <span>page {page + 1}</span>
            <button onClick={onNextPage} disabled={runs.length < 20}>next →</button>
          </div>
        </>
      )}
    </div>
  );
}

function RunDetail({
  runId, run, tasks, onBack, formatAge,
}: {
  runId: string;
  run?: WorkflowRun;
  tasks: WorkflowTask[];
  onBack: () => void;
  formatAge: (ts: string) => string;
}) {
  const [expandedTask, setExpandedTask] = useState<string | null>(null);

  return (
    <div>
      <button className="db-back" onClick={onBack}>← runs</button>
      <h3 className="db-run-title">
        Run: {runId.slice(0, 16)}
        {run && <span className="db-run-meta"> · {run.total_tasks} tasks · ${run.total_cost.toFixed(4)}</span>}
      </h3>
      <table className="db-tbl">
        <thead>
          <tr>
            <th>task</th>
            <th>state</th>
            <th>assigned</th>
            <th>step</th>
            <th>decision</th>
            <th>age</th>
          </tr>
        </thead>
        <tbody>
          {tasks.map(task => (
            <>
              <tr key={task.id} onClick={() => setExpandedTask(expandedTask === task.id ? null : task.id)} style={{ cursor: 'pointer' }}>
                <td className="db-mono">{task.source_task_id}</td>
                <td className={task.state === 'completed' ? 'db-green' : task.state === 'failed' ? 'db-red' : 'db-amber'}>{task.state}</td>
                <td>{task.assigned_to}</td>
                <td>{task.current_step}</td>
                <td>{task.final_decision ?? '—'}</td>
                <td>{formatAge(task.created_at)}</td>
              </tr>
              {expandedTask === task.id && (
                <tr key={`${task.id}-detail`}>
                  <td colSpan={6}>
                    <div className="db-decision-tree">
                      {task.decisions.map((d, i) => (
                        <div key={i} className="db-decision-node">
                          <span className="db-decision-step">{d.step}</span>
                          {d.model && <span className="db-decision-model">[{d.model}]</span>}
                          {d.cost > 0 && <span className="db-decision-cost">${d.cost.toFixed(4)}</span>}
                          <pre className="db-decision-json">{JSON.stringify(d.decision, null, 2)}</pre>
                        </div>
                      ))}
                    </div>
                  </td>
                </tr>
              )}
            </>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
cd ~/development/site
git add src/admin-app/views/workflows/
git commit -m "feat: add WorkflowRunsView component"
```

---

## Task 12: Build WorkflowCompareView

**Files:**
- Create: `~/development/site/src/admin-app/views/workflows/WorkflowCompareView.tsx`

- [ ] **Step 1: Create the compare view**

```tsx
import { useEffect, useState } from 'react';
import { jimboOperatorFetch } from '@/lib/jimbo-operator-fetch';

const API = '/api/jimbo/workflows';

interface MetricsData {
  total_tasks: number;
  completed: number;
  failed: number;
  awaiting_human: number;
  success_rate: number;
  avg_cost: number;
  human_override_rate: number;
  by_config_hash?: Array<{
    config_hash: string | null;
    total_tasks: number;
    success_rate: number;
    avg_cost: number;
    human_override_rate: number;
  }>;
}

export function WorkflowCompareView() {
  const [metrics, setMetrics] = useState<MetricsData | null>(null);
  const [period, setPeriod] = useState('7d');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    jimboOperatorFetch(`${API}/metrics?workflow=vault-triage&period=${period}`)
      .then(r => r.ok ? r.json() : Promise.reject('Failed to load metrics'))
      .then(data => { setMetrics(data); setError(null); })
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false));
  }, [period]);

  if (loading) return <div className="db-loading">loading metrics...</div>;
  if (error) return <div className="db-error">{error}</div>;
  if (!metrics) return null;

  const pct = (n: number) => `${(n * 100).toFixed(1)}%`;

  return (
    <div className="db-page">
      <div className="db-period-picker">
        {['1d', '7d', '30d'].map(p => (
          <button key={p} className={period === p ? 'on' : ''} onClick={() => setPeriod(p)}>{p}</button>
        ))}
      </div>

      <div className="db-metrics-summary">
        <div className="db-metric">
          <span className="db-metric-label">total</span>
          <span className="db-metric-value">{metrics.total_tasks}</span>
        </div>
        <div className="db-metric">
          <span className="db-metric-label">success</span>
          <span className="db-metric-value db-green">{pct(metrics.success_rate)}</span>
        </div>
        <div className="db-metric">
          <span className="db-metric-label">avg cost</span>
          <span className="db-metric-value">${metrics.avg_cost.toFixed(4)}</span>
        </div>
        <div className="db-metric">
          <span className="db-metric-label">human %</span>
          <span className="db-metric-value db-amber">{pct(metrics.human_override_rate)}</span>
        </div>
      </div>

      {metrics.by_config_hash && metrics.by_config_hash.length > 1 && (
        <>
          <h3 className="db-section-title">by config variant</h3>
          <table className="db-tbl">
            <thead>
              <tr>
                <th>hash</th>
                <th>tasks</th>
                <th>success</th>
                <th>human %</th>
              </tr>
            </thead>
            <tbody>
              {metrics.by_config_hash.map((row, i) => (
                <tr key={i}>
                  <td className="db-mono">{row.config_hash?.slice(0, 12) ?? 'none'}</td>
                  <td>{row.total_tasks}</td>
                  <td className="db-green">{pct(row.success_rate)}</td>
                  <td className="db-amber">{pct(row.human_override_rate)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
cd ~/development/site
git add src/admin-app/views/workflows/WorkflowCompareView.tsx
git commit -m "feat: add WorkflowCompareView metrics component"
```

---

## Task 13: Wire Up Workflows in AdminApp

**Files:**
- Modify: `~/development/site/src/admin-app/App.tsx`

- [ ] **Step 1: Add imports**

Add to the imports section of `App.tsx`:

```typescript
import { WorkflowRunsView } from '@/admin-app/views/workflows/WorkflowRunsView';
import { WorkflowCompareView } from '@/admin-app/views/workflows/WorkflowCompareView';
```

- [ ] **Step 2: Add workflows rendering block**

After the `{ctx === 'system' && (...)}` block, add:

```tsx
{ctx === 'workflows' && (
  <div className="db-page">
    {subNav === 0 && (
      <WorkflowRunsView
        page={viewState.workflowsPage}
        selectedRunId={viewState.workflowsRunId}
        onSelectRun={(runId) => updateViewState((current) => ({
          ...current,
          workflowsRunId: runId,
        }))}
        onPrevPage={() => updateViewState((current) => ({
          ...current,
          workflowsPage: Math.max(0, current.workflowsPage - 1),
        }))}
        onNextPage={() => updateViewState((current) => ({
          ...current,
          workflowsPage: current.workflowsPage + 1,
        }))}
        formatAge={timeAgo}
      />
    )}
    {subNav === 1 && <WorkflowCompareView />}
  </div>
)}
```

- [ ] **Step 3: Build and test locally**

Run: `cd ~/development/site && npm run build`
Expected: Clean build. Then `npm run dev` and navigate to `/app/jimbo/dashboard` — "workflows" tab should appear in navigation.

- [ ] **Step 4: Commit**

```bash
cd ~/development/site
git add src/admin-app/App.tsx
git commit -m "feat: wire up workflows tab in dashboard"
```

---

## Task 14: Add Dashboard Styles for Workflows

**Files:**
- Modify: `~/development/site/src/components/admin/DashboardPage.astro`

- [ ] **Step 1: Add workflow-specific styles**

Append to the `<style lang="scss" is:global>` block in `DashboardPage.astro`:

```scss
/* ── workflow views ── */

.db-back {
  background: none;
  border: none;
  color: var(--db-accent);
  font-family: var(--font-mono);
  font-size: 12px;
  cursor: pointer;
  padding: 4px 0;
  margin-bottom: 8px;
  &:hover { text-decoration: underline; }
}

.db-run-title {
  font-size: 13px;
  font-weight: 600;
  margin: 8px 0;
}

.db-run-meta {
  font-weight: 400;
  color: var(--color-text-muted);
}

.db-decision-tree {
  padding: 8px 12px;
  background: var(--color-surface);
  border-left: 2px solid var(--db-accent);
}

.db-decision-node {
  margin-bottom: 8px;
  &:last-child { margin-bottom: 0; }
}

.db-decision-step {
  font-weight: 600;
  color: var(--db-accent);
  margin-right: 6px;
}

.db-decision-model {
  color: var(--color-text-muted);
  margin-right: 6px;
}

.db-decision-cost {
  color: var(--db-amber);
  margin-right: 6px;
}

.db-decision-json {
  font-size: 11px;
  margin: 4px 0 0;
  padding: 4px 8px;
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  overflow-x: auto;
  max-height: 120px;
}

.db-period-picker {
  margin-bottom: 12px;
  button {
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    color: var(--color-text);
    font-family: var(--font-mono);
    font-size: 11px;
    padding: 3px 8px;
    cursor: pointer;
    margin-right: 4px;
    &.on { border-color: var(--db-accent); color: var(--db-accent); }
  }
}

.db-metrics-summary {
  display: flex;
  gap: 16px;
  margin-bottom: 16px;
  padding: 8px 0;
  border-bottom: 1px solid var(--color-border);
}

.db-metric {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.db-metric-label {
  font-size: 10px;
  text-transform: uppercase;
  color: var(--color-text-muted);
  letter-spacing: 0.5px;
}

.db-metric-value {
  font-size: 16px;
  font-weight: 600;
}

.db-section-title {
  font-size: 12px;
  font-weight: 600;
  margin: 12px 0 6px;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.db-green { color: var(--db-green); }
.db-red { color: var(--db-red); }
.db-amber { color: var(--db-amber); }
.db-mono { font-family: var(--font-mono); }

.db-pager {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  font-size: 11px;
  button {
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    color: var(--color-text);
    font-family: var(--font-mono);
    font-size: 11px;
    padding: 2px 8px;
    cursor: pointer;
    &:disabled { opacity: 0.3; cursor: default; }
  }
}
```

Note: Some of these classes (`.db-green`, `.db-red`, etc.) may already exist in the file. Check before adding duplicates — only add the ones that are new.

- [ ] **Step 2: Build and visually verify**

Run: `cd ~/development/site && npm run dev`
Navigate to `/app/jimbo/dashboard`, click "workflows" tab. Verify:
- Runs tab loads (may show empty if no data yet)
- Compare tab loads metrics (may show zeros)
- Styling matches the lo-fi dashboard aesthetic

- [ ] **Step 3: Commit**

```bash
cd ~/development/site
git add src/components/admin/DashboardPage.astro
git commit -m "feat: add workflow dashboard styles"
```

---

## Task 15: Deploy and Verify End-to-End

- [ ] **Step 1: Deploy jimbo-api**

```bash
cd ~/development/jimbo/jimbo-api
git push origin main
ssh jimbo 'cd /home/openclaw/jimbo-api && git pull && npm run build && sudo systemctl restart jimbo-api'
```

- [ ] **Step 2: Verify metrics endpoint on VPS**

```bash
ssh jimbo 'curl -s http://localhost:3100/api/workflows/metrics?workflow=vault-triage&period=30d -H "X-API-Key: $JIMBO_API_KEY" | python3 -m json.tool'
```

Expected: JSON with `total_tasks`, `success_rate`, etc. Values may be 0 if no workflow runs exist with config_hash yet.

- [ ] **Step 3: Push workspace changes**

```bash
cd ~/development/openclaw
bash workspace/workspace-push.sh
```

- [ ] **Step 4: Trigger a test workflow run**

```bash
ssh jimbo 'cd /home/openclaw/workspace && JIMBO_API_KEY=$(grep JIMBO_API_KEY /opt/jimbo-api.env | cut -d= -f2) python3 vault-orchestration-cron.py'
```

Verify output shows config_hash being computed and task records including it.

- [ ] **Step 5: Verify dashboard**

Deploy site (or check localhost:4321). Navigate to `/app/jimbo/dashboard` → workflows tab. Confirm the test run appears with data.

- [ ] **Step 6: Commit completion doc**

```bash
cd ~/development/openclaw
# Write completion doc (separate step)
git add docs/superpowers/completions/
git commit -m "docs: phase 2 completion summary"
```

---

## Summary

| Task | Repo | What |
|------|------|------|
| 1-6 | jimbo-api | DB migration, schemas, metrics service, runs endpoint |
| 7-8 | openclaw | Python config_hash computation + propagation |
| 9-14 | site | Proxy route, URL state, 2 view components, wiring, styles |
| 15 | all | Deploy and verify end-to-end |

**Estimated work:** Tasks 1-8 (backend) can be done in one session. Tasks 9-14 (frontend) in a second session. Task 15 (deploy) third session or same day.

**Dependencies:** Tasks 1-6 must be done before 7-8 (API needs config_hash support before Python sends it). Tasks 9-14 can start after Task 6 (proxy just needs the endpoints to exist). Task 15 requires all others complete.
