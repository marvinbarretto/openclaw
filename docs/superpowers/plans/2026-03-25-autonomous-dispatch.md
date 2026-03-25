# Autonomous Task Dispatch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an autonomous dispatch system that selects vault tasks, proposes batches for Marvin's approval, dispatches them to Claude Code on M2, and posts results back.

**Architecture:** VPS orchestrates (dispatch.py + jimbo-api), M2 executes (Claude Code via SSH + tmux). Approval via web-links in Telegram messages. Curated batch queue with continuous drip.

**Tech Stack:** jimbo-api (Hono/TypeScript, better-sqlite3, Vitest), dispatch.py (Python 3.11 stdlib), Claude Code on M2

**Spec:** `docs/superpowers/specs/2026-03-25-autonomous-dispatch-design.md`

---

## File Map

### jimbo-api (`~/development/jimbo/jimbo-api`)

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `src/types/dispatch.ts` | TypeScript interfaces for dispatch queue and API payloads |
| Create | `src/services/dispatch.ts` | Dispatch queue CRUD, DoR gate logic, batch proposal, approval tokens |
| Create | `src/routes/dispatch.ts` | API endpoints for /api/dispatch/* |
| Modify | `src/db/index.ts` | Add dispatch_queue table + vault_notes column migrations |
| Modify | `src/types/vault.ts` | Add dispatch_status, agent_type, definition_of_done to VaultNote types |
| Modify | `src/services/vault.ts` | Support new fields in list/update operations |
| Modify | `src/index.ts` | Mount dispatch routes |
| Create | `test/dispatch.test.ts` | Tests for dispatch service + routes |

### openclaw (`~/development/openclaw`)

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `workspace/dispatch.py` | Main orchestrator script (lockfile, loop, SSH, Telegram, results) |
| Create | `workspace/dispatch/templates/coder.md` | Coder agent prompt template |
| Create | `workspace/dispatch/templates/researcher.md` | Researcher agent prompt template |
| Create | `workspace/dispatch/templates/drafter.md` | Drafter agent prompt template |
| Modify | `workspace/accountability-check.py` | Add check_dispatch_today() |
| Modify | `scripts/workspace-push.sh` | Include dispatch/ directory in rsync |
| Create | `workspace/tests/test_dispatch.py` | Tests for dispatch.py parsing and logic |

### VPS infrastructure

| Action | Target | Responsibility |
|--------|--------|---------------|
| Modify | `/root/.ssh/config` on VPS | ControlMaster for VPS→M2 via Tailscale |
| Add | VPS root crontab | `*/5 * * * *` dispatch.py entry |

---

## Task 1: Dispatch Types (jimbo-api)

**Files:**
- Create: `~/development/jimbo/jimbo-api/src/types/dispatch.ts`

- [ ] **Step 1: Create dispatch type definitions**

```typescript
// src/types/dispatch.ts

export type AgentType = 'coder' | 'researcher' | 'drafter';

export type DispatchStatus =
  | 'proposed'
  | 'approved'
  | 'rejected'
  | 'dispatching'
  | 'running'
  | 'completed'
  | 'failed';

