# Jimbo Improvements — Post-Review Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix broken worker pipeline, stop cost bleed with automated model switching, patch incorrect OpenRouter reporting, deploy tasks-triage, and build live dashboard pages (activity feed + schedule) — in priority order.

**Architecture:** Six tasks ordered by impact. Tasks 1-3 are quick fixes to workspace scripts (stdlib Python). Task 4 is a deploy. Task 5 adds API endpoints to jimbo-api (Hono/Node) and two new pages to the site (Astro/React). Task 6 is tuning.

**Tech Stack:** Python 3.11 stdlib (workspace scripts), Hono/Node (jimbo-api), Astro/React (site), SQLite (databases), rsync (deployment).

**Repos involved:**
- `openclaw/` — workspace scripts, skills, decisions (this repo, `/Users/marvinbarretto/development/openclaw/`)
- `jimbo/notes-triage-api/` — jimbo-api (Hono, port 3100) at `/Users/marvinbarretto/development/jimbo/notes-triage-api/`
- `site/` — personal site (Astro/Cloudflare) at `/Users/marvinbarretto/development/site/`

---

## Task 1: Fix OpenRouter Balance Reporting

**Why first:** The briefing led with "overdrawn by $20.92" which is wrong. Erodes trust. Quick fix.

**Root cause:** `openrouter-usage.py` `cmd_balance()` calculates `remaining = limit - usage`. OpenRouter's `/auth/key` returns a stale `limit` that doesn't reflect top-ups. The hourly `alert-check.py` was already fixed to report usage only, but the balance command (called by the briefing skill) still does the broken maths.

**Files:**
- Modify: `workspace/openrouter-usage.py:57-85`

**Step 1: Patch cmd_balance to report usage only**

Replace the balance calculation. Remove `remaining` and the low-balance warnings that depend on it.

```python
def cmd_balance():
    """Show current credit usage."""
    data = api_get("/auth/key")
    info = data.get("data", data)

    usage = info.get("usage")
    limit = info.get("limit")

    if usage is None:
        print(json.dumps({"error": "unexpected response format", "raw": data}))
        sys.exit(1)

    result = {
        "usage_total": round(usage, 4),
        "limit_reported": round(limit, 4) if limit is not None else None,
        "note": "limit from /auth/key is stale and does not reflect top-ups",
    }

    print(f"OpenRouter: ${usage:.2f} used (check openrouter.ai for actual balance)")

    return result
```

**Step 2: Verify script still parses**

Run: `python3 -c "import py_compile; py_compile.compile('workspace/openrouter-usage.py', doraise=True)"`
Expected: No output (success)

**Step 3: Commit**

```bash
git add workspace/openrouter-usage.py
git commit -m "fix: remove broken OpenRouter balance calculation, report usage only"
```

---

## Task 2: Fix the Worker Pipeline

**Why second:** Biggest blocker. Without working workers, the briefing falls back to scanning raw email through a single context window. No `experiment-tracker.db` means hourly alerts fail after 08:00. No gems means no surprise game.

**Root cause:** Multiple silent failure modes identified:
1. SKILL.md uses `/tmp/` for worker output — may not persist between Docker exec calls
2. Jimbo may skip the experiment-tracker log step (Step 4), so `alert-check.py` never sees a run
3. Fallback path is too easy to take silently — Jimbo falls back without reporting why

**Files:**
- Modify: `skills/sift-digest/SKILL.md` — fix temp paths, make logging mandatory, improve fallback reporting

**Step 1: Replace /tmp paths with /workspace paths**

In `skills/sift-digest/SKILL.md`, find and replace all `/tmp/shortlist.json` with `/workspace/.worker-shortlist.json` and `/tmp/gems.json` with `/workspace/.worker-gems.json`. Also update the prose references ("Read `/tmp/shortlist.json`" etc.).

There are 4 occurrences:
- Step 1 command: `--output /tmp/shortlist.json` → `--output /workspace/.worker-shortlist.json`
- Step 1 prose: "Read `/tmp/shortlist.json`" → "Read `/workspace/.worker-shortlist.json`"
- Step 2 command: `--shortlist /tmp/shortlist.json ... --output /tmp/gems.json` → `--shortlist /workspace/.worker-shortlist.json ... --output /workspace/.worker-gems.json`
- Step 2 prose: "Read `/tmp/gems.json`" → "Read `/workspace/.worker-gems.json`"

**Step 2: Add mandatory cleanup section**

After the existing Step 4, add a new section:

```markdown
### Step 5: Mandatory cleanup (do NOT skip)

After presenting the digest to Marvin, run these commands regardless of whether the workers succeeded or failed:

\`\`\`bash
# Log the briefing run — this is what alert-check.py looks for
python3 /workspace/experiment-tracker.py log \
    --task briefing-synthesis \
    --model <your-model-id> \
    --input-tokens 0 \
    --output-tokens 0 \
    --output-summary "Briefing delivered. Workers: <success|fallback>"

# Clean up worker temp files
rm -f /workspace/.worker-shortlist.json /workspace/.worker-gems.json
\`\`\`

This step MUST run even if you used the fallback path. The token counts can be zero — the important thing is that a `briefing-synthesis` row exists in the DB for today's date, otherwise the hourly Telegram status will report "briefing missing" all day.
```

**Step 3: Improve fallback reporting**

Replace the existing "Fallback" section at the bottom of the skill with:

```markdown
## Fallback

If a worker script fails (script error, missing API key, malformed output):
1. **Tell Marvin which worker failed and why** — e.g. "Email triage worker crashed: GOOGLE_AI_API_KEY not set. Falling back to reading the digest directly."
2. Read `/workspace/email-digest.json` directly and present highlights
3. Still run Step 5 (mandatory cleanup) — log with `--output-summary "Fallback: <reason>"`
4. Do NOT silently fall back — Marvin needs to know the pipeline is broken
```

**Step 4: Commit**

```bash
git add skills/sift-digest/SKILL.md
git commit -m "fix: use /workspace for worker temp files, make experiment-tracker logging mandatory"
```

---

## Task 3: Automated Model Switching (Cron)

**Why third:** Haiku running 24/7 for heartbeat ticks costs ~$5/day. Switch to Flash for everything except the briefing window.

**Design:** Two cron jobs on VPS:
- 06:45 UTC → switch to Haiku (briefing prep)
- 07:30 UTC → switch back to Flash (cheap mode)

Cost impact: ~$1-1.50/day instead of ~$5/day.

**Files:**
- Modify: `workspace/HEARTBEAT.md` — add cost awareness
- Reference: `scripts/model-swap.sh` — the sed+restart pattern to reuse

**Step 1: Add cost awareness to HEARTBEAT.md**

Read the current file, then add this section near the top (after the intro, before the first check):

```markdown
## Cost awareness

Every heartbeat tick costs tokens. Before running ANY check:
1. Is there a specific trigger (time of day, user message, calendar event)?
2. If no trigger matches right now, do NOTHING. Output nothing. Return immediately.
3. Never run all checks on every tick — only the ones whose time window matches.

If in doubt, stay silent. Silence is free.
```

**Step 2: Document the cron jobs for VPS deployment**

Create a section in this plan for manual VPS execution. The cron entries to add to VPS root crontab:

```bash
# Model swap: Haiku for briefing window, Flash for everything else
# 06:45 UTC — switch to Haiku before morning briefing
45 6 * * * sed -i 's|"primary": "[^"]*"|"primary": "openrouter/anthropic/claude-haiku-4.5"|' /home/openclaw/.openclaw/openclaw.json && systemctl restart openclaw >> /var/log/model-swap.log 2>&1

# 07:30 UTC — switch to Flash after briefing
30 7 * * * sed -i 's|"primary": "[^"]*"|"primary": "google/gemini-2.5-flash"|' /home/openclaw/.openclaw/openclaw.json && systemctl restart openclaw >> /var/log/model-swap.log 2>&1
```

**Step 3: Commit**

```bash
git add workspace/HEARTBEAT.md
git commit -m "perf: add cost-awareness to heartbeat, document model-swap cron"
```

---

## Task 4: Deploy Everything

**Why fourth:** Tasks 1-3 are code changes. This pushes them all to VPS along with the tasks-triage work from earlier this session.

**Step 1: Push workspace files**

```bash
./scripts/workspace-push.sh
```

Pushes: `tasks-helper.py`, `activity-log.py`, `openrouter-usage.py`, `HEARTBEAT.md`, and all workspace files.

**Step 2: Push skills**

```bash
./scripts/skills-push.sh
```

Pushes: `daily-briefing/SKILL.md` (updated with section 3.5), `sift-digest/SKILL.md` (fixed paths), `tasks-triage/SKILL.md` (new).

**Step 3: Add model-swap cron entries on VPS**

```bash
ssh jimbo
sudo crontab -e
# Add the two model-swap entries from Task 3 Step 2
# Verify with: sudo crontab -l
```

**Step 4: Verify deployment**

