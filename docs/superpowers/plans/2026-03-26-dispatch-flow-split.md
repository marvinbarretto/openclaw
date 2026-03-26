# Dispatch Flow Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable dispatch to pull commissions from GitHub Issues (ralph label) and deliver recon tasks without PR ceremony, so the dispatch system can start processing real work.

**Architecture:** Two changes to jimbo-api: (1) new `proposeFromGitHub()` service method that queries the GitHub API for `ralph`-labeled issues and inserts them into the dispatch queue with `flow=commission`, `task_source=github`; (2) schema additions for `flow`, `issue_number`, `issue_repo` on dispatch_queue. On the openclaw side: a new recon output contract template and updates to the existing commission output contract to include issue auto-close. The worker guide (dispatch-check.md) gets updated to branch on `flow` when selecting the output contract.

**Tech Stack:** TypeScript, Hono, better-sqlite3, Vitest, GitHub REST API

**Repos:**
- `~/development/jimbo/jimbo-api` — API changes (schema, types, service, routes, tests)
- `~/development/openclaw` — template changes (output contracts, worker guide)

---

### Task 1: Schema — add flow and issue columns to dispatch_queue

**Files:**
- Modify: `~/development/jimbo/jimbo-api/src/db/index.ts:334-343` (after PR feedback loop columns)
- Modify: `~/development/jimbo/jimbo-api/src/types/dispatch.ts`

- [ ] **Step 1: Write the failing test**

Add to `~/development/jimbo/jimbo-api/test/dispatch.test.ts`, inside the top-level `describe`:

```typescript
describe('flow and issue columns', () => {
  it('dispatch_queue should have flow, issue_number, issue_repo columns', () => {
    const db = getDb();
    const row = db.prepare(
      `INSERT INTO dispatch_queue (task_id, task_source, agent_type, status, flow, issue_number, issue_repo)
       VALUES ('flow-test', 'github', 'coder', 'proposed', 'commission', 42, 'marvinbarretto/localshout-next')
       RETURNING *`
    ).get() as Record<string, unknown>;

    expect(row.flow).toBe('commission');
    expect(row.issue_number).toBe(42);
    expect(row.issue_repo).toBe('marvinbarretto/localshout-next');
  });

  it('flow should default to commission', () => {
    const db = getDb();
    const row = db.prepare(
      `INSERT INTO dispatch_queue (task_id, task_source, agent_type, status)
       VALUES ('flow-default', 'vault', 'researcher', 'proposed')
       RETURNING flow`
    ).get() as { flow: string };

    expect(row.flow).toBe('commission');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/development/jimbo/jimbo-api && npx vitest run test/dispatch.test.ts --reporter=verbose 2>&1 | tail -20`
Expected: FAIL — `flow` column doesn't exist yet.

- [ ] **Step 3: Add migration columns in db/index.ts**

Add after the PR feedback loop columns block (after line 343) in `~/development/jimbo/jimbo-api/src/db/index.ts`:

```typescript
  // Flow split columns (2026-03-26)
  const dispatchFlowCols: [string, string][] = [
    ['flow', "TEXT NOT NULL DEFAULT 'commission'"],
    ['issue_number', 'INTEGER'],
    ['issue_repo', 'TEXT'],
  ];
  for (const [col, type] of dispatchFlowCols) {
    try { db.exec(`ALTER TABLE dispatch_queue ADD COLUMN ${col} ${type}`); } catch {}
  }
```

- [ ] **Step 4: Update DispatchQueueItem type**

In `~/development/jimbo/jimbo-api/src/types/dispatch.ts`, add three fields to the `DispatchQueueItem` interface, after `rejection_reason`:

```typescript
  flow: 'commission' | 'recon';
  issue_number: number | null;
  issue_repo: string | null;
```

Also add the `DispatchFlow` type and export it:

```typescript
export type DispatchFlow = 'commission' | 'recon';
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd ~/development/jimbo/jimbo-api && npx vitest run test/dispatch.test.ts --reporter=verbose 2>&1 | tail -20`
Expected: PASS — all tests including the new ones.

- [ ] **Step 6: Commit**

