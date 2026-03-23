# Calendar Configuration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let Marvin choose which Google Calendars Jimbo processes, with optional tags (e.g., "options", "airbnb") that affect how events are presented in the briefing.

**Architecture:** Two JSON settings (`calendar_available`, `calendar_config`) stored in the existing jimbo-api settings table. Pipeline pushes the calendar list; UI reads/writes the config; calendar-helper.py reads the whitelist at event-fetch time. No new tables, no new API endpoints beyond settings.

**Tech Stack:** Python 3.11 stdlib (sandbox scripts), TypeScript/Hono (jimbo-api), React/Astro (site), SCSS/CSS classes (AdminStyles)

**Spec:** `docs/superpowers/specs/2026-03-23-calendar-config-design.md`

**Repos involved:**
- `~/development/openclaw` — calendar-helper.py, briefing-prep.py, briefing skill
- `~/development/jimbo/jimbo-api` — settings service (small fix)
- `~/development/site` — calendar admin page

**Deploy order:** jimbo-api → sandbox scripts (rsync) → site (git push) → skill (skills-push.sh) → seed data → configure

---

### Task 1: Suppress Telegram notifications for large settings (jimbo-api)

The settings service sends Telegram notifications including the full value on every upsert. `calendar_available` is ~3KB of JSON — this would spam Telegram twice daily. Skip notification for known bulk keys.

**Files:**
- Modify: `~/development/jimbo/jimbo-api/src/services/settings.ts:23-31`

- [ ] **Step 1: Add notification skip list**

In `upsertSetting`, skip `notifySettingUpdate` for keys that are bulk data:

```typescript
const SILENT_KEYS = new Set(['calendar_available', 'calendar_config']);

export function upsertSetting(key: string, value: string): Setting {
  const db = getDb();
  db.prepare(
    `INSERT INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now'))
     ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = datetime('now')`
  ).run(key, value);

  if (!SILENT_KEYS.has(key)) {
    notifySettingUpdate(key, value);
  }
  return getSetting(key)!;
}
```

- [ ] **Step 2: Test manually**

```bash
cd ~/development/jimbo/jimbo-api
npm run build
```

Verify it compiles. No unit test needed — this is a 2-line guard on an existing function.

- [ ] **Step 3: Deploy to VPS**

```bash
git add src/services/settings.ts
git commit -m "fix: suppress telegram notifications for bulk settings"
git push
ssh jimbo 'cd ~/development/jimbo/jimbo-api && git pull && npm run build && cp -r dist/* . && sudo systemctl restart jimbo-api'
```

- [ ] **Step 4: Verify**

Note: all `curl` commands in this plan use `$API_KEY`. Source it first: `export API_KEY=$(grep API_KEY /opt/openclaw.env | cut -d= -f2)` on VPS, or read from project memory locally.

```bash
curl -sk -X PUT -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"value": "test"}' \
  "https://167.99.206.214/api/settings/calendar_available"
```

Check Telegram — no notification should arrive. Then clean up:

```bash
# Verify it was saved
curl -sk -H "X-API-Key: $API_KEY" \
  "https://167.99.206.214/api/settings/calendar_available"
```

---

### Task 2: Add `--whitelist` flag to calendar-helper.py (sandbox)

Add the ability for `list-events` to read enabled calendar IDs from the jimbo-api settings.

**Files:**
- Modify: `~/development/openclaw/workspace/calendar-helper.py`

- [ ] **Step 1: Add `--whitelist` flag to argparse**

In the `list-events` subparser (after `--primary-only`):

```python
le.add_argument("--whitelist", action="store_true",
    help="Read enabled calendars from jimbo-api settings (requires JIMBO_API_URL and JIMBO_API_KEY)")
```

- [ ] **Step 2: Add helper function to read settings from API**

Add above `cmd_list_calendars`:

```python
def get_setting_from_api(key):
    """Read a single setting from jimbo-api. Returns the value string, or None on failure."""
    api_url = os.environ.get("JIMBO_API_URL")
    api_key = os.environ.get("JIMBO_API_KEY")
    if not api_url or not api_key:
        print(f"WARNING: JIMBO_API_URL or JIMBO_API_KEY not set, cannot read {key}", file=sys.stderr)
        return None
    try:
        req = urllib.request.Request(
            f"{api_url}/api/settings/{key}",
            headers={"X-API-Key": api_key},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            return data.get("value")
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as e:
        print(f"WARNING: Failed to read {key} from API: {e}", file=sys.stderr)
        return None
```

- [ ] **Step 3: Update `cmd_list_events` to handle `--whitelist`**

In `cmd_list_events`, replace the calendar ID selection block. The current logic is:

```python
if calendar_ids is None:
    cal_list = api_request(access_token, "users/me/calendarList")
    if args.primary_only:
        calendar_ids = [
            c["id"] for c in cal_list.get("items", [])
            if c.get("primary") or c.get("accessRole") == "owner"
        ]
    else:
        calendar_ids = [c["id"] for c in cal_list.get("items", [])]
```

Replace with:

```python
# Track tags for each calendar (from whitelist config)
calendar_tags = {}

if calendar_ids is None:
    if args.whitelist:
        # Read whitelist from jimbo-api
        config_str = get_setting_from_api("calendar_config")
        if config_str:
            try:
                config = json.loads(config_str)
                calendars = config.get("calendars", {})
                calendar_ids = [cid for cid, cfg in calendars.items() if cfg.get("enabled")]
                calendar_tags = {cid: cfg.get("tag") for cid, cfg in calendars.items() if cfg.get("enabled")}
            except (json.JSONDecodeError, AttributeError):
                print("WARNING: calendar_config is invalid JSON, falling back to --primary-only", file=sys.stderr)
                calendar_ids = None

    if calendar_ids is None:
        # Fallback: fetch from Google API
        cal_list = api_request(access_token, "users/me/calendarList")
        if args.primary_only or args.whitelist:
            # --whitelist falls back here if config missing/invalid
            calendar_ids = [
                c["id"] for c in cal_list.get("items", [])
                if c.get("primary") or c.get("accessRole") == "owner"
            ]
            if args.whitelist:
                print("WARNING: No calendar_config found, using --primary-only fallback", file=sys.stderr)
        else:
            calendar_ids = [c["id"] for c in cal_list.get("items", [])]
```

- [ ] **Step 4: Add tag field to event output**

In the event append block, add the tag:

```python
all_events.append({
    "calendar": cal_id,
    "summary": summary,
    "start": start_val,
    "end": end_val,
    "location": event.get("location", ""),
    "status": event.get("status", ""),
    "html_link": event.get("htmlLink", ""),
    "tag": calendar_tags.get(cal_id),
})
```

- [ ] **Step 5: Test locally**

```bash
# Without whitelist (should work as before)
python3 workspace/calendar-helper.py list-events --days 1 --primary-only | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'{len(d)} events')"

# With whitelist (will fall back since no API locally — check stderr for warning)
JIMBO_API_URL=http://localhost:9999 JIMBO_API_KEY=test \
  python3 workspace/calendar-helper.py list-events --days 1 --whitelist 2>&1 | head -5
```

- [ ] **Step 6: Commit**

```bash
git add workspace/calendar-helper.py
git commit -m "feat: add --whitelist flag to calendar-helper.py"
```

---

### Task 3: Add `put_setting` helper and calendar sync to briefing-prep.py (sandbox)

Add a helper to push settings to jimbo-api, then add a new pipeline step to sync the calendar list.

**Files:**
- Modify: `~/development/openclaw/workspace/briefing-prep.py`

- [ ] **Step 1: Ensure urllib imports exist**

Check the imports at the top of `briefing-prep.py`. If `urllib.request` and `urllib.error` are not imported, add:

```python
import urllib.request
import urllib.error
```

- [ ] **Step 2: Add `put_setting` helper function**

