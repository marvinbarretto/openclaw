#!/usr/bin/env python3
"""
Google Tasks API client for Jimbo's sandbox.

Fetches tasks from the default "My Tasks" list in Google Tasks, ingests them
into the vault as markdown, and optionally classifies them using Gemini Flash.
Designed to run daily at 05:00 UTC on VPS cron — sweeps anything left on the
list overnight into the vault. Other task lists are ignored. Google Tasks
becomes a daily scratchpad: jot things during the day, anything still there
in the morning gets vaulted and classified.

Python 3.11 stdlib only. Reads credentials from environment variables
(same OAuth credentials as gmail-helper.py / calendar-helper.py).

Environment variables:
    GOOGLE_CALENDAR_CLIENT_ID      — OAuth client ID
    GOOGLE_CALENDAR_CLIENT_SECRET  — OAuth client secret
    GOOGLE_CALENDAR_REFRESH_TOKEN  — OAuth refresh token (with tasks.readonly scope)
    GOOGLE_AI_API_KEY              — Google AI API key (for classify command)

Usage:
    python3 tasks-helper.py fetch                          # dump new tasks since last run (My Tasks only)
    python3 tasks-helper.py fetch --all                    # dump all tasks from My Tasks list
    python3 tasks-helper.py ingest                         # convert fetched tasks to vault markdown
    python3 tasks-helper.py ingest --dry-run               # preview without writing
    python3 tasks-helper.py classify                       # classify inbox items via Gemini Flash
    python3 tasks-helper.py classify --dry-run             # preview classifications
    python3 tasks-helper.py classify --threshold 7         # auto-accept confidence >= 7 (default: 8)
    python3 tasks-helper.py pipeline                       # fetch + ingest + classify in one go
"""

import argparse
import datetime
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

# ---------------------------------------------------------------------------
# Paths — all relative to /workspace/ (sandbox) or script dir (laptop)
# ---------------------------------------------------------------------------

_script_dir = os.path.dirname(os.path.abspath(__file__))
TOKEN_CACHE = os.path.join(_script_dir, ".tasks-access-token.json")
FETCH_OUTPUT = os.path.join(_script_dir, "tasks-fetch.json")
STATE_FILE = os.path.join(_script_dir, ".tasks-last-fetch.json")
VAULT_INBOX = os.path.join(_script_dir, "vault", "inbox")
VAULT_NOTES = os.path.join(_script_dir, "vault", "notes")
VAULT_ARCHIVE = os.path.join(_script_dir, "vault", "archive")
VAULT_NEEDS_CONTEXT = os.path.join(_script_dir, "vault", "needs-context")
TRIAGE_PENDING = os.path.join(_script_dir, "tasks-triage-pending.json")

TASKS_API = "https://tasks.googleapis.com/tasks/v1"
TOKEN_URL = "https://oauth2.googleapis.com/token"
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

URL_RE = re.compile(r'https?://[^\s<>"\')\]]+')

# ---------------------------------------------------------------------------
# Type taxonomy (same as process-inbox.py)
# ---------------------------------------------------------------------------

TYPE_TAXONOMY = """
Assign exactly ONE type from this list:

- bookmark — a saved URL/link to read or reference later
- recipe — food/drink recipe or restaurant/food recommendation
- media — film, TV, music, podcast, YouTube, book recommendation
- travel — destination, deal, flight, accommodation, trip idea
- idea — personal thought, project idea, creative concept
- reference — factual info saved for later (address, phone, how-to, code snippet)
- event — a specific event with a date/time (gig, meetup, match, appointment)
- task — an action item or to-do (may be completed/stale)
- checklist — a list of items (packing list, shopping list, routine)
- person — contact info, someone to remember
- finance — money, budgeting, deals, subscriptions, banking
- health — fitness, nutrition, medical, wellbeing
- quote — a saved quote or passage
- journal — personal reflection, diary entry, mood note
- political — political commentary, article, opinion piece
"""

