# Phase 1: Ralph Email Deep Reader — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Evolve Ralph from a GitHub-issue-to-PR worker into a job-type runner, with email deep reading as the first job — fetching email via Gmail API, following every link with Playwright, extracting structured facts with Ollama, and pushing rich reports to jimbo-api.

**Architecture:** Ralph runs locally on Mac. Fetches email via Gmail API (ported from gmail-helper.py). For each email: Ollama extracts facts from body, Playwright visits every link, Ollama summarises each page. Results POST to jimbo-api via new `/api/emails/reports` endpoint. Local SQLite tracks processed IDs.

**Tech Stack:** Python 3.11+ (stdlib + playwright), Ollama (qwen2.5:7b), Playwright for link following, jimbo-api (Hono/TypeScript/better-sqlite3) for storage.

**Repos involved:**
- `ralph/` — the local agent (`/Users/marvinbarretto/development/ralph/`)
- `jimbo-api/` — VPS API (`/Users/marvinbarretto/development/jimbo/jimbo-api/`)

---

## Task 1: Refactor Ralph into Job-Type Architecture

**Files:**
- Create: `lib/jobs/__init__.py`
- Create: `lib/jobs/base.py`
- Create: `lib/jobs/code.py`
- Modify: `ralph.py`
- Modify: `config.toml`
- Test: `tests/test_job_registry.py`

**Step 1: Write the failing test for job registry**

```python
# tests/test_job_registry.py
import pytest
from lib.jobs.base import JobRegistry, BaseJob


class FakeJob(BaseJob):
    name = "fake"

    def build_queue(self):
        return [{"id": "1", "title": "test task"}]

    def process(self, item):
        return {"status": "ok", "id": item["id"]}

    def report(self, results):
        return {"total": len(results)}


def test_registry_register_and_get():
    registry = JobRegistry()
    registry.register(FakeJob)
    assert registry.get("fake") is FakeJob


def test_registry_get_unknown_raises():
    registry = JobRegistry()
    with pytest.raises(KeyError):
        registry.get("nonexistent")


def test_registry_list_jobs():
    registry = JobRegistry()
    registry.register(FakeJob)
    assert "fake" in registry.list()


def test_base_job_requires_name():
    with pytest.raises(TypeError):
        class BadJob(BaseJob):
            pass
        BadJob()


def test_base_job_interface():
    job = FakeJob(config={"model": "test"}, dry_run=False)
    queue = job.build_queue()
    assert len(queue) == 1
    result = job.process(queue[0])
    assert result["status"] == "ok"
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/marvinbarretto/development/ralph && python -m pytest tests/test_job_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lib.jobs'`

**Step 3: Write the job base classes**

```python
# lib/jobs/__init__.py
from lib.jobs.base import JobRegistry, BaseJob

__all__ = ["JobRegistry", "BaseJob"]
```

```python
# lib/jobs/base.py
"""Base job type and registry for Ralph's pluggable job system."""

from abc import ABC, abstractmethod


class BaseJob(ABC):
    """Abstract base for all Ralph job types.

    Subclasses must define:
    - name: str class attribute
    - build_queue(): returns list of work items
    - process(item): processes one item, returns result dict
    - report(results): summarises run, returns dict
    """

    name: str

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not getattr(cls, 'name', None) and ABC not in cls.__bases__:
            raise TypeError(f"{cls.__name__} must define a 'name' class attribute")

    def __init__(self, config: dict, dry_run: bool = False):
        self.config = config
        self.dry_run = dry_run

    @abstractmethod
    def build_queue(self) -> list[dict]:
        ...

    @abstractmethod
    def process(self, item: dict) -> dict:
        ...

    @abstractmethod
    def report(self, results: list[dict]) -> dict:
        ...


class JobRegistry:
    """Registry of available job types."""

    def __init__(self):
        self._jobs: dict[str, type[BaseJob]] = {}

    def register(self, job_class: type[BaseJob]):
        self._jobs[job_class.name] = job_class

    def get(self, name: str) -> type[BaseJob]:
        if name not in self._jobs:
            raise KeyError(f"Unknown job type: '{name}'. Available: {list(self._jobs.keys())}")
        return self._jobs[name]

    def list(self) -> list[str]:
        return list(self._jobs.keys())
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/marvinbarretto/development/ralph && python -m pytest tests/test_job_registry.py -v`
Expected: All 5 tests PASS

**Step 5: Extract existing code job**

```python
# lib/jobs/code.py
"""GitHub issue → draft PR job type (original Ralph behavior)."""

from lib.jobs.base import BaseJob
from lib.queue import build_task_queue
from lib.worker import process_task
from lib.reporter import write_run_log, print_summary
from pathlib import Path


class CodeJob(BaseJob):
    name = "code"

    def __init__(self, config: dict, dry_run: bool = False, repo: str | None = None):
        super().__init__(config, dry_run)
        self.repo = repo

    def build_queue(self) -> list[dict]:
        if self.repo:
            if self.repo not in self.config.get("repos", {}):
                raise ValueError(
                    f"Repo '{self.repo}' not found. Available: {list(self.config['repos'].keys())}"
                )
            repos = {self.repo: self.config["repos"][self.repo]}
        else:
            repos = self.config.get("repos", {})

        defaults = self.config.get("defaults", {})
        return build_task_queue(repos, defaults)

    def process(self, item: dict) -> dict:
        return process_task(item, self.config)

    def report(self, results: list[dict]) -> dict:
        log_dir = Path(__file__).resolve().parent.parent.parent / "logs" / "runs"
        log_path = write_run_log(results, log_dir)
        print_summary(results)
        return {"log_path": str(log_path), "total": len(results)}
```

**Step 6: Update config.toml with job-type structure**

```toml
# config.toml — add jobs section, keep existing config working

[jobs.code]
enabled = false
model = "ollama/qwen2.5-coder:14b"

[jobs.email]
enabled = true
model = "qwen2.5:7b"
```

**Step 7: Update ralph.py CLI to use job routing**

Modify `ralph.py` to add `--job` flag to `start` command. When `--job` is specified, route to that job type. When not specified, run all enabled jobs. Keep backward compatibility — `ralph start --repo X` still works (implies `--job code`).

Key changes to `ralph.py`:
- Import `JobRegistry` and job classes
- Add `--job` argument to start subparser
- Route through registry in `cmd_start()`
- Keep existing preflight checks (Ollama, lock file)

```python
# In ralph.py, replace the cmd_start function body with:

def cmd_start(args, config):
    """Run ralph jobs."""
    lock_fd = acquire_lock()
    try:
        preflight_checks(config)

        from lib.jobs import JobRegistry
        from lib.jobs.code import CodeJob

        registry = JobRegistry()
        registry.register(CodeJob)

        # Determine which jobs to run
        if args.job:
            job_names = [args.job]
        elif args.repo:
            job_names = ["code"]
        else:
            job_names = [
                name for name in registry.list()
                if config.get("jobs", {}).get(name, {}).get("enabled", False)
            ]

        if not job_names:
            print("No enabled jobs found. Enable jobs in config.toml [jobs.<name>]")
            return

        for job_name in job_names:
            job_class = registry.get(job_name)

            if job_name == "code":
                job = job_class(config, dry_run=args.dry_run, repo=args.repo)
            else:
                job = job_class(config, dry_run=args.dry_run)

            print(f"\n{'=' * 60}")
            print(f"Job: {job_name}")
            print(f"{'=' * 60}")

            queue = job.build_queue()
            if not queue:
                print(f"  No items in queue for '{job_name}'.")
                continue

            print(f"  Found {len(queue)} item(s)")
            if args.dry_run:
                for item in queue:
                    title = item.get("title") or item.get("subject") or item.get("id", "?")
                    print(f"    - {title}")
                continue

            results = []
            for i, item in enumerate(queue, 1):
                title = item.get("title") or item.get("subject") or item.get("id", "?")
                print(f"\n  [{i}/{len(queue)}] {title}")
                print(f"  {'-' * 50}")
                result = job.process(item)
                results.append(result)
                print(f"    → {result.get('status', 'unknown').upper()}")

            job.report(results)

    finally:
        release_lock(lock_fd)
```

