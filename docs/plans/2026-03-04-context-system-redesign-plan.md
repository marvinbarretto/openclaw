# Context System Redesign — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extend context_items with structured fields (timeframe, status, category, expires_at) so all consumers read from one source of truth and Jimbo can reason about priority conflicts and expiry.

**Architecture:** Add four nullable columns to the existing context_items table in jimbo-api's inline schema. Extend existing CRUD endpoints, update the site's context editor UI with structured fields for priorities/goals, migrate sandbox scripts to read from the API exclusively.

**Tech Stack:** better-sqlite3 (jimbo-api), Hono (API routes), React/SCSS (site UI), stdlib Python (sandbox scripts)

---

### Task 1: Add structured columns to context_items schema

**Files:**
- Modify: `/Users/marvinbarretto/development/jimbo/notes-triage-api/src/db/index.ts:18-25`
- Modify: `/Users/marvinbarretto/development/jimbo/notes-triage-api/src/db/schema.sql:18-25`

**Step 1: Add columns to inline schema in db/index.ts**

In the `context_items` CREATE TABLE block (line 18-25), add four nullable columns after `sort_order`:

```sql
timeframe TEXT,
status TEXT CHECK(status IN ('active', 'paused', 'completed', 'deferred')),
category TEXT CHECK(category IN ('project', 'life-area', 'habit', 'one-off')),
expires_at TEXT
```

**Step 2: Add ALTER TABLE migration for existing databases**

After the `db.exec(SCHEMA)` call (around line 101), add migration statements. better-sqlite3 is synchronous so wrap in try/catch (ALTER TABLE fails if column exists):

```typescript
// Migration: add structured fields to context_items
const migrations = [
  'ALTER TABLE context_items ADD COLUMN timeframe TEXT',
  'ALTER TABLE context_items ADD COLUMN status TEXT',
  'ALTER TABLE context_items ADD COLUMN category TEXT',
  'ALTER TABLE context_items ADD COLUMN expires_at TEXT',
];
for (const sql of migrations) {
  try { db.exec(sql); } catch (e) { /* column already exists */ }
}
```

**Step 3: Update schema.sql to match**

Add the same four columns to the standalone schema.sql file for reference.

**Step 4: Commit**

```bash
cd /Users/marvinbarretto/development/jimbo/notes-triage-api
git add src/db/index.ts src/db/schema.sql
git commit -m "feat: add structured fields to context_items schema"
```

---

### Task 2: Update TypeScript types

**Files:**
- Modify: `/Users/marvinbarretto/development/jimbo/notes-triage-api/src/types/context.ts:20-28`
- Modify: `/Users/marvinbarretto/development/site/src/types/context.ts` (mirror)

**Step 1: Extend ContextItem type in jimbo-api**

Add to the `ContextItem` interface (line 20):

```typescript
export interface ContextItem {
  id: number;
  section_id: number;
  label: string | null;
  content: string;
  sort_order: number;
  updated_at: string;
  timeframe: string | null;
  status: 'active' | 'paused' | 'completed' | 'deferred' | null;
  category: 'project' | 'life-area' | 'habit' | 'one-off' | null;
  expires_at: string | null;
}
```

**Step 2: Mirror the same changes in the site types file**

Copy the exact same interface to `/Users/marvinbarretto/development/site/src/types/context.ts`.

**Step 3: Commit both repos**

```bash
cd /Users/marvinbarretto/development/jimbo/notes-triage-api
git add src/types/context.ts
git commit -m "feat: add structured fields to ContextItem type"

cd /Users/marvinbarretto/development/site
git add src/types/context.ts
git commit -m "feat: add structured fields to ContextItem type"
```

---

### Task 3: Update context service CRUD operations

**Files:**
- Modify: `/Users/marvinbarretto/development/jimbo/notes-triage-api/src/services/context.ts:129-165`

**Step 1: Update addItem to accept structured fields**

Modify `addItem` (line 129) to accept and insert the new fields:

```typescript
export function addItem(
  sectionId: number,
  label: string | null,
  content: string,
  timeframe?: string | null,
  status?: string | null,
  category?: string | null,
  expires_at?: string | null
) {
  const db = getDb();
  const maxOrder = db.prepare(
    'SELECT MAX(sort_order) as max FROM context_items WHERE section_id = ?'
  ).get(sectionId) as any;
  const sortOrder = (maxOrder?.max ?? -1) + 1;

  const result = db.prepare(
    `INSERT INTO context_items (section_id, label, content, sort_order, timeframe, status, category, expires_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
  ).run(sectionId, label, content, sortOrder, timeframe ?? null, status ?? null, category ?? null, expires_at ?? null);

  touchFileBySection(sectionId);
  notifyContextUpdate(getSlugBySection(sectionId));
  return result.lastInsertRowid;
}
```

**Step 2: Update updateItem to handle structured fields**

Modify `updateItem` (line 149) to accept the new fields in the updates object:

```typescript
export function updateItem(
  id: number,
  updates: {
    label?: string | null;
    content?: string;
    timeframe?: string | null;
    status?: string | null;
    category?: string | null;
    expires_at?: string | null;
  }
) {
  const db = getDb();
  const fields: string[] = [];
  const values: any[] = [];

  for (const [key, value] of Object.entries(updates)) {
    if (value !== undefined) {
      fields.push(`${key} = ?`);
      values.push(value);
    }
  }

  if (fields.length === 0) return;

  values.push(id);
  db.prepare(`UPDATE context_items SET ${fields.join(', ')} WHERE id = ?`).run(...values);

  const item = db.prepare('SELECT section_id FROM context_items WHERE id = ?').get(id) as any;
  if (item) {
    touchFileBySection(item.section_id);
    notifyContextUpdate(getSlugBySection(item.section_id));
  }
}
```

**Step 3: Add getExpiringItems function**

Add at the end of the service file:

```typescript
export function getExpiringItems(days: number) {
  const db = getDb();
  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() + days);
  const cutoffStr = cutoff.toISOString().split('T')[0];

  return db.prepare(`
    SELECT ci.*, cs.name as section_name, cf.slug as file_slug, cf.display_name as file_name
    FROM context_items ci
    JOIN context_sections cs ON ci.section_id = cs.id
    JOIN context_files cf ON cs.file_id = cf.id
    WHERE ci.expires_at IS NOT NULL
      AND ci.expires_at <= ?
      AND (ci.status IS NULL OR ci.status != 'completed')
    ORDER BY ci.expires_at ASC
  `).all(cutoffStr);
}
```

**Step 4: Commit**

```bash
cd /Users/marvinbarretto/development/jimbo/notes-triage-api
git add src/services/context.ts
git commit -m "feat: extend context service with structured fields and expiring items query"
```

---

### Task 4: Add expiring items API endpoint

**Files:**
- Modify: `/Users/marvinbarretto/development/jimbo/notes-triage-api/src/routes/context.ts`

**Step 1: Add the endpoint**

Add after the existing item routes (around line 120):

```typescript
// GET /items/expiring?days=30
context.get('/items/expiring', (c) => {
  const days = parseInt(c.req.query('days') || '30');
  if (isNaN(days) || days < 1) {
    return c.json({ error: 'days must be a positive integer' }, 400);
  }
  const items = getExpiringItems(days);
  return c.json(items);
});
```

Import `getExpiringItems` from the service file.

**Step 2: Update existing item routes to pass through structured fields**

In the `POST /sections/:id/items` handler (line 82), extract and pass the new fields:

```typescript
context.post('/sections/:id/items', async (c) => {
  const sectionId = parseInt(c.req.param('id'));
  const { label, content, timeframe, status, category, expires_at } = await c.req.json();
  const id = addItem(sectionId, label ?? null, content, timeframe, status, category, expires_at);
  return c.json({ id }, 201);
});
```

In the `PUT /items/:id` handler (line 96), the existing code already passes `await c.req.json()` as updates — verify it passes all fields through to `updateItem`. It should work without changes if `updateItem` accepts the full updates object.

**Step 3: Commit**

```bash
cd /Users/marvinbarretto/development/jimbo/notes-triage-api
git add src/routes/context.ts
git commit -m "feat: add expiring items endpoint and structured fields passthrough"
```

---

### Task 5: Seed new settings for conflict detection thresholds

**Files:**
- Modify: `/Users/marvinbarretto/development/jimbo/notes-triage-api/src/db/index.ts:38-55`

**Step 1: Add threshold settings to seed data**

Add to the existing `INSERT OR IGNORE INTO settings` block:

```sql
INSERT OR IGNORE INTO settings (key, value) VALUES ('max_active_priorities', '5');
INSERT OR IGNORE INTO settings (key, value) VALUES ('expiry_warning_days', '14');
INSERT OR IGNORE INTO settings (key, value) VALUES ('stale_priority_days', '14');
```

**Step 2: Commit**

```bash
cd /Users/marvinbarretto/development/jimbo/notes-triage-api
git add src/db/index.ts
git commit -m "feat: seed conflict detection threshold settings"
```

---

### Task 6: Build and deploy jimbo-api

**Step 1: Build**

```bash
cd /Users/marvinbarretto/development/jimbo/notes-triage-api
npm run build
```

**Step 2: Deploy to VPS**

```bash
rsync -avz dist/ jimbo:/home/openclaw/notes-triage-api/dist/
ssh jimbo 'cd /home/openclaw/notes-triage-api && cp -r dist/* . && sudo systemctl restart notes-triage-api'
```

**Step 3: Verify**

```bash
ssh jimbo 'curl -s -H "X-API-Key: $(grep API_KEY /opt/openclaw.env | cut -d= -f2)" http://localhost:3100/api/context/files/priorities' | python3 -m json.tool
```

Check that items now include `timeframe`, `status`, `category`, `expires_at` (all null for existing items).

**Step 4: Commit (tag)**

```bash
cd /Users/marvinbarretto/development/jimbo/notes-triage-api
git tag context-structured-fields-v1
```

---

### Task 7: Update site UI — extend ItemRow with structured fields

**Files:**
- Modify: `/Users/marvinbarretto/development/site/src/components/context/ItemRow.tsx`
- Modify: `/Users/marvinbarretto/development/site/src/components/context/ContextEditor.scss`

**Step 1: Add structured field inputs to ItemRow**

When in edit mode and the parent file slug is `priorities` or `goals`, render additional fields below the content textarea. The component needs to know the file slug — pass it as a new prop.

Add to ItemRow props:

```typescript
interface ItemRowProps {
  item: ContextItem;
  format: 'list' | 'prose';
  fileSlug?: string;
  onUpdate: (id: number, updates: Partial<ContextItem>) => void;
  onDelete: (id: number) => void;
}
```

In the edit form, after the content input, conditionally render:

```tsx
{(fileSlug === 'priorities' || fileSlug === 'goals') && (
  <div className="context-editor__item-meta">
    <select
      value={editStatus || ''}
      onChange={(e) => setEditStatus(e.target.value || null)}
      className="context-editor__meta-select"
    >
      <option value="">No status</option>
      <option value="active">Active</option>
      <option value="paused">Paused</option>
      <option value="completed">Completed</option>
      <option value="deferred">Deferred</option>
    </select>
    <select
      value={editCategory || ''}
      onChange={(e) => setEditCategory(e.target.value || null)}
      className="context-editor__meta-select"
    >
      <option value="">No category</option>
      <option value="project">Project</option>
      <option value="life-area">Life area</option>
      <option value="habit">Habit</option>
      <option value="one-off">One-off</option>
    </select>
    <input
      type="text"
      value={editTimeframe || ''}
      onChange={(e) => setEditTimeframe(e.target.value || null)}
      placeholder="Timeframe (e.g. '3 months')"
      className="context-editor__meta-input"
    />
    <input
      type="date"
      value={editExpiresAt || ''}
      onChange={(e) => setEditExpiresAt(e.target.value || null)}
      className="context-editor__meta-input"
    />
  </div>
)}
```

Add local state for the four fields, initialised from `item.timeframe`, etc.

Include all four fields in the save handler's `onUpdate` call.

**Step 2: Add status chips and expiry badges in view mode**

In the non-editing view, after the item content, show:

```tsx
{item.status && (
  <span className={`context-editor__status-chip context-editor__status-chip--${item.status}`}>
    {item.status}
  </span>
)}
{item.expires_at && isExpiringSoon(item.expires_at) && (
  <span className="context-editor__expiry-badge">
    expires {item.expires_at}
  </span>
)}
```

Helper function:

```typescript
function isExpiringSoon(dateStr: string, days = 14): boolean {
  const expiry = new Date(dateStr);
  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() + days);
  return expiry <= cutoff;
}
```

**Step 3: Add SCSS for structured fields**

Add to ContextEditor.scss, following existing BEM and design token patterns:

```scss
&__item-meta {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
  margin-top: var(--space-2);
}