CLASSIFICATION_PROMPT = """You are classifying a personal note from Google Tasks into a structured vault.

{taxonomy}

Return valid JSON only. No markdown, no explanation. Schema:
{{
  "type": "one of the types above",
  "tags": ["1-5 lowercase tags"],
  "title": "cleaned up title (fix caps, remove URLs, max 80 chars)",
  "status": "active|needs-context|archived",
  "stale_reason": "stale|completed|past-event|empty (required if archived, omit otherwise)",
  "confidence": 8
}}

Rules:
- confidence 1-10. If <= 5, set status to "needs-context".
- Single-item shopping notes older than 1 month: archive as completed.
- Opaque 2-3 word notes where meaning is unclear: needs-context.
- Bare URLs: classify based on content if available, otherwise bookmark.
- Past events or completed tasks: archive.
"""

# ---------------------------------------------------------------------------
# OAuth token management (same pattern as gmail-helper.py)
# ---------------------------------------------------------------------------

def get_env(name):
    val = os.environ.get(name)
    if not val:
        print(f"ERROR: {name} environment variable not set", file=sys.stderr)
        sys.exit(1)
    return val


def log(msg):
    print(msg, file=sys.stderr)


def refresh_access_token(client_id, client_secret, refresh_token):
    """Get a fresh access token, using cache if still valid."""
    if os.path.exists(TOKEN_CACHE):
        try:
            with open(TOKEN_CACHE) as f:
                cached = json.load(f)
            expires_at = cached.get("expires_at", 0)
            if datetime.datetime.now(datetime.timezone.utc).timestamp() < expires_at - 60:
                return cached["access_token"]
        except (json.JSONDecodeError, KeyError):
            pass

    data = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }).encode()

    req = urllib.request.Request(TOKEN_URL, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    try:
        with urllib.request.urlopen(req) as resp:
            tokens = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"ERROR: Token refresh failed ({e.code}): {body}", file=sys.stderr)
        if e.code in (400, 401):
            print("The refresh token may be expired or missing tasks.readonly scope.", file=sys.stderr)
            print("Ask Marvin to re-run google-auth.py.", file=sys.stderr)
        sys.exit(1)

    expires_at = datetime.datetime.now(datetime.timezone.utc).timestamp() + tokens.get("expires_in", 3600)
    cache_data = {
        "access_token": tokens["access_token"],
        "expires_at": expires_at,
    }
    try:
        with open(TOKEN_CACHE, "w") as f:
            json.dump(cache_data, f)
    except OSError:
        pass

    return tokens["access_token"]


# ---------------------------------------------------------------------------
# Tasks API helpers
# ---------------------------------------------------------------------------

def tasks_request(access_token, path):
    """Make an authenticated request to the Google Tasks API."""
    url = f"{TASKS_API}/{path}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {access_token}")

    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"ERROR: Tasks API ({e.code}): {body}", file=sys.stderr)
        sys.exit(1)


def fetch_all_tasks(access_token, tasklist_id, updated_min=None):
    """Fetch tasks from a list, optionally filtering by updated time."""
    all_tasks = []
    page_token = None

    while True:
        path = f"lists/{urllib.parse.quote(tasklist_id)}/tasks?maxResults=100&showCompleted=false&showHidden=false"
        if updated_min:
            path += f"&updatedMin={urllib.parse.quote(updated_min)}"
        if page_token:
            path += f"&pageToken={page_token}"

        result = tasks_request(access_token, path)
        all_tasks.extend(result.get("items", []))

        page_token = result.get("nextPageToken")
        if not page_token:
            break

    return all_tasks