Add near the top of the file, after imports:

```python
def put_setting(key, value_str):
    """PUT a string value to jimbo-api settings. value_str must be a string."""
    api_url = os.environ.get("JIMBO_API_URL")
    api_key = os.environ.get("JIMBO_API_KEY")
    if not api_url or not api_key:
        return False
    try:
        body = json.dumps({"value": value_str}).encode()
        req = urllib.request.Request(
            f"{api_url}/api/settings/{key}",
            data=body, method="PUT",
            headers={"Content-Type": "application/json", "X-API-Key": api_key},
        )
        urllib.request.urlopen(req, timeout=10)
        return True
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        print(f"WARNING: Failed to PUT setting {key}: {e}", file=sys.stderr)
        return False
```

- [ ] **Step 3: Add Step 0 — calendar list sync**

Insert immediately before the `# --- Step 4: Calendar ---` comment in `run_pipeline`:

```python
# --- Step 0: Sync calendar list to API ---
if not dry_run:
    result = subprocess.run(
        [sys.executable, os.path.join(_script_dir, "calendar-helper.py"), "list-calendars"],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode == 0:
        if put_setting("calendar_available", result.stdout.strip()):
            pipeline_status["calendar_sync"] = {"status": "ok"}
        else:
            pipeline_status["calendar_sync"] = {"status": "failed", "error": "API PUT failed"}
    else:
        pipeline_status["calendar_sync"] = {"status": "failed", "error": result.stderr.strip()[:200]}
else:
    pipeline_status["calendar_sync"] = {"status": "skipped (dry-run)"}
```

- [ ] **Step 4: Change Step 4 to use `--whitelist`**

Find the existing calendar step and change `"--primary-only"` to `"--whitelist"`:

```python
# --- Step 4: Calendar ---
if not dry_run:
    result = subprocess.run(
        [sys.executable, os.path.join(_script_dir, "calendar-helper.py"),
         "list-events", "--days", "1", "--whitelist"],
        capture_output=True, text=True, timeout=30,
    )
```

- [ ] **Step 5: Commit**

```bash
git add workspace/briefing-prep.py
git commit -m "feat: sync calendar list to API and use whitelist in pipeline"
```

---

### Task 4: Deploy sandbox scripts to VPS

Push the updated calendar-helper.py and briefing-prep.py to the VPS.

**Files:**
- Uses: `~/development/openclaw/scripts/workspace-push.sh`

- [ ] **Step 1: Run workspace-push.sh**

```bash
./scripts/workspace-push.sh
```

This rsyncs all workspace files (including calendar-helper.py and briefing-prep.py) to the VPS.

- [ ] **Step 2: Seed calendar_available by running the pipeline step manually**

```bash
ssh jimbo 'export $(grep -v "^#" /opt/openclaw.env | xargs) && \
  sudo -E -u openclaw HOME=/home/openclaw \
  docker exec -i openclaw-sandbox python3 /workspace/calendar-helper.py list-calendars'
```

Check the output looks right (36 calendars as JSON). Then push it to the API:

```bash
# Grab the output and PUT it to settings
ssh jimbo 'export $(grep -v "^#" /opt/openclaw.env | xargs) && \
  CALS=$(sudo -E -u openclaw HOME=/home/openclaw \
    docker exec -i openclaw-sandbox python3 /workspace/calendar-helper.py list-calendars) && \
  curl -sk -X PUT -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
    -d "{\"value\": $(echo "$CALS" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))")}" \
    "https://167.99.206.214/api/settings/calendar_available"'
```

- [ ] **Step 3: Verify the setting was saved**

```bash
curl -sk -H "X-API-Key: $API_KEY" \
  "https://167.99.206.214/api/settings/calendar_available" | python3 -c "
import json, sys
data = json.load(sys.stdin)
cals = json.loads(data['value'])
print(f'{len(cals)} calendars synced, updated_at: {data[\"updated_at\"]}')"
```

Expected: `36 calendars synced, updated_at: 2026-03-23 ...`

- [ ] **Step 4: Commit deploy note**

No code change — just verify the deploy worked.

---

### Task 5: Build calendar admin page (site)

Create the Astro page, React component, and hook for the calendar configuration UI.

**Files:**
- Create: `~/development/site/src/pages/app/jimbo/calendar.astro`
- Create: `~/development/site/src/components/admin/CalendarAdmin.tsx`
- Create: `~/development/site/src/hooks/useCalendarApi.ts`
- Modify: `~/development/site/src/components/admin/AdminTabs.tsx:3-13`

- [ ] **Step 1: Add Calendar tab to AdminTabs**

In `~/development/site/src/components/admin/AdminTabs.tsx`, add to the TABS array after Settings:

```typescript
const TABS = [
  { label: 'Health', href: '/app/jimbo/health' },
  { label: 'Vault Notes', href: '/app/jimbo/vault-notes' },
  { label: 'Context', href: '/app/jimbo/context' },
  { label: 'Activity', href: '/app/jimbo/activity' },
  { label: 'Triage', href: '/app/jimbo/triage' },
  { label: 'Settings', href: '/app/jimbo/settings' },
  { label: 'Calendar', href: '/app/jimbo/calendar' },
  { label: 'Emails', href: '/app/jimbo/emails' },
  { label: 'Costs', href: '/app/jimbo/costs' },
  { label: 'Status', href: '/app/jimbo/status' },
] as const;
```

- [ ] **Step 2: Create the hook**

Create `~/development/site/src/hooks/useCalendarApi.ts`:

```typescript
import { useState, useEffect, useCallback } from 'react';

const API_URL = import.meta.env.PUBLIC_JIMBO_API_URL || 'http://localhost:3100';
const API_KEY = import.meta.env.PUBLIC_JIMBO_API_KEY || '';

function headers(): HeadersInit {
  return {
    'Content-Type': 'application/json',
    'X-API-Key': API_KEY,
  };
}

export interface CalendarEntry {
  id: string;
  summary: string;
  access_role: string;
  primary?: boolean;
}

export interface CalendarItemConfig {
  enabled: boolean;
  tag: string | null;
}

export interface CalendarConfig {
  calendars: Record<string, CalendarItemConfig>;
}

export interface CalendarViewItem extends CalendarEntry {
  enabled: boolean;
  tag: string | null;
}

export function useCalendarApi() {
  const [available, setAvailable] = useState<CalendarEntry[]>([]);
  const [config, setConfig] = useState<CalendarConfig>({ calendars: {} });
  const [lastSynced, setLastSynced] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // Fetch both settings in parallel
      const [availRes, configRes] = await Promise.all([
        fetch(`${API_URL}/api/settings/calendar_available`, { headers: headers() }),
        fetch(`${API_URL}/api/settings/calendar_config`, { headers: headers() }),
      ]);

      if (availRes.ok) {
        const availData = await availRes.json();
        const parsed = JSON.parse(availData.value || '[]');
        setAvailable(parsed);
        setLastSynced(availData.updated_at || null);
      }

      if (configRes.ok) {
        const configData = await configRes.json();
        const parsed = JSON.parse(configData.value || '{"calendars":{}}');
        setConfig(parsed);
      }
      // 404 for config is fine — means no config saved yet
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  }, []);

  const saveConfig = useCallback(async (newConfig: CalendarConfig) => {
    setSaving(true);
    setError(null);
    setConfig(newConfig); // optimistic
    try {
      const res = await fetch(`${API_URL}/api/settings/calendar_config`, {
        method: 'PUT',
        headers: headers(),
        body: JSON.stringify({ value: JSON.stringify(newConfig) }),
      });
      if (!res.ok) throw new Error(`Failed to save: ${res.status}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error');
      await fetchData(); // rollback
    } finally {
      setSaving(false);
    }
  }, [fetchData]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Merge available + config into a view
  const calendars: CalendarViewItem[] = available.map((cal) => ({
    ...cal,
    enabled: config.calendars[cal.id]?.enabled ?? false,
    tag: config.calendars[cal.id]?.tag ?? null,
  }));

  // Sort: primary first, then owners, then readers
  calendars.sort((a, b) => {
    if (a.primary && !b.primary) return -1;
    if (!a.primary && b.primary) return 1;
    if (a.access_role === 'owner' && b.access_role !== 'owner') return -1;
    if (a.access_role !== 'owner' && b.access_role === 'owner') return 1;
    return a.summary.localeCompare(b.summary);
  });

  const ownerCalendars = calendars.filter((c) => c.access_role === 'owner' || c.primary);
  const subscribedCalendars = calendars.filter((c) => c.access_role !== 'owner' && !c.primary);

  // Collect existing tags for the dropdown
  const existingTags = new Set<string>();
  Object.values(config.calendars).forEach((cfg) => {
    if (cfg.tag) existingTags.add(cfg.tag);
  });
  const tagOptions = Array.from(new Set([...existingTags, 'options', 'airbnb', 'work'])).sort();

  return {
    ownerCalendars,
    subscribedCalendars,
    config,
    tagOptions,
    lastSynced,
    loading,
    saving,
    error,
    saveConfig,
    fetchData,
  };
}
```

- [ ] **Step 3: Create the component**

Create `~/development/site/src/components/admin/CalendarAdmin.tsx`:

```tsx
import { useState } from 'react';
import { AdminPage } from './AdminPage';
import { ApiErrorBanner } from './ApiErrorBanner';
import { useCalendarApi } from '../../hooks/useCalendarApi';
import type { CalendarConfig, CalendarViewItem } from '../../hooks/useCalendarApi';

