# ADR-037: Configurable Settings via API

## Status

Accepted

## Context

Many operational values across workspace scripts are hardcoded: email fetch interval, body truncation limits, briefing thresholds, cost rates, worker batch sizes, budget ceilings. Changing any of these requires editing Python scripts and redeploying via rsync.

We built a settings API (key-value store in jimbo-api, backed by SQLite) and a settings UI page on the personal site as part of the alert improvements work (2026-03-02). Currently only `email_fetch_interval_hours` is exposed.

The question: which hardcoded values should become configurable settings, and how should scripts consume them?

## Decision

Expand the settings API with 17 settings across 4 groups:

**Email Pipeline:** `email_fetch_interval_hours` (1), `email_body_max_length` (5000), `email_max_links` (20)

**Briefing & Scheduling:** `briefing_grace_hour_utc` (8), `vault_priority_threshold` (7), `stale_priorities_days` (10), `stale_goals_days` (45)

**Cost & Budget:** `monthly_budget_usd` (25), `budget_alert_threshold` (80), `cost_rate_gemini_flash_input` (0.15), `cost_rate_gemini_flash_output` (0.60), `cost_rate_haiku_input` (0.80), `cost_rate_haiku_output` (4.00)

**Workers:** `worker_api_timeout_seconds` (30), `triage_batch_size` (50), `reader_batch_size` (15), `triage_budget_ceiling` (0.02), `reader_budget_ceiling` (0.08)

Scripts read settings via the settings API. If the API is unreachable, scripts fall back to hardcoded defaults (same values as the seed data). This means settings are always optional — nothing breaks if the API is down.

A `settings-helper.py` script provides a simple interface for sandbox scripts to read settings, similar to `context-helper.py`.

The settings UI groups settings into labelled sections for readability.

## Consequences

**Easier:**
- Tune operational parameters without code changes or redeployment
- Single source of truth for cost rates (currently duplicated in cost-tracker.py and experiment-tracker.py)
- Budget and threshold changes take effect immediately
- Visible audit trail (updated_at timestamps, Telegram notifications)

**Harder:**
- Scripts have a new dependency (settings API) — mitigated by fallback defaults
- More network calls from sandbox scripts — mitigated by caching in settings-helper.py
- Settings page grows — mitigated by section grouping

**Not included (intentionally):**
- Email blacklists (lists, not scalar values — different UX needed)
- HEARTBEAT timing windows (prose interpreted by Jimbo, not by code)
- Model selection (already handled by model-swap.sh)
