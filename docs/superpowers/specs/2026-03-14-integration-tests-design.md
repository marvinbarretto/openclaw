# Integration Test Suite Design

## Goal

Catch bugs at the boundaries between repos (Ralph → jimbo-api → decision worker → briefing) that unit tests with mocks can never find. Every test hits a real jimbo-api instance with a real SQLite database — no mocks at the HTTP layer.

## Architecture

```
pytest (Python)
  │
  ├── conftest.py          Session fixture: starts jimbo-api subprocess
  │                         on random port with throwaway SQLite DB
  │
  ├── helpers.py            ApiClient (stdlib urllib), test data builders
  │
  ├── test_email_reports.py     Ralph ↔ jimbo-api contract
  ├── test_email_decisions.py   Decision worker ↔ jimbo-api contract
  ├── test_context_api.py       Worker context fetching ↔ jimbo-api contract
  ├── test_briefing_integration.py  Briefing-prep ↔ jimbo-api contract
  └── test_schema_contract.py   Schema drift protection
```

### Server lifecycle (conftest.py)

Session-scoped pytest fixture that:

1. Checks `node_modules` exists in jimbo-api directory — fails fast with a clear message if not (native `better-sqlite3` bindings require `npm install`)
2. Creates a temp directory for the test SQLite DB
3. Picks a random available port (bind to port 0, read the assigned port)
4. Starts `node /path/to/jimbo-api/src/index.js` as a subprocess with env:
   - `CONTEXT_DB_PATH` → temp DB path
   - `PORT` → the random port
   - `API_KEY` → a known test value (e.g. `test-api-key-integration`)
5. Polls GET `/health` until 200 or timeout (5s) — uses the unauthenticated health endpoint, not `/api/*` which requires the API key
6. Yields `{"url": "http://localhost:{port}", "api_key": "test-api-key-integration", "db_path": temp_db_path}` to all tests
7. On teardown: kills the Node process, deletes the temp directory

jimbo-api path defaults to `../jimbo/jimbo-api/` relative to openclaw root, overridable via `JIMBO_API_PATH` env var.

### ApiClient (helpers.py)

Thin wrapper around `urllib.request` — same HTTP code the workers use. Methods:

- `get(path)` → parsed JSON
- `post(path, body)` → parsed JSON
- `patch(path, body)` → parsed JSON

Handles `X-API-Key` header, `Content-Type: application/json`, JSON encoding/decoding. Raises on non-2xx status with the response body for debugging.

### Test data builders (helpers.py)

Functions that return realistic test data matching what Ralph and the decision worker actually produce:

- `build_full_report(gmail_id=None)` → complete email report with body_analysis, entities, events, links, screenshots. Generates a unique gmail_id if not provided.
- `build_minimal_report(gmail_id=None)` → bare minimum fields
- `build_decision()` → full decision with all scoring fields (relevance_score, category, suggested_action, reason, insight, connections, time_sensitive, deadline)

### Test isolation

Each test function starts clean. A `clear_data` fixture (function-scoped) connects directly to the temp SQLite DB file (path provided by the session fixture) and runs `DELETE FROM email_reports` (and other tables as needed). This avoids needing DELETE endpoints in the API. Tests never depend on ordering or state from other tests.

### Context seeding

Context data (priorities, interests, goals) is seeded by inserting directly into the temp SQLite DB from Python using `sqlite3.connect(db_path)`. This avoids needing to chain multiple API calls (jimbo-api has no single "create context file" endpoint — files are created by a seed script, then sections/items are added individually).

### Task config

Tests that instantiate workers (e.g. `EmailDecisionWorker`) use the real task config JSON files from `workspace/tasks/`. The test fixture ensures the Python path includes the workspace directory so `load_task_config()` finds them.

## Test modules

### test_email_reports.py — Ralph ↔ jimbo-api contract

Protects the boundary where Ralph pushes extracted email data to jimbo-api. Real bugs this catches: wrong API paths, missing fields, JSON columns losing nested data.

Tests:
- **POST full report** — all fields stored, nothing dropped
- **POST minimal report** — works with just required fields
- **POST duplicate gmail_id** — verify upsert behaviour (jimbo-api uses ON CONFLICT DO UPDATE)
- **GET undecided** — only reports without decisions returned
- **GET with min_relevance filter** — filtering works correctly after decisions
- **GET stats** — counts match actual data
- **JSON round-trip** — body_analysis and links arrays with nested objects survive SQLite JSON storage
- **Auth failure** — request without API key returns 401

### test_email_decisions.py — Decision worker ↔ jimbo-api contract

Runs the actual `EmailDecisionWorker` class against a real jimbo-api. Only the LLM call is mocked — everything else is real HTTP.

