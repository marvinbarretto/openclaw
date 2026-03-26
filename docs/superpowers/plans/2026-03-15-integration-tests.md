# Integration Test Suite Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a pytest integration test suite that catches bugs at the boundaries between Ralph, jimbo-api, and the VPS workers by hitting a real jimbo-api instance with a real SQLite database.

**Architecture:** Each test run starts a fresh jimbo-api Node subprocess on a random port with a throwaway SQLite DB. Tests use a thin Python HTTP client (stdlib `urllib`) and direct SQLite access for isolation. Only LLM calls are mocked — all HTTP and DB operations are real.

**Tech Stack:** Python 3.11 stdlib (pytest for test runner), Node.js (jimbo-api subprocess), SQLite (throwaway DB)

**Spec:** `docs/superpowers/specs/2026-03-14-integration-tests-design.md`

---

## Chunk 1: Test Infrastructure

### Task 1: conftest.py — Server Fixture and Test Isolation

**Files:**
- Create: `workspace/tests/integration/__init__.py`
- Create: `workspace/tests/integration/conftest.py`

This is the foundation everything else depends on. The session fixture starts jimbo-api as a subprocess on a random port with a throwaway SQLite DB. The function-scoped `clear_data` fixture ensures each test starts clean.

- [ ] **Step 1: Create the integration test package**

```bash
touch workspace/tests/integration/__init__.py
```

- [ ] **Step 2: Write conftest.py with server fixture**

Create `workspace/tests/integration/conftest.py`:

```python
"""
Fixtures for integration tests against a real jimbo-api instance.

Session fixture: starts jimbo-api as a Node subprocess on a random port
with a throwaway SQLite DB. Every test gets a clean database via the
clear_data fixture.

No mocks at the HTTP layer — these tests verify real network calls
between Python workers and the Node API.
"""

import json
import os
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.error

import pytest


# Where to find jimbo-api — default is ../jimbo/jimbo-api/ relative to openclaw root
_openclaw_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)
))))
_default_jimbo_path = os.path.join(os.path.dirname(_openclaw_root), "jimbo", "jimbo-api")

TEST_API_KEY = "test-api-key-integration"


def _find_free_port():
    """Bind to port 0 and let the OS assign an available port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_health(port, timeout=10):
    """Poll GET /health until 200 or timeout. No auth needed on /health."""
    url = f"http://127.0.0.1:{port}/health"
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, ConnectionRefusedError, OSError) as e:
            last_error = e
        time.sleep(0.2)
    raise RuntimeError(
        f"jimbo-api failed to start within {timeout}s on port {port}: {last_error}"
    )


@pytest.fixture(scope="session")
def jimbo_server():
    """Start a real jimbo-api instance for the entire test session.

    Yields a dict with:
      - url: base URL (http://127.0.0.1:{port})
      - api_key: the test API key
      - db_path: path to the throwaway SQLite DB
      - port: the port number

    On teardown: kills the Node process and deletes the temp directory.
    """
    jimbo_path = os.environ.get("JIMBO_API_PATH", _default_jimbo_path)

    # Fail fast if node_modules is missing — better-sqlite3 needs native bindings
    node_modules = os.path.join(jimbo_path, "node_modules")
    if not os.path.isdir(node_modules):
        pytest.fail(
            f"jimbo-api node_modules not found at {node_modules}. "
            f"Run 'npm install' in {jimbo_path} first."
        )

    # Create throwaway DB in a temp directory
    tmp_dir = tempfile.mkdtemp(prefix="jimbo-test-")
    db_path = os.path.join(tmp_dir, "test.db")
    port = _find_free_port()

    env = {
        **os.environ,
        "CONTEXT_DB_PATH": db_path,
        "PORT": str(port),
        "API_KEY": TEST_API_KEY,
    }

    # Start jimbo-api as a subprocess
    entry_point = os.path.join(jimbo_path, "src", "index.ts")
    proc = subprocess.Popen(
        ["npx", "tsx", entry_point],
        cwd=jimbo_path,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        _wait_for_health(port)
    except RuntimeError:
        # Capture output for debugging
        proc.kill()
        stdout, stderr = proc.communicate(timeout=5)
        shutil.rmtree(tmp_dir, ignore_errors=True)
        pytest.fail(
            f"jimbo-api failed to start.\n"
            f"stdout: {stdout.decode()[:500]}\n"
            f"stderr: {stderr.decode()[:500]}"
        )

    yield {
        "url": f"http://127.0.0.1:{port}",
        "api_key": TEST_API_KEY,
        "db_path": db_path,
        "port": port,
        "_proc": proc,
        "_tmp_dir": tmp_dir,
    }

    # Teardown: kill the server, clean up temp files
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)
    shutil.rmtree(tmp_dir, ignore_errors=True)


def _clear_all_tables(db_path):
    """Delete all rows from data tables via direct SQLite access."""
    db = sqlite3.connect(db_path)
    try:
        db.execute("DELETE FROM email_reports")
        db.execute("DELETE FROM context_items")
        db.execute("DELETE FROM context_sections")
        db.execute("DELETE FROM context_files")
        db.execute("DELETE FROM activities")
        db.execute("DELETE FROM vault_notes")
        db.execute("DELETE FROM costs")
        db.execute("DELETE FROM runs")
        db.commit()
    finally:
        db.close()


@pytest.fixture
def clear_data(jimbo_server):
    """Clear all data BEFORE each test by deleting rows directly from SQLite.

    We clean before (not after) so that a test failure doesn't leave
    dirty state for the next test. We connect directly to the throwaway
    DB file rather than using API endpoints — jimbo-api has no DELETE
    /all endpoint, and we need guaranteed clean state.
    """
    _clear_all_tables(jimbo_server["db_path"])
    yield
```

- [ ] **Step 3: Verify the fixture starts and stops cleanly**

Create a minimal smoke test to validate the fixture works:

```python
# workspace/tests/integration/test_smoke.py
"""Smoke test — verify jimbo-api starts and responds to health checks."""


def test_health_endpoint(jimbo_server):
    """The /health endpoint should return 200 with {status: 'ok'}.

    This is our canary — if this fails, the server fixture is broken
    and no other integration tests will work.
    """
    import json
    import urllib.request

    url = f"{jimbo_server['url']}/health"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read())
        assert data["status"] == "ok"
```

- [ ] **Step 4: Run the smoke test**

Run: `cd /Users/marvinbarretto/development/openclaw && python -m pytest workspace/tests/integration/test_smoke.py -v`
Expected: PASS — jimbo-api starts on random port, health check succeeds

- [ ] **Step 5: Commit**

```bash
git add workspace/tests/integration/__init__.py workspace/tests/integration/conftest.py workspace/tests/integration/test_smoke.py
git commit -m "feat: integration test infrastructure — jimbo-api session fixture"
```

---

### Task 2: helpers.py — API Client and Test Data Builders

**Files:**
- Create: `workspace/tests/integration/helpers.py`

The API client wraps stdlib `urllib` — same HTTP code the workers use. Test data builders produce realistic payloads matching what Ralph and the decision worker actually send.

- [ ] **Step 1: Write helpers.py**

Create `workspace/tests/integration/helpers.py`:

```python
"""
Shared helpers for integration tests.

ApiClient: thin HTTP wrapper using stdlib urllib — same transport the
workers use. Handles auth headers, JSON encoding, and error reporting.

Test data builders: functions that return realistic payloads matching
what Ralph and the decision worker actually produce. Uses real-world
data (Watford events, actual newsletter names) instead of foo/bar.
"""

import json
import urllib.request
import urllib.error
import uuid


class ApiClient:
    """HTTP client for jimbo-api. Uses stdlib urllib — no requests library.

    Every call includes the X-API-Key header and Content-Type.
    Raises on non-2xx status with the response body for debugging.
    """

    def __init__(self, base_url, api_key):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def get(self, path):
        """GET a JSON endpoint. Returns parsed response body."""
        url = f"{self.base_url}{path}"
        req = urllib.request.Request(url, headers={
            "X-API-Key": self.api_key,
            "Accept": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode() if e.fp else ""
            raise AssertionError(
                f"GET {path} returned {e.code}: {body}"
            ) from e

    def post(self, path, body):
        """POST JSON to an endpoint. Returns parsed response body."""
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode()
        req = urllib.request.Request(url, data=data, headers={
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            resp_body = e.read().decode() if e.fp else ""
            raise AssertionError(
                f"POST {path} returned {e.code}: {resp_body}"
            ) from e

    def patch(self, path, body):
        """PATCH JSON to an endpoint. Returns parsed response body."""
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode()
        req = urllib.request.Request(url, data=data, method="PATCH", headers={
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            resp_body = e.read().decode() if e.fp else ""
            raise AssertionError(
                f"PATCH {path} returned {e.code}: {resp_body}"
            ) from e

    def get_raw(self, path):
        """GET without API key — for testing auth failures."""
        url = f"{self.base_url}{path}"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        return urllib.request.urlopen(req, timeout=10)


def build_full_report(gmail_id=None):
    """Build a complete email report matching what Ralph actually sends.

    Includes body_analysis with nested structure, links with metadata,
    and all optional fields populated. Uses realistic data — a Watford
    Observer newsletter with local events.
    """
    return {
        "gmail_id": gmail_id or f"msg_{uuid.uuid4().hex[:12]}",
        "thread_id": f"thread_{uuid.uuid4().hex[:8]}",
        "processed_at": "2026-03-15T08:30:00Z",
        "from_name": "Watford Observer",
        "from_email": "newsletter@watfordobserver.co.uk",
        "subject": "Weekend events in Watford: Palace Theatre comedy night + Cassiobury parkrun",
        "body_analysis": {
            "summary": "Local events newsletter covering weekend activities in Watford area",
            "key_facts": [
                "Comedy night at Palace Theatre featuring Ed Byrne, Saturday 8pm, tickets from £22",
                "Cassiobury parkrun returns after path resurfacing, Saturday 9am",
                "New Vietnamese restaurant opening on The Parade next week",
            ],
            "entities": [
                {"name": "Palace Theatre", "type": "venue"},
                {"name": "Ed Byrne", "type": "person"},
                {"name": "Cassiobury Park", "type": "location"},
            ],
            "events": [
                {
                    "title": "Ed Byrne: If I'm Honest",
                    "date": "2026-03-22",
                    "venue": "Palace Theatre, Watford",
                    "price": "from £22",
                },
            ],
            "sentiment": "positive",
            "relevance_signals": ["local events", "comedy", "fitness"],
        },
        "links": [
            {
                "url": "https://watfordobserver.co.uk/events/comedy-night-palace",
                "title": "Comedy night at Palace Theatre",
                "confidence": 0.9,
                "followed": True,
                "content_summary": "Ed Byrne performs new stand-up show at Watford Palace Theatre",
            },
            {
                "url": "https://www.parkrun.org.uk/cassiobury/",
                "title": "Cassiobury parkrun",
                "confidence": 0.85,
                "followed": True,
                "content_summary": "Weekly 5k run in Cassiobury Park, Watford",
            },
        ],
        "model": "llama3.2:3b",
        "processing_time_seconds": 12.5,
    }


def build_minimal_report(gmail_id=None):
    """Build the bare minimum email report — just required fields.

    This is the smallest valid payload Ralph could send. Tests verify
    jimbo-api handles missing optional fields gracefully.
    """
    return {
        "gmail_id": gmail_id or f"msg_{uuid.uuid4().hex[:12]}",
        "from_email": "noreply@example.com",
        "subject": "Test email",
        "processed_at": "2026-03-15T09:00:00Z",
        "body_analysis": {"summary": "Minimal test email"},
        "links": [],
    }


def build_decision(relevance_score=7):
    """Build a full decision payload matching what the decision worker sends.

    Includes all scoring fields: relevance_score, category, suggested_action,
    reason, insight, connections, time_sensitive, and deadline. Uses realistic
    values that reflect how the worker actually scores newsletter content.
    """
    return {
        "relevance_score": relevance_score,
        "category": "local-events",
        "suggested_action": "review",
        "reason": "Contains specific Watford events matching interests in live comedy and fitness",
        "insight": "Ed Byrne at Palace Theatre is worth booking — last show sold out in 3 days",
        "connections": ["comedy-interest", "watford-local", "fitness-goal"],
        "time_sensitive": True,
        "deadline": "2026-03-22",
    }
```

- [ ] **Step 2: Verify helpers import cleanly**

Run: `cd /Users/marvinbarretto/development/openclaw && python -c "from workspace.tests.integration.helpers import ApiClient, build_full_report, build_minimal_report, build_decision; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add workspace/tests/integration/helpers.py
git commit -m "feat: integration test helpers — API client and test data builders"
```

---

## Chunk 2: Email Reports and Schema Contract Tests

### Task 3: test_email_reports.py — Ralph <-> jimbo-api Contract

**Files:**
- Create: `workspace/tests/integration/test_email_reports.py`

Protects the boundary where Ralph pushes extracted email data to jimbo-api. Real bugs this catches: wrong API paths, missing fields, JSON columns losing nested data.

- [ ] **Step 1: Write test_email_reports.py**

Create `workspace/tests/integration/test_email_reports.py`:

```python
"""
Ralph <-> jimbo-api contract tests.

Protects the boundary where Ralph pushes extracted email data to jimbo-api.
Real bugs this catches:
  - Wrong API paths (Ralph sends to /api/emails/reports, not /api/emails)
  - Missing required fields causing 400s
  - JSON columns (body_analysis, links) losing nested data through SQLite storage
  - Upsert behaviour when Ralph re-processes the same email
  - Auth failures when API key is missing or wrong

Every test hits a real jimbo-api instance with a real SQLite database.
"""

import json
import urllib.error
import urllib.request

from .helpers import ApiClient, build_full_report, build_minimal_report, build_decision


class TestPostReport:
    """Tests for POST /api/emails/reports — Ralph pushing email data."""

    def test_full_report_stored_completely(self, jimbo_server, clear_data):
        """When Ralph sends a complete email report with all fields populated,
        every field should be stored and retrievable — nothing silently dropped.

        This is the happy path: body_analysis with nested entities and events,
        links array with metadata, processing stats. All must survive the
        POST -> SQLite -> GET round-trip.
        """
        client = ApiClient(jimbo_server["url"], jimbo_server["api_key"])
        report = build_full_report(gmail_id="msg_full_test_001")

        # POST the report
        created = client.post("/api/emails/reports", report)

        assert created["gmail_id"] == "msg_full_test_001"
        assert created["subject"] == report["subject"]
        assert created["from_email"] == report["from_email"]
        assert created["from_name"] == report["from_name"]
        assert created["model"] == "llama3.2:3b"

        # GET it back by gmail_id
        fetched = client.get("/api/emails/reports/msg_full_test_001")
        assert fetched["gmail_id"] == "msg_full_test_001"
        assert fetched["subject"] == report["subject"]

    def test_minimal_report_accepted(self, jimbo_server, clear_data):
        """jimbo-api should accept a report with only required fields.

        Ralph sometimes processes emails where extraction yields minimal
        data — empty links, bare summary. The API must not reject these.
        """
        client = ApiClient(jimbo_server["url"], jimbo_server["api_key"])
        report = build_minimal_report(gmail_id="msg_minimal_001")

        created = client.post("/api/emails/reports", report)

        assert created["gmail_id"] == "msg_minimal_001"
        assert created["subject"] == "Test email"
        # Optional fields should have sensible defaults
        assert created["from_name"] == ""
        assert created["links"] == []

    def test_duplicate_gmail_id_upserts(self, jimbo_server, clear_data):
        """When Ralph re-processes an email (same gmail_id), the report
        should be updated — not rejected or duplicated.

        jimbo-api uses ON CONFLICT(gmail_id) DO UPDATE to handle this.
        The second POST should update body_analysis and links but keep
        the same gmail_id.
        """
        client = ApiClient(jimbo_server["url"], jimbo_server["api_key"])
        gmail_id = "msg_upsert_001"

        # First POST
        report_v1 = build_minimal_report(gmail_id=gmail_id)
        report_v1["subject"] = "Original subject"
        client.post("/api/emails/reports", report_v1)

        # Second POST with updated data
        report_v2 = build_full_report(gmail_id=gmail_id)
        report_v2["subject"] = "Original subject"  # subject not in ON CONFLICT UPDATE
        client.post("/api/emails/reports", report_v2)

        # Should still be one report, with updated body_analysis
        fetched = client.get(f"/api/emails/reports/{gmail_id}")
        assert fetched["gmail_id"] == gmail_id
        # body_analysis should be from v2 (the full report)
        assert "key_facts" in fetched["body_analysis"]


class TestGetReports:
    """Tests for GET /api/emails/reports — listing and filtering."""

    def test_undecided_endpoint_returns_only_undecided(self, jimbo_server, clear_data):
        """GET /undecided should return only reports that haven't been
        processed by the decision worker yet.

        This is what the decision worker polls to find work. If it returns
        already-decided reports, the worker wastes LLM calls re-scoring them.
        """
        client = ApiClient(jimbo_server["url"], jimbo_server["api_key"])

        # Create two reports
        client.post("/api/emails/reports", build_full_report(gmail_id="msg_undecided_001"))
        client.post("/api/emails/reports", build_full_report(gmail_id="msg_undecided_002"))

        # Decide one of them
        client.patch("/api/emails/reports/msg_undecided_001/decide", build_decision())

        # Only the undecided one should appear
        undecided = client.get("/api/emails/reports/undecided")
        gmail_ids = [r["gmail_id"] for r in undecided]
        assert "msg_undecided_002" in gmail_ids
        assert "msg_undecided_001" not in gmail_ids

    def test_min_relevance_filter(self, jimbo_server, clear_data):
        """GET /api/emails/reports?min_relevance=7 should only return
        reports with relevance_score >= 7.

        briefing-prep.py uses this to fetch only high-scoring reports
        for the Opus briefing. Low-scoring spam shouldn't pollute the
        briefing input.
        """
        client = ApiClient(jimbo_server["url"], jimbo_server["api_key"])

        # Create and decide two reports with different scores
        client.post("/api/emails/reports", build_full_report(gmail_id="msg_high_001"))
        client.patch("/api/emails/reports/msg_high_001/decide", build_decision(relevance_score=8))

        client.post("/api/emails/reports", build_full_report(gmail_id="msg_low_001"))
        client.patch("/api/emails/reports/msg_low_001/decide", build_decision(relevance_score=3))

        # Filter for min_relevance=7
        filtered = client.get("/api/emails/reports?min_relevance=7")
        gmail_ids = [r["gmail_id"] for r in filtered]
        assert "msg_high_001" in gmail_ids
        assert "msg_low_001" not in gmail_ids

    def test_stats_match_actual_data(self, jimbo_server, clear_data):
        """GET /stats should return counts that match the actual database state.

        The dashboard uses stats to show pipeline health. If counts are
        wrong, Marvin sees misleading numbers.
        """
        client = ApiClient(jimbo_server["url"], jimbo_server["api_key"])

        # Start empty
        stats = client.get("/api/emails/reports/stats")
        assert stats["total"] == 0
        assert stats["undecided"] == 0
        assert stats["decided"] == 0

        # Add two reports, decide one
        client.post("/api/emails/reports", build_full_report(gmail_id="msg_stats_001"))
        client.post("/api/emails/reports", build_full_report(gmail_id="msg_stats_002"))
        client.patch("/api/emails/reports/msg_stats_001/decide", build_decision())

        stats = client.get("/api/emails/reports/stats")
        assert stats["total"] == 2
        assert stats["decided"] == 1
        assert stats["undecided"] == 1


class TestJsonRoundTrip:
    """Tests for JSON data surviving the SQLite storage round-trip."""

    def test_body_analysis_nested_objects_survive(self, jimbo_server, clear_data):
        """body_analysis contains nested entities, events, and relevance
        signals. All must survive being JSON.stringify'd into SQLite and
        JSON.parse'd back out.

        Real failure mode: SQLite stores as TEXT, mapRow() calls JSON.parse().
        If the JSON is malformed or truncated, we lose structured data.
        """
        client = ApiClient(jimbo_server["url"], jimbo_server["api_key"])
        report = build_full_report(gmail_id="msg_json_001")

        client.post("/api/emails/reports", report)
        fetched = client.get("/api/emails/reports/msg_json_001")

        # Verify nested structure survived
        ba = fetched["body_analysis"]
        assert ba["summary"] == report["body_analysis"]["summary"]
        assert len(ba["key_facts"]) == 3
        assert len(ba["entities"]) == 3
        assert ba["entities"][0]["name"] == "Palace Theatre"
        assert ba["entities"][0]["type"] == "venue"
        assert len(ba["events"]) == 1
        assert ba["events"][0]["venue"] == "Palace Theatre, Watford"
        assert ba["relevance_signals"] == ["local events", "comedy", "fitness"]

    def test_links_array_with_nested_metadata(self, jimbo_server, clear_data):
        """links is an array of objects, each with url, title, confidence,
        followed flag, and content_summary. All must round-trip intact.

        Ralph's link follower produces these — if they're lost, the briefing
        has no clickable URLs to show Marvin.
        """
        client = ApiClient(jimbo_server["url"], jimbo_server["api_key"])
        report = build_full_report(gmail_id="msg_links_001")

        client.post("/api/emails/reports", report)
        fetched = client.get("/api/emails/reports/msg_links_001")

        links = fetched["links"]
        assert len(links) == 2
        assert links[0]["url"] == report["links"][0]["url"]
        assert links[0]["confidence"] == 0.9
        assert links[0]["followed"] is True
        assert links[1]["title"] == "Cassiobury parkrun"


class TestAuth:
    """Tests for API authentication."""

    def test_missing_api_key_returns_401(self, jimbo_server, clear_data):
        """Requests without an X-API-Key header should get 401 Unauthorized.

        All /api/* routes require authentication. The /health endpoint
        is the only unauthenticated route.
        """
        url = f"{jimbo_server['url']}/api/emails/reports/stats"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=5)
            assert False, "Expected 401 but got 200"
        except urllib.error.HTTPError as e:
            assert e.code == 401
```

- [ ] **Step 2: Run the tests**

Run: `cd /Users/marvinbarretto/development/openclaw && python -m pytest workspace/tests/integration/test_email_reports.py -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add workspace/tests/integration/test_email_reports.py
git commit -m "feat: integration tests — Ralph <-> jimbo-api email report contract"
```

---

### Task 4: test_schema_contract.py — Schema Drift Protection

**Files:**
- Create: `workspace/tests/integration/test_schema_contract.py`

Guards against the most common failure mode: one repo changes a field name or type and the other doesn't know. Uses maximally-populated payloads.

- [ ] **Step 1: Write test_schema_contract.py**

Create `workspace/tests/integration/test_schema_contract.py`:

```python
"""
Schema drift protection tests.

Guards against the most common multi-repo failure mode: one repo changes
a field name or type and the other repo doesn't know.

Uses maximally-populated payloads to catch any field that gets silently
dropped. If Ralph adds a new field to body_analysis and jimbo-api doesn't
preserve it, these tests catch it.
"""

from .helpers import ApiClient, build_full_report, build_decision


class TestFullReportRoundTrip:
    """Verify every field Ralph sends survives the POST -> SQLite -> GET cycle."""

    def test_all_report_fields_preserved(self, jimbo_server, clear_data):
        """POST a maximally-populated report, GET it back, and verify
        every field matches.

        This catches silent field drops — e.g., if jimbo-api's createReport()
        doesn't include a new field in the INSERT statement, or if mapRow()
        doesn't parse a JSON column correctly.
        """
        client = ApiClient(jimbo_server["url"], jimbo_server["api_key"])
        report = build_full_report(gmail_id="msg_schema_full_001")

        client.post("/api/emails/reports", report)
        fetched = client.get("/api/emails/reports/msg_schema_full_001")

        # Top-level fields
        assert fetched["gmail_id"] == report["gmail_id"]
        assert fetched["from_email"] == report["from_email"]
        assert fetched["from_name"] == report["from_name"]
        assert fetched["subject"] == report["subject"]
        assert fetched["model"] == report["model"]
        assert fetched["processing_time_seconds"] == report["processing_time_seconds"]

        # JSON fields — must survive stringify -> store -> parse cycle
        assert fetched["body_analysis"] == report["body_analysis"]
        assert fetched["links"] == report["links"]

        # Default state: not yet decided
        assert fetched["decided"] is False
        assert fetched["decision"] is None
        assert fetched["relevance_score"] is None


class TestFullDecisionRoundTrip:
    """Verify every decision field survives the PATCH -> SQLite -> GET cycle."""

    def test_all_decision_fields_preserved(self, jimbo_server, clear_data):
        """PATCH a maximally-populated decision, GET the report back,
        and verify every decision field is correct.

        jimbo-api stores decisions two ways:
          1. The entire decision object as JSON in the `decision` column
          2. relevance_score as a discrete INTEGER column (for SQL filtering)

        The API response nests decision fields under a `decision` object.
        This test verifies both the nested structure and the discrete column.
        """
        client = ApiClient(jimbo_server["url"], jimbo_server["api_key"])

        # Create a report first
        client.post("/api/emails/reports", build_full_report(gmail_id="msg_schema_decision_001"))

        # PATCH with a full decision
        decision = build_decision(relevance_score=8)
        result = client.patch("/api/emails/reports/msg_schema_decision_001/decide", decision)

        # Verify the response has the decision nested correctly
        assert result["decided"] is True
        assert result["relevance_score"] == 8  # discrete column
        assert result["decision"] is not None

        # Every field in the decision blob must match what we sent
        d = result["decision"]
        assert d["relevance_score"] == 8
        assert d["category"] == "local-events"
        assert d["suggested_action"] == "review"
        assert d["reason"] == decision["reason"]
        assert d["insight"] == decision["insight"]
        assert d["connections"] == ["comedy-interest", "watford-local", "fitness-goal"]
        assert d["time_sensitive"] is True
        assert d["deadline"] == "2026-03-22"

        # GET it back separately to verify persistence (not just in-memory)
        fetched = client.get("/api/emails/reports/msg_schema_decision_001")
        assert fetched["decided"] is True
        assert fetched["relevance_score"] == 8
        assert fetched["decision"]["category"] == "local-events"
        assert fetched["decision"]["connections"] == ["comedy-interest", "watford-local", "fitness-goal"]


class TestNestedJsonIntegrity:
    """Verify deeply nested JSON structures survive SQLite storage."""

    def test_deep_body_analysis_nesting(self, jimbo_server, clear_data):
        """body_analysis can contain arbitrarily nested objects — entities
        with type fields, events with date/venue/price, and arrays of
        relevance signals. All must survive the SQLite TEXT column.
        """
        client = ApiClient(jimbo_server["url"], jimbo_server["api_key"])
        report = build_full_report(gmail_id="msg_schema_deep_001")

        # Add extra nesting to push the limits
        report["body_analysis"]["metadata"] = {
            "extraction_version": 2,
            "confidence_scores": {"entities": 0.95, "events": 0.88, "summary": 0.92},
            "nested_tags": [["comedy", "live"], ["fitness", "outdoor"]],
        }

        client.post("/api/emails/reports", report)
        fetched = client.get("/api/emails/reports/msg_schema_deep_001")

        assert fetched["body_analysis"]["metadata"]["extraction_version"] == 2
        assert fetched["body_analysis"]["metadata"]["confidence_scores"]["entities"] == 0.95
        assert fetched["body_analysis"]["metadata"]["nested_tags"] == [["comedy", "live"], ["fitness", "outdoor"]]

    def test_connections_array_in_decision(self, jimbo_server, clear_data):
        """The connections array in a decision links email content to
        Marvin's priorities and interests. It's stored inside the decision
        JSON blob and must come back as a proper array, not a string.
        """
        client = ApiClient(jimbo_server["url"], jimbo_server["api_key"])

        client.post("/api/emails/reports", build_full_report(gmail_id="msg_schema_conn_001"))
        decision = build_decision()
        decision["connections"] = ["priority-localshout", "interest-comedy", "goal-fitness", "interest-watford-fc"]
        client.patch("/api/emails/reports/msg_schema_conn_001/decide", decision)

        fetched = client.get("/api/emails/reports/msg_schema_conn_001")
        connections = fetched["decision"]["connections"]

        # Must be a list, not a string
        assert isinstance(connections, list)
        assert len(connections) == 4
        assert "priority-localshout" in connections


class TestNullAndEmptyHandling:
    """Verify optional fields handle null and empty values correctly."""

    def test_null_optional_fields(self, jimbo_server, clear_data):
        """Optional fields sent as null or missing should come back as
        null/None — not as empty strings, not as 'null' string, not dropped.
        """
        client = ApiClient(jimbo_server["url"], jimbo_server["api_key"])

        report = build_minimal_report(gmail_id="msg_schema_null_001")
        client.post("/api/emails/reports", report)

        fetched = client.get("/api/emails/reports/msg_schema_null_001")
        # These were never set, should be null/default
        assert fetched["decision"] is None
        assert fetched["relevance_score"] is None
        assert fetched["decided"] is False

    def test_empty_arrays_preserved(self, jimbo_server, clear_data):
        """Empty arrays (links: []) should come back as empty arrays,
        not null, not dropped, not the string '[]'.
        """
        client = ApiClient(jimbo_server["url"], jimbo_server["api_key"])

        report = build_minimal_report(gmail_id="msg_schema_empty_001")
        report["links"] = []
        client.post("/api/emails/reports", report)

        fetched = client.get("/api/emails/reports/msg_schema_empty_001")
        assert fetched["links"] == []
        assert isinstance(fetched["links"], list)

    def test_empty_connections_in_decision(self, jimbo_server, clear_data):
        """A decision with connections: [] should preserve the empty array.

        Some emails genuinely have no connections to priorities — the
        decision worker scores them but finds nothing to link.
        """
        client = ApiClient(jimbo_server["url"], jimbo_server["api_key"])

        client.post("/api/emails/reports", build_full_report(gmail_id="msg_schema_emptyconn_001"))
        decision = build_decision()
        decision["connections"] = []
        decision["deadline"] = None
        client.patch("/api/emails/reports/msg_schema_emptyconn_001/decide", decision)

        fetched = client.get("/api/emails/reports/msg_schema_emptyconn_001")
        assert fetched["decision"]["connections"] == []
        assert fetched["decision"]["deadline"] is None
```

- [ ] **Step 2: Run the tests**

Run: `cd /Users/marvinbarretto/development/openclaw && python -m pytest workspace/tests/integration/test_schema_contract.py -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add workspace/tests/integration/test_schema_contract.py
git commit -m "feat: integration tests — schema drift protection for email reports"
```

---

## Chunk 3: Decision Worker and Context API Tests

### Task 5: test_email_decisions.py — Decision Worker <-> jimbo-api Contract

**Files:**
- Create: `workspace/tests/integration/test_email_decisions.py`

Runs against the real jimbo-api. Only the LLM call is mocked — everything else is real HTTP.

- [ ] **Step 1: Write test_email_decisions.py**

Create `workspace/tests/integration/test_email_decisions.py`:

```python
"""
Decision worker <-> jimbo-api contract tests.

Verifies the PATCH /decide endpoint works correctly when the decision
worker submits scoring results. Only the LLM call would be mocked in
a full worker test — here we test the HTTP contract directly.

Real bugs this catches:
  - Decision fields not stored in the JSON blob
  - relevance_score not written to the discrete column (breaks SQL filtering)
  - decided flag not set (report keeps appearing in /undecided)
  - decided_at timestamp not recorded
"""

from .helpers import ApiClient, build_full_report, build_decision


class TestDecideEndpoint:
    """Tests for PATCH /api/emails/reports/:gmail_id/decide."""

    def test_decision_stores_all_fields(self, jimbo_server, clear_data):
        """When the decision worker PATCHes a decision, every field should
        be stored: the full JSON blob in the `decision` column AND the
        relevance_score in its discrete column.

        The discrete column matters because listing endpoints filter on it
        (WHERE relevance_score >= ?).
        """
        client = ApiClient(jimbo_server["url"], jimbo_server["api_key"])

        # Seed a report
        client.post("/api/emails/reports", build_full_report(gmail_id="msg_decide_001"))

        # Submit decision
        decision = build_decision(relevance_score=9)
        result = client.patch("/api/emails/reports/msg_decide_001/decide", decision)

        # Verify response shape
        assert result["decided"] is True
        assert result["relevance_score"] == 9  # discrete column
        assert result["decided_at"] is not None  # timestamp recorded
        assert result["decision"]["relevance_score"] == 9  # in JSON blob too
        assert result["decision"]["category"] == "local-events"
        assert result["decision"]["insight"] == decision["insight"]

    def test_decided_report_leaves_undecided_list(self, jimbo_server, clear_data):
        """After a report is decided, it should no longer appear in the
        /undecided endpoint.

        If it still appears, the decision worker will re-process it on
        the next run — wasting LLM calls and potentially overwriting
        the existing decision.
        """
        client = ApiClient(jimbo_server["url"], jimbo_server["api_key"])

        # Create and decide a report
        client.post("/api/emails/reports", build_full_report(gmail_id="msg_decided_001"))
        client.patch("/api/emails/reports/msg_decided_001/decide", build_decision())

        # Should not appear in undecided
        undecided = client.get("/api/emails/reports/undecided")
        gmail_ids = [r["gmail_id"] for r in undecided]
        assert "msg_decided_001" not in gmail_ids

    def test_decide_nonexistent_report_returns_404(self, jimbo_server, clear_data):
        """PATCHing a decision for a gmail_id that doesn't exist should
        return 404 — not create a phantom record.
        """
        client = ApiClient(jimbo_server["url"], jimbo_server["api_key"])

        try:
            client.patch("/api/emails/reports/msg_ghost_001/decide", build_decision())
            assert False, "Expected 404"
        except AssertionError as e:
            assert "404" in str(e)

    def test_decide_requires_relevance_score(self, jimbo_server, clear_data):
        """The decision endpoint requires relevance_score as a number.

        If the LLM returns garbage and the worker sends a decision without
        relevance_score, the API should reject it with 400 rather than
        storing an incomplete decision.
        """
        client = ApiClient(jimbo_server["url"], jimbo_server["api_key"])

        client.post("/api/emails/reports", build_full_report(gmail_id="msg_invalid_001"))

        try:
            # Missing relevance_score entirely
            client.patch("/api/emails/reports/msg_invalid_001/decide", {
                "category": "local-events",
                "reason": "test",
            })
            assert False, "Expected 400"
        except AssertionError as e:
            assert "400" in str(e)

    def test_multiple_reports_decided_independently(self, jimbo_server, clear_data):
        """Each report's decision should be independent — deciding one
        report must not affect another.

        Catches bugs where a shared variable or wrong WHERE clause
        could bleed state between reports.
        """
        client = ApiClient(jimbo_server["url"], jimbo_server["api_key"])

        # Create three reports
        for i in range(3):
            client.post("/api/emails/reports", build_full_report(gmail_id=f"msg_multi_{i:03d}"))

        # Decide first with score 9, second with score 3
        client.patch("/api/emails/reports/msg_multi_000/decide", build_decision(relevance_score=9))
        client.patch("/api/emails/reports/msg_multi_001/decide", build_decision(relevance_score=3))

        # Third should still be undecided
        undecided = client.get("/api/emails/reports/undecided")
        gmail_ids = [r["gmail_id"] for r in undecided]
        assert "msg_multi_002" in gmail_ids
        assert len(gmail_ids) == 1

        # Verify independent scores
        r0 = client.get("/api/emails/reports/msg_multi_000")
        r1 = client.get("/api/emails/reports/msg_multi_001")
        assert r0["relevance_score"] == 9
        assert r1["relevance_score"] == 3
```

- [ ] **Step 2: Run the HTTP contract tests**

Run: `cd /Users/marvinbarretto/development/openclaw && python -m pytest workspace/tests/integration/test_email_decisions.py::TestDecideEndpoint -v`
Expected: All tests PASS

- [ ] **Step 3: Write worker-level tests with mocked LLM**

Add to `workspace/tests/integration/test_email_decisions.py`:

```python
import os
import sys
from unittest.mock import patch

# Add workspace dir so we can import the worker
_workspace_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _workspace_dir not in sys.path:
    sys.path.insert(0, _workspace_dir)


class TestEmailDecisionWorker:
    """Tests that run the actual EmailDecisionWorker class against a real
    jimbo-api. Only the LLM call is mocked — HTTP and DB are real.

    This catches integration bugs that HTTP-only tests miss: the worker's
    fetch → prompt → parse → patch pipeline as a whole.
    """

    def test_worker_processes_undecided_reports(self, jimbo_server, clear_data):
        """Seed reports, run the worker with a mocked LLM, verify decisions
        are PATCHed back with correct fields.

        The mock LLM returns a valid JSON decision. The worker should
        fetch undecided reports, call the LLM for each, parse the response,
        and PATCH the decision back to jimbo-api.
        """
        client = ApiClient(jimbo_server["url"], jimbo_server["api_key"])

        # Seed two undecided reports
        client.post("/api/emails/reports", build_full_report(gmail_id="msg_worker_001"))
        client.post("/api/emails/reports", build_full_report(gmail_id="msg_worker_002"))

        mock_response = {
            "text": json.dumps({
                "relevance_score": 7,
                "category": "local-events",
                "suggested_action": "surface-in-briefing",
                "reason": "Local comedy event matches interests",
                "insight": "Ed Byrne at Palace Theatre worth booking",
                "connections": ["comedy-interest"],
                "time_sensitive": True,
                "deadline": "2026-03-22",
            }),
            "input_tokens": 500,
            "output_tokens": 100,
        }

        os.environ["JIMBO_API_URL"] = jimbo_server["url"]
        os.environ["JIMBO_API_KEY"] = jimbo_server["api_key"]
        try:
            from workers.email_decision import EmailDecisionWorker
            with patch("workers.email_decision.call_model", return_value=mock_response), \
                 patch.object(EmailDecisionWorker, "log_run"):  # skip experiment tracker
                worker = EmailDecisionWorker()
                result = worker.run()

            assert result["decided"] == 2
            assert result["errors"] == 0

            # Verify decisions were persisted
            r1 = client.get("/api/emails/reports/msg_worker_001")
            assert r1["decided"] is True
            assert r1["decision"]["category"] == "local-events"
        finally:
            os.environ.pop("JIMBO_API_URL", None)
            os.environ.pop("JIMBO_API_KEY", None)

    def test_worker_handles_empty_queue(self, jimbo_server, clear_data):
        """When there are no undecided reports, the worker should complete
        gracefully with decided=0 and errors=0.

        The LLM should never be called — no reports means no work.
        """
        os.environ["JIMBO_API_URL"] = jimbo_server["url"]
        os.environ["JIMBO_API_KEY"] = jimbo_server["api_key"]
        try:
            from workers.email_decision import EmailDecisionWorker
            with patch("workers.email_decision.call_model") as mock_call, \
                 patch.object(EmailDecisionWorker, "log_run"):
                worker = EmailDecisionWorker()
                result = worker.run()

            assert result["decided"] == 0
            assert result["errors"] == 0
            mock_call.assert_not_called()  # no LLM calls if queue is empty
        finally:
            os.environ.pop("JIMBO_API_URL", None)
            os.environ.pop("JIMBO_API_KEY", None)

    def test_worker_handles_llm_garbage(self, jimbo_server, clear_data):
        """When the LLM returns unparseable text (not JSON), the report
        should stay undecided and the worker should not crash.

        The worker increments errors but continues to the next report.
        """
        client = ApiClient(jimbo_server["url"], jimbo_server["api_key"])
        client.post("/api/emails/reports", build_full_report(gmail_id="msg_garbage_001"))

        mock_response = {
            "text": "I'm sorry, I can't score this email. It seems irrelevant.",
            "input_tokens": 500,
            "output_tokens": 50,
        }

        os.environ["JIMBO_API_URL"] = jimbo_server["url"]
        os.environ["JIMBO_API_KEY"] = jimbo_server["api_key"]
        try:
            from workers.email_decision import EmailDecisionWorker
            with patch("workers.email_decision.call_model", return_value=mock_response), \
                 patch.object(EmailDecisionWorker, "log_run"):
                worker = EmailDecisionWorker()
                result = worker.run()

            assert result["decided"] == 0
            assert result["errors"] == 1

            # Report should still be undecided
            undecided = client.get("/api/emails/reports/undecided")
            gmail_ids = [r["gmail_id"] for r in undecided]
            assert "msg_garbage_001" in gmail_ids
        finally:
            os.environ.pop("JIMBO_API_URL", None)
            os.environ.pop("JIMBO_API_KEY", None)

    def test_worker_handles_llm_missing_fields(self, jimbo_server, clear_data):
        """When the LLM returns valid JSON but without relevance_score,
        the report should stay undecided.

        parse_decision() returns None when relevance_score is missing,
        so the worker skips the PATCH and increments errors.
        """
        client = ApiClient(jimbo_server["url"], jimbo_server["api_key"])
        client.post("/api/emails/reports", build_full_report(gmail_id="msg_nofield_001"))

        mock_response = {
            "text": json.dumps({
                "category": "local-events",
                "reason": "Missing the required relevance_score field",
            }),
            "input_tokens": 500,
            "output_tokens": 80,
        }

        os.environ["JIMBO_API_URL"] = jimbo_server["url"]
        os.environ["JIMBO_API_KEY"] = jimbo_server["api_key"]
        try:
            from workers.email_decision import EmailDecisionWorker
            with patch("workers.email_decision.call_model", return_value=mock_response), \
                 patch.object(EmailDecisionWorker, "log_run"):
                worker = EmailDecisionWorker()
                result = worker.run()

            assert result["decided"] == 0
            assert result["errors"] == 1

            # Report should still be undecided
            undecided = client.get("/api/emails/reports/undecided")
            gmail_ids = [r["gmail_id"] for r in undecided]
            assert "msg_nofield_001" in gmail_ids
        finally:
            os.environ.pop("JIMBO_API_URL", None)
            os.environ.pop("JIMBO_API_KEY", None)
```