```bash
ssh jimbo "python3 -c \"import py_compile; py_compile.compile('/home/openclaw/.openclaw/workspace/openrouter-usage.py', doraise=True)\" && echo 'openrouter OK'"
ssh jimbo "ls -la /home/openclaw/.openclaw/workspace/skills/tasks-triage/SKILL.md && echo 'tasks-triage skill OK'"
ssh jimbo "grep 'worker-shortlist' /home/openclaw/.openclaw/workspace/skills/sift-digest/SKILL.md && echo 'sift-digest paths OK'"
```

---

## Task 5: Live Dashboard Pages (Activity Feed + Schedule)

**Why fifth:** Biggest build but highest long-term value. Gives Marvin real-time visibility into Jimbo's activity and a clear view of the daily schedule.

**Architecture:**

```
Docker sandbox                    VPS host                    Cloudflare
┌──────────────────┐   volume    ┌──────────────────┐   API    ┌──────────────┐
│ activity-log.db  │───mount────▶│ jimbo-api        │◀────────│ site         │
│ cost-tracker.db  │            │  /api/dashboard/* │         │  /app/jimbo/ │
│ experiment-      │            │                   │         │  activity    │
│   tracker.db     │            │                   │         │  schedule    │
└──────────────────┘            └──────────────────┘         └──────────────┘
```

### Sub-task 5a: Add dashboard API endpoints to jimbo-api

**Repo:** `/Users/marvinbarretto/development/jimbo/notes-triage-api/`

**Files:**
- Create: `src/routes/dashboard.ts`
- Modify: `src/index.ts` — mount the new route

**Endpoints:**

```
GET /api/dashboard/feed?hours=24     — merged activity + costs + experiments, newest first
GET /api/dashboard/summary?days=7    — aggregated stats
GET /api/dashboard/schedule          — returns the full cron/task schedule as structured data
```

**`src/routes/dashboard.ts`:**