def load_last_fetch_time():
    """Load the timestamp of the last successful fetch."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                state = json.load(f)
            return state.get("last_fetch")
        except (json.JSONDecodeError, KeyError):
            pass
    return None


def save_last_fetch_time():
    """Save the current time as the last fetch time."""
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    try:
        with open(STATE_FILE, "w") as f:
            json.dump({"last_fetch": now}, f)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Vault helpers
# ---------------------------------------------------------------------------

def make_id(source_id):
    """Generate a stable vault ID from the Google Tasks ID."""
    h = hashlib.sha256(f"gtask:{source_id}".encode()).hexdigest()[:8]
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


def file_exists_in_vault(note_id):
    """Check if a note with this ID already exists in any vault directory."""
    for vault_dir in [VAULT_INBOX, VAULT_NOTES, VAULT_ARCHIVE, VAULT_NEEDS_CONTEXT]:
        if not os.path.isdir(vault_dir):
            continue
        for fname in os.listdir(vault_dir):
            if note_id in fname:
                return True
    return False


def extract_urls(text):
    """Pull all URLs from text."""
    return URL_RE.findall(text) if text else []


def build_markdown(task, list_title):
    """Convert a single task dict to markdown string."""
    title = (task.get("title") or "").strip()
    notes = (task.get("notes") or "").strip()
    source_id = task["id"]
    note_id = make_id(source_id)
    status = "inbox" if task.get("status") == "needsAction" else "archived"

    urls = extract_urls(f"{title} {notes}")
    created = (task.get("due") or task.get("updated", ""))[:10]
    updated = (task.get("updated") or "")[:10]

    # Rough pre-classification
    text = f"{title} {notes}".lower()
    title_stripped = URL_RE.sub('', title).strip()
    if urls and len(title_stripped) < 5:
        rough_type = "bookmark"
    elif any(w in text for w in ['recipe', 'tbsp', 'tsp', 'simmer', 'roast', 'bake']):
        rough_type = "recipe"
    else:
        rough_type = "unknown"

    # Build body
    if rough_type == "bookmark" and urls:
        body_title = URL_RE.sub('', title).strip()
        body = body_title if body_title else ""
    else:
        body = title

    if notes:
        body = f"{body}\n\n{notes}" if body else notes

    links_section = ""
    if urls:
        link_lines = "\n".join(f"- {u}" for u in urls)
        links_section = f"\n\n## Links\n{link_lines}"

    now = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d')
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
processed: {now}
title: "{title[:120].replace('"', "'")}"
---"""

    return f"{frontmatter}\n\n{body}{links_section}\n"


# ---------------------------------------------------------------------------
# Gemini Flash classification
# ---------------------------------------------------------------------------

def classify_with_gemini(api_key, note_content, note_filename):
    """Send a note to Gemini Flash for classification. Returns parsed JSON or None."""
    prompt = CLASSIFICATION_PROMPT.format(taxonomy=TYPE_TAXONOMY)
    full_prompt = f"{prompt}\n\n---\nFilename: {note_filename}\n\n{note_content[:3000]}"

    url = GEMINI_API_URL.format(model=GEMINI_MODEL) + f"?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": full_prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 500,
        },
    }

    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
        log(f"  WARNING: Gemini API error for {note_filename}: {e}")
        return None

    try:
        text = result["candidates"][0]["content"]["parts"][0]["text"]
        # Strip markdown code fences if present
        text = re.sub(r'^```(?:json)?\s*', '', text.strip())
        text = re.sub(r'\s*```$', '', text.strip())
        return json.loads(text)
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        log(f"  WARNING: Could not parse Gemini response for {note_filename}: {e}")
        return None


def parse_frontmatter(content):
    """Parse YAML frontmatter from markdown content."""
    match = re.match(r'^---\n(.*?)\n---\n?(.*)', content, re.DOTALL)
    if not match:
        return None, content

    yaml_text = match.group(1)
    body = match.group(2)

    fm = {}
    for line in yaml_text.split('\n'):
        m = re.match(r'^(\w[\w-]*)\s*:\s*(.*)', line)
        if m:
            key = m.group(1)
            val = m.group(2).strip()
            if val.startswith('['):
                try:
                    fm[key] = json.loads(val)
                except json.JSONDecodeError:
                    fm[key] = val
            elif val.startswith('"') and val.endswith('"'):
                fm[key] = val[1:-1]
            else:
                fm[key] = val
    return fm, body


