#!/usr/bin/env python3
"""Ingest Google Tasks dump into vault inbox as markdown files.

Reads data/tasks-dump.json (from tasks-dump.py) and writes one markdown file
per open task into data/vault/inbox/. Completed tasks go to data/vault/archive/.

Usage:
    python3 scripts/ingest-tasks.py                    # default: open tasks only
    python3 scripts/ingest-tasks.py --include-completed # also ingest completed tasks
    python3 scripts/ingest-tasks.py --dry-run           # preview without writing
"""

import json
import hashlib
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DUMP_PATH = REPO_ROOT / "data" / "tasks-dump.json"
VAULT_INBOX = REPO_ROOT / "data" / "vault" / "inbox"
VAULT_ARCHIVE = REPO_ROOT / "data" / "vault" / "archive"

URL_RE = re.compile(r'https?://[^\s<>"\')\]]+')


def make_id(source_id):
    """Generate a stable vault ID from the Google Tasks ID."""
    h = hashlib.sha256(f"gtask:{source_id}".encode()).hexdigest()[:8]
    return f"note_{h}"


def sanitise_filename(title, note_id):
    """Create a filesystem-safe filename from title."""
    if not title or len(title.strip()) < 2:
        return f"{note_id}.md"
    # Take first 60 chars, remove unsafe chars
    clean = re.sub(r'[^\w\s\-]', '', title[:60]).strip()
    clean = re.sub(r'\s+', '-', clean).lower()
    if not clean:
        return f"{note_id}.md"
    return f"{clean}--{note_id[:12]}.md"


def extract_urls(text):
    """Pull all URLs from text."""
    return URL_RE.findall(text) if text else []


def parse_date(iso_str):
    """Parse ISO date string to YYYY-MM-DD."""
    if not iso_str:
        return ""
    try:
        return iso_str[:10]
    except (ValueError, IndexError):
        return ""


def classify_rough(title, notes=""):
    """Rough pre-classification based on obvious signals. Not the LLM step —
    just enough to separate bare URLs from recipes from plain text."""
    text = f"{title} {notes}".lower()
    urls = extract_urls(f"{title} {notes}")

    # Bare URL with no other content
    title_stripped = URL_RE.sub('', title).strip()
    if urls and len(title_stripped) < 5:
        return "bookmark"

    # Recipe signals
    if any(w in text for w in ['#food', 'recipe', 'tbsp', 'tsp', 'teaspoon',
                                'tablespoon', 'cloves', 'minced', 'chopped',
                                'simmer', 'roast', 'bake']):
        return "recipe"

    return "unknown"


def build_markdown(task, list_title):
    """Convert a single task dict to markdown string."""
    title = (task.get("title") or "").strip()
    notes = (task.get("notes") or "").strip()
    source_id = task["id"]
    note_id = make_id(source_id)
    status = "inbox" if task["status"] == "needsAction" else "archived"

    urls = extract_urls(f"{title} {notes}")
    rough_type = classify_rough(title, notes)
    created = parse_date(task.get("due") or task.get("updated"))
    updated = parse_date(task.get("updated"))

    # Build body: title text (with URLs stripped if it's a bookmark), then notes
    if rough_type == "bookmark" and urls:
        body_title = URL_RE.sub('', title).strip()
        body = body_title if body_title else ""
    else:
        body = title

    if notes:
        body = f"{body}\n\n{notes}" if body else notes

    # Links section
    links_section = ""
    if urls:
        link_lines = "\n".join(f"- {u}" for u in urls)
        links_section = f"\n\n## Links\n{link_lines}"

    # Keep link
    keep_links = [l for l in task.get("links", []) if l.get("type") == "keep_note"]
    if keep_links:
        links_section += f"\n- Keep: {keep_links[0]['link']}"

    frontmatter = f"""---
id: {note_id}
source: google-tasks
source_id: "{source_id}"
source_list: "{list_title}"
type: {rough_type}
status: {status}
tags: []
created: {created}
updated: {updated}
processed: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}
title: "{title[:120].replace('"', "'")}"
---"""

    return f"{frontmatter}\n\n{body}{links_section}\n"


def main():
    include_completed = "--include-completed" in sys.argv
    dry_run = "--dry-run" in sys.argv

    if not DUMP_PATH.exists():
        print(f"Error: {DUMP_PATH} not found. Run tasks-dump.py first.")
        sys.exit(1)

    with open(DUMP_PATH) as f:
        data = json.load(f)

    # Create vault directories
    if not dry_run:
        VAULT_INBOX.mkdir(parents=True, exist_ok=True)
        VAULT_ARCHIVE.mkdir(parents=True, exist_ok=True)

    stats = {"inbox": 0, "archived": 0, "skipped_empty": 0, "skipped_completed": 0}

    for task_list in data["lists"]:
        list_title = task_list["title"]

        for task in task_list["tasks"]:
            title = (task.get("title") or "").strip()

            # Skip truly empty tasks
            if not title and not task.get("notes"):
                stats["skipped_empty"] += 1
                continue

            is_completed = task["status"] == "completed"

            if is_completed and not include_completed:
                stats["skipped_completed"] += 1
                continue

            note_id = make_id(task["id"])
            md = build_markdown(task, list_title)
            filename = sanitise_filename(title, note_id)

            if is_completed:
                dest = VAULT_ARCHIVE / filename
                stats["archived"] += 1
            else:
                dest = VAULT_INBOX / filename
                stats["inbox"] += 1

            if dry_run:
                if stats["inbox"] + stats["archived"] <= 5:
                    print(f"--- {dest.name} ---")
                    print(md[:500])
                    print()
            else:
                dest.write_text(md, encoding="utf-8")

    print(f"Done. Inbox: {stats['inbox']}, Archived: {stats['archived']}, "
          f"Skipped empty: {stats['skipped_empty']}, "
          f"Skipped completed: {stats['skipped_completed']}")

    if dry_run:
        print("\n(Dry run — no files written)")


if __name__ == "__main__":
    main()
