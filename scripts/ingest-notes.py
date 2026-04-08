#!/usr/bin/env python3
"""Batch ingest loose notes into the Jimbo vault via API.

Reads a plaintext file where notes are separated by `---` on its own line.
Each note block becomes a vault item POSTed to jimbo-api as status=inbox.

The script tries to extract a title from the first line of each block.
If the first line looks like a heading or is short enough, it becomes the title
and the rest becomes the body. Otherwise the whole block is the body and the
title is auto-generated from the first ~60 characters.

Supports optional per-note metadata on the first line(s):
    type: task
    tags: project, urgent
    due: 2026-04-15

Usage:
    python3 scripts/ingest-notes.py data/notes-dump.txt           # dry-run (default)
    python3 scripts/ingest-notes.py data/notes-dump.txt --live     # actually POST to API
    python3 scripts/ingest-notes.py data/notes-dump.txt --source phone  # tag the source
    echo "buy milk" | python3 scripts/ingest-notes.py -            # read from stdin

Environment:
    JIMBO_API_URL   — base URL for jimbo-api (required for --live)
    JIMBO_API_KEY   — API key for jimbo-api (required for --live)

Conventions:
    - Stdlib only (no pip). Matches project conventions.
    - Dry-run by default; --live flag for writes.
    - Each note goes in as status=inbox for later triage/scoring.
"""

import json
import os
import re
import sys
import urllib.request
import urllib.error
from pathlib import Path

KNOWN_TYPES = {
    "task", "idea", "bookmark", "reference", "recipe", "travel",
    "media", "checklist", "person", "finance", "health", "quote",
    "journal", "political", "event",
}

URL_RE = re.compile(r'https?://[^\s<>"\')\]]+')
META_RE = re.compile(r'^(type|tags|due|priority)\s*:\s*(.+)$', re.IGNORECASE)


def parse_blocks(text):
    """Split text on `---` delimiter lines. Returns list of non-empty blocks."""
    blocks = re.split(r'\n---+\n', text)
    return [b.strip() for b in blocks if b.strip()]


def extract_metadata(lines):
    """Pull optional key: value metadata from the top of a block.

    Returns (metadata_dict, remaining_lines).
    Stops at the first line that isn't a metadata line.
    """
    meta = {}
    consumed = 0
    for line in lines:
        m = META_RE.match(line)
        if m:
            key = m.group(1).lower()
            val = m.group(2).strip()
            meta[key] = val
            consumed += 1
        else:
            break
    # Skip blank lines between metadata and content
    remaining = lines[consumed:]
    while remaining and not remaining[0].strip():
        remaining = remaining[1:]
    return meta, remaining


def extract_title_and_body(lines):
    """Determine title and body from remaining lines (after metadata).

    Heuristics:
    - If first line starts with # → markdown heading → title
    - If first line is ≤80 chars and followed by a blank line → title
    - If first line is ≤80 chars and the block has multiple lines → title
    - Otherwise → auto-title from first 60 chars, whole block is body
    """
    if not lines:
        return "(empty note)", ""

    first = lines[0].strip()

    # Markdown heading
    if first.startswith("#"):
        title = re.sub(r'^#+\s*', '', first)
        body = "\n".join(lines[1:]).strip()
        return title[:120], body

    # Short first line with content below
    if len(first) <= 80 and len(lines) > 1:
        # Check if second line is blank (clear title separator)
        if not lines[1].strip():
            title = first
            body = "\n".join(lines[2:]).strip()
            return title[:120], body
        # Even without blank line, short first line = title
        title = first
        body = "\n".join(lines[1:]).strip()
        return title[:120], body

    # Single short line — it's both title and body
    if len(first) <= 80 and len(lines) == 1:
        return first[:120], ""

    # Long block — auto-title
    full_text = "\n".join(lines).strip()
    # Take first sentence or first 60 chars
    first_sentence = re.split(r'[.\n]', first)[0][:60]
    title = first_sentence.strip()
    if not title:
        title = first[:60].strip()
    return title[:120], full_text


def guess_type(title, body):
    """Rough type guess from content. Returns type string or 'unknown'."""
    text = f"{title} {body}".lower()
    urls = URL_RE.findall(text)

    # Bare URL
    title_without_urls = URL_RE.sub('', title).strip()
    if urls and len(title_without_urls) < 5:
        return "bookmark"

    # Recipe signals
    if any(w in text for w in ['recipe', 'tbsp', 'tsp', 'simmer', 'bake',
                                'preheat', 'ingredients', 'chopped']):
        return "recipe"

    # Task signals
    if any(w in text for w in ['todo', 'fix', 'need to', 'should',
                                'must', 'remember to', 'don\'t forget']):
        return "task"

    # Idea signals
    if any(w in text for w in ['what if', 'idea:', 'maybe', 'could we',
                                'experiment', 'try out']):
        return "idea"

    return "unknown"