```typescript
import { Hono } from "hono";
import Database from "better-sqlite3";

const SANDBOX_WORKSPACE = process.env.SANDBOX_WORKSPACE
  || "/home/openclaw/.openclaw/workspace";

function openDb(name: string): Database.Database | null {
  const path = `${SANDBOX_WORKSPACE}/${name}`;
  try {
    return new Database(path, { readonly: true });
  } catch {
    return null;
  }
}

const app = new Hono();

// --- Live activity feed ---
app.get("/feed", (c) => {
  const hours = Number(c.req.query("hours") || "24");
  const cutoff = new Date(Date.now() - hours * 3600_000).toISOString();
  const items: Array<{ type: string; timestamp: string; data: unknown }> = [];

  const actDb = openDb("activity-log.db");
  if (actDb) {
    const rows = actDb.prepare(
      "SELECT * FROM activities WHERE timestamp >= ? ORDER BY timestamp DESC LIMIT 200"
    ).all(cutoff);
    for (const r of rows) items.push({ type: "activity", timestamp: (r as any).timestamp, data: r });
    actDb.close();
  }

  const costDb = openDb("cost-tracker.db");
  if (costDb) {
    const rows = costDb.prepare(
      "SELECT * FROM costs WHERE timestamp >= ? ORDER BY timestamp DESC LIMIT 200"
    ).all(cutoff);
    for (const r of rows) items.push({ type: "cost", timestamp: (r as any).timestamp, data: r });
    costDb.close();
  }

  const expDb = openDb("experiment-tracker.db");
  if (expDb) {
    const rows = expDb.prepare(
      "SELECT * FROM runs WHERE timestamp >= ? ORDER BY timestamp DESC LIMIT 200"
    ).all(cutoff);
    for (const r of rows) items.push({ type: "experiment", timestamp: (r as any).timestamp, data: r });
    expDb.close();
  }

  items.sort((a, b) => b.timestamp.localeCompare(a.timestamp));
  return c.json({ generated_at: new Date().toISOString(), hours, count: items.length, items });
});

// --- Summary stats ---
app.get("/summary", (c) => {
  const days = Number(c.req.query("days") || "7");
  const cutoff = new Date(Date.now() - days * 86400_000).toISOString();
  const summary: Record<string, unknown> = { days };

  const costDb = openDb("cost-tracker.db");
  if (costDb) {
    const row = costDb.prepare(
      "SELECT SUM(estimated_cost) as total, COUNT(*) as count FROM costs WHERE timestamp >= ?"
    ).get(cutoff) as any;
    summary.costs = { total: row?.total || 0, entries: row?.count || 0 };
    const byModel = costDb.prepare(
      "SELECT model, SUM(estimated_cost) as total, COUNT(*) as count FROM costs WHERE timestamp >= ? GROUP BY model ORDER BY total DESC"
    ).all(cutoff);
    summary.costs_by_model = byModel;
    costDb.close();
  }

  const actDb = openDb("activity-log.db");
  if (actDb) {
    const byType = actDb.prepare(
      "SELECT task_type, COUNT(*) as count FROM activities WHERE timestamp >= ? GROUP BY task_type ORDER BY count DESC"
    ).all(cutoff);
    summary.activities_by_type = byType;
    actDb.close();
  }

  const expDb = openDb("experiment-tracker.db");
  if (expDb) {
    const row = expDb.prepare(
      "SELECT COUNT(*) as count, AVG(conductor_rating) as avg_rating FROM runs WHERE timestamp >= ?"
    ).get(cutoff) as any;
    summary.experiments = {
      count: row?.count || 0,
      avg_conductor_rating: row?.avg_rating ? Math.round(row.avg_rating * 10) / 10 : null,
    };
    expDb.close();
  }

  return c.json({ generated_at: new Date().toISOString(), ...summary });
});

// --- Daily schedule (static data, rendered from known cron entries) ---
app.get("/schedule", (c) => {
  const schedule = [
    { time: "04:30", timezone: "UTC", task: "Vault task scoring", model: "Gemini Flash", script: "prioritise-tasks.py", frequency: "daily" },
    { time: "05:00", timezone: "UTC", task: "Google Tasks sweep", model: "Gemini Flash", script: "tasks-helper.py pipeline", frequency: "daily" },
    { time: "06:45", timezone: "UTC", task: "Model swap → Haiku", model: null, script: "sed + systemctl restart", frequency: "daily" },
    { time: ":00", timezone: "UTC", task: "Email fetch (interval-aware)", model: null, script: "email-fetch-cron.py", frequency: "hourly" },
    { time: "07:00", timezone: "UTC", task: "Morning briefing", model: "Claude Haiku 4.5", script: "OpenClaw cron (sift-digest + daily-briefing)", frequency: "daily" },
    { time: "07:30", timezone: "UTC", task: "Model swap → Flash", model: null, script: "sed + systemctl restart", frequency: "daily" },
    { time: ":30", timezone: "UTC", task: "Status check (Telegram)", model: null, script: "alert-check.py status", frequency: "hourly" },
  ];

  // Add today's actual run status from experiment tracker if available
  const today = new Date().toISOString().slice(0, 10);
  const expDb = openDb("experiment-tracker.db");
  let todayRuns: any[] = [];
  if (expDb) {
    todayRuns = expDb.prepare(
      "SELECT task_id, timestamp, model, output_tokens, conductor_rating FROM runs WHERE timestamp LIKE ?"
    ).all(`${today}%`) as any[];
    expDb.close();
  }

  return c.json({
    generated_at: new Date().toISOString(),
    schedule,
    today_runs: todayRuns,
  });
});

export default app;
```

**Mount in `src/index.ts`** — add after existing route mounts:

```typescript
import dashboard from "./routes/dashboard";
// ... inside the route setup section:
app.route("/api/dashboard", dashboard);
```

**Add `SANDBOX_WORKSPACE` to the systemd env** (on VPS):

```bash
# In /etc/systemd/system/notes-triage-api.service, add:
Environment=SANDBOX_WORKSPACE=/home/openclaw/.openclaw/workspace
```

**Add Caddy routes** (on VPS `/etc/caddy/Caddyfile`):

```
handle /api/dashboard {
    reverse_proxy localhost:3100
}
handle /api/dashboard/* {
    reverse_proxy localhost:3100
}
```

### Sub-task 5b: Build the Activity Feed page

**Repo:** `/Users/marvinbarretto/development/site/`

**Files:**
- Create: `src/hooks/useDashboardApi.ts`
- Create: `src/components/dashboard/ActivityFeed.tsx`
- Create: `src/components/dashboard/ActivityFeed.scss`
- Create: `src/pages/app/jimbo/activity.astro`

**`src/hooks/useDashboardApi.ts`:**

