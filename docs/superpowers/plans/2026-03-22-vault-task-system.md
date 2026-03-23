# Vault Task Management System — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform jimbo-api's vault_notes table into a task management system with lifecycle states, ownership, nudge tracking, subtasks, routing, and a summary dashboard endpoint.

**Architecture:** Extend the existing Hono/SQLite API — add 8 columns to vault_notes, extend the service layer with new query capabilities, add 3 new endpoints (tasks/summary, batch PATCH, subtask operations), and extend existing list/update endpoints with new filters and fields.

**Tech Stack:** TypeScript, Hono, better-sqlite3, Vitest. All work is in the jimbo-api repo at `/Users/marvinbarretto/development/jimbo/jimbo-api`.

**Spec:** `/Users/marvinbarretto/development/openclaw/docs/superpowers/specs/2026-03-21-vault-task-system-design.md`

**Scope:** This plan covers the jimbo-api database and API work only (spec Phase 1 items 1-3, 9). The Python script revisions (tasks-helper.py, prioritise-tasks.py), skill files (vault-grooming, daily-briefing, HEARTBEAT.md), and deployment of those to the VPS are a separate follow-up plan in the openclaw repo. The API must be built and deployed first — everything else consumes it.

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `src/db/index.ts` | Modify | Add 8 columns via ALTER TABLE migrations |
| `src/types/vault.ts` | Modify | Extend interfaces with new fields |
| `src/services/vault.ts` | Modify | New queries, extended filters, task summary, batch update, subtask ops |
| `src/routes/vault.ts` | Modify | New endpoints, extended query params |
| `test/vault.test.ts` | Modify | Tests for all new functionality |

No new files. All work extends existing patterns.

---

### Task 1: Database Migration — Add 8 Columns

**Files:**
- Modify: `src/db/index.ts:185-222` (migrations section)

- [ ] **Step 1: Write failing test — new columns exist after DB init**

Add to `test/vault.test.ts`:

```ts
describe('schema migrations', () => {
  it('vault_notes has task management columns', () => {
    const db = getDb();
    const columns = db.prepare("PRAGMA table_info(vault_notes)").all() as { name: string }[];
    const names = columns.map(c => c.name);
    expect(names).toContain('owner');
    expect(names).toContain('due_date');
    expect(names).toContain('blocked_by');
    expect(names).toContain('parent_id');
    expect(names).toContain('source_signal');
    expect(names).toContain('last_nudged_at');
    expect(names).toContain('nudge_count');
    expect(names).toContain('route');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/marvinbarretto/development/jimbo/jimbo-api && npm test`
Expected: FAIL — columns don't exist yet

- [ ] **Step 3: Add migrations to db/index.ts**

Add to the migrations section in `src/db/index.ts` (after existing try/catch blocks around line 222):

