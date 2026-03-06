# Alert Improvements + Configurable Email Fetch — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix misleading hourly alerts (credits, briefing) and make email fetch frequency configurable from the site UI.

**Architecture:** Three independent workstreams: (1) fix alert-check.py in openclaw repo, (2) add settings API to jimbo-api, (3) add settings UI to site. Plus a new email-fetch-cron.py wrapper and updated VPS cron.

**Tech Stack:** Python 3.11 stdlib (alert-check, email-fetch-cron), Hono/TypeScript/better-sqlite3 (jimbo-api), Astro/React/SCSS (site)

**Repos:**
- `openclaw/` — `/Users/marvinbarretto/development/openclaw/`
- `jimbo-api/` — `/Users/marvinbarretto/development/jimbo/notes-triage-api/`
- `site/` — `/Users/marvinbarretto/development/site/`

---

## Task 1: Fix credits check in alert-check.py

**Files:**
- Modify: `openclaw/workspace/alert-check.py:127-165`

**Step 1: Write the updated `check_credits` function**

Replace the existing function. Drop the `remaining` calculation and `CREDIT_ALERT_THRESHOLD`. Just report usage:

```python
def check_credits():
    """Check OpenRouter credit usage. Returns (ok, summary)."""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return False, "OPENROUTER_API_KEY not set"

    url = "https://openrouter.ai/api/v1/auth/key"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except (urllib.error.HTTPError, urllib.error.URLError, OSError) as e:
        return False, f"OpenRouter API request failed: {e}"

    info = data.get("data", data)
    usage = info.get("usage")

    if usage is None:
        return False, f"unexpected OpenRouter response: {json.dumps(data)}"

    return True, f"OpenRouter: ${usage:.2f} used"
```

Also remove the `CREDIT_ALERT_THRESHOLD = 1.0` constant at line 36.

**Step 2: Update `check_status` to use info icon for credits**

