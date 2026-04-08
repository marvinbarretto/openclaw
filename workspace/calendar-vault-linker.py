#!/usr/bin/env python3
"""
Cross-reference calendar events with vault tasks.

Finds vault tasks/notes that relate to upcoming calendar events by matching
tags, project names, and keywords. Output is included in briefing-input.json.

Python 3.11 stdlib only. No pip dependencies.

Usage:
    python3 calendar-vault-linker.py                  # next 7 days
    python3 calendar-vault-linker.py --days 1          # today only
    python3 calendar-vault-linker.py --json            # JSON output
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone


VAULT_DIR = os.environ.get("VAULT_DIR", "/workspace/vault/notes")

# Words too common to match on
STOP_WORDS = {
    "the", "and", "for", "with", "from", "this", "that", "will", "have",
    "are", "was", "been", "being", "call", "meeting", "check", "review",
    "update", "follow", "discussion", "chat", "sync", "catch", "weekly",
    "daily", "monthly", "time", "date", "today", "tomorrow", "morning",
    "afternoon", "evening", "session", "online", "zoom", "teams", "google",
    "meet", "link", "join", "invite", "calendar", "event", "reminder",
    "sunrise", "sunset", "confirmed", "apr", "mar", "may", "jun", "jul",
    "aug", "sep", "oct", "nov", "dec", "jan", "feb", "2026", "2027",
    "com", "org", "net", "https", "http", "www", "group",
}


def get_calendar_events(days=7):
    """Fetch calendar events via calendar-helper.py. Returns list of event dicts."""
    try:
        result = subprocess.run(
            ["python3", "/workspace/calendar-helper.py", "list-events", "--days", str(days)],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout)
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return data.get("events", data.get("items", []))
    except (subprocess.SubprocessError, json.JSONDecodeError, FileNotFoundError):
        pass

    return []


def extract_keywords(text):
    """Extract meaningful keywords from text."""
    # Remove common calendar noise
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[^\w\s-]", " ", text.lower())
    words = text.split()

    keywords = set()
    for word in words:
        word = word.strip("-")
        if len(word) >= 3 and word not in STOP_WORDS:
            keywords.add(word)

    return keywords


def parse_vault_note(filepath):
    """Parse frontmatter from a vault note."""
    try:
        with open(filepath) as f:
            content = f.read(2000)
    except OSError:
        return None

    if not content.startswith("---"):
        return None

    end = content.find("---", 3)
    if end == -1:
        return None

    meta = {}
    for line in content[3:end].strip().split("\n"):
        if ":" in line:
            key, _, val = line.partition(":")
            meta[key.strip()] = val.strip().strip('"').strip("'")

    meta["_body_preview"] = content[end + 3:][:200].strip()
    meta["_filename"] = os.path.basename(filepath)
    return meta


def find_matching_notes(event_keywords, vault_notes):
    """Find vault notes that match event keywords. Returns scored matches."""
    matches = []

    for note in vault_notes:
        score = 0
        matched_on = []

        title = note.get("title", "").lower()
        tags = note.get("tags", "").strip("[]").lower()
        project = note.get("project", "").lower()
        body = note.get("_body_preview", "").lower()

        note_text = f"{title} {tags} {project} {body}"
        note_words = set(note_text.split())

        for keyword in event_keywords:
            if keyword in title:
                score += 3
                matched_on.append(f"title:{keyword}")
            elif keyword in tags:
                score += 4  # Tag matches are strongest signal
                matched_on.append(f"tag:{keyword}")
            elif keyword in project:
                score += 4
                matched_on.append(f"project:{keyword}")
            elif keyword in note_words:
                score += 1
                matched_on.append(f"body:{keyword}")

        if score >= 4:  # Minimum threshold — tag/project match or multiple word hits
            matches.append({
                "file": note["_filename"],
                "title": note.get("title", note["_filename"]),
                "type": note.get("type", "unknown"),
                "status": note.get("status", "unknown"),
                "priority": note.get("priority", ""),
                "score": score,
                "matched_on": matched_on[:5],
            })

    matches.sort(key=lambda m: m["score"], reverse=True)
    return matches[:3]  # Top 3 per event


def load_vault_notes():
    """Load all vault notes."""
    notes = []
    if not os.path.exists(VAULT_DIR):
        return notes

    for filename in os.listdir(VAULT_DIR):
        if not filename.endswith(".md"):
            continue
        meta = parse_vault_note(os.path.join(VAULT_DIR, filename))
        if meta and meta.get("status") not in ("archived", "done"):
            notes.append(meta)

    return notes


def main():
    args = sys.argv[1:]
    days = 7
    json_output = "--json" in args

    if "--days" in args:
        idx = args.index("--days")
        if idx + 1 < len(args):
            try:
                days = int(args[idx + 1])
            except ValueError:
                pass

    events = get_calendar_events(days)
    if not events:
        if json_output:
            print(json.dumps({"links": [], "status": "no_events"}))
        else:
            print("No calendar events found.")
        return

    # Normalize events — calendar-helper may return nested structures
    normalized = []
    for event in events:
        if isinstance(event, dict):
            e = {"summary": event.get("summary", "")}
            start = event.get("start", "")
            if isinstance(start, dict):
                e["start"] = start.get("dateTime", start.get("date", ""))
            else:
                e["start"] = str(start)
            normalized.append(e)
        elif isinstance(event, str):
            normalized.append({"summary": event, "start": ""})
    events = normalized

    vault_notes = load_vault_notes()
    if not vault_notes:
        if json_output:
            print(json.dumps({"links": [], "status": "no_vault_notes"}))
        else:
            print("No vault notes found.")
        return

    links = []

    for event in events:
        # Handle both dict events and raw text lines
        if isinstance(event, dict):
            summary = event.get("summary", "")
            start = event.get("start", "")
            # Skip events that are just metadata (no real summary)
            if not summary or len(summary) < 3:
                continue
        else:
            summary = str(event)
            start = ""

        keywords = extract_keywords(summary)
        if not keywords or len(keywords) < 2:
            continue

        matches = find_matching_notes(keywords, vault_notes)
        if matches:
            links.append({
                "event": summary,
                "start": start,
                "vault_matches": matches,
            })

    if json_output:
        print(json.dumps({"links": links, "status": "ok", "events_checked": len(events)}, indent=2))
    else:
        if not links:
            print(f"Checked {len(events)} events against {len(vault_notes)} vault notes — no connections found.")
            return

        print(f"Found {len(links)} calendar-vault connections:\n")
        for link in links:
            print(f"📅 {link['event']}")
            if link.get("start"):
                print(f"   {link['start']}")
            for match in link["vault_matches"]:
                print(f"   → [{match['type']}] {match['title']} (score: {match['score']}, matched: {', '.join(match['matched_on'][:3])})")
            print()


if __name__ == "__main__":
    main()