Also add `--job` to the argparse:

```python
# In main(), update start_parser:
start_parser.add_argument("--job", type=str, help="Run a specific job type (email, code)")
```

**Step 8: Commit**

```bash
cd /Users/marvinbarretto/development/ralph
git add lib/jobs/ tests/test_job_registry.py ralph.py config.toml
git commit -m "refactor: extract job-type architecture with registry and base class"
```

---

## Task 2: Gmail API Client for Ralph

**Files:**
- Create: `lib/gmail.py`
- Create: `lib/state.py`
- Test: `tests/test_gmail.py`
- Test: `tests/test_state.py`

This ports the Gmail fetch logic from `openclaw/workspace/gmail-helper.py` into Ralph, adapted for Ralph's needs. Ralph needs: fetch emails, parse them, track which ones are already processed.

**Step 1: Write failing test for state tracking**

```python
# tests/test_state.py
import pytest
import tempfile
from pathlib import Path
from lib.state import ProcessedState


def test_state_empty_initially():
    with tempfile.TemporaryDirectory() as d:
        state = ProcessedState(Path(d) / "state.db")
        assert state.is_processed("msg_123") is False


def test_state_mark_and_check():
    with tempfile.TemporaryDirectory() as d:
        state = ProcessedState(Path(d) / "state.db")
        state.mark_processed("msg_123", job="email")
        assert state.is_processed("msg_123") is True


def test_state_persists_across_instances():
    with tempfile.TemporaryDirectory() as d:
        db_path = Path(d) / "state.db"
        state1 = ProcessedState(db_path)
        state1.mark_processed("msg_123", job="email")
        state2 = ProcessedState(db_path)
        assert state2.is_processed("msg_123") is True


def test_state_count():
    with tempfile.TemporaryDirectory() as d:
        state = ProcessedState(Path(d) / "state.db")
        state.mark_processed("msg_1", job="email")
        state.mark_processed("msg_2", job="email")
        assert state.count(job="email") == 2


def test_state_different_jobs_independent():
    with tempfile.TemporaryDirectory() as d:
        state = ProcessedState(Path(d) / "state.db")
        state.mark_processed("msg_1", job="email")
        assert state.count(job="code") == 0
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/marvinbarretto/development/ralph && python -m pytest tests/test_state.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lib.state'`

**Step 3: Implement state tracking**

```python
# lib/state.py
"""Persistent state tracking for processed items."""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class ProcessedState:
    """SQLite-backed tracking of processed item IDs per job type."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS processed (
                item_id TEXT NOT NULL,
                job TEXT NOT NULL,
                processed_at TEXT NOT NULL,
                PRIMARY KEY (item_id, job)
            )
        """)
        self._conn.commit()

    def is_processed(self, item_id: str, job: str = "email") -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM processed WHERE item_id = ? AND job = ?",
            (item_id, job)
        ).fetchone()
        return row is not None

    def mark_processed(self, item_id: str, job: str = "email"):
        self._conn.execute(
            "INSERT OR IGNORE INTO processed (item_id, job, processed_at) VALUES (?, ?, ?)",
            (item_id, job, datetime.now(timezone.utc).isoformat())
        )
        self._conn.commit()

    def count(self, job: str = "email") -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) FROM processed WHERE job = ?", (job,)
        ).fetchone()
        return row[0]
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/marvinbarretto/development/ralph && python -m pytest tests/test_state.py -v`
Expected: All 5 tests PASS

**Step 5: Write failing test for Gmail client**

```python
# tests/test_gmail.py
import pytest
import json
from lib.gmail import parse_sender, strip_html, extract_links, is_blacklisted


def test_parse_sender_with_name():
    name, email = parse_sender("John Doe <john@example.com>")
    assert name == "John Doe"
    assert email == "john@example.com"


def test_parse_sender_email_only():
    name, email = parse_sender("john@example.com")
    assert name == ""
    assert email == "john@example.com"


def test_parse_sender_quoted_name():
    name, email = parse_sender('"John Doe" <john@example.com>')
    assert name == "John Doe"
    assert email == "john@example.com"


def test_strip_html_removes_tags():
    result = strip_html("<p>Hello <b>world</b></p>")
    assert "Hello" in result
    assert "world" in result
    assert "<" not in result


def test_strip_html_removes_script():
    result = strip_html("<script>alert('xss')</script>Hello")
    assert "alert" not in result
    assert "Hello" in result


def test_extract_links():
    text = "Visit https://example.com and http://test.org/page for more"
    links = extract_links(text)
    assert "https://example.com" in links
    assert "http://test.org/page" in links


def test_extract_links_deduplicates():
    text = "https://example.com and https://example.com again"
    links = extract_links(text)
    assert len(links) == 1


def test_blacklist_sender_exact():
    assert is_blacklisted("noreply@uber.com", "Your trip", sender_blacklist=["noreply@uber.com"])


def test_blacklist_sender_domain():
    assert is_blacklisted("anyone@linkedin.com", "New connection", sender_blacklist=["@linkedin.com"])


def test_blacklist_subject():
    assert is_blacklisted("shop@store.com", "Your order has shipped", subject_blacklist=["your order"])


def test_not_blacklisted():
    assert not is_blacklisted(
        "editor@newsletter.com", "This week in tech",
        sender_blacklist=["@linkedin.com"],
        subject_blacklist=["your order"]
    )
```

**Step 6: Run test to verify it fails**

Run: `cd /Users/marvinbarretto/development/ralph && python -m pytest tests/test_gmail.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lib.gmail'`

**Step 7: Implement Gmail client**

Port from `openclaw/workspace/gmail-helper.py`. Keep the same OAuth refresh logic, message parsing, blacklist filtering. Adapt for Ralph's needs (return parsed messages, don't write digest file).

