# Calendar Configuration — Design Spec

**Date:** 2026-03-23
**Context:** Briefing review session 13. Calendar section polluted with 36 calendars (shared, subscribed, stale) when only ~5 are wanted. No way to configure which calendars Jimbo processes.

## Problem

`calendar-helper.py list-events --primary-only` filters to `primary` or `accessRole == "owner"` — but the account owns 16 calendars, many unwanted (Habits, Fourfold Media, Six Nations Rugby, Cricket, etc.). Shared/subscribed calendars also leak through inconsistently. The briefing mixes other people's events (Quiet Waters, Breaky, Zoom Prayer, Cookin!) with Marvin's real schedule.

## Design

### Data Model

Two JSON blobs stored in the existing `settings` table (no new tables, no migrations):

**`calendar_available`** — pushed by the pipeline, read by the UI:
```json
[
  { "id": "marvinbarretto@gmail.com", "summary": "marvinbarretto@gmail.com", "access_role": "owner", "primary": true },
  { "id": "marbar.alt@gmail.com", "summary": "marbar.alt@gmail.com", "access_role": "owner", "primary": false },
  { "id": "dd13ho8iol4ah4larbk6kopnlo@group.calendar.google.com", "summary": "Habits", "access_role": "owner", "primary": false },
  ...
]
```

**`calendar_config`** — user's choices, read by the pipeline:
```json
{
  "calendars": {
    "marvinbarretto@gmail.com": { "enabled": true, "tag": null },
    "marbar.alt@gmail.com": { "enabled": true, "tag": "options" },
    "e354762795861514286dc8ff3e67c5e8f25cecbe8c223e21cc93e345273d5484@group.calendar.google.com": { "enabled": true, "tag": "airbnb" },
    "dd13ho8iol4ah4larbk6kopnlo@group.calendar.google.com": { "enabled": false, "tag": null }
  }
}
```

- Any calendar ID not in `calendar_config` = **disabled** by default.
- `tag` is a freeform string. `"options"` means Jimbo labels entries as lower confidence. Other tags (e.g., `"airbnb"`, `"work"`) can inform briefing presentation. `null` = no special treatment.

### Data Flow

```
briefing-prep.py (cron 06:15 / 14:15)
  │
  ├─ Step 0 (NEW): calendar-helper.py list-calendars
  │   → POST result to jimbo-api PUT /api/settings/calendar_available
  │   (refreshes the available list for the UI)
  │
  ├─ Step 4 (CHANGED): calendar-helper.py list-events --days 1 --whitelist
  │   → reads calendar_config from jimbo-api GET /api/settings/calendar_config
  │   → only fetches events from enabled calendar IDs
  │   → adds "tag" field to each event in output
  │   → outputs filtered, tagged events as JSON
  │
  └─ ... (rest of pipeline unchanged)

Site UI (user, on demand)
  │
  ├─ GET /api/settings/calendar_available → renders calendar list
  ├─ GET /api/settings/calendar_config → current whitelist + tags
  ├─ User toggles checkboxes, sets tags via dropdown
  └─ PUT /api/settings/calendar_config → saves config
```

### Component Changes

#### 1. `calendar-helper.py` (sandbox)

**New flag:** `--whitelist` on `list-events` subcommand.

When `--whitelist` is passed:
1. Read `JIMBO_API_URL` and `JIMBO_API_KEY` from env (already available — same as `context-helper.py`)
2. GET `{JIMBO_API_URL}/api/settings/calendar_config`
3. Parse the JSON, extract enabled calendar IDs
4. Use those IDs instead of fetching all/primary-only calendars
5. Add `"tag"` field to each event in output (from the config)

If the API call fails or config is empty, fall back to `--primary-only` behaviour with a stderr warning.

**No other changes** to existing commands (`list-calendars`, `create-event`, etc.).

#### 2. `briefing-prep.py` (sandbox)

**New step** before the existing calendar step:
```python
# Step 0: Sync calendar list to API
result = subprocess.run(
    [sys.executable, "calendar-helper.py", "list-calendars"],
    capture_output=True, text=True, timeout=30,
)
if result.returncode == 0:
    put_setting("calendar_available", result.stdout.strip())
    pipeline_status["calendar_sync"] = {"status": "ok"}
else:
    pipeline_status["calendar_sync"] = {"status": "failed", "error": result.stderr.strip()[:200]}
```

**Changed step 4:** Replace `--primary-only` with `--whitelist`:
```python
[sys.executable, "calendar-helper.py", "list-events", "--days", "1", "--whitelist"]
```

`--whitelist` takes precedence over `--primary-only` if both are passed. They should not be combined — `briefing-prep.py` only passes `--whitelist`.

**Helper function `put_setting(key, value)`** — HTTP PUT to jimbo-api settings endpoint. Uses `JIMBO_API_URL` and `JIMBO_API_KEY` env vars.

**Serialisation note:** The settings API stores all values as strings (`value TEXT` column). The `put_setting` helper must send the raw JSON string as the value — not a parsed object. Since `result.stdout` from `list-calendars` is already valid JSON text, send it directly:
```python
def put_setting(key, value_str):
    """PUT a string value to jimbo-api settings. value_str must be a string."""
    body = json.dumps({"value": value_str}).encode()
    req = urllib.request.Request(
        f"{JIMBO_API_URL}/api/settings/{key}",
        data=body, method="PUT",
        headers={"Content-Type": "application/json", "X-API-Key": JIMBO_API_KEY},
    )
    urllib.request.urlopen(req, timeout=10)
```

On the reading side, `calendar-helper.py --whitelist` and the site UI must `JSON.parse()` the string value retrieved from the settings API.

#### 3. Site — new page `/app/jimbo/calendar`

**Files:**
- `src/pages/app/jimbo/calendar.astro` — page wrapper (follows settings.astro pattern)
- `src/components/admin/CalendarAdmin.tsx` — React component
- `src/hooks/useCalendarApi.ts` — data fetching hook

**AdminTabs.tsx:** Add `{ label: 'Calendar', href: '/app/jimbo/calendar' }` to TABS array.

**UI layout:**

```
Calendar Configuration                    Last synced: 2 hours ago

Owner calendars
┌────┬──────────────────────────┬────────────┐
│ ✓  │ Calendar                 │ Tag        │
├────┼──────────────────────────┼────────────┤
│ ☑  │ marvinbarretto@gmail.com │ —          │
│ ☑  │ marbar.alt@gmail.com     │ options ▾  │
│ ☑  │ Airbnb                   │ airbnb ▾   │
│ ☐  │ Habits                   │ —          │
│ ☐  │ Fourfold Media           │ —          │
│ ☐  │ Watford FC               │ —          │
│ ☐  │ Travel                   │ —          │
│ ...                                        │
└────┴──────────────────────────┴────────────┘

Subscribed calendars
┌────┬──────────────────────────┬────────────┐
│ ☐  │ Songkick                 │ —          │
│ ☐  │ Lectures London          │ —          │
│ ☐  │ Jimbo Suggestions        │ —          │
│ ...                                        │
└────┴──────────────────────────┴────────────┘

                                      [Save]
```

- Split into "Owner calendars" and "Subscribed calendars" sections
- Primary calendar (marvinbarretto@gmail.com) shown first with a "(primary)" badge
- Tag dropdown: `—`, `options`, `airbnb`, `work`, or custom text input. Dropdown is dynamically populated from existing tags in saved `calendar_config` plus the hardcoded defaults, so custom tags persist across sessions.
- "Last synced" timestamp from the `calendar_available` setting's `updated_at` (the settings table records this automatically on write — no extra metadata needed)
- Save button writes `calendar_config` to settings API

**Hook (`useCalendarApi.ts`):**
```typescript
export function useCalendarApi() {
  // Fetches both calendar_available and calendar_config from settings
  // Returns merged view: each calendar with its enabled/tag state
  // Provides saveConfig(config) to PUT calendar_config
}
```

### Briefing Skill Impact

The daily-briefing skill should reference tags when presenting calendar data:
- `tag: "options"` → "From your options calendar — lower confidence"
- `tag: "airbnb"` → "Airbnb booking"
- `tag: null` → presented as a firm commitment

This is a skill prompt change, not a code change. Update `skills/daily-briefing/SKILL.md` to reference calendar tags.

### Migration / Rollout

1. Deploy calendar-helper.py changes (new `--whitelist` flag)
2. Deploy briefing-prep.py changes (sync calendar list + use `--whitelist`)
3. Run briefing-prep.py once manually to seed `calendar_available` in settings
4. Deploy site with new calendar page
5. Marvin configures calendars via UI
6. Update `skills/daily-briefing/SKILL.md` to reference calendar tags in presentation guidance
7. Deploy updated skill via `skills-push.sh`
8. Next pipeline run uses the whitelist automatically

**Fallback:** If `calendar_config` is missing or empty, `--whitelist` falls back to `--primary-only` behaviour. No breakage during rollout.

### What This Doesn't Do

- No live calendar API calls from the site (stays server-side, sandbox-only)
- No new jimbo-api tables or migrations
- No changes to the Google OAuth scope
- No per-event filtering (entire calendars are included or excluded)
- No calendar write features (that's a separate initiative)

### Extensibility

This establishes the pattern for future config pages:
- Email blacklist editor → same settings-backed approach
- Model picker → same UI pattern
- Briefing schedule → same UI pattern

Each gets its own tab in AdminTabs, its own component, its own hook. The settings API is the shared backend.