```ts
// Task management columns (2026-03-22)
const taskMgmtCols = [
  ["owner", "TEXT DEFAULT 'unassigned'"],
  ["due_date", "TEXT"],
  ["blocked_by", "TEXT"],
  ["parent_id", "TEXT"],
  ["source_signal", "TEXT"],
  ["last_nudged_at", "TEXT"],
  ["nudge_count", "INTEGER DEFAULT 0"],
  ["route", "TEXT DEFAULT 'unrouted'"],
];
for (const [col, type] of taskMgmtCols) {
  try { db.exec(`ALTER TABLE vault_notes ADD COLUMN ${col} ${type}`); } catch {}
}

// Indexes for task queries
try { db.exec('CREATE INDEX IF NOT EXISTS idx_vault_owner ON vault_notes(owner)'); } catch {}
try { db.exec('CREATE INDEX IF NOT EXISTS idx_vault_status_owner ON vault_notes(status, owner)'); } catch {}
try { db.exec('CREATE INDEX IF NOT EXISTS idx_vault_parent_id ON vault_notes(parent_id)'); } catch {}
try { db.exec('CREATE INDEX IF NOT EXISTS idx_vault_route ON vault_notes(status, route)'); } catch {}
try { db.exec('CREATE INDEX IF NOT EXISTS idx_vault_due_date ON vault_notes(due_date)'); } catch {}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/marvinbarretto/development/jimbo/jimbo-api && npm test`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/marvinbarretto/development/jimbo/jimbo-api
git add src/db/index.ts test/vault.test.ts
git commit -m "feat: add task management columns to vault_notes schema"
```

---

### Task 2: Extend Types — New Fields

**Files:**
- Modify: `src/types/vault.ts`

- [ ] **Step 1: Update VaultNote interface**

Add to `VaultNote` interface:

```ts
owner: string;
due_date: string | null;
blocked_by: string | null;
parent_id: string | null;
source_signal: string | null;
last_nudged_at: string | null;
nudge_count: number;
route: string;
```

- [ ] **Step 2: Update VaultNoteSummary interface**

Add the same fields to `VaultNoteSummary` (they're useful in list views):

```ts
owner: string;
due_date: string | null;
blocked_by: string | null;
parent_id: string | null;
source_signal: string | null;
last_nudged_at: string | null;
nudge_count: number;
route: string;
```

- [ ] **Step 3: Update VaultListParams interface**

Add new filter params:

```ts
owner?: string;
route?: string;
overdue?: boolean;
due_before?: string;
parent_id?: string;
has_parent?: boolean;
```

- [ ] **Step 4: Update VaultNoteUpdate interface**

Add updatable fields:

```ts
owner?: string;
due_date?: string | null;
blocked_by?: string | null;
parent_id?: string | null;
source_signal?: string | null;
last_nudged_at?: string | null;
nudge_count?: number;
route?: string;
```

- [ ] **Step 5: Update VaultNoteCreate interface**

Add fields accepted on creation:

```ts
owner?: string;
due_date?: string;
blocked_by?: string;
parent_id?: string;
source_signal?: string;
route?: string;
```

- [ ] **Step 6: Add VaultTaskSummary interface**

```ts
export interface VaultTaskSummary {
  done_today: number;
  done_this_week: number;
  new_today: number;
  inbox_count: number;
  active_count: number;
  in_progress: Record<string, number>;
  blocked: number;
  deferred: number;
  velocity_7d: number;
  velocity_30d: number;
  overdue: number;
}
```

- [ ] **Step 7: Verify existing tests still pass**

Run: `cd /Users/marvinbarretto/development/jimbo/jimbo-api && npm test`
Expected: PASS (type changes are additive, no breaking changes)

- [ ] **Step 8: Commit**

```bash
cd /Users/marvinbarretto/development/jimbo/jimbo-api
git add src/types/vault.ts
git commit -m "feat: extend vault types with task management fields"
```

---

### Task 3: Extend listNotes — New Filters

**Files:**
- Modify: `src/services/vault.ts` (listNotes function)
- Modify: `test/vault.test.ts`

- [ ] **Step 1: Write failing tests for new filters**

Add to `test/vault.test.ts`:

```ts
describe('listNotes filters — task management', () => {
  beforeEach(() => {
    const db = getDb();
    db.exec('DELETE FROM vault_notes');
  });

  it('filters by owner', () => {
    seedNote({ id: 'n1', title: 'A', owner: 'marvin' });
    seedNote({ id: 'n2', title: 'B', owner: 'jimbo' });
    seedNote({ id: 'n3', title: 'C', owner: 'unassigned' });
    const result = listNotes({ owner: 'marvin' });
    expect(result.total).toBe(1);
    expect(result.notes[0].id).toBe('n1');
  });

  it('filters by route', () => {
    seedNote({ id: 'n1', title: 'A', route: 'jimbo_vps' });
    seedNote({ id: 'n2', title: 'B', route: 'claude_code' });
    const result = listNotes({ route: 'jimbo_vps' });
    expect(result.total).toBe(1);
    expect(result.notes[0].id).toBe('n1');
  });

  it('filters overdue tasks', () => {
    seedNote({ id: 'n1', title: 'A', due_date: '2020-01-01', status: 'active' });
    seedNote({ id: 'n2', title: 'B', due_date: '2099-01-01', status: 'active' });
    seedNote({ id: 'n3', title: 'C', due_date: '2020-01-01', status: 'done' });
    const result = listNotes({ overdue: true });
    expect(result.total).toBe(1);
    expect(result.notes[0].id).toBe('n1');
  });

  it('filters by due_before', () => {
    seedNote({ id: 'n1', title: 'A', due_date: '2026-03-20', status: 'deferred' });
    seedNote({ id: 'n2', title: 'B', due_date: '2026-03-25', status: 'deferred' });
    const result = listNotes({ due_before: '2026-03-22' });
    expect(result.total).toBe(1);
    expect(result.notes[0].id).toBe('n1');
  });

  it('filters by parent_id', () => {
    seedNote({ id: 'parent', title: 'Parent' });
    seedNote({ id: 'child1', title: 'Child 1', parent_id: 'parent' });
    seedNote({ id: 'child2', title: 'Child 2', parent_id: 'parent' });
    seedNote({ id: 'other', title: 'Other' });
    const result = listNotes({ parent_id: 'parent' });
    expect(result.total).toBe(2);
  });

  it('excludes subtasks with has_parent=false', () => {
    seedNote({ id: 'parent', title: 'Parent' });
    seedNote({ id: 'child', title: 'Child', parent_id: 'parent' });
    seedNote({ id: 'top', title: 'Top Level' });
    const result = listNotes({ has_parent: false });
    expect(result.total).toBe(2);
    expect(result.notes.map(n => n.id).sort()).toEqual(['parent', 'top']);
  });

  it('supports multi-value status filter', () => {
    seedNote({ id: 'n1', title: 'A', status: 'active' });
    seedNote({ id: 'n2', title: 'B', status: 'inbox' });
    seedNote({ id: 'n3', title: 'C', status: 'done' });
    const result = listNotes({ status: 'active,inbox' });
    expect(result.total).toBe(2);
  });
});
```

Note: `seedNote` helper needs updating to accept new fields — see step 3.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/marvinbarretto/development/jimbo/jimbo-api && npm test`
Expected: FAIL — new params not handled, seedNote doesn't accept new fields

- [ ] **Step 3: Update seedNote helper to accept new fields**

Update the `seedNote` helper in `test/vault.test.ts` to include new columns in its INSERT statement:

```ts
function seedNote(overrides: Partial<{
  id: string; title: string; type: string; status: string;
  body: string; ai_priority: number; manual_priority: number;
  actionability: string; source: string; tags: string;
  owner: string; due_date: string; blocked_by: string;
  parent_id: string; source_signal: string; route: string;
  last_nudged_at: string; nudge_count: number;
  created_at: string; updated_at: string;
}>): string {
  const db = getDb();
  const id = overrides.id ?? `note_${Math.random().toString(36).slice(2, 10)}`;
  db.prepare(`INSERT INTO vault_notes (
    id, title, type, status, body, ai_priority, manual_priority,
    actionability, source, tags, owner, due_date, blocked_by,
    parent_id, source_signal, route, last_nudged_at, nudge_count,
    created_at, updated_at
  ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))`).run(
    id,
    overrides.title ?? 'Test note',
    overrides.type ?? 'task',
    overrides.status ?? 'active',
    overrides.body ?? null,
    overrides.ai_priority ?? null,
    overrides.manual_priority ?? null,
    overrides.actionability ?? null,
    overrides.source ?? null,
    overrides.tags ?? null,
    overrides.owner ?? 'unassigned',
    overrides.due_date ?? null,
    overrides.blocked_by ?? null,
    overrides.parent_id ?? null,
    overrides.source_signal ?? null,
    overrides.route ?? 'unrouted',
    overrides.last_nudged_at ?? null,
    overrides.nudge_count ?? 0,
  );
  // Apply timestamp overrides if provided (after INSERT so datetime('now') defaults work)
  if (overrides.created_at || overrides.updated_at) {
    const updates: string[] = [];
    const vals: unknown[] = [];
    if (overrides.created_at) { updates.push('created_at = ?'); vals.push(overrides.created_at); }
    if (overrides.updated_at) { updates.push('updated_at = ?'); vals.push(overrides.updated_at); }
    vals.push(id);
    db.prepare(`UPDATE vault_notes SET ${updates.join(', ')} WHERE id = ?`).run(...vals);
  }
  return id;
}
```

- [ ] **Step 4: Implement new filters in listNotes service**

In `src/services/vault.ts`, update the `listNotes` function. Add after the existing filter blocks:

```ts
if (params.owner) {
  where.push('owner = ?');
  values.push(params.owner);
}

if (params.route) {
  where.push('route = ?');
  values.push(params.route);
}

if (params.overdue) {
  where.push("due_date < date('now') AND status NOT IN ('done', 'archived', 'deferred')");
}

if (params.due_before) {
  where.push('due_date <= ?');
  values.push(params.due_before);
}

if (params.parent_id) {
  where.push('parent_id = ?');
  values.push(params.parent_id);
}

if (params.has_parent === false) {
  where.push('parent_id IS NULL');
}
```

Also update the multi-value status support. Replace the existing status filter:

```ts
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
```

Update `SUMMARY_COLUMNS` to include new fields:

```ts
const SUMMARY_COLUMNS = `id, title, type, status, ai_priority, ai_rationale, manual_priority, sort_position, actionability, source, tags, owner, due_date, blocked_by, parent_id, source_signal, last_nudged_at, nudge_count, route, created_at, updated_at, completed_at`;
```

Add `effective_priority` to the sort map. The staleness boost is `MIN(days_since_update / 15.0, 3.0)` — float division, capped at 3.0:

```ts
const STALENESS_BOOST = "MIN((julianday('now') - julianday(COALESCE(updated_at, created_at))) / 15.0, 3.0)";

const sortMap: Record<string, string> = {
  ai_priority: 'ai_priority',
  manual_priority: 'manual_priority',
  effective_priority: `COALESCE(manual_priority, ai_priority, 0) + ${STALENESS_BOOST}`,
  created_at: 'created_at',
  updated_at: 'updated_at',
};
```

Add a test for effective_priority sort (add to the filter tests in Task 3):

```ts
it('sorts by effective_priority with staleness boost', () => {
  const db = getDb();
  // High priority, recently updated
  seedNote({ id: 'fresh', title: 'Fresh', ai_priority: 8 });
  // Low priority, very stale (boost should push it up)
  seedNote({ id: 'stale', title: 'Stale', ai_priority: 5 });
  db.prepare("UPDATE vault_notes SET updated_at = datetime('now', '-60 days') WHERE id = 'stale'").run();
  // stale effective = 5 + 3.0 (capped) = 8.0
  // fresh effective = 8 + 0 = 8.0 (tie, but stale created first)

  // Even lower priority, extremely stale
  seedNote({ id: 'ancient', title: 'Ancient', ai_priority: 3 });
  db.prepare("UPDATE vault_notes SET updated_at = datetime('now', '-90 days') WHERE id = 'ancient'").run();
  // ancient effective = 3 + 3.0 (capped) = 6.0 — still lower

  const result = listNotes({ sort: 'effective_priority', order: 'desc' });
  // fresh (8.0) and stale (8.0) should be above ancient (6.0)
  expect(result.notes[result.notes.length - 1].id).toBe('ancient');
});
```

- [ ] **Step 5: Update route handler to parse new query params**

In `src/routes/vault.ts`, update the `GET /notes` handler to parse new params:

```ts
owner: c.req.query('owner') || undefined,
route: c.req.query('route') || undefined,
due_before: c.req.query('due_before') || undefined,
parent_id: c.req.query('parent_id') || undefined,
```

For multi-value status support, replace the existing `status` param parsing:

```ts
// Support both ?status=active,inbox and ?status=active&status=inbox
const statusValues = c.req.queries('status');
if (statusValues && statusValues.length > 0) {
  params.status = statusValues.join(',');
}
```

And add after the existing param parsing:

```ts
const overdue = c.req.query('overdue');
if (overdue === 'true') params.overdue = true;

const hasParent = c.req.query('has_parent');
if (hasParent === 'false') params.has_parent = false;
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /Users/marvinbarretto/development/jimbo/jimbo-api && npm test`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
cd /Users/marvinbarretto/development/jimbo/jimbo-api
git add src/services/vault.ts src/routes/vault.ts test/vault.test.ts
git commit -m "feat: extend vault list with owner, route, overdue, subtask filters"
```

---

### Task 4: Extend updateNote — New Fields + Status Transition Logic

**Files:**
- Modify: `src/services/vault.ts` (updateNote function)
- Modify: `test/vault.test.ts`

- [ ] **Step 1: Write failing tests for new update fields and status logic**

```ts
describe('updateNote — task management fields', () => {
  beforeEach(() => {
    const db = getDb();
    db.exec('DELETE FROM vault_notes');
  });

  it('updates owner', () => {
    seedNote({ id: 'n1', title: 'Task' });
    const updated = updateNote('n1', { owner: 'marvin' });
    expect(updated!.owner).toBe('marvin');
  });

  it('updates due_date', () => {
    seedNote({ id: 'n1', title: 'Task' });
    const updated = updateNote('n1', { due_date: '2026-04-01' });
    expect(updated!.due_date).toBe('2026-04-01');
  });

  it('clears due_date with null', () => {
    seedNote({ id: 'n1', title: 'Task', due_date: '2026-04-01' });
    const updated = updateNote('n1', { due_date: null });
    expect(updated!.due_date).toBeNull();
  });

  it('sets blocked_by when transitioning to blocked', () => {
    seedNote({ id: 'n1', title: 'Task', status: 'in_progress' });
    const updated = updateNote('n1', { status: 'blocked', blocked_by: 'Waiting for iOS build' });
    expect(updated!.status).toBe('blocked');
    expect(updated!.blocked_by).toBe('Waiting for iOS build');
  });

  it('clears blocked_by when leaving blocked status', () => {
    seedNote({ id: 'n1', title: 'Task', status: 'blocked', blocked_by: 'Something' });
    const updated = updateNote('n1', { status: 'in_progress' });
    expect(updated!.status).toBe('in_progress');
    expect(updated!.blocked_by).toBeNull();
  });

  it('updates route', () => {
    seedNote({ id: 'n1', title: 'Task' });
    const updated = updateNote('n1', { route: 'claude_code' });
    expect(updated!.route).toBe('claude_code');
  });

  it('updates last_nudged_at and nudge_count', () => {
    seedNote({ id: 'n1', title: 'Task' });
    const updated = updateNote('n1', { last_nudged_at: '2026-03-22T14:30:00Z', nudge_count: 1 });
    expect(updated!.last_nudged_at).toBe('2026-03-22T14:30:00Z');
    expect(updated!.nudge_count).toBe(1);
  });

  it('updates parent_id for subtask assignment', () => {
    seedNote({ id: 'parent', title: 'Parent' });
    seedNote({ id: 'child', title: 'Child' });
    const updated = updateNote('child', { parent_id: 'parent' });
    expect(updated!.parent_id).toBe('parent');
  });

  it('updates source_signal', () => {
    seedNote({ id: 'n1', title: 'Task' });
    const updated = updateNote('n1', { source_signal: 'email:abc123' });
    expect(updated!.source_signal).toBe('email:abc123');
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/marvinbarretto/development/jimbo/jimbo-api && npm test`
Expected: FAIL

- [ ] **Step 3: Extend updateNote in services/vault.ts**

Add new field handling after the existing field blocks in `updateNote`:

```ts
if (patch.owner !== undefined) { sets.push('owner = ?'); values.push(patch.owner); }
if (patch.due_date !== undefined) { sets.push('due_date = ?'); values.push(patch.due_date); }
if (patch.blocked_by !== undefined) { sets.push('blocked_by = ?'); values.push(patch.blocked_by); }
if (patch.parent_id !== undefined) { sets.push('parent_id = ?'); values.push(patch.parent_id); }
if (patch.source_signal !== undefined) { sets.push('source_signal = ?'); values.push(patch.source_signal); }
if (patch.last_nudged_at !== undefined) { sets.push('last_nudged_at = ?'); values.push(patch.last_nudged_at); }
if (patch.nudge_count !== undefined) { sets.push('nudge_count = ?'); values.push(patch.nudge_count); }
if (patch.route !== undefined) { sets.push('route = ?'); values.push(patch.route); }
```

Add blocked_by transition logic inside the existing `if (patch.status !== undefined)` block:

```ts
if (patch.status !== undefined) {
  sets.push('status = ?');
  values.push(patch.status);

  if (patch.status === 'done' && existing.status !== 'done') {
    sets.push('completed_at = datetime(\'now\')');
  } else if (existing.status === 'done' && patch.status !== 'done') {
    sets.push('completed_at = NULL');
  }

  // Clear blocked_by when leaving blocked status
  if (existing.status === 'blocked' && patch.status !== 'blocked' && patch.blocked_by === undefined) {
    sets.push('blocked_by = NULL');
  }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/marvinbarretto/development/jimbo/jimbo-api && npm test`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/marvinbarretto/development/jimbo/jimbo-api
git add src/services/vault.ts test/vault.test.ts
git commit -m "feat: extend vault update with task management fields and status logic"
```

---

### Task 5: Extend createNote — Accept New Fields

**Files:**
- Modify: `src/services/vault.ts` (createNote function)
- Modify: `test/vault.test.ts`

- [ ] **Step 1: Write failing tests**

```ts
describe('createNote — task management fields', () => {
  beforeEach(() => {
    const db = getDb();
    db.exec('DELETE FROM vault_notes');
  });

  it('creates note with owner', () => {
    const note = createNote({ title: 'Task', owner: 'jimbo' });
    expect(note.owner).toBe('jimbo');
  });

  it('defaults owner to unassigned', () => {
    const note = createNote({ title: 'Task' });
    expect(note.owner).toBe('unassigned');
  });

  it('creates note with due_date and source_signal', () => {
    const note = createNote({ title: 'Task', due_date: '2026-04-01', source_signal: 'google-tasks:abc' });
    expect(note.due_date).toBe('2026-04-01');
    expect(note.source_signal).toBe('google-tasks:abc');
  });

  it('creates subtask with parent_id', () => {
    const parent = createNote({ title: 'Parent' });
    const child = createNote({ title: 'Child', parent_id: parent.id });
    expect(child.parent_id).toBe(parent.id);
  });

  it('creates note with route', () => {
    const note = createNote({ title: 'Task', route: 'jimbo_vps' });
    expect(note.route).toBe('jimbo_vps');
  });

  it('defaults route to unrouted', () => {
    const note = createNote({ title: 'Task' });
    expect(note.route).toBe('unrouted');
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/marvinbarretto/development/jimbo/jimbo-api && npm test`
Expected: FAIL

- [ ] **Step 3: Extend createNote in services/vault.ts**

Update the INSERT statement to include new columns:

```ts
export function createNote(input: VaultNoteCreate): VaultNote {
  const db = getDb();
  const id = generateId();

  db.prepare(
    `INSERT INTO vault_notes (id, title, body, type, status, source, tags, manual_priority, actionability, owner, due_date, blocked_by, parent_id, source_signal, route, created_at, updated_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))`
  ).run(
    id,
    input.title,
    input.body ?? null,
    input.type ?? 'task',
    input.status ?? 'active',
    input.source ?? null,
    input.tags ?? null,
    input.manual_priority ?? null,
    input.actionability ?? null,
    input.owner ?? 'unassigned',
    input.due_date ?? null,
    input.blocked_by ?? null,
    input.parent_id ?? null,
    input.source_signal ?? null,
    input.route ?? 'unrouted',
  );

  return db.prepare('SELECT * FROM vault_notes WHERE id = ?').get(id) as VaultNote;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/marvinbarretto/development/jimbo/jimbo-api && npm test`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/marvinbarretto/development/jimbo/jimbo-api
git add src/services/vault.ts test/vault.test.ts
git commit -m "feat: extend vault create with task management fields"
```

---

### Task 6: Task Summary Endpoint

**Files:**
- Modify: `src/services/vault.ts` (add getTaskSummary function)
- Modify: `src/routes/vault.ts` (add GET /tasks/summary route)
- Modify: `test/vault.test.ts`

- [ ] **Step 1: Write failing tests**

```ts
describe('getTaskSummary', () => {
  beforeEach(() => {
    const db = getDb();
    db.exec('DELETE FROM vault_notes');
  });

  it('returns zeros when empty', () => {
    const summary = getTaskSummary();
    expect(summary.done_today).toBe(0);
    expect(summary.inbox_count).toBe(0);
    expect(summary.velocity_7d).toBe(0);
  });

  it('counts done_today', () => {
    seedNote({ id: 'n1', title: 'A', status: 'done' });
    // Manually set completed_at to today
    const db = getDb();
    db.prepare("UPDATE vault_notes SET completed_at = datetime('now') WHERE id = 'n1'").run();
    const summary = getTaskSummary();
    expect(summary.done_today).toBe(1);
  });

  it('counts inbox and active separately', () => {
    seedNote({ id: 'n1', title: 'A', status: 'inbox' });
    seedNote({ id: 'n2', title: 'B', status: 'inbox' });
    seedNote({ id: 'n3', title: 'C', status: 'active' });
    const summary = getTaskSummary();
    expect(summary.inbox_count).toBe(2);
    expect(summary.active_count).toBe(1);
  });

  it('groups in_progress by owner', () => {
    seedNote({ id: 'n1', title: 'A', status: 'in_progress', owner: 'marvin' });
    seedNote({ id: 'n2', title: 'B', status: 'in_progress', owner: 'marvin' });
    seedNote({ id: 'n3', title: 'C', status: 'in_progress', owner: 'jimbo' });
    const summary = getTaskSummary();
    expect(summary.in_progress).toEqual({ marvin: 2, jimbo: 1 });
  });

  it('counts blocked and deferred', () => {
    seedNote({ id: 'n1', title: 'A', status: 'blocked', blocked_by: 'X' });
    seedNote({ id: 'n2', title: 'B', status: 'deferred' });
    seedNote({ id: 'n3', title: 'C', status: 'deferred' });
    const summary = getTaskSummary();
    expect(summary.blocked).toBe(1);
    expect(summary.deferred).toBe(2);
  });

  it('counts overdue tasks', () => {
    seedNote({ id: 'n1', title: 'A', status: 'active', due_date: '2020-01-01' });
    seedNote({ id: 'n2', title: 'B', status: 'active', due_date: '2099-01-01' });
    seedNote({ id: 'n3', title: 'C', status: 'done', due_date: '2020-01-01' });
    const summary = getTaskSummary();
    expect(summary.overdue).toBe(1);
  });

  it('calculates velocity', () => {
    const db = getDb();
    // Create 7 done tasks completed in last 7 days
    for (let i = 0; i < 7; i++) {
      seedNote({ id: `done_${i}`, title: `Done ${i}`, status: 'done' });
      db.prepare(`UPDATE vault_notes SET completed_at = datetime('now', '-${i} days') WHERE id = 'done_${i}'`).run();
    }
    const summary = getTaskSummary();
    expect(summary.velocity_7d).toBe(1);
    expect(summary.done_this_week).toBe(7);
  });

  it('counts new_today based on created_at', () => {
    seedNote({ id: 'n1', title: 'New today' });
    // created_at is set to now by seedNote
    const summary = getTaskSummary();
    expect(summary.new_today).toBeGreaterThanOrEqual(1);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/marvinbarretto/development/jimbo/jimbo-api && npm test`
Expected: FAIL — getTaskSummary doesn't exist

- [ ] **Step 3: Implement getTaskSummary in services/vault.ts**

```ts
export function getTaskSummary(): VaultTaskSummary {
  const db = getDb();

  const doneToday = (db.prepare(
    "SELECT COUNT(*) as count FROM vault_notes WHERE status = 'done' AND date(completed_at) = date('now')"
  ).get() as { count: number }).count;

  const doneThisWeek = (db.prepare(
    "SELECT COUNT(*) as count FROM vault_notes WHERE status = 'done' AND completed_at >= datetime('now', '-7 days')"
  ).get() as { count: number }).count;

  const done30d = (db.prepare(
    "SELECT COUNT(*) as count FROM vault_notes WHERE status = 'done' AND completed_at >= datetime('now', '-30 days')"
  ).get() as { count: number }).count;

  const newToday = (db.prepare(
    "SELECT COUNT(*) as count FROM vault_notes WHERE date(created_at) = date('now')"
  ).get() as { count: number }).count;

  const inboxCount = (db.prepare(
    "SELECT COUNT(*) as count FROM vault_notes WHERE status = 'inbox'"
  ).get() as { count: number }).count;

  const activeCount = (db.prepare(
    "SELECT COUNT(*) as count FROM vault_notes WHERE status = 'active'"
  ).get() as { count: number }).count;

  const inProgressRows = db.prepare(
    "SELECT owner, COUNT(*) as count FROM vault_notes WHERE status = 'in_progress' GROUP BY owner"
  ).all() as { owner: string; count: number }[];
  const in_progress: Record<string, number> = {};
  for (const row of inProgressRows) {
    in_progress[row.owner] = row.count;
  }

  const blocked = (db.prepare(
    "SELECT COUNT(*) as count FROM vault_notes WHERE status = 'blocked'"
  ).get() as { count: number }).count;

  const deferred = (db.prepare(
    "SELECT COUNT(*) as count FROM vault_notes WHERE status = 'deferred'"
  ).get() as { count: number }).count;

  const overdue = (db.prepare(
    "SELECT COUNT(*) as count FROM vault_notes WHERE due_date < date('now') AND status NOT IN ('done', 'archived', 'deferred')"
  ).get() as { count: number }).count;

  return {
    done_today: doneToday,
    done_this_week: doneThisWeek,
    new_today: newToday,
    inbox_count: inboxCount,
    active_count: activeCount,
    in_progress,
    blocked,
    deferred,
    velocity_7d: Math.round((doneThisWeek / 7) * 100) / 100,
    velocity_30d: Math.round((done30d / 30) * 100) / 100,
    overdue,
  };
}
```

- [ ] **Step 4: Add route handler**

In `src/routes/vault.ts`, add before the `/notes` routes (so `/tasks/summary` doesn't collide with `/notes/:id`):

```ts
vault.get('/tasks/summary', (c) => {
  return c.json(getTaskSummary());
});
```

Update import:
```ts
import { listNotes, getNote, createNote, updateNote, getStats, getTaskSummary } from '../services/vault.js';
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/marvinbarretto/development/jimbo/jimbo-api && npm test`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/marvinbarretto/development/jimbo/jimbo-api
git add src/services/vault.ts src/routes/vault.ts test/vault.test.ts
git commit -m "feat: add task summary endpoint for status dashboard"
```

---

### Task 7: Batch Update Endpoint

**Files:**
- Modify: `src/services/vault.ts` (add batchUpdateNotes function)
- Modify: `src/routes/vault.ts` (add PATCH /notes/batch route)
- Modify: `test/vault.test.ts`

- [ ] **Step 1: Write failing tests**

```ts
describe('batchUpdateNotes', () => {
  beforeEach(() => {
    const db = getDb();
    db.exec('DELETE FROM vault_notes');
  });

  it('updates multiple notes at once', () => {
    seedNote({ id: 'n1', title: 'A', status: 'inbox' });
    seedNote({ id: 'n2', title: 'B', status: 'inbox' });
    seedNote({ id: 'n3', title: 'C', status: 'active' });
    const results = batchUpdateNotes(['n1', 'n2'], { status: 'archived' });
    expect(results.updated).toBe(2);
    expect(results.errors).toEqual([]);
    expect(getNote('n1')!.status).toBe('archived');
    expect(getNote('n2')!.status).toBe('archived');
    expect(getNote('n3')!.status).toBe('active');
  });

  it('reports errors for missing notes', () => {
    seedNote({ id: 'n1', title: 'A' });
    const results = batchUpdateNotes(['n1', 'missing'], { status: 'done' });
    expect(results.updated).toBe(1);
    expect(results.errors).toEqual([{ id: 'missing', error: 'Note not found' }]);
  });

  it('applies status transition logic per item', () => {
    seedNote({ id: 'n1', title: 'A', status: 'active' });
    const results = batchUpdateNotes(['n1'], { status: 'done' });
    expect(results.updated).toBe(1);
    expect(getNote('n1')!.completed_at).not.toBeNull();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/marvinbarretto/development/jimbo/jimbo-api && npm test`
Expected: FAIL

- [ ] **Step 3: Implement batchUpdateNotes**

In `src/services/vault.ts`:

```ts
export function batchUpdateNotes(ids: string[], patch: VaultNoteUpdate): { updated: number; errors: { id: string; error: string }[] } {
  const db = getDb();
  const errors: { id: string; error: string }[] = [];
  let updated = 0;

  const run = db.transaction(() => {
    for (const id of ids) {
      const result = updateNote(id, patch);
      if (result === null) {
        errors.push({ id, error: 'Note not found' });
      } else {
        updated++;
      }
    }
  });
  run();

  return { updated, errors };
}
```

- [ ] **Step 4: Add route handler**

In `src/routes/vault.ts`:

```ts
// IMPORTANT: Register BEFORE vault.patch('/notes/:id', ...) to avoid :id matching "batch"
vault.patch('/notes/batch', async (c) => {
  const body = await c.req.json();
  if (!body.ids || !Array.isArray(body.ids) || !body.patch) {
    return c.json({ error: 'ids (array) and patch (object) are required' }, 400);
  }
  const result = batchUpdateNotes(body.ids, body.patch);
  return c.json(result);
});
```

Update import to include `batchUpdateNotes`.

**Route ordering is critical.** Insert this handler ABOVE the existing `vault.patch('/notes/:id', ...)` line in the file. Task 9 will verify the final ordering.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/marvinbarretto/development/jimbo/jimbo-api && npm test`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/marvinbarretto/development/jimbo/jimbo-api
git add src/services/vault.ts src/routes/vault.ts test/vault.test.ts
git commit -m "feat: add batch update endpoint for grooming sessions"
```

---

### Task 8: Subtask Operations

**Files:**
- Modify: `src/services/vault.ts` (add getSubtasks function)
- Modify: `src/routes/vault.ts` (add subtask routes)
- Modify: `test/vault.test.ts`

- [ ] **Step 1: Write failing tests**

```ts
describe('subtask operations', () => {
  beforeEach(() => {
    const db = getDb();
    db.exec('DELETE FROM vault_notes');
  });

  it('getSubtasks returns children ordered by sort_position', () => {
    seedNote({ id: 'parent', title: 'Parent' });
    seedNote({ id: 'c1', title: 'Child 1', parent_id: 'parent' });
    seedNote({ id: 'c2', title: 'Child 2', parent_id: 'parent' });
    const db = getDb();
    db.prepare("UPDATE vault_notes SET sort_position = 2 WHERE id = 'c1'").run();
    db.prepare("UPDATE vault_notes SET sort_position = 1 WHERE id = 'c2'").run();
    const subtasks = getSubtasks('parent');
    expect(subtasks).toHaveLength(2);
    expect(subtasks[0].id).toBe('c2');
    expect(subtasks[1].id).toBe('c1');
  });

  it('getSubtasks returns empty array for note with no children', () => {
    seedNote({ id: 'lonely', title: 'No kids' });
    const subtasks = getSubtasks('lonely');
    expect(subtasks).toEqual([]);
  });

  it('POST /notes/:id/subtasks creates child with parent_id set', () => {
    const parent = createNote({ title: 'Parent task' });
    const child = createNote({ title: 'Subtask 1', parent_id: parent.id });
    expect(child.parent_id).toBe(parent.id);
    const subtasks = getSubtasks(parent.id);
    expect(subtasks).toHaveLength(1);
    expect(subtasks[0].title).toBe('Subtask 1');
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/marvinbarretto/development/jimbo/jimbo-api && npm test`
Expected: FAIL — getSubtasks doesn't exist

- [ ] **Step 3: Implement getSubtasks**

In `src/services/vault.ts`:

```ts
export function getSubtasks(parentId: string): VaultNoteSummary[] {
  const db = getDb();
  return db.prepare(
    `SELECT ${SUMMARY_COLUMNS} FROM vault_notes WHERE parent_id = ? ORDER BY sort_position ASC NULLS LAST, created_at ASC`
  ).all(parentId) as VaultNoteSummary[];
}
```

- [ ] **Step 4: Add route handlers**

In `src/routes/vault.ts`:

```ts
vault.get('/notes/:id/subtasks', (c) => {
  const note = getNote(c.req.param('id'));
  if (!note) {
    return c.json({ error: 'Note not found' }, 404);
  }
  return c.json(getSubtasks(c.req.param('id')));
});

vault.post('/notes/:id/subtasks', async (c) => {
  const parentId = c.req.param('id');
  const parent = getNote(parentId);
  if (!parent) {
    return c.json({ error: 'Parent note not found' }, 404);
  }
  const body = await c.req.json();
  if (!body.title) {
    return c.json({ error: 'title is required' }, 400);
  }
  const note = createNote({ ...body, parent_id: parentId });
  return c.json(note, 201);
});
```

Update import to include `getSubtasks`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/marvinbarretto/development/jimbo/jimbo-api && npm test`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/marvinbarretto/development/jimbo/jimbo-api
git add src/services/vault.ts src/routes/vault.ts test/vault.test.ts
git commit -m "feat: add subtask operations — list and create children"
```

---

### Task 9: Route Ordering & Integration Test

**Files:**
- Modify: `src/routes/vault.ts` (ensure route ordering is correct)
- Modify: `test/vault.test.ts`

- [ ] **Step 1: Verify route registration order**

In `src/routes/vault.ts`, routes must be ordered to avoid path conflicts. Ensure:

```ts
// Static paths first
vault.get('/tasks/summary', ...);
vault.get('/stats', ...);
vault.post('/ingest', ...);

// Batch before parameterized
vault.patch('/notes/batch', ...);

// Collection routes
vault.get('/notes', ...);
vault.post('/notes', ...);

// Parameterized routes last
vault.get('/notes/:id', ...);
vault.patch('/notes/:id', ...);
vault.get('/notes/:id/subtasks', ...);
vault.post('/notes/:id/subtasks', ...);
```

- [ ] **Step 2: Write integration test for full task lifecycle**

```ts
describe('full task lifecycle', () => {
  beforeEach(() => {
    const db = getDb();
    db.exec('DELETE FROM vault_notes');
  });

  it('inbox → active → in_progress → done with subtasks', () => {
    // Create parent task (simulating Google Tasks intake)
    const parent = createNote({
      title: 'Fix iOS build and ship',
      status: 'inbox',
      source: 'google-tasks',
      source_signal: 'google-tasks:abc123',
    });
    expect(parent.status).toBe('inbox');
    expect(parent.owner).toBe('unassigned');

    // Groom: activate and break down
    const updated = updateNote(parent.id, { status: 'active' });
    expect(updated!.status).toBe('active');

    // Create subtasks
    const sub1 = createNote({ title: 'Fix build errors', parent_id: parent.id, status: 'active' });
    const sub2 = createNote({ title: 'Ship to App Store', parent_id: parent.id, status: 'active' });
    expect(getSubtasks(parent.id)).toHaveLength(2);

    // Assign parent to Marvin
    updateNote(parent.id, { status: 'in_progress', owner: 'marvin' });

    // Complete subtask 1
    updateNote(sub1.id, { status: 'done' });
    expect(getNote(sub1.id)!.completed_at).not.toBeNull();

    // Block subtask 2
    updateNote(sub2.id, { status: 'blocked', blocked_by: 'Waiting for Apple review' });

    // Check summary reflects state
    const summary = getTaskSummary();
    expect(summary.done_today).toBeGreaterThanOrEqual(1);
    expect(summary.blocked).toBe(1);
    expect(summary.in_progress.marvin).toBe(1);

    // Unblock and complete
    updateNote(sub2.id, { status: 'in_progress' });
    expect(getNote(sub2.id)!.blocked_by).toBeNull();
    updateNote(sub2.id, { status: 'done' });

    // Complete parent
    updateNote(parent.id, { status: 'done' });
    expect(getNote(parent.id)!.completed_at).not.toBeNull();
  });
});
```

- [ ] **Step 3: Run all tests**

Run: `cd /Users/marvinbarretto/development/jimbo/jimbo-api && npm test`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
cd /Users/marvinbarretto/development/jimbo/jimbo-api
git add src/routes/vault.ts test/vault.test.ts
git commit -m "feat: verify route ordering and add lifecycle integration test"
```

---

### Task 10: Build, Deploy, Verify

**Files:**
- No code changes — build and deploy

- [ ] **Step 1: Run full test suite**

Run: `cd /Users/marvinbarretto/development/jimbo/jimbo-api && npm test`
Expected: ALL PASS

- [ ] **Step 2: Build**

Run: `cd /Users/marvinbarretto/development/jimbo/jimbo-api && npm run build`
Expected: Clean compilation, no errors

- [ ] **Step 3: Deploy to VPS**

```bash
cd /Users/marvinbarretto/development/jimbo/jimbo-api
git push
ssh jimbo 'cd /home/openclaw/jimbo-api && git pull && npm run build'
sudo ssh jimbo 'systemctl restart jimbo-api'
```

- [ ] **Step 4: Verify migration ran (columns exist)**

```bash
KEY=$(cat <<< "$JIMBO_API_KEY") && curl -s -H "X-API-Key: ${KEY}" https://167.99.206.214/api/vault/tasks/summary | python3 -m json.tool
```

Expected: JSON response with all summary fields, mostly zeros.

- [ ] **Step 5: Test create with new fields**

```bash
KEY=$(cat <<< "$JIMBO_API_KEY") && curl -s -X POST -H "X-API-Key: ${KEY}" -H "Content-Type: application/json" \
  -d '{"title":"Test task lifecycle","status":"inbox","source_signal":"test","owner":"unassigned"}' \
  https://167.99.206.214/api/vault/notes | python3 -m json.tool
```

Expected: Created note with owner, route, and all new fields populated.

- [ ] **Step 6: Test status transition**

Using the ID from step 5:

```bash
KEY=$(cat <<< "$JIMBO_API_KEY") && curl -s -X PATCH -H "X-API-Key: ${KEY}" -H "Content-Type: application/json" \
  -d '{"status":"done"}' \
  https://167.99.206.214/api/vault/notes/<ID> | python3 -m json.tool
```

Expected: status=done, completed_at populated.

- [ ] **Step 7: Verify summary reflects changes**

```bash
KEY=$(cat <<< "$JIMBO_API_KEY") && curl -s -H "X-API-Key: ${KEY}" https://167.99.206.214/api/vault/tasks/summary | python3 -m json.tool
```

Expected: done_today >= 1

- [ ] **Step 8: Clean up test note**

```bash
KEY=$(cat <<< "$JIMBO_API_KEY") && curl -s -X PATCH -H "X-API-Key: ${KEY}" -H "Content-Type: application/json" \
  -d '{"status":"archived"}' \
  https://167.99.206.214/api/vault/notes/<ID>
```

- [ ] **Step 9: Commit any final changes and tag**

```bash
cd /Users/marvinbarretto/development/jimbo/jimbo-api
git tag v0.2.0-task-system
```