&__meta-select,
&__meta-input {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  padding: var(--space-1) var(--space-2);
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  color: var(--color-text);
  border-radius: var(--border-radius);

  &:focus {
    outline: none;
    border-color: var(--color-accent);
  }
}

&__status-chip {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
  padding: 0 var(--space-2);
  border-radius: var(--border-radius);
  margin-left: var(--space-2);

  &--active {
    color: #22c55e;
    border: 1px solid #22c55e;
  }
  &--paused,
  &--deferred {
    color: var(--color-text-muted);
    border: 1px solid var(--color-border);
  }
  &--completed {
    color: var(--color-text-muted);
    text-decoration: line-through;
    border: 1px solid var(--color-border);
  }
}

&__expiry-badge {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  color: #f59e0b;
  border: 1px solid #f59e0b;
  border-radius: var(--border-radius);
  padding: 0 var(--space-2);
  margin-left: var(--space-2);
}
```

**Step 4: Pass fileSlug through from SectionCard to ItemRow**

In the parent component that renders SectionCard/ItemRow, ensure `fileSlug` (the active file's slug) is passed down. Check how `SectionCard` receives its props and thread `fileSlug` through.

**Step 5: Commit**

```bash
cd /Users/marvinbarretto/development/site
git add src/components/context/ItemRow.tsx src/components/context/ContextEditor.scss
git commit -m "feat: add structured fields UI for priorities and goals items"
```

---

### Task 8: Update useContextApi hook for structured fields

**Files:**
- Modify: `/Users/marvinbarretto/development/site/src/hooks/useContextApi.ts`

**Step 1: Verify addItem and updateItem pass through new fields**

Check the `addItem` function (around line 134). It should already pass the full body object to the API. If it destructures only `label` and `content`, extend it:

```typescript
const addItem = useCallback(async (
  sectionId: number,
  data: { label?: string; content: string; timeframe?: string | null; status?: string | null; category?: string | null; expires_at?: string | null }
) => {
  const res = await fetch(`${apiUrl}/api/context/sections/${sectionId}/items`, {
    method: 'POST',
    headers: headers(),
    body: JSON.stringify(data),
  });
  // ... optimistic update with all fields
}, [apiUrl]);
```

Same for `updateItem` — ensure the updates object passes all fields through.

**Step 2: Commit**

```bash
cd /Users/marvinbarretto/development/site
git add src/hooks/useContextApi.ts
git commit -m "feat: pass structured fields through context API hook"
```

---

### Task 9: Deploy site

**Step 1: Build and deploy**

Follow the existing site deployment process (Cloudflare Workers/Pages).

**Step 2: Verify**

Open the context editor at `/app/jimbo/context`, edit a priorities item, confirm the structured fields appear and save correctly.

---

### Task 10: Update context-helper.py to include structured fields

**Files:**
- Modify: `/Users/marvinbarretto/development/openclaw/workspace/context-helper.py:47-72`

**Step 1: Extend format_file output**

In the `format_file` function, after rendering each item's label/content line, append a metadata line if any structured fields are set:

```python
def format_item_meta(item):
    parts = []
    if item.get('status'):
        parts.append(item['status'])
    if item.get('category'):
        parts.append(item['category'])
    if item.get('timeframe'):
        parts.append(item['timeframe'])
    if item.get('expires_at'):
        parts.append(f"expires {item['expires_at']}")
    if parts:
        return f"  [{' | '.join(parts)}]"
    return ''
```

Call this after each item line in `format_file`:

```python
meta = format_item_meta(item)
if meta:
    lines.append(meta)
```

**Step 2: Commit**

```bash
cd /Users/marvinbarretto/development/openclaw
git add workspace/context-helper.py
git commit -m "feat: include structured fields in context-helper.py output"
```

---

### Task 11: Migrate prioritise-tasks.py to read from API

**Files:**
- Modify: `/Users/marvinbarretto/development/openclaw/workspace/prioritise-tasks.py:38-40,180-204`

**Step 1: Replace file reads with API calls**

Replace `load_context()` (lines 180-190) to use context-helper.py's approach:

```python
def load_context():
    """Load priorities and goals from context API."""
    api_url = os.environ.get('JIMBO_API_URL', '')
    api_key = os.environ.get('JIMBO_API_KEY', '')

    if not api_url or not api_key:
        # Fallback to local files
        return _load_context_files()

    context_parts = []
    for slug in ['priorities', 'goals']:
        try:
            req = urllib.request.Request(
                f'{api_url}/api/context/files/{slug}',
                headers={'X-API-Key': api_key}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                context_parts.append(_format_context(data))
        except Exception as e:
            print(f'Warning: failed to fetch {slug} from API: {e}', file=sys.stderr)
            return _load_context_files()

    return '\n\n'.join(context_parts)


def _load_context_files():
    """Fallback: read local markdown files."""
    parts = []
    for name in ['PRIORITIES.md', 'GOALS.md']:
        path = os.path.join(CONTEXT_DIR, name)
        if os.path.exists(path):
            with open(path) as f:
                parts.append(f.read())
    return '\n\n'.join(parts)


def _format_context(data):
    """Format API response as readable text."""
    lines = [f"# {data['display_name']}"]
    for section in data.get('sections', []):
        lines.append(f"\n## {section['name']}")
        for item in section.get('items', []):
            if item.get('label'):
                lines.append(f"- **{item['label']}** — {item['content']}")
            else:
                lines.append(f"- {item['content']}")
    return '\n'.join(lines)
```

**Step 2: Update context_mtime to use API updated_at**

Replace `context_mtime()` (lines 193-204) to query the API for the file's `updated_at` timestamp instead of checking file mtime:

```python
def context_mtime():
    """Get latest context update time from API (or file mtime as fallback)."""
    api_url = os.environ.get('JIMBO_API_URL', '')
    api_key = os.environ.get('JIMBO_API_KEY', '')

    if api_url and api_key:
        try:
            req = urllib.request.Request(
                f'{api_url}/api/context/files',
                headers={'X-API-Key': api_key}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                files = json.loads(resp.read())
                dates = [f['updated_at'] for f in files if f.get('updated_at')]
                if dates:
                    return max(dates)
        except Exception:
            pass

    # Fallback to file mtime
    mtimes = []
    for name in ['PRIORITIES.md', 'GOALS.md']:
        path = os.path.join(CONTEXT_DIR, name)
        if os.path.exists(path):
            mtimes.append(os.path.getmtime(path))
    return max(mtimes) if mtimes else 0
```

**Step 3: Add JIMBO_API_URL and JIMBO_API_KEY to the prioritise-tasks cron**

These env vars need passing into the docker exec call in the VPS crontab. They're already in `/opt/openclaw.env`.

Update the 04:30 cron entry to include:

```bash
-e JIMBO_API_URL=$JIMBO_API_URL \
-e JIMBO_API_KEY=$JIMBO_API_KEY \
```

**Step 4: Commit**

```bash
cd /Users/marvinbarretto/development/openclaw
git add workspace/prioritise-tasks.py
git commit -m "feat: migrate prioritise-tasks.py to read context from API"
```

---

### Task 12: Update daily-briefing skill with conflict detection

**Files:**
- Modify: `/Users/marvinbarretto/development/openclaw/skills/daily-briefing/SKILL.md`

**Step 1: Add context health check section**

After the existing context reading steps, add a new section to the skill:

```markdown
### Step N: Context health check

Review the structured fields in the priorities output. Check for:

1. **Active priority count** — if more than 5 items show `[active]`, note this in the briefing: "You have {N} active priorities — consider pausing something."
2. **Expiring soon** — any item with `expires {date}` where date is within 14 days: "Heads up: {item} expires in {N} days."
3. **Stale priorities** — any active priority that hasn't appeared in recent vault tasks or activity logs for 2+ weeks: "Haven't seen activity on {item} recently — still active?"

Read threshold settings if available:
```
python3 /workspace/settings-helper.py get max_active_priorities --default 5
python3 /workspace/settings-helper.py get expiry_warning_days --default 14
python3 /workspace/settings-helper.py get stale_priority_days --default 14
```

Present findings conversationally — this isn't a report, it's a nudge.
```

**Step 2: Commit**

```bash
cd /Users/marvinbarretto/development/openclaw
git add skills/daily-briefing/SKILL.md
git commit -m "feat: add context health check to daily briefing skill"
```

---

### Task 13: Push workspace changes and deploy

**Step 1: Push workspace to VPS**

```bash
cd /Users/marvinbarretto/development/openclaw
./scripts/workspace-push.sh
```

**Step 2: Update VPS crontab**

SSH to VPS and update the prioritise-tasks cron entry to pass API env vars.

**Step 3: Verify end-to-end**

```bash
# Test context-helper.py with structured fields
ssh jimbo 'docker exec -e JIMBO_API_URL=$JIMBO_API_URL -e JIMBO_API_KEY=$JIMBO_API_KEY $(docker ps -q --filter name=openclaw-sbx) python3 /workspace/context-helper.py priorities'

# Test prioritise-tasks.py reads from API
ssh jimbo 'docker exec -e JIMBO_API_URL=$JIMBO_API_URL -e JIMBO_API_KEY=$JIMBO_API_KEY -e GOOGLE_AI_API_KEY=$GOOGLE_AI_API_KEY $(docker ps -q --filter name=openclaw-sbx) python3 /workspace/prioritise-tasks.py --dry-run --limit 1'
```

**Step 4: Commit (tag)**

```bash
cd /Users/marvinbarretto/development/openclaw
git tag context-redesign-v1
```

---

### Task 14: Backfill existing priorities via triage session

**No code changes.** This is a manual step done via the web UI or a triage session.

Open the context editor at `/app/jimbo/context`, go to Priorities, and set status/category/timeframe/expires_at on each existing item:

- **LocalShout** — active, project, ongoing
- **OpenClaw/Jimbo** — active, project, ongoing
- **Hinge X** — active, life-area, "3 months from March 2026", expires 2026-06-04
- **MacBook M2 sale** — active, one-off, "this week"
- **YNAB/finances** — active, life-area, ongoing
- etc.

---

### Task 15: Write ADR

**Files:**
- Create: `/Users/marvinbarretto/development/openclaw/decisions/041-context-structured-fields.md`

Document: what changed, why, the structured fields model, migration approach, which consumers now read from API, what stays as markdown.

Follow template in `decisions/_template.md`.

```bash
cd /Users/marvinbarretto/development/openclaw
git add decisions/041-context-structured-fields.md
git commit -m "docs: ADR-041 — context items structured fields"
```
