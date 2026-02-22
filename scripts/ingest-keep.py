#!/usr/bin/env python3
"""Ingest Google Keep export into vault inbox as markdown files.

Reads individual JSON files from data/export/Keep/Keep 1/ (Google Takeout format)
and writes one markdown file per active note into data/vault/inbox/.
Archived Keep notes go to data/vault/archive/.

Usage:
    python3 scripts/ingest-keep.py                      # active notes only
    python3 scripts/ingest-keep.py --include-archived    # also ingest archived notes
    python3 scripts/ingest-keep.py --dry-run             # preview without writing
    python3 scripts/ingest-keep.py --stats               # just print stats, no output
"""

import json
import hashlib
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
KEEP_DIR = REPO_ROOT / "data" / "export" / "Keep" / "Keep 1"
VAULT_INBOX = REPO_ROOT / "data" / "vault" / "inbox"
VAULT_ARCHIVE = REPO_ROOT / "data" / "vault" / "archive"

URL_RE = re.compile(r'https?://[^\s<>"\')\]]+')


def make_id(source_filename):
    """Generate a stable vault ID from the Keep filename."""
    h = hashlib.sha256(f"keep:{source_filename}".encode()).hexdigest()[:8]
    return f"note_{h}"


def sanitise_filename(title, note_id):
    """Create a filesystem-safe filename from title."""
    if not title or len(title.strip()) < 2:
        return f"{note_id}.md"
    clean = re.sub(r'[^\w\s\-]', '', title[:60]).strip()
    clean = re.sub(r'\s+', '-', clean).lower()
    if not clean:
        return f"{note_id}.md"
    return f"{clean}--{note_id[:12]}.md"


def usec_to_date(usec):
    """Convert microsecond timestamp to YYYY-MM-DD."""
    if not usec:
        return ""
    try:
        dt = datetime.fromtimestamp(usec / 1_000_000, tz=timezone.utc)
        return dt.strftime("%Y-%m-%d")
    except (ValueError, OSError, OverflowError):
        return ""


def extract_urls(text):
    """Pull all URLs from text."""
    return URL_RE.findall(text) if text else []


def classify_rough(title, text_content, labels, has_list):
    """Rough pre-classification based on obvious signals."""
    combined = f"{title} {text_content}".lower()

    # Checklists
    if has_list:
        return "checklist"

    # Labels give strong signals
    label_names = [l["name"].lower() for l in (labels or [])]
    if any(l in label_names for l in ["food", "recipe", "recipes", "cooking"]):
        return "recipe"
    if any(l in label_names for l in ["travel", "trips", "holiday"]):
        return "travel"
    if any(l in label_names for l in ["media", "watch", "read", "music", "film"]):
        return "media"

    # Bare URL with no other content
    urls = extract_urls(combined)
    text_without_urls = URL_RE.sub('', combined).strip()
    if urls and len(text_without_urls) < 10:
        return "bookmark"

    # Recipe signals
    if any(w in combined for w in ['#food', 'recipe', 'tbsp', 'tsp', 'teaspoon',
                                    'tablespoon', 'cloves', 'minced', 'chopped',
                                    'simmer', 'roast', 'bake']):
        return "recipe"

    return "unknown"


def build_checklist_body(list_content):
    """Convert Keep listContent to markdown checklist."""
    lines = []
    for item in list_content:
        text = item.get("text", "").strip()
        if not text:
            continue
        checked = item.get("isChecked", False)
        marker = "[x]" if checked else "[ ]"
        lines.append(f"- {marker} {text}")
    return "\n".join(lines)


def build_markdown(note_data, source_filename):
    """Convert a single Keep note dict to markdown string."""
    title = (note_data.get("title") or "").strip()
    text_content = (note_data.get("textContent") or "").strip()
    list_content = note_data.get("listContent")
    labels = note_data.get("labels", [])
    annotations = note_data.get("annotations", [])
    is_archived = note_data.get("isArchived", False)

    note_id = make_id(source_filename)
    status = "archived" if is_archived else "inbox"

    created = usec_to_date(note_data.get("createdTimestampUsec"))
    updated = usec_to_date(note_data.get("userEditedTimestampUsec"))

    has_list = list_content is not None and len(list_content) > 0
    rough_type = classify_rough(title, text_content, labels, has_list)

    # Tags from labels
    tags = [l["name"].lower() for l in labels] if labels else []

    # Build body
    body_parts = []
    if text_content:
        body_parts.append(text_content)
    if has_list:
        body_parts.append(build_checklist_body(list_content))
    body = "\n\n".join(body_parts)

    # Links from text URLs + annotations
    all_urls = extract_urls(f"{title} {text_content}")
    for ann in annotations:
        url = ann.get("url", "")
        if url and url not in all_urls:
            all_urls.append(url)

    links_section = ""
    if all_urls:
        link_lines = "\n".join(f"- {u}" for u in all_urls)
        links_section = f"\n\n## Links\n{link_lines}"

    # Annotation titles (useful context)
    ann_section = ""
    titled_anns = [a for a in annotations if a.get("title")]
    if titled_anns:
        ann_lines = "\n".join(f"- {a['title']}" for a in titled_anns)
        ann_section = f"\n\n## Link titles\n{ann_lines}"

    # Use title or first line of content as display title
    display_title = title
    if not display_title and body:
        display_title = body.split('\n')[0][:120]
    if not display_title:
        display_title = "Untitled"

    tags_yaml = json.dumps(tags) if tags else "[]"

    frontmatter = f"""---
id: {note_id}
source: google-keep
source_id: "{source_filename}"
type: {rough_type}
status: {status}
tags: {tags_yaml}
created: {created}
updated: {updated}
processed: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}
title: "{display_title[:120].replace('"', "'")}"
---"""

    return f"{frontmatter}\n\n{body}{links_section}{ann_section}\n"