```bash
cd ~/development/jimbo/jimbo-api
git add src/db/index.ts src/types/dispatch.ts test/dispatch.test.ts
git commit -m "feat: add flow, issue_number, issue_repo columns to dispatch_queue"
```

---

### Task 2: Service — proposeFromGitHub()

**Files:**
- Modify: `~/development/jimbo/jimbo-api/src/services/dispatch.ts`
- Modify: `~/development/jimbo/jimbo-api/src/types/dispatch.ts`
- Test: `~/development/jimbo/jimbo-api/test/dispatch.test.ts`

- [ ] **Step 1: Add types for GitHub proposal**

In `~/development/jimbo/jimbo-api/src/types/dispatch.ts`, add:

```typescript
export interface GitHubIssue {
  number: number;
  title: string;
  body: string | null;
  labels: Array<{ name: string }>;
}

export interface DispatchProposeFromGitHubParams {
  repos: string[];       // e.g. ['marvinbarretto/localshout-next']
  batch_size?: number;   // default 3
}
```

- [ ] **Step 2: Write the failing tests**

Add to `~/development/jimbo/jimbo-api/test/dispatch.test.ts`:

```typescript
const { proposeFromGitHub } = await import('../src/services/dispatch.js');

describe('proposeFromGitHub', () => {
  it('should insert GitHub issues into dispatch_queue', () => {
    const mockIssues: GitHubIssue[] = [
      { number: 73, title: 'fix: Re-enable E2E tests', body: '## Problem\nTests are broken\n\n## Acceptance criteria\n- [ ] E2E tests pass', labels: [{ name: 'ralph' }, { name: 'infrastructure' }] },
      { number: 117, title: 'App Store submission', body: '## Problem\nNeed to submit', labels: [{ name: 'human' }, { name: 'ios' }] },
    ];

    const result = proposeFromGitHub(mockIssues, 'marvinbarretto/localshout-next');
    expect(result.items).toHaveLength(1); // only #73 — #117 has no ralph label
    expect(result.items[0].task_id).toBe('localshout-next#73');
    expect(result.items[0].task_source).toBe('github');
    expect(result.items[0].flow).toBe('commission');
    expect(result.items[0].issue_number).toBe(73);
    expect(result.items[0].issue_repo).toBe('marvinbarretto/localshout-next');
    expect(result.items[0].agent_type).toBe('coder');
  });

  it('should infer agent_type from labels', () => {
    const mockIssues: GitHubIssue[] = [
      { number: 10, title: 'Research gig feeds', body: 'body', labels: [{ name: 'ralph' }, { name: 'research' }] },
    ];

    const result = proposeFromGitHub(mockIssues, 'marvinbarretto/localshout-next');
    expect(result.items[0].agent_type).toBe('researcher');
  });

  it('should skip issues already in the dispatch queue', () => {
    const db = getDb();
    db.prepare(
      `INSERT INTO dispatch_queue (task_id, task_source, agent_type, status, flow, issue_number, issue_repo)
       VALUES ('localshout-next#50', 'github', 'coder', 'completed', 'commission', 50, 'marvinbarretto/localshout-next')`
    ).run();

    const mockIssues: GitHubIssue[] = [
      { number: 50, title: 'Already dispatched', body: 'body', labels: [{ name: 'ralph' }] },
      { number: 51, title: 'New issue', body: 'body', labels: [{ name: 'ralph' }] },
    ];

    const result = proposeFromGitHub(mockIssues, 'marvinbarretto/localshout-next');
    expect(result.items).toHaveLength(1);
    expect(result.items[0].issue_number).toBe(51);
  });

  it('should skip issues without acceptance criteria in body', () => {
    const mockIssues: GitHubIssue[] = [
      { number: 60, title: 'Vague issue', body: 'Just do the thing', labels: [{ name: 'ralph' }] },
      { number: 61, title: 'Well-specced', body: '## Acceptance criteria\n- [ ] Tests pass', labels: [{ name: 'ralph' }] },
    ];

    const result = proposeFromGitHub(mockIssues, 'marvinbarretto/localshout-next');
    expect(result.items).toHaveLength(1);
    expect(result.items[0].issue_number).toBe(61);
  });

  it('should respect batch_size', () => {
    const mockIssues: GitHubIssue[] = Array.from({ length: 5 }, (_, i) => ({
      number: i + 1,
      title: `Issue ${i + 1}`,
      body: '## Acceptance criteria\n- [ ] Done',
      labels: [{ name: 'ralph' }],
    }));

    const result = proposeFromGitHub(mockIssues, 'marvinbarretto/localshout-next', 2);
    expect(result.items).toHaveLength(2);
  });

  it('should sort by priority labels', () => {
    const mockIssues: GitHubIssue[] = [
      { number: 1, title: 'Low priority', body: '## Acceptance criteria\n- [ ] Done', labels: [{ name: 'ralph' }] },
      { number: 2, title: 'Blocks launch', body: '## Acceptance criteria\n- [ ] Done', labels: [{ name: 'ralph' }, { name: 'P0-blocks-launch' }] },
      { number: 3, title: 'Before launch', body: '## Acceptance criteria\n- [ ] Done', labels: [{ name: 'ralph' }, { name: 'P1-before-launch' }] },
    ];

    const result = proposeFromGitHub(mockIssues, 'marvinbarretto/localshout-next');
    expect(result.items[0].issue_number).toBe(2); // P0 first
    expect(result.items[1].issue_number).toBe(3); // P1 second
    expect(result.items[2].issue_number).toBe(1); // no priority last
  });
});
```