In `check_status()`, the credits check should always show ℹ️ instead of ✅/❌ (it's informational, not pass/fail). Change the icon logic:

```python
def check_status():
    """Run all checks and return a combined one-line summary."""
    checks = [
        ("digest", check_digest),
        ("briefing", check_briefing),
        ("credits", check_credits),
    ]

    parts = []
    any_bad = False
    for name, fn in checks:
        try:
            ok, summary = fn()
        except Exception as e:
            ok, summary = False, f"{name} error: {e}"

        if name == "credits":
            # Credits is informational, not pass/fail
            icon = "\u2139\ufe0f" if ok else "\u274c"
        else:
            icon = "\u2705" if ok else "\u274c"
            if not ok:
                any_bad = True

        parts.append(f"{icon} {summary}")

    return not any_bad, " | ".join(parts)
```

**Step 3: Commit**

```bash
cd /Users/marvinbarretto/development/openclaw
git add workspace/alert-check.py
git commit -m "fix: report OpenRouter usage only, drop misleading balance calculation"
```

---

## Task 2: Make briefing check time-aware in alert-check.py

**Files:**
- Modify: `openclaw/workspace/alert-check.py:81-124`

**Step 1: Update `check_briefing` with grace period**

Replace the existing function. Before 08:00 UTC, report pending instead of failure:

```python
BRIEFING_GRACE_HOUR = 8  # UTC hour after which missing briefing is an error

def check_briefing():
    """Check experiment-tracker.db has a run with today's date. Returns (ok, summary)."""
    current_hour = now_utc().hour

    if not os.path.exists(TRACKER_DB_PATH):
        if current_hour < BRIEFING_GRACE_HOUR:
            return True, "briefing pending"
        return False, "experiment-tracker.db not found"

    try:
        db = sqlite3.connect(TRACKER_DB_PATH)
        db.row_factory = sqlite3.Row
    except sqlite3.Error as e:
        return False, f"experiment-tracker.db unreadable: {e}"

    today = now_utc().strftime("%Y-%m-%d")

    try:
        row = db.execute(
            "SELECT COUNT(*) as count FROM runs WHERE timestamp LIKE ?",
            (f"{today}%",),
        ).fetchone()

        if row["count"] == 0:
            db.close()
            if current_hour < BRIEFING_GRACE_HOUR:
                return True, "briefing pending"
            return False, f"briefing missing for {today}"

        # Get summary of today's runs
        runs = db.execute(
            """SELECT task_id, COUNT(*) as count,
                      SUM(output_tokens) as total_output_tokens
               FROM runs WHERE timestamp LIKE ?
               GROUP BY task_id""",
            (f"{today}%",),
        ).fetchall()

        db.close()

        parts = []
        for r in runs:
            parts.append(f"{r['task_id']}: {r['count']} run(s)")

        summary = f"briefing ran ({', '.join(parts)})"
        return True, summary

    except sqlite3.Error as e:
        db.close()
        return False, f"experiment-tracker.db query failed: {e}"
```

**Step 2: Update `check_status` icon for pending briefing**

The pending state uses ⏳ instead of ✅. Update the icon logic in `check_status`:

```python
        if name == "credits":
            icon = "\u2139\ufe0f" if ok else "\u274c"
        elif name == "briefing" and ok and "pending" in summary:
            icon = "\u23f3"  # hourglass for pending
        else:
            icon = "\u2705" if ok else "\u274c"
            if not ok:
                any_bad = True
```

**Step 3: Commit**

```bash
cd /Users/marvinbarretto/development/openclaw
git add workspace/alert-check.py
git commit -m "fix: make briefing check time-aware, pending before 08:00 UTC"
```

---

## Task 3: Update digest check to show volume not freshness

**Files:**
- Modify: `openclaw/workspace/alert-check.py:48-78`

**Step 1: Update `check_digest` to report volume**

Replace the freshness-based message with email count and new count:

```python
def check_digest():
    """Check email-digest.json exists and report volume. Returns (ok, summary)."""
    if not os.path.exists(DIGEST_PATH):
        return False, "email-digest.json not found"

    try:
        with open(DIGEST_PATH) as f:
            digest = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return False, f"email-digest.json unreadable: {e}"

    generated_at = digest.get("generated_at")
    if not generated_at:
        return False, "email-digest.json missing generated_at field"

    try:
        gen_time = datetime.datetime.fromisoformat(generated_at)
        if gen_time.tzinfo is None:
            gen_time = gen_time.replace(tzinfo=datetime.timezone.utc)
    except ValueError:
        return False, f"email-digest.json has invalid generated_at: {generated_at}"

    email_count = len(digest.get("items", []))
    previous_count = digest.get("previous_count")

    if previous_count is not None:
        new_count = max(0, email_count - previous_count)
        return True, f"digest: {email_count} emails today ({new_count} new)"
    else:
        return True, f"digest: {email_count} emails today"
```

Also remove the `MAX_DIGEST_AGE_HOURS = 25` constant — no longer needed.

**Step 2: Commit**

```bash
cd /Users/marvinbarretto/development/openclaw
git add workspace/alert-check.py
git commit -m "feat: show email volume in digest check instead of freshness"
```

---

## Task 4: Add settings table to jimbo-api database

**Files:**
- Modify: `jimbo-api/src/db/index.ts:5-31`

**Step 1: Add settings table to SCHEMA**

Append to the existing `SCHEMA` string in `src/db/index.ts`, after the context_items table:

```sql
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

INSERT OR IGNORE INTO settings (key, value) VALUES ('email_fetch_interval_hours', '1');
```

**Step 2: Commit**

```bash
cd /Users/marvinbarretto/development/jimbo/notes-triage-api
git add src/db/index.ts
git commit -m "feat: add settings table with email_fetch_interval_hours default"
```

---

## Task 5: Add settings types to jimbo-api

**Files:**
- Create: `jimbo-api/src/types/settings.ts`

**Step 1: Write the types file**

```typescript
export interface Setting {
  key: string;
  value: string;
  updated_at: string;
}

export interface SettingsMap {
  [key: string]: string;
}
```

**Step 2: Commit**

```bash
cd /Users/marvinbarretto/development/jimbo/notes-triage-api
git add src/types/settings.ts
git commit -m "feat: add settings types"
```

---

## Task 6: Add settings service to jimbo-api

**Files:**
- Create: `jimbo-api/src/services/settings.ts`

**Step 1: Write the settings service**

Follow the context service pattern — CRUD with Telegram notification:

```typescript
import { getDb } from '../db/index.js';
import type { Setting, SettingsMap } from '../types/settings.js';

let notifyTimer: ReturnType<typeof setTimeout> | null = null;
const pendingNotifications = new Set<string>();

export function getAllSettings(): SettingsMap {
  const db = getDb();
  const rows = db.prepare('SELECT key, value FROM settings ORDER BY key').all() as Setting[];
  const map: SettingsMap = {};
  for (const row of rows) {
    map[row.key] = row.value;
  }
  return map;
}

export function getSetting(key: string): Setting | null {
  const db = getDb();
  const row = db.prepare('SELECT key, value, updated_at FROM settings WHERE key = ?').get(key) as Setting | undefined;
  return row || null;
}

export function upsertSetting(key: string, value: string): Setting {
  const db = getDb();
  db.prepare(
    `INSERT INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now'))
     ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = datetime('now')`
  ).run(key, value);

  notifySettingUpdate(key, value);
  return getSetting(key)!;
}

export function notifySettingUpdate(key: string, value: string): void {
  pendingNotifications.add(`${key} = ${value}`);

  if (notifyTimer) clearTimeout(notifyTimer);

  notifyTimer = setTimeout(() => {
    const changes = [...pendingNotifications];
    pendingNotifications.clear();
    notifyTimer = null;
    sendTelegramNotification(changes).catch(() => {});
  }, 2000);
}

async function sendTelegramNotification(changes: string[]): Promise<void> {
  const token = process.env.TELEGRAM_BOT_TOKEN;
  const chatId = process.env.TELEGRAM_CHAT_ID;
  if (!token || !chatId) return;

  const message = `⚙️ Settings updated: ${changes.join(', ')}`;

  const url = `https://api.telegram.org/bot${token}/sendMessage`;
  const body = JSON.stringify({ chat_id: chatId, text: message });

  try {
    await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body,
    });
  } catch {
    // Non-critical
  }
}
```

**Step 2: Commit**

```bash
cd /Users/marvinbarretto/development/jimbo/notes-triage-api
git add src/services/settings.ts
git commit -m "feat: add settings service with CRUD and Telegram notifications"
```

---

## Task 7: Add settings routes to jimbo-api

**Files:**
- Create: `jimbo-api/src/routes/settings.ts`
- Modify: `jimbo-api/src/index.ts:24-25`

**Step 1: Write the routes file**

```typescript
import { Hono } from 'hono';
import { getAllSettings, getSetting, upsertSetting } from '../services/settings.js';

