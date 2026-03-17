# Autonomous Mind Phase 1 — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build vault-reader, vault-connector, and vault-roulette, then update HEARTBEAT.md to use them in the background research rotation.

**Architecture:** Three workers in `/workspace/workers/` subclassing `BaseWorker`. Each has a task config in `/workspace/tasks/`, a test file in `/workspace/tests/`, and follows the existing email_triage.py/newsletter_reader.py patterns. HEARTBEAT.md gets a new "Background research" section referencing all three.

**Tech Stack:** Python 3.11 stdlib only. `html.parser.HTMLParser` for HTML stripping. Flash (gemini-2.5-flash) via BaseWorker.call(). unittest for tests.

**Spec:** `docs/superpowers/specs/2026-03-17-autonomous-mind-design.md`

---

## File Map

| Action | Path | Purpose |
|--------|------|---------|
| Create | `workspace/workers/vault_reader.py` | Fetch bookmark URLs, summarise, enrich vault notes |
| Create | `workspace/workers/vault_connector.py` | Find vault notes related to input text |
| Create | `workspace/workers/vault_roulette.py` | Pick random/decaying vault notes |
| Create | `workspace/tasks/vault-reader.json` | Config for vault-reader |
| Create | `workspace/tasks/vault-connector.json` | Config for vault-connector |
| Create | `workspace/tasks/vault-roulette.json` | Config for vault-roulette |
| Create | `workspace/tests/test_vault_reader.py` | Tests for vault-reader |
| Create | `workspace/tests/test_vault_connector.py` | Tests for vault-connector |
| Create | `workspace/tests/test_vault_roulette.py` | Tests for vault-roulette |
| Modify | `workspace/HEARTBEAT.md` | Add background research rotation |

---

## Shared Utilities

Before building modules, we need two shared helpers used by all three: frontmatter parsing and HTML text extraction. These live in a new utility file rather than duplicating across workers.

### Task 1: Vault utilities — frontmatter parser and HTML text extractor

**Files:**
- Create: `workspace/workers/vault_utils.py`
- Create: `workspace/tests/test_vault_utils.py`

- [ ] **Step 1: Write failing test for frontmatter parsing**

```python
# workspace/tests/test_vault_utils.py
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from workers.vault_utils import parse_frontmatter, extract_urls


class TestParseFrontmatter(unittest.TestCase):
    def test_basic_frontmatter(self):
        content = "---\ntitle: Test Note\ntype: bookmark\nstatus: active\ntags: [\"ai\", \"agents\"]\n---\n\nBody text here."
        meta, body = parse_frontmatter(content)
        self.assertEqual(meta["title"], "Test Note")
        self.assertEqual(meta["type"], "bookmark")
        self.assertEqual(meta["status"], "active")
        self.assertIn("Body text here", body)

    def test_no_frontmatter(self):
        content = "Just a plain file."
        meta, body = parse_frontmatter(content)
        self.assertEqual(meta, {})
        self.assertEqual(body, "Just a plain file.")

    def test_frontmatter_with_quotes(self):
        content = '---\ntitle: "Quoted: title"\nconfidence: 9\n---\n\nBody.'
        meta, body = parse_frontmatter(content)
        self.assertEqual(meta["title"], "Quoted: title")
        self.assertEqual(meta["confidence"], "9")


class TestExtractUrls(unittest.TestCase):
    def test_links_section(self):
        content = "---\ntype: bookmark\n---\n\n## Links\n- https://example.com/article\n- https://other.com/page\n"
        urls = extract_urls(content)
        self.assertEqual(urls, ["https://example.com/article", "https://other.com/page"])

    def test_no_links(self):
        content = "---\ntype: task\n---\n\nJust a task."
        urls = extract_urls(content)
        self.assertEqual(urls, [])

    def test_inline_urls(self):
        content = "---\ntype: bookmark\n---\n\nCheck out https://example.com/inline for details."
        urls = extract_urls(content)
        self.assertEqual(urls, ["https://example.com/inline"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd workspace && python3 -m pytest tests/test_vault_utils.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'workers.vault_utils'`

- [ ] **Step 3: Implement vault_utils.py**

```python
# workspace/workers/vault_utils.py
"""Shared utilities for vault workers. Frontmatter parsing, URL extraction, HTML stripping."""

import os
import re
from html.parser import HTMLParser


def parse_frontmatter(content):
    """Parse YAML frontmatter from a vault note. Returns (meta_dict, body_string).

    Simple parser — handles key: value pairs, quoted values, and arrays.
    Does not use yaml lib (stdlib only).
    """
    if not content.startswith("---"):
        return {}, content

    end = content.find("---", 3)
    if end == -1:
        return {}, content

    frontmatter = content[3:end]
    body = content[end + 3:].strip()

    meta = {}
    for line in frontmatter.strip().split("\n"):
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        val = val.strip()
        # Strip surrounding quotes
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            val = val[1:-1]
        meta[key.strip()] = val

    return meta, body


def extract_urls(content):
    """Extract URLs from a vault note. Checks ## Links section first, then inline URLs."""
    urls = []
    url_pattern = re.compile(r'https?://[^\s<>"\')\]]+')

    # Check for ## Links section
    links_match = re.search(r'^## Links\s*\n(.*?)(?=\n##|\Z)', content, re.MULTILINE | re.DOTALL)
    if links_match:
        links_section = links_match.group(1)
        urls = url_pattern.findall(links_section)
    else:
        # Fall back to any URLs in body (after frontmatter)
        _, body = parse_frontmatter(content)
        urls = url_pattern.findall(body)

    return urls


class _HTMLTextExtractor(HTMLParser):
    """Extract readable text from HTML, stripping tags."""

    SKIP_TAGS = {"script", "style", "nav", "header", "footer", "noscript", "svg", "iframe"}

    def __init__(self):
        super().__init__()
        self._pieces = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self.SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag.lower() in self.SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._skip_depth == 0:
            text = data.strip()
            if text:
                self._pieces.append(text)

    def get_text(self):
        return "\n".join(self._pieces)


def html_to_text(html_content):
    """Convert HTML to readable text using stdlib HTMLParser.

    Strips script, style, nav, header, footer, noscript, svg, iframe tags.
    """
    extractor = _HTMLTextExtractor()
    try:
        extractor.feed(html_content)
    except Exception:
        # Malformed HTML — return raw with tags stripped via regex fallback
        return re.sub(r'<[^>]+>', ' ', html_content).strip()
    return extractor.get_text()


def write_vault_note_atomic(filepath, content):
    """Write content to a vault note file atomically (write-to-temp-then-rename)."""
    tmp_path = filepath + ".tmp"
    with open(tmp_path, "w") as f:
        f.write(content)
    os.replace(tmp_path, filepath)


def update_frontmatter(content, updates):
    """Update frontmatter fields in a vault note. Returns new content string.

    Adds new fields and overwrites existing ones. Preserves body and field order.
    """
    meta, body = parse_frontmatter(content)
    meta.update(updates)

    # Rebuild frontmatter
    lines = ["---"]
    for key, val in meta.items():
        # Keep arrays and quoted strings as-is if they look like JSON
        if isinstance(val, str) and (val.startswith("[") or val.startswith("{")):
            lines.append(f"{key}: {val}")
        elif isinstance(val, str) and ":" in val:
            lines.append(f'{key}: "{val}"')
        else:
            lines.append(f"{key}: {val}")
    lines.append("---")

    if body:
        lines.append("")
        lines.append(body)

    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd workspace && python3 -m pytest tests/test_vault_utils.py -v`
Expected: all tests PASS

- [ ] **Step 5: Write test for HTML text extraction**

Add to `workspace/tests/test_vault_utils.py`:

```python
from workers.vault_utils import html_to_text, update_frontmatter, write_vault_note_atomic


class TestHtmlToText(unittest.TestCase):
    def test_basic_html(self):
        html = "<html><body><h1>Title</h1><p>Paragraph one.</p><p>Paragraph two.</p></body></html>"
        text = html_to_text(html)
        self.assertIn("Title", text)
        self.assertIn("Paragraph one", text)
        self.assertNotIn("<", text)

    def test_strips_script_and_style(self):
        html = "<html><head><style>body{color:red}</style></head><body><script>alert('hi')</script><p>Real content.</p></body></html>"
        text = html_to_text(html)
        self.assertIn("Real content", text)
        self.assertNotIn("alert", text)
        self.assertNotIn("color:red", text)

    def test_strips_nav_and_footer(self):
        html = "<nav>Menu items</nav><main><p>Article content.</p></main><footer>Copyright</footer>"
        text = html_to_text(html)
        self.assertIn("Article content", text)
        self.assertNotIn("Menu items", text)
        self.assertNotIn("Copyright", text)


class TestUpdateFrontmatter(unittest.TestCase):
    def test_adds_new_fields(self):
        content = "---\ntitle: Test\ntype: bookmark\n---\n\nBody."
        updated = update_frontmatter(content, {"enriched": "true", "enriched_at": "2026-03-17T12:00:00Z"})
        self.assertIn("enriched: true", updated)
        self.assertIn("enriched_at:", updated)
        self.assertIn("Body.", updated)

    def test_overwrites_existing_fields(self):
        content = "---\ntitle: Old\ntype: bookmark\n---\n\nBody."
        updated = update_frontmatter(content, {"title": "New Title"})
        self.assertIn("title: New Title", updated)
        self.assertNotIn("title: Old", updated)
```

- [ ] **Step 6: Run all tests to verify they pass**

Run: `cd workspace && python3 -m pytest tests/test_vault_utils.py -v`
Expected: all tests PASS

- [ ] **Step 7: Commit**

```bash
git add workspace/workers/vault_utils.py workspace/tests/test_vault_utils.py
git commit -m "feat: vault utilities — frontmatter parser, URL extractor, HTML stripper"
```

---

### Task 2: vault-reader — fetch, summarise, enrich bookmarks

**Files:**
- Create: `workspace/workers/vault_reader.py`
- Create: `workspace/tasks/vault-reader.json`
- Create: `workspace/tests/test_vault_reader.py`

- [ ] **Step 1: Create task config**

```json
// workspace/tasks/vault-reader.json
{
    "task_id": "vault-reader",
    "default_model": "gemini-2.5-flash",
    "fallback_model": "gemini-2.5-flash-lite",
    "max_content_chars": 5000,
    "context_slugs": ["priorities", "interests"],
    "skip_if_enriched": true
}
```

- [ ] **Step 2: Write failing tests**

```python
# workspace/tests/test_vault_reader.py
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from workers.vault_reader import VaultReader, fetch_url_text


class TestFetchUrlText(unittest.TestCase):
    @patch("workers.vault_reader.urllib.request.urlopen")
    def test_fetches_and_strips_html(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"<html><body><p>Article content here.</p></body></html>"
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.headers = {"content-type": "text/html"}
        mock_urlopen.return_value = mock_resp

        text = fetch_url_text("https://example.com/article")
        self.assertIn("Article content here", text)
        self.assertNotIn("<p>", text)

    @patch("workers.vault_reader.urllib.request.urlopen")
    def test_truncates_long_content(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = ("<p>" + "x" * 10000 + "</p>").encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.headers = {"content-type": "text/html"}
        mock_urlopen.return_value = mock_resp

        text = fetch_url_text("https://example.com/long", max_chars=5000)
        self.assertLessEqual(len(text), 5000)

    @patch("workers.vault_reader.urllib.request.urlopen")
    def test_handles_timeout(self, mock_urlopen):
        mock_urlopen.side_effect = Exception("timeout")
        text = fetch_url_text("https://example.com/slow")
        self.assertIsNone(text)


class TestVaultReader(unittest.TestCase):
    def _make_bookmark(self, tmpdir, filename="bookmark-test.md", url="https://example.com/article", enriched=False):
        content = f"---\nid: note_test\ntype: bookmark\nstatus: active\ntags: [\"ai\"]\ntitle: Test Bookmark\n"
        if enriched:
            content += "enriched: true\nenriched_at: 2026-03-17T00:00:00Z\n"
        content += f"---\n\n## Links\n- {url}\n"
        path = os.path.join(tmpdir, filename)
        with open(path, "w") as f:
            f.write(content)
        return path

    @patch("workers.vault_reader.fetch_url_text")
    @patch("workers.base_worker.call_model")
    def test_read_enriches_bookmark(self, mock_call, mock_fetch):
        mock_fetch.return_value = "Article about agent architectures and tool use patterns."
        mock_call.return_value = {
            "text": json.dumps({
                "summary": "Overview of agent architectures.",
                "themes": ["agents", "tool-use"],
                "entities": ["LangChain", "OpenAI"],
                "connections": ["LocalShout AI pipeline"]
            }),
            "input_tokens": 1000,
            "output_tokens": 200,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._make_bookmark(tmpdir)
            worker = VaultReader(vault_dir=tmpdir)
            result = worker.read(path)

            self.assertEqual(result["status"], "enriched")
            self.assertIn("agent architectures", result["summary"])

            # Verify file was updated
            with open(path) as f:
                content = f.read()
            self.assertIn("enriched: true", content)
            self.assertIn("Overview of agent architectures", content)

    @patch("workers.vault_reader.fetch_url_text")
    def test_read_skips_already_enriched(self, mock_fetch):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._make_bookmark(tmpdir, enriched=True)
            worker = VaultReader(vault_dir=tmpdir)
            result = worker.read(path)
            self.assertEqual(result["status"], "already_enriched")
            mock_fetch.assert_not_called()

    def test_read_no_url(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "note.md")
            with open(path, "w") as f:
                f.write("---\ntype: task\ntitle: No URL\n---\n\nJust a task.\n")
            worker = VaultReader(vault_dir=tmpdir)
            result = worker.read(path)
            self.assertEqual(result["status"], "no_url")

    def test_next_picks_oldest_unread(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create two bookmarks — older one should be picked first
            self._make_bookmark(tmpdir, "old.md", "https://example.com/old")
            import time; time.sleep(0.1)
            self._make_bookmark(tmpdir, "new.md", "https://example.com/new")

            worker = VaultReader(vault_dir=tmpdir)
            path = worker.find_next()
            self.assertTrue(path.endswith("old.md"))

    def test_stats(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._make_bookmark(tmpdir, "a.md", enriched=False)
            self._make_bookmark(tmpdir, "b.md", enriched=True)
            self._make_bookmark(tmpdir, "c.md", enriched=False)

            worker = VaultReader(vault_dir=tmpdir)
            stats = worker.stats()
            self.assertEqual(stats["total_bookmarks"], 3)
            self.assertEqual(stats["enriched"], 1)
            self.assertEqual(stats["unread"], 2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd workspace && python3 -m pytest tests/test_vault_reader.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 4: Implement vault_reader.py**

```python
#!/usr/bin/env python3
"""
Vault reader worker.

Fetches bookmark URLs, extracts readable text, summarises via Flash,
enriches vault notes with summary, themes, and connections.

Uses Reader pattern (ADR-003): LLM call on untrusted web content returns
fixed-schema JSON only. No tools, no direct file writes from LLM response.
The script validates and writes.

Usage:
    python3 workers/vault_reader.py read --file vault/notes/bookmark-x.md
    python3 workers/vault_reader.py next
    python3 workers/vault_reader.py stats
    python3 workers/vault_reader.py next --dry-run
"""

import argparse
import json
import os
import re
import sys
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from workers.base_worker import BaseWorker
from workers.vault_utils import (
    parse_frontmatter, extract_urls, html_to_text,
    write_vault_note_atomic, update_frontmatter,
)

_workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

READER_SYSTEM_PROMPT = """You are a content summariser. You receive article text extracted from a web page.
Return JSON only — no markdown fences, no explanation.

Response schema:
{
  "summary": "<2-3 sentence summary of the article>",
  "themes": ["<theme1>", "<theme2>", ...],
  "entities": ["<named entity1>", "<named entity2>", ...],
  "connections": ["<connection to user context1>", ...]
}"""


def fetch_url_text(url, max_chars=5000, timeout=15):
    """Fetch a URL and return readable text. Returns None on failure."""
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; JimboReader/1.0)",
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            content_type = resp.headers.get("content-type", "")

        # Decode
        if "charset=" in content_type:
            charset = content_type.split("charset=")[-1].split(";")[0].strip()
        else:
            charset = "utf-8"
        try:
            html = raw.decode(charset)
        except (UnicodeDecodeError, LookupError):
            html = raw.decode("utf-8", errors="replace")

        # Strip HTML to text
        text = html_to_text(html)

        # Truncate
        if len(text) > max_chars:
            text = text[:max_chars]

        return text if text.strip() else None

    except Exception as e:
        sys.stderr.write(f"[vault-reader] fetch failed for {url}: {e}\n")
        return None


def parse_llm_json(text):
    """Parse JSON from LLM response, stripping markdown fences if present."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


class VaultReader(BaseWorker):
    def __init__(self, vault_dir=None):
        super().__init__("vault-reader")
        self.vault_dir = vault_dir or os.path.join("/workspace", "vault", "notes")
        self.max_chars = self.config.get("max_content_chars", 5000)
        self.skip_enriched = self.config.get("skip_if_enriched", True)

    def _scan_bookmarks(self):
        """Scan vault for bookmark notes. Returns list of (filepath, meta) tuples."""
        bookmarks = []
        if not os.path.exists(self.vault_dir):
            return bookmarks
        for filename in os.listdir(self.vault_dir):
            if not filename.endswith(".md"):
                continue
            filepath = os.path.join(self.vault_dir, filename)
            try:
                with open(filepath) as f:
                    content = f.read(2000)
                meta, _ = parse_frontmatter(content)
                if meta.get("type") == "bookmark":
                    bookmarks.append((filepath, meta))
            except OSError:
                continue
        return bookmarks

    def find_next(self):
        """Find the oldest unread bookmark. Returns filepath or None."""
        bookmarks = self._scan_bookmarks()
        unread = [(fp, m) for fp, m in bookmarks
                  if not (self.skip_enriched and m.get("enriched") == "true")]
        if not unread:
            return None
        # Sort by file mtime (oldest first)
        unread.sort(key=lambda x: os.path.getmtime(x[0]))
        return unread[0][0]

    def stats(self):
        """Return bookmark stats."""
        bookmarks = self._scan_bookmarks()
        enriched = sum(1 for _, m in bookmarks if m.get("enriched") == "true")
        return {
            "total_bookmarks": len(bookmarks),
            "enriched": enriched,
            "unread": len(bookmarks) - enriched,
        }

    def read(self, filepath, dry_run=False):
        """Read and enrich a single bookmark note. Returns result dict."""
        with open(filepath) as f:
            content = f.read()

        meta, body = parse_frontmatter(content)
        filename = os.path.basename(filepath)

        # Skip if already enriched
        if self.skip_enriched and meta.get("enriched") == "true":
            return {"file": filename, "status": "already_enriched"}

        # Extract URL
        urls = extract_urls(content)
        if not urls:
            return {"file": filename, "status": "no_url"}

        url = urls[0]
        sys.stderr.write(f"[vault-reader] fetching {url}\n")

        # Fetch content
        text = fetch_url_text(url, max_chars=self.max_chars)
        if text is None:
            return {"file": filename, "url": url, "status": "fetch_failed"}

        # Build context for connections
        context = self.get_context()
        context_summary = "\n".join(f"- {k}" for k in context.keys())

        # Reader call — fixed schema, no tools (ADR-003)
        prompt = f"""Article text (from {url}):

{text}

User's context topics: {context_summary}
Note tags: {meta.get('tags', '[]')}

Summarise this article and find connections to the user's context."""

        result = self.call(prompt, system=READER_SYSTEM_PROMPT)
        parsed = parse_llm_json(result["text"])

        if parsed is None:
            sys.stderr.write(f"[vault-reader] failed to parse LLM response for {filename}\n")
            return {"file": filename, "url": url, "status": "parse_failed"}

        summary = parsed.get("summary", "")
        themes = parsed.get("themes", [])
        entities = parsed.get("entities", [])
        connections = parsed.get("connections", [])

        if not dry_run:
            # Update frontmatter
            import datetime
            now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            new_content = update_frontmatter(content, {
                "enriched": "true",
                "enriched_at": now,
            })

            # Append summary section to body
            enrichment = f"\n\n## Summary (auto-enriched)\n\n{summary}\n"
            if themes:
                enrichment += f"\n**Themes:** {', '.join(themes)}\n"
            if entities:
                enrichment += f"\n**Entities:** {', '.join(entities)}\n"
            if connections:
                enrichment += f"\n**Connections:** {', '.join(connections)}\n"

            new_content += enrichment
            write_vault_note_atomic(filepath, new_content)
            sys.stderr.write(f"[vault-reader] enriched {filename}\n")

        self.log_run(
            input_tokens=result["input_tokens"],
            output_tokens=result["output_tokens"],
            input_summary=f"{filename}: {url}",
            output_summary=f"{'enriched' if not dry_run else 'dry-run'}: {len(themes)} themes, {len(connections)} connections",
        )

        return {
            "file": filename,
            "url": url,
            "status": "enriched" if not dry_run else "dry_run",
            "summary": summary,
            "themes": themes,
            "connections": connections,
        }

    def run(self, input_data=None):
        """Not used — vault-reader uses read/next/stats commands via main()."""
        raise NotImplementedError("Use read(), find_next(), or stats()")


def main():
    parser = argparse.ArgumentParser(description="Vault reader — fetch and enrich bookmarks")
    sub = parser.add_subparsers(dest="command", required=True)

    read_p = sub.add_parser("read", help="Read and enrich a specific bookmark")
    read_p.add_argument("--file", required=True, help="Path to vault note")
    read_p.add_argument("--dry-run", action="store_true")

    next_p = sub.add_parser("next", help="Read the next unread bookmark")
    next_p.add_argument("--dry-run", action="store_true")

    sub.add_parser("stats", help="Show bookmark enrichment stats")

    args = parser.parse_args()
    worker = VaultReader()

    if args.command == "stats":
        print(json.dumps(worker.stats(), indent=2))
    elif args.command == "read":
        result = worker.read(args.file, dry_run=args.dry_run)
        print(json.dumps(result, indent=2))
    elif args.command == "next":
        path = worker.find_next()
        if path is None:
            print(json.dumps({"status": "no_unread_bookmarks"}))
        else:
            result = worker.read(path, dry_run=args.dry_run)
            print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd workspace && python3 -m pytest tests/test_vault_reader.py -v`
Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add workspace/workers/vault_reader.py workspace/tasks/vault-reader.json workspace/tests/test_vault_reader.py
git commit -m "feat: vault-reader — fetch, summarise, enrich bookmarks"
```

---

### Task 3: vault-connector — find related vault notes

**Files:**
- Create: `workspace/workers/vault_connector.py`
- Create: `workspace/tasks/vault-connector.json`
- Create: `workspace/tests/test_vault_connector.py`

- [ ] **Step 1: Create task config**

```json
// workspace/tasks/vault-connector.json
{
    "task_id": "vault-connector",
    "default_model": "gemini-2.5-flash",
    "fallback_model": "gemini-2.5-flash-lite",
    "max_results": 5,
    "vault_dir": "/workspace/vault/notes",
    "min_keyword_hits": 1
}
```

- [ ] **Step 2: Write failing tests**

```python
# workspace/tests/test_vault_connector.py
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from workers.vault_connector import VaultConnector


class TestVaultConnector(unittest.TestCase):
    def _make_note(self, tmpdir, filename, title, note_type="task", tags="[]", priority="5", body=""):
        content = f"---\ntitle: {title}\ntype: {note_type}\nstatus: active\ntags: {tags}\npriority: {priority}\n---\n\n{body}\n"
        path = os.path.join(tmpdir, filename)
        with open(path, "w") as f:
            f.write(content)
        return path

    @patch("workers.base_worker.call_model")
    def test_match_finds_keyword_hits(self, mock_call):
        mock_call.return_value = {
            "text": json.dumps({"keywords": ["mortgage", "finance", "rates"]}),
            "input_tokens": 100,
            "output_tokens": 50,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            self._make_note(tmpdir, "finance.md", "SIPP timing", tags='["finance"]', priority="8",
                            body="Mortgage rates and SIPP contribution timing.")
            self._make_note(tmpdir, "cooking.md", "Lamb tagine", note_type="recipe", tags='["food"]',
                            body="A hearty lamb tagine recipe.")
            self._make_note(tmpdir, "travel.md", "Spain trip", note_type="travel", tags='["travel"]',
                            body="Planning a trip to Spain.")

            connector = VaultConnector(vault_dir=tmpdir)
            result = connector.match("Fed rate outlook and mortgage impact")

            self.assertGreater(len(result["matches"]), 0)
            self.assertEqual(result["matches"][0]["file"], "finance.md")

    @patch("workers.base_worker.call_model")
    def test_match_respects_max_results(self, mock_call):
        mock_call.return_value = {
            "text": json.dumps({"keywords": ["test"]}),
            "input_tokens": 100,
            "output_tokens": 50,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            for i in range(10):
                self._make_note(tmpdir, f"note{i}.md", f"Test note {i}", body="test content")

            connector = VaultConnector(vault_dir=tmpdir)
            connector.max_results = 3
            result = connector.match("test query")
            self.assertLessEqual(len(result["matches"]), 3)

    @patch("workers.base_worker.call_model")
    def test_match_returns_empty_on_no_hits(self, mock_call):
        mock_call.return_value = {
            "text": json.dumps({"keywords": ["quantum", "physics"]}),
            "input_tokens": 100,
            "output_tokens": 50,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            self._make_note(tmpdir, "cooking.md", "Lamb tagine", note_type="recipe", body="A recipe.")

            connector = VaultConnector(vault_dir=tmpdir)
            result = connector.match("quantum physics research")
            self.assertEqual(len(result["matches"]), 0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd workspace && python3 -m pytest tests/test_vault_connector.py -v`
Expected: FAIL

- [ ] **Step 4: Implement vault_connector.py**

```python
#!/usr/bin/env python3
"""
Vault connector worker.

Finds vault notes related to input text via keyword extraction + grep + tag matching.

Usage:
    python3 workers/vault_connector.py match --query "Fed rate outlook and mortgage impact"
    python3 workers/vault_connector.py match-email --gmail-id 19cf919de37e57bc
    python3 workers/vault_connector.py match-event --summary "Watford vs Wrexham"
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from workers.base_worker import BaseWorker
from workers.vault_utils import parse_frontmatter

_workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

KEYWORD_SYSTEM_PROMPT = """Extract 5-10 keywords and named entities from this text.
Return JSON only — no markdown fences, no explanation.
Schema: {"keywords": ["keyword1", "keyword2", ...]}"""


class VaultConnector(BaseWorker):
    def __init__(self, vault_dir=None):
        super().__init__("vault-connector")
        self.vault_dir = vault_dir or self.config.get("vault_dir", "/workspace/vault/notes")
        self.max_results = self.config.get("max_results", 5)
        self.min_hits = self.config.get("min_keyword_hits", 1)

    def _extract_keywords(self, text):
        """Call Flash to extract keywords from text."""
        result = self.call(text, system=KEYWORD_SYSTEM_PROMPT)
        response = result["text"].strip()
        if response.startswith("```"):
            response = response.split("\n", 1)[1] if "\n" in response else response[3:]
        if response.endswith("```"):
            response = response[:-3].strip()
        try:
            parsed = json.loads(response)
            return parsed.get("keywords", []), result
        except json.JSONDecodeError:
            return [], result

    def _scan_notes(self):
        """Scan vault and return list of (filepath, meta, body) tuples."""
        notes = []
        if not os.path.exists(self.vault_dir):
            return notes
        for filename in os.listdir(self.vault_dir):
            if not filename.endswith(".md"):
                continue
            filepath = os.path.join(self.vault_dir, filename)
            try:
                with open(filepath) as f:
                    content = f.read()
                meta, body = parse_frontmatter(content)
                if meta.get("status") != "active":
                    continue
                notes.append((filepath, meta, body))
            except OSError:
                continue
        return notes

    def _score_note(self, keywords, meta, body):
        """Score a note against keywords. Returns (score, reasons)."""
        score = 0
        reasons = []

        filename_lower = meta.get("title", "").lower()
        body_lower = body.lower()
        tags_str = meta.get("tags", "[]").lower()

        for kw in keywords:
            kw_lower = kw.lower()
            if kw_lower in filename_lower:
                score += 3
                reasons.append(f"title: {kw}")
            if kw_lower in body_lower:
                score += 1
                reasons.append(f"keyword: {kw}")
            if kw_lower in tags_str:
                score += 2
                reasons.append(f"tag: {kw}")

        # Priority bonus
        try:
            priority = int(meta.get("priority", "0"))
            if priority >= 7:
                score += 1
                reasons.append(f"priority >= 7")
        except ValueError:
            pass

        return score, reasons

    def match(self, query):
        """Find vault notes matching a text query. Returns result dict."""
        keywords, llm_result = self._extract_keywords(query)
        if not keywords:
            return {"query": query, "matches": [], "keywords_extracted": []}

        notes = self._scan_notes()
        scored = []

        for filepath, meta, body in notes:
            score, reasons = self._score_note(keywords, meta, body)
            if score >= self.min_hits:
                scored.append({
                    "file": os.path.basename(filepath),
                    "title": meta.get("title", os.path.basename(filepath)),
                    "type": meta.get("type", "unknown"),
                    "priority": int(meta.get("priority", "0")) if meta.get("priority", "").isdigit() else 0,
                    "match_reasons": reasons,
                    "snippet": body[:80].strip() if body else "",
                    "score": score,
                })

        # Sort by score descending, then priority descending
        scored.sort(key=lambda x: (x["score"], x["priority"]), reverse=True)
        matches = scored[:self.max_results]

        # Remove internal score from output
        for m in matches:
            del m["score"]

        self.log_run(
            input_tokens=llm_result["input_tokens"],
            output_tokens=llm_result["output_tokens"],
            input_summary=f"query: {query[:80]}",
            output_summary=f"{len(matches)} matches from {len(notes)} notes",
        )

        return {
            "query": query,
            "matches": matches,
            "keywords_extracted": keywords,
        }

    def match_from_briefing(self, gmail_id):
        """Find vault notes related to a specific email insight from briefing-input.json."""
        briefing_path = os.path.join(_workspace_dir, "briefing-input.json")
        if not os.path.exists(briefing_path):
            return {"error": "briefing-input.json not found", "matches": []}

        with open(briefing_path) as f:
            data = json.load(f)

        # Search email insights for the gmail_id
        for insight in data.get("email_insights", []):
            if insight.get("gmail_id") == gmail_id:
                query = f"{insight.get('subject', '')} {insight.get('insight', '')} {insight.get('reason', '')}"
                return self.match(query.strip())

        return {"error": f"gmail_id {gmail_id} not found in briefing-input.json", "matches": []}

    def run(self, input_data=None):
        raise NotImplementedError("Use match() or match_from_briefing()")


def main():
    parser = argparse.ArgumentParser(description="Vault connector — find related notes")
    sub = parser.add_subparsers(dest="command", required=True)

    match_p = sub.add_parser("match", help="Find notes matching a text query")
    match_p.add_argument("--query", required=True)

    email_p = sub.add_parser("match-email", help="Find notes related to an email insight")
    email_p.add_argument("--gmail-id", required=True)

    event_p = sub.add_parser("match-event", help="Find notes related to a calendar event")
    event_p.add_argument("--summary", required=True)

    args = parser.parse_args()
    connector = VaultConnector()

    if args.command == "match":
        result = connector.match(args.query)
    elif args.command == "match-email":
        result = connector.match_from_briefing(args.gmail_id)
    elif args.command == "match-event":
        result = connector.match(args.summary)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd workspace && python3 -m pytest tests/test_vault_connector.py -v`
Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add workspace/workers/vault_connector.py workspace/tasks/vault-connector.json workspace/tests/test_vault_connector.py
git commit -m "feat: vault-connector — keyword extraction and vault note matching"
```

---

### Task 4: vault-roulette — random/decaying note picker

**Files:**
- Create: `workspace/workers/vault_roulette.py`
- Create: `workspace/tasks/vault-roulette.json`
- Create: `workspace/tests/test_vault_roulette.py`

- [ ] **Step 1: Create task config**

```json
// workspace/tasks/vault-roulette.json
{
    "task_id": "vault-roulette",
    "default_model": "gemini-2.5-flash",
    "decay_threshold_days": 30,
    "type_weights": {"idea": 3, "bookmark": 2, "task": 1, "recipe": 2, "travel": 2},
    "exclude_types": ["journal"]
}
```

- [ ] **Step 2: Write failing tests**

```python
# workspace/tests/test_vault_roulette.py
import json
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from workers.vault_roulette import VaultRoulette


class TestVaultRoulette(unittest.TestCase):
    def _make_note(self, tmpdir, filename, title, note_type="idea", tags="[]", age_days=0):
        content = f"---\ntitle: {title}\ntype: {note_type}\nstatus: active\ntags: {tags}\n---\n\nContent for {title}.\n"
        path = os.path.join(tmpdir, filename)
        with open(path, "w") as f:
            f.write(content)
        if age_days > 0:
            mtime = time.time() - (age_days * 86400)
            os.utime(path, (mtime, mtime))
        return path

    def test_spin_returns_a_note(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._make_note(tmpdir, "idea1.md", "Cool idea", "idea")
            self._make_note(tmpdir, "idea2.md", "Another idea", "idea")

            roulette = VaultRoulette(vault_dir=tmpdir)
            result = roulette.spin()
            self.assertIn(result["file"], ["idea1.md", "idea2.md"])
            self.assertEqual(result["type"], "idea")

    def test_spin_decaying_filters_by_age(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._make_note(tmpdir, "old.md", "Old idea", "idea", age_days=45)
            self._make_note(tmpdir, "new.md", "Fresh idea", "idea", age_days=2)

            roulette = VaultRoulette(vault_dir=tmpdir)
            result = roulette.spin(decaying=True, decay_days=30)
            self.assertEqual(result["file"], "old.md")

    def test_spin_excludes_types(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._make_note(tmpdir, "journal.md", "My journal", "journal")
            self._make_note(tmpdir, "idea.md", "An idea", "idea")

            roulette = VaultRoulette(vault_dir=tmpdir)
            result = roulette.spin()
            self.assertEqual(result["file"], "idea.md")

    def test_spin_empty_vault(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            roulette = VaultRoulette(vault_dir=tmpdir)
            result = roulette.spin()
            self.assertEqual(result["status"], "no_candidates")

    def test_spin_type_filter(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._make_note(tmpdir, "recipe.md", "Tagine", "recipe")
            self._make_note(tmpdir, "idea.md", "AI thing", "idea")

            roulette = VaultRoulette(vault_dir=tmpdir)
            result = roulette.spin(note_type="recipe")
            self.assertEqual(result["file"], "recipe.md")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd workspace && python3 -m pytest tests/test_vault_roulette.py -v`
Expected: FAIL

- [ ] **Step 4: Implement vault_roulette.py**

```python
#!/usr/bin/env python3
"""
Vault roulette worker.

Picks a random or decaying vault note and returns it with context
about why it's being surfaced.

Usage:
    python3 workers/vault_roulette.py spin
    python3 workers/vault_roulette.py spin --decaying --days 30
    python3 workers/vault_roulette.py spin --type idea
"""

import argparse
import json
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from workers.base_worker import BaseWorker
from workers.vault_utils import parse_frontmatter


class VaultRoulette(BaseWorker):
    def __init__(self, vault_dir=None):
        super().__init__("vault-roulette")
        self.vault_dir = vault_dir or os.path.join("/workspace", "vault", "notes")
        self.type_weights = self.config.get("type_weights", {"idea": 3, "bookmark": 2, "task": 1})
        self.exclude_types = set(self.config.get("exclude_types", ["journal"]))
        self.default_decay_days = self.config.get("decay_threshold_days", 30)

    def _scan_notes(self):
        """Scan vault notes, return list of (filepath, meta, mtime) tuples."""
        notes = []
        if not os.path.exists(self.vault_dir):
            return notes
        for filename in os.listdir(self.vault_dir):
            if not filename.endswith(".md"):
                continue
            filepath = os.path.join(self.vault_dir, filename)
            try:
                with open(filepath) as f:
                    content = f.read(2000)
                meta, _ = parse_frontmatter(content)
                if meta.get("status") != "active":
                    continue
                mtime = os.path.getmtime(filepath)
                notes.append((filepath, meta, mtime))
            except OSError:
                continue
        return notes

    def spin(self, decaying=False, decay_days=None, note_type=None):
        """Pick a random vault note. Returns result dict."""
        decay_days = decay_days or self.default_decay_days
        now = time.time()

        notes = self._scan_notes()

        # Filter excluded types
        notes = [(fp, m, mt) for fp, m, mt in notes if m.get("type") not in self.exclude_types]

        # Filter by type if specified
        if note_type:
            notes = [(fp, m, mt) for fp, m, mt in notes if m.get("type") == note_type]

        # Filter by decay if requested
        if decaying:
            threshold = now - (decay_days * 86400)
            notes = [(fp, m, mt) for fp, m, mt in notes if mt < threshold]

        if not notes:
            return {"status": "no_candidates"}

        # Weighted random selection
        weights = []
        for filepath, meta, mtime in notes:
            note_type_val = meta.get("type", "other")
            type_weight = self.type_weights.get(note_type_val, 1)
            age_days = (now - mtime) / 86400
            age_weight = min(age_days / 30, 3)  # Cap at 3x for very old notes
            priority_weight = 1
            try:
                priority = int(meta.get("priority", "0"))
                if priority >= 7:
                    priority_weight = 1.5
            except ValueError:
                pass
            weights.append(type_weight * age_weight * priority_weight)

        # Weighted random choice
        chosen_idx = random.choices(range(len(notes)), weights=weights, k=1)[0]
        filepath, meta, mtime = notes[chosen_idx]

        age_days = int((now - mtime) / 86400)
        filename = os.path.basename(filepath)

        # Read body preview
        try:
            with open(filepath) as f:
                content = f.read()
            _, body = parse_frontmatter(content)
            preview = body[:200].strip() if body else ""
        except OSError:
            preview = ""

        return {
            "file": filename,
            "title": meta.get("title", filename),
            "type": meta.get("type", "unknown"),
            "days_since_touched": age_days,
            "reason": f"Untouched for {age_days} days." if age_days > 0 else "Random pick.",
            "content_preview": preview,
        }

    def run(self, input_data=None):
        raise NotImplementedError("Use spin()")


def main():
    parser = argparse.ArgumentParser(description="Vault roulette — random note picker")
    sub = parser.add_subparsers(dest="command", required=True)

    spin_p = sub.add_parser("spin", help="Pick a random note")
    spin_p.add_argument("--decaying", action="store_true", help="Only pick notes older than threshold")
    spin_p.add_argument("--days", type=int, default=None, help="Decay threshold in days")
    spin_p.add_argument("--type", dest="note_type", default=None, help="Filter to specific note type")

    args = parser.parse_args()
    roulette = VaultRoulette()

    result = roulette.spin(
        decaying=args.decaying,
        decay_days=args.days,
        note_type=args.note_type,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd workspace && python3 -m pytest tests/test_vault_roulette.py -v`
Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add workspace/workers/vault_roulette.py workspace/tasks/vault-roulette.json workspace/tests/test_vault_roulette.py
git commit -m "feat: vault-roulette — random and decaying note picker"
```

---

### Task 5: Update HEARTBEAT.md — background research rotation

**Files:**
- Modify: `workspace/HEARTBEAT.md`

- [ ] **Step 1: Add background research section to HEARTBEAT.md**

Insert after the "Telegram status" section at the end of the file:

```markdown
## Background research (one random module per heartbeat)

Each heartbeat, pick ONE at random from this list. Don't repeat the same module two heartbeats in a row — use memory to track what you did last.

1. **Read a bookmark**: `python3 /workspace/workers/vault_reader.py next` — fetch and summarise the oldest unread bookmark. If it connects to something in today's email or your priorities, tell Marvin via Telegram. Example: "Just read your bookmark about agent architectures. Key themes: multi-agent coordination, tool use. Connects to your LocalShout priority."

2. **Vault roulette**: `python3 /workspace/workers/vault_roulette.py spin --decaying` — surface a note dormant 30+ days. If it connects to today's email or calendar, share it. If not, note it in memory — it might connect later. Example: "Dormant note resurface: 'Gamifying habit tracking' (42 days). Songkick email about Romare + your interest in reward systems might connect."

3. **Email × vault collision**: Pick an email insight from today's briefing-input.json. Run `python3 /workspace/workers/vault_connector.py match --query "<insight text>"`. If 2+ keyword hits, send the connection. Example: "Today's Seeking Alpha article about Fed rates connects to your SIPP timing task (priority 8) and your mortgage calculator bookmark."

**Rules:**
- Skip silently if the module finds nothing interesting. Don't send "nothing to report."
- Log every run to activity-log, even silent ones.
- You have conversation context the modules don't — if a result connects to something Marvin mentioned earlier today, say so.
- If you notice a pattern across multiple runs, synthesise it into an insight.
```

- [ ] **Step 2: Deploy updated HEARTBEAT.md and all new workers**

Run: `./scripts/workspace-push.sh`

- [ ] **Step 3: Test vault-reader on VPS inside Docker sandbox**

Run:
```bash
ssh jimbo 'export $(grep -v "^#" /opt/openclaw.env | xargs) && docker exec \
  -e GOOGLE_AI_API_KEY=$GOOGLE_AI_API_KEY \
  -e JIMBO_API_URL=$JIMBO_API_URL \
  -e JIMBO_API_KEY=$JIMBO_API_KEY \
  $(docker ps -q --filter name=openclaw-sbx) \
  python3 /workspace/workers/vault_reader.py stats'
```

Expected: JSON showing total_bookmarks, enriched, unread counts.

Then test an actual read:
```bash
ssh jimbo 'export $(grep -v "^#" /opt/openclaw.env | xargs) && docker exec \
  -e GOOGLE_AI_API_KEY=$GOOGLE_AI_API_KEY \
  -e JIMBO_API_URL=$JIMBO_API_URL \
  -e JIMBO_API_KEY=$JIMBO_API_KEY \
  $(docker ps -q --filter name=openclaw-sbx) \
  python3 /workspace/workers/vault_reader.py next --dry-run'
```

Expected: JSON with status "dry_run", summary, themes, connections.

- [ ] **Step 4: Test vault-connector on VPS**

```bash
ssh jimbo 'export $(grep -v "^#" /opt/openclaw.env | xargs) && docker exec \
  -e GOOGLE_AI_API_KEY=$GOOGLE_AI_API_KEY \
  -e JIMBO_API_URL=$JIMBO_API_URL \
  -e JIMBO_API_KEY=$JIMBO_API_KEY \
  $(docker ps -q --filter name=openclaw-sbx) \
  python3 /workspace/workers/vault_connector.py match --query "travel deals spain budget"'
```

Expected: JSON with matches array and keywords_extracted.

- [ ] **Step 5: Test vault-roulette on VPS**

```bash
ssh jimbo 'docker exec $(docker ps -q --filter name=openclaw-sbx) \
  python3 /workspace/workers/vault_roulette.py spin'
```

Expected: JSON with a random note, title, type, days_since_touched, reason, preview.

- [ ] **Step 6: Commit all changes and push**

```bash
git add -A
git commit -m "feat: phase 1 complete — vault-reader, vault-connector, vault-roulette + HEARTBEAT.md rotation"
git push
```

---

## Summary

After this plan is executed:
- **vault-reader** can fetch any bookmark URL, extract text, summarise via Flash, and enrich the vault note
- **vault-connector** can find vault notes related to any text query via keyword extraction + grep + tag matching
- **vault-roulette** can pick random or decaying notes with weighted selection
- **HEARTBEAT.md** has a background research rotation using all three modules
- All workers have tests, task configs, and follow BaseWorker patterns
- Everything is deployed to VPS and tested in the Docker sandbox

Jimbo's next heartbeat will start using the rotation. The activity log will show whether he follows through.