```typescript
import { useState, useEffect, useCallback } from 'react';

const API_URL = import.meta.env.PUBLIC_CONTEXT_API_URL
  || import.meta.env.PUBLIC_TRIAGE_API_URL
  || 'http://localhost:3100';
const API_KEY = import.meta.env.PUBLIC_CONTEXT_API_KEY
  || import.meta.env.PUBLIC_TRIAGE_API_KEY || '';

function headers(): HeadersInit {
  return { 'Content-Type': 'application/json', 'X-API-Key': API_KEY };
}

export interface FeedItem {
  type: 'activity' | 'cost' | 'experiment';
  timestamp: string;
  data: Record<string, unknown>;
}

export interface FeedResponse {
  generated_at: string;
  hours: number;
  count: number;
  items: FeedItem[];
}

export interface SummaryResponse {
  generated_at: string;
  days: number;
  costs?: { total: number; entries: number };
  costs_by_model?: Array<{ model: string; total: number; count: number }>;
  activities_by_type?: Array<{ task_type: string; count: number }>;
  experiments?: { count: number; avg_conductor_rating: number | null };
}

export interface ScheduleEntry {
  time: string;
  timezone: string;
  task: string;
  model: string | null;
  script: string;
  frequency: string;
}

export interface ScheduleResponse {
  generated_at: string;
  schedule: ScheduleEntry[];
  today_runs: Array<Record<string, unknown>>;
}

export function useFeed(hours = 24, refreshInterval = 30000) {
  const [data, setData] = useState<FeedResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchFeed = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/api/dashboard/feed?hours=${hours}`, { headers: headers() });
      if (!res.ok) throw new Error(`Feed failed: ${res.status}`);
      setData(await res.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  }, [hours]);

  useEffect(() => {
    fetchFeed();
    const interval = setInterval(fetchFeed, refreshInterval);
    return () => clearInterval(interval);
  }, [fetchFeed, refreshInterval]);

  return { data, loading, error, refresh: fetchFeed };
}

export function useSummary(days = 7) {
  const [data, setData] = useState<SummaryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchSummary = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/api/dashboard/summary?days=${days}`, { headers: headers() });
      if (!res.ok) throw new Error(`Summary failed: ${res.status}`);
      setData(await res.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => { fetchSummary(); }, [fetchSummary]);

  return { data, loading, error, refresh: fetchSummary };
}

export function useSchedule() {
  const [data, setData] = useState<ScheduleResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchSchedule = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/api/dashboard/schedule`, { headers: headers() });
      if (!res.ok) throw new Error(`Schedule failed: ${res.status}`);
      setData(await res.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchSchedule(); }, [fetchSchedule]);

  return { data, loading, error, refresh: fetchSchedule };
}
```

**`src/components/dashboard/ActivityFeed.tsx`:**

Interactive React component. Live-updating feed styled like a breaking news ticker. Each item shows:
- Timestamp (HH:MM)
- Type icon: `$` for cost, `⚡` for activity, `🧪` for experiment
- One-line summary derived from the data
- Colour stripe: amber for costs, blue for activities, green for experiments

Summary bar at top showing: total cost today, activity count, last briefing status.

Auto-refreshes every 30 seconds via the `useFeed` hook.

Component structure:
```tsx
import { useFeed, useSummary } from '../../hooks/useDashboardApi';
import type { FeedItem } from '../../hooks/useDashboardApi';
import './ActivityFeed.scss';

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
}

function summariseItem(item: FeedItem): string {
  const d = item.data as Record<string, any>;
  switch (item.type) {
    case 'cost':
      return `${d.model}: ${d.input_tokens + d.output_tokens} tokens ($${(d.estimated_cost || 0).toFixed(4)}) — ${d.task_type}`;
    case 'activity':
      return `${d.task_type}: ${d.description}`;
    case 'experiment':
      return `${d.task_id} (${d.model}): ${d.output_tokens} tokens${d.conductor_rating ? ` — rated ${d.conductor_rating}/10` : ''}`;
    default:
      return JSON.stringify(d);
  }
}