const settings = new Hono();

// GET /settings — all settings as key-value map
settings.get('/', (c) => {
  return c.json(getAllSettings());
});

// GET /settings/:key — single setting
settings.get('/:key', (c) => {
  const setting = getSetting(c.req.param('key'));
  if (!setting) {
    return c.json({ error: 'Setting not found' }, 404);
  }
  return c.json(setting);
});

// PUT /settings/:key — upsert setting
settings.put('/:key', async (c) => {
  const { value } = await c.req.json<{ value: string }>();
  if (value === undefined || value === null) {
    return c.json({ error: 'value is required' }, 400);
  }
  const setting = upsertSetting(c.req.param('key'), String(value));
  return c.json(setting);
});

export default settings;
```

**Step 2: Register routes in `src/index.ts`**

Add import and route registration after the context route:

```typescript
import settings from './routes/settings.js';
```

```typescript
app.route('/api/settings', settings);
```

**Step 3: Commit**

```bash
cd /Users/marvinbarretto/development/jimbo/notes-triage-api
git add src/routes/settings.ts src/index.ts
git commit -m "feat: add settings API routes (GET all, GET one, PUT upsert)"
```

---

## Task 8: Write settings service tests

**Files:**
- Create: `jimbo-api/test/settings.test.ts`

**Step 1: Write the test file**

Follow the context.test.ts pattern exactly — temp DB, dynamic imports:

```typescript
import { describe, it, expect, beforeEach } from 'vitest';
import { mkdirSync } from 'node:fs';
import path from 'node:path';

const TEST_DB_DIR = './test/tmp-settings';
const TEST_DB_PATH = path.join(TEST_DB_DIR, 'test.db');
process.env.CONTEXT_DB_PATH = TEST_DB_PATH;

const { getDb } = await import('../src/db/index.js');
const { getAllSettings, getSetting, upsertSetting } = await import('../src/services/settings.js');