Note: the worker tests need `import json` and the helpers at the top of the file. Add these imports:

```python
import json
import os
import sys
from unittest.mock import patch

from .helpers import ApiClient, build_full_report, build_decision
```

- [ ] **Step 4: Run all decision tests**

Run: `cd /Users/marvinbarretto/development/openclaw && python -m pytest workspace/tests/integration/test_email_decisions.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add workspace/tests/integration/test_email_decisions.py
git commit -m "feat: integration tests — decision worker <-> jimbo-api contract"
```

---

### Task 6: test_context_api.py — Worker Context Fetching

**Files:**
- Create: `workspace/tests/integration/test_context_api.py`

Verifies workers can fetch structured context from jimbo-api and get usable text back. Real bugs this catches: wrong API paths for context, response format changes, empty sections.

- [ ] **Step 1: Write test_context_api.py**

Create `workspace/tests/integration/test_context_api.py`:

```python
"""
Worker context fetching <-> jimbo-api contract tests.

Verifies that workers can fetch structured context (priorities, interests,
goals) from jimbo-api and get usable data back.

Real bugs this catches:
  - Wrong API paths (workers fetch /api/context/files/{slug})
  - Response format changes (sections/items nesting)
  - Empty context files causing worker crashes
  - Missing slugs causing unhandled 404s

Context is seeded directly into the test SQLite DB — jimbo-api has no
single "create context file" endpoint, so we insert rows directly
using Python's sqlite3 module.
"""

import sqlite3

from .helpers import ApiClient


def seed_context(db_path, slug, display_name, sections):
    """Insert context data directly into SQLite for testing.

    This bypasses the API because jimbo-api's context file creation
    happens via a seed script, not a single API endpoint.

    Args:
        db_path: path to the throwaway SQLite DB
        slug: context file slug (e.g., 'priorities')
        display_name: human-readable name (e.g., 'Priorities')
        sections: list of {name, items: [{label, content, status?, category?}]}
    """
    db = sqlite3.connect(db_path)
    try:
        db.execute(
            "INSERT INTO context_files (slug, display_name, sort_order) VALUES (?, ?, 0)",
            (slug, display_name),
        )
        file_id = db.execute(
            "SELECT id FROM context_files WHERE slug = ?", (slug,)
        ).fetchone()[0]

        for i, section in enumerate(sections):
            db.execute(
                "INSERT INTO context_sections (file_id, name, sort_order) VALUES (?, ?, ?)",
                (file_id, section["name"], i),
            )
            section_id = db.execute(
                "SELECT id FROM context_sections WHERE file_id = ? AND name = ?",
                (file_id, section["name"]),
            ).fetchone()[0]

            for j, item in enumerate(section.get("items", [])):
                db.execute(
                    "INSERT INTO context_items (section_id, label, content, status, category, sort_order) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        section_id,
                        item.get("label"),
                        item["content"],
                        item.get("status", "active"),
                        item.get("category"),
                        j,
                    ),
                )
        db.commit()
    finally:
        db.close()


class TestContextFetch:
    """Tests for GET /api/context/files/:slug — worker context fetching."""

    def test_seed_and_fetch_priorities(self, jimbo_server, clear_data):
        """Workers fetch priorities via GET /api/context/files/priorities.

        The response should include the display name, sections with names,
        and items with labels and content. This is what BaseWorker.get_context()
        calls for each context_slug in the task config.
        """
        seed_context(jimbo_server["db_path"], "priorities", "Priorities", [
            {
                "name": "This Week",
                "items": [
                    {"label": "LocalShout", "content": "Ship MVP landing page", "status": "active", "category": "project"},
                    {"label": "Jimbo", "content": "Fix morning briefing pipeline", "status": "active", "category": "project"},
                ],
            },
        ])

        client = ApiClient(jimbo_server["url"], jimbo_server["api_key"])
        data = client.get("/api/context/files/priorities")

        assert data["slug"] == "priorities"
        assert data["display_name"] == "Priorities"
        assert len(data["sections"]) == 1
        assert data["sections"][0]["name"] == "This Week"
        items = data["sections"][0]["items"]
        assert len(items) == 2
        assert items[0]["label"] == "LocalShout"
        assert items[0]["content"] == "Ship MVP landing page"
        assert items[0]["status"] == "active"

    def test_seed_and_fetch_interests(self, jimbo_server, clear_data):
        """Same pattern as priorities but for interests.

        Workers like email-triage use interests to score relevance —
        if the API returns wrong data, emails get mis-scored.
        """
        seed_context(jimbo_server["db_path"], "interests", "Interests", [
            {
                "name": "Entertainment",
                "items": [
                    {"label": "Football", "content": "Watford FC, Arsenal. Match days, transfer news"},
                    {"label": "Comedy", "content": "Stand-up, panel shows. Ed Byrne, James Acaster"},
                ],
            },
            {
                "name": "Lifestyle",
                "items": [
                    {"label": "Fitness", "content": "Running, gym. Cassiobury parkrun"},
                    {"label": "Travel", "content": "Deals, weekend breaks. Flight scanner alerts"},
                ],
            },
        ])

        client = ApiClient(jimbo_server["url"], jimbo_server["api_key"])
        data = client.get("/api/context/files/interests")

        assert data["display_name"] == "Interests"
        assert len(data["sections"]) == 2
        assert data["sections"][0]["name"] == "Entertainment"
        assert data["sections"][1]["name"] == "Lifestyle"

        # Verify items in second section
        lifestyle_items = data["sections"][1]["items"]
        assert len(lifestyle_items) == 2
        labels = [item["label"] for item in lifestyle_items]
        assert "Fitness" in labels
        assert "Travel" in labels

    def test_multiple_sections_and_items(self, jimbo_server, clear_data):
        """A context file with multiple sections, each with multiple items,
        should preserve the full nested structure.

        This catches bugs where only the first section or first item
        is returned — a common off-by-one in SQL queries.
        """
        seed_context(jimbo_server["db_path"], "goals", "Goals", [
            {
                "name": "Q1 2026",
                "items": [
                    {"label": "LocalShout MVP", "content": "Launch community platform", "category": "project"},
                    {"label": "Spanish B1", "content": "Pass B1 exam by March", "category": "habit"},
                ],
            },
            {
                "name": "Long-term",
                "items": [
                    {"label": "Financial independence", "content": "Build passive income streams", "category": "life-area"},
                ],
            },
        ])

        client = ApiClient(jimbo_server["url"], jimbo_server["api_key"])
        data = client.get("/api/context/files/goals")

        assert len(data["sections"]) == 2

        q1_items = data["sections"][0]["items"]
        assert len(q1_items) == 2
        assert q1_items[0]["category"] == "project"
        assert q1_items[1]["category"] == "habit"

        lt_items = data["sections"][1]["items"]
        assert len(lt_items) == 1
        assert lt_items[0]["category"] == "life-area"

    def test_empty_context_file_returns_empty_sections(self, jimbo_server, clear_data):
        """A context file that exists but has no sections should return
        an empty sections array — not 404, not an error.

        Workers must handle this gracefully without crashing.
        """
        seed_context(jimbo_server["db_path"], "empty-file", "Empty Context", [])

        client = ApiClient(jimbo_server["url"], jimbo_server["api_key"])
        data = client.get("/api/context/files/empty-file")

        assert data["slug"] == "empty-file"
        assert data["sections"] == []

    def test_missing_context_file_returns_404(self, jimbo_server, clear_data):
        """Fetching a slug that doesn't exist should return 404.

        Workers log a warning and continue when this happens — they
        don't crash. But the API must return 404, not 200 with empty data.
        """
        client = ApiClient(jimbo_server["url"], jimbo_server["api_key"])

        import urllib.error
        try:
            client.get("/api/context/files/nonexistent-slug")
            assert False, "Expected 404"
        except AssertionError as e:
            assert "404" in str(e)
```

