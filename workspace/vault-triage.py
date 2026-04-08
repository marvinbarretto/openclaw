#!/usr/bin/env python3
"""
Autonomous vault inbox triage and stale note cleanup.

Runs daily (04:00 UTC) to:
1. Auto-classify obvious inbox items (URLs → bookmark, lists → checklist)
2. Archive stale inbox items (>30 days, no tags, no project)
3. Mark clearly-done tasks as done
4. Report actions via Telegram Bot API

Python 3.11 stdlib only. No pip dependencies.

Usage:
    python3 vault-triage.py                    # dry-run (default)
    python3 vault-triage.py --live             # apply changes
    python3 vault-triage.py --live --quiet     # apply without Telegram report
    python3 vault-triage.py stats              # show vault statistics
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone


VAULT_DIR = os.environ.get("VAULT_DIR", "/workspace/vault")
NOTES_DIR = os.path.join(VAULT_DIR, "notes")
INBOX_DIR = os.path.join(VAULT_DIR, "inbox")
ARCHIVE_DIR = os.path.join(VAULT_DIR, "archive")
JIMBO_API_URL = os.environ.get("JIMBO_API_URL", "")
JIMBO_API_KEY = os.environ.get("JIMBO_API_KEY", "")

STALE_DAYS = 30
URL_PATTERN = re.compile(r"^https?://\S+$")
CHECKLIST_PATTERN = re.compile(r"^(\s*[-*]\s|\s*\d+[.)]\s)", re.MULTILINE)
DONE_MARKERS = re.compile(r"\b(done|completed|finished|shipped|merged|deployed|cancelled|canceled)\b", re.IGNORECASE)


def parse_frontmatter(filepath):
    """Parse YAML frontmatter from a markdown file. Returns (meta_dict, body, raw_content)."""
    try:
        with open(filepath) as f:
            content = f.read()
    except OSError:
        return None, "", ""

    if not content.startswith("---"):
        return {}, content, content

    end = content.find("---", 3)
    if end == -1:
        return {}, content, content

    frontmatter = content[3:end]
    body = content[end + 3:].strip()

    meta = {}
    for line in frontmatter.strip().split("\n"):
        if ":" in line:
            key, _, val = line.partition(":")
            meta[key.strip()] = val.strip().strip('"').strip("'")

    return meta, body, content


def update_frontmatter(filepath, updates):
    """Update specific frontmatter fields in a file."""
    with open(filepath) as f:
        content = f.read()

    if not content.startswith("---"):
        return False

    end = content.find("---", 3)
    if end == -1:
        return False

    lines = content[3:end].strip().split("\n")
    body = content[end + 3:]

    updated_keys = set()
    new_lines = []
    for line in lines:
        if ":" in line:
            key = line.partition(":")[0].strip()
            if key in updates:
                new_lines.append(f"{key}: {updates[key]}")
                updated_keys.add(key)
                continue
        new_lines.append(line)

    # Add any new keys not already in frontmatter
    for key, val in updates.items():
        if key not in updated_keys:
            new_lines.append(f"{key}: {val}")

    new_content = "---\n" + "\n".join(new_lines) + "\n---" + body

    with open(filepath, "w") as f:
        f.write(new_content)
    return True


def move_file(filepath, dest_dir):
    """Move a file to destination directory."""
    os.makedirs(dest_dir, exist_ok=True)
    filename = os.path.basename(filepath)
    dest = os.path.join(dest_dir, filename)
    # Handle name collision
    if os.path.exists(dest):
        base, ext = os.path.splitext(filename)
        dest = os.path.join(dest_dir, f"{base}-{int(time.time())}{ext}")
    os.rename(filepath, dest)
    return dest


def classify_inbox_item(meta, body, filename):
    """Attempt to auto-classify an inbox item. Returns (new_type, reason) or (None, None)."""
    title = meta.get("title", filename)
    content = f"{title}\n{body}".strip()

    # URL-only content → bookmark
    lines = [l.strip() for l in content.split("\n") if l.strip()]
    if len(lines) <= 3 and any(URL_PATTERN.match(l) for l in lines):
        return "bookmark", "content is primarily a URL"

    # Checklist pattern → checklist
    matches = CHECKLIST_PATTERN.findall(body)
    if len(matches) >= 3:
        return "checklist", f"contains {len(matches)} list items"

    return None, None


def check_stale_inbox(meta, filepath):
    """Check if an inbox item is stale enough to auto-archive."""
    # Must have no tags and no project
    tags = meta.get("tags", "").strip("[]")
    if tags and tags != "":
        return False, ""

    if meta.get("project", ""):
        return False, ""

    # Check file age
    try:
        created = meta.get("created_at", "")
        if created:
            # Try parsing ISO date
            created_date = datetime.fromisoformat(created.replace("Z", "+00:00"))
        else:
            # Fall back to file mtime
            mtime = os.path.getmtime(filepath)
            created_date = datetime.fromtimestamp(mtime, tz=timezone.utc)

        age_days = (datetime.now(timezone.utc) - created_date).days
        if age_days >= STALE_DAYS:
            return True, f"stale ({age_days} days old, no tags, no project)"
    except (ValueError, OSError):
        pass

    return False, ""


def check_done_task(meta, body):
    """Check if a task appears to be done."""
    if meta.get("type") != "task":
        return False, ""

    title = meta.get("title", "")
    # Check title and first few lines for done markers
    check_text = f"{title}\n{body[:500]}"
    if DONE_MARKERS.search(check_text):
        return True, "title/body contains done marker"

    return False, ""


def send_telegram_report(actions):
    """Send a summary of triage actions via Telegram Bot API."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return

    classified = [a for a in actions if a["action"] == "classify"]
    archived = [a for a in actions if a["action"] == "archive"]
    done = [a for a in actions if a["action"] == "mark_done"]

    if not actions:
        return

    parts = ["📋 <b>Vault Triage Report</b>"]

    if classified:
        parts.append(f"\n<b>Auto-classified ({len(classified)}):</b>")
        for a in classified[:5]:
            parts.append(f"  • {a['title'][:40]} → {a['new_type']}")
        if len(classified) > 5:
            parts.append(f"  ... and {len(classified) - 5} more")

    if archived:
        parts.append(f"\n<b>Auto-archived ({len(archived)}):</b>")
        for a in archived[:5]:
            parts.append(f"  • {a['title'][:40]} ({a['reason']})")
        if len(archived) > 5:
            parts.append(f"  ... and {len(archived) - 5} more")

    if done:
        parts.append(f"\n<b>Marked done ({len(done)}):</b>")
        for a in done[:5]:
            parts.append(f"  • {a['title'][:40]}")

    text = "\n".join(parts)
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
    }).encode()

    try:
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=data,
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
    except (urllib.error.URLError, OSError) as e:
        sys.stderr.write(f"Telegram send failed: {e}\n")