def main():
    include_archived = "--include-archived" in sys.argv
    dry_run = "--dry-run" in sys.argv
    stats_only = "--stats" in sys.argv

    if not KEEP_DIR.exists():
        print(f"Error: {KEEP_DIR} not found.")
        print("Export Keep data via Google Takeout and extract to data/export/Keep/")
        sys.exit(1)

    json_files = sorted(KEEP_DIR.glob("*.json"))
    print(f"Found {len(json_files)} Keep notes")

    if not dry_run and not stats_only:
        VAULT_INBOX.mkdir(parents=True, exist_ok=True)
        VAULT_ARCHIVE.mkdir(parents=True, exist_ok=True)

    stats = {
        "inbox": 0, "archived": 0, "skipped_trashed": 0,
        "skipped_archived": 0, "skipped_empty": 0,
        "types": {}, "labels": {}
    }

    for json_path in json_files:
        with open(json_path, encoding="utf-8") as f:
            try:
                note = json.load(f)
            except json.JSONDecodeError:
                continue

        # Skip trashed notes
        if note.get("isTrashed", False):
            stats["skipped_trashed"] += 1
            continue

        is_archived = note.get("isArchived", False)
        if is_archived and not include_archived:
            stats["skipped_archived"] += 1
            continue

        # Skip empty notes
        has_content = (note.get("textContent") or "").strip()
        has_list = note.get("listContent") and len(note["listContent"]) > 0
        has_title = (note.get("title") or "").strip()
        if not has_content and not has_list and not has_title:
            stats["skipped_empty"] += 1
            continue

        source_filename = json_path.name
        note_id = make_id(source_filename)

        # Track labels
        for label in note.get("labels", []):
            name = label["name"]
            stats["labels"][name] = stats["labels"].get(name, 0) + 1

        if stats_only:
            rough_type = classify_rough(
                note.get("title", ""), note.get("textContent", ""),
                note.get("labels"), has_list
            )
            stats["types"][rough_type] = stats["types"].get(rough_type, 0) + 1
            if is_archived:
                stats["archived"] += 1
            else:
                stats["inbox"] += 1
            continue

        md = build_markdown(note, source_filename)
        title = note.get("title") or (note.get("textContent") or "")[:60]
        filename = sanitise_filename(title, note_id)

        if is_archived:
            dest = VAULT_ARCHIVE / filename
            stats["archived"] += 1
        else:
            dest = VAULT_INBOX / filename
            stats["inbox"] += 1

        rough_type = classify_rough(
            note.get("title", ""), note.get("textContent", ""),
            note.get("labels"), has_list
        )
        stats["types"][rough_type] = stats["types"].get(rough_type, 0) + 1

        if dry_run:
            if stats["inbox"] + stats["archived"] <= 5:
                print(f"--- {dest.name} ---")
                print(md[:500])
                print()
        else:
            dest.write_text(md, encoding="utf-8")

    print(f"\nResults:")
    print(f"  Inbox: {stats['inbox']}")
    print(f"  Archived: {stats['archived']}")
    print(f"  Skipped trashed: {stats['skipped_trashed']}")
    print(f"  Skipped archived: {stats['skipped_archived']}")
    print(f"  Skipped empty: {stats['skipped_empty']}")

    if stats["types"]:
        print(f"\nRough types:")
        for t, count in sorted(stats["types"].items(), key=lambda x: -x[1]):
            print(f"  {t}: {count}")

    if stats["labels"]:
        print(f"\nLabels found:")
        for l, count in sorted(stats["labels"].items(), key=lambda x: -x[1]):
            print(f"  {l}: {count}")

    if dry_run:
        print("\n(Dry run — no files written)")
    if stats_only:
        print("\n(Stats only — no files written)")


if __name__ == "__main__":
    main()