describe('settings service', () => {
  beforeEach(() => {
    mkdirSync(TEST_DB_DIR, { recursive: true });
    const db = getDb();
    db.exec('DELETE FROM settings');
  });

  describe('getAllSettings', () => {
    it('returns empty map when no settings', () => {
      const result = getAllSettings();
      expect(result).toEqual({});
    });

    it('returns all settings as key-value map', () => {
      const db = getDb();
      db.prepare("INSERT INTO settings (key, value) VALUES ('a', '1')").run();
      db.prepare("INSERT INTO settings (key, value) VALUES ('b', '2')").run();

      const result = getAllSettings();
      expect(result).toEqual({ a: '1', b: '2' });
    });
  });

  describe('getSetting', () => {
    it('returns null for missing key', () => {
      expect(getSetting('nonexistent')).toBeNull();
    });

    it('returns setting with metadata', () => {
      const db = getDb();
      db.prepare("INSERT INTO settings (key, value) VALUES ('test_key', 'test_value')").run();

      const result = getSetting('test_key');
      expect(result).not.toBeNull();
      expect(result!.key).toBe('test_key');
      expect(result!.value).toBe('test_value');
      expect(result!.updated_at).toBeDefined();
    });
  });

  describe('upsertSetting', () => {
    it('inserts new setting', () => {
      const result = upsertSetting('new_key', 'new_value');
      expect(result.key).toBe('new_key');
      expect(result.value).toBe('new_value');

      expect(getSetting('new_key')!.value).toBe('new_value');
    });

    it('updates existing setting', () => {
      upsertSetting('key', 'original');
      const result = upsertSetting('key', 'updated');
      expect(result.value).toBe('updated');

      expect(getSetting('key')!.value).toBe('updated');
    });

    it('updates updated_at on change', () => {
      const first = upsertSetting('key', 'v1');
      const second = upsertSetting('key', 'v2');
      // updated_at should be set (can't assert exact time, just presence)
      expect(second.updated_at).toBeDefined();
    });
  });
});
```

**Step 2: Run the tests**

```bash
cd /Users/marvinbarretto/development/jimbo/notes-triage-api
npx vitest run test/settings.test.ts
```

Expected: all tests pass.

**Step 3: Commit**

```bash
cd /Users/marvinbarretto/development/jimbo/notes-triage-api
git add test/settings.test.ts
git commit -m "test: add settings service tests"
```

---

## Task 9: Add settings types to site

**Files:**
- Create: `site/src/types/settings.ts`

**Step 1: Write the types**

```typescript
export interface Setting {
  key: string;
  value: string;
  updated_at: string;
}

export interface SettingsMap {
  [key: string]: string;
}
```

**Step 2: Commit**

```bash
cd /Users/marvinbarretto/development/site
git add src/types/settings.ts
git commit -m "feat: add settings types"
```

---

## Task 10: Add useSettingsApi hook to site

**Files:**
- Create: `site/src/hooks/useSettingsApi.ts`

**Step 1: Write the hook**

Follow the useContextApi pattern — same env vars, same auth header:

```typescript
import { useState, useEffect, useCallback } from 'react';
import type { Setting, SettingsMap } from '../types/settings';

const API_URL = import.meta.env.PUBLIC_CONTEXT_API_URL ||
                import.meta.env.PUBLIC_TRIAGE_API_URL ||
                'http://localhost:3100';
const API_KEY = import.meta.env.PUBLIC_CONTEXT_API_KEY ||
                import.meta.env.PUBLIC_TRIAGE_API_KEY || '';

const headers: Record<string, string> = {
  'Content-Type': 'application/json',
  'X-API-Key': API_KEY,
};