def triage_inbox(live=False):
    """Process inbox items for auto-classification and stale archival."""
    if not os.path.exists(INBOX_DIR):
        print(f"Inbox dir not found: {INBOX_DIR}")
        return []

    actions = []

    for filename in sorted(os.listdir(INBOX_DIR)):
        if not filename.endswith(".md"):
            continue

        filepath = os.path.join(INBOX_DIR, filename)
        meta, body, raw = parse_frontmatter(filepath)
        if meta is None:
            continue

        title = meta.get("title", filename.replace(".md", "").replace("-", " "))

        # Try auto-classification
        new_type, reason = classify_inbox_item(meta, body, filename)
        if new_type:
            action = {
                "action": "classify",
                "file": filename,
                "title": title,
                "new_type": new_type,
                "reason": reason,
            }
            actions.append(action)
            if live:
                update_frontmatter(filepath, {"type": new_type, "status": "notes"})
                move_file(filepath, NOTES_DIR)
            print(f"  CLASSIFY {filename} → {new_type} ({reason})")
            continue

        # Check for stale
        is_stale, stale_reason = check_stale_inbox(meta, filepath)
        if is_stale:
            action = {
                "action": "archive",
                "file": filename,
                "title": title,
                "reason": stale_reason,
            }
            actions.append(action)
            if live:
                update_frontmatter(filepath, {"status": "archived"})
                move_file(filepath, ARCHIVE_DIR)
            print(f"  ARCHIVE {filename} ({stale_reason})")

    return actions


def triage_active(live=False):
    """Check active notes for done tasks."""
    if not os.path.exists(NOTES_DIR):
        return []

    actions = []

    for filename in sorted(os.listdir(NOTES_DIR)):
        if not filename.endswith(".md"):
            continue

        filepath = os.path.join(NOTES_DIR, filename)
        meta, body, raw = parse_frontmatter(filepath)
        if meta is None:
            continue

        title = meta.get("title", filename)

        is_done, reason = check_done_task(meta, body)
        if is_done:
            action = {
                "action": "mark_done",
                "file": filename,
                "title": title,
                "reason": reason,
            }
            actions.append(action)
            if live:
                update_frontmatter(filepath, {"status": "done"})
                move_file(filepath, ARCHIVE_DIR)
            print(f"  DONE {filename} ({reason})")

    return actions


def show_stats():
    """Show vault statistics."""
    dirs = {
        "notes": NOTES_DIR,
        "inbox": INBOX_DIR,
        "archive": ARCHIVE_DIR,
    }

    print("Vault Statistics:")
    for name, path in dirs.items():
        if os.path.exists(path):
            count = len([f for f in os.listdir(path) if f.endswith(".md")])
            print(f"  {name}: {count} files")
        else:
            print(f"  {name}: (not found)")

    # Type breakdown for active notes
    if os.path.exists(NOTES_DIR):
        types = {}
        for filename in os.listdir(NOTES_DIR):
            if not filename.endswith(".md"):
                continue
            meta, _, _ = parse_frontmatter(os.path.join(NOTES_DIR, filename))
            if meta:
                t = meta.get("type", "unknown")
                types[t] = types.get(t, 0) + 1

        print("\n  Type breakdown (notes):")
        for t, count in sorted(types.items(), key=lambda x: -x[1]):
            print(f"    {t}: {count}")


def main():
    args = sys.argv[1:]

    if "stats" in args:
        show_stats()
        return

    live = "--live" in args
    quiet = "--quiet" in args

    mode = "LIVE" if live else "DRY-RUN"
    print(f"Vault triage ({mode})")
    print()

    print("Inbox triage:")
    inbox_actions = triage_inbox(live=live)
    if not inbox_actions:
        print("  (no actions needed)")

    print()
    print("Active notes check:")
    active_actions = triage_active(live=live)
    if not active_actions:
        print("  (no actions needed)")

    all_actions = inbox_actions + active_actions

    print(f"\nTotal: {len(all_actions)} actions")

    if live and all_actions and not quiet:
        send_telegram_report(all_actions)

    # Output JSON for piping
    if "--json" in args:
        print(json.dumps(all_actions, indent=2))


if __name__ == "__main__":
    main()