export function ActivityFeed() {
  const { data: feed, loading, error } = useFeed(24, 30000);
  const { data: summary } = useSummary(1);

  return (
    <div className="activity-feed">
      {/* Summary bar */}
      <div className="activity-feed__summary">
        <div className="activity-feed__stat">
          <span className="activity-feed__stat-value">
            ${summary?.costs?.total?.toFixed(2) || '0.00'}
          </span>
          <span className="activity-feed__stat-label label">Cost today</span>
        </div>
        <div className="activity-feed__stat">
          <span className="activity-feed__stat-value">
            {feed?.count || 0}
          </span>
          <span className="activity-feed__stat-label label">Events (24h)</span>
        </div>
        <div className="activity-feed__stat">
          <span className="activity-feed__stat-value">
            {summary?.experiments?.avg_conductor_rating?.toFixed(1) || '—'}
          </span>
          <span className="activity-feed__stat-label label">Avg quality</span>
        </div>
      </div>

      {/* Status */}
      {loading && !feed && <p className="activity-feed__loading label">Loading...</p>}
      {error && <p className="activity-feed__error">{error}</p>}

      {/* Feed items */}
      <div className="activity-feed__items">
        {feed?.items.map((item, i) => (
          <div key={i} className={`activity-feed__item activity-feed__item--${item.type}`}>
            <span className="activity-feed__time label">{formatTime(item.timestamp)}</span>
            <span className="activity-feed__icon">
              {item.type === 'cost' ? '$' : item.type === 'experiment' ? '~' : '>'}
            </span>
            <span className="activity-feed__text">{summariseItem(item)}</span>
          </div>
        ))}
      </div>

      {/* Auto-refresh indicator */}
      {feed && (
        <p className="activity-feed__refresh label">
          Last updated: {formatTime(feed.generated_at)} · refreshes every 30s
        </p>
      )}
    </div>
  );
}
```

**`src/components/dashboard/ActivityFeed.scss`:**

```scss
.activity-feed {
  max-width: 900px;

  &__summary {
    display: flex;
    gap: var(--space-8);
    flex-wrap: wrap;
    margin-bottom: var(--space-8);
    padding-bottom: var(--space-6);
    border-bottom: 1px solid var(--color-border);
  }

  &__stat {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }

  &__stat-value {
    font-size: var(--text-2xl);
    font-weight: var(--weight-bold);
    font-family: var(--font-mono);
    line-height: 1;
  }

  &__loading, &__refresh {
    color: var(--color-text-muted);
    margin-top: var(--space-4);
  }

  &__error {
    color: #dc2626;
    font-size: var(--text-sm);
    font-family: var(--font-mono);
  }

  &__items {
    display: flex;
    flex-direction: column;
  }

  &__item {
    display: flex;
    align-items: baseline;
    gap: var(--space-3);
    padding: var(--space-2) 0;
    border-bottom: 1px solid var(--color-surface);
    font-size: var(--text-sm);
    line-height: var(--leading-relaxed);

    &--cost { border-left: 3px solid #d97706; padding-left: var(--space-3); }
    &--activity { border-left: 3px solid #2563eb; padding-left: var(--space-3); }
    &--experiment { border-left: 3px solid #16a34a; padding-left: var(--space-3); }
  }

  &__time {
    flex-shrink: 0;
    width: 3.5em;
  }

  &__icon {
    flex-shrink: 0;
    width: 1.2em;
    font-family: var(--font-mono);
    font-weight: var(--weight-bold);
    color: var(--color-text-muted);
  }

  &__text {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}
```

**`src/pages/app/jimbo/activity.astro`:**

```astro
---
import AppLayout from '../../../layouts/AppLayout.astro';
import { ActivityFeed } from '../../../components/dashboard/ActivityFeed';
---

<AppLayout title="Jimbo Activity">
  <section class="activity-page">
    <div class="container">
      <a href="/app/jimbo" class="activity-page__back label">&larr; Back to Dashboard</a>
      <span class="label">Live Feed</span>
      <h1 class="activity-page__title">Jimbo Activity</h1>
      <p class="activity-page__intro">Real-time view of everything Jimbo is doing — costs, activities, and worker runs. Updates every 30 seconds.</p>
      <ActivityFeed client:load />
    </div>
  </section>
</AppLayout>

<style lang="scss">
  .activity-page {
    padding: var(--space-12) 0;

    .container {
      max-width: 900px;
      margin: 0 auto;
      padding: 0 var(--space-6);
    }

    &__back {
      display: inline-block;
      margin-bottom: var(--space-8);
      text-decoration: none;
      color: var(--color-text-muted);
      &:hover { color: var(--color-accent); }
    }

    &__title {
      font-size: var(--text-3xl);
      font-weight: var(--weight-bold);
      margin-bottom: var(--space-2);
    }

    &__intro {
      color: var(--color-text-muted);
      max-width: 50ch;
      margin-bottom: var(--space-8);
    }
  }
</style>
```

### Sub-task 5c: Build the Schedule page

**Repo:** `/Users/marvinbarretto/development/site/`

**Files:**
- Create: `src/components/dashboard/ScheduleView.tsx`
- Create: `src/components/dashboard/ScheduleView.scss`
- Create: `src/pages/app/jimbo/schedule.astro`

**`src/components/dashboard/ScheduleView.tsx`:**

Displays the daily cron schedule as a timeline, with today's run statuses overlaid.

```tsx
import { useSchedule } from '../../hooks/useDashboardApi';
import './ScheduleView.scss';

export function ScheduleView() {
  const { data, loading, error } = useSchedule();

  if (loading && !data) return <p className="label">Loading schedule...</p>;
  if (error) return <p className="schedule-view__error">{error}</p>;
  if (!data) return null;

  const todayRunTasks = new Set(data.today_runs.map((r: any) => r.task_id));

  return (
    <div className="schedule-view">
      {/* Timeline */}
      <div className="schedule-view__timeline">
        {data.schedule.map((entry, i) => {
          const isHourly = entry.frequency === 'hourly';
          const hasRun = !isHourly && todayRunTasks.has(entry.script.split(' ')[0]?.replace('.py', ''));

          return (
            <div key={i} className={`schedule-view__entry ${isHourly ? 'schedule-view__entry--hourly' : ''}`}>
              <div className="schedule-view__time-col">
                <span className="schedule-view__time label">{entry.time}</span>
                <span className="schedule-view__freq label">{entry.frequency}</span>
              </div>
              <div className="schedule-view__dot-col">
                <span className={`schedule-view__dot ${hasRun ? 'schedule-view__dot--done' : ''}`} />
                {i < data.schedule.length - 1 && <span className="schedule-view__line" />}
              </div>
              <div className="schedule-view__detail">
                <span className="schedule-view__task">{entry.task}</span>
                {entry.model && <span className="schedule-view__model label">{entry.model}</span>}
                <span className="schedule-view__script label">{entry.script}</span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Today's runs */}
      {data.today_runs.length > 0 && (
        <div className="schedule-view__runs">
          <h2 className="schedule-view__runs-title">Today's runs</h2>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Task</th>
                  <th>Model</th>
                  <th>Tokens</th>
                  <th>Rating</th>
                </tr>
              </thead>
              <tbody>
                {data.today_runs.map((run: any, i: number) => (
                  <tr key={i}>
                    <td className="label">{new Date(run.timestamp).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}</td>
                    <td>{run.task_id}</td>
                    <td className="label">{run.model}</td>
                    <td className="label">{run.output_tokens || '—'}</td>
                    <td>{run.conductor_rating ? `${run.conductor_rating}/10` : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
```

**`src/components/dashboard/ScheduleView.scss`:**

```scss
.schedule-view {
  max-width: 900px;

  &__error {
    color: #dc2626;
    font-size: var(--text-sm);
    font-family: var(--font-mono);
  }

  &__timeline {
    display: flex;
    flex-direction: column;
  }

  &__entry {
    display: flex;
    gap: var(--space-4);
    min-height: 3.5rem;

    &--hourly {
      opacity: 0.6;
    }
  }

  &__time-col {
    flex-shrink: 0;
    width: 5rem;
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    padding-top: var(--space-1);
  }

  &__time {
    font-family: var(--font-mono);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
  }

  &__freq {
    font-size: var(--text-xs);
    margin-top: 2px;
  }

  &__dot-col {
    flex-shrink: 0;
    width: 1.5rem;
    display: flex;
    flex-direction: column;
    align-items: center;
  }

  &__dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    border: 2px solid var(--color-border);
    background: var(--color-bg);
    flex-shrink: 0;
    margin-top: var(--space-1);

    &--done {
      background: #16a34a;
      border-color: #16a34a;
    }
  }

  &__line {
    flex: 1;
    width: 2px;
    background: var(--color-border);
    min-height: var(--space-4);
  }

  &__detail {
    flex: 1;
    padding-bottom: var(--space-4);
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  &__task {
    font-size: var(--text-sm);
    font-weight: var(--weight-medium);
  }

  &__model {
    color: var(--color-accent);
  }

  &__script {
    color: var(--color-text-muted);
  }

  &__runs {
    margin-top: var(--space-10);
  }

  &__runs-title {
    font-size: var(--text-xl);
    margin-bottom: var(--space-4);
  }
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--text-sm);

  th, td {
    padding: var(--space-2) var(--space-3);
    text-align: left;
    border-bottom: 1px solid var(--color-surface);
    white-space: nowrap;
  }

  th {
    font-family: var(--font-mono);
    font-size: var(--text-xs);
    font-weight: var(--weight-medium);
    letter-spacing: var(--tracking-wider);
    text-transform: uppercase;
    color: var(--color-text-muted);
    border-bottom-color: var(--color-border);
  }

  tbody tr:hover {
    background: var(--color-surface);
  }
}

.table-wrap {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}
```

**`src/pages/app/jimbo/schedule.astro`:**

```astro
---
import AppLayout from '../../../layouts/AppLayout.astro';
import { ScheduleView } from '../../../components/dashboard/ScheduleView';
---

<AppLayout title="Jimbo Schedule">
  <section class="schedule-page">
    <div class="container">
      <a href="/app/jimbo" class="schedule-page__back label">&larr; Back to Dashboard</a>
      <span class="label">Daily Schedule</span>
      <h1 class="schedule-page__title">Jimbo Schedule</h1>
      <p class="schedule-page__intro">Everything Jimbo does each day — cron jobs, model swaps, worker runs. Green dots show what's completed today.</p>
      <ScheduleView client:load />
    </div>
  </section>
</AppLayout>

<style lang="scss">
  .schedule-page {
    padding: var(--space-12) 0;

    .container {
      max-width: 900px;
      margin: 0 auto;
      padding: 0 var(--space-6);
    }

    &__back {
      display: inline-block;
      margin-bottom: var(--space-8);
      text-decoration: none;
      color: var(--color-text-muted);
      &:hover { color: var(--color-accent); }
    }

    &__title {
      font-size: var(--text-3xl);
      font-weight: var(--weight-bold);
      margin-bottom: var(--space-2);
    }

    &__intro {
      color: var(--color-text-muted);
      max-width: 50ch;
      margin-bottom: var(--space-8);
    }
  }
</style>
```

### Sub-task 5d: Add links to dashboard index

**Modify:** `src/pages/app/jimbo/index.astro` — add cards for Activity and Schedule linking to the new pages, following the existing card pattern.

### Sub-task 5e: Deploy jimbo-api + site

```bash
# jimbo-api: build and deploy
cd /Users/marvinbarretto/development/jimbo/notes-triage-api
npm run build
rsync -avz dist/ jimbo:/home/openclaw/notes-triage-api/dist/

# Add SANDBOX_WORKSPACE env to systemd unit
ssh jimbo "sudo systemctl edit notes-triage-api"
# Add: Environment=SANDBOX_WORKSPACE=/home/openclaw/.openclaw/workspace
ssh jimbo "sudo systemctl daemon-reload && sudo systemctl restart notes-triage-api"

# Add Caddy routes
ssh jimbo "sudo nano /etc/caddy/Caddyfile"
# Add /api/dashboard and /api/dashboard/* reverse_proxy entries
ssh jimbo "sudo systemctl reload caddy"

# Site: auto-deploys via Cloudflare Pages on push
cd /Users/marvinbarretto/development/site
git add . && git commit -m "feat: add live activity feed and schedule pages for Jimbo dashboard"
git push
```

---

## Task 6: Improve Email Digest Quality

**Why last:** Ongoing tuning. Depends on worker pipeline (Task 2) being functional.

**Areas to investigate after deployment:**

### 6a: Blacklist tuning
Add Sentry deploy notifications to `workspace/gmail-helper.py` blacklist. Review last week's digests for other noise patterns.

### 6b: Worker prompt tuning
After workers are running, review output quality. Are they extracting specific links and prices? Adjust prompts in `workspace/workers/email_triage.py` and `workspace/workers/newsletter_reader.py`.

### 6c: Body length increase
Current `email_body_max_length` = 5000 chars. Newsletters may truncate. Consider 8000-10000 via settings UI.

### 6d: Model exploration
Research Gemini 2.5 Pro pricing for triage worker. Use `experiment-tracker.py compare` to A/B test after pipeline is running.

**No code changes — investigation and tuning after deployment.**

---

## Execution Order Summary

| # | Task | Type | Blocked By |
|---|------|------|------------|
| 1 | Fix OpenRouter balance | Code fix (openclaw) | — |
| 2 | Fix worker pipeline | Skill edit (openclaw) | — |
| 3 | Automated model switching | HEARTBEAT edit + VPS cron | — |
| 4 | Deploy everything | Deploy (VPS) | 1, 2, 3 |
| 5 | Live dashboard pages | New feature (jimbo-api + site) | — (parallel) |
| 6 | Email digest tuning | Investigation | 2, 4 |

Tasks 1-3 can run in parallel. Task 4 deploys them. Task 5 is independent (different repos). Task 6 needs the pipeline running.

---

## VPS Manual Steps Checklist

These require SSH access and can't be automated from this repo:

- [ ] Add model-swap cron entries to VPS root crontab (Task 3)
- [ ] Add `SANDBOX_WORKSPACE` env to notes-triage-api systemd unit (Task 5e)
- [ ] Add `/api/dashboard` and `/api/dashboard/*` Caddy routes (Task 5e)
- [ ] Debug Google Calendar OAuth if still failing (separate investigation)