export function useSettingsApi() {
  const [settings, setSettings] = useState<SettingsMap>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchSettings = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/api/settings`, { headers });
      if (!res.ok) throw new Error(`Failed to fetch settings: ${res.status}`);
      const data: SettingsMap = await res.json();
      setSettings(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  }, []);

  const updateSetting = useCallback(async (key: string, value: string) => {
    setError(null);
    // Optimistic update
    setSettings((prev) => ({ ...prev, [key]: value }));
    try {
      const res = await fetch(`${API_URL}/api/settings/${key}`, {
        method: 'PUT',
        headers,
        body: JSON.stringify({ value }),
      });
      if (!res.ok) throw new Error(`Failed to update setting: ${res.status}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error');
      // Revert on failure
      await fetchSettings();
    }
  }, [fetchSettings]);

  useEffect(() => {
    fetchSettings();
  }, [fetchSettings]);

  return { settings, loading, error, updateSetting, fetchSettings };
}
```

**Step 2: Commit**

```bash
cd /Users/marvinbarretto/development/site
git add src/hooks/useSettingsApi.ts
git commit -m "feat: add useSettingsApi hook"
```

---

## Task 11: Add settings page and component to site

**Files:**
- Create: `site/src/pages/app/jimbo/settings.astro`
- Create: `site/src/components/settings/SettingsEditor.tsx`
- Create: `site/src/components/settings/SettingsEditor.scss`

**Step 1: Write the Astro page**

```astro
---
import AppLayout from '../../../layouts/AppLayout.astro';
import { SettingsEditor } from '../../../components/settings/SettingsEditor';
---

<AppLayout title="Settings">
  <SettingsEditor client:load />
</AppLayout>
```

**Step 2: Write the React component**

```tsx
import { useSettingsApi } from '../../hooks/useSettingsApi';
import { useState } from 'react';
import './SettingsEditor.scss';

