# Settings Expansion Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Expand the settings API from 1 setting to 17, grouped into 4 sections, with a settings-helper.py for sandbox scripts to consume them.

**Architecture:** Seed new settings in jimbo-api DB schema. Update the site UI to render settings in grouped sections. Create settings-helper.py (Python stdlib) for sandbox scripts. Update workspace scripts to read from settings-helper.py with fallback defaults.

**Tech Stack:** SQLite/Hono/TypeScript (jimbo-api), Astro/React/SCSS (site), Python 3.11 stdlib (openclaw workspace)

**Repos:**
- `jimbo-api/` — `/Users/marvinbarretto/development/jimbo/notes-triage-api/`
- `site/` — `/Users/marvinbarretto/development/site/`
- `openclaw/` — `/Users/marvinbarretto/development/openclaw/`

---

### Task 1: Seed all settings in jimbo-api DB

**Files:**
- Modify: `jimbo-api/src/db/index.ts:38`

**Step 1: Add all seed rows after the existing one**

Replace line 38 (the single INSERT) with all 17 settings:

```sql
INSERT OR IGNORE INTO settings (key, value) VALUES ('email_fetch_interval_hours', '1');
INSERT OR IGNORE INTO settings (key, value) VALUES ('email_body_max_length', '5000');
INSERT OR IGNORE INTO settings (key, value) VALUES ('email_max_links', '20');
INSERT OR IGNORE INTO settings (key, value) VALUES ('briefing_grace_hour_utc', '8');
INSERT OR IGNORE INTO settings (key, value) VALUES ('vault_priority_threshold', '7');
INSERT OR IGNORE INTO settings (key, value) VALUES ('stale_priorities_days', '10');
INSERT OR IGNORE INTO settings (key, value) VALUES ('stale_goals_days', '45');
INSERT OR IGNORE INTO settings (key, value) VALUES ('monthly_budget_usd', '25');
INSERT OR IGNORE INTO settings (key, value) VALUES ('budget_alert_threshold', '80');
INSERT OR IGNORE INTO settings (key, value) VALUES ('cost_rate_gemini_flash_input', '0.15');
INSERT OR IGNORE INTO settings (key, value) VALUES ('cost_rate_gemini_flash_output', '0.60');
INSERT OR IGNORE INTO settings (key, value) VALUES ('cost_rate_haiku_input', '0.80');
INSERT OR IGNORE INTO settings (key, value) VALUES ('cost_rate_haiku_output', '4.00');
INSERT OR IGNORE INTO settings (key, value) VALUES ('worker_api_timeout_seconds', '30');
INSERT OR IGNORE INTO settings (key, value) VALUES ('triage_batch_size', '50');
INSERT OR IGNORE INTO settings (key, value) VALUES ('reader_batch_size', '15');
INSERT OR IGNORE INTO settings (key, value) VALUES ('triage_budget_ceiling', '0.02');
INSERT OR IGNORE INTO settings (key, value) VALUES ('reader_budget_ceiling', '0.08');
```

`INSERT OR IGNORE` means existing settings keep their current values — only new keys get seeded.

**Step 2: Run tests to verify nothing breaks**

```bash
cd /Users/marvinbarretto/development/jimbo/notes-triage-api
npx vitest run
```

