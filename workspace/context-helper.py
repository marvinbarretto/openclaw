#!/usr/bin/env python3
"""
Context API client for Jimbo's sandbox.

Fetches context data (Priorities, Interests, Goals) from the jimbo-api
and formats it as readable text for Jimbo's context window.

Python 3.11 stdlib only. No pip dependencies.

Usage:
    python3 /workspace/context-helper.py priorities
    python3 /workspace/context-helper.py interests
    python3 /workspace/context-helper.py goals
    python3 /workspace/context-helper.py all
"""

import json
import os
import sys
import urllib.request
import urllib.error


API_URL = os.environ.get("JIMBO_API_URL", "http://localhost:3100")
API_KEY = os.environ.get("JIMBO_API_KEY", os.environ.get("API_KEY", ""))


def fetch_file(slug):
    """Fetch a context file from the API. Returns parsed JSON or None."""
    url = f"{API_URL}/api/context/files/{slug}"
    req = urllib.request.Request(
        url,
        headers={
            "X-API-Key": API_KEY,
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
        sys.stderr.write(f"context-helper.py: failed to fetch {slug}: {e}\n")
        return None


def format_item_meta(item):
    """Format structured metadata fields for a context item."""
    parts = []
    if item.get('status'):
        parts.append(item['status'])
    if item.get('category'):
        parts.append(item['category'])
    if item.get('timeframe'):
        parts.append(item['timeframe'])
    if item.get('expires_at'):
        parts.append(f"expires {item['expires_at']}")
    if parts:
        return f"  [{' | '.join(parts)}]"
    return ''


def format_file(data):
    """Format a context file as readable markdown-like text."""
    lines = [f"# {data['display_name']}", ""]

    for section in data.get("sections", []):
        lines.append(f"## {section['name']}")
        lines.append("")

        for item in section.get("items", []):
            if item.get("label"):
                lines.append(f"- **{item['label']}** — {item['content']}")
            else:
                if section.get("format") == "prose":
                    lines.append(item["content"])
                    lines.append("")
                else:
                    lines.append(f"- {item['content']}")

            meta = format_item_meta(item)
            if meta:
                lines.append(meta)

        lines.append("")

    # Include updated_at so skills can check freshness
    updated_at = data.get("updated_at")
    if updated_at:
        lines.append(f"_Last updated: {updated_at}_")

    return "\n".join(lines).strip()


def main():
    if len(sys.argv) < 2:
        sys.stderr.write("Usage: python3 context-helper.py <slug|all>\n")
        sys.stderr.write("  Slugs: priorities, interests, goals\n")
        sys.exit(1)

    slug = sys.argv[1].lower()

    if not API_KEY:
        sys.stderr.write("context-helper.py: JIMBO_API_KEY or API_KEY not set\n")
        sys.exit(1)

    if slug == "all":
        success_count = 0
        for s in ["priorities", "interests", "goals"]:
            data = fetch_file(s)
            if data:
                print(format_file(data))
                print("\n---\n")
                success_count += 1
            else:
                sys.stderr.write(f"  Skipping {s} — fetch failed\n")
        if success_count == 0:
            sys.stderr.write("context-helper.py: all fetches failed\n")
            sys.exit(1)
    else:
        data = fetch_file(slug)
        if data:
            print(format_file(data))
        else:
            sys.exit(1)


if __name__ == "__main__":
    main()
