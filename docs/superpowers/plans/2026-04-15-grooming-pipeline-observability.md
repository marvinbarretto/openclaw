# Grooming Pipeline Observability — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the grooming pipeline observable — track when analysis starts, how long it takes, whether it completes, and surface this in the dashboard UI and Telegram alerts.

**Architecture:** Add `grooming_started_at` timestamp to vault_notes (jimbo-api), set it when `prioritise-tasks.py` marks items for analysis, auto-set it server-side when `grooming_status` transitions to `analysis_pending`. Add Telegram reporting to `decompose-epic.py`. Update the site dashboard to show elapsed time and grooming events in the timeline.

**Tech Stack:** SQLite (jimbo-api), Python stdlib (workspace scripts), React/TypeScript (site dashboard)

---

### Task 1: Add `grooming_started_at` column to jimbo-api

**Files:**
- Modify: `/Users/marvinbarretto/development/jimbo/jimbo-api/src/db/index.ts:428-448` (migration section)
- Modify: `/Users/marvinbarretto/development/jimbo/jimbo-api/src/services/vault.ts:43` (SUMMARY_COLUMNS)
- Modify: `/Users/marvinbarretto/development/jimbo/jimbo-api/src/services/vault.ts:173-255` (updateNote)
- Modify: `/Users/marvinbarretto/development/jimbo/jimbo-api/src/schemas/vault.ts:5-46` (VaultNoteSchema)

- [ ] **Step 1: Add column migration**

In `src/db/index.ts`, after the `epicLifecycleCols` migration block (after line 448), add:

```typescript
    // Grooming observability (2026-04-15)
    try { db.exec(`ALTER TABLE vault_notes ADD COLUMN grooming_started_at TEXT`); } catch {}
    // Backfill: existing analysis_pending notes get grooming_started_at from updated_at
    try {
      db.exec(`UPDATE vault_notes SET grooming_started_at = COALESCE(updated_at, created_at) WHERE grooming_status IN ('analysis_pending', 'decomposition_proposed', 'awaiting_review', 'revision_requested') AND grooming_started_at IS NULL`);
    } catch {}
```

- [ ] **Step 2: Add to SUMMARY_COLUMNS**

In `src/services/vault.ts:43`, add `grooming_started_at` to the SUMMARY_COLUMNS string, after `blocked_at`:

```typescript
const SUMMARY_COLUMNS = `id, seq, title, type, status, ai_priority, ai_rationale, manual_priority, sort_position, actionability, source, tags, assigned_to, due_date, blocked_by, parent_id, source_signal, last_nudged_at, nudge_count, route, dispatch_status, agent_type, acceptance_criteria, ready, suggested_agent_type, suggested_route, suggested_ac, grooming_status, required_skills, suggested_skills, executor, is_epic, epic_started_at, blocked_reason, blocked_at, grooming_started_at, created_at, updated_at, completed_at`;
```

- [ ] **Step 3: Auto-set grooming_started_at in updateNote**

In `src/services/vault.ts`, after the `grooming_status` update line (line 203), add server-side timestamp logic:

```typescript
  if (patch.grooming_status !== undefined) {
    sets.push('grooming_status = ?'); values.push(patch.grooming_status);
    // Set grooming_started_at when entering the pipeline
    if (patch.grooming_status === 'analysis_pending' && !existing.grooming_started_at) {
      sets.push("grooming_started_at = datetime('now')");
    }
    // Clear grooming_started_at when grooming completes or resets
    if (patch.grooming_status === 'ready' || patch.grooming_status === 'ungroomed') {
      sets.push('grooming_started_at = NULL');
    }
  }
```

Note: This replaces the existing single line `if (patch.grooming_status !== undefined) { sets.push('grooming_status = ?'); values.push(patch.grooming_status); }`.

- [ ] **Step 4: Add to Zod schema**

In `src/schemas/vault.ts`, add to `VaultNoteSchema` (after `blocked_at` line 45):

```typescript
  grooming_started_at: z.string().nullable().default(null),
```

- [ ] **Step 5: Build and verify**

```bash
cd /Users/marvinbarretto/development/jimbo/jimbo-api
npm run build
```

Expected: Clean build, no type errors.

- [ ] **Step 6: Commit**

```bash
cd /Users/marvinbarretto/development/jimbo/jimbo-api
git add src/db/index.ts src/services/vault.ts src/schemas/vault.ts
git commit -m "feat: add grooming_started_at timestamp for pipeline observability"
```

---

### Task 2: Add Telegram reporting to decompose-epic.py

**Files:**
- Modify: `/Users/marvinbarretto/development/openclaw/workspace/decompose-epic.py`

- [ ] **Step 1: Add Telegram reporting function**

After the existing imports (line 18), add the Telegram import and reporting:

```python
try:
    from alert import send_telegram
except ImportError:
    send_telegram = None
```

- [ ] **Step 2: Add summary report to main()**

Replace the `main()` function (lines 177-218) with one that tracks results and sends a Telegram summary:

```python
def main():
    parser = argparse.ArgumentParser(description="Decompose epics into sub-tasks")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    epics = fetch_pending_epics(args.limit)
    if not epics:
        print("No epics pending decomposition.")
        return

    print(f"Found {len(epics)} epics to decompose.\n")

    succeeded = []
    failed = []

    for task in epics:
        title = task.get("title", "untitled")
        task_id = task["id"]
        seq = task.get("seq", "?")
        print(f"Decomposing: #{seq} {title} ({task_id})")

        try:
            proposal = decompose_task(task)
            sub_count = len(proposal.get("sub_tasks", []))
            print(f"  → {sub_count} sub-tasks proposed")
            print(f"  → Analysis: {proposal.get('analysis', '')[:100]}...")

            if args.dry_run:
                print(f"  [dry-run] Would create proposal with {sub_count} sub-tasks")
                print(json.dumps(proposal, indent=2))
                succeeded.append((seq, title, sub_count))
                continue

            result = create_proposal(task_id, proposal)
            if result:
                update_grooming_status(task_id, "decomposition_proposed")
                print(f"  ✓ Proposal created (id: {result.get('id')})")
                succeeded.append((seq, title, sub_count))
            else:
                print(f"  ✗ Failed to create proposal")
                failed.append((seq, title, "API write failed"))

        except json.JSONDecodeError as e:
            print(f"  ✗ LLM returned invalid JSON: {e}")
            failed.append((seq, title, f"invalid JSON: {e}"))
        except Exception as e:
            print(f"  ✗ Error: {e}")
            failed.append((seq, title, str(e)))

        print()

    # Summary report
    prefix = "[dry-run] " if args.dry_run else ""
    lines = [f"[Epic Decomposition] {prefix}{len(succeeded)}/{len(epics)} processed"]
    if succeeded:
        for seq, title, count in succeeded:
            lines.append(f"  ✓ #{seq} {title} → {count} sub-tasks")
    if failed:
        lines.append(f"  ✗ {len(failed)} failed:")
        for seq, title, reason in failed:
            lines.append(f"    #{seq} {title}: {reason}")

    summary = "\n".join(lines)
    print(f"\n{summary}")

    if not args.dry_run and send_telegram and (succeeded or failed):
        send_telegram(summary)
```

- [ ] **Step 3: Verify script runs**

```bash
cd /Users/marvinbarretto/development/openclaw/workspace
python3 decompose-epic.py --dry-run --limit 1
```

Expected: Script runs, shows dry-run output (or "No epics pending decomposition.").

- [ ] **Step 4: Commit**

```bash
cd /Users/marvinbarretto/development/openclaw
git add workspace/decompose-epic.py
git commit -m "feat: add Telegram reporting to decompose-epic.py"
```

---

### Task 3: Set grooming_started_at in prioritise-tasks.py

**Files:**
- Modify: `/Users/marvinbarretto/development/openclaw/workspace/prioritise-tasks.py:846-848`

- [ ] **Step 1: Add grooming_started_at to the epic patch**

In `prioritise-tasks.py`, find the block at ~line 846-848 where epics get `grooming_status = "analysis_pending"`. Add the timestamp:

```python
                if is_epic:
                    patch["actionability"] = "needs-breakdown"
                    patch["grooming_status"] = "analysis_pending"
                    patch["grooming_started_at"] = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                    patch["suggested_route"] = "marvin"
                    # Don't set skills/executor for epics
                    s_skills = None
                    s_executor = None
                    s_agent = None
```

Note: `datetime` is already imported at line 26.

- [ ] **Step 2: Commit**

```bash
cd /Users/marvinbarretto/development/openclaw
git add workspace/prioritise-tasks.py
git commit -m "feat: set grooming_started_at when marking epics for analysis"
```

---

### Task 4: Update site VaultNote type and grooming panel

**Files:**
- Modify: `/Users/marvinbarretto/development/site/src/types/vault.ts:30` (add field)
- Modify: `/Users/marvinbarretto/development/site/src/admin-app/views/vault/VaultView.tsx:100-127` (grooming panel data)
- Modify: `/Users/marvinbarretto/development/site/src/admin-app/views/vault/VaultView.tsx:232-248` (grooming panel render)

- [ ] **Step 1: Add grooming_started_at to VaultNote type**

In `src/types/vault.ts`, after `blocked_at` (line 30), add:

```typescript
  grooming_started_at: string | null;
```

- [ ] **Step 2: Expand grooming panel data to include timestamps**

In `VaultView.tsx`, change the `groomingNotes` state type and the fetch to include `updated_at` and `grooming_started_at` (line 100):

```typescript
  const [groomingNotes, setGroomingNotes] = useState<Record<string, { id: string; seq: number; title: string; grooming_started_at: string | null; updated_at: string | null }[]>>({});
```

Update the fetch loop (lines 108-123) to capture these fields:

```typescript
      const byStatus: Record<string, { id: string; seq: number; title: string; grooming_started_at: string | null; updated_at: string | null }[]> = {};
```

And the items push (line 117):

```typescript
            items.push({ id: n.id, seq: n.seq, title: n.title, grooming_started_at: n.grooming_started_at ?? null, updated_at: n.updated_at ?? null });
```

- [ ] **Step 3: Show elapsed time in grooming panel**

Replace the grooming note rendering (lines 237-245) with timing info:

```tsx
              {notes.map(n => {
                const since = n.grooming_started_at || n.updated_at;
                return (
                  <div
                    key={n.id}
                    className="db-grooming-note"
                    style={{ fontSize: 11, padding: '2px 0 2px 12px', cursor: 'pointer', color: 'var(--c-text)', display: 'flex', justifyContent: 'space-between' }}
                    onClick={(e) => { e.preventDefault(); setSelectedNoteId(n.id); }}
                  >
                    <span>
                      <span className="db-muted">#{n.seq}</span>{' '}{n.title}
                    </span>
                    {since && (
                      <span className="db-muted" style={{ fontSize: 10, whiteSpace: 'nowrap', marginLeft: 8 }}>
                        {timeAgo(since)}
                      </span>
                    )}
                  </div>
                );
              })}
```

Add the `timeAgo` import at the top of `VaultView.tsx` if not already present:

```typescript
import { timeAgo } from '@/admin-app/dashboard/formatters';
```

- [ ] **Step 4: Verify locally**

```bash
cd /Users/marvinbarretto/development/site
npm run dev
```

Open `/app/jimbo/dashboard/tasks/backlog` in browser. Grooming panel items should show "Xh ago" on the right side of each item.

- [ ] **Step 5: Commit**

```bash
cd /Users/marvinbarretto/development/site
git add src/types/vault.ts src/admin-app/views/vault/VaultView.tsx
git commit -m "feat: show elapsed time in grooming pipeline panel"
```

---

### Task 5: Add grooming events to activity timeline

**Files:**
- Modify: `/Users/marvinbarretto/development/site/src/admin-app/views/vault/VaultNoteModal.tsx:527-564`

- [ ] **Step 1: Add grooming_started_at to the activity timeline**

In `VaultNoteModal.tsx`, add a grooming event entry after the `epic_started_at` event (after line 542) and before `blocked_at`:

```tsx
              {note.grooming_started_at && (
                <div className="db-timeline-event db-timeline-event--system">
                  <span className="db-timeline-date">{timeAgo(note.grooming_started_at)}</span>
                  <span className="db-timeline-action">grooming started</span>
                </div>
              )}
              {note.grooming_status && note.grooming_status !== 'ungroomed' && (
                <div className="db-timeline-event db-timeline-event--system">
                  <span className="db-timeline-date">{timeAgo(note.updated_at)}</span>
                  <span className="db-timeline-action">grooming: {note.grooming_status.replace(/_/g, ' ')}</span>
                </div>
              )}
```

- [ ] **Step 2: Verify in browser**

Open a task detail modal for one of the grooming items. Activity section should now show "grooming started" with timestamp and current grooming status.

- [ ] **Step 3: Commit**

```bash
cd /Users/marvinbarretto/development/site
git add src/admin-app/views/vault/VaultNoteModal.tsx
git commit -m "feat: show grooming events in task activity timeline"
```

---

### Task 6: Deploy

- [ ] **Step 1: Deploy jimbo-api**

jimbo-api deploys via git push. Give user the command:

```bash
cd /Users/marvinbarretto/development/jimbo/jimbo-api
git push origin main
```

Migration runs automatically on next restart (column add is idempotent via try-catch).

- [ ] **Step 2: Push workspace scripts**

```bash
cd /Users/marvinbarretto/development/openclaw
./workspace-push.sh
```

- [ ] **Step 3: Push site**

Site auto-deploys on git push:

```bash
cd /Users/marvinbarretto/development/site
git push origin main
```

- [ ] **Step 4: Verify end-to-end**

After deploy, check:
1. Dashboard backlog page — grooming panel items show "Xh ago"
2. Task detail modal — activity timeline shows "grooming started" and current status
3. Next time `decompose-epic.py` runs, Telegram should report results
