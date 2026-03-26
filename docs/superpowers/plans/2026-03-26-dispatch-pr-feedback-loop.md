# Dispatch PR Feedback Loop — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the dispatch PR model so every agent type produces a PR and vault tasks auto-update when PRs are merged or closed.

**Architecture:** GitHub webhooks POST to jimbo-api, which matches PRs to dispatch tasks and updates vault state. Templates are refactored into agent-specific work instructions plus a shared output contract. Subtask rollup notifies via Telegram when all children complete. R2 stores visual evidence.

**Tech Stack:** jimbo-api (Hono, better-sqlite3, TypeScript), Vitest, Cloudflare R2 (S3-compatible API), GitHub Webhooks, Playwright (screenshots/video in agent templates)

**Repos involved:**
- `~/development/jimbo/jimbo-api` — API changes (schema, webhook route, services)
- `~/development/openclaw` — template refactoring, spec/plan docs
- `~/development/hub` — folder initialisation, CLAUDE.md update

---

## File Map

### jimbo-api — New Files
- `src/routes/webhooks.ts` — GitHub webhook route (HMAC validation, PR event handling)
- `src/services/telegram.ts` — shared Telegram notification helper (extracted from settings.ts pattern)
- `test/webhooks.test.ts` — webhook handler tests

### jimbo-api — Modified Files
- `src/db/index.ts` — add `pr_url`, `pr_state`, `rejection_reason` columns to dispatch_queue (~line 332)
- `src/types/dispatch.ts` — add PR fields to DispatchQueueItem, new webhook types
- `src/services/dispatch.ts` — extend completeTask to store pr_url, add lookupByPrUrl/lookupByBranch
- `src/services/vault.ts` — add checkSubtaskRollup method
- `src/index.ts` — mount webhook route before /api/* middleware
- `test/dispatch.test.ts` — add tests for pr_url storage and lookup

### openclaw — New Files
- `workspace/dispatch/templates/_output-contract.md` — shared PR/branching/evidence rules

### openclaw — Modified Files
- `workspace/dispatch/templates/coder.md` — extract shared rules to output contract, reference it
- `workspace/dispatch/templates/researcher.md` — rewrite with PR flow + hub target
- `workspace/dispatch/templates/drafter.md` — rewrite with PR flow + hub/site target

### hub — Modified Files
- `CLAUDE.md` — add dispatch context
- `docs/research/.gitkeep` — new directory
- `docs/drafts/.gitkeep` — new directory
- `docs/lists/.gitkeep` — new directory

---

## Task 1: Schema — Add PR columns to dispatch_queue

**Files:**
- Modify: `~/development/jimbo/jimbo-api/src/db/index.ts:332` (after dispatch_queue indexes)
- Modify: `~/development/jimbo/jimbo-api/src/types/dispatch.ts:12-31` (DispatchQueueItem interface)
- Test: `~/development/jimbo/jimbo-api/test/dispatch.test.ts`

- [ ] **Step 1: Add PR fields to DispatchQueueItem type**

In `src/types/dispatch.ts`, add three fields to the `DispatchQueueItem` interface after `error_message`:

```typescript
  pr_url: string | null;
  pr_state: string | null;        // 'open' | 'merged' | 'rejected'
  rejection_reason: string | null;
```

- [ ] **Step 2: Add migration for new columns**

In `src/db/index.ts`, after the dispatch_queue index creation block (~line 332), add:

```typescript
  // PR feedback loop columns (2026-03-26)
  const dispatchPrCols: [string, string][] = [
    ['pr_url', 'TEXT'],
    ['pr_state', 'TEXT'],
    ['rejection_reason', 'TEXT'],
  ];
  for (const [col, type] of dispatchPrCols) {
    try { db.exec(`ALTER TABLE dispatch_queue ADD COLUMN ${col} ${type}`); } catch {}
  }
  try { db.exec('CREATE INDEX IF NOT EXISTS idx_dispatch_pr_url ON dispatch_queue(pr_url)'); } catch {}
```

- [ ] **Step 3: Run existing tests to confirm no regressions**

Run: `cd ~/development/jimbo/jimbo-api && npx vitest run test/dispatch.test.ts`
Expected: All existing tests pass (new nullable columns don't break anything)

- [ ] **Step 4: Commit**

```bash
cd ~/development/jimbo/jimbo-api
git add src/db/index.ts src/types/dispatch.ts
git commit -m "feat: add pr_url, pr_state, rejection_reason columns to dispatch_queue"
```

---

## Task 2: Extend completeTask to store pr_url

**Files:**
- Modify: `~/development/jimbo/jimbo-api/src/types/dispatch.ts:48-52` (DispatchCompleteParams)
- Modify: `~/development/jimbo/jimbo-api/src/services/dispatch.ts:134-145` (completeTask)
- Test: `~/development/jimbo/jimbo-api/test/dispatch.test.ts`

- [ ] **Step 1: Write failing test for pr_url storage**

In `test/dispatch.test.ts`, add a new test after the existing completeTask tests:

```typescript
test('completeTask stores pr_url when provided', () => {
  // Setup: create a proposed + approved + started task
  const db = getDb();
  db.prepare(`INSERT INTO vault_notes (id, title, status, type, dispatch_status, agent_type, acceptance_criteria, route, ai_priority, actionability)
    VALUES ('pr-test', 'PR test task', 'active', 'task', 'ready', 'coder', 'Tests pass', 'jimbo', 7, 'clear')`).run();

  const batch = proposeBatch({ batch_size: 1 });
  approveBatch({ batch_id: batch.batch_id, token: batch.token });
  const next = getNextApproved();
  startTask(next!.id);

  const result = completeTask({
    id: next!.id,
    result_summary: 'Fixed the thing',
    pr_url: 'https://github.com/marvinbarretto-labs/localshout-next/pull/200',
  });

  expect(result?.pr_url).toBe('https://github.com/marvinbarretto-labs/localshout-next/pull/200');
  expect(result?.pr_state).toBe('open');
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/development/jimbo/jimbo-api && npx vitest run test/dispatch.test.ts -t "stores pr_url"`
Expected: FAIL — `pr_url` not in DispatchCompleteParams, completeTask doesn't handle it

- [ ] **Step 3: Add pr_url to DispatchCompleteParams**

In `src/types/dispatch.ts`, update the interface:

```typescript
export interface DispatchCompleteParams {
  id: number;
  result_summary: string;
  result_artifacts?: string;
  pr_url?: string;
}
```

- [ ] **Step 4: Update completeTask to store pr_url and set pr_state**

In `src/services/dispatch.ts`, replace the completeTask function:

```typescript
export function completeTask(params: DispatchCompleteParams): DispatchQueueItem | null {
  const db = getDb();
  db.prepare(
    `UPDATE dispatch_queue SET status = 'completed', result_summary = ?, result_artifacts = ?, pr_url = ?, pr_state = ?, completed_at = ? WHERE id = ?`
  ).run(
    params.result_summary,
    params.result_artifacts ?? null,
    params.pr_url ?? null,
    params.pr_url ? 'open' : null,
    now(),
    params.id
  );

  const item = db.prepare('SELECT * FROM dispatch_queue WHERE id = ?').get(params.id) as DispatchQueueItem;
  if (item?.task_source === 'vault') {
    db.prepare(`UPDATE vault_notes SET status = 'done', dispatch_status = 'done', completed_at = datetime('now'), updated_at = datetime('now') WHERE id = ?`)
      .run(item.task_id);
  }
  return item;
}
```

- [ ] **Step 5: Update /complete route to pass pr_url**

In `src/routes/dispatch.ts`, update the `/complete` handler to include `pr_url`:

```typescript
dispatch.post('/complete', async (c) => {
  const body = await c.req.json<{ id: number; result_summary: string; result_artifacts?: string; pr_url?: string }>();
  if (!body.id || !body.result_summary) {
    return c.json({ error: 'id and result_summary required' }, 400);
  }
  const result = completeTask(body);
  if (!result) return c.json({ error: 'Task not found' }, 404);
  return c.json(result);
});
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd ~/development/jimbo/jimbo-api && npx vitest run test/dispatch.test.ts -t "stores pr_url"`
Expected: PASS

- [ ] **Step 7: Run full test suite**

Run: `cd ~/development/jimbo/jimbo-api && npx vitest run`
Expected: All tests pass

- [ ] **Step 8: Commit**

```bash
cd ~/development/jimbo/jimbo-api
git add src/types/dispatch.ts src/services/dispatch.ts src/routes/dispatch.ts test/dispatch.test.ts
git commit -m "feat: store pr_url on dispatch task completion"
```

---

## Task 3: PR lookup functions

**Files:**
- Modify: `~/development/jimbo/jimbo-api/src/services/dispatch.ts`
- Test: `~/development/jimbo/jimbo-api/test/dispatch.test.ts`

- [ ] **Step 1: Write failing tests for lookup functions**

In `test/dispatch.test.ts`:

```typescript
test('lookupByPrUrl finds dispatch task by PR URL', () => {
  // Reuse a completed task with pr_url from previous test setup
  const db = getDb();
  db.prepare(`INSERT INTO dispatch_queue (task_id, task_source, agent_type, status, pr_url, pr_state)
    VALUES ('lookup-1', 'vault', 'coder', 'completed', 'https://github.com/org/repo/pull/99', 'open')`).run();

  const result = lookupByPrUrl('https://github.com/org/repo/pull/99');
  expect(result).not.toBeNull();
  expect(result?.task_id).toBe('lookup-1');
});

test('lookupByBranch finds dispatch task by branch name', () => {
  const db = getDb();
  db.prepare(`INSERT INTO dispatch_queue (task_id, task_source, agent_type, status, pr_url, pr_state)
    VALUES ('lookup-branch-1', 'vault', 'coder', 'completed', 'https://github.com/org/repo/pull/100', 'open')`).run();

  const result = lookupByBranch('dispatch/lookup-branch-1');
  expect(result).not.toBeNull();
  expect(result?.task_id).toBe('lookup-branch-1');
});

test('lookupByBranch returns null for non-dispatch branch', () => {
  const result = lookupByBranch('feature/something');
  expect(result).toBeNull();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/development/jimbo/jimbo-api && npx vitest run test/dispatch.test.ts -t "lookup"`
Expected: FAIL — functions not defined

- [ ] **Step 3: Implement lookup functions**

In `src/services/dispatch.ts`, add:

```typescript
export function lookupByPrUrl(prUrl: string): DispatchQueueItem | null {
  const db = getDb();
  return db.prepare('SELECT * FROM dispatch_queue WHERE pr_url = ? ORDER BY id DESC LIMIT 1').get(prUrl) as DispatchQueueItem | null;
}

export function lookupByBranch(branchName: string): DispatchQueueItem | null {
  const match = branchName.match(/^dispatch\/(.+)$/);
  if (!match) return null;
  const taskId = match[1];
  const db = getDb();
  return db.prepare(
    `SELECT * FROM dispatch_queue WHERE task_id = ? AND status IN ('completed', 'running') ORDER BY id DESC LIMIT 1`
  ).get(taskId) as DispatchQueueItem | null;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/development/jimbo/jimbo-api && npx vitest run test/dispatch.test.ts -t "lookup"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd ~/development/jimbo/jimbo-api
git add src/services/dispatch.ts test/dispatch.test.ts
git commit -m "feat: add PR URL and branch-based dispatch task lookup"
```

---

## Task 4: Shared Telegram notification helper

**Files:**
- Create: `~/development/jimbo/jimbo-api/src/services/telegram.ts`
- Test: `~/development/jimbo/jimbo-api/test/telegram.test.ts`

- [ ] **Step 1: Write test for sendTelegram**

Create `test/telegram.test.ts`:

```typescript
import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest';
import { sendTelegram } from '../src/services/telegram.js';

describe('sendTelegram', () => {
  const originalEnv = process.env;

  beforeEach(() => {
    process.env = { ...originalEnv, TELEGRAM_BOT_TOKEN: 'test-token', TELEGRAM_CHAT_ID: '12345' };
  });

  afterEach(() => {
    process.env = originalEnv;
    vi.restoreAllMocks();
  });

  test('sends message when env vars are set', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValue(new Response('ok'));

    await sendTelegram('Test message');

    expect(fetchSpy).toHaveBeenCalledOnce();
    const [url, opts] = fetchSpy.mock.calls[0];
    expect(url).toBe('https://api.telegram.org/bottest-token/sendMessage');
    const body = JSON.parse(opts!.body as string);
    expect(body.chat_id).toBe('12345');
    expect(body.text).toBe('Test message');
  });

  test('does nothing when env vars are missing', async () => {
    delete process.env.TELEGRAM_BOT_TOKEN;
    const fetchSpy = vi.spyOn(global, 'fetch');

    await sendTelegram('Test message');

    expect(fetchSpy).not.toHaveBeenCalled();
  });

  test('does not throw on fetch failure', async () => {
    vi.spyOn(global, 'fetch').mockRejectedValue(new Error('network'));

    await expect(sendTelegram('Test message')).resolves.toBeUndefined();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/development/jimbo/jimbo-api && npx vitest run test/telegram.test.ts`
Expected: FAIL — module not found

- [ ] **Step 3: Implement sendTelegram**

Create `src/services/telegram.ts`:

```typescript
export async function sendTelegram(message: string, parseMode?: 'HTML' | 'Markdown'): Promise<void> {
  const token = process.env.TELEGRAM_BOT_TOKEN;
  const chatId = process.env.TELEGRAM_CHAT_ID;
  if (!token || !chatId) return;

  const url = `https://api.telegram.org/bot${token}/sendMessage`;
  const body: Record<string, string> = { chat_id: chatId, text: message };
  if (parseMode) body.parse_mode = parseMode;

  try {
    await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  } catch {
    // Non-critical — don't crash the caller
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/development/jimbo/jimbo-api && npx vitest run test/telegram.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd ~/development/jimbo/jimbo-api
git add src/services/telegram.ts test/telegram.test.ts
git commit -m "feat: extract shared Telegram notification helper"
```

---

## Task 5: Subtask rollup check

**Files:**
- Modify: `~/development/jimbo/jimbo-api/src/services/vault.ts:321-326` (near getSubtasks)
- Test: `~/development/jimbo/jimbo-api/test/vault-rollup.test.ts`

- [ ] **Step 1: Write failing test for checkSubtaskRollup**

Create `test/vault-rollup.test.ts`:

```typescript
import { describe, test, expect, beforeAll } from 'vitest';
import { getDb } from '../src/db/index.js';
import { checkSubtaskRollup } from '../src/services/vault.js';

const TEST_DB = '/tmp/test-vault-rollup.db';

beforeAll(() => {
  process.env.CONTEXT_DB_PATH = TEST_DB;
  try { require('fs').unlinkSync(TEST_DB); } catch {}
  getDb(); // init schema
});

describe('checkSubtaskRollup', () => {
  test('returns allDone=true when all children are done', () => {
    const db = getDb();
    db.prepare(`INSERT INTO vault_notes (id, title, status, type) VALUES ('parent-1', 'Parent task', 'active', 'task')`).run();
    db.prepare(`INSERT INTO vault_notes (id, title, status, type, parent_id) VALUES ('child-1', 'Child 1', 'done', 'task', 'parent-1')`).run();
    db.prepare(`INSERT INTO vault_notes (id, title, status, type, parent_id) VALUES ('child-2', 'Child 2', 'done', 'task', 'parent-1')`).run();

    const result = checkSubtaskRollup('parent-1');
    expect(result.allDone).toBe(true);
    expect(result.children).toHaveLength(2);
    expect(result.parent?.id).toBe('parent-1');
  });

  test('returns allDone=false when some children are not done', () => {
    const db = getDb();
    db.prepare(`INSERT INTO vault_notes (id, title, status, type) VALUES ('parent-2', 'Parent task 2', 'active', 'task')`).run();
    db.prepare(`INSERT INTO vault_notes (id, title, status, type, parent_id) VALUES ('child-3', 'Child 3', 'done', 'task', 'parent-2')`).run();
    db.prepare(`INSERT INTO vault_notes (id, title, status, type, parent_id) VALUES ('child-4', 'Child 4', 'active', 'task', 'parent-2')`).run();

    const result = checkSubtaskRollup('parent-2');
    expect(result.allDone).toBe(false);
  });

  test('returns null parent when parent_id does not exist', () => {
    const result = checkSubtaskRollup('nonexistent');
    expect(result.parent).toBeNull();
    expect(result.children).toHaveLength(0);
    expect(result.allDone).toBe(false);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/development/jimbo/jimbo-api && npx vitest run test/vault-rollup.test.ts`
Expected: FAIL — checkSubtaskRollup not exported

- [ ] **Step 3: Implement checkSubtaskRollup**

In `src/services/vault.ts`, after the existing `getSubtasks` function (~line 326), add:

```typescript
export interface SubtaskRollupResult {
  allDone: boolean;
  children: VaultNoteSummary[];
  parent: VaultNoteSummary | null;
}

export function checkSubtaskRollup(parentId: string): SubtaskRollupResult {
  const db = getDb();
  const parent = db.prepare(`SELECT ${SUMMARY_COLUMNS} FROM vault_notes WHERE id = ?`).get(parentId) as VaultNoteSummary | undefined;
  if (!parent) {
    return { allDone: false, children: [], parent: null };
  }

  const children = getSubtasks(parentId);
  if (children.length === 0) {
    return { allDone: false, children: [], parent };
  }

  const allDone = children.every(c => c.status === 'done');
  return { allDone, children, parent };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/development/jimbo/jimbo-api && npx vitest run test/vault-rollup.test.ts`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `cd ~/development/jimbo/jimbo-api && npx vitest run`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
cd ~/development/jimbo/jimbo-api
git add src/services/vault.ts test/vault-rollup.test.ts
git commit -m "feat: add subtask rollup check for parent task notification"
```

---

## Task 6: GitHub webhook route

**Files:**
- Create: `~/development/jimbo/jimbo-api/src/routes/webhooks.ts`
- Modify: `~/development/jimbo/jimbo-api/src/index.ts:25` (mount before /api/* middleware)
- Test: `~/development/jimbo/jimbo-api/test/webhooks.test.ts`

- [ ] **Step 1: Write failing tests for webhook handler**

Create `test/webhooks.test.ts`:

```typescript
import { describe, test, expect, beforeAll, vi, afterEach } from 'vitest';
import { Hono } from 'hono';
import crypto from 'node:crypto';
import { getDb } from '../src/db/index.js';
import webhooks from '../src/routes/webhooks.js';

const TEST_DB = '/tmp/test-webhooks.db';
const WEBHOOK_SECRET = 'test-webhook-secret';

function sign(body: string): string {
  const hmac = crypto.createHmac('sha256', WEBHOOK_SECRET);
  hmac.update(body);
  return 'sha256=' + hmac.digest('hex');
}

function makePrPayload(action: string, prUrl: string, branch: string, merged = false) {
  return {
    action,
    pull_request: {
      html_url: prUrl,
      merged,
      head: { ref: branch },
      number: 42,
      base: { repo: { full_name: 'marvinbarretto-labs/localshout-next' } },
    },
  };
}

let app: Hono;

beforeAll(() => {
  process.env.CONTEXT_DB_PATH = TEST_DB;
  process.env.GITHUB_WEBHOOK_SECRET = WEBHOOK_SECRET;
  try { require('fs').unlinkSync(TEST_DB); } catch {}
  getDb();
  app = new Hono();
  app.route('/webhooks', webhooks);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('GitHub webhook', () => {
  test('rejects request with invalid signature', async () => {
    const body = JSON.stringify(makePrPayload('opened', 'https://github.com/org/repo/pull/1', 'dispatch/test-1'));
    const res = await app.request('/webhooks/github', {
      method: 'POST',
      body,
      headers: {
        'Content-Type': 'application/json',
        'X-Hub-Signature-256': 'sha256=invalid',
        'X-GitHub-Event': 'pull_request',
      },
    });
    expect(res.status).toBe(401);
  });

  test('ignores non-pull_request events', async () => {
    const body = JSON.stringify({ action: 'created' });
    const res = await app.request('/webhooks/github', {
      method: 'POST',
      body,
      headers: {
        'Content-Type': 'application/json',
        'X-Hub-Signature-256': sign(body),
        'X-GitHub-Event': 'push',
      },
    });
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json.ignored).toBe(true);
  });

  test('updates pr_state to merged on merge event', async () => {
    const db = getDb();
    db.prepare(`INSERT INTO vault_notes (id, title, status, type, dispatch_status) VALUES ('wh-merge', 'Webhook merge test', 'active', 'task', 'running')`).run();
    db.prepare(`INSERT INTO dispatch_queue (task_id, task_source, agent_type, status, pr_url, pr_state) VALUES ('wh-merge', 'vault', 'coder', 'completed', 'https://github.com/org/repo/pull/42', 'open')`).run();

    const payload = makePrPayload('closed', 'https://github.com/org/repo/pull/42', 'dispatch/wh-merge', true);
    const body = JSON.stringify(payload);

    const res = await app.request('/webhooks/github', {
      method: 'POST',
      body,
      headers: {
        'Content-Type': 'application/json',
        'X-Hub-Signature-256': sign(body),
        'X-GitHub-Event': 'pull_request',
      },
    });
    expect(res.status).toBe(200);

    const item = db.prepare('SELECT * FROM dispatch_queue WHERE task_id = ?').get('wh-merge') as any;
    expect(item.pr_state).toBe('merged');

    const note = db.prepare('SELECT * FROM vault_notes WHERE id = ?').get('wh-merge') as any;
    expect(note.status).toBe('done');
    expect(note.dispatch_status).toBe('done');
  });

  test('updates pr_state to rejected on close without merge', async () => {
    const db = getDb();
    db.prepare(`INSERT INTO vault_notes (id, title, status, type, dispatch_status) VALUES ('wh-reject', 'Webhook reject test', 'active', 'task', 'running')`).run();
    db.prepare(`INSERT INTO dispatch_queue (task_id, task_source, agent_type, status, pr_url, pr_state) VALUES ('wh-reject', 'vault', 'coder', 'completed', 'https://github.com/org/repo/pull/43', 'open')`).run();

    const payload = makePrPayload('closed', 'https://github.com/org/repo/pull/43', 'dispatch/wh-reject', false);
    const body = JSON.stringify(payload);

    const res = await app.request('/webhooks/github', {
      method: 'POST',
      body,
      headers: {
        'Content-Type': 'application/json',
        'X-Hub-Signature-256': sign(body),
        'X-GitHub-Event': 'pull_request',
      },
    });
    expect(res.status).toBe(200);

    const item = db.prepare('SELECT * FROM dispatch_queue WHERE task_id = ?').get('wh-reject') as any;
    expect(item.pr_state).toBe('rejected');

    const note = db.prepare('SELECT * FROM vault_notes WHERE id = ?').get('wh-reject') as any;
    expect(note.status).toBe('active');
    expect(note.dispatch_status).toBe('needs_grooming');
  });

  test('matches by branch name when pr_url not found', async () => {
    const db = getDb();
    db.prepare(`INSERT INTO vault_notes (id, title, status, type, dispatch_status) VALUES ('wh-branch', 'Branch match test', 'active', 'task', 'running')`).run();
    db.prepare(`INSERT INTO dispatch_queue (task_id, task_source, agent_type, status, pr_state) VALUES ('wh-branch', 'vault', 'coder', 'completed', 'open')`).run();

    const payload = makePrPayload('closed', 'https://github.com/org/repo/pull/99', 'dispatch/wh-branch', true);
    const body = JSON.stringify(payload);

    const res = await app.request('/webhooks/github', {
      method: 'POST',
      body,
      headers: {
        'Content-Type': 'application/json',
        'X-Hub-Signature-256': sign(body),
        'X-GitHub-Event': 'pull_request',
      },
    });
    expect(res.status).toBe(200);

    const item = db.prepare('SELECT * FROM dispatch_queue WHERE task_id = ?').get('wh-branch') as any;
    expect(item.pr_state).toBe('merged');
    expect(item.pr_url).toBe('https://github.com/org/repo/pull/99');
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/development/jimbo/jimbo-api && npx vitest run test/webhooks.test.ts`
Expected: FAIL — module not found

- [ ] **Step 3: Implement webhook route**

Create `src/routes/webhooks.ts`:

```typescript
import { Hono } from 'hono';
import crypto from 'node:crypto';
import { getDb } from '../db/index.js';
import { lookupByPrUrl, lookupByBranch } from '../services/dispatch.js';
import { checkSubtaskRollup } from '../services/vault.js';
import { sendTelegram } from '../services/telegram.js';
import type { DispatchQueueItem } from '../types/dispatch.js';

const webhooks = new Hono();

function verifySignature(body: string, signature: string | undefined): boolean {
  const secret = process.env.GITHUB_WEBHOOK_SECRET;
  if (!secret || !signature) return false;
  const hmac = crypto.createHmac('sha256', secret);
  hmac.update(body);
  const expected = 'sha256=' + hmac.digest('hex');
  return crypto.timingSafeEqual(Buffer.from(expected), Buffer.from(signature));
}

webhooks.post('/github', async (c) => {
  const body = await c.req.text();
  const signature = c.req.header('X-Hub-Signature-256');
  const event = c.req.header('X-GitHub-Event');

  if (!verifySignature(body, signature)) {
    return c.json({ error: 'Invalid signature' }, 401);
  }

  if (event !== 'pull_request') {
    return c.json({ ignored: true, reason: `Event type: ${event}` });
  }

  const payload = JSON.parse(body);
  const { action, pull_request: pr } = payload;
  const prUrl = pr.html_url;
  const branch = pr.head.ref;
  const merged = pr.merged;
  const repoFullName = pr.base.repo.full_name;
  const prNumber = pr.number;

  // Find the dispatch task — pr_url first, branch fallback
  let item = lookupByPrUrl(prUrl);
  if (!item) item = lookupByBranch(branch);
  if (!item) {
    return c.json({ ignored: true, reason: 'No matching dispatch task' });
  }

  const db = getDb();

  if (action === 'opened' || action === 'reopened') {
    db.prepare('UPDATE dispatch_queue SET pr_url = ?, pr_state = ? WHERE id = ?')
      .run(prUrl, 'open', item.id);

    if (action === 'reopened' && item.task_source === 'vault') {
      db.prepare(`UPDATE vault_notes SET status = 'active', dispatch_status = 'running', updated_at = datetime('now') WHERE id = ?`)
        .run(item.task_id);
    }
    return c.json({ handled: true, action, task_id: item.task_id });
  }

  if (action === 'closed' && merged) {
    db.prepare('UPDATE dispatch_queue SET pr_state = ? WHERE id = ?')
      .run('merged', item.id);

    if (item.task_source === 'vault') {
      db.prepare(`UPDATE vault_notes SET status = 'done', dispatch_status = 'done', completed_at = datetime('now'), updated_at = datetime('now') WHERE id = ?`)
        .run(item.task_id);

      // Subtask rollup check
      const note = db.prepare('SELECT parent_id FROM vault_notes WHERE id = ?').get(item.task_id) as { parent_id: string | null } | undefined;
      if (note?.parent_id) {
        const rollup = checkSubtaskRollup(note.parent_id);
        if (rollup.allDone && rollup.parent) {
          const childList = rollup.children.map(c => `• ${c.title} — PR merged ✓`).join('\n');
          await sendTelegram(
            `✅ All subtasks complete for: ${rollup.parent.title}\n\n${childList}\n\nReady to close the parent? Mark done in vault or reply here.`
          );
        }
      }
    }
    return c.json({ handled: true, action: 'merged', task_id: item.task_id });
  }

  if (action === 'closed' && !merged) {
    // Fetch rejection reason from last PR comment
    let rejectionReason: string | null = null;
    try {
      const ghToken = process.env.GITHUB_TOKEN;
      if (ghToken) {
        const commentsUrl = `https://api.github.com/repos/${repoFullName}/issues/${prNumber}/comments?per_page=1&sort=created&direction=desc`;
        const res = await fetch(commentsUrl, {
          headers: { Authorization: `Bearer ${ghToken}`, Accept: 'application/vnd.github+json' },
        });
        if (res.ok) {
          const comments = await res.json() as Array<{ body: string }>;
          if (comments.length > 0) {
            rejectionReason = comments[0].body;
          }
        }
      }
    } catch {
      // Non-critical — proceed without rejection reason
    }

    db.prepare('UPDATE dispatch_queue SET pr_state = ?, rejection_reason = ? WHERE id = ?')
      .run('rejected', rejectionReason, item.id);

    if (item.task_source === 'vault') {
      db.prepare(`UPDATE vault_notes SET status = 'active', dispatch_status = 'needs_grooming', updated_at = datetime('now') WHERE id = ?`)
        .run(item.task_id);
    }
    return c.json({ handled: true, action: 'rejected', task_id: item.task_id, has_reason: !!rejectionReason });
  }

  return c.json({ ignored: true, reason: `Unhandled action: ${action}` });
});

export default webhooks;
```

- [ ] **Step 4: Mount webhook route in index.ts**

In `src/index.ts`, add the import after the existing imports (~line 17):

```typescript
import webhooks from './routes/webhooks.js';
```

Mount it **before** the `/api/*` middleware block (~line 27, before the public dispatch approval endpoints):

```typescript
// GitHub webhook endpoint (no API key — uses HMAC signature validation)
app.route('/webhooks', webhooks);
```

- [ ] **Step 5: Run webhook tests**

Run: `cd ~/development/jimbo/jimbo-api && npx vitest run test/webhooks.test.ts`
Expected: All PASS

- [ ] **Step 6: Run full test suite**

Run: `cd ~/development/jimbo/jimbo-api && npx vitest run`
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
cd ~/development/jimbo/jimbo-api
git add src/routes/webhooks.ts src/index.ts test/webhooks.test.ts
git commit -m "feat: add GitHub webhook handler for PR feedback loop"
```

---

## Task 7: Centralised output contract template

**Files:**
- Create: `~/development/openclaw/workspace/dispatch/templates/_output-contract.md`
- Modify: `~/development/openclaw/workspace/dispatch/templates/coder.md`

- [ ] **Step 1: Create the output contract**

Create `workspace/dispatch/templates/_output-contract.md`:

```markdown
# Dispatch Output Contract

Every dispatch task, regardless of agent type, MUST follow this contract. Your agent-specific template tells you HOW to do the work. This contract tells you how to DELIVER it.

## Branching

- Branch name: `dispatch/{task_id}`
- Branch from `main` (or the repo's default branch)
- Use conventional commits: `type: description` — lowercase, imperative, ~70 chars

## Push and Open a PR — THIS IS MANDATORY

After completing your work:

1. `git push origin dispatch/{task_id}`
2. Open a PR using `gh pr create` following this format:

### PR Title
Use the task title or `type: [Scope] description`

### PR Body

```
## Summary
One paragraph: what you changed and why.

## Changes
- `path/to/file.ext` — what changed and why
- `path/to/other.ext` — what changed and why

## Definition of Done Checklist
For each criterion in the acceptance criteria:
- [x] Criterion — evidence (test output, screenshot URL, manual verification)

## Screenshots
Before: {R2_URL or "N/A — no visual changes"}
After: {R2_URL or "N/A — no visual changes"}
Video: {R2_URL or "N/A — no interactive changes"}

## Testing
What you ran and the results.

---
Dispatched by Jimbo · Task #{seq} · Agent: {agent_type}
```

## Visual Evidence (when applicable)

If your changes affect UI:

1. Checkout `main`, start dev server, capture screenshots of affected pages using Playwright
2. Checkout your feature branch, start dev server, capture the same pages
3. For interactive changes (keyboard, hover, animation): use Playwright `recordVideo` to capture a `.webm`
4. Upload to R2:
   - `curl -X PUT "https://${R2_DISPATCH_PUBLIC_URL}/{task_id}/before.png" --upload-file before.png`
   - Same for `after.png` and `demo.webm`
5. Embed the public URLs in the PR body under Screenshots

If your changes are NOT visual (backend, research, drafts): write "N/A — no visual changes" in the Screenshots section.

**Fallback:** If R2 upload fails, commit screenshots to `.dispatch/screenshots/` on the branch and note the fallback in the PR body.

## Result JSON

Write your result to `/tmp/dispatch-{task_id}.result` as JSON:

### On completion (PR opened successfully):
```json
{
  "status": "completed",
  "summary": "One-line description of what was done",
  "pr_url": "https://github.com/owner/repo/pull/N",
  "branch": "dispatch/{task_id}",
  "files_changed": ["path/to/file.ext"],
  "screenshots": {
    "before": "https://r2-url/before.png",
    "after": "https://r2-url/after.png",
    "video": "https://r2-url/demo.webm"
  }
}
```

`pr_url` is REQUIRED for completed status. If you cannot open a PR, use the blocked status instead.

### On blocked (cannot complete):
```json
{
  "status": "blocked",
  "summary": "What prevented completion",
  "branch": "dispatch/{task_id}",
  "blockers": ["Specific reason 1", "Specific reason 2"],
  "files_changed": ["any files touched before blocking"]
}
```

## Rules

- NEVER ask for user input — you are autonomous
- If a tool is blocked, find an alternative
- If you cannot complete the work, use the blocked status — do not leave work half-done without reporting
- One task at a time, one branch, one PR
```

- [ ] **Step 2: Refactor coder.md to reference the output contract**

Remove the PR format section, push instructions, and result JSON format from `coder.md`. Replace with a reference:

Keep the coder-specific work instructions (steps 1-6: understand, branch, capture before, implement, test, capture after). Remove steps 7-8 (R2 upload, push + PR) and the result JSON format — these are now in `_output-contract.md`.

Add at the end of the coder-specific instructions:

```markdown
---

**Output:** Follow the dispatch output contract (`_output-contract.md`) for branching, pushing, PR format, evidence upload, and result JSON.
```

- [ ] **Step 3: Commit**

```bash
cd ~/development/openclaw
git add workspace/dispatch/templates/_output-contract.md workspace/dispatch/templates/coder.md
git commit -m "feat: extract shared dispatch output contract from coder template"
```

---

## Task 8: Rewrite researcher and drafter templates

**Files:**
- Modify: `~/development/openclaw/workspace/dispatch/templates/researcher.md`
- Modify: `~/development/openclaw/workspace/dispatch/templates/drafter.md`

- [ ] **Step 1: Rewrite researcher.md**

Replace the current content of `workspace/dispatch/templates/researcher.md`:

```markdown
# Dispatch Agent: Researcher

You are a research agent. Your task is to investigate a topic thoroughly and produce a structured research document.

## Task
**Title:** {title}
**Acceptance Criteria:** {definition_of_done}
**Task ID:** {task_id}

## Target
- **Repo:** {dispatch_repo} (default: hub)
- **Output path:** docs/research/{task_id}.md

## Instructions

1. **Understand the question.** Read the title and acceptance criteria carefully. What does Marvin actually need to know? What decision is this research informing?

2. **Clone the repo and branch.** Clone {dispatch_repo}, create branch `dispatch/{task_id}`.

3. **Research.** Use web search, documentation, and any available tools to gather information. Look for:
   - Primary sources (official docs, published benchmarks, pricing pages)
   - Multiple perspectives (not just the first result)
   - Concrete data (numbers, dates, pricing, limits)

4. **Write the research document.** Create `docs/research/{task_id}.md` with this structure:
   - **Summary** — 2-3 sentence answer to the core question
   - **Findings** — organised by sub-topic, with evidence and sources
   - **Comparison** (if applicable) — table or structured comparison
   - **Recommendation** — what Marvin should do, with reasoning
   - **Sources** — numbered list of URLs with brief descriptions

5. **Quality check.** Every claim must have a source. No filler. No hedging. Be direct and opinionated — Marvin wants a recommendation, not a balanced essay.

---

**Output:** Follow the dispatch output contract (`_output-contract.md`) for branching, pushing, PR format, evidence upload, and result JSON.
```

- [ ] **Step 2: Rewrite drafter.md**

Replace the current content of `workspace/dispatch/templates/drafter.md`:

```markdown
# Dispatch Agent: Drafter

You are a writing agent. Your task is to produce a draft document matching Marvin's voice and style.

## Task
**Title:** {title}
**Acceptance Criteria:** {definition_of_done}
**Task ID:** {task_id}

## Target
- **Repo:** {dispatch_repo} (default: hub)
- **Output path:** {output_path} (default: docs/drafts/{task_id}.md)

## Instructions

1. **Understand the brief.** Read the title and acceptance criteria. What is this piece for? Who reads it? What tone?

2. **Clone the repo and branch.** Clone {dispatch_repo}, create branch `dispatch/{task_id}`.

3. **Research.** Gather context for the topic. Read relevant existing content in the repo to match style. If writing for the blog (`site` repo), read 2-3 existing posts in `src/content/posts/` for tone calibration.

4. **Write the draft.** Save to {output_path}. Writing rules:
   - **Voice:** Marvin's — opinionated, direct, occasionally funny. No corporate speak.
   - **Structure:** Clear sections, short paragraphs. Get to the point fast.
   - **No filler:** Every sentence earns its place. Cut "In this article, we will explore..."
   - **Markdown frontmatter:** Include title, date, tags if the output is a blog post

5. **Self-edit.** Read it back. Cut 10%. Check that it sounds like a person wrote it, not an AI.

---

**Output:** Follow the dispatch output contract (`_output-contract.md`) for branching, pushing, PR format, evidence upload, and result JSON.
```

- [ ] **Step 3: Commit**

```bash
cd ~/development/openclaw
git add workspace/dispatch/templates/researcher.md workspace/dispatch/templates/drafter.md
git commit -m "feat: rewrite researcher and drafter templates with PR flow"
```

---

## Task 9: Hub repo initialisation

**Files:**
- Modify: `~/development/hub/CLAUDE.md`
- Create: `~/development/hub/docs/research/.gitkeep`
- Create: `~/development/hub/docs/drafts/.gitkeep`
- Create: `~/development/hub/docs/lists/.gitkeep`

- [ ] **Step 1: Create directory structure**

```bash
cd ~/development/hub
mkdir -p docs/research docs/drafts docs/lists
touch docs/research/.gitkeep docs/drafts/.gitkeep docs/lists/.gitkeep
```

- [ ] **Step 2: Update CLAUDE.md**

Replace the content of `~/development/hub/CLAUDE.md`:

```markdown
# Hub

Personal infrastructure repo — system control, automation, dashboards, operational docs, and dispatch outputs spanning all projects.

## Structure
- `docs/specs/` — design specs and architecture decisions
- `docs/plans/` — implementation plans
- `docs/research/` — research outputs from dispatch (comparisons, analysis, investigations)
- `docs/drafts/` — content drafts from dispatch (blog posts, documentation, writeups)
- `docs/lists/` — curated URL lists, tool comparisons, reference material
- `scripts/` — setup and automation scripts (Tailscale, ADB, cron)
- `dashboards/` — Jimbo dashboard pages, status displays

## Dispatch Target

This repo receives non-code dispatch outputs. When an agent lands here via a dispatch task:

- **Researchers** write to `docs/research/{task-id}.md`
- **Drafters** write to `docs/drafts/{task-id}.md` (or `docs/lists/` for curated lists)
- All work arrives as PRs from `dispatch/{task_id}` branches
- Follow the dispatch output contract for PR format, branching, and result JSON

## Conventions
- Follow root `~/development/CLAUDE.md` conventions
- Scripts default to dry-run; `--live` flag for writes
```

- [ ] **Step 3: Commit**

```bash
cd ~/development/hub
git add docs/research/.gitkeep docs/drafts/.gitkeep docs/lists/.gitkeep CLAUDE.md
git commit -m "feat: initialise hub dispatch folders and update CLAUDE.md"
```

---

## Task 10: Rejection feedback in dispatch worker prompt

**Files:**
- Modify: `~/development/openclaw/workspace/dispatch/dispatch-check.md`

- [ ] **Step 1: Update dispatch-check.md with rejection feedback instructions**

Add a new section to `workspace/dispatch/dispatch-check.md` after the template loading instructions:

```markdown
### Rejection Feedback Injection

Before rendering the final prompt for a task, check if the task has been previously rejected:

1. Query dispatch history: `GET /api/dispatch/queue?task_id={task_id}&status=rejected`
2. If results exist, take the most recent item's `rejection_reason`
3. If `rejection_reason` is not null, inject this block between the agent template and the output contract:

```
---
PREVIOUS ATTEMPT FEEDBACK

This task was attempted before and the PR was rejected.
Reviewer feedback: {rejection_reason}

Learn from this feedback and adjust your approach accordingly.
---
```

This ensures agents learn from previous failures without Marvin needing to re-explain the problem.
```

- [ ] **Step 2: Commit**

```bash
cd ~/development/openclaw
git add workspace/dispatch/dispatch-check.md
git commit -m "feat: add rejection feedback injection to dispatch worker guide"
```

---

## Task 11: R2 bucket setup and env var documentation

**Files:**
- Modify: `~/development/openclaw/CLAUDE.md` (add R2 env vars to sandbox section)
- Modify: `~/development/openclaw/CAPABILITIES.md` (if it exists, document R2 bucket)

- [ ] **Step 1: Document R2 credentials for M2 dispatch**

In `~/development/openclaw/CLAUDE.md`, add to the "Sandbox API keys" section (or create a new "M2 Dispatch Env Vars" section nearby):

```markdown
### M2 Dispatch Env Vars

The M2 dispatch worker needs these env vars for visual evidence upload:
- `R2_DISPATCH_ACCOUNT_ID` — Cloudflare account ID
- `R2_DISPATCH_ACCESS_KEY_ID` — R2 API token key ID
- `R2_DISPATCH_SECRET_ACCESS_KEY` — R2 API token secret
- `R2_DISPATCH_BUCKET_NAME` — Bucket name (e.g. `dispatch-evidence`)
- `R2_DISPATCH_PUBLIC_URL` — Public URL prefix for the bucket

The jimbo-api (VPS) needs these for webhook handling:
- `GITHUB_WEBHOOK_SECRET` — shared secret for GitHub webhook HMAC validation
- `GITHUB_TOKEN` — PAT for fetching PR comments on rejection (needs `repo` scope or fine-grained read on target repos)
```

- [ ] **Step 2: Create R2 bucket (manual step — document the commands)**

This is a manual Cloudflare dashboard or wrangler step. Document for reference:

```bash
# Via wrangler (if installed):
npx wrangler r2 bucket create dispatch-evidence

# Then create an API token in Cloudflare dashboard:
# R2 > Manage R2 API Tokens > Create API Token
# Permissions: Object Read & Write
# Specify bucket: dispatch-evidence
# Save the Access Key ID and Secret Access Key
```

- [ ] **Step 3: Commit documentation update**

```bash
cd ~/development/openclaw
git add CLAUDE.md
git commit -m "docs: add M2 dispatch R2 and webhook env var documentation"
```

---

## Task 12: Configure GitHub webhooks (manual)

This task is manual — cannot be automated via code.

- [ ] **Step 1: Configure webhook on localshout-next**

Go to: `https://github.com/marvinbarretto-labs/localshout-next/settings/hooks/new`
- Payload URL: `https://167.99.206.214/webhooks/github`
- Content type: `application/json`
- Secret: (value of `GITHUB_WEBHOOK_SECRET`)
- Events: "Let me select individual events" → check only "Pull requests"
- Active: checked

- [ ] **Step 2: Configure webhook on hub**

Go to: `https://github.com/marvinbarretto-labs/hub/settings/hooks/new`
- Same settings as above

- [ ] **Step 3: Test webhook delivery**

After configuring, open and close a test PR on either repo. Check jimbo-api logs:

```bash
ssh jimbo
journalctl -u jimbo-api -f
```

Verify the webhook arrives and is processed (look for the JSON response in logs).

- [ ] **Step 4: Add GITHUB_WEBHOOK_SECRET and GITHUB_TOKEN to VPS env**

```bash
ssh jimbo
# Add to /opt/openclaw.env:
# GITHUB_WEBHOOK_SECRET=<generated-secret>
# GITHUB_TOKEN=<existing-or-new-pat>
sudo systemctl restart jimbo-api
```

---

## Task 13: Deploy jimbo-api changes

**Files:** None — deployment task

- [ ] **Step 1: Build jimbo-api**

```bash
cd ~/development/jimbo/jimbo-api
npm run build
```

- [ ] **Step 2: Run full test suite one final time**

```bash
npx vitest run
```

Expected: All tests pass

- [ ] **Step 3: Deploy to VPS**

```bash
cd ~/development/jimbo/jimbo-api
git push
ssh jimbo "cd ~/development/jimbo/jimbo-api && git pull && npm run build && cp -r dist/* . && sudo systemctl restart jimbo-api"
```

- [ ] **Step 4: Verify deployment**

```bash
curl -sk -H "X-API-Key: $API_KEY" "https://167.99.206.214/api/health"
curl -sk "https://167.99.206.214/api/dispatch/status"
```

- [ ] **Step 5: Push openclaw template changes to VPS**

```bash
cd ~/development/openclaw
./scripts/workspace-push.sh
```

---

## Summary

| Task | Repo | What |
|------|------|------|
| 1 | jimbo-api | Schema: add pr_url, pr_state, rejection_reason columns |
| 2 | jimbo-api | Extend completeTask to store pr_url |
| 3 | jimbo-api | PR lookup functions (by URL and branch) |
| 4 | jimbo-api | Shared Telegram notification helper |
| 5 | jimbo-api | Subtask rollup check |
| 6 | jimbo-api | GitHub webhook route + mount |
| 7 | openclaw | Centralised output contract template |
| 8 | openclaw | Rewrite researcher + drafter templates |
| 9 | hub | Folder initialisation + CLAUDE.md |
| 10 | openclaw | Rejection feedback in dispatch worker guide |
| 11 | openclaw | R2 + webhook env var documentation |
| 12 | manual | Configure GitHub webhooks on repos |
| 13 | manual | Deploy jimbo-api + push templates |