export interface DispatchQueueItem {
  id: number;
  task_id: string;
  task_source: string;
  agent_type: AgentType;
  batch_id: string | null;
  status: DispatchStatus;
  dispatch_prompt: string | null;
  dispatch_repo: string | null;
  result_summary: string | null;
  result_artifacts: string | null;
  error_message: string | null;
  retry_count: number;
  proposed_at: string | null;
  approved_at: string | null;
  rejected_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface DispatchProposeParams {
  batch_size?: number;  // default 3
}

export interface DispatchApproveParams {
  batch_id: string;
  items?: number[];  // specific item IDs, or all if omitted
  token: string;
}

export interface DispatchRejectParams {
  batch_id: string;
  token: string;
}

export interface DispatchCompleteParams {
  id: number;
  result_summary: string;
  result_artifacts?: string;  // JSON string
}

export interface DispatchFailParams {
  id: number;
  error_message: string;
}

export interface DispatchListParams {
  status?: string;
  batch_id?: string;
  limit?: number;
  offset?: number;
}

export const AGENT_TYPES: AgentType[] = ['coder', 'researcher', 'drafter'];

export const DISPATCH_STATUSES: DispatchStatus[] = [
  'proposed', 'approved', 'rejected', 'dispatching', 'running', 'completed', 'failed'
];
```

- [ ] **Step 2: Commit**

```bash
cd ~/development/jimbo/jimbo-api
git add src/types/dispatch.ts
git commit -m "feat: add dispatch queue type definitions"
```

---

## Task 2: Database Migration (jimbo-api)

**Files:**
- Modify: `~/development/jimbo/jimbo-api/src/db/index.ts`
- Modify: `~/development/jimbo/jimbo-api/src/types/vault.ts`

- [ ] **Step 1: Add dispatch_queue table to schema**

In `src/db/index.ts`, add to the `SCHEMA` constant (after existing CREATE TABLE statements):

```sql
CREATE TABLE IF NOT EXISTS dispatch_queue (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id TEXT NOT NULL,
  task_source TEXT NOT NULL DEFAULT 'vault',
  agent_type TEXT NOT NULL,
  batch_id TEXT,
  status TEXT NOT NULL DEFAULT 'proposed',
  dispatch_prompt TEXT,
  dispatch_repo TEXT,
  result_summary TEXT,
  result_artifacts TEXT,
  error_message TEXT,
  retry_count INTEGER DEFAULT 0,
  proposed_at TEXT,
  approved_at TEXT,
  rejected_at TEXT,
  started_at TEXT,
  completed_at TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);
```

- [ ] **Step 2: Add migrations for indexes and vault columns**

In `src/db/index.ts`, add to the migrations section (the try/catch blocks after schema creation):

```typescript
// Dispatch queue indexes
try { db.exec(`CREATE INDEX idx_dispatch_status ON dispatch_queue(status)`); } catch {}
try { db.exec(`CREATE INDEX idx_dispatch_task_id ON dispatch_queue(task_id)`); } catch {}
try { db.exec(`CREATE INDEX idx_dispatch_batch_id ON dispatch_queue(batch_id)`); } catch {}

// Vault dispatch fields (may already exist from vault task system — try/catch handles it)
try { db.exec(`ALTER TABLE vault_notes ADD COLUMN dispatch_status TEXT DEFAULT 'none'`); } catch {}
try { db.exec(`ALTER TABLE vault_notes ADD COLUMN agent_type TEXT`); } catch {}
try { db.exec(`ALTER TABLE vault_notes ADD COLUMN definition_of_done TEXT`); } catch {}
try { db.exec(`ALTER TABLE vault_notes ADD COLUMN actionability TEXT`); } catch {}
```

- [ ] **Step 3: Update vault types to include new fields**

In `src/types/vault.ts`, add to the `VaultNote` interface:

```typescript
dispatch_status: string;    // 'none' | 'needs_grooming' | 'ready'
agent_type: string | null;  // 'coder' | 'researcher' | 'drafter'
definition_of_done: string | null;
actionability: string | null; // 'clear' | 'vague' | 'needs-breakdown'
```

Add to `VaultNoteUpdate`:

```typescript
dispatch_status?: string;
agent_type?: string | null;
definition_of_done?: string | null;
actionability?: string | null;
```

Add to `VaultListParams`:

```typescript
dispatch_status?: string;
agent_type?: string;
```

- [ ] **Step 4: Update vault service to handle new fields in updateNote()**

In `src/services/vault.ts`, inside `updateNote()`, add handling for the new fields in the dynamic SET clause builder (following the existing pattern):

```typescript
if (patch.dispatch_status !== undefined) { sets.push('dispatch_status = ?'); values.push(patch.dispatch_status); }
if (patch.agent_type !== undefined) { sets.push('agent_type = ?'); values.push(patch.agent_type); }
if (patch.definition_of_done !== undefined) { sets.push('definition_of_done = ?'); values.push(patch.definition_of_done); }
if (patch.actionability !== undefined) { sets.push('actionability = ?'); values.push(patch.actionability); }
```

In `listNotes()`, add filtering for the new fields (following existing pattern):

```typescript
if (params.dispatch_status) {
  where.push('dispatch_status = ?');
  values.push(params.dispatch_status);
}
if (params.agent_type) {
  where.push('agent_type = ?');
  values.push(params.agent_type);
}
```

- [ ] **Step 5: Run tests to verify nothing broke**

```bash
cd ~/development/jimbo/jimbo-api
npm test
```

Expected: All existing tests pass. New columns don't break existing queries because they have defaults.

- [ ] **Step 6: Commit**

```bash
git add src/db/index.ts src/types/vault.ts src/services/vault.ts
git commit -m "feat: add dispatch_queue table and vault dispatch fields"
```

---

## Task 3: Dispatch Service (jimbo-api)

**Files:**
- Create: `~/development/jimbo/jimbo-api/src/services/dispatch.ts`
- Create: `~/development/jimbo/jimbo-api/test/dispatch.test.ts`

- [ ] **Step 1: Write tests for core dispatch operations**

```typescript
// test/dispatch.test.ts
import { describe, it, expect, beforeEach } from 'vitest';
import { getDb } from '../src/db/index.js';

// Use isolated test database
process.env.CONTEXT_DB_PATH = './test/tmp-dispatch-db';

import {
  proposeBatch,
  approveBatch,
  rejectBatch,
  getNextApproved,
  startTask,
  completeTask,
  failTask,
  listQueue,
  generateApprovalToken,
  validateApprovalToken,
} from '../src/services/dispatch.js';

function seedReadyNote(overrides: Record<string, unknown> = {}) {
  const db = getDb();
  const id = 'note_' + Math.random().toString(36).slice(2, 10);
  db.prepare(`INSERT INTO vault_notes (id, title, type, status, route, dispatch_status, agent_type, definition_of_done, actionability, ai_priority)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`).run(
    id,
    overrides.title ?? 'Test task',
    overrides.type ?? 'task',
    overrides.status ?? 'active',
    overrides.route ?? 'claude_code',
    overrides.dispatch_status ?? 'ready',
    overrides.agent_type ?? 'coder',
    overrides.definition_of_done ?? 'Tests pass and PR opened',
    overrides.actionability ?? 'clear',
    overrides.ai_priority ?? 7,
  );
  return id;
}

describe('dispatch service', () => {
  beforeEach(() => {
    const db = getDb();
    db.exec('DELETE FROM dispatch_queue');
    db.exec('DELETE FROM vault_notes');
  });

  describe('proposeBatch', () => {
    it('should propose ready vault tasks', () => {
      const id1 = seedReadyNote({ ai_priority: 9 });
      const id2 = seedReadyNote({ ai_priority: 7 });
      seedReadyNote({ dispatch_status: 'needs_grooming' }); // should be excluded

      const batch = proposeBatch({ batch_size: 3 });
      expect(batch.items).toHaveLength(2);
      expect(batch.items[0].task_id).toBe(id1); // higher priority first
      expect(batch.batch_id).toMatch(/^batch-\d{8}-\d{6}$/);
    });

    it('should exclude tasks already in queue', () => {
      const id = seedReadyNote();
      proposeBatch({ batch_size: 3 }); // first proposal
      const second = proposeBatch({ batch_size: 3 }); // should skip already-proposed
      expect(second.items).toHaveLength(0);
    });

    it('should exclude recently rejected tasks (24h cooldown)', () => {
      const id = seedReadyNote();
      const batch = proposeBatch({ batch_size: 3 });
      rejectBatch({ batch_id: batch.batch_id, token: 'test' });

      const second = proposeBatch({ batch_size: 3 });
      expect(second.items).toHaveLength(0); // still in cooldown
    });
  });

  describe('approveBatch', () => {
    it('should approve all items in a batch', () => {
      seedReadyNote();
      seedReadyNote();
      const batch = proposeBatch({ batch_size: 3 });

      approveBatch({ batch_id: batch.batch_id, token: 'test' });

      const queue = listQueue({ status: 'approved' });
      expect(queue.items).toHaveLength(2);
    });

    it('should approve specific items only', () => {
      seedReadyNote();
      seedReadyNote();
      const batch = proposeBatch({ batch_size: 3 });
      const firstId = batch.items[0].id;

      approveBatch({ batch_id: batch.batch_id, items: [firstId], token: 'test' });

      const approved = listQueue({ status: 'approved' });
      const rejected = listQueue({ status: 'rejected' });
      expect(approved.items).toHaveLength(1);
      expect(rejected.items).toHaveLength(1);
    });
  });

  describe('task execution lifecycle', () => {
    it('should flow through dispatching → running → completed', () => {
      seedReadyNote();
      const batch = proposeBatch({ batch_size: 1 });
      approveBatch({ batch_id: batch.batch_id, token: 'test' });

      const next = getNextApproved();
      expect(next).not.toBeNull();

      startTask(next!.id);
      const running = listQueue({ status: 'running' });
      expect(running.items).toHaveLength(1);

      completeTask({ id: next!.id, result_summary: 'PR #42 opened' });
      const completed = listQueue({ status: 'completed' });
      expect(completed.items).toHaveLength(1);
      expect(completed.items[0].result_summary).toBe('PR #42 opened');
    });

    it('should retry failed tasks up to 2 times', () => {
      seedReadyNote();
      const batch = proposeBatch({ batch_size: 1 });
      approveBatch({ batch_id: batch.batch_id, token: 'test' });

      const next = getNextApproved();
      startTask(next!.id);
      failTask({ id: next!.id, error_message: 'timeout' });

      // Should be back in approved with retry_count = 1
      const retried = getNextApproved();
      expect(retried).not.toBeNull();
      expect(retried!.retry_count).toBe(1);
    });
  });

  describe('approval tokens', () => {
    it('should generate and validate tokens', () => {
      const token = generateApprovalToken('batch-20260325-120000');
      expect(validateApprovalToken('batch-20260325-120000', token)).toBe(true);
      expect(validateApprovalToken('batch-20260325-120000', 'wrong')).toBe(false);
    });
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ~/development/jimbo/jimbo-api
npm test -- test/dispatch.test.ts
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement dispatch service**

```typescript
// src/services/dispatch.ts
import { getDb } from '../db/index.js';
import crypto from 'node:crypto';
import type {
  DispatchQueueItem,
  DispatchProposeParams,
  DispatchApproveParams,
  DispatchRejectParams,
  DispatchCompleteParams,
  DispatchFailParams,
  DispatchListParams,
  AgentType,
} from '../types/dispatch.js';

const APPROVAL_SECRET = process.env.DISPATCH_APPROVAL_SECRET || process.env.API_KEY || 'dispatch-default-secret';
const REJECTION_COOLDOWN_HOURS = 24;
const MAX_RETRIES = 2;

function now(): string {
  return new Date().toISOString().replace('T', ' ').slice(0, 19);
}

function generateBatchId(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  return `batch-${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`;
}

export function generateApprovalToken(batchId: string): string {
  const expiry = Date.now() + 24 * 60 * 60 * 1000; // 24h
  const payload = `${batchId}:${expiry}`;
  const sig = crypto.createHmac('sha256', APPROVAL_SECRET).update(payload).digest('hex').slice(0, 16);
  return Buffer.from(`${payload}:${sig}`).toString('base64url');
}

export function validateApprovalToken(batchId: string, token: string): boolean {
  try {
    const decoded = Buffer.from(token, 'base64url').toString();
    const [tokenBatchId, expiryStr, sig] = decoded.split(':');
    if (tokenBatchId !== batchId) return false;
    if (Date.now() > Number(expiryStr)) return false;
    const expectedSig = crypto.createHmac('sha256', APPROVAL_SECRET)
      .update(`${tokenBatchId}:${expiryStr}`).digest('hex').slice(0, 16);
    return sig === expectedSig;
  } catch {
    return false;
  }
}

export function proposeBatch(params: DispatchProposeParams): { batch_id: string; items: DispatchQueueItem[]; token: string } {
  const db = getDb();
  const batchSize = params.batch_size ?? 3;
  const batchId = generateBatchId();

  // Find vault tasks that pass the DoR gate
  // Excludes: tasks already in queue (any active status), recently rejected (cooldown)
  const readyTasks = db.prepare(`
    SELECT vn.id, vn.title, vn.agent_type, vn.definition_of_done, vn.ai_priority, vn.route
    FROM vault_notes vn
    WHERE vn.dispatch_status = 'ready'
      AND vn.route = 'claude_code'
      AND vn.actionability = 'clear'
      AND vn.agent_type IS NOT NULL
      AND vn.definition_of_done IS NOT NULL
      AND COALESCE(vn.ai_priority, 0) >= 5
      AND vn.id NOT IN (
        SELECT task_id FROM dispatch_queue
        WHERE status NOT IN ('rejected', 'completed', 'failed')
      )
      AND vn.id NOT IN (
        SELECT task_id FROM dispatch_queue
        WHERE status = 'rejected'
        AND rejected_at > datetime('now', '-${REJECTION_COOLDOWN_HOURS} hours')
      )
    ORDER BY COALESCE(vn.ai_priority, 0) DESC
    LIMIT ?
  `).all(batchSize) as Array<{ id: string; title: string; agent_type: AgentType; definition_of_done: string; ai_priority: number; route: string }>;

  const items: DispatchQueueItem[] = [];
  const timestamp = now();

  for (const task of readyTasks) {
    const result = db.prepare(`
      INSERT INTO dispatch_queue (task_id, task_source, agent_type, batch_id, status, proposed_at)
      VALUES (?, 'vault', ?, ?, 'proposed', ?)
    `).run(task.id, task.agent_type, batchId, timestamp);

    const item = db.prepare('SELECT * FROM dispatch_queue WHERE id = ?').get(result.lastInsertRowid) as DispatchQueueItem;
    items.push(item);
  }

  const token = generateApprovalToken(batchId);
  return { batch_id: batchId, items, token };
}

export function approveBatch(params: DispatchApproveParams): { approved: number; rejected: number } {
  const db = getDb();
  const timestamp = now();

  if (params.items && params.items.length > 0) {
    // Approve specific items, reject the rest
    const placeholders = params.items.map(() => '?').join(',');
    db.prepare(`UPDATE dispatch_queue SET status = 'approved', approved_at = ? WHERE batch_id = ? AND id IN (${placeholders}) AND status = 'proposed'`)
      .run(timestamp, params.batch_id, ...params.items);
    db.prepare(`UPDATE dispatch_queue SET status = 'rejected', rejected_at = ? WHERE batch_id = ? AND id NOT IN (${placeholders}) AND status = 'proposed'`)
      .run(timestamp, params.batch_id, ...params.items);
  } else {
    // Approve all
    db.prepare(`UPDATE dispatch_queue SET status = 'approved', approved_at = ? WHERE batch_id = ? AND status = 'proposed'`)
      .run(timestamp, params.batch_id);
  }

  const approved = (db.prepare(`SELECT COUNT(*) as count FROM dispatch_queue WHERE batch_id = ? AND status = 'approved'`).get(params.batch_id) as { count: number }).count;
  const rejected = (db.prepare(`SELECT COUNT(*) as count FROM dispatch_queue WHERE batch_id = ? AND status = 'rejected'`).get(params.batch_id) as { count: number }).count;
  return { approved, rejected };
}

export function rejectBatch(params: DispatchRejectParams): { rejected: number } {
  const db = getDb();
  const timestamp = now();
  const result = db.prepare(`UPDATE dispatch_queue SET status = 'rejected', rejected_at = ? WHERE batch_id = ? AND status = 'proposed'`)
    .run(timestamp, params.batch_id);
  return { rejected: result.changes };
}

export function getNextApproved(): DispatchQueueItem | null {
  const db = getDb();
  return (db.prepare(`SELECT * FROM dispatch_queue WHERE status = 'approved' ORDER BY id ASC LIMIT 1`).get() as DispatchQueueItem) ?? null;
}

export function startTask(id: number): DispatchQueueItem | null {
  const db = getDb();
  db.prepare(`UPDATE dispatch_queue SET status = 'running', started_at = ? WHERE id = ? AND status IN ('approved', 'dispatching')`)
    .run(now(), id);
  return (db.prepare('SELECT * FROM dispatch_queue WHERE id = ?').get(id) as DispatchQueueItem) ?? null;
}

export function completeTask(params: DispatchCompleteParams): DispatchQueueItem | null {
  const db = getDb();
  db.prepare(`UPDATE dispatch_queue SET status = 'completed', result_summary = ?, result_artifacts = ?, completed_at = ? WHERE id = ?`)
    .run(params.result_summary, params.result_artifacts ?? null, now(), params.id);

  // Update vault task status to done
  const item = db.prepare('SELECT * FROM dispatch_queue WHERE id = ?').get(params.id) as DispatchQueueItem;
  if (item?.task_source === 'vault') {
    db.prepare(`UPDATE vault_notes SET status = 'done', completed_at = datetime('now'), updated_at = datetime('now') WHERE id = ?`)
      .run(item.task_id);
  }
  return item;
}

export function failTask(params: DispatchFailParams): DispatchQueueItem | null {
  const db = getDb();
  const item = db.prepare('SELECT * FROM dispatch_queue WHERE id = ?').get(params.id) as DispatchQueueItem;
  if (!item) return null;

  if (item.retry_count < MAX_RETRIES) {
    // Retry: back to approved
    db.prepare(`UPDATE dispatch_queue SET status = 'approved', error_message = ?, retry_count = retry_count + 1, started_at = NULL, completed_at = NULL WHERE id = ?`)
      .run(params.error_message, params.id);
  } else {
    // Max retries: mark failed, vault task needs grooming
    db.prepare(`UPDATE dispatch_queue SET status = 'failed', error_message = ?, completed_at = ? WHERE id = ?`)
      .run(params.error_message, now(), params.id);
    if (item.task_source === 'vault') {
      db.prepare(`UPDATE vault_notes SET dispatch_status = 'needs_grooming', updated_at = datetime('now') WHERE id = ?`)
        .run(item.task_id);
    }
  }
  return db.prepare('SELECT * FROM dispatch_queue WHERE id = ?').get(params.id) as DispatchQueueItem;
}

export function listQueue(params: DispatchListParams): { items: DispatchQueueItem[]; total: number } {
  const db = getDb();
  const where: string[] = [];
  const values: unknown[] = [];

  if (params.status) {
    if (params.status.includes(',')) {
      const statuses = params.status.split(',');
      where.push(`status IN (${statuses.map(() => '?').join(',')})`);
      values.push(...statuses);
    } else {
      where.push('status = ?');
      values.push(params.status);
    }
  }
  if (params.batch_id) {
    where.push('batch_id = ?');
    values.push(params.batch_id);
  }

  const whereClause = where.length > 0 ? `WHERE ${where.join(' AND ')}` : '';
  const total = (db.prepare(`SELECT COUNT(*) as count FROM dispatch_queue ${whereClause}`).get(...values) as { count: number }).count;

  const limit = params.limit ?? 50;
  const offset = params.offset ?? 0;
  const items = db.prepare(`SELECT * FROM dispatch_queue ${whereClause} ORDER BY id DESC LIMIT ? OFFSET ?`)
    .all(...values, limit, offset) as DispatchQueueItem[];

  return { items, total };
}

export function getRunningTask(): DispatchQueueItem | null {
  const db = getDb();
  return (db.prepare(`SELECT * FROM dispatch_queue WHERE status = 'running' ORDER BY started_at ASC LIMIT 1`).get() as DispatchQueueItem) ?? null;
}

export function getProposedBatch(): { batch_id: string; items: DispatchQueueItem[] } | null {
  const db = getDb();
  const first = db.prepare(`SELECT batch_id FROM dispatch_queue WHERE status = 'proposed' ORDER BY id ASC LIMIT 1`).get() as { batch_id: string } | undefined;
  if (!first) return null;
  const items = db.prepare(`SELECT * FROM dispatch_queue WHERE batch_id = ? AND status = 'proposed'`).all(first.batch_id) as DispatchQueueItem[];
  return { batch_id: first.batch_id, items };
}

// Auto-expire proposed batches older than 24h
export function expireOldProposals(): number {
  const db = getDb();
  const result = db.prepare(`UPDATE dispatch_queue SET status = 'rejected', rejected_at = ? WHERE status = 'proposed' AND proposed_at < datetime('now', '-24 hours')`)
    .run(now());
  return result.changes;
}

export function updatePrompt(id: number, prompt: string, repo?: string): void {
  const db = getDb();
  db.prepare(`UPDATE dispatch_queue SET dispatch_prompt = ?, dispatch_repo = ? WHERE id = ?`)
    .run(prompt, repo ?? null, id);
}
```

- [ ] **Step 4: Run tests**

```bash
cd ~/development/jimbo/jimbo-api
npm test -- test/dispatch.test.ts
```

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/services/dispatch.ts test/dispatch.test.ts
git commit -m "feat: implement dispatch service with batch proposal, approval, and lifecycle"
```

---

## Task 4: Dispatch API Routes (jimbo-api)

**Files:**
- Create: `~/development/jimbo/jimbo-api/src/routes/dispatch.ts`
- Modify: `~/development/jimbo/jimbo-api/src/index.ts`

- [ ] **Step 1: Create dispatch routes**

```typescript
// src/routes/dispatch.ts
import { Hono } from 'hono';
import {
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
  updatePrompt,
  generateApprovalToken,
  validateApprovalToken,
} from '../services/dispatch.js';

const dispatch = new Hono();

// List queue items
dispatch.get('/queue', (c) => {
  const params = {
    status: c.req.query('status'),
    batch_id: c.req.query('batch_id'),
    limit: c.req.query('limit') ? Number(c.req.query('limit')) : undefined,
    offset: c.req.query('offset') ? Number(c.req.query('offset')) : undefined,
  };
  return c.json(listQueue(params));
});

// Get current state (running task, proposed batch, etc.)
dispatch.get('/status', (c) => {
  const running = getRunningTask();
  const proposed = getProposedBatch();
  const nextApproved = getNextApproved();
  return c.json({ running, proposed, next_approved: nextApproved });
});

// Propose a new batch
dispatch.post('/propose', async (c) => {
  const body = await c.req.json<{ batch_size?: number }>().catch(() => ({}));
  expireOldProposals(); // cleanup before proposing
  const result = proposeBatch({ batch_size: body.batch_size });

  if (result.items.length === 0) {
    return c.json({ message: 'No ready tasks available', batch_id: null, items: [] });
  }

  // Build approval URLs for Telegram message
  const baseUrl = process.env.JIMBO_API_URL || 'https://167.99.206.214';
  const approveUrl = `${baseUrl}/api/dispatch/approve-link?batch=${result.batch_id}&token=${result.token}`;
  const rejectUrl = `${baseUrl}/api/dispatch/reject-link?batch=${result.batch_id}&token=${result.token}`;

  return c.json({
    ...result,
    approve_url: approveUrl,
    reject_url: rejectUrl,
  }, 201);
});

// Approve via web link (GET — clicked from Telegram)
dispatch.get('/approve-link', (c) => {
  const batchId = c.req.query('batch');
  const token = c.req.query('token');
  const itemsParam = c.req.query('items');

  if (!batchId || !token) {
    return c.html('<h1>Bad request</h1><p>Missing batch or token.</p>', 400);
  }
  if (!validateApprovalToken(batchId, token)) {
    return c.html('<h1>Expired or invalid</h1><p>This approval link has expired. Ask dispatch to propose again.</p>', 403);
  }

  const items = itemsParam ? itemsParam.split(',').map(Number) : undefined;
  const result = approveBatch({ batch_id: batchId, items, token });
  return c.html(`<h1>Approved</h1><p>${result.approved} tasks approved, ${result.rejected} rejected.</p><p>Dispatch will start within 5 minutes.</p>`);
});

// Reject via web link (GET — clicked from Telegram)
dispatch.get('/reject-link', (c) => {
  const batchId = c.req.query('batch');
  const token = c.req.query('token');

  if (!batchId || !token) {
    return c.html('<h1>Bad request</h1>', 400);
  }
  if (!validateApprovalToken(batchId, token)) {
    return c.html('<h1>Expired or invalid</h1>', 403);
  }

  const result = rejectBatch({ batch_id: batchId, token });
  return c.html(`<h1>Rejected</h1><p>${result.rejected} tasks returned to queue.</p>`);
});

// Approve via API (POST — from dashboard or scripts)
dispatch.post('/approve', async (c) => {
  const body = await c.req.json<{ batch_id: string; items?: number[] }>();
  if (!body.batch_id) return c.json({ error: 'batch_id required' }, 400);
  // API callers are already authenticated via X-API-Key, no approval token needed
  const result = approveBatch({ batch_id: body.batch_id, items: body.items, token: 'api-auth' });
  return c.json(result);
});

// Reject via API
dispatch.post('/reject', async (c) => {
  const body = await c.req.json<{ batch_id: string }>();
  if (!body.batch_id) return c.json({ error: 'batch_id required' }, 400);
  const result = rejectBatch({ batch_id: body.batch_id, token: 'api-auth' });
  return c.json(result);
});

// Get next approved task for execution
dispatch.get('/next', (c) => {
  const next = getNextApproved();
  if (!next) return c.json({ message: 'No approved tasks' }, 404);
  return c.json(next);
});

// Mark task as started
dispatch.post('/start', async (c) => {
  const { id, prompt, repo } = await c.req.json<{ id: number; prompt?: string; repo?: string }>();
  if (!id) return c.json({ error: 'id required' }, 400);
  if (prompt) updatePrompt(id, prompt, repo);
  const result = startTask(id);
  if (!result) return c.json({ error: 'Task not found or not in approved state' }, 404);
  return c.json(result);
});

// Report completion
dispatch.post('/complete', async (c) => {
  const body = await c.req.json<{ id: number; result_summary: string; result_artifacts?: string }>();
  if (!body.id || !body.result_summary) return c.json({ error: 'id and result_summary required' }, 400);
  const result = completeTask(body);
  if (!result) return c.json({ error: 'Task not found' }, 404);
  return c.json(result);
});

// Report failure
dispatch.post('/fail', async (c) => {
  const body = await c.req.json<{ id: number; error_message: string }>();
  if (!body.id || !body.error_message) return c.json({ error: 'id and error_message required' }, 400);
  const result = failTask(body);
  if (!result) return c.json({ error: 'Task not found' }, 404);
  return c.json(result);
});

// History (completed + failed)
dispatch.get('/history', (c) => {
  const params = {
    status: c.req.query('status') || 'completed,failed',
    limit: c.req.query('limit') ? Number(c.req.query('limit')) : 20,
    offset: c.req.query('offset') ? Number(c.req.query('offset')) : 0,
  };
  return c.json(listQueue(params));
});

export default dispatch;
```

- [ ] **Step 2: Mount dispatch routes in index.ts**

In `src/index.ts`, add:

```typescript
import dispatch from './routes/dispatch.js';
```

And in the route mounting section (alongside other `app.route()` calls):

```typescript
app.route('/api/dispatch', dispatch);
```

**Note:** The `/approve-link` and `/reject-link` GET endpoints are called via browser clicks from Telegram. They return HTML, not JSON. They still go through the `apiKeyAuth` middleware on `/api/*`, which means the approval token in the URL is the auth mechanism — but the middleware will block the request because there's no X-API-Key header in a browser click.

**Fix:** These two GET endpoints need to bypass auth. Either:
- Mount them outside `/api/*` (e.g. `/dispatch/approve-link`)
- Or add a middleware exception for these paths

The simplest approach: mount the link handlers separately before the auth middleware:

```typescript
// In index.ts, BEFORE the auth middleware
import { Hono } from 'hono';

// Public dispatch approval endpoints (no API key — token is the auth)
app.get('/dispatch/approve', (c) => { /* same handler as approve-link */ });
app.get('/dispatch/reject', (c) => { /* same handler as reject-link */ });

// Then the authenticated API routes
app.use('/api/*', apiKeyAuth);
app.route('/api/dispatch', dispatch);
```

Adjust the route handler to import the approval logic directly. Keep it DRY by calling the service functions.

- [ ] **Step 3: Run all tests**

```bash
cd ~/development/jimbo/jimbo-api
npm test
```

Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add src/routes/dispatch.ts src/index.ts
git commit -m "feat: add dispatch API routes with web-link approval"
```

---

## Task 5: Build and Deploy jimbo-api

**Files:**
- Modify: `~/development/jimbo/jimbo-api` (build output)

- [ ] **Step 1: Build**

```bash
cd ~/development/jimbo/jimbo-api
npm run build
```

Expected: Clean compilation to `dist/`.

- [ ] **Step 2: Push to GitHub**

```bash
git push origin main
```

- [ ] **Step 3: Deploy to VPS**

```bash
ssh jimbo "cd ~/development/jimbo/jimbo-api && git pull && npm run build && cp -r dist/* . && sudo systemctl restart jimbo-api"
```

- [ ] **Step 4: Verify deployment**

```bash
curl -sk -H "X-API-Key: $JIMBO_API_KEY" "https://167.99.206.214/api/dispatch/queue"
```

Expected: `{"items":[],"total":0}`

- [ ] **Step 5: Verify approval link route works**

```bash
curl -sk "https://167.99.206.214/dispatch/approve?batch=test&token=invalid"
```

Expected: HTML response with "Expired or invalid" (proves the public route is mounted).

---

## Task 6: Prompt Templates (openclaw)

**Files:**
- Create: `~/development/openclaw/workspace/dispatch/templates/coder.md`
- Create: `~/development/openclaw/workspace/dispatch/templates/researcher.md`
- Create: `~/development/openclaw/workspace/dispatch/templates/drafter.md`

- [ ] **Step 1: Create templates directory**

```bash
mkdir -p ~/development/openclaw/workspace/dispatch/templates
```

- [ ] **Step 2: Write coder template**

Create `workspace/dispatch/templates/coder.md`:

```markdown
You are an autonomous coding agent dispatched to complete a specific task. Work independently and efficiently.

## Task
{title}

## Definition of Done
{definition_of_done}

## Repository
Working directory: {dispatch_repo}

## Instructions
1. Read the relevant code to understand the current state
2. Create a feature branch: `dispatch/{task_id}`
3. Implement the change to satisfy the Definition of Done
4. Run the project's test suite — fix any failures your changes introduced
5. Commit using conventional commits (type: description)
6. Push the branch and open a PR with a clear description referencing this task

## Constraints
- Do not modify files unrelated to the task
- Do not add dependencies without clear justification
- If the test suite doesn't exist or is broken before your changes, note this but don't fix it
- If you get stuck or the task is ambiguous, write your findings and stop — do not guess

## On Completion
Write a JSON file to /tmp/dispatch-{task_id}.result:

```json
{{
  "status": "completed",
  "summary": "one paragraph describing what you did",
  "pr_url": "the PR URL",
  "branch": "dispatch/{task_id}",
  "files_changed": ["list", "of", "files"]
}}
```

If you cannot complete the task, write:

```json
{{
  "status": "blocked",
  "summary": "what you attempted",
  "blockers": "why you couldn't complete it"
}}
```

## North Star (code comment context)
<!-- This agent is v1 of an autonomous dispatch system. Future versions (Approach 3) will use
     git worktrees for isolation, structured output validation, and concurrent execution.
     For now: one task at a time, prompt-level constraints, trust the agent. -->
```

- [ ] **Step 3: Write researcher template**

Create `workspace/dispatch/templates/researcher.md`:

```markdown
You are an autonomous research agent dispatched to investigate a topic and produce structured findings.

## Task
{title}

## Definition of Done
{definition_of_done}

## Instructions
1. Search for relevant information using web search, documentation, and any available tools
2. Compare options where the task requires a decision
3. Cite sources — include URLs where you found key information
4. Write a structured summary that directly addresses the Definition of Done

## Constraints
- Stay focused on the specific research question — do not expand scope
- Prefer recent sources (last 12 months) over older ones
- If information is contradictory, present both sides rather than picking one
- If you cannot find reliable information, say so — do not fabricate

## On Completion
Write a JSON file to /tmp/dispatch-{task_id}.result:

```json
{{
  "status": "completed",
  "summary": "2-3 paragraph summary of findings",
  "recommendations": ["actionable recommendation 1", "recommendation 2"],
  "sources": ["url1", "url2"]
}}
```

If you cannot complete the research:

```json
{{
  "status": "blocked",
  "summary": "what you found so far",
  "blockers": "why the research is incomplete"
}}
```
```

- [ ] **Step 4: Write drafter template**

Create `workspace/dispatch/templates/drafter.md`:

```markdown
You are an autonomous content drafting agent dispatched to produce written content.

## Task
{title}

## Definition of Done
{definition_of_done}

## Output Location
Save the draft to: {output_path}

## Instructions
1. Research the topic if you need background context
2. Write the content to satisfy the Definition of Done
3. Match the tone and style of existing content in the project if applicable
4. Save the final draft to the output location specified above

## Constraints
- Write in Marvin's voice — opinionated, direct, technically informed, occasionally funny
- Do not pad with filler — every paragraph should earn its place
- If a specific format is required (blog post, documentation, spec), follow its conventions
- If the output location doesn't exist, create the necessary directories

## On Completion
Write a JSON file to /tmp/dispatch-{task_id}.result:

```json
{{
  "status": "completed",
  "summary": "one paragraph describing what was drafted",
  "output_path": "{output_path}",
  "word_count": 0
}}
```

If you cannot complete the draft:

```json
{{
  "status": "blocked",
  "summary": "what you attempted",
  "blockers": "why the draft is incomplete"
}}
```
```

- [ ] **Step 5: Commit**

```bash
cd ~/development/openclaw
git add workspace/dispatch/templates/
git commit -m "feat: add dispatch agent prompt templates (coder, researcher, drafter)"
```

---

## Task 7: The Orchestrator — dispatch.py (openclaw)

**Files:**
- Create: `~/development/openclaw/workspace/dispatch.py`
- Create: `~/development/openclaw/workspace/tests/test_dispatch.py`

- [ ] **Step 1: Write tests for parseable logic**

```python
# workspace/tests/test_dispatch.py
"""Tests for dispatch.py parsing and template logic."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

class TestResultParsing(unittest.TestCase):
    """Test the result JSON parsing with fallback."""

    def test_valid_json(self):
        from dispatch import parse_result
        raw = '{"status": "completed", "summary": "Did the thing", "pr_url": "https://github.com/..."}'
        result = parse_result(raw)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['summary'], 'Did the thing')

    def test_json_with_markdown_fences(self):
        from dispatch import parse_result
        raw = '```json\n{"status": "completed", "summary": "Did it"}\n```'
        result = parse_result(raw)
        self.assertEqual(result['status'], 'completed')

    def test_malformed_json_falls_back(self):
        from dispatch import parse_result
        raw = 'I completed the task and opened PR #42. Everything works.'
        result = parse_result(raw)
        self.assertEqual(result['status'], 'completed_unstructured')
        self.assertIn('PR #42', result['summary'])

    def test_empty_result(self):
        from dispatch import parse_result
        result = parse_result('')
        self.assertEqual(result['status'], 'failed')
        self.assertIn('empty', result['summary'].lower())


class TestTemplateRendering(unittest.TestCase):
    """Test prompt template variable substitution."""

    def test_renders_variables(self):
        from dispatch import render_template
        template = "Task: {title}\nDoD: {definition_of_done}\nRepo: {dispatch_repo}"
        result = render_template(template, {
            'title': 'Add dark mode',
            'definition_of_done': 'Toggle works, persists in localStorage',
            'dispatch_repo': '~/development/localshout-next',
            'task_id': 'note_abc123',
        })
        self.assertIn('Add dark mode', result)
        self.assertIn('~/development/localshout-next', result)

    def test_missing_variable_preserved(self):
        from dispatch import render_template
        template = "Task: {title}\nOptional: {output_path}"
        result = render_template(template, {'title': 'Research flights', 'task_id': 'note_xyz'})
        self.assertIn('Research flights', result)
        self.assertIn('{output_path}', result)  # not rendered, preserved


class TestBatchIdParsing(unittest.TestCase):

    def test_valid_batch_id(self):
        from dispatch import is_valid_batch_id
        self.assertTrue(is_valid_batch_id('batch-20260325-143000'))
        self.assertFalse(is_valid_batch_id('not-a-batch'))
        self.assertFalse(is_valid_batch_id(''))


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ~/development/openclaw/workspace
python3 -m pytest tests/test_dispatch.py -v 2>/dev/null || python3 -m unittest tests.test_dispatch -v
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement dispatch.py**

Create `workspace/dispatch.py` — this is the main orchestrator. Full implementation:

```python
#!/usr/bin/env python3
"""
Autonomous task dispatch orchestrator.

Runs via cron every 5 minutes on VPS. Proposes batches from jimbo-api,
monitors agent sessions on M2 via SSH+tmux, reports results.

Usage:
  python3 dispatch.py              # dry-run (default)
  python3 dispatch.py --live       # actually dispatch
  python3 dispatch.py --status     # show current queue state

North Star: This is Approach 2 (API-backed dispatch). Code comments
reference Approach 3 (full agent runtime) as the upgrade path:
worker pool, persistent daemon, capability registry, git worktrees.
"""

import fcntl
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import urllib.error

# --- Configuration ---

API_URL = os.environ.get('JIMBO_API_URL', 'http://localhost:3100')
API_KEY = os.environ.get('JIMBO_API_KEY', os.environ.get('API_KEY', ''))
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')
M2_SSH_HOST = 'm2'  # SSH alias configured in ~/.ssh/config
TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), 'dispatch', 'templates')
LOCK_FILE = '/tmp/dispatch.lock'

# Approach 3: These become configurable per-task or via settings API
TIMEOUTS = {'coder': 1800, 'researcher': 900, 'drafter': 1200}  # seconds
DEFAULT_BATCH_SIZE = 3

# --- Utility functions ---

def log(msg):
    sys.stderr.write(f'[dispatch] {msg}\n')


def api_request(method, path, body=None):
    """Make an authenticated request to jimbo-api."""
    url = f'{API_URL}{path}'
    data = json.dumps(body).encode() if body else None
    headers = {'X-API-Key': API_KEY, 'Accept': 'application/json'}
    if data:
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode() if e.fp else ''
        log(f'API error: {method} {path} → {e.code}: {body_text[:200]}')
        return None
    except Exception as e:
        log(f'API request failed: {method} {path} → {e}')
        return None


def send_telegram(message):
    """Send a Telegram message. Fire-and-forget."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log('Telegram not configured, skipping notification')
        return False
    url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'
    payload = json.dumps({
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': 'HTML',
        'disable_web_page_preview': True,
    }).encode()
    req = urllib.request.Request(url, data=payload,
        headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        log(f'Telegram send failed: {e}')
        return False


def ssh_cmd(cmd, timeout=30):
    """Run a command on M2 via SSH. Returns (success, stdout, stderr)."""
    try:
        result = subprocess.run(
            ['ssh', '-o', 'ConnectTimeout=5', M2_SSH_HOST, cmd],
            capture_output=True, text=True, timeout=timeout
        )
        return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return False, '', 'SSH timeout'
    except Exception as e:
        return False, '', str(e)


def check_m2_reachable():
    """Quick connectivity check to M2."""
    ok, _, _ = ssh_cmd('true', timeout=10)
    return ok


def parse_result(raw):
    """Parse agent result JSON with fallback for malformed output."""
    if not raw or not raw.strip():
        return {'status': 'failed', 'summary': 'Empty result file'}

    text = raw.strip()

    # Try direct JSON parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting JSON from markdown fences
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Fallback: treat raw text as summary
    return {
        'status': 'completed_unstructured',
        'summary': text[:500],
    }


def render_template(template_text, variables):
    """Render a prompt template with variable substitution."""
    result = template_text
    for key, value in variables.items():
        result = result.replace('{' + key + '}', str(value))
    return result


def is_valid_batch_id(batch_id):
    return bool(batch_id and re.match(r'^batch-\d{8}-\d{6}$', batch_id))


def load_template(agent_type):
    """Load prompt template for an agent type."""
    path = os.path.join(TEMPLATE_DIR, f'{agent_type}.md')
    if not os.path.exists(path):
        log(f'Template not found: {path}')
        return None
    with open(path) as f:
        return f.read()


# --- Core dispatch logic ---

def check_running(dry_run=False):
    """Check if there's a running task and monitor it."""
    status = api_request('GET', '/api/dispatch/status')
    if not status or not status.get('running'):
        return False  # nothing running

    task = status['running']
    task_id = task['task_id']
    timeout = TIMEOUTS.get(task['agent_type'], 1800)

    # Check for completion signal
    ok, signal, _ = ssh_cmd(f'cat /tmp/dispatch-{task_id}.signal 2>/dev/null')
    if ok and 'DISPATCH_DONE' in signal:
        # Collect result
        _, result_raw, _ = ssh_cmd(f'cat /tmp/dispatch-{task_id}.result 2>/dev/null')
        result = parse_result(result_raw)

        if result['status'] in ('completed', 'completed_unstructured'):
            log(f'Task {task_id} completed: {result.get("summary", "")[:100]}')
            if not dry_run:
                api_request('POST', '/api/dispatch/complete', {
                    'id': task['id'],
                    'result_summary': result.get('summary', ''),
                    'result_artifacts': json.dumps({
                        k: v for k, v in result.items() if k not in ('status', 'summary')
                    }) if len(result) > 2 else None,
                })
                send_telegram(f'[Dispatch] Done: {task_id} ({task["agent_type"]})\n{result.get("summary", "")[:200]}')
                # Cleanup
                ssh_cmd(f'rm -f /tmp/dispatch-{task_id}.{{prompt,log,signal,result}}')
        elif result['status'] == 'blocked':
            log(f'Task {task_id} blocked: {result.get("blockers", "")}')
            if not dry_run:
                api_request('POST', '/api/dispatch/fail', {
                    'id': task['id'],
                    'error_message': f'Blocked: {result.get("blockers", "unknown")}',
                })
                # Mark vault task as needs_grooming
                api_request('PATCH', f'/api/vault/notes/{task_id}', {
                    'dispatch_status': 'needs_grooming',
                })
                send_telegram(f'[Dispatch] Blocked: {task_id}\n{result.get("blockers", "")[:200]}')
                ssh_cmd(f'rm -f /tmp/dispatch-{task_id}.{{prompt,log,signal,result}}')
        else:
            log(f'Task {task_id} failed: {result.get("summary", "")}')
            if not dry_run:
                api_request('POST', '/api/dispatch/fail', {
                    'id': task['id'],
                    'error_message': result.get('summary', 'Unknown failure'),
                })
                send_telegram(f'[Dispatch] Failed: {task_id}\n{result.get("summary", "")[:200]}')
                ssh_cmd(f'rm -f /tmp/dispatch-{task_id}.{{prompt,log,signal,result}}')

        return True  # was running, now handled

    # Check for timeout
    started = task.get('started_at', '')
    if started:
        try:
            import datetime
            started_dt = datetime.datetime.fromisoformat(started.replace(' ', 'T'))
            elapsed = (datetime.datetime.utcnow() - started_dt).total_seconds()
            if elapsed > timeout:
                log(f'Task {task_id} timed out after {int(elapsed)}s')
                if not dry_run:
                    ssh_cmd(f'tmux kill-session -t dispatch-{task_id} 2>/dev/null')
                    api_request('POST', '/api/dispatch/fail', {
                        'id': task['id'],
                        'error_message': f'Timeout after {int(elapsed)}s (limit: {timeout}s)',
                    })
                    send_telegram(f'[Dispatch] Timeout: {task_id} after {int(elapsed)}s')
                    ssh_cmd(f'rm -f /tmp/dispatch-{task_id}.{{prompt,log,signal,result}}')
                return True
        except Exception as e:
            log(f'Error parsing start time: {e}')

    log(f'Task {task_id} still running')
    return True  # still running


def dispatch_next(dry_run=False):
    """Dispatch the next approved task to M2."""
    task = api_request('GET', '/api/dispatch/next')
    if not task or 'id' not in task:
        return False  # nothing to dispatch

    task_id = task['task_id']
    agent_type = task['agent_type']
    log(f'Dispatching {task_id} ({agent_type})')

    # Load and render template
    template = load_template(agent_type)
    if not template:
        log(f'No template for agent type: {agent_type}')
        if not dry_run:
            api_request('POST', '/api/dispatch/fail', {
                'id': task['id'],
                'error_message': f'No template for agent type: {agent_type}',
            })
        return False

    # Get vault task details for template variables
    vault_task = api_request('GET', f'/api/vault/notes/{task_id}')
    if not vault_task:
        log(f'Vault task not found: {task_id}')
        return False

    # Determine repo path for coder tasks
    dispatch_repo = task.get('dispatch_repo', '')
    if not dispatch_repo and agent_type == 'coder':
        # Default: try to infer from task title/body
        dispatch_repo = '~/development/localshout-next'  # sensible default for now
        # Approach 3: agent capability registry maps task metadata to repos

    prompt = render_template(template, {
        'title': vault_task.get('title', ''),
        'definition_of_done': vault_task.get('definition_of_done', ''),
        'dispatch_repo': dispatch_repo,
        'task_id': task_id,
        'output_path': f'/tmp/dispatch-{task_id}-output',
    })

    if dry_run:
        log(f'DRY RUN: Would dispatch {task_id} to M2')
        log(f'Prompt preview ({len(prompt)} chars):\n{prompt[:300]}...')
        return True

    # Push prompt to M2
    try:
        proc = subprocess.run(
            ['ssh', M2_SSH_HOST, f'cat > /tmp/dispatch-{task_id}.prompt'],
            input=prompt.encode(), capture_output=True, timeout=15
        )
        if proc.returncode != 0:
            raise Exception(f'Push failed: {proc.stderr.decode()[:200]}')
    except Exception as e:
        log(f'Failed to push prompt: {e}')
        api_request('POST', '/api/dispatch/fail', {
            'id': task['id'], 'error_message': f'SSH prompt push failed: {e}',
        })
        return False

    # Start tmux session
    tmux_cmd = (
        f'tmux new-session -d -s dispatch-{task_id} '
        f'"claude -p --bare --dangerously-skip-permissions '
        f'\\"$(cat /tmp/dispatch-{task_id}.prompt)\\" '
        f'> /tmp/dispatch-{task_id}.log 2>&1; '
        f'echo DISPATCH_DONE > /tmp/dispatch-{task_id}.signal"'
    )
    ok, _, err = ssh_cmd(tmux_cmd, timeout=15)
    if not ok:
        log(f'Failed to start tmux: {err}')
        api_request('POST', '/api/dispatch/fail', {
            'id': task['id'], 'error_message': f'tmux start failed: {err}',
        })
        return False

    # Mark as running
    api_request('POST', '/api/dispatch/start', {
        'id': task['id'], 'prompt': prompt, 'repo': dispatch_repo,
    })
    send_telegram(f'[Dispatch] Running: {vault_task.get("title", task_id)} ({agent_type})')
    return True


def propose_batch(dry_run=False):
    """Propose a new batch of tasks for approval."""
    result = api_request('POST', '/api/dispatch/propose', {
        'batch_size': DEFAULT_BATCH_SIZE,
    })
    if not result or not result.get('items'):
        log('No tasks ready for dispatch')
        return False

    items = result['items']
    batch_id = result['batch_id']
    approve_url = result.get('approve_url', '')
    reject_url = result.get('reject_url', '')

    # Build Telegram message
    lines = [f'[Dispatch] Batch {batch_id} — {len(items)} tasks ready:\n']
    for i, item in enumerate(items, 1):
        # Get vault task title
        vault_task = api_request('GET', f'/api/vault/notes/{item["task_id"]}')
        title = vault_task.get('title', item['task_id']) if vault_task else item['task_id']
        icon = {'coder': '🔧', 'researcher': '🔍', 'drafter': '✏️'}.get(item['agent_type'], '📋')
        lines.append(f'{i}. {icon} {title} ({item["agent_type"]})')

    lines.append(f'\n<a href="{approve_url}">Approve all</a>')
    lines.append(f'<a href="{reject_url}">Reject</a>')

    message = '\n'.join(lines)

    if dry_run:
        log(f'DRY RUN: Would send batch proposal:\n{message}')
        return True

    send_telegram(message)
    log(f'Proposed batch {batch_id} with {len(items)} tasks')
    return True


def show_status():
    """Print current dispatch status."""
    status = api_request('GET', '/api/dispatch/status')
    if not status:
        print('Could not reach jimbo-api')
        return

    print(json.dumps(status, indent=2))

    queue = api_request('GET', '/api/dispatch/queue?status=proposed,approved,running')
    if queue:
        print(f'\nActive queue: {queue["total"]} items')
        for item in queue.get('items', []):
            print(f'  [{item["status"]}] {item["task_id"]} ({item["agent_type"]})')


# --- Main ---

def main():
    args = sys.argv[1:]
    dry_run = '--live' not in args

    if '--status' in args:
        show_status()
        return

    if dry_run:
        log('DRY RUN mode (use --live for real dispatch)')

    # Acquire lock (Approach 3: persistent daemon replaces this)
    lock_fd = open(LOCK_FILE, 'w')
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (BlockingIOError, OSError):
        log('Another dispatch instance is running, exiting')
        return

    # Check M2 connectivity
    if not check_m2_reachable():
        log('M2 unreachable via SSH')
        # Only alert once — check if we already know it's offline
        # Approach 3: proper health tracking with backoff
        send_telegram('[Dispatch] M2 unreachable — pausing dispatch')
        return

    # The dispatch loop (one pass per cron invocation)
    # 1. Check running tasks
    if check_running(dry_run):
        return  # handled a running task, check again next cycle

    # 2. Dispatch next approved task
    if dispatch_next(dry_run):
        return  # dispatched, check again next cycle

    # 3. Check for proposed batches (waiting for approval)
    status = api_request('GET', '/api/dispatch/status')
    if status and status.get('proposed'):
        log(f'Batch {status["proposed"]["batch_id"]} awaiting approval')
        return  # still waiting

    # 4. Propose new batch
    propose_batch(dry_run)


if __name__ == '__main__':
    main()
```

- [ ] **Step 4: Run tests**

```bash
cd ~/development/openclaw/workspace
python3 -m unittest tests.test_dispatch -v
```

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
cd ~/development/openclaw
git add workspace/dispatch.py workspace/tests/test_dispatch.py
git commit -m "feat: add dispatch orchestrator with lockfile, dry-run, SSH+tmux execution"
```

---

## Task 8: Infrastructure Setup

**Files:**
- Modify: `~/development/openclaw/scripts/workspace-push.sh`

- [ ] **Step 1: Update workspace-push.sh to include dispatch directory**

Add `dispatch/` to the rsync includes in `scripts/workspace-push.sh`. Find the existing include list and add:

```bash
--include 'dispatch/' --include 'dispatch/**'
```

Or if it uses explicit file lists, add the dispatch directory to the list of synced paths.

- [ ] **Step 2: Push workspace to VPS**

```bash
cd ~/development/openclaw
./scripts/workspace-push.sh
```

- [ ] **Step 3: Configure SSH ControlMaster on VPS for M2**

```bash
ssh jimbo "cat >> /root/.ssh/config" << 'EOF'

# M2 home station via Tailscale — connection multiplexing
Host m2
  HostName 100.121.128.3
  User marvinbarretto
  ControlMaster auto
  ControlPath /tmp/ssh-m2-%r@%h:%p
  ControlPersist 600
  ConnectTimeout 5
EOF
```

- [ ] **Step 4: Test SSH from VPS to M2**

```bash
ssh jimbo "ssh -o ConnectTimeout=5 m2 'echo M2_OK'"
```

Expected: `M2_OK`

- [ ] **Step 5: Add dispatch.py to VPS cron**

```bash
ssh jimbo "crontab -l > /tmp/crontab.bak && echo '*/5 * * * * cd /home/openclaw/.openclaw/workspace && /usr/bin/python3 dispatch.py --live >> /var/log/dispatch.log 2>&1' >> /tmp/crontab.bak && crontab /tmp/crontab.bak"
```

**Note:** Start with `--live` disabled (no `--live` flag) for the first day to monitor dry-run output. Switch to `--live` once confirmed working.

- [ ] **Step 6: Verify cron is installed**

```bash
ssh jimbo "crontab -l | grep dispatch"
```

Expected: The dispatch.py cron entry.

- [ ] **Step 7: Commit workspace-push changes**

```bash
cd ~/development/openclaw
git add scripts/workspace-push.sh
git commit -m "chore: add dispatch templates to workspace-push.sh"
```

---

## Task 9: Accountability Integration (openclaw)

**Files:**
- Modify: `~/development/openclaw/workspace/accountability-check.py`

- [ ] **Step 1: Add dispatch check function**

Add to `workspace/accountability-check.py`, after the existing check functions:

```python
def check_dispatch_today():
    """Check dispatch activity for today."""
    try:
        result = api_request('GET', '/api/dispatch/queue')
        if not result:
            return True, 'dispatch: API unreachable'

        items = result.get('items', [])
        today = datetime.date.today().isoformat()

        completed = [i for i in items if i.get('status') == 'completed' and (i.get('completed_at') or '').startswith(today)]
        failed = [i for i in items if i.get('status') == 'failed' and (i.get('completed_at') or '').startswith(today)]
        running = [i for i in items if i.get('status') == 'running']

        parts = []
        if completed:
            parts.append(f'{len(completed)} completed')
        if failed:
            parts.append(f'{len(failed)} failed')
        if running:
            parts.append(f'{len(running)} running')

        if not parts:
            return True, 'dispatch: no activity today'
        return True, f'dispatch: {", ".join(parts)}'
    except Exception as e:
        return True, f'dispatch: error ({e})'
```

- [ ] **Step 2: Wire into the main report**

Find where other checks are called (the main `run_checks()` or similar function) and add:

```python
dispatch_ok, dispatch_summary = check_dispatch_today()
parts.append(dispatch_summary)
```

- [ ] **Step 3: Commit**

```bash
cd ~/development/openclaw
git add workspace/accountability-check.py
git commit -m "feat: add dispatch activity check to accountability report"
```

---

## Task 10: End-to-End Dry Run

- [ ] **Step 1: Groom one vault task to ready state**

Pick a real vault task and set the dispatch fields via API:

```bash
# Find a high-priority task
curl -sk -H "X-API-Key: $JIMBO_API_KEY" \
  "https://167.99.206.214/api/vault/notes?sort=ai_priority&order=desc&status=active&limit=5" | python3 -m json.tool

# Pick one and update it
curl -sk -X PATCH -H "X-API-Key: $JIMBO_API_KEY" -H "Content-Type: application/json" \
  "https://167.99.206.214/api/vault/notes/NOTE_ID_HERE" \
  -d '{
    "route": "claude_code",
    "dispatch_status": "ready",
    "agent_type": "researcher",
    "definition_of_done": "A structured summary with 3+ sources comparing the options",
    "actionability": "clear"
  }'
```

- [ ] **Step 2: Run dispatch.py in dry-run mode locally**

```bash
cd ~/development/openclaw/workspace
export JIMBO_API_URL=https://167.99.206.214
export JIMBO_API_KEY=<your key>
python3 dispatch.py
```

Expected: Shows "DRY RUN" logs, proposes a batch, shows what Telegram message would be sent, shows prompt preview.

- [ ] **Step 3: Test the proposal API directly**

```bash
curl -sk -X POST -H "X-API-Key: $JIMBO_API_KEY" -H "Content-Type: application/json" \
  "https://167.99.206.214/api/dispatch/propose" \
  -d '{"batch_size": 1}'
```

Expected: Returns a batch with the groomed task, including approval URLs.

- [ ] **Step 4: Test the approval link**

Copy the `approve_url` from step 3 and open it in a browser, or curl it:

```bash
curl -sk "APPROVE_URL_HERE"
```

Expected: HTML page saying "Approved. 1 tasks approved."

- [ ] **Step 5: Verify the task is now approved**

```bash
curl -sk -H "X-API-Key: $JIMBO_API_KEY" \
  "https://167.99.206.214/api/dispatch/queue?status=approved"
```

Expected: The task appears with `status: approved`.

- [ ] **Step 6: Run dispatch.py --live with the approved task**

```bash
python3 dispatch.py --live
```

Expected: Dispatches to M2 via SSH+tmux, shows "Running: ..." in logs, sends Telegram notification.

- [ ] **Step 7: Monitor and collect results**

Wait for the agent to finish (check with `ssh m2 "cat /tmp/dispatch-NOTE_ID.signal"`), then run dispatch.py again:

```bash
python3 dispatch.py --live
```

Expected: Picks up the completed result, posts to jimbo-api, sends Telegram notification, cleans up temp files.

- [ ] **Step 8: Enable cron with --live**

Once verified:

```bash
ssh jimbo "crontab -l | sed 's/dispatch.py/dispatch.py --live/' | crontab -"
```

- [ ] **Step 9: Final commit — update CAPABILITIES.md**

Add to the Autonomy section of `CAPABILITIES.md`:

```markdown
| Autonomous dispatch | `/api/dispatch/status` | dispatch.py on VPS, Claude Code on M2. Proposes batches, Telegram approval, SSH+tmux execution. |
```

```bash
cd ~/development/openclaw
git add CAPABILITIES.md
git commit -m "docs: add dispatch system to capability catalogue"
```

---

## Dependency Order

```
Task 1 (types) → Task 2 (migration) → Task 3 (service+tests) → Task 4 (routes) → Task 5 (deploy)
                                                                                          ↓
Task 6 (templates) ──────────────────────────────────────────────────────→ Task 7 (dispatch.py)
                                                                                          ↓
                                                                         Task 8 (infra setup)
                                                                                          ↓
                                                                         Task 9 (accountability)
                                                                                          ↓
                                                                         Task 10 (e2e test)
```

Tasks 1-5 (jimbo-api) and Task 6 (templates) can be done in parallel by different agents. Tasks 7-10 depend on both tracks completing.
