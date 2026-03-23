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
import datetime
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
import insights_store

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

    def find_next(self, exclude=None):
        """Find the oldest unread bookmark. Returns filepath or None.

        Args:
            exclude: set of filepaths to skip (e.g. previously failed fetches).
        """
        exclude = exclude or set()
        bookmarks = self._scan_bookmarks()
        unread = [(fp, m) for fp, m in bookmarks
                  if not (self.skip_enriched and m.get("enriched") == "true")
                  and fp not in exclude]
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

        # Insight production (ADR-045): if themes connect to priorities/interests,
        # record a pattern insight — but only if it's novel
        if not dry_run and connections and themes:
            insight_text = f"Bookmark '{meta.get('title', filename)}' themes [{', '.join(themes[:3])}] connect to: {', '.join(connections[:3])}"
            insight_tags = themes[:5]
            if not insights_store.has_similar_insight(insight_text, insight_tags):
                insights_store.add_insight(
                    module="vault-reader",
                    run_id=self.run_id,
                    insight_type="connection",
                    text=insight_text,
                    tags=insight_tags,
                    confidence=min(0.5 + 0.1 * len(connections), 0.9),
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
        max_attempts = 5
        skipped = set()
        for attempt in range(max_attempts):
            path = worker.find_next(exclude=skipped)
            if path is None:
                print(json.dumps({"status": "no_unread_bookmarks", "skipped": len(skipped)}))
                break
            result = worker.read(path, dry_run=args.dry_run)
            if result.get("status") in ("fetch_failed", "no_url"):
                skipped.add(path)
                sys.stderr.write(
                    f"[vault-reader] skipping {os.path.basename(path)} "
                    f"({result['status']}), trying next...\n"
                )
                continue
            print(json.dumps(result, indent=2))
            break
        else:
            print(json.dumps({
                "status": "all_failed",
                "attempted": max_attempts,
                "skipped_files": [os.path.basename(p) for p in skipped],
            }, indent=2))


if __name__ == "__main__":
    main()