Also add this import at the top of the test file alongside the existing imports:

```typescript
import type { GitHubIssue } from '../src/types/dispatch.js';
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd ~/development/jimbo/jimbo-api && npx vitest run test/dispatch.test.ts --reporter=verbose 2>&1 | tail -30`
Expected: FAIL — `proposeFromGitHub` doesn't exist yet.

- [ ] **Step 4: Implement proposeFromGitHub**

Add to `~/development/jimbo/jimbo-api/src/services/dispatch.ts`:

```typescript
import type { GitHubIssue, AgentType } from '../types/dispatch.js';

const PRIORITY_LABELS: Record<string, number> = {
  'P0-blocks-launch': 100,
  'P1-before-launch': 75,
  'P2: Soon': 50,
};

function inferAgentType(labels: Array<{ name: string }>): AgentType {
  const names = labels.map(l => l.name);
  if (names.includes('research')) return 'researcher';
  return 'coder';
}

function getPriorityScore(labels: Array<{ name: string }>): number {
  for (const label of labels) {
    if (label.name in PRIORITY_LABELS) return PRIORITY_LABELS[label.name];
  }
  return 0;
}

function hasAcceptanceCriteria(body: string | null): boolean {
  if (!body) return false;
  return /acceptance\s+criteria/i.test(body);
}

export function proposeFromGitHub(
  issues: GitHubIssue[],
  repo: string,
  batchSize: number = 3,
): { batch_id: string; items: DispatchQueueItem[]; token: string } {
  const db = getDb();
  const batchId = generateBatchId();
  const timestamp = now();
  const repoShort = repo.split('/').pop() ?? repo;

  // Filter: must have ralph label, acceptance criteria, and not already queued
  const candidates = issues
    .filter(issue => issue.labels.some(l => l.name === 'ralph'))
    .filter(issue => hasAcceptanceCriteria(issue.body))
    .filter(issue => {
      const existing = db.prepare(
        `SELECT id FROM dispatch_queue WHERE issue_number = ? AND issue_repo = ? AND status NOT IN ('failed')`
      ).get(issue.number, repo);
      return !existing;
    })
    .sort((a, b) => getPriorityScore(b.labels) - getPriorityScore(a.labels))
    .slice(0, batchSize);

  const items: DispatchQueueItem[] = [];

  for (const issue of candidates) {
    const agentType = inferAgentType(issue.labels);
    const taskId = `${repoShort}#${issue.number}`;

    const result = db.prepare(`
      INSERT INTO dispatch_queue (task_id, task_source, agent_type, batch_id, status, flow, issue_number, issue_repo, proposed_at)
      VALUES (?, 'github', ?, ?, 'proposed', 'commission', ?, ?, ?)
    `).run(taskId, agentType, batchId, issue.number, repo, timestamp);

    const item = db.prepare('SELECT * FROM dispatch_queue WHERE id = ?').get(result.lastInsertRowid) as DispatchQueueItem;
    items.push(item);
  }

  const token = generateApprovalToken(batchId);
  return { batch_id: batchId, items, token };
}
```

- [ ] **Step 5: Export proposeFromGitHub**

Make sure `proposeFromGitHub` is exported from the module. It's already `export function`, so just add it to the import in the test file:

Update the test file's dynamic import to include `proposeFromGitHub`:

```typescript
const {
  proposeBatch,
  approveBatch,
  rejectBatch,
  getNextApproved,
  startTask,
  completeTask,
  failTask,
  listQueue,
  getRunningTask,
  getProposedBatch,
  expireOldProposals,
  generateApprovalToken,
  validateApprovalToken,
  lookupByPrUrl,
  lookupByBranch,
  proposeFromGitHub,
} = await import('../src/services/dispatch.js');
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd ~/development/jimbo/jimbo-api && npx vitest run test/dispatch.test.ts --reporter=verbose 2>&1 | tail -30`
Expected: PASS — all tests including proposeFromGitHub tests.

- [ ] **Step 7: Commit**

```bash
cd ~/development/jimbo/jimbo-api
git add src/services/dispatch.ts src/types/dispatch.ts test/dispatch.test.ts
git commit -m "feat: add proposeFromGitHub for commission dispatch from GitHub Issues"
```

---

### Task 3: Route — POST /propose/github endpoint

**Files:**
- Modify: `~/development/jimbo/jimbo-api/src/routes/dispatch.ts`
- Modify: `~/development/jimbo/jimbo-api/src/services/dispatch.ts` (add fetchGitHubIssues helper)

- [ ] **Step 1: Add fetchGitHubIssues helper to dispatch service**

This function calls the GitHub API to get open issues with the `ralph` label. Add to `~/development/jimbo/jimbo-api/src/services/dispatch.ts`:

```typescript
export async function fetchGitHubIssues(repo: string): Promise<GitHubIssue[]> {
  const token = process.env.GITHUB_TOKEN;
  if (!token) throw new Error('GITHUB_TOKEN not set');

  const url = `https://api.github.com/repos/${repo}/issues?labels=ralph&state=open&sort=created&direction=asc&per_page=30`;
  const res = await fetch(url, {
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/vnd.github+json',
    },
  });

  if (!res.ok) {
    throw new Error(`GitHub API error: ${res.status} ${res.statusText}`);
  }

  return res.json() as Promise<GitHubIssue[]>;
}
```

- [ ] **Step 2: Add the route**

Add to `~/development/jimbo/jimbo-api/src/routes/dispatch.ts`, after the existing `/propose` route. Also add `proposeFromGitHub` and `fetchGitHubIssues` to the import:

```typescript
// Propose commissions from GitHub Issues
dispatch.post('/propose/github', async (c) => {
  const body = await c.req.json<{ repos?: string[]; batch_size?: number }>().catch(() => ({}));
  const repos = body.repos ?? ['marvinbarretto/localshout-next'];
  const batchSize = body.batch_size ?? 3;

  const allItems: DispatchQueueItem[] = [];
  let batchId: string | null = null;
  let token: string | null = null;

  for (const repo of repos) {
    try {
      const issues = await fetchGitHubIssues(repo);
      if (issues.length === 0) continue;

      const result = proposeFromGitHub(issues, repo, batchSize - allItems.length);
      if (result.items.length > 0) {
        allItems.push(...result.items);
        batchId = result.batch_id;
        token = result.token;
      }
    } catch (err) {
      return c.json({ error: `Failed to fetch issues from ${repo}: ${(err as Error).message}` }, 500);
    }

    if (allItems.length >= batchSize) break;
  }

  if (allItems.length === 0) {
    return c.json({ message: 'No eligible ralph issues found', batch_id: null, items: [] });
  }

  const baseUrl = process.env.JIMBO_API_URL || 'https://167.99.206.214';
  return c.json({
    batch_id: batchId,
    items: allItems,
    token,
    approve_url: `${baseUrl}/dispatch/approve?batch=${batchId}&token=${token}`,
    reject_url: `${baseUrl}/dispatch/reject?batch=${batchId}&token=${token}`,
  }, 201);
});
```

- [ ] **Step 3: Update the imports at the top of dispatch.ts routes**

Add `proposeFromGitHub` and `fetchGitHubIssues` to the import from `'../services/dispatch.js'`. Also import the `DispatchQueueItem` type:

```typescript
import type { DispatchQueueItem } from '../types/dispatch.js';
```

- [ ] **Step 4: Run all dispatch tests to verify nothing broke**

Run: `cd ~/development/jimbo/jimbo-api && npx vitest run test/dispatch.test.ts --reporter=verbose 2>&1 | tail -20`
Expected: PASS — existing tests still work.

- [ ] **Step 5: Commit**

```bash
cd ~/development/jimbo/jimbo-api
git add src/routes/dispatch.ts src/services/dispatch.ts
git commit -m "feat: add POST /propose/github route for commission dispatch"
```

---

### Task 4: Update completeTask to skip vault update for GitHub-sourced tasks

**Files:**
- Modify: `~/development/jimbo/jimbo-api/src/services/dispatch.ts`
- Test: `~/development/jimbo/jimbo-api/test/dispatch.test.ts`

- [ ] **Step 1: Write the failing test**

Add to `~/development/jimbo/jimbo-api/test/dispatch.test.ts`, inside the `task execution lifecycle` describe block:

```typescript
it('should NOT update vault_notes for github-sourced tasks', () => {
  const db = getDb();
  // Insert a github-sourced dispatch item directly (no vault note)
  db.prepare(
    `INSERT INTO dispatch_queue (task_id, task_source, agent_type, status, flow, issue_number, issue_repo)
     VALUES ('localshout-next#99', 'github', 'coder', 'approved', 'commission', 99, 'marvinbarretto/localshout-next')`
  ).run();

  const item = db.prepare(`SELECT * FROM dispatch_queue WHERE task_id = 'localshout-next#99'`).get() as DispatchQueueItem;
  startTask(item.id);
  const result = completeTask({
    id: item.id,
    result_summary: 'PR opened',
    pr_url: 'https://github.com/marvinbarretto/localshout-next/pull/99',
  });

  expect(result?.status).toBe('completed');
  // No vault_notes row should exist or be updated — this task came from GitHub
  const vaultRow = db.prepare(`SELECT * FROM vault_notes WHERE id = 'localshout-next#99'`).get();
  expect(vaultRow).toBeUndefined();
});
```

- [ ] **Step 2: Run test to verify it passes (or fails if vault update crashes)**

Run: `cd ~/development/jimbo/jimbo-api && npx vitest run test/dispatch.test.ts --reporter=verbose 2>&1 | tail -20`

Check: the current `completeTask` tries to update `vault_notes` for all tasks with `task_source === 'vault'`. Since this test uses `task_source = 'github'`, the existing code should already skip the vault update. If it passes, this is a verification test. If it fails (e.g. because the vault update query errors on missing row), we need the fix.

- [ ] **Step 3: If the test fails, update completeTask**

In `~/development/jimbo/jimbo-api/src/services/dispatch.ts`, the `completeTask` function already checks `item?.task_source === 'vault'` before updating vault_notes. Verify this guard exists. If it does, no code change needed — the test is a safety net.

- [ ] **Step 4: Commit**

```bash
cd ~/development/jimbo/jimbo-api
git add test/dispatch.test.ts
git commit -m "test: verify github-sourced tasks skip vault_notes update"
```

---

### Task 5: Commission output contract — add issue auto-close

**Files:**
- Modify: `~/development/openclaw/workspace/dispatch/templates/_output-contract.md`

- [ ] **Step 1: Add issue closing line to PR body template**

In `~/development/openclaw/workspace/dispatch/templates/_output-contract.md`, update the PR Body section. After the existing `Dispatched by Jimbo` footer line, add the issue reference. Find the line:

```
Dispatched by Jimbo · Task #{seq} · Agent: {agent_type}
```

Replace with:

```
Dispatched by Jimbo · Task #{seq} · Agent: {agent_type}
{issue_close_line}
```

- [ ] **Step 2: Add explanation of {issue_close_line} variable**

In the same file, in the template variables section (or add one near the top), add an explanation. After the existing variable list on line 44 (`{task_id}`, `{seq}`, `{agent_type}`), add:

```
- `{issue_close_line}` — For commissions: `Closes owner/repo#N`. For non-commission tasks: empty string.
```

- [ ] **Step 3: Commit**

```bash
cd ~/development/openclaw
git add workspace/dispatch/templates/_output-contract.md
git commit -m "feat: add issue auto-close line to commission output contract"
```

---

### Task 6: Recon output contract — new template

**Files:**
- Create: `~/development/openclaw/workspace/dispatch/templates/_recon-contract.md`

- [ ] **Step 1: Create the recon output contract**

Write to `~/development/openclaw/workspace/dispatch/templates/_recon-contract.md`:

```markdown
# Recon Output Contract