- [ ] **Step 2: Run the tests**

Run: `cd /Users/marvinbarretto/development/openclaw && python -m pytest workspace/tests/integration/test_context_api.py -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add workspace/tests/integration/test_context_api.py
git commit -m "feat: integration tests — context API contract for worker context fetching"
```

---

## Chunk 4: Briefing Integration Tests

### Task 7: test_briefing_integration.py — Briefing-prep <-> jimbo-api Contract

**Files:**
- Create: `workspace/tests/integration/test_briefing_integration.py`
- Modify: `workspace/briefing-prep.py` (fix decision field nesting bug)

Verifies `fetch_email_insights()` returns the right data for the Opus prompt. **This task also fixes the known bug** where decision fields are read as top-level but jimbo-api nests them under `decision`.

- [ ] **Step 1: Write the failing test that exposes the decision field nesting bug**

Create `workspace/tests/integration/test_briefing_integration.py` — start with just the bug-exposing test:

```python
"""
Briefing-prep <-> jimbo-api contract tests.

Verifies that fetch_email_insights() in briefing-prep.py correctly
fetches and processes decided email reports for the Opus briefing prompt.

Real bugs this catches:
  - Decision fields read as top-level when jimbo-api nests them under `decision`
  - Time window filtering (client-side in Python, not an API parameter)
  - Relevance sorting (highest score first)
  - Empty results handling

KNOWN BUG CAUGHT HERE: fetch_email_insights() reads r.get("category")
as a top-level field, but jimbo-api's mapRow() returns decision fields
nested under a `decision` object. The category field (and others) come
back as None instead of their actual values.
"""

import datetime
import os
import sys

from .helpers import ApiClient, build_full_report, build_decision

# Add workspace dir to path so we can import briefing-prep functions
_workspace_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _workspace_dir not in sys.path:
    sys.path.insert(0, _workspace_dir)


class TestDecisionFieldAccess:
    """Verify fetch_email_insights() correctly reads decision fields.

    This is the most important test — it catches the known bug where
    decision fields are read from the wrong nesting level.
    """

    def test_category_read_from_decision_object(self, jimbo_server, clear_data):
        """fetch_email_insights() must read category from r['decision']['category'],
        not r['category'].

        jimbo-api's mapRow() returns:
          {
            gmail_id: '...',
            relevance_score: 8,  // discrete column, top-level
            decision: {          // JSON blob, nested
              relevance_score: 8,
              category: 'local-events',
              ...
            }
          }

        The bug: briefing-prep.py does r.get('category') which returns None
        because category is inside the decision object, not top-level.
        """
        client = ApiClient(jimbo_server["url"], jimbo_server["api_key"])

        # Seed a report and decide it
        client.post("/api/emails/reports", build_full_report(gmail_id="msg_brief_cat_001"))
        client.patch("/api/emails/reports/msg_brief_cat_001/decide", build_decision(relevance_score=8))

        # Verify the API response shape — decision fields ARE nested
        report = client.get("/api/emails/reports/msg_brief_cat_001")
        assert report["decision"]["category"] == "local-events"
        assert report.get("category") is None  # NOT top-level

        # Now test fetch_email_insights() handles this correctly
        os.environ["JIMBO_API_URL"] = jimbo_server["url"]
        os.environ["JIMBO_API_KEY"] = jimbo_server["api_key"]

        try:
            # Import after setting env vars
            # Use importlib to avoid caching issues
            import importlib
            bp = importlib.import_module("briefing-prep")
            importlib.reload(bp)

            insights, status = bp.fetch_email_insights(hours=24, min_relevance=1)

            assert status["status"] == "ok"
            assert len(insights) >= 1

            # The critical assertion: category must not be None
            insight = next(i for i in insights if i["gmail_id"] == "msg_brief_cat_001")
            assert insight["category"] == "local-events", (
                f"category is {insight['category']!r} — fetch_email_insights() is reading "
                f"from the wrong level. Decision fields are nested under r['decision'], "
                f"not top-level."
            )
            assert insight["suggested_action"] == "review"
            assert insight["reason"] is not None
            assert insight["insight"] is not None
            assert insight["connections"] == ["comedy-interest", "watford-local", "fitness-goal"]
            assert insight["time_sensitive"] is True
            assert insight["deadline"] == "2026-03-22"
        finally:
            # Clean up env vars
            os.environ.pop("JIMBO_API_URL", None)
            os.environ.pop("JIMBO_API_KEY", None)
```

- [ ] **Step 2: Run the test to confirm it fails (the known bug)**

Run: `cd /Users/marvinbarretto/development/openclaw && python -m pytest workspace/tests/integration/test_briefing_integration.py::TestDecisionFieldAccess::test_category_read_from_decision_object -v`
Expected: FAIL — `category is None` because fetch_email_insights reads from wrong level

- [ ] **Step 3: Fix the bug in briefing-prep.py**

In `workspace/briefing-prep.py`, the `fetch_email_insights()` function reads decision fields as top-level (`r.get("category")`), but jimbo-api nests them under `r["decision"]`. Fix by reading from the decision object:

Change lines 360-372 in `fetch_email_insights()` from:

```python
            recent.append({
                "gmail_id": r.get("gmail_id"),
                "subject": r.get("subject"),
                "from_email": r.get("from_email"),
                "relevance_score": r.get("relevance_score"),
                "category": r.get("category"),
                "suggested_action": r.get("suggested_action"),
                "reason": r.get("reason"),
                "insight": r.get("insight"),
                "connections": r.get("connections", []),
                "time_sensitive": r.get("time_sensitive", False),
                "deadline": r.get("deadline"),
            })
```

To:

```python
            # Decision fields are nested under r["decision"] — jimbo-api's
            # mapRow() parses the JSON blob into a nested object.
            # relevance_score is ALSO a discrete top-level column (for SQL filtering).
            decision = r.get("decision") or {}
            recent.append({
                "gmail_id": r.get("gmail_id"),
                "subject": r.get("subject"),
                "from_email": r.get("from_email"),
                "relevance_score": r.get("relevance_score"),
                "category": decision.get("category"),
                "suggested_action": decision.get("suggested_action"),
                "reason": decision.get("reason"),
                "insight": decision.get("insight"),
                "connections": decision.get("connections", []),
                "time_sensitive": decision.get("time_sensitive", False),
                "deadline": decision.get("deadline"),
            })
```

- [ ] **Step 4: Run the test again to verify it passes**

Run: `cd /Users/marvinbarretto/development/openclaw && python -m pytest workspace/tests/integration/test_briefing_integration.py::TestDecisionFieldAccess::test_category_read_from_decision_object -v`
Expected: PASS

- [ ] **Step 5: Write the remaining briefing integration tests**

Add to `workspace/tests/integration/test_briefing_integration.py`:

```python
class TestFetchEmailInsights:
    """Tests for the full fetch_email_insights() function."""

    def test_time_window_filtering(self, jimbo_server, clear_data):
        """Reports decided outside the time window should be excluded.

        fetch_email_insights() filters client-side by decided_at timestamp.
        A report decided 20 hours ago should NOT appear when hours=14.
        A report decided 1 hour ago SHOULD appear.

        We manipulate decided_at directly in SQLite because the API always
        sets decided_at to 'now' — there's no way to backdate via the API.
        """
        client = ApiClient(jimbo_server["url"], jimbo_server["api_key"])

        # Create and decide two reports
        client.post("/api/emails/reports", build_full_report(gmail_id="msg_old_001"))
        client.patch("/api/emails/reports/msg_old_001/decide", build_decision(relevance_score=8))

        client.post("/api/emails/reports", build_full_report(gmail_id="msg_new_001"))
        client.patch("/api/emails/reports/msg_new_001/decide", build_decision(relevance_score=8))

        # Backdate the first report's decided_at to 20 hours ago
        import sqlite3
        old_time = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=20)).isoformat()
        db = sqlite3.connect(jimbo_server["db_path"])
        db.execute("UPDATE email_reports SET decided_at = ? WHERE gmail_id = ?", (old_time, "msg_old_001"))
        db.commit()
        db.close()

        os.environ["JIMBO_API_URL"] = jimbo_server["url"]
        os.environ["JIMBO_API_KEY"] = jimbo_server["api_key"]
        try:
            import importlib
            bp = importlib.import_module("briefing-prep")
            importlib.reload(bp)
            insights, status = bp.fetch_email_insights(hours=14, min_relevance=1)

            gmail_ids = [i["gmail_id"] for i in insights]
            assert "msg_new_001" in gmail_ids, "Recent report should be included"
            assert "msg_old_001" not in gmail_ids, (
                "Report decided 20 hours ago should be excluded with hours=14"
            )
        finally:
            os.environ.pop("JIMBO_API_URL", None)
            os.environ.pop("JIMBO_API_KEY", None)

    def test_sorted_by_relevance_descending(self, jimbo_server, clear_data):
        """Insights should be sorted highest relevance_score first.

        The Opus prompt processes them in order — highest-scoring emails
        should appear first so Opus sees the most important items first.
        """
        client = ApiClient(jimbo_server["url"], jimbo_server["api_key"])

        # Create reports with different scores
        for gmail_id, score in [("msg_sort_low", 3), ("msg_sort_high", 9), ("msg_sort_mid", 6)]:
            client.post("/api/emails/reports", build_full_report(gmail_id=gmail_id))
            client.patch(f"/api/emails/reports/{gmail_id}/decide", build_decision(relevance_score=score))

        os.environ["JIMBO_API_URL"] = jimbo_server["url"]
        os.environ["JIMBO_API_KEY"] = jimbo_server["api_key"]
        try:
            import importlib
            bp = importlib.import_module("briefing-prep")
            importlib.reload(bp)
            insights, status = bp.fetch_email_insights(hours=24, min_relevance=1)

            scores = [i["relevance_score"] for i in insights]
            assert scores == sorted(scores, reverse=True), (
                f"Insights not sorted by relevance descending: {scores}"
            )
        finally:
            os.environ.pop("JIMBO_API_URL", None)
            os.environ.pop("JIMBO_API_KEY", None)

    def test_min_relevance_filtering(self, jimbo_server, clear_data):
        """Low-scoring reports should be excluded by the API query parameter.

        briefing-prep passes min_relevance=5 by default — spam and
        irrelevant emails (score < 5) shouldn't waste Opus's context window.
        """
        client = ApiClient(jimbo_server["url"], jimbo_server["api_key"])

        client.post("/api/emails/reports", build_full_report(gmail_id="msg_rel_high"))
        client.patch("/api/emails/reports/msg_rel_high/decide", build_decision(relevance_score=8))

        client.post("/api/emails/reports", build_full_report(gmail_id="msg_rel_low"))
        client.patch("/api/emails/reports/msg_rel_low/decide", build_decision(relevance_score=2))

        os.environ["JIMBO_API_URL"] = jimbo_server["url"]
        os.environ["JIMBO_API_KEY"] = jimbo_server["api_key"]
        try:
            import importlib
            bp = importlib.import_module("briefing-prep")
            importlib.reload(bp)
            insights, status = bp.fetch_email_insights(hours=24, min_relevance=5)

            gmail_ids = [i["gmail_id"] for i in insights]
            assert "msg_rel_high" in gmail_ids
            assert "msg_rel_low" not in gmail_ids
        finally:
            os.environ.pop("JIMBO_API_URL", None)
            os.environ.pop("JIMBO_API_KEY", None)

    def test_empty_results_handled_gracefully(self, jimbo_server, clear_data):
        """When no reports match (empty DB or all below threshold),
        fetch_email_insights should return an empty list and ok status.

        If it throws an exception, the entire briefing pipeline crashes.
        """
        os.environ["JIMBO_API_URL"] = jimbo_server["url"]
        os.environ["JIMBO_API_KEY"] = jimbo_server["api_key"]
        try:
            import importlib
            bp = importlib.import_module("briefing-prep")
            importlib.reload(bp)
            insights, status = bp.fetch_email_insights(hours=24, min_relevance=5)

            assert insights == []
            assert status["status"] == "ok"
            assert status["count"] == 0
        finally:
            os.environ.pop("JIMBO_API_URL", None)
            os.environ.pop("JIMBO_API_KEY", None)

    def test_all_output_fields_present(self, jimbo_server, clear_data):
        """Every insight should include all fields the Opus prompt expects.

        If a field is missing, the Opus prompt template will show 'None'
        or crash when trying to access it.
        """
        client = ApiClient(jimbo_server["url"], jimbo_server["api_key"])

        client.post("/api/emails/reports", build_full_report(gmail_id="msg_fields_001"))
        client.patch("/api/emails/reports/msg_fields_001/decide", build_decision(relevance_score=7))

        os.environ["JIMBO_API_URL"] = jimbo_server["url"]
        os.environ["JIMBO_API_KEY"] = jimbo_server["api_key"]
        try:
            import importlib
            bp = importlib.import_module("briefing-prep")
            importlib.reload(bp)
            insights, _ = bp.fetch_email_insights(hours=24, min_relevance=1)

            assert len(insights) >= 1
            insight = insights[0]

            # Every field the Opus prompt template expects
            expected_fields = [
                "gmail_id", "subject", "from_email", "relevance_score",
                "category", "suggested_action", "reason", "insight",
                "connections", "time_sensitive", "deadline",
            ]
            for field in expected_fields:
                assert field in insight, f"Missing field: {field}"
        finally:
            os.environ.pop("JIMBO_API_URL", None)
            os.environ.pop("JIMBO_API_KEY", None)

    def test_no_api_credentials_returns_skipped(self, jimbo_server, clear_data):
        """When JIMBO_API_URL or JIMBO_API_KEY is missing, fetch_email_insights
        should return empty list with status 'skipped' — not crash.

        This happens on dev machines where env vars aren't set.
        """
        # Ensure env vars are NOT set
        os.environ.pop("JIMBO_API_URL", None)
        os.environ.pop("JIMBO_API_KEY", None)

        import importlib
        bp = importlib.import_module("briefing-prep")
        importlib.reload(bp)
        insights, status = bp.fetch_email_insights()

        assert insights == []
        assert status["status"] == "skipped"
```

- [ ] **Step 6: Run all briefing integration tests**

Run: `cd /Users/marvinbarretto/development/openclaw && python -m pytest workspace/tests/integration/test_briefing_integration.py -v`
Expected: All tests PASS (including the bug-fix test)

- [ ] **Step 7: Commit the bug fix and tests together**

```bash
git add workspace/briefing-prep.py workspace/tests/integration/test_briefing_integration.py
git commit -m "fix: fetch_email_insights reads decision fields from nested object

Decision fields (category, suggested_action, reason, etc.) are nested
under r['decision'] in jimbo-api responses, not top-level. This was
causing all decision fields except relevance_score to be None in the
briefing pipeline."
```

---

## Chunk 5: Cleanup

### Task 8: Remove Smoke Test and Final Verification

**Files:**
- Delete: `workspace/tests/integration/test_smoke.py` (was only for fixture validation)

- [ ] **Step 1: Remove the smoke test**

Delete `workspace/tests/integration/test_smoke.py` — its purpose was to validate the fixture during Task 1. The real tests in subsequent tasks cover health check verification implicitly (every test uses the fixture).

```bash
rm workspace/tests/integration/test_smoke.py
```

- [ ] **Step 2: Run the full integration test suite**

Run: `cd /Users/marvinbarretto/development/openclaw && python -m pytest workspace/tests/integration/ -v`
Expected: All tests PASS

- [ ] **Step 3: Run existing unit tests to verify no regressions**

Run: `cd /Users/marvinbarretto/development/openclaw && python -m pytest workspace/tests/ -v --ignore=workspace/tests/integration/`
Expected: All 23 existing unit tests PASS

- [ ] **Step 4: Commit cleanup**

```bash
git rm workspace/tests/integration/test_smoke.py
git commit -m "chore: remove integration smoke test — covered by real tests"
```