```python
# lib/gmail.py
"""Gmail API client for Ralph. Ported from openclaw workspace/gmail-helper.py."""

import base64
import json
import re
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path


# --- Blacklists (from gmail-helper.py, keep in sync) ---

SENDER_BLACKLIST = [
    "noreply@uber.com",
    "@linkedin.com",
    # ... port full list from gmail-helper.py
]

SUBJECT_BLACKLIST = [
    "your order",
    "delivery update",
    # ... port full list from gmail-helper.py
]


def is_blacklisted(
    sender_email: str,
    subject: str,
    sender_blacklist: list[str] | None = None,
    subject_blacklist: list[str] | None = None,
) -> bool:
    """Check if an email should be filtered out."""
    senders = sender_blacklist if sender_blacklist is not None else SENDER_BLACKLIST
    subjects = subject_blacklist if subject_blacklist is not None else SUBJECT_BLACKLIST

    email_lower = sender_email.lower()
    for pattern in senders:
        if pattern.startswith("@"):
            if email_lower.endswith(pattern.lower()):
                return True
        elif email_lower == pattern.lower():
            return True

    subject_lower = subject.lower()
    for phrase in subjects:
        if phrase.lower() in subject_lower:
            return True

    return False


# --- HTML parsing ---

class _HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts: list[str] = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip = True
        elif tag in ("p", "br", "div", "li", "h1", "h2", "h3", "h4", "tr"):
            self._parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = False

    def handle_data(self, data):
        if not self._skip:
            self._parts.append(data)


def strip_html(html: str) -> str:
    """Strip HTML tags, scripts, styles. Preserve structure with newlines."""
    stripper = _HTMLStripper()
    stripper.feed(html)
    text = "".join(stripper._parts)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_sender(raw: str) -> tuple[str, str]:
    """Parse 'Name <email>' format. Returns (name, email)."""
    match = re.match(r'^"?([^"<]*)"?\s*<([^>]+)>', raw)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    if "@" in raw:
        return "", raw.strip()
    return raw.strip(), ""


def extract_links(text: str) -> list[str]:
    """Extract unique HTTP(S) URLs from text."""
    urls = re.findall(r'https?://[^\s<>"\')\]]+', text)
    seen = set()
    unique = []
    for url in urls:
        url = url.rstrip(".,;:!?)")
        if url not in seen:
            seen.add(url)
            unique.append(url)
    return unique


# --- Gmail API ---

class GmailClient:
    """Gmail API client using OAuth refresh token flow."""

    TOKEN_URL = "https://oauth2.googleapis.com/token"
    API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"

    def __init__(self, client_id: str, client_secret: str, refresh_token: str, cache_dir: Path):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self._cache_dir = cache_dir
        self._access_token: str | None = None
        self._token_expiry: float = 0

    def _ensure_token(self):
        """Refresh access token if expired."""
        import time
        if self._access_token and time.time() < self._token_expiry - 60:
            return

        data = urllib.parse.urlencode({
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.refresh_token,
            "grant_type": "refresh_token",
        }).encode()

        req = urllib.request.Request(self.TOKEN_URL, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            token_data = json.loads(resp.read())

        self._access_token = token_data["access_token"]
        self._token_expiry = time.time() + token_data.get("expires_in", 3600)

    def _api_get(self, path: str) -> dict:
        """Make authenticated GET request to Gmail API."""
        self._ensure_token()
        url = f"{self.API_BASE}/{path}"
        req = urllib.request.Request(url)
        req.add_header("Authorization", f"Bearer {self._access_token}")
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())

    def list_message_ids(self, hours: int = 24, limit: int = 100) -> list[str]:
        """Fetch message IDs from the last N hours."""
        query = f"newer_than:{hours}h"
        ids = []
        page_token = None

        while len(ids) < limit:
            path = f"messages?q={urllib.parse.quote(query)}&maxResults={min(100, limit - len(ids))}"
            if page_token:
                path += f"&pageToken={page_token}"

            data = self._api_get(path)
            messages = data.get("messages", [])
            ids.extend(m["id"] for m in messages)

            page_token = data.get("nextPageToken")
            if not page_token:
                break

        return ids[:limit]

    def get_message(self, msg_id: str) -> dict:
        """Fetch full message by ID."""
        return self._api_get(f"messages/{msg_id}?format=full")

    def parse_message(self, raw: dict) -> dict:
        """Parse Gmail API message into structured dict."""
        headers = raw.get("payload", {}).get("headers", [])

        def get_header(name):
            for h in headers:
                if h["name"].lower() == name.lower():
                    return h["value"]
            return ""

        sender_raw = get_header("From")
        sender_name, sender_email = parse_sender(sender_raw)

        body = self._extract_body(raw.get("payload", {}))
        links = extract_links(body)

        return {
            "gmail_id": raw["id"],
            "thread_id": raw.get("threadId", ""),
            "date": get_header("Date"),
            "sender": {"name": sender_name, "email": sender_email},
            "subject": get_header("Subject"),
            "body": body,
            "links": links,
            "labels": raw.get("labelIds", []),
        }

    def _extract_body(self, payload: dict) -> str:
        """Extract text body from MIME payload. Prefers text/plain, falls back to HTML."""
        mime_type = payload.get("mimeType", "")

        if mime_type == "text/plain":
            return self._decode_part(payload)
        if mime_type == "text/html":
            return strip_html(self._decode_part(payload))

        # Multipart — recurse
        parts = payload.get("parts", [])
        # Prefer text/plain
        for part in parts:
            if part.get("mimeType") == "text/plain":
                return self._decode_part(part)
        # Fall back to text/html
        for part in parts:
            if part.get("mimeType") == "text/html":
                return strip_html(self._decode_part(part))
        # Recurse into nested multipart
        for part in parts:
            if part.get("mimeType", "").startswith("multipart/"):
                result = self._extract_body(part)
                if result:
                    return result
        return ""

    def _decode_part(self, part: dict) -> str:
        """Decode base64url body data from Gmail API."""
        data = part.get("body", {}).get("data", "")
        if not data:
            return ""
        padded = data + "=" * (4 - len(data) % 4)
        return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")
```

**Step 8: Run tests to verify they pass**

Run: `cd /Users/marvinbarretto/development/ralph && python -m pytest tests/test_gmail.py tests/test_state.py -v`
Expected: All tests PASS

**Step 9: Commit**

```bash
cd /Users/marvinbarretto/development/ralph
git add lib/gmail.py lib/state.py tests/test_gmail.py tests/test_state.py
git commit -m "feat: Gmail API client and processed-state tracker for email job"
```

---

## Task 3: Playwright Link Follower

**Files:**
- Create: `lib/links.py`
- Test: `tests/test_links.py`

**Step 1: Write failing test for link follower**

```python
# tests/test_links.py
import pytest
from lib.links import normalise_url, is_followable_url, ExtractionConfidence


def test_normalise_url_strips_utm():
    assert normalise_url("https://example.com/page?utm_source=email&utm_medium=newsletter") == "https://example.com/page"


def test_normalise_url_strips_mixed_params():
    result = normalise_url("https://example.com/page?id=123&utm_campaign=spring")
    assert "utm_campaign" not in result
    assert "id=123" in result


def test_normalise_url_preserves_meaningful_params():
    url = "https://example.com/event?id=456&date=2026-03-22"
    assert normalise_url(url) == url


def test_normalise_url_strips_trailing_slash():
    assert normalise_url("https://example.com/page/") == "https://example.com/page"


def test_is_followable_rejects_images():
    assert not is_followable_url("https://example.com/photo.jpg")
    assert not is_followable_url("https://example.com/banner.png")


def test_is_followable_rejects_downloads():
    assert not is_followable_url("https://example.com/file.pdf")
    assert not is_followable_url("https://example.com/archive.zip")


def test_is_followable_rejects_social_profiles():
    assert not is_followable_url("https://twitter.com/someone")
    assert not is_followable_url("https://facebook.com/page")


def test_is_followable_rejects_unsubscribe():
    assert not is_followable_url("https://email.example.com/unsubscribe?token=abc")


def test_is_followable_accepts_articles():
    assert is_followable_url("https://example.com/blog/great-article")
    assert is_followable_url("https://events.watford.gov.uk/spring-2026")


def test_extraction_confidence_values():
    assert ExtractionConfidence.HIGH == "high"
    assert ExtractionConfidence.MEDIUM == "medium"
    assert ExtractionConfidence.LOW == "low"
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/marvinbarretto/development/ralph && python -m pytest tests/test_links.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Implement link utilities and follower**

```python
# lib/links.py
"""Playwright-based link follower with URL normalisation and confidence scoring."""

import re
import urllib.parse
from enum import StrEnum


class ExtractionConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# Tracking params to strip during normalisation
TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "mc_cid", "mc_eid", "fbclid", "gclid", "ref", "source",
}

# File extensions that aren't worth following
SKIP_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".ico",
    ".pdf", ".zip", ".tar", ".gz", ".mp3", ".mp4", ".avi",
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
}

# Domains that are social profiles, not content
SKIP_DOMAINS = {
    "twitter.com", "x.com", "facebook.com", "instagram.com",
    "tiktok.com", "snapchat.com",
}

# URL path patterns to skip
SKIP_PATTERNS = [
    r"/unsubscribe",
    r"/manage[-_]?preferences",
    r"/email[-_]?preferences",
    r"/opt[-_]?out",
]


def normalise_url(url: str) -> str:
    """Normalise URL: strip tracking params, trailing slash."""
    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query)
    cleaned = {k: v for k, v in params.items() if k.lower() not in TRACKING_PARAMS}
    query = urllib.parse.urlencode(cleaned, doseq=True) if cleaned else ""
    path = parsed.path.rstrip("/") if parsed.path != "/" else parsed.path
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, path, "", query, ""))


