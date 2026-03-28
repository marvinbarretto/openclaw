# Dispatch Briefing Integration

**Date:** 2026-03-28
**Status:** Design — awaiting review
**Depends on:** jimbo-api (dispatch service), briefing-prep.py, daily-briefing skill
**Builds on:** 2026-03-26-dispatch-flow-split-design.md (Phase 3)

## Problem

The briefing pipeline knows nothing about dispatch. Commissions run, PRs land, recon completes — but the morning/afternoon briefing doesn't mention any of it. Marvin has to check GitHub and the dispatch dashboard separately to know what's happening with agent work.

The flow split spec (Phase 3) calls for briefings to show commission status, quest priorities, and recon completions. The data is all there in jimbo-api's dispatch_queue table — it just needs to reach the briefing.

## Design

### 1. New endpoint: `GET /api/dispatch/briefing-summary`

Server-side aggregation endpoint. One call returns everything the briefing needs about dispatch state.

**Response shape:**

```json
{
  "commissions": {
    "prs_for_review": [
      { "task_id": "localshout-next#73", "pr_url": "https://...", "issue_repo": "marvinbarretto/localshout-next", "issue_number": 73, "result_summary": "Implemented E2E test runner" }
    ],
    "in_progress": [
      { "task_id": "localshout-next#85", "agent_type": "coder", "issue_repo": "marvinbarretto/localshout-next", "issue_number": 85, "started_at": "2026-03-28T06:00:00Z" }
    ],
    "awaiting_dispatch": 5
  },
  "recon": {
    "recently_completed": [
      { "task_id": "venue-api-research", "result_summary": "Compared 4 venue APIs...", "completed_at": "2026-03-28T02:00:00Z" }
    ]
  },
  "needs_grooming": 2
}
```

**Query logic:**

| Field | SQL / Logic |
|-------|-------------|
| `prs_for_review` | `flow='commission' AND status='completed' AND pr_state='open'` |
| `in_progress` | `flow='commission' AND status='running'` |
| `awaiting_dispatch` | Count of open `ralph`-labeled GitHub issues NOT already in dispatch_queue. Calls `fetchGitHubIssues()` and subtracts queued issue_numbers. |
| `recently_completed` (recon) | `flow='recon' AND status='completed' AND completed_at > NOW - 24h` |
| `needs_grooming` | Existing `getNeedsGroomingCount()` |

**`awaiting_dispatch` fallback:** If `GITHUB_TOKEN` is not set or the API call fails, return `null` instead of a number. The briefing should handle this gracefully ("GitHub unavailable" or just skip the line).

**Repos for `awaiting_dispatch`:** Hardcode `['marvinbarretto/localshout-next']` for now. Extend later if more repos get `ralph` issues.

### 2. New step in `briefing-prep.py`

Add a dispatch step after vault tasks (Step 5) and before context summary (Step 7).

```python
# --- Step 5b: Dispatch status ---
if not dry_run:
    dispatch_data, dispatch_status = fetch_dispatch_summary()
    pipeline_status["dispatch"] = dispatch_status
else:
    dispatch_data = {}
    pipeline_status["dispatch"] = {"status": "skipped (dry-run)"}
```

`fetch_dispatch_summary()` calls `GET /api/dispatch/briefing-summary` using the existing `JIMBO_API_URL` and `JIMBO_API_KEY` env vars. Returns `(data_dict, status_dict)` following the same pattern as `fetch_email_insights()`.

The `dispatch` key is added to `briefing-input.json` alongside the existing keys.

### 3. Daily briefing skill update

Add a new section **between** "Task status" (section 4) and the closing question. Call it **"Dispatch"** or weave it into the task status section — whichever feels more natural in context.

**Presentation rules:**

- **PRs for review:** "You've got N PRs ready for review" + one line per PR with task_id and summary. Link to PR URL.
- **In progress:** "N commissions running" — only mention if > 0, one line each.
- **Awaiting dispatch:** "N ralph issues ready to dispatch" — only mention if > 0.
- **Recon landed:** "Recon on {task_id} landed overnight — {summary}" — only for recently_completed items.
- **Needs grooming:** "N tasks need grooming before they can be dispatched" — only if > 0.
- **Skip the whole section** if everything is zero/empty. Don't say "no dispatch activity" — just don't send the message.

**Live fallback:** If `briefing-input.json` has no `dispatch` key (stale data, pipeline didn't run), the skill should call the endpoint directly:

```bash
curl -sf -H "X-API-Key: $JIMBO_API_KEY" "$JIMBO_API_URL/api/dispatch/briefing-summary"
```

This mirrors the existing pattern where the skill can fall back to live API calls.

## Scope

This is Phase 3 only. No changes to:
- Dispatch queue logic or lifecycle
- Vault scoring or task selection
- The `flow` field on vault_notes (Phase 4, manual/gradual)
- GitHub webhook handler
- R2 evidence pipeline

## Files Changed

### jimbo-api (`~/development/jimbo/jimbo-api`)
- `src/routes/dispatch.ts` — new `GET /briefing-summary` route
- `src/services/dispatch.ts` — new `getBriefingSummary()` function

### openclaw (`~/development/openclaw`)
- `workspace/briefing-prep.py` — new `fetch_dispatch_summary()` function + step 5b
- `skills/daily-briefing/SKILL.md` — new dispatch section in briefing delivery

### Tests
- `test/dispatch.test.ts` — tests for `getBriefingSummary()`