export function SettingsEditor() {
  const { settings, loading, error, updateSetting } = useSettingsApi();
  const [pendingValues, setPendingValues] = useState<Record<string, string>>({});

  if (loading && Object.keys(settings).length === 0) {
    return <div className="settings-editor"><p>Loading settings...</p></div>;
  }

  const settingsConfig = [
    {
      key: 'email_fetch_interval_hours',
      label: 'Email fetch interval',
      description: 'How often to check for new emails (hours)',
      type: 'number' as const,
      min: 1,
      max: 24,
    },
  ];

  function handleChange(key: string, value: string) {
    setPendingValues((prev) => ({ ...prev, [key]: value }));
  }

  function handleSave(key: string) {
    const value = pendingValues[key];
    if (value !== undefined) {
      updateSetting(key, value);
      setPendingValues((prev) => {
        const next = { ...prev };
        delete next[key];
        return next;
      });
    }
  }

  function handleKeyDown(key: string, e: React.KeyboardEvent) {
    if (e.key === 'Enter') {
      handleSave(key);
    }
  }

  return (
    <div className="settings-editor">
      <h2>Jimbo Settings</h2>

      {error && <p className="settings-editor__error">{error}</p>}

      <div className="settings-editor__list">
        {settingsConfig.map((config) => {
          const currentValue = pendingValues[config.key] ?? settings[config.key] ?? '';
          const isDirty = pendingValues[config.key] !== undefined;

          return (
            <div key={config.key} className="settings-editor__item">
              <div className="settings-editor__item-header">
                <label className="settings-editor__label" htmlFor={config.key}>
                  {config.label}
                </label>
                <span className="settings-editor__description">{config.description}</span>
              </div>
              <div className="settings-editor__item-controls">
                <input
                  id={config.key}
                  type={config.type}
                  min={config.min}
                  max={config.max}
                  value={currentValue}
                  onChange={(e) => handleChange(config.key, e.target.value)}
                  onKeyDown={(e) => handleKeyDown(config.key, e)}
                  className="settings-editor__input"
                />
                {isDirty && (
                  <button
                    onClick={() => handleSave(config.key)}
                    className="settings-editor__save-btn"
                  >
                    Save
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
```

**Step 3: Write the SCSS**

```scss
.settings-editor {
  max-width: 640px;
  padding: var(--space-4) 0;

  h2 {
    font-size: var(--text-lg);
    font-weight: 600;
    margin-bottom: var(--space-6);
  }

  &__error {
    color: var(--color-accent);
    margin-bottom: var(--space-4);
    font-size: var(--text-sm);
  }

  &__list {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }

  &__item {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    padding: var(--space-4);
    border: 1px solid var(--color-border);
    border-radius: var(--border-radius);
    background: var(--color-surface);
  }

  &__item-header {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }

  &__label {
    font-weight: 600;
    font-size: var(--text-base);
  }

  &__description {
    font-size: var(--text-sm);
    color: var(--color-text-muted);
  }

  &__item-controls {
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }

  &__input {
    font-family: var(--font-mono);
    font-size: var(--text-base);
    padding: var(--space-2) var(--space-3);
    border: 1px solid var(--color-border);
    border-radius: var(--border-radius);
    background: var(--color-bg);
    color: var(--color-text);
    width: 6rem;

    &:focus {
      outline: 2px solid var(--color-accent);
      outline-offset: -1px;
    }
  }

  &__save-btn {
    font-family: var(--font-mono);
    font-size: var(--text-sm);
    padding: var(--space-2) var(--space-3);
    border: 1px solid var(--color-accent);
    border-radius: var(--border-radius);
    background: var(--color-accent);
    color: var(--color-white);
    cursor: pointer;
    transition: opacity var(--transition-fast);

    &:hover {
      opacity: 0.85;
    }
  }
}
```

**Step 4: Commit**

```bash
cd /Users/marvinbarretto/development/site
git add src/pages/app/jimbo/settings.astro src/components/settings/SettingsEditor.tsx src/components/settings/SettingsEditor.scss
git commit -m "feat: add settings page with email fetch interval control"
```

---

## Task 12: Create email-fetch-cron.py wrapper

**Files:**
- Create: `openclaw/workspace/email-fetch-cron.py`

**Step 1: Write the wrapper script**

This runs hourly via cron. Reads interval from settings API, checks digest age, fetches if stale:

```python
#!/usr/bin/env python3
"""
Interval-aware email fetch wrapper for cron.

Reads email_fetch_interval_hours from jimbo-api settings, checks digest age,
and runs gmail-helper.py if the digest is stale.

Python 3.11 stdlib only. No pip dependencies.

Environment variables:
    JIMBO_API_URL  — jimbo-api base URL (default: http://localhost:3100)
    JIMBO_API_KEY  — API key for jimbo-api
"""

import datetime
import json
import os
import subprocess
import sys
import urllib.request
import urllib.error

_script_dir = os.path.dirname(os.path.abspath(__file__))
DIGEST_PATH = os.path.join(_script_dir, "email-digest.json")
GMAIL_HELPER = os.path.join(_script_dir, "gmail-helper.py")
ALERT_SCRIPT = os.path.join(_script_dir, "alert.py")

DEFAULT_INTERVAL_HOURS = 1


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def get_interval_from_api():
    """Fetch email_fetch_interval_hours from settings API. Returns hours as int."""
    api_url = os.environ.get("JIMBO_API_URL", "http://localhost:3100")
    api_key = os.environ.get("JIMBO_API_KEY", os.environ.get("API_KEY", ""))

    url = f"{api_url}/api/settings/email_fetch_interval_hours"
    req = urllib.request.Request(
        url,
        headers={
            "X-API-Key": api_key,
            "Content-Type": "application/json",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        return int(data.get("value", DEFAULT_INTERVAL_HOURS))
    except (urllib.error.HTTPError, urllib.error.URLError, OSError, ValueError, KeyError):
        return DEFAULT_INTERVAL_HOURS


def get_digest_age_hours():
    """Return age of email-digest.json in hours, or None if missing/unreadable."""
    if not os.path.exists(DIGEST_PATH):
        return None

    try:
        with open(DIGEST_PATH) as f:
            digest = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    generated_at = digest.get("generated_at")
    if not generated_at:
        return None

    try:
        gen_time = datetime.datetime.fromisoformat(generated_at)
        if gen_time.tzinfo is None:
            gen_time = gen_time.replace(tzinfo=datetime.timezone.utc)
    except ValueError:
        return None

    age = now_utc() - gen_time
    return age.total_seconds() / 3600


def get_current_email_count():
    """Return number of items in current digest, or 0 if missing."""
    if not os.path.exists(DIGEST_PATH):
        return 0
    try:
        with open(DIGEST_PATH) as f:
            digest = json.load(f)
        return len(digest.get("items", []))
    except (json.JSONDecodeError, OSError):
        return 0


def inject_previous_count(count):
    """Read the digest file and add previous_count field."""
    if not os.path.exists(DIGEST_PATH):
        return
    try:
        with open(DIGEST_PATH) as f:
            digest = json.load(f)
        digest["previous_count"] = count
        with open(DIGEST_PATH, "w") as f:
            json.dump(digest, f, indent=2)
    except (json.JSONDecodeError, OSError):
        pass


def send_alert(message):
    """Send alert via alert.py."""
    subprocess.run([sys.executable, ALERT_SCRIPT, message])


def main():
    interval = get_interval_from_api()
    age = get_digest_age_hours()

    if age is not None and age < interval:
        # Digest is fresh enough, skip
        return

    # Record current count before fetch overwrites
    previous_count = get_current_email_count()

    # Run gmail-helper.py fetch
    result = subprocess.run(
        [sys.executable, GMAIL_HELPER, "fetch", "--hours", str(min(interval * 2, 48))],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        send_alert(f"email-fetch-cron FAILED: {result.stderr[:200]}")
        sys.exit(1)

    # Inject previous_count into the new digest
    inject_previous_count(previous_count)


if __name__ == "__main__":
    main()
```

**Step 2: Commit**

```bash
cd /Users/marvinbarretto/development/openclaw
git add workspace/email-fetch-cron.py
git commit -m "feat: add interval-aware email fetch wrapper for hourly cron"
```

---

## Task 13: Update CLAUDE.md and documentation

**Files:**
- Modify: `openclaw/CLAUDE.md` — update cron schedule section, add settings API docs
- Modify: `openclaw/CAPABILITIES.md` — add settings row

**Step 1: Update CLAUDE.md cron section**

Replace the 06:00 email fetch cron entry with the hourly email-fetch-cron.py entry:

```
# Hourly — email fetch (interval-aware, reads setting from API)
0 * * * * export $(...) && \
  docker exec -e GOOGLE_CALENDAR_CLIENT_ID=$GOOGLE_CALENDAR_CLIENT_ID \
              -e GOOGLE_CALENDAR_CLIENT_SECRET=$GOOGLE_CALENDAR_CLIENT_SECRET \
              -e GOOGLE_CALENDAR_REFRESH_TOKEN=$GOOGLE_CALENDAR_REFRESH_TOKEN \
              -e JIMBO_API_URL=$JIMBO_API_URL \
              -e JIMBO_API_KEY=$JIMBO_API_KEY \
              -e TELEGRAM_BOT_TOKEN=$TELEGRAM_BOT_TOKEN \
              -e TELEGRAM_CHAT_ID=$TELEGRAM_CHAT_ID \
  $(docker ps -q --filter name=openclaw-sbx) \
  python3 /workspace/email-fetch-cron.py \
  >> /var/log/email-fetch.log 2>&1
```

Add `email-fetch-cron.py` to the Key Files section with description.

Add settings API info to the Architecture section (jimbo-api serves `/api/settings/*`).

**Step 2: Commit**

```bash
cd /Users/marvinbarretto/development/openclaw
git add CLAUDE.md CAPABILITIES.md
git commit -m "docs: update cron schedule and add settings API documentation"
```

---

## Task 14: Deploy and verify

**Step 1: Push workspace files to VPS**

```bash
cd /Users/marvinbarretto/development/openclaw
./scripts/workspace-push.sh --live
```

**Step 2: Deploy jimbo-api**

```bash
cd /Users/marvinbarretto/development/jimbo/notes-triage-api
# Build and deploy per existing workflow
ssh jimbo "cd /home/openclaw/.openclaw/workspace && git pull && npm run build && sudo systemctl restart jimbo-api"
```

**Step 3: Deploy site**

```bash
cd /Users/marvinbarretto/development/site
# Build and deploy via Cloudflare Pages per existing workflow
```

**Step 4: Update VPS cron**

SSH to VPS and update root crontab:
- Remove the old `0 6 * * *` gmail-helper.py entry
- The hourly alert-check.py cron already runs — it will pick up the new alert-check.py from workspace

**Step 5: Verify**

1. Check settings API: `curl -H "X-API-Key: $KEY" https://marvinbarretto.dev/api/settings`
2. Check settings UI: visit `https://site.marvinbarretto.workers.dev/app/jimbo/settings`
3. Wait for next hourly cron and check Telegram message format
4. Verify email-fetch-cron.py runs: check `/var/log/email-fetch.log`

**Step 6: Commit any final tweaks and tag**

```bash
git tag alert-improvements-v1
```