function formatAge(dateStr: string | null): string {
  if (!dateStr) return 'never';
  const diff = Date.now() - new Date(dateStr + 'Z').getTime();
  const hours = Math.floor(diff / 3600000);
  if (hours < 1) return 'just now';
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export function CalendarAdmin() {
  const {
    ownerCalendars,
    subscribedCalendars,
    config,
    tagOptions,
    lastSynced,
    loading,
    saving,
    error,
    saveConfig,
  } = useCalendarApi();

  const [localConfig, setLocalConfig] = useState<CalendarConfig | null>(null);
  const [editingCustomTag, setEditingCustomTag] = useState<string | null>(null);
  const [customTagValue, setCustomTagValue] = useState('');

  // Use local edits if dirty, otherwise show saved config
  const activeConfig = localConfig ?? config;
  const isDirty = localConfig !== null;

  const toggleEnabled = (calId: string, currentlyEnabled: boolean) => {
    const prev = localConfig ?? { ...config };
    const calendars = { ...prev.calendars };
    calendars[calId] = {
      enabled: !currentlyEnabled,
      tag: calendars[calId]?.tag ?? null,
    };
    setLocalConfig({ calendars });
  };

  const setTag = (calId: string, tag: string | null) => {
    const prev = localConfig ?? { ...config };
    const calendars = { ...prev.calendars };
    calendars[calId] = {
      enabled: calendars[calId]?.enabled ?? false,
      tag,
    };
    setLocalConfig({ calendars });
  };

  const handleSave = async () => {
    if (!localConfig) return;
    await saveConfig(localConfig);
    setLocalConfig(null);
  };

  const handleReset = () => {
    setLocalConfig(null);
  };

  const getEnabled = (calId: string) => activeConfig.calendars[calId]?.enabled ?? false;
  const getTag = (calId: string) => activeConfig.calendars[calId]?.tag ?? null;

  const renderTable = (calendars: CalendarViewItem[], title: string) => {
    if (calendars.length === 0) return null;
    return (
      <div style={{ marginBottom: 'var(--space-4)' }}>
        <h3 style={{ fontSize: 'var(--text-sm)', fontWeight: 'var(--weight-bold)' as any, marginBottom: 'var(--space-2)' }}>
          {title}
        </h3>
        <table className="admin-table">
          <thead>
            <tr>
              <th style={{ width: '3rem' }}>On</th>
              <th>Calendar</th>
              <th style={{ width: '10rem' }}>Tag</th>
            </tr>
          </thead>
          <tbody>
            {calendars.map((cal) => {
              const enabled = getEnabled(cal.id);
              const tag = getTag(cal.id);
              return (
                <tr key={cal.id}>
                  <td>
                    <input
                      type="checkbox"
                      checked={enabled}
                      onChange={() => toggleEnabled(cal.id, enabled)}
                    />
                  </td>
                  <td>
                    <span>{cal.summary}</span>
                    {cal.primary && (
                      <span className="muted" style={{ marginLeft: 'var(--space-1)' }}>(primary)</span>
                    )}
                  </td>
                  <td>
                    {editingCustomTag === cal.id ? (
                      <input
                        type="text"
                        className="admin-form__input"
                        placeholder="tag name"
                        value={customTagValue}
                        onChange={(e) => setCustomTagValue(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' && customTagValue) {
                            setTag(cal.id, customTagValue);
                            setEditingCustomTag(null);
                          }
                          if (e.key === 'Escape') setEditingCustomTag(null);
                        }}
                        onBlur={() => {
                          if (customTagValue) setTag(cal.id, customTagValue);
                          setEditingCustomTag(null);
                        }}
                        autoFocus
                        style={{ fontSize: 'var(--text-xs)', padding: '2px 4px' }}
                      />
                    ) : (
                      <select
                        className="admin-form__input"
                        value={tag ?? ''}
                        onChange={(e) => {
                          if (e.target.value === '__custom') {
                            setCustomTagValue('');
                            setEditingCustomTag(cal.id);
                          } else {
                            setTag(cal.id, e.target.value || null);
                          }
                        }}
                        style={{ fontSize: 'var(--text-xs)', padding: '2px 4px' }}
                      >
                        <option value="">—</option>
                        {tagOptions.map((t) => (
                          <option key={t} value={t}>{t}</option>
                        ))}
                        <option value="__custom">custom...</option>
                      </select>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    );
  };

  return (
    <AdminPage
      activeTab="/app/jimbo/calendar"
      breadcrumbs={[{ label: 'Calendar' }]}
      actions={
        <span className="muted" style={{ fontSize: 'var(--text-xs)' }}>
          Last synced: {formatAge(lastSynced)}
        </span>
      }
    >
      <ApiErrorBanner error={error} />
      {loading ? (
        <div className="admin-loading">Loading...</div>
      ) : ownerCalendars.length === 0 && subscribedCalendars.length === 0 ? (
        <div className="admin-empty">
          No calendars found. The pipeline needs to run at least once to sync the calendar list.
        </div>
      ) : (
        <>
          {renderTable(ownerCalendars, 'Your calendars')}
          {renderTable(subscribedCalendars, 'Subscribed calendars')}
          <div style={{ display: 'flex', gap: 'var(--space-2)', marginTop: 'var(--space-3)' }}>
            <button
              className="admin-btn admin-btn--primary"
              onClick={handleSave}
              disabled={!isDirty || saving}
            >
              {saving ? 'Saving...' : 'Save'}
            </button>
            {isDirty && (
              <button className="admin-btn" onClick={handleReset}>
                Reset
              </button>
            )}
          </div>
        </>
      )}
    </AdminPage>
  );
}
```

- [ ] **Step 4: Create the Astro page**

Create `~/development/site/src/pages/app/jimbo/calendar.astro`:

```astro
---
import AppLayout from '../../../layouts/AppLayout.astro';
import AdminStyles from '../../../components/admin/AdminStyles.astro';
import { CalendarAdmin } from '../../../components/admin/CalendarAdmin';
---

<AppLayout title="Calendar — Jimbo">
  <AdminStyles />
  <CalendarAdmin client:load />
</AppLayout>
```

- [ ] **Step 5: Verify it builds**

```bash
cd ~/development/site
npm run build
```

Fix any TypeScript errors.

- [ ] **Step 6: Commit**

```bash
cd ~/development/site
git add src/pages/app/jimbo/calendar.astro src/components/admin/CalendarAdmin.tsx src/hooks/useCalendarApi.ts src/components/admin/AdminTabs.tsx
git commit -m "feat: calendar config admin page with whitelist and tags"
```

- [ ] **Step 7: Deploy site**

```bash
git push
```

Cloudflare Workers auto-deploys on push.

---

### Task 6: Update daily-briefing skill to use calendar tags

Replace the hardcoded marbar.alt note with tag-based guidance.

**Files:**
- Modify: `~/development/openclaw/skills/daily-briefing/SKILL.md:61`

- [ ] **Step 1: Update the calendar note**

Replace line 61:

```
**Calendar note:** Marvin has two Google accounts on his calendar. Events from `marbar.alt@gmail.com` are an "options" calendar — nudges about events that *might* be happening, not commitments. Treat them as lower-confidence possibilities, not fixed schedule items.
```

With:

```
**Calendar tags:** Events in `briefing-input.json` may include a `tag` field from the calendar config:
- `tag: "options"` — this is an "options" calendar (e.g. marbar.alt). These are nudges about events that *might* be happening, not commitments. Present as "From your options calendar" and treat as lower-confidence possibilities.
- `tag: "airbnb"` — Airbnb booking/hosting events. Present with hosting context.
- `tag: null` or missing — a firm commitment. Present normally.
- Any other tag value — mention the tag for context (e.g., "from your [tag] calendar").
```

- [ ] **Step 2: Commit**

```bash
cd ~/development/openclaw
git add skills/daily-briefing/SKILL.md
git commit -m "feat: update briefing skill to use calendar tags"
```

- [ ] **Step 3: Deploy skill to VPS**

```bash
./scripts/skills-push.sh
```

---

### Task 7: Configure calendars and verify end-to-end

Marvin uses the new UI to select which calendars to include, then we verify the pipeline uses the whitelist.

- [ ] **Step 1: Open the calendar config page**

Navigate to the site's calendar admin page and configure:
- Enable: `marvinbarretto@gmail.com` (primary, no tag)
- Enable: `marbar.alt@gmail.com` (tag: `options`)
- Enable: any other calendars Marvin wants (Airbnb, Travel, Birthdays, etc.)
- Disable: everything else

Save.

- [ ] **Step 2: Verify the config was saved**

```bash
curl -sk -H "X-API-Key: $API_KEY" \
  "https://167.99.206.214/api/settings/calendar_config" | python3 -m json.tool
```

- [ ] **Step 3: Test calendar-helper.py with the whitelist on VPS**

```bash
ssh jimbo 'export $(grep -v "^#" /opt/openclaw.env | xargs) && \
  sudo -E -u openclaw HOME=/home/openclaw \
  docker exec -i openclaw-sandbox python3 /workspace/calendar-helper.py list-events --days 1 --whitelist' \
  | python3 -c "import json,sys; events=json.load(sys.stdin); print(f'{len(events)} events'); [print(f\"  {e['summary']} (tag: {e.get('tag')}, cal: {e['calendar'][:20]})\") for e in events[:10]]"
```

Expected: fewer events than before (only from enabled calendars), with `tag` field populated.

- [ ] **Step 4: Wait for next pipeline run (or trigger manually)**

Either wait for the next cron run (06:15 or 14:15) or trigger manually:

```bash
ssh jimbo 'export $(grep -v "^#" /opt/openclaw.env | xargs) && \
  sudo -E -u openclaw HOME=/home/openclaw \
  docker exec -i openclaw-sandbox python3 /workspace/briefing-prep.py morning --dry-run'
```

Check that `briefing-input.json` only contains events from enabled calendars with tag fields.

- [ ] **Step 5: Commit completion note**

No code change — just verify the full flow works end-to-end.