def parse_note(block, source):
    """Parse a single text block into a vault note dict."""
    lines = block.split("\n")

    meta, remaining = extract_metadata(lines)
    title, body = extract_title_and_body(remaining)

    # Type: explicit metadata > guess
    note_type = meta.get("type", "").lower()
    if note_type not in KNOWN_TYPES:
        note_type = guess_type(title, body)
    if note_type == "unknown":
        note_type = "reference"  # safe default for loose notes

    note = {
        "title": title,
        "type": note_type,
        "body": body,
        "status": "inbox",
        "source": source,
        "route": "claude_code",
        "owner": "marvin",
    }

    # Optional metadata
    if "tags" in meta:
        tags = [t.strip() for t in meta["tags"].split(",") if t.strip()]
        note["tags"] = json.dumps(tags)
    if "due" in meta:
        note["due_date"] = meta["due"]
    if "priority" in meta:
        try:
            note["manual_priority"] = int(meta["priority"])
        except ValueError:
            pass

    return note


def post_note(note, api_url, api_key):
    """POST a note to the vault API. Returns (success, response_text, status_code)."""
    url = f"{api_url}/api/vault/notes"
    data = json.dumps(note).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": api_key,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8")
            return True, body, resp.status
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8") if e.fp else ""
        return False, body, e.code
    except urllib.error.URLError as e:
        return False, str(e.reason), 0
    except Exception as e:
        return False, str(e), 0


def print_note_preview(i, note, total):
    """Print a dry-run preview of a note."""
    print(f"\n{'='*60}")
    print(f"  Note {i}/{total}")
    print(f"  Title:  {note['title']}")
    print(f"  Type:   {note['type']}")
    if note.get("tags"):
        print(f"  Tags:   {note['tags']}")
    if note.get("due_date"):
        print(f"  Due:    {note['due_date']}")
    if note.get("manual_priority"):
        print(f"  Priority: {note['manual_priority']}")
    body_preview = note["body"][:200].replace("\n", " ") if note["body"] else "(no body)"
    print(f"  Body:   {body_preview}")
    if len(note.get("body", "")) > 200:
        print(f"          ... ({len(note['body'])} chars total)")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Batch ingest loose notes into the Jimbo vault.",
        epilog="Separate notes with --- on its own line.",
    )
    parser.add_argument(
        "input",
        help="Path to notes file, or - for stdin",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Actually POST to the vault API (default is dry-run)",
    )
    parser.add_argument(
        "--source",
        default="batch-ingest",
        help="Source label for vault notes (default: batch-ingest)",
    )
    parser.add_argument(
        "--type",
        dest="force_type",
        choices=sorted(KNOWN_TYPES),
        help="Force all notes to this type (overrides guessing)",
    )
    args = parser.parse_args()

    # Read input
    if args.input == "-":
        text = sys.stdin.read()
    else:
        path = Path(args.input)
        if not path.exists():
            print(f"Error: {path} not found", file=sys.stderr)
            sys.exit(1)
        text = path.read_text(encoding="utf-8")

    blocks = parse_blocks(text)
    if not blocks:
        print("No notes found. Separate notes with --- on its own line.")
        sys.exit(0)

    print(f"Found {len(blocks)} note(s)")

    # Parse all notes
    notes = []
    for block in blocks:
        note = parse_note(block, args.source)
        if args.force_type:
            note["type"] = args.force_type
        notes.append(note)

    if not args.live:
        # Dry-run: preview all notes
        print("\n--- DRY RUN (use --live to POST to vault) ---")
        for i, note in enumerate(notes, 1):
            print_note_preview(i, note, len(notes))
        print(f"\n{'='*60}")
        print(f"\nTotal: {len(notes)} notes ready to ingest")
        print(f"Run with --live to POST them to the vault.")
        return

    # Live mode: check env
    api_url = os.environ.get("JIMBO_API_URL")
    api_key = os.environ.get("JIMBO_API_KEY")
    if not api_url or not api_key:
        print("Error: JIMBO_API_URL and JIMBO_API_KEY must be set", file=sys.stderr)
        print("  export JIMBO_API_URL=https://...")
        print("  export JIMBO_API_KEY=...")
        sys.exit(1)

    # POST each note
    success = 0
    failed = 0
    for i, note in enumerate(notes, 1):
        ok, resp_text, status_code = post_note(note, api_url, api_key)
        if ok:
            try:
                resp_data = json.loads(resp_text)
                note_id = resp_data.get("id", "?")
            except (json.JSONDecodeError, KeyError):
                note_id = "?"
            print(f"  [{i}/{len(notes)}] ✓ {note['title'][:50]} (id: {note_id})")
            success += 1
        else:
            print(f"  [{i}/{len(notes)}] ✗ {note['title'][:50]} — HTTP {status_code}: {resp_text[:100]}")
            failed += 1

    print(f"\nDone: {success} ingested, {failed} failed, {len(notes)} total")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
