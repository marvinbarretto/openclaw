# Dispatch Briefing Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface dispatch system status (commissions, recon, grooming) in the morning/afternoon briefing so Marvin sees agent work alongside email, calendar, and vault data.

**Architecture:** One new service function (`getBriefingSummary`) in jimbo-api that aggregates dispatch_queue state into a briefing-ready shape. One new route exposes it at `GET /briefing-summary`. `briefing-prep.py` calls this endpoint and adds a `dispatch` key to `briefing-input.json`. The daily-briefing skill reads the new key and presents dispatch status.

**Tech Stack:** TypeScript, Hono, better-sqlite3, Vitest (jimbo-api); Python 3.11 stdlib (briefing-prep.py); SKILL.md (daily-briefing)

**Repos:**
- `~/development/jimbo/jimbo-api` — service function, route, tests
- `~/development/openclaw` — briefing-prep.py, daily-briefing skill

---

### Task 1: Service — getBriefingSummary()

**Files:**
- Modify: `~/development/jimbo/jimbo-api/src/services/dispatch.ts`
- Modify: `~/development/jimbo/jimbo-api/src/types/dispatch.ts`
- Test: `~/development/jimbo/jimbo-api/test/dispatch.test.ts`

- [ ] **Step 1: Add the BriefingSummary type**

In `~/development/jimbo/jimbo-api/src/types/dispatch.ts`, add after the existing type exports:

```typescript
export interface BriefingSummaryCommissionItem {
  task_id: string;
  pr_url: string | null;
  issue_repo: string | null;
  issue_number: number | null;
  result_summary: string | null;
  agent_type: string;
  started_at: string | null;
}

export interface BriefingSummaryReconItem {
  task_id: string;
  result_summary: string | null;
  completed_at: string | null;
}

export interface BriefingSummary {
  commissions: {
    prs_for_review: BriefingSummaryCommissionItem[];
    in_progress: BriefingSummaryCommissionItem[];
    awaiting_dispatch: number | null;
  };
  recon: {
    recently_completed: BriefingSummaryReconItem[];
  };
  needs_grooming: number;
}
```

- [ ] **Step 2: Write the failing tests**

Add to `~/development/jimbo/jimbo-api/test/dispatch.test.ts`, inside the top-level `describe`, after the existing test blocks. Also add `getBriefingSummary` to the dynamic import at the top of the file:

```typescript
// Add to the import block at the top:
// getBriefingSummary,

describe('getBriefingSummary', () => {
  it('should return empty summary when queue is empty', () => {
    const summary = getBriefingSummary();
    expect(summary.commissions.prs_for_review).toEqual([]);
    expect(summary.commissions.in_progress).toEqual([]);
    expect(summary.commissions.awaiting_dispatch).toBeNull(); // no GITHUB_TOKEN in test
    expect(summary.recon.recently_completed).toEqual([]);
    expect(summary.needs_grooming).toBe(0);
  });

  it('should return PRs for review (completed commissions with pr_state=open)', () => {
    const db = getDb();
    db.prepare(
      `INSERT INTO dispatch_queue (task_id, task_source, agent_type, status, flow, issue_number, issue_repo, pr_url, pr_state, result_summary, completed_at)
       VALUES ('localshout-next#73', 'github', 'coder', 'completed', 'commission', 73, 'marvinbarretto/localshout-next', 'https://github.com/marvinbarretto/localshout-next/pull/73', 'open', 'Added E2E tests', datetime('now'))`
    ).run();

    const summary = getBriefingSummary();
    expect(summary.commissions.prs_for_review).toHaveLength(1);
    expect(summary.commissions.prs_for_review[0].task_id).toBe('localshout-next#73');
    expect(summary.commissions.prs_for_review[0].pr_url).toBe('https://github.com/marvinbarretto/localshout-next/pull/73');
    expect(summary.commissions.prs_for_review[0].issue_number).toBe(73);
  });

  it('should return in-progress commissions', () => {
    const db = getDb();
    db.prepare(
      `INSERT INTO dispatch_queue (task_id, task_source, agent_type, status, flow, issue_number, issue_repo, started_at)
       VALUES ('localshout-next#85', 'github', 'coder', 'running', 'commission', 85, 'marvinbarretto/localshout-next', datetime('now'))`
    ).run();

    const summary = getBriefingSummary();
    expect(summary.commissions.in_progress).toHaveLength(1);
    expect(summary.commissions.in_progress[0].task_id).toBe('localshout-next#85');
    expect(summary.commissions.in_progress[0].agent_type).toBe('coder');
  });

  it('should return recently completed recon tasks', () => {
    const db = getDb();
    db.prepare(
      `INSERT INTO dispatch_queue (task_id, task_source, agent_type, status, flow, result_summary, completed_at)
       VALUES ('venue-api-research', 'vault', 'researcher', 'completed', 'recon', 'Compared 4 venue APIs', datetime('now', '-2 hours'))`
    ).run();

    const summary = getBriefingSummary();
    expect(summary.recon.recently_completed).toHaveLength(1);
    expect(summary.recon.recently_completed[0].task_id).toBe('venue-api-research');
    expect(summary.recon.recently_completed[0].result_summary).toBe('Compared 4 venue APIs');
  });

  it('should NOT include recon completed more than 24h ago', () => {
    const db = getDb();
    db.prepare(
      `INSERT INTO dispatch_queue (task_id, task_source, agent_type, status, flow, result_summary, completed_at)
       VALUES ('old-recon', 'vault', 'researcher', 'completed', 'recon', 'Old research', datetime('now', '-25 hours'))`
    ).run();

    const summary = getBriefingSummary();
    expect(summary.recon.recently_completed).toHaveLength(0);
  });

  it('should NOT include merged PRs in prs_for_review', () => {
    const db = getDb();
    db.prepare(
      `INSERT INTO dispatch_queue (task_id, task_source, agent_type, status, flow, pr_url, pr_state, completed_at)
       VALUES ('merged-task', 'github', 'coder', 'completed', 'commission', 'https://github.com/x/y/pull/1', 'merged', datetime('now'))`
    ).run();

    const summary = getBriefingSummary();
    expect(summary.commissions.prs_for_review).toHaveLength(0);
  });

  it('should count needs_grooming from vault_notes', () => {
    seedReadyNote({ dispatch_status: 'needs_grooming' });
    seedReadyNote({ dispatch_status: 'needs_grooming' });
    seedReadyNote({ dispatch_status: 'ready' });

    const summary = getBriefingSummary();
    expect(summary.needs_grooming).toBe(2);
  });
});
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd ~/development/jimbo/jimbo-api && npx vitest run test/dispatch.test.ts --reporter=verbose 2>&1 | tail -20`
Expected: FAIL — `getBriefingSummary` is not exported.

- [ ] **Step 4: Implement getBriefingSummary**

Add to `~/development/jimbo/jimbo-api/src/services/dispatch.ts`, after the `getNeedsGroomingCount` function:

```typescript
export function getBriefingSummary(): BriefingSummary {
  const db = getDb();

  // Commissions: PRs ready for review (completed, PR still open)
  const prsForReview = db.prepare(`
    SELECT task_id, pr_url, issue_repo, issue_number, result_summary, agent_type, started_at
    FROM dispatch_queue
    WHERE flow = 'commission' AND status = 'completed' AND pr_state = 'open'
    ORDER BY completed_at DESC
  `).all() as BriefingSummaryCommissionItem[];

  // Commissions: currently running
  const inProgress = db.prepare(`
    SELECT task_id, pr_url, issue_repo, issue_number, result_summary, agent_type, started_at
    FROM dispatch_queue
    WHERE flow = 'commission' AND status = 'running'
    ORDER BY started_at ASC
  `).all() as BriefingSummaryCommissionItem[];

  // Awaiting dispatch: ralph issues not in queue (requires GITHUB_TOKEN)
  let awaitingDispatch: number | null = null;
  // This is populated async by the route handler, not here — keep it null in the sync function.
  // The route will call fetchGitHubIssues and compute the count.

  // Recon: completed in last 24h
  const recentRecon = db.prepare(`
    SELECT task_id, result_summary, completed_at
    FROM dispatch_queue
    WHERE flow = 'recon' AND status = 'completed' AND completed_at > datetime('now', '-24 hours')
    ORDER BY completed_at DESC
  `).all() as BriefingSummaryReconItem[];

  const needsGrooming = getNeedsGroomingCount();

  return {
    commissions: {
      prs_for_review: prsForReview,
      in_progress: inProgress,
      awaiting_dispatch: awaitingDispatch,
    },
    recon: {
      recently_completed: recentRecon,
    },
    needs_grooming: needsGrooming,
  };
}
```