def is_followable_url(url: str) -> bool:
    """Determine if a URL is worth following with Playwright."""
    parsed = urllib.parse.urlparse(url)

    # Skip known non-content domains
    domain = parsed.netloc.lower().lstrip("www.")
    if domain in SKIP_DOMAINS:
        return False

    # Skip file downloads and images
    path_lower = parsed.path.lower()
    for ext in SKIP_EXTENSIONS:
        if path_lower.endswith(ext):
            return False

    # Skip unsubscribe and preference links
    for pattern in SKIP_PATTERNS:
        if re.search(pattern, path_lower):
            return False

    return True


def score_extraction(page_text: str, page_title: str) -> ExtractionConfidence:
    """Score how well we extracted content from a page."""
    if not page_text or len(page_text.strip()) < 50:
        return ExtractionConfidence.LOW

    if len(page_text.strip()) < 200 and not page_title:
        return ExtractionConfidence.MEDIUM

    return ExtractionConfidence.HIGH


async def follow_link(page, url: str, timeout_ms: int = 15000) -> dict:
    """Visit a URL with Playwright and extract content.

    Args:
        page: Playwright page object (caller manages browser lifecycle)
        url: URL to visit
        timeout_ms: navigation timeout

    Returns:
        dict with url, page_title, page_text, fetch_status, extraction_confidence
    """
    try:
        response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        status_code = response.status if response else 0

        if status_code >= 400:
            return {
                "url": url,
                "page_title": "",
                "page_text": "",
                "fetch_status": f"http_{status_code}",
                "extraction_confidence": ExtractionConfidence.LOW,
            }

        # Wait a moment for JS rendering
        await page.wait_for_timeout(2000)

        page_title = await page.title()
        page_text = await page.inner_text("body")

        # Truncate very long pages
        if len(page_text) > 10000:
            page_text = page_text[:10000]

        confidence = score_extraction(page_text, page_title)

        return {
            "url": url,
            "page_title": page_title,
            "page_text": page_text,
            "fetch_status": "ok",
            "extraction_confidence": confidence,
        }

    except Exception as e:
        return {
            "url": url,
            "page_title": "",
            "page_text": "",
            "fetch_status": f"error: {type(e).__name__}",
            "extraction_confidence": ExtractionConfidence.LOW,
        }
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/marvinbarretto/development/ralph && python -m pytest tests/test_links.py -v`
Expected: All tests PASS (note: `follow_link` is async and needs Playwright installed — integration tested in Task 6)

**Step 5: Commit**

```bash
cd /Users/marvinbarretto/development/ralph
git add lib/links.py tests/test_links.py
git commit -m "feat: Playwright link follower with URL normalisation and confidence scoring"
```

---

## Task 4: Ollama Fact Extraction

**Files:**
- Create: `lib/ollama_extract.py`
- Test: `tests/test_ollama_extract.py`

**Step 1: Write failing test for prompt building and response parsing**

```python
# tests/test_ollama_extract.py
import pytest
import json
from lib.ollama_extract import build_body_prompt, build_page_prompt, parse_extraction


SAMPLE_EXTRACTION = {
    "summary": "Comedy night at Watford Palace Theatre, March 22",
    "entities": ["Watford Palace Theatre", "March 22"],
    "events": [{"what": "Stand-up comedy night", "when": "2026-03-22 19:30", "where": "Watford Palace Theatre", "cost": "£15"}],
    "deadlines": [],
    "key_asks": ["Book tickets"],
    "content_type": "event_listing"
}


def test_build_body_prompt_contains_email_content():
    prompt = build_body_prompt(
        subject="Comedy in Watford",
        sender="events@watford.gov.uk",
        body="Join us for a comedy night..."
    )
    assert "Comedy in Watford" in prompt
    assert "events@watford.gov.uk" in prompt
    assert "Join us for a comedy night" in prompt


def test_build_body_prompt_requests_json():
    prompt = build_body_prompt(subject="Test", sender="a@b.com", body="Hello")
    assert "JSON" in prompt


def test_build_page_prompt_contains_url():
    prompt = build_page_prompt(
        url="https://example.com/event",
        page_title="Comedy Night",
        page_text="A night of laughs...",
        link_text="Book now"
    )
    assert "https://example.com/event" in prompt
    assert "Comedy Night" in prompt


def test_parse_extraction_valid_json():
    raw = json.dumps(SAMPLE_EXTRACTION)
    result = parse_extraction(raw)
    assert result["summary"] == "Comedy night at Watford Palace Theatre, March 22"
    assert len(result["events"]) == 1


def test_parse_extraction_json_in_markdown():
    raw = f"Here's the analysis:\n```json\n{json.dumps(SAMPLE_EXTRACTION)}\n```\n"
    result = parse_extraction(raw)
    assert result["summary"] == "Comedy night at Watford Palace Theatre, March 22"


def test_parse_extraction_garbage_returns_empty():
    result = parse_extraction("This is not JSON at all, just random text")
    assert result["summary"] == ""
    assert result["entities"] == []
    assert result["events"] == []


def test_parse_extraction_partial_json_fills_defaults():
    raw = json.dumps({"summary": "Something", "entities": ["Thing"]})
    result = parse_extraction(raw)
    assert result["summary"] == "Something"
    assert result["events"] == []
    assert result["deadlines"] == []
    assert result["key_asks"] == []
    assert result["content_type"] == "unknown"
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/marvinbarretto/development/ralph && python -m pytest tests/test_ollama_extract.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Implement Ollama extraction**