Tests:
- **Worker processes undecided reports** — seed reports, run worker, verify decisions PATCHed back with correct fields
- **Decided reports leave undecided list** — after worker runs, undecided endpoint returns empty
- **Worker handles empty queue** — no undecided reports, worker completes gracefully
- **Worker handles LLM garbage** — mock returns unparseable text, report stays undecided, worker doesn't crash
- **Worker handles LLM missing fields** — mock returns JSON without relevance_score, report stays undecided
- **All decision fields verified** — relevance_score, category, suggested_action, reason, insight, connections, time_sensitive, deadline all stored correctly. Note: jimbo-api stores decisions as a JSON blob in the `decision` column with `relevance_score` also as a discrete column. The API response nests decision fields under a `decision` object — tests verify this exact shape.

### test_context_api.py — Worker context fetching ↔ jimbo-api contract

Verifies workers can fetch structured context and get usable text back. Real bugs this catches: wrong API paths for context, response format changes, empty sections.

Tests:
- **Seed and fetch priorities** — seed context directly in DB, fetch via BaseWorker.get_context() with context_slugs config, verify readable text with correct content
- **Seed and fetch interests** — same for interests slug
- **Seed and fetch goals** — same for goals slug
- **Multiple sections and items** — verify nested structure renders correctly
- **Empty context file** — file exists but has no sections, worker handles gracefully
- **Missing context file** — slug doesn't exist, worker logs warning and continues

### test_briefing_integration.py — Briefing-prep ↔ jimbo-api contract

Verifies `fetch_email_insights()` returns the right data for the Opus prompt. Real bugs this catches: wrong query parameters, decision field access patterns, sort order.

Note: time window filtering is done client-side in `fetch_email_insights()` (not an API parameter). Tests verify both the API fetch and the Python-side filtering.

Tests:
- **Fetch recent decided reports** — seed reports, decide them, fetch insights, verify shape and content
- **Sorted by relevance descending** — highest relevance_score first
- **Time window filtering** — seed a report decided 20 hours ago and one decided 1 hour ago, verify only the recent one appears (client-side filtering in fetch_email_insights)
- **Min relevance filtering** — low-scoring reports excluded by API query parameter
- **Empty results** — no decided reports, returns empty list gracefully
- **Decision field access pattern** — verify that `fetch_email_insights()` correctly reads decision fields from the API response shape (jimbo-api nests them under `decision`, not top-level). This test will likely catch a real bug in the current code.
- **All output fields present** — relevance_score, category, suggested_action, reason, insight, connections, time_sensitive, deadline all in output

### test_schema_contract.py — Schema drift protection

Guards against the most common failure mode: one repo changes a field name or type and the other doesn't know. Tests use maximally-populated payloads to catch any field that gets silently dropped.

Tests:
- **Full report round-trip** — POST every field Ralph sends, GET it back, assert field-by-field equality
- **Full decision round-trip** — PATCH every field the decision worker sends, GET it back, assert equality (verifying both the discrete `relevance_score` column and the `decision` JSON blob)
- **Nested JSON integrity** — body_analysis with deep nesting, links array with multiple entries, connections array — all survive SQLite JSON storage
- **Null/empty handling** — optional fields sent as null or empty arrays, verify they come back correctly (not dropped, not converted to wrong types)

## Running the tests

```bash
# From openclaw root — run integration tests only
pytest workspace/tests/integration/ -v

# Run everything (unit + integration)
pytest workspace/tests/ -v

# Skip integration tests (no Node/jimbo-api needed)
pytest workspace/tests/ -v --ignore=workspace/tests/integration/

# Point to a non-default jimbo-api location
JIMBO_API_PATH=/path/to/jimbo-api pytest workspace/tests/integration/ -v
```

## Prerequisites

- Node.js installed (for jimbo-api subprocess)
- jimbo-api repo available with `npm install` already done (native `better-sqlite3` bindings)
- Default path: `../jimbo/jimbo-api/` relative to openclaw root (override with `JIMBO_API_PATH`)
- pytest installed
- No network access needed — everything is localhost

## Code style

- Every test module has a docstring explaining what boundary it protects and what real bugs it catches
- Every test function has a docstring in plain English describing the scenario
- Inline comments explain "why" not "what"
- Test data uses realistic values from the actual system (Watford events, real newsletter names) — not `foo`/`bar`
- Tests read like documentation of how the system works

## What this doesn't cover

- **Dashboard rendering** — that's a Playwright browser test, different concern
- **Ralph's extraction pipeline** — that's local Ollama/Playwright, tested separately
- **LLM output quality** — integration tests mock the LLM, they verify plumbing not intelligence
- **VPS deployment** — tests run locally, not against production

## Known bugs to verify

The spec review identified that `fetch_email_insights()` in `briefing-prep.py` reads `r.get("category")` as a top-level field, but jimbo-api's `mapRow` returns decision fields nested under a `decision` object. The integration tests should confirm whether this is actually a bug and, if so, the fix should be part of the implementation.