Every recon task follows this contract. Your agent-specific template tells you HOW to do the work. This contract tells you how to DELIVER it.

## Output

1. Clone the target repo and checkout main (or the repo's default branch)
2. Write your output to the specified output path
3. Commit with conventional commit: `docs: {title}`
4. Push directly to main

Do NOT create a branch. Do NOT open a PR. Commit directly.

## Result JSON

Write your result to `/tmp/dispatch-{task_id}.result` as JSON:

### On completion:

```json
{
  "status": "completed",
  "summary": "2-3 sentence summary of findings/output",
  "artifact_path": "path/to/output/file.md",
  "repo": "owner/repo",
  "commit_sha": "abc123"
}
```

### On blocked:

```json
{
  "status": "blocked",
  "summary": "What prevented completion",
  "blockers": ["Specific reason 1"]
}
```

## Rules

- NEVER ask for user input — you are autonomous
- Commit directly to main — no branch, no PR
- If you cannot complete, use blocked status
- If a tool is blocked, find an alternative
```

- [ ] **Step 2: Commit**

```bash
cd ~/development/openclaw
git add workspace/dispatch/templates/_recon-contract.md
git commit -m "feat: add recon output contract for direct-commit delivery"
```

---

### Task 7: Update worker guide — flow-based contract selection

**Files:**
- Modify: `~/development/openclaw/workspace/dispatch/dispatch-check.md`

- [ ] **Step 1: Update the prompt assembly step**

In `~/development/openclaw/workspace/dispatch/dispatch-check.md`, update step 5 (currently reads the output contract) to branch on flow. Replace the current step 5:

```
5. Read the output contract from `~/development/openclaw/workspace/dispatch/templates/_output-contract.md`
```

With:

```
5. Select the output contract based on the task's `flow` field:
   - If `flow` is `commission`: Read `~/development/openclaw/workspace/dispatch/templates/_output-contract.md`
   - If `flow` is `recon`: Read `~/development/openclaw/workspace/dispatch/templates/_recon-contract.md`
```

- [ ] **Step 2: Update step 6 — add issue_close_line variable**

In the template variables list (step 6), add:

```
- `{issue_close_line}`: For commissions with an issue_number: `Closes {issue_repo}#{issue_number}`. Otherwise: empty string.
```

- [ ] **Step 3: Update step 3 — commission context from GitHub**

Add a new step between the current step 3 (get vault task details) and step 4 (read template). This handles fetching richer context for commissions:

```
3b. If `task_source` is `github`, fetch the issue body for richer context:
    ```bash
    curl -sf -H "Authorization: Bearer $GITHUB_TOKEN" -H "Accept: application/vnd.github+json" \
      "https://api.github.com/repos/{issue_repo}/issues/{issue_number}"
    ```
    Use the issue body as the task context (replaces vault task body for commissions).
    The issue body contains Problem, Expected behaviour, Acceptance criteria, Context, and Scope sections.
```

- [ ] **Step 4: Update step 10 — recon Telegram notification**

Add after the completion reporting step:

```
10b. If `flow` is `recon`, send a Telegram notification:
     ```bash
     curl -sf -X POST -H "X-API-Key: $JIMBO_API_KEY" -H "Content-Type: application/json" \
       "$JIMBO_API_URL/api/dispatch/notify-recon" -d '{"id": DISPATCH_ID}'
     ```
```

- [ ] **Step 5: Commit**

```bash
cd ~/development/openclaw
git add workspace/dispatch/dispatch-check.md
git commit -m "feat: update dispatch worker guide for flow-based contract selection"
```

---

### Task 8: Route — POST /dispatch/notify-recon endpoint

**Files:**
- Modify: `~/development/jimbo/jimbo-api/src/routes/dispatch.ts`

- [ ] **Step 1: Add the notify-recon route**

Add to `~/development/jimbo/jimbo-api/src/routes/dispatch.ts`, after the `/complete` route:

```typescript
// Send Telegram notification for completed recon tasks
dispatch.post('/notify-recon', async (c) => {
  const { id } = await c.req.json<{ id: number }>();
  if (!id) return c.json({ error: 'id required' }, 400);

  const item = listQueue({ status: 'completed' }).items.find(i => i.id === id);
  if (!item) return c.json({ error: 'Completed task not found' }, 404);
  if (item.flow !== 'recon') return c.json({ error: 'Task is not a recon task' }, 400);

  const summary = item.result_summary ?? 'No summary available';
  const taskId = item.task_id;
  const message = `📄 Recon complete: ${taskId}\n\n${summary}`;

  await sendTelegram(message);
  return c.json({ notified: true, task_id: taskId });
});
```

Add `sendTelegram` to the imports at the top:

```typescript
import { sendTelegram } from '../services/telegram.js';
```

- [ ] **Step 2: Run all tests to verify nothing broke**

Run: `cd ~/development/jimbo/jimbo-api && npx vitest run --reporter=verbose 2>&1 | tail -20`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
cd ~/development/jimbo/jimbo-api
git add src/routes/dispatch.ts
git commit -m "feat: add POST /notify-recon route for recon Telegram notifications"
```

---

### Task 9: Update existing proposeBatch to set flow field for vault tasks

**Files:**
- Modify: `~/development/jimbo/jimbo-api/src/services/dispatch.ts`
- Test: `~/development/jimbo/jimbo-api/test/dispatch.test.ts`

- [ ] **Step 1: Write the failing test**

Add to `~/development/jimbo/jimbo-api/test/dispatch.test.ts`, inside the `proposeBatch` describe:

```typescript
it('should set flow to commission for vault-sourced tasks by default', () => {
  seedReadyNote();
  const batch = proposeBatch({ batch_size: 1 });
  expect(batch.items[0].flow).toBe('commission');
});
```

- [ ] **Step 2: Run test to check if it passes already**

Run: `cd ~/development/jimbo/jimbo-api && npx vitest run test/dispatch.test.ts --reporter=verbose 2>&1 | tail -20`

The test should already pass because `flow` defaults to `'commission'` in the schema. This is a verification test confirming the default works correctly for the existing vault flow.

- [ ] **Step 3: Commit**

```bash
cd ~/development/jimbo/jimbo-api
git add test/dispatch.test.ts
git commit -m "test: verify vault-sourced dispatch tasks get flow=commission by default"
```

---

### Task 10: End-to-end verification — manual test

This task is manual. No code changes.

- [ ] **Step 1: Run the full test suite across both repos**

```bash
cd ~/development/jimbo/jimbo-api && npx vitest run --reporter=verbose
```

Expected: all tests pass.

- [ ] **Step 2: Verify the schema migration works on a fresh DB**

```bash
cd ~/development/jimbo/jimbo-api
rm -f test/tmp-dispatch/test.db
npx vitest run test/dispatch.test.ts --reporter=verbose
```

Expected: tests pass with a fresh database (migrations create all columns).

- [ ] **Step 3: List the changes for deployment**

jimbo-api changes to deploy to VPS:
```bash
cd ~/development/jimbo/jimbo-api && git log --oneline main..HEAD
```

openclaw changes to push via workspace-push.sh:
```bash
cd ~/development/openclaw && git log --oneline main..HEAD
```

- [ ] **Step 4: Document what's ready**

After this plan completes:
- `POST /api/dispatch/propose/github` is available — call it with `{ "repos": ["marvinbarretto/localshout-next"] }` to propose commissions from GitHub Issues
- The existing `POST /api/dispatch/propose` continues to work for vault tasks
- The M2 worker can distinguish commission vs recon via the `flow` field
- Commission PRs include `Closes owner/repo#N` for auto-close
- Recon tasks commit directly and send Telegram notifications
- The orchestrator on VPS needs updating to call `/propose/github` (separate task, outside this plan)