Add `BriefingSummary`, `BriefingSummaryCommissionItem`, and `BriefingSummaryReconItem` to the import block at the top of the file:

```typescript
import type {
  // ... existing imports ...
  BriefingSummary,
  BriefingSummaryCommissionItem,
  BriefingSummaryReconItem,
} from '../types/dispatch.js';
```

- [ ] **Step 5: Add getBriefingSummary to the test imports**

In `~/development/jimbo/jimbo-api/test/dispatch.test.ts`, add `getBriefingSummary` to the dynamic import block at the top:

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
  getBriefingSummary,
} = await import('../src/services/dispatch.js');
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd ~/development/jimbo/jimbo-api && npx vitest run test/dispatch.test.ts --reporter=verbose 2>&1 | tail -30`
Expected: PASS — all tests including getBriefingSummary tests.

- [ ] **Step 7: Commit**

```bash
cd ~/development/jimbo/jimbo-api
git add src/services/dispatch.ts src/types/dispatch.ts test/dispatch.test.ts
git commit -m "feat: add getBriefingSummary for dispatch briefing integration"
```

---

### Task 2: Route — GET /briefing-summary

**Files:**
- Modify: `~/development/jimbo/jimbo-api/src/routes/dispatch.ts`

- [ ] **Step 1: Add the route**

In `~/development/jimbo/jimbo-api/src/routes/dispatch.ts`, add `getBriefingSummary` to the existing import from `'../services/dispatch.js'`. `fetchGitHubIssues` and `listQueue` are already imported.

Add this route after the existing `dispatch.get('/status', ...)` route:

```typescript
// Briefing summary — aggregated dispatch state for briefing pipeline
dispatch.get('/briefing-summary', async (c) => {
  const summary = getBriefingSummary();

  // Enrich with awaiting_dispatch count from GitHub (async)
  try {
    const repos = ['marvinbarretto/localshout-next'];
    let totalAwaiting = 0;

    for (const repo of repos) {
      const issues = await fetchGitHubIssues(repo);
      // Subtract issues already in the queue by checking issue_number
      const queuedItems = listQueue({ status: 'proposed,approved,running,completed' }).items;
      const queuedNumbers = queuedItems
        .filter(item => item.issue_repo === repo)
        .map(item => item.issue_number);

      const unqueued = issues.filter(
        i => i.labels.some(l => l.name === 'ralph') && !queuedNumbers.includes(i.number)
      );
      totalAwaiting += unqueued.length;
    }

    summary.commissions.awaiting_dispatch = totalAwaiting;
  } catch {
    // GITHUB_TOKEN missing or API error — leave as null
    summary.commissions.awaiting_dispatch = null;
  }

  return c.json(summary);
});
```

- [ ] **Step 2: Run all dispatch tests to verify nothing broke**

Run: `cd ~/development/jimbo/jimbo-api && npx vitest run test/dispatch.test.ts --reporter=verbose 2>&1 | tail -20`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
cd ~/development/jimbo/jimbo-api
git add src/routes/dispatch.ts
git commit -m "feat: add GET /briefing-summary route for dispatch status in briefings"
```

---

### Task 3: briefing-prep.py — fetch dispatch summary

**Files:**
- Modify: `~/development/openclaw/workspace/briefing-prep.py`

- [ ] **Step 1: Add fetch_dispatch_summary function**

Add this function after the existing `fetch_email_insights` function (around line 420) in `~/development/openclaw/workspace/briefing-prep.py`:

```python
def fetch_dispatch_summary():
    """Fetch dispatch briefing summary from jimbo-api.

    Returns (dispatch_dict, status_dict).
    """
    api_url = os.environ.get("JIMBO_API_URL", "")
    api_key = os.environ.get("JIMBO_API_KEY", "")

    if not api_url or not api_key:
        return {}, {"status": "skipped", "error": "no API credentials"}

    try:
        url = f"{api_url}/api/dispatch/briefing-summary"
        req = urllib.request.Request(url, headers={
            "X-API-Key": api_key,
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())

        # Count items for pipeline status
        prs = len(data.get("commissions", {}).get("prs_for_review", []))
        running = len(data.get("commissions", {}).get("in_progress", []))
        awaiting = data.get("commissions", {}).get("awaiting_dispatch")
        recon = len(data.get("recon", {}).get("recently_completed", []))
        grooming = data.get("needs_grooming", 0)

        sys.stderr.write(
            f"[briefing-prep] dispatch: {prs} PRs for review, {running} running, "
            f"awaiting={awaiting}, {recon} recon completed, {grooming} needs grooming\n"
        )
        return data, {
            "status": "ok",
            "prs_for_review": prs,
            "in_progress": running,
            "awaiting_dispatch": awaiting,
            "recon_completed": recon,
            "needs_grooming": grooming,
        }

    except Exception as e:
        sys.stderr.write(f"[briefing-prep] failed to fetch dispatch summary: {e}\n")
        return {}, {"status": "failed", "error": str(e)[:200]}
```

- [ ] **Step 2: Add dispatch step to run_pipeline**

In `~/development/openclaw/workspace/briefing-prep.py`, in the `run_pipeline` function, add the dispatch step after the vault step (Step 5) and before the triage pending step (Step 6). Insert after line `pipeline_status["vault"] = {"status": "skipped"}` (around line 263):

```python
    # --- Step 5b: Dispatch status ---
    dispatch_data = {}
    if not dry_run:
        dispatch_data, dispatch_status = fetch_dispatch_summary()
        pipeline_status["dispatch"] = dispatch_status
    else:
        pipeline_status["dispatch"] = {"status": "skipped (dry-run)"}
```

- [ ] **Step 3: Add dispatch_data to the output assembly**

In the `run_pipeline` function, in the output assembly block (around line 280), add the `dispatch` key. After `"vault_tasks": vault_tasks,` add:

```python
        "dispatch": dispatch_data,
```

- [ ] **Step 4: Add dispatch stats to the status alert**

In the `send_status_alert` function, add dispatch stats. After the vault section (around line 496), add:

```python
    # Dispatch
    dispatch = pipeline_status.get("dispatch", {})
    if dispatch.get("status") == "ok":
        dispatch_parts = []
        prs = dispatch.get("prs_for_review", 0)
        running = dispatch.get("in_progress", 0)
        if prs: dispatch_parts.append(f"{prs} PRs to review")
        if running: dispatch_parts.append(f"{running} running")
        if dispatch_parts:
            parts.append(f"dispatch: {', '.join(dispatch_parts)}")
```

- [ ] **Step 5: Add dispatch to the activity log description**

In the `log_to_activity` function, after `task_count = vault.get("tasks", 0)` (around line 97), add:

```python
    dispatch_info = pipeline_status.get("dispatch", {})
    dispatch_prs = dispatch_info.get("prs_for_review", 0)
```

And update the description format string to include it. Change the description line to:

```python
            "--description", f"{label} pipeline: {email_count} emails, {gem_count} gems, {insight_count} insights, {event_count} events, {task_count} vault tasks, {dispatch_prs} PRs to review",
```

- [ ] **Step 6: Commit**

```bash
cd ~/development/openclaw
git add workspace/briefing-prep.py
git commit -m "feat: add dispatch summary step to briefing pipeline"
```

---

### Task 4: Daily briefing skill — dispatch section

**Files:**
- Modify: `~/development/openclaw/skills/daily-briefing/SKILL.md`

- [ ] **Step 1: Add dispatch section to briefing delivery**

In `~/development/openclaw/skills/daily-briefing/SKILL.md`, in Step 2 (Deliver the briefing), add a new section 5 after "Task status" (section 4). Insert before the "After delivering" line:

```markdown
5. **Dispatch status** — If `briefing-input.json` has a `dispatch` key with data, report agent work status. If the key is missing or empty, call the API directly as fallback: `curl -sf -H "X-API-Key: $JIMBO_API_KEY" "$JIMBO_API_URL/api/dispatch/briefing-summary"`

   Present what's relevant, skip what's empty:
   - **PRs for review:** "You've got N PRs ready for review" + one line per PR: "{task_id}: {result_summary}" with PR URL. This is your highest-priority dispatch item — these need human eyes.
   - **In progress:** "N commissions running" + one line each with task_id. Only mention if > 0.
   - **Awaiting dispatch:** "N ralph issues ready to dispatch" — only if > 0. If `null`, skip (means GitHub was unreachable).
   - **Recon landed:** "Recon on {task_id} landed — {result_summary}" for each recently completed recon task.
   - **Needs grooming:** "N tasks need grooming before dispatch" — only if > 0.

   Skip the entire section if everything is zero/empty. Don't say "no dispatch activity."
```

- [ ] **Step 2: Add dispatch fallback to the live data section**

In Step 1, Option C (Live data, last resort), add:

```markdown
- Dispatch: `curl -sf -H "X-API-Key: $JIMBO_API_KEY" "$JIMBO_API_URL/api/dispatch/briefing-summary"`
```

- [ ] **Step 3: Commit**

```bash
cd ~/development/openclaw
git add skills/daily-briefing/SKILL.md
git commit -m "feat: add dispatch status section to daily briefing skill"
```

---

### Task 5: End-to-end verification

This task is manual verification. No code changes.

- [ ] **Step 1: Run the full jimbo-api test suite**

```bash
cd ~/development/jimbo/jimbo-api && npx vitest run --reporter=verbose
```

Expected: all tests pass, including the new getBriefingSummary tests.

- [ ] **Step 2: Verify briefing-prep.py syntax**

```bash
cd ~/development/openclaw && python3 -c "import py_compile; py_compile.compile('workspace/briefing-prep.py', doraise=True)"
```

Expected: no errors.

- [ ] **Step 3: Test briefing-prep.py dry-run locally**

```bash
cd ~/development/openclaw/workspace && python3 briefing-prep.py morning --dry-run
```

Expected: outputs JSON with `dispatch` key showing `{"status": "skipped (dry-run)"}`.

- [ ] **Step 4: List changes for deployment**

jimbo-api changes:
```bash
cd ~/development/jimbo/jimbo-api && git log --oneline -5
```

openclaw changes:
```bash
cd ~/development/openclaw && git log --oneline -5
```

- [ ] **Step 5: Document deployment steps**

After this plan completes, deploy:

1. **jimbo-api:** `git push` → SSH to VPS → `cd ~/jimbo-api && git pull && npm run build && cp -r dist/* . && systemctl restart jimbo-api`
2. **openclaw workspace:** `cd ~/development/openclaw && ./scripts/workspace-push.sh` (pushes briefing-prep.py)
3. **openclaw skills:** `cd ~/development/openclaw && ./scripts/skills-push.sh` (pushes daily-briefing skill)
4. **Verify on VPS:** `curl -sf -H "X-API-Key: $API_KEY" "https://167.99.206.214/api/dispatch/briefing-summary"` should return the summary JSON