def build_frontmatter(fm):
    """Serialize a frontmatter dict back to YAML string."""
    lines = ['---']
    key_order = [
        'id', 'source', 'source_id', 'source_list', 'type', 'status',
        'tags', 'created', 'updated', 'processed', 'title', 'confidence',
        'stale_reason', 'priority', 'priority_reason', 'actionability',
        'scored', 'suggested_status',
    ]
    written = set()
    for key in key_order:
        if key in fm:
            lines.append(_format_fm_line(key, fm[key]))
            written.add(key)
    for key in fm:
        if key not in written:
            lines.append(_format_fm_line(key, fm[key]))
    lines.append('---')
    return '\n'.join(lines)


def _format_fm_line(key, val):
    """Format a single frontmatter key-value line."""
    if isinstance(val, list):
        return f'{key}: {json.dumps(val)}'
    elif isinstance(val, str) and ('"' in val or ':' in val or val != val.strip()
                                    or val.startswith('[') or val.startswith('{')
                                    or val == '' or val in ('true', 'false', 'null')):
        return f'{key}: "{val}"'
    else:
        return f'{key}: {val}'


# ---------------------------------------------------------------------------
# Triage pending file
# ---------------------------------------------------------------------------

def _write_triage_pending(triage_items, total_classified, stats):
    """Write tasks-triage-pending.json for items that landed in needs-context."""
    if not triage_items:
        # No ambiguous items this run — remove stale file if it exists
        if os.path.exists(TRIAGE_PENDING):
            os.remove(TRIAGE_PENDING)
        return

    today = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d')
    pending = {
        "sweep_date": today,
        "total_classified": total_classified,
        "classified_ok": stats["notes"] + stats["archived"],
        "needs_triage": len(triage_items),
        "items": triage_items,
    }

    try:
        with open(TRIAGE_PENDING, "w") as f:
            json.dump(pending, f, indent=2)
        log(f"Wrote {TRIAGE_PENDING} with {len(triage_items)} items for triage")
    except OSError as e:
        log(f"WARNING: Could not write triage pending file: {e}")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_fetch(access_token, args):
    """Fetch tasks from Google Tasks API."""
    updated_min = None
    if not args.all:
        updated_min = load_last_fetch_time()
        if updated_min:
            log(f"Fetching tasks updated since {updated_min}")
        else:
            log("No previous fetch found — fetching all open tasks")

    # Only fetch from the default "My Tasks" list — other lists are ignored.
    # Google Tasks API uses the magic ID "@default" for the primary list.
    # This keeps Google Tasks as a daily scratchpad: anything left overnight
    # gets swept into the vault each morning.
    log("Fetching from My Tasks (default list only)...")

    output = {
        "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "incremental": updated_min is not None,
        "updated_min": updated_min,
        "lists": [],
    }

    tasks = fetch_all_tasks(access_token, "@default", updated_min=updated_min)
    log(f"  My Tasks: {len(tasks)} tasks")
    total_tasks = len(tasks)

    output["lists"].append({
        "id": "@default",
        "title": "My Tasks",
        "tasks": tasks,
    })

    output["total_tasks"] = total_tasks

    with open(FETCH_OUTPUT, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    save_last_fetch_time()

    log(f"Total: {total_tasks} tasks fetched")
    log(f"Written to {FETCH_OUTPUT}")
    print(json.dumps({"status": "ok", "total": total_tasks, "output": FETCH_OUTPUT}))


def cmd_ingest(args):
    """Convert fetched tasks to vault markdown files."""
    if not os.path.exists(FETCH_OUTPUT):
        log(f"ERROR: {FETCH_OUTPUT} not found. Run 'fetch' first.")
        sys.exit(1)

    with open(FETCH_OUTPUT) as f:
        data = json.load(f)

    if not args.dry_run:
        os.makedirs(VAULT_INBOX, exist_ok=True)
        os.makedirs(VAULT_ARCHIVE, exist_ok=True)

    stats = {"inbox": 0, "archived": 0, "skipped_empty": 0, "skipped_exists": 0}

    for task_list in data["lists"]:
        list_title = task_list["title"]

        for task in task_list["tasks"]:
            title = (task.get("title") or "").strip()

            if not title and not task.get("notes"):
                stats["skipped_empty"] += 1
                continue

            note_id = make_id(task["id"])

            # Skip if already in vault
            if file_exists_in_vault(note_id):
                stats["skipped_exists"] += 1
                continue

            md = build_markdown(task, list_title)
            filename = sanitise_filename(title, note_id)
            is_completed = task.get("status") == "completed"

            if is_completed:
                dest = os.path.join(VAULT_ARCHIVE, filename)
                stats["archived"] += 1
            else:
                dest = os.path.join(VAULT_INBOX, filename)
                stats["inbox"] += 1

            if args.dry_run:
                if stats["inbox"] + stats["archived"] <= 5:
                    log(f"--- {filename} ---")
                    log(md[:500])
                    log("")
            else:
                with open(dest, "w", encoding="utf-8") as f:
                    f.write(md)

    log(f"Inbox: {stats['inbox']}, Archived: {stats['archived']}, "
        f"Skipped empty: {stats['skipped_empty']}, "
        f"Already exists: {stats['skipped_exists']}")

    if args.dry_run:
        log("(Dry run — no files written)")

    print(json.dumps({"status": "ok", **stats}))


def cmd_classify(args):
    """Classify inbox items using Gemini Flash."""
    api_key = get_env("GOOGLE_AI_API_KEY")
    threshold = args.threshold

    if not os.path.isdir(VAULT_INBOX):
        log(f"No inbox directory at {VAULT_INBOX}")
        print(json.dumps({"status": "ok", "classified": 0}))
        return

    files = sorted(f for f in os.listdir(VAULT_INBOX) if f.endswith(".md"))
    if not files:
        log("Inbox is empty — nothing to classify")
        print(json.dumps({"status": "ok", "classified": 0}))
        return

    if args.limit:
        files = files[:args.limit]

    log(f"Classifying {len(files)} inbox items (threshold: {threshold})...")

    if not args.dry_run:
        os.makedirs(VAULT_NOTES, exist_ok=True)
        os.makedirs(VAULT_ARCHIVE, exist_ok=True)
        os.makedirs(VAULT_NEEDS_CONTEXT, exist_ok=True)

    stats = {"notes": 0, "archived": 0, "needs_context": 0, "failed": 0, "queued": 0}
    triage_items = []  # track items routed to needs-context this run

    for i, fname in enumerate(files):
        filepath = os.path.join(VAULT_INBOX, fname)
        with open(filepath, encoding="utf-8") as f:
            content = f.read()

        if (i + 1) % 10 == 0:
            log(f"  Processing {i + 1}/{len(files)}...")

        result = classify_with_gemini(api_key, content, fname)
        if result is None:
            stats["failed"] += 1
            continue

        confidence = result.get("confidence", 0)
        status = result.get("status", "needs-context")

        # Override: low confidence → needs-context
        if confidence <= 5:
            status = "needs-context"

        # Determine destination
        if status == "archived":
            dest_dir = VAULT_ARCHIVE
            stats["archived"] += 1
        elif status == "needs-context":
            dest_dir = VAULT_NEEDS_CONTEXT
            stats["needs_context"] += 1
            # Track for triage pending file
            fm_parsed, _ = parse_frontmatter(content)
            raw_title = fm_parsed.get("title", fname) if fm_parsed else fname
            triage_items.append({
                "filename": fname,
                "raw_title": raw_title,
                "suggested_type": result.get("type", "unknown"),
                "suggested_tags": result.get("tags", []),
                "confidence": confidence,
            })
        elif confidence >= threshold:
            dest_dir = VAULT_NOTES
            stats["notes"] += 1
        else:
            # Below threshold but not needs-context — queue for manual review
            stats["queued"] += 1
            continue

        # Update frontmatter
        fm, body = parse_frontmatter(content)
        if fm:
            fm["type"] = result.get("type", fm.get("type", "unknown"))
            fm["tags"] = result.get("tags", fm.get("tags", []))
            fm["title"] = result.get("title", fm.get("title", ""))
            fm["status"] = status
            fm["confidence"] = confidence
            if result.get("stale_reason"):
                fm["stale_reason"] = result["stale_reason"]
            updated_content = build_frontmatter(fm) + '\n' + body
        else:
            updated_content = content

        if args.dry_run:
            log(f"  {fname} → {status} (confidence: {confidence}, type: {result.get('type')})")
        else:
            # Write to destination
            dest_path = os.path.join(dest_dir, fname)
            with open(dest_path, "w", encoding="utf-8") as f:
                f.write(updated_content)
            # Remove from inbox
            os.remove(filepath)

    log(f"Notes: {stats['notes']}, Archived: {stats['archived']}, "
        f"Needs context: {stats['needs_context']}, Queued: {stats['queued']}, "
        f"Failed: {stats['failed']}")

    if args.dry_run:
        log("(Dry run — no files moved)")
    else:
        # Write triage pending file for items that need Marvin's input
        _write_triage_pending(triage_items, len(files), stats)

    print(json.dumps({"status": "ok", **stats}))


def cmd_pipeline(access_token, args):
    """Run the full pipeline: fetch → ingest → classify."""
    log("=== Step 1: Fetch ===")
    cmd_fetch(access_token, args)

    log("")
    log("=== Step 2: Ingest ===")
    cmd_ingest(args)

    log("")
    log("=== Step 3: Classify ===")
    cmd_classify(args)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Google Tasks helper for Jimbo's vault")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # fetch
    fetch_parser = subparsers.add_parser("fetch", help="Fetch tasks from Google Tasks API")
    fetch_parser.add_argument("--all", action="store_true", help="Fetch all tasks, not just since last run")

    # ingest
    ingest_parser = subparsers.add_parser("ingest", help="Convert fetched tasks to vault markdown")
    ingest_parser.add_argument("--dry-run", action="store_true", help="Preview without writing files")

    # classify
    classify_parser = subparsers.add_parser("classify", help="Classify inbox items via Gemini Flash")
    classify_parser.add_argument("--dry-run", action="store_true", help="Preview without moving files")
    classify_parser.add_argument("--threshold", type=int, default=8, help="Auto-accept confidence threshold (default: 8)")
    classify_parser.add_argument("--limit", type=int, default=None, help="Max items to classify")

    # pipeline (fetch + ingest + classify)
    pipeline_parser = subparsers.add_parser("pipeline", help="Run full pipeline: fetch + ingest + classify")
    pipeline_parser.add_argument("--all", action="store_true", help="Fetch all tasks, not just since last run")
    pipeline_parser.add_argument("--dry-run", action="store_true", help="Preview without writing/moving files")
    pipeline_parser.add_argument("--threshold", type=int, default=8, help="Auto-accept confidence threshold (default: 8)")
    pipeline_parser.add_argument("--limit", type=int, default=None, help="Max items to classify")

    args = parser.parse_args()

    # Get credentials from env
    client_id = get_env("GOOGLE_CALENDAR_CLIENT_ID")
    client_secret = get_env("GOOGLE_CALENDAR_CLIENT_SECRET")
    refresh_token = get_env("GOOGLE_CALENDAR_REFRESH_TOKEN")

    access_token = refresh_access_token(client_id, client_secret, refresh_token)

    if args.command == "fetch":
        cmd_fetch(access_token, args)
    elif args.command == "ingest":
        cmd_ingest(args)
    elif args.command == "classify":
        cmd_classify(args)
    elif args.command == "pipeline":
        cmd_pipeline(access_token, args)


if __name__ == "__main__":
    main()