Expected: all tests pass (settings tests clear the table in beforeEach, so seed data doesn't interfere).

**Step 3: Commit**

```bash
git add src/db/index.ts
git commit -m "feat: seed all 17 settings in DB schema (ADR-037)"
```

---

### Task 2: Update settings UI with grouped sections

**Files:**
- Modify: `site/src/components/settings/SettingsEditor.tsx`
- Modify: `site/src/components/settings/SettingsEditor.scss`

**Step 1: Replace the settingsConfig array with grouped sections**

Replace the entire `settingsConfig` array and rendering logic in SettingsEditor.tsx. The new structure groups settings into labelled sections:

```tsx
import { useSettingsApi } from '../../hooks/useSettingsApi';
import { useState } from 'react';
import './SettingsEditor.scss';

interface SettingConfig {
  key: string;
  label: string;
  description: string;
  type: 'number';
  min?: number;
  max?: number;
  step?: number;
}

interface SettingsSection {
  title: string;
  settings: SettingConfig[];
}

const sections: SettingsSection[] = [
  {
    title: 'Email Pipeline',
    settings: [
      { key: 'email_fetch_interval_hours', label: 'Fetch interval (hours)', description: 'How often to check for new emails', type: 'number', min: 1, max: 24 },
      { key: 'email_body_max_length', label: 'Body truncation (chars)', description: 'Max characters of email body to store', type: 'number', min: 1000, max: 20000 },
      { key: 'email_max_links', label: 'Max links per email', description: 'Max links to extract from each email', type: 'number', min: 5, max: 100 },
    ],
  },
  {
    title: 'Briefing & Scheduling',
    settings: [
      { key: 'briefing_grace_hour_utc', label: 'Briefing grace hour (UTC)', description: 'Before this hour, missing briefing shows "pending"', type: 'number', min: 0, max: 23 },
      { key: 'vault_priority_threshold', label: 'Vault priority threshold', description: 'Min priority score (1-10) to appear in briefing', type: 'number', min: 1, max: 10 },
      { key: 'stale_priorities_days', label: 'Stale priorities warning (days)', description: 'Days before warning that priorities need updating', type: 'number', min: 1, max: 90 },
      { key: 'stale_goals_days', label: 'Stale goals warning (days)', description: 'Days before warning that goals need updating', type: 'number', min: 7, max: 180 },
    ],
  },
  {
    title: 'Cost & Budget',
    settings: [
      { key: 'monthly_budget_usd', label: 'Monthly budget (USD)', description: 'Monthly spending budget for all LLM APIs', type: 'number', min: 1, max: 100 },
      { key: 'budget_alert_threshold', label: 'Budget alert at (%)', description: 'Percentage of budget that triggers an alert', type: 'number', min: 10, max: 100 },
      { key: 'cost_rate_gemini_flash_input', label: 'Flash input ($/1M tokens)', description: 'Gemini Flash input cost per 1M tokens', type: 'number', min: 0, step: 0.01 },
      { key: 'cost_rate_gemini_flash_output', label: 'Flash output ($/1M tokens)', description: 'Gemini Flash output cost per 1M tokens', type: 'number', min: 0, step: 0.01 },
      { key: 'cost_rate_haiku_input', label: 'Haiku input ($/1M tokens)', description: 'Claude Haiku input cost per 1M tokens', type: 'number', min: 0, step: 0.01 },
      { key: 'cost_rate_haiku_output', label: 'Haiku output ($/1M tokens)', description: 'Claude Haiku output cost per 1M tokens', type: 'number', min: 0, step: 0.01 },
    ],
  },
  {
    title: 'Workers',
    settings: [
      { key: 'worker_api_timeout_seconds', label: 'API timeout (seconds)', description: 'Timeout for LLM API calls', type: 'number', min: 5, max: 120 },
      { key: 'triage_batch_size', label: 'Triage batch size', description: 'Emails per batch for triage worker', type: 'number', min: 5, max: 200 },
      { key: 'reader_batch_size', label: 'Reader batch size', description: 'Emails per batch for newsletter reader', type: 'number', min: 5, max: 100 },
      { key: 'triage_budget_ceiling', label: 'Triage budget ceiling (USD)', description: 'Max spend per triage run', type: 'number', min: 0, step: 0.01 },
      { key: 'reader_budget_ceiling', label: 'Reader budget ceiling (USD)', description: 'Max spend per reader run', type: 'number', min: 0, step: 0.01 },
    ],
  },
];

export function SettingsEditor() {
  const { settings, loading, error, updateSetting } = useSettingsApi();
  const [pendingValues, setPendingValues] = useState<Record<string, string>>({});

  if (loading && Object.keys(settings).length === 0) {
    return <div className="settings-editor"><p>Loading settings...</p></div>;
  }

  function handleChange(key: string, value: string) {
    setPendingValues((prev) => ({ ...prev, [key]: value }));
  }

  function handleSave(key: string) {
    const value = pendingValues[key] ?? settings[key];
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

      {sections.map((section) => (
        <div key={section.title} className="settings-editor__section">
          <h3 className="settings-editor__section-title">{section.title}</h3>
          <div className="settings-editor__list">
            {section.settings.map((config) => {
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
                      step={config.step}
                      value={currentValue}
                      onChange={(e) => handleChange(config.key, e.target.value)}
                      onKeyDown={(e) => handleKeyDown(config.key, e)}
                      className="settings-editor__input"
                    />
                    <button
                      onClick={() => handleSave(config.key)}
                      className={`settings-editor__save-btn${isDirty ? ' settings-editor__save-btn--dirty' : ''}`}
                    >
                      Save
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
```

**Step 2: Add section title styles to SCSS**

Add after the `h2` rule in SettingsEditor.scss:

```scss
  &__section {
    margin-bottom: var(--space-6);
  }

  &__section-title {
    font-size: var(--text-base);
    font-weight: 600;
    color: var(--color-text-muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: var(--space-3);
    padding-bottom: var(--space-2);
    border-bottom: 1px solid var(--color-border);
  }
```

**Step 3: Commit**

```bash
cd /Users/marvinbarretto/development/site
git add src/components/settings/SettingsEditor.tsx src/components/settings/SettingsEditor.scss
git commit -m "feat: expand settings UI with 17 settings in 4 grouped sections (ADR-037)"
```

---

### Task 3: Create settings-helper.py for sandbox scripts

**Files:**
- Create: `openclaw/workspace/settings-helper.py`

**Step 1: Write the helper script**

Follow the context-helper.py pattern — stdlib only, reads from jimbo-api, outputs formatted text or JSON.

```python
#!/usr/bin/env python3
"""
Settings API client for Jimbo's sandbox.

Fetches settings from jimbo-api and returns values for use by other scripts.

Python 3.11 stdlib only. No pip dependencies.

Usage:
    python3 /workspace/settings-helper.py get email_fetch_interval_hours
    python3 /workspace/settings-helper.py get email_fetch_interval_hours --default 1
    python3 /workspace/settings-helper.py all
    python3 /workspace/settings-helper.py all --json
"""

import json
import os
import sys
import urllib.request
import urllib.error


API_URL = os.environ.get("JIMBO_API_URL", "http://localhost:3100")
API_KEY = os.environ.get("JIMBO_API_KEY", os.environ.get("API_KEY", ""))


def fetch_all():
    """Fetch all settings. Returns dict or None on failure."""
    url = f"{API_URL}/api/settings"
    req = urllib.request.Request(
        url,
        headers={"X-API-Key": API_KEY, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        return None


def fetch_one(key):
    """Fetch a single setting. Returns value string or None on failure."""
    url = f"{API_URL}/api/settings/{key}"
    req = urllib.request.Request(
        url,
        headers={"X-API-Key": API_KEY, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            return data.get("value")
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        return None


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("get", "all"):
        sys.stderr.write("Usage: settings-helper.py {get <key> [--default <val>] | all [--json]}\n")
        sys.exit(1)

    command = sys.argv[1]

    if command == "all":
        settings = fetch_all()
        if settings is None:
            sys.stderr.write("settings-helper.py: failed to fetch settings\n")
            sys.exit(1)
        if "--json" in sys.argv:
            print(json.dumps(settings, indent=2))
        else:
            for key, value in sorted(settings.items()):
                print(f"{key}={value}")

    elif command == "get":
        if len(sys.argv) < 3:
            sys.stderr.write("Usage: settings-helper.py get <key> [--default <val>]\n")
            sys.exit(1)
        key = sys.argv[2]
        default = None
        if "--default" in sys.argv:
            idx = sys.argv.index("--default")
            if idx + 1 < len(sys.argv):
                default = sys.argv[idx + 1]

        value = fetch_one(key)
        if value is None:
            if default is not None:
                print(default)
            else:
                sys.stderr.write(f"settings-helper.py: setting '{key}' not found\n")
                sys.exit(1)
        else:
            print(value)


if __name__ == "__main__":
    main()
```

**Step 2: Verify syntax**

```bash
python3 -c "import ast; ast.parse(open('/Users/marvinbarretto/development/openclaw/workspace/settings-helper.py').read())"
```

**Step 3: Commit**

```bash
cd /Users/marvinbarretto/development/openclaw
git add workspace/settings-helper.py
git commit -m "feat: add settings-helper.py for sandbox scripts to read settings API"
```

---

### Task 4: Update workspace scripts to read from settings

**Files:**
- Modify: `openclaw/workspace/alert-check.py:35` — read `briefing_grace_hour_utc`
- Modify: `openclaw/workspace/email-fetch-cron.py` — already reads from API, no change needed
- Modify: `openclaw/workspace/gmail-helper.py:42-43` — read `email_body_max_length`, `email_max_links`
- Modify: `openclaw/workspace/cost-tracker.py:31-36,62` — read cost rates and budget threshold
- Modify: `openclaw/workspace/experiment-tracker.py:37-44` — read cost rates

Each script should try to read from the settings API but fall back to the current hardcoded default if the API is unreachable. Use a shared helper function pattern:

**Step 1: Add a `get_setting` helper to each script that needs it**

Add this function near the top of each script (after imports). Do NOT import settings-helper.py — keep each script self-contained (stdlib only, no cross-imports):

```python
def get_setting(key, default):
    """Read a setting from the settings API, or return default on failure."""
    api_url = os.environ.get("JIMBO_API_URL", "http://localhost:3100")
    api_key = os.environ.get("JIMBO_API_KEY", os.environ.get("API_KEY", ""))
    url = f"{api_url}/api/settings/{key}"
    req = urllib.request.Request(url, headers={"X-API-Key": api_key})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            return type(default)(data.get("value", default))
    except Exception:
        return default
```

**Step 2: Update alert-check.py**

Replace `BRIEFING_GRACE_HOUR = 8` with:
```python
BRIEFING_GRACE_HOUR = get_setting("briefing_grace_hour_utc", 8)
```

**Step 3: Update gmail-helper.py**

Replace lines 42-43:
```python
MAX_BODY_LENGTH = get_setting("email_body_max_length", 5000)
SNIPPET_LENGTH = 200  # keep hardcoded, not worth a setting
```

Replace the max links `[:20]` usage (around line 360):
```python
MAX_LINKS = get_setting("email_max_links", 20)
```
And use `[:MAX_LINKS]` instead of `[:20]`.

**Step 4: Update cost-tracker.py**

Replace `COST_RATES` dict with settings-aware version:
```python
COST_RATES = {
    "gemini-2.5-flash": {
        "input": get_setting("cost_rate_gemini_flash_input", 0.15),
        "output": get_setting("cost_rate_gemini_flash_output", 0.60),
    },
    "claude-haiku-4.5": {
        "input": get_setting("cost_rate_haiku_input", 0.80),
        "output": get_setting("cost_rate_haiku_output", 4.00),
    },
}
```

Keep the other model rates hardcoded (they're not actively used).

Replace budget alert threshold default:
```python
default_threshold = get_setting("budget_alert_threshold", 80) / 100.0
```

**Step 5: Update experiment-tracker.py**

Same COST_RATES replacement as cost-tracker.py (use `get_setting`). This eliminates the duplication — both scripts now read from the same source.

**Step 6: Verify all scripts parse**

```bash
cd /Users/marvinbarretto/development/openclaw/workspace
for f in alert-check.py gmail-helper.py cost-tracker.py experiment-tracker.py; do
  python3 -c "import ast; ast.parse(open('$f').read())" && echo "$f OK" || echo "$f FAIL"
done
```

**Step 7: Commit**

```bash
cd /Users/marvinbarretto/development/openclaw
git add workspace/alert-check.py workspace/gmail-helper.py workspace/cost-tracker.py workspace/experiment-tracker.py
git commit -m "feat: read settings from API in workspace scripts with fallback defaults (ADR-037)"
```

---

### Task 5: Deploy and verify

**Step 1: Build and deploy jimbo-api**

```bash
cd /Users/marvinbarretto/development/jimbo/notes-triage-api
npm run build
rsync -avz --delete dist/ jimbo:/home/openclaw/notes-triage-api/ --exclude='node_modules' --exclude='data' --exclude='package-lock.json' --exclude='package.json'
ssh jimbo "sudo systemctl restart notes-triage-api"
```

Verify new settings are seeded:
```bash
ssh jimbo "curl -s -H 'X-API-Key: 7e37e4ae1650b6ebc2a925b918924d80' http://localhost:3100/api/settings | python3 -m json.tool"
```

Should show all 17 settings.

**Step 2: Push workspace and site**

```bash
cd /Users/marvinbarretto/development/openclaw
./scripts/workspace-push.sh --live

cd /Users/marvinbarretto/development/site
git push origin master
```

**Step 3: Verify settings page shows all 4 sections**

Visit `https://site.marvinbarretto.workers.dev/app/jimbo/settings` — should show Email Pipeline, Briefing & Scheduling, Cost & Budget, Workers sections.

**Step 4: Verify a script reads settings**

```bash
ssh jimbo "export \$(grep -v '^#' /opt/openclaw.env | xargs) && docker exec -e JIMBO_API_URL=\$JIMBO_API_URL -e JIMBO_API_KEY=\$JIMBO_API_KEY \$(docker ps -q --filter name=openclaw-sbx) python3 /workspace/settings-helper.py all"
```

Should print all 17 settings as `key=value` pairs.