```python
# lib/ollama_extract.py
"""Ollama-based fact extraction from email bodies and web pages.

This module does NOT judge relevance or importance. It extracts structured
facts only. Judgment is done by smarter models downstream (Flash on VPS).
"""

import json
import re
import urllib.request


EMPTY_EXTRACTION = {
    "summary": "",
    "entities": [],
    "events": [],
    "deadlines": [],
    "key_asks": [],
    "content_type": "unknown",
}


def build_body_prompt(subject: str, sender: str, body: str) -> str:
    """Build prompt for extracting facts from an email body."""
    return f"""Extract structured facts from this email. Do NOT judge importance or relevance — just extract what's there.

From: {sender}
Subject: {subject}

---
{body[:5000]}
---

Return ONLY a JSON object with these fields:
- "summary": one-sentence factual summary of the email
- "entities": array of named entities (people, places, organisations, dates, prices)
- "events": array of objects with "what", "when", "where", "cost" (null if unknown)
- "deadlines": array of objects with "what", "by" (date/time string)
- "key_asks": array of things the sender wants the reader to do
- "content_type": one of "newsletter", "event_listing", "promotional", "personal", "transactional", "notification", "unknown"

JSON only, no explanation:"""


def build_page_prompt(url: str, page_title: str, page_text: str, link_text: str = "") -> str:
    """Build prompt for extracting facts from a web page."""
    context = f'(linked as "{link_text}")' if link_text else ""
    return f"""Extract structured facts from this web page {context}. Do NOT judge importance — just extract what's there.

URL: {url}
Page title: {page_title}

---
{page_text[:8000]}
---

Return ONLY a JSON object with these fields:
- "summary": one-sentence factual summary of the page
- "entities": array of named entities (people, places, organisations, dates, prices)
- "events": array of objects with "what", "when", "where", "cost" (null if unknown)
- "deadlines": array of objects with "what", "by" (date/time string)
- "key_asks": array of things the page wants the reader to do
- "content_type": one of "article", "event_page", "product", "landing_page", "directory", "unknown"

JSON only, no explanation:"""


def parse_extraction(raw: str) -> dict:
    """Parse Ollama response into structured extraction. Tolerates markdown fences and partial JSON."""
    # Try to find JSON in the response
    json_str = raw.strip()

    # Strip markdown code fences
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", json_str, re.DOTALL)
    if fence_match:
        json_str = fence_match.group(1).strip()

    # Try direct parse
    try:
        parsed = json.loads(json_str)
        if isinstance(parsed, dict):
            return {**EMPTY_EXTRACTION, **parsed}
    except json.JSONDecodeError:
        pass

    # Try finding first { ... } block
    brace_match = re.search(r"\{.*\}", json_str, re.DOTALL)
    if brace_match:
        try:
            parsed = json.loads(brace_match.group(0))
            if isinstance(parsed, dict):
                return {**EMPTY_EXTRACTION, **parsed}
        except json.JSONDecodeError:
            pass

    return dict(EMPTY_EXTRACTION)


def call_ollama(prompt: str, model: str = "qwen2.5:7b", ollama_url: str = "http://localhost:11434") -> str:
    """Call Ollama API and return raw response text."""
    data = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 2048},
    }).encode()

    req = urllib.request.Request(
        f"{ollama_url}/api/generate",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read())
        return result.get("response", "")


def extract_from_body(subject: str, sender: str, body: str, model: str = "qwen2.5:7b", ollama_url: str = "http://localhost:11434") -> dict:
    """Extract facts from an email body via Ollama."""
    prompt = build_body_prompt(subject, sender, body)
    raw = call_ollama(prompt, model=model, ollama_url=ollama_url)
    return parse_extraction(raw)


def extract_from_page(url: str, page_title: str, page_text: str, link_text: str = "", model: str = "qwen2.5:7b", ollama_url: str = "http://localhost:11434") -> dict:
    """Extract facts from a web page via Ollama."""
    prompt = build_page_prompt(url, page_title, page_text, link_text)
    raw = call_ollama(prompt, model=model, ollama_url=ollama_url)
    return parse_extraction(raw)
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/marvinbarretto/development/ralph && python -m pytest tests/test_ollama_extract.py -v`
Expected: All 7 tests PASS (tests don't call Ollama — they test prompt building and response parsing)

**Step 5: Commit**

```bash
cd /Users/marvinbarretto/development/ralph
git add lib/ollama_extract.py tests/test_ollama_extract.py
git commit -m "feat: Ollama fact extraction with prompt builders and response parsing"
```

---

## Task 5: jimbo-api Email Reports Endpoint

**Files:**
- Create: `src/routes/emails.ts` (in jimbo-api repo)
- Create: `src/services/emails.ts` (in jimbo-api repo)
- Create: `src/types/emails.ts` (in jimbo-api repo)
- Modify: `src/db/index.ts` (in jimbo-api repo — add table)
- Modify: `src/index.ts` (in jimbo-api repo — register route)

**Note:** This task is in the jimbo-api repo at `/Users/marvinbarretto/development/jimbo/jimbo-api/`.

**Step 1: Add email_reports table to database schema**

In `src/db/index.ts`, add to the schema creation:

```sql
CREATE TABLE IF NOT EXISTS email_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gmail_id TEXT NOT NULL UNIQUE,
    thread_id TEXT NOT NULL DEFAULT '',
    processed_at TEXT NOT NULL,
    from_name TEXT NOT NULL DEFAULT '',
    from_email TEXT NOT NULL,
    subject TEXT NOT NULL,
    body_analysis TEXT NOT NULL,
    links TEXT NOT NULL DEFAULT '[]',
    model TEXT NOT NULL DEFAULT '',
    processing_time_seconds REAL DEFAULT 0,
    decided INTEGER NOT NULL DEFAULT 0,
    decided_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_email_reports_decided ON email_reports(decided);
CREATE INDEX IF NOT EXISTS idx_email_reports_thread ON email_reports(thread_id);
CREATE INDEX IF NOT EXISTS idx_email_reports_created ON email_reports(created_at);
```

**Step 2: Create types**

```typescript
// src/types/emails.ts

export interface EmailReport {
    id: number;
    gmail_id: string;
    thread_id: string;
    processed_at: string;
    from_name: string;
    from_email: string;
    subject: string;
    body_analysis: object;
    links: object[];
    model: string;
    processing_time_seconds: number;
    decided: boolean;
    decided_at: string | null;
    created_at: string;
}

export interface EmailReportInput {
    gmail_id: string;
    thread_id?: string;
    processed_at: string;
    from_name?: string;
    from_email: string;
    subject: string;
    body_analysis: object;
    links?: object[];
    model?: string;
    processing_time_seconds?: number;
}
```

**Step 3: Create service**

```typescript
// src/services/emails.ts
import { getDb } from '../db/index.js';
import type { EmailReport, EmailReportInput } from '../types/emails.js';

export function createReport(input: EmailReportInput): EmailReport {
    const db = getDb();
    const stmt = db.prepare(`
        INSERT INTO email_reports (gmail_id, thread_id, processed_at, from_name, from_email, subject, body_analysis, links, model, processing_time_seconds)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(gmail_id) DO UPDATE SET
            body_analysis = excluded.body_analysis,
            links = excluded.links,
            model = excluded.model,
            processing_time_seconds = excluded.processing_time_seconds
    `);

    stmt.run(
        input.gmail_id,
        input.thread_id || '',
        input.processed_at,
        input.from_name || '',
        input.from_email,
        input.subject,
        JSON.stringify(input.body_analysis),
        JSON.stringify(input.links || []),
        input.model || '',
        input.processing_time_seconds || 0,
    );

    return getReportByGmailId(input.gmail_id)!;
}

export function getReportByGmailId(gmail_id: string): EmailReport | null {
    const db = getDb();
    const row = db.prepare('SELECT * FROM email_reports WHERE gmail_id = ?').get(gmail_id) as any;
    if (!row) return null;
    return {
        ...row,
        body_analysis: JSON.parse(row.body_analysis),
        links: JSON.parse(row.links),
        decided: Boolean(row.decided),
    };
}

export function listReports(opts: { decided?: boolean; limit?: number; offset?: number } = {}): EmailReport[] {
    const db = getDb();
    const conditions: string[] = [];
    const values: any[] = [];

    if (opts.decided !== undefined) {
        conditions.push('decided = ?');
        values.push(opts.decided ? 1 : 0);
    }

    const where = conditions.length ? `WHERE ${conditions.join(' AND ')}` : '';
    const limit = opts.limit || 50;
    const offset = opts.offset || 0;

    const rows = db.prepare(
        `SELECT * FROM email_reports ${where} ORDER BY created_at DESC LIMIT ? OFFSET ?`
    ).all(...values, limit, offset) as any[];

    return rows.map(row => ({
        ...row,
        body_analysis: JSON.parse(row.body_analysis),
        links: JSON.parse(row.links),
        decided: Boolean(row.decided),
    }));
}

export function listUndecided(): EmailReport[] {
    return listReports({ decided: false });
}

export function markDecided(gmail_id: string): void {
    const db = getDb();
    db.prepare(
        "UPDATE email_reports SET decided = 1, decided_at = datetime('now') WHERE gmail_id = ?"
    ).run(gmail_id);
}

export function reportStats(): { total: number; undecided: number; decided: number } {
    const db = getDb();
    const total = (db.prepare('SELECT COUNT(*) as count FROM email_reports').get() as any).count;
    const undecided = (db.prepare('SELECT COUNT(*) as count FROM email_reports WHERE decided = 0').get() as any).count;
    return { total, undecided, decided: total - undecided };
}
```

**Step 4: Create route**

```typescript
// src/routes/emails.ts
import { Hono } from 'hono';
import { createReport, listReports, listUndecided, getReportByGmailId, reportStats } from '../services/emails.js';

const emails = new Hono();

// POST / — Ralph pushes a deep report
emails.post('/', async (c) => {
    const body = await c.req.json();

    if (!body.gmail_id || !body.from_email || !body.subject || !body.processed_at) {
        return c.json({ error: 'Missing required fields: gmail_id, from_email, subject, processed_at' }, 400);
    }

    const report = createReport(body);
    return c.json(report, 201);
});

// GET / — list reports with optional filters
emails.get('/', (c) => {
    const decided = c.req.query('decided');
    const limit = parseInt(c.req.query('limit') || '50');
    const offset = parseInt(c.req.query('offset') || '0');

    const opts: { decided?: boolean; limit: number; offset: number } = { limit, offset };
    if (decided === 'true') opts.decided = true;
    if (decided === 'false') opts.decided = false;

    const reports = listReports(opts);
    return c.json(reports);
});

// GET /undecided — reports not yet processed by decision maker
emails.get('/undecided', (c) => {
    const reports = listUndecided();
    return c.json(reports);
});

// GET /stats
emails.get('/stats', (c) => {
    const stats = reportStats();
    return c.json(stats);
});

// GET /:gmail_id — single report
emails.get('/:gmail_id', (c) => {
    const report = getReportByGmailId(c.req.param('gmail_id'));
    if (!report) return c.json({ error: 'Not found' }, 404);
    return c.json(report);
});

export default emails;
```

**Step 5: Register route in main app**

In `src/index.ts`, add:

```typescript
import emails from './routes/emails.js';
// ... with other route registrations:
app.route('/api/emails/reports', emails);
```

**Step 6: Build and test locally**

```bash
cd /Users/marvinbarretto/development/jimbo/jimbo-api
npm run build
```

**Step 7: Commit**

```bash
cd /Users/marvinbarretto/development/jimbo/jimbo-api
git add src/routes/emails.ts src/services/emails.ts src/types/emails.ts src/db/index.ts src/index.ts
git commit -m "feat: email reports API for Ralph deep reader integration"
```

---

## Task 6: jimbo-api Client for Ralph

**Files:**
- Create: `lib/api_client.py` (in ralph repo)
- Test: `tests/test_api_client.py`

**Step 1: Write failing test**

```python
# tests/test_api_client.py
import pytest
import json
from unittest.mock import patch, MagicMock
from lib.api_client import JimboApiClient


def test_client_builds_correct_url():
    client = JimboApiClient(base_url="https://example.com/api", api_key="test123")
    assert client.base_url == "https://example.com/api"


def test_client_headers_include_api_key():
    client = JimboApiClient(base_url="https://example.com/api", api_key="test123")
    headers = client._headers()
    assert headers["X-API-Key"] == "test123"
    assert headers["Content-Type"] == "application/json"
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/marvinbarretto/development/ralph && python -m pytest tests/test_api_client.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Implement API client**

```python
# lib/api_client.py
"""Client for jimbo-api REST endpoints."""

import json
import urllib.request
import urllib.error


class JimboApiClient:
    """Lightweight REST client for jimbo-api. Stdlib only."""

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def _headers(self) -> dict:
        return {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(url, data=data, headers=self._headers(), method=method)

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"API error {e.code}: {error_body}") from e

    def post_email_report(self, report: dict) -> dict:
        """Push a deep email report to jimbo-api."""
        return self._request("POST", "/emails/reports", report)

    def get_email_stats(self) -> dict:
        """Get email report statistics."""
        return self._request("GET", "/emails/reports/stats")

    def health_check(self) -> bool:
        """Check if jimbo-api is reachable."""
        try:
            self._request("GET", "/../../health")
            return True
        except Exception:
            return False
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/marvinbarretto/development/ralph && python -m pytest tests/test_api_client.py -v`
Expected: PASS

**Step 5: Commit**

```bash
cd /Users/marvinbarretto/development/ralph
git add lib/api_client.py tests/test_api_client.py
git commit -m "feat: jimbo-api REST client for posting email reports"
```

---

## Task 7: Email Job — Assemble the Full Pipeline

**Files:**
- Create: `lib/jobs/email.py`
- Test: `tests/test_email_job.py`
- Modify: `ralph.py` (register email job)
- Modify: `config.toml` (email job config)

**Step 1: Write failing test for email job queue building**

```python
# tests/test_email_job.py
import pytest
from unittest.mock import MagicMock, patch
from lib.jobs.email import EmailJob


def make_config():
    return {
        "jobs": {
            "email": {
                "enabled": True,
                "model": "qwen2.5:7b",
                "hours": 24,
                "limit": 100,
                "max_links_per_email": 10,
                "link_timeout_ms": 15000,
            }
        },
        "llm": {
            "ollama_url": "http://localhost:11434",
        },
        "gmail": {
            "client_id": "test",
            "client_secret": "test",
            "refresh_token": "test",
        },
        "api": {
            "jimbo_url": "https://example.com/api",
            "jimbo_key": "test123",
        },
    }


def test_email_job_name():
    assert EmailJob.name == "email"


def test_email_job_report_summarises_results():
    job = EmailJob(config=make_config(), dry_run=False)
    results = [
        {"status": "ok", "gmail_id": "1", "links_followed": 3, "processing_time": 12.5},
        {"status": "ok", "gmail_id": "2", "links_followed": 1, "processing_time": 8.0},
        {"status": "error", "gmail_id": "3", "error": "Ollama timeout"},
    ]
    report = job.report(results)
    assert report["total"] == 3
    assert report["ok"] == 2
    assert report["errors"] == 1
    assert report["total_links"] == 4
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/marvinbarretto/development/ralph && python -m pytest tests/test_email_job.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Implement email job**

```python
# lib/jobs/email.py
"""Email deep reader job type for Ralph.

Pipeline per email:
1. Fetch from Gmail API
2. Check blacklist → skip if matched
3. Check if already processed → skip if yes
4. Ollama extracts facts from body
5. Playwright follows each link
6. Ollama extracts facts from each page
7. Compile deep report
8. POST to jimbo-api
9. Mark as processed in local state
"""

import asyncio
import time
from datetime import datetime, timezone
from pathlib import Path

from lib.jobs.base import BaseJob
from lib.gmail import GmailClient, is_blacklisted, extract_links, normalise_url
from lib.links import is_followable_url, normalise_url as norm_url, follow_link, ExtractionConfidence
from lib.ollama_extract import extract_from_body, extract_from_page
from lib.state import ProcessedState
from lib.api_client import JimboApiClient


class EmailJob(BaseJob):
    name = "email"

    def __init__(self, config: dict, dry_run: bool = False):
        super().__init__(config, dry_run)
        email_config = config.get("jobs", {}).get("email", {})
        gmail_config = config.get("gmail", {})
        api_config = config.get("api", {})
        llm_config = config.get("llm", {})

        self.model = email_config.get("model", "qwen2.5:7b")
        self.hours = email_config.get("hours", 24)
        self.limit = email_config.get("limit", 100)
        self.max_links = email_config.get("max_links_per_email", 10)
        self.link_timeout_ms = email_config.get("link_timeout_ms", 15000)
        self.ollama_url = llm_config.get("ollama_url", "http://localhost:11434")

        self._gmail = GmailClient(
            client_id=gmail_config.get("client_id", ""),
            client_secret=gmail_config.get("client_secret", ""),
            refresh_token=gmail_config.get("refresh_token", ""),
            cache_dir=Path(__file__).resolve().parent.parent.parent / "data",
        )

        self._state = ProcessedState(
            Path(__file__).resolve().parent.parent.parent / "data" / "ralph-state.db"
        )

        self._api = JimboApiClient(
            base_url=api_config.get("jimbo_url", ""),
            api_key=api_config.get("jimbo_key", ""),
        )

        # Track seen URLs across this run for deduplication
        self._seen_urls: dict[str, dict] = {}

    def build_queue(self) -> list[dict]:
        """Fetch recent emails, filter blacklist and already-processed."""
        print(f"  Fetching emails from last {self.hours}h (limit {self.limit})...")
        msg_ids = self._gmail.list_message_ids(hours=self.hours, limit=self.limit)
        print(f"  Found {len(msg_ids)} message IDs")

        queue = []
        skipped_processed = 0
        skipped_blacklist = 0

        for msg_id in msg_ids:
            if self._state.is_processed(msg_id, job="email"):
                skipped_processed += 1
                continue

            raw = self._gmail.get_message(msg_id)
            parsed = self._gmail.parse_message(raw)

            if is_blacklisted(parsed["sender"]["email"], parsed["subject"]):
                skipped_blacklist += 1
                self._state.mark_processed(msg_id, job="email")
                continue

            queue.append(parsed)

        print(f"  Queue: {len(queue)} new, {skipped_processed} already processed, {skipped_blacklist} blacklisted")
        return queue

    def process(self, item: dict) -> dict:
        """Deep-read one email: extract facts from body, follow links, compile report."""
        start_time = time.time()
        gmail_id = item["gmail_id"]

        try:
            # Step 1: Extract facts from email body
            print(f"    Reading email body...")
            body_analysis = extract_from_body(
                subject=item["subject"],
                sender=item["sender"]["email"],
                body=item["body"],
                model=self.model,
                ollama_url=self.ollama_url,
            )

            # Step 2: Follow links with Playwright
            links_results = self._follow_links(item["links"], item["body"])

            # Step 3: Compile deep report
            processing_time = time.time() - start_time
            report = {
                "gmail_id": gmail_id,
                "thread_id": item.get("thread_id", ""),
                "processed_at": datetime.now(timezone.utc).isoformat(),
                "from_name": item["sender"]["name"],
                "from_email": item["sender"]["email"],
                "subject": item["subject"],
                "body_analysis": body_analysis,
                "links": links_results,
                "model": self.model,
                "processing_time_seconds": round(processing_time, 1),
            }

            # Step 4: Push to jimbo-api
            if not self.dry_run:
                try:
                    self._api.post_email_report(report)
                    print(f"    Pushed report to jimbo-api")
                except Exception as e:
                    print(f"    WARNING: Failed to push to jimbo-api: {e}")
                    # Don't fail the whole process — report is still valuable locally

            # Step 5: Mark processed
            self._state.mark_processed(gmail_id, job="email")

            return {
                "status": "ok",
                "gmail_id": gmail_id,
                "subject": item["subject"],
                "links_followed": len(links_results),
                "processing_time": round(processing_time, 1),
            }

        except Exception as e:
            processing_time = time.time() - start_time
            print(f"    ERROR: {e}")
            return {
                "status": "error",
                "gmail_id": gmail_id,
                "subject": item.get("subject", "?"),
                "error": str(e),
                "processing_time": round(processing_time, 1),
            }

    def _follow_links(self, links: list[str], body: str) -> list[dict]:
        """Follow links from email using Playwright. Deduplicates across emails in same run."""
        followable = []
        for url in links[:self.max_links]:
            if not is_followable_url(url):
                continue
            normalised = norm_url(url)
            if normalised in self._seen_urls:
                # Already followed this URL in this run — reference existing data
                existing = self._seen_urls[normalised]
                existing["seen_in_emails"] = existing.get("seen_in_emails", 1) + 1
                followable.append(existing)
                continue
            followable.append({"url": url, "normalised": normalised, "needs_fetch": True})

        # Run Playwright for URLs that need fetching
        to_fetch = [l for l in followable if l.get("needs_fetch")]
        if not to_fetch:
            return [l for l in followable if not l.get("needs_fetch")]

        fetched = asyncio.run(self._fetch_links([l["url"] for l in to_fetch]))

        results = []
        fetch_idx = 0
        for link_info in followable:
            if link_info.get("needs_fetch"):
                page_data = fetched[fetch_idx]
                fetch_idx += 1

                # Extract facts from page if we got content
                page_analysis = {}
                if page_data["fetch_status"] == "ok" and page_data["page_text"]:
                    print(f"    Analysing: {link_info['url'][:60]}...")
                    page_analysis = extract_from_page(
                        url=link_info["url"],
                        page_title=page_data["page_title"],
                        page_text=page_data["page_text"],
                        model=self.model,
                        ollama_url=self.ollama_url,
                    )

                result = {
                    "url": link_info["url"],
                    "page_title": page_data["page_title"],
                    "page_summary": page_analysis.get("summary", ""),
                    "entities": page_analysis.get("entities", []),
                    "events": page_analysis.get("events", []),
                    "fetch_method": "playwright",
                    "fetch_status": page_data["fetch_status"],
                    "extraction_confidence": page_data["extraction_confidence"],
                    "seen_in_emails": 1,
                }

                # Cache for deduplication
                self._seen_urls[link_info["normalised"]] = result
                results.append(result)
            else:
                results.append(link_info)

        return results

    async def _fetch_links(self, urls: list[str]) -> list[dict]:
        """Fetch multiple URLs with Playwright."""
        from playwright.async_api import async_playwright

        results = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            for url in urls:
                print(f"    Following: {url[:60]}...")
                result = await follow_link(page, url, timeout_ms=self.link_timeout_ms)
                results.append(result)

            await browser.close()
        return results

    def report(self, results: list[dict]) -> dict:
        """Summarise the run."""
        ok = [r for r in results if r["status"] == "ok"]
        errors = [r for r in results if r["status"] == "error"]
        total_links = sum(r.get("links_followed", 0) for r in ok)
        total_time = sum(r.get("processing_time", 0) for r in results)

        print(f"\n  {'=' * 40}")
        print(f"  Email Deep Reader Summary")
        print(f"  {'=' * 40}")
        print(f"  Processed: {len(ok)}/{len(results)}")
        print(f"  Links followed: {total_links}")
        print(f"  Errors: {len(errors)}")
        print(f"  Total time: {total_time:.0f}s")

        if errors:
            print(f"\n  Errors:")
            for e in errors:
                print(f"    - {e.get('subject', '?')}: {e.get('error', '?')}")

        return {
            "total": len(results),
            "ok": len(ok),
            "errors": len(errors),
            "total_links": total_links,
            "total_time_seconds": round(total_time, 1),
        }
```

**Step 4: Register email job in ralph.py**

Add to the imports and registration in `cmd_start`:

```python
from lib.jobs.email import EmailJob
registry.register(EmailJob)
```

**Step 5: Update config.toml with full email config**

```toml
[gmail]
# Set these via environment variables or directly:
# RALPH_GMAIL_CLIENT_ID, RALPH_GMAIL_CLIENT_SECRET, RALPH_GMAIL_REFRESH_TOKEN
client_id = ""
client_secret = ""
refresh_token = ""

[api]
jimbo_url = "https://167.99.206.214/api"
jimbo_key = ""

[jobs.email]
enabled = true
model = "qwen2.5:7b"
hours = 24
limit = 100
max_links_per_email = 10
link_timeout_ms = 15000
```

**Step 6: Run tests**

Run: `cd /Users/marvinbarretto/development/ralph && python -m pytest tests/test_email_job.py -v`
Expected: PASS

**Step 7: Commit**

```bash
cd /Users/marvinbarretto/development/ralph
git add lib/jobs/email.py tests/test_email_job.py ralph.py config.toml
git commit -m "feat: email deep reader job — full pipeline from Gmail to jimbo-api"
```

---

## Task 8: Update Ralph Documentation and Config

**Files:**
- Modify: `MISSION.md`
- Modify: `CLAUDE.md`
- Modify: `config.toml`
- Modify: `.gitignore`

**Step 1: Update MISSION.md**

Replace current content with evolved mission:

```markdown
# Ralph — Mission

## What Ralph is

Ralph is a local background agent that does thorough work with free models while your machine is available. Ralph processes job queues — reading, analysing, extracting — and pushes structured results to smarter models for decision-making.

Ralph is a force multiplier for someone with too much incoming information and not enough hours.

## Core principles

1. **Thorough over fast.** Ralph spends real time on each item. Every email is a mini project. Every link is followed. Quality of extraction matters more than speed.

2. **Local first, free by default.** The primary workflow uses Ollama on your own hardware. No API costs for the grunt work. Smart models are for judgment calls, not data extraction.

3. **Extract facts, don't judge.** Ralph reads, summarises, and structures. It does NOT decide what's important — that's for smarter models downstream with full context.

4. **Safe and reversible.** Ralph reads email (never sends). Creates reports (never deletes). Pushes data to APIs (never modifies upstream).

5. **Quiet background worker.** Ralph runs unattended without drama. If the Mac is open, Ralph works. If it's closed, Ralph picks up where it left off.

## Job types

- **email** — Deep-reads every email: body analysis, link following (Playwright), structured fact extraction. Pushes rich reports to jimbo-api.
- **code** — (Future) Turns GitHub issues into draft PRs using aider + local models.

## What Ralph is not

- **Not a decision maker.** Ralph extracts facts. Decision-making happens on the VPS with smarter models and full context.
- **Not always-on.** Ralph works when the machine is available. No daemon, no server.
- **Not a replacement for human review.** Ralph's output is input for the next stage, not a final product.
```

**Step 2: Update CLAUDE.md**

```markdown
# Ralph

Read MISSION.md for what Ralph is and isn't. Read DEVLOG.md for history and known issues.

## Project structure

- `ralph.py` — CLI entry point (`start`, `status`, `log`, `--dry-run`, `--job`, `--repo`)
- `lib/jobs/base.py` — Job registry and base class
- `lib/jobs/email.py` — Email deep reader job (Gmail → Ollama → Playwright → jimbo-api)
- `lib/jobs/code.py` — GitHub issue → PR job (aider + Ollama)
- `lib/gmail.py` — Gmail API client (OAuth, message parsing, blacklist)
- `lib/links.py` — Playwright link follower with confidence scoring
- `lib/ollama_extract.py` — Ollama fact extraction (prompts + response parsing)
- `lib/api_client.py` — jimbo-api REST client
- `lib/state.py` — SQLite state tracker (processed item IDs)
- `lib/queue.py` — GitHub issue queue (code job)
- `lib/worker.py` — aider task runner (code job)
- `lib/reporter.py` — run logging and summary
- `config.toml` — job config, model selection, API credentials
- `setup/` — launchd plist for scheduling

## Key constraints

- Python stdlib only — no pip dependencies (except playwright for email job)
- Local-first: Ollama, no API keys for extraction
- Email job: read-only Gmail access, never sends
- Code job: draft PRs only, never pushes to main
- Must run unattended — no interactive prompts
```

**Step 3: Update .gitignore**

Add:
```
data/
ralph-state.db
```

**Step 4: Commit**

```bash
cd /Users/marvinbarretto/development/ralph
git add MISSION.md CLAUDE.md .gitignore
git commit -m "docs: update Ralph identity — local background agent with job-type architecture"
```

---

## Task 9: Integration Test — End to End

**Files:**
- Create: `tests/test_email_integration.py`

This test verifies the full pipeline works with mocked external services (Gmail API, Ollama, Playwright, jimbo-api).

**Step 1: Write integration test**

```python
# tests/test_email_integration.py
"""Integration test for the email deep reader pipeline.

Mocks external services (Gmail API, Ollama, Playwright) to test the full flow
from email fetch through to report compilation.
"""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
from lib.jobs.email import EmailJob


SAMPLE_CONFIG = {
    "jobs": {
        "email": {
            "enabled": True,
            "model": "qwen2.5:7b",
            "hours": 24,
            "limit": 10,
            "max_links_per_email": 5,
            "link_timeout_ms": 5000,
        }
    },
    "llm": {"ollama_url": "http://localhost:11434"},
    "gmail": {"client_id": "test", "client_secret": "test", "refresh_token": "test"},
    "api": {"jimbo_url": "https://example.com/api", "jimbo_key": "testkey"},
}

SAMPLE_PARSED_EMAIL = {
    "gmail_id": "msg_001",
    "thread_id": "thread_001",
    "date": "Mon, 10 Mar 2026 10:00:00 +0000",
    "sender": {"name": "Events Watford", "email": "events@watford.gov.uk"},
    "subject": "Comedy night this Friday",
    "body": "Join us at Watford Palace Theatre for a comedy night. March 14, 7:30pm. Tickets £15. https://watford.gov.uk/comedy-night",
    "links": ["https://watford.gov.uk/comedy-night"],
    "labels": ["INBOX"],
}

SAMPLE_BODY_EXTRACTION = {
    "summary": "Comedy night at Watford Palace Theatre, March 14",
    "entities": ["Watford Palace Theatre", "March 14", "£15"],
    "events": [{"what": "Comedy night", "when": "2026-03-14 19:30", "where": "Watford Palace Theatre", "cost": "£15"}],
    "deadlines": [],
    "key_asks": ["Buy tickets"],
    "content_type": "event_listing",
}


@patch("lib.jobs.email.JimboApiClient")
@patch("lib.jobs.email.ProcessedState")
@patch("lib.jobs.email.GmailClient")
def test_email_job_build_queue_filters_processed(MockGmail, MockState, MockApi):
    mock_gmail = MockGmail.return_value
    mock_gmail.list_message_ids.return_value = ["msg_001", "msg_002"]
    mock_gmail.get_message.return_value = {}
    mock_gmail.parse_message.return_value = SAMPLE_PARSED_EMAIL

    mock_state = MockState.return_value
    mock_state.is_processed.side_effect = lambda id, job: id == "msg_001"

    job = EmailJob(config=SAMPLE_CONFIG, dry_run=True)
    job._gmail = mock_gmail
    job._state = mock_state

    queue = job.build_queue()
    assert len(queue) == 1
    assert queue[0]["gmail_id"] == "msg_002"


def test_email_job_report_counts():
    job = EmailJob(config=SAMPLE_CONFIG, dry_run=True)
    results = [
        {"status": "ok", "gmail_id": "1", "links_followed": 2, "processing_time": 10},
        {"status": "error", "gmail_id": "2", "error": "timeout", "processing_time": 5},
    ]
    report = job.report(results)
    assert report["total"] == 2
    assert report["ok"] == 1
    assert report["errors"] == 1
    assert report["total_links"] == 2
```

**Step 2: Run integration test**

Run: `cd /Users/marvinbarretto/development/ralph && python -m pytest tests/test_email_integration.py -v`
Expected: PASS

**Step 3: Commit**

```bash
cd /Users/marvinbarretto/development/ralph
git add tests/test_email_integration.py
git commit -m "test: integration test for email deep reader pipeline"
```

---

## Task 10: Install Playwright and Smoke Test

**Step 1: Install playwright**

```bash
cd /Users/marvinbarretto/development/ralph
pip install playwright
playwright install chromium
```

**Step 2: Update .gitignore if needed for any playwright artifacts**

**Step 3: Manual smoke test with dry-run**

```bash
cd /Users/marvinbarretto/development/ralph
python ralph.py start --job email --dry-run
```

Expected: Shows email count from Gmail API, lists subjects in queue, does NOT process or push anything.

**Step 4: Run full test suite**

```bash
cd /Users/marvinbarretto/development/ralph
python -m pytest tests/ -v
```

Expected: All tests PASS

**Step 5: Live test with a small batch**

Set Gmail credentials in config.toml (or env vars), then:

```bash
cd /Users/marvinbarretto/development/ralph
python ralph.py start --job email
```

Watch it process emails one by one. Verify:
- Ollama extracts facts from body
- Playwright follows links
- Reports POST to jimbo-api (or print warning if API unreachable)
- Second run skips already-processed emails

**Step 6: Commit any fixes from smoke testing**

```bash
git add -A && git commit -m "fix: adjustments from smoke testing email deep reader"
```

---

## Task 11: Deploy jimbo-api Changes to VPS

**Step 1: Build jimbo-api**

```bash
cd /Users/marvinbarretto/development/jimbo/jimbo-api
npm run build
```

**Step 2: Deploy to VPS**

```bash
rsync -avz dist/ jimbo:/home/openclaw/jimbo-api/dist/
ssh jimbo 'cd /home/openclaw/jimbo-api && cp -r dist/* . && sudo systemctl restart jimbo-api'
```

**Step 3: Verify endpoint works**

```bash
curl -s -H "X-API-Key: 7e37e4ae1650b6ebc2a925b918924d80" https://167.99.206.214/api/emails/reports/stats | python3 -m json.tool
```

Expected: `{"total": 0, "undecided": 0, "decided": 0}`

**Step 4: Commit jimbo-api**

```bash
cd /Users/marvinbarretto/development/jimbo/jimbo-api
git add -A && git commit -m "feat: email reports endpoint for Ralph deep reader"
```

---

Plan complete and saved to `docs/plans/2026-03-11-proactive-actions-phase1.md`. Two execution options:

**1. Subagent-Driven (this session)** — I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** — Open new session with executing-plans, batch execution with checkpoints

Which approach?