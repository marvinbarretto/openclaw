# Alert Improvements + Configurable Email Fetch

**Date:** 2026-03-02
**Status:** Design

## Problem

The hourly `alert-check.py status` messages have three issues:

1. **Credits check is wrong** — OpenRouter `/auth/key` returns stale `limit` that doesn't reflect top-ups. Shows "-$20.11 remaining" when real balance is $29.89+.
2. **Briefing check is noisy** — `experiment-tracker.db` only has entries after Jimbo's morning briefing (~07:00 UTC). Before that, every hourly check shows a red X. Expected absence treated as failure.
3. **Email freshness is stale** — digest fetched once daily at 06:00. Could be much fresher since Gmail API is free. Frequency should be configurable from the site UI.

## Design

### 1. Fix credits check (alert-check.py)

Drop the misleading `limit - usage` = remaining calculation. Report usage only:

- Before: `❌ OpenRouter balance LOW: $-20.11 remaining ($30.11 used of $10.00 limit)`
- After: `ℹ️ OpenRouter: $30.11 used`

Remove the `CREDIT_ALERT_THRESHOLD` logic entirely. If we find a reliable balance endpoint later, we can add it back.

### 2. Make briefing check time-aware (alert-check.py)

Introduce a grace period. The briefing runs at ~07:00 UTC:

- Before 08:00 UTC: `⏳ briefing pending`  (no alert, neutral icon)
- After 08:00 UTC with today's runs: `✅ briefing ran (email-triage: 1, newsletter-deep-read: 1)`
- After 08:00 UTC with no runs: `❌ briefing missing for today`
- DB not found: same logic — pending before 08:00, missing after

### 3. Configurable email fetch frequency

#### 3a. Settings API (jimbo-api)

New `settings` table in the existing SQLite database:

```sql
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO settings (key, value) VALUES ('email_fetch_interval_hours', '1');
```

Endpoints (under existing API key auth):

- `GET /api/settings` → all settings as `{ key: value }` object
- `GET /api/settings/:key` → single setting `{ key, value, updated_at }`
- `PUT /api/settings/:key` → upsert, body: `{ value: string }`. Telegram notification on change.

#### 3b. Settings UI (site)

New page at `/app/jimbo/settings`:

- `useSettingsApi()` hook — simple GET/PUT against `/api/settings`
- Form with labelled number input for `email_fetch_interval_hours` (freeform, default 1)
- Follow context editor visual patterns (same layout, same styling)

#### 3c. Email fetch wrapper (VPS sandbox)

New script: `workspace/email-fetch-cron.py`

Called by an hourly cron job. Logic:

1. Read `email_fetch_interval_hours` from settings API (`JIMBO_API_URL`)
2. Read `email-digest.json` to get `generated_at` timestamp
3. If age >= interval hours: run `gmail-helper.py fetch --hours <interval>`
4. If age < interval: exit silently
5. Before overwriting digest, record `previous_count` (items in current digest) into the new digest metadata

Fallback: if settings API is unreachable, default to 1 hour.

#### 3d. Updated digest check (alert-check.py)

Replace freshness-based message with volume-based:

- Before: `✅ digest fresh (06:02 UTC, 116 emails, 2.0h ago)`
- After: `✅ digest: 116 emails today (23 new)`

Where:
- "today" = total items in current digest (fetched with `--hours` covering today)
- "new" = current count minus `previous_count` from last fetch
- If `previous_count` is missing (first run), just show total: `✅ digest: 116 emails today`

#### 3e. Updated cron schedule

Replace the single daily 06:00 fetch with:

```cron
# Hourly — email fetch (interval-aware)
0 * * * * export $(...) && docker exec ... python3 /workspace/email-fetch-cron.py >> /var/log/email-fetch.log 2>&1
```

Remove the old 06:00 gmail-helper.py cron entry.

### Example alert messages after changes

```
✅ 08:00 ✅ digest: 116 emails today (23 new) | ⏳ briefing pending | ℹ️ OpenRouter: $30.11 used
```

```
✅ 09:00 ✅ digest: 132 emails today (16 new) | ✅ briefing ran (email-triage: 1, newsletter-deep-read: 1) | ℹ️ OpenRouter: $30.11 used
```

```
❌ 10:00 ✅ digest: 132 emails today (0 new) | ❌ briefing missing for today | ℹ️ OpenRouter: $30.11 used
```

## Repos affected

- **openclaw/** — `workspace/alert-check.py`, new `workspace/email-fetch-cron.py`
- **jimbo-api/** — new settings table, routes, service
- **site/** — new settings page, hook, components

## Not in scope

- Restoring credit balance check (need a reliable OpenRouter endpoint first)
- Dashboard display of settings
- Other configurable settings (can add later to the same table)
