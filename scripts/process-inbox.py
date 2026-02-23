#!/usr/bin/env python3
"""
LLM batch processor for vault inbox items.

Reads markdown files from data/vault/inbox/, sends each to Claude Haiku
for classification, updates frontmatter, and moves files to:
  - data/vault/notes/       — classified, active notes
  - data/vault/needs-context/ — ambiguous items LLM couldn't classify
  - data/vault/archive/     — stale, dead, or completed items

Python 3.11 stdlib only. No pip dependencies.

Environment variables:
    ANTHROPIC_API_KEY — Anthropic API key

Usage:
    python3 scripts/process-inbox.py                       # process all
    python3 scripts/process-inbox.py --wave 1              # labelled items only
    python3 scripts/process-inbox.py --limit 20            # first 20
    python3 scripts/process-inbox.py --dry-run             # show output, don't move
    python3 scripts/process-inbox.py --dry-run --limit 5   # quick test
"""

import argparse
import datetime
import html.parser
import json
import os
import re
import shutil
import ssl
import sys
import time
import urllib.error
import urllib.request

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
INBOX_DIR = os.path.join(REPO_ROOT, "data", "vault", "inbox")
NOTES_DIR = os.path.join(REPO_ROOT, "data", "vault", "notes")
NEEDS_CONTEXT_DIR = os.path.join(REPO_ROOT, "data", "vault", "needs-context")
ARCHIVE_DIR = os.path.join(REPO_ROOT, "data", "vault", "archive")

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"

OLLAMA_API_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")

# ---------------------------------------------------------------------------
# Context files (baked in at import time would be too large — read at runtime)
# ---------------------------------------------------------------------------

CONTEXT_FILES = [
    os.path.join(REPO_ROOT, "context", "INTERESTS.md"),
    os.path.join(REPO_ROOT, "context", "PRIORITIES.md"),
    os.path.join(REPO_ROOT, "context", "TASTE.md"),
    os.path.join(REPO_ROOT, "context", "GOALS.md"),
    os.path.join(REPO_ROOT, "context", "PATTERNS.md"),
]

# ---------------------------------------------------------------------------
# Type taxonomy for the LLM
# ---------------------------------------------------------------------------

TYPE_TAXONOMY = """
## Type taxonomy

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
- person — contact info, someone to remember, a recommendation about a person
- finance — money, budgeting, deals, subscriptions, banking
- health — fitness, nutrition, medical, wellbeing
- quote — a saved quote or passage
- journal — personal reflection, diary entry, mood note
- political — political commentary, article, opinion piece
"""

CLASSIFICATION_RULES = """
## Classification rules

1. Return valid JSON only. No markdown, no explanation.
2. `type` must be exactly one value from the taxonomy above.
3. `tags` — 1 to 5 lowercase tags. Be specific (e.g. "watford-fc" not "football", "angular" not "tech").
4. `title` — clean up the title. Fix capitalisation, remove URLs, truncate if over 80 chars. Keep it descriptive.
5. `status` — one of:
   - "active" — still relevant, worth keeping
   - "needs-context" — genuinely ambiguous, can't classify without more info
   - "archived" — stale, completed, dead URL, past event, or no longer relevant
6. `stale_reason` — required if status is "archived". One of:
   - "stale" — too old to be relevant
   - "dead-url" — URL is dead/broken (I'll tell you if it is)
   - "completed" — task/action that's clearly done
   - "duplicate" — appears to be a duplicate
   - "past-event" — event that has already happened
   - "empty" — no meaningful content
7. If the note has a created date older than 2 years and refers to a specific event or time-sensitive item, it's likely stale.
8. If a URL is reported as dead (404/timeout), lean towards archiving unless the text content is valuable on its own.
9. Bare URLs with no context: if the URL is dead, archive. If alive, classify based on the page title.
10. `confidence` — required. A number from 1-10 indicating how confident you are in your classification. Be honest.
11. If your confidence is 5 or below, set status to "needs-context". It is better to flag something for manual review than to guess wrong.
12. Recurring nudges/habit triggers (e.g. "plan the week", recipes with ratings like "9/10", questions like "any bargains?") should be archived as stale — these are converted Google Keep recurring notes, not real tasks.
13. Opaque 2-3 word notes older than 3 months where the meaning is unclear should be set to "needs-context" — don't guess.
14. URLs to event listing sites (filmclub, fane.co.uk, dice, etc.) are likely project:localshout tasks — sources of events to integrate, not passive bookmarks.
15. Notes with just a person's name are usually contact tasks ("reach out to X"), not passive person records. Tag with person:<name>.
16. Notes that look like prompts for an AI conversation ("interview me about", "help me work through") are project:openclaw tasks or completed items.
17. "Shape Up" is a Basecamp product development book, not a fitness book. Be wary of short titles that sound like one domain but belong to another.
18. Bare Twitter/X URLs without fetched content MUST go to needs-context — do NOT guess the topic.
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_env(name):
    """Get a required environment variable or exit."""
    val = os.environ.get(name)
    if not val:
        print(f"ERROR: {name} environment variable not set", file=sys.stderr)
        sys.exit(1)
    return val


def log(msg):
    """Print to stderr for progress logging."""
    print(msg, file=sys.stderr)


# ---------------------------------------------------------------------------
# Frontmatter parsing
# ---------------------------------------------------------------------------

def parse_frontmatter(content):
    """Parse YAML frontmatter from markdown content.

    Returns (frontmatter_dict, body) or (None, content) if no frontmatter.
    """
    match = re.match(r'^---\n(.*?)\n---\n?(.*)', content, re.DOTALL)
    if not match:
        return None, content

    yaml_text = match.group(1)
    body = match.group(2)

    # Simple YAML parser — handles our flat frontmatter format
    fm = {}
    for line in yaml_text.split('\n'):
        # Match key: value pairs
        m = re.match(r'^(\w[\w-]*)\s*:\s*(.*)', line)
        if m:
            key = m.group(1)
            val = m.group(2).strip()
            # Parse arrays
            if val.startswith('['):
                try:
                    fm[key] = json.loads(val)
                except json.JSONDecodeError:
                    fm[key] = val
            # Parse quoted strings
            elif val.startswith('"') and val.endswith('"'):
                fm[key] = val[1:-1]
            else:
                fm[key] = val
    return fm, body


def build_frontmatter(fm):
    """Serialize a frontmatter dict back to YAML string."""
    lines = ['---']
    # Preserve a sensible key order
    key_order = [
        'id', 'source', 'source_id', 'source_list', 'type', 'status',
        'tags', 'created', 'updated', 'processed', 'title', 'stale_reason',
    ]
    written = set()
    for key in key_order:
        if key in fm:
            lines.append(_format_fm_line(key, fm[key]))
            written.add(key)
    # Any remaining keys
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


def update_frontmatter(content, updates):
    """Update frontmatter fields in markdown content. Returns new content."""
    fm, body = parse_frontmatter(content)
    if fm is None:
        return content
    fm.update(updates)
    return build_frontmatter(fm) + '\n' + body


# ---------------------------------------------------------------------------
# URL title fetching
# ---------------------------------------------------------------------------

class TitleExtractor(html.parser.HTMLParser):
    """Extract <title> from HTML."""
    def __init__(self):
        super().__init__()
        self._in_title = False
        self._title = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == 'title':
            self._in_title = True

    def handle_endtag(self, tag):
        if tag.lower() == 'title':
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self._title.append(data)

    def get_title(self):
        return ' '.join(self._title).strip()


def fetch_url_title(url, timeout=5):
    """Fetch a URL and extract its <title>. Returns (title, is_dead).

    title is None if we couldn't extract one.
    is_dead is True if the URL returned an error or timed out.
    """
    # Skip non-HTTP URLs
    if not url.startswith(('http://', 'https://')):
        return None, False

    # Skip known dead domains
    dead_domains = ['twitter.com', 'x.com']  # Often block scraping
    try:
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.lower()
        # Don't mark twitter as dead — just skip title fetch
        if any(d in domain for d in dead_domains):
            return None, False
    except Exception:
        pass

    # Create SSL context that doesn't verify (some sites have bad certs)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(url)
    req.add_header('User-Agent', 'Mozilla/5.0 (compatible; bot)')

    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            # Only parse HTML
            content_type = resp.headers.get('Content-Type', '')
            if 'html' not in content_type.lower():
                return None, False
            # Read first 32KB only
            data = resp.read(32768)
            text = data.decode('utf-8', errors='replace')
            parser = TitleExtractor()
            parser.feed(text)
            title = parser.get_title()
            return (title if title else None), False
    except urllib.error.HTTPError as e:
        if e.code in (404, 410, 403):
            return None, True
        return None, False
    except (urllib.error.URLError, OSError, TimeoutError):
        return None, True
    except Exception:
        return None, False


def extract_urls(text):
    """Extract URLs from text."""
    return re.findall(r'https?://[^\s<>"\')\]]+', text)


# ---------------------------------------------------------------------------
# LLM classification
# ---------------------------------------------------------------------------

def load_context():
    """Load Marvin's context files for the system prompt."""
    sections = []
    for path in CONTEXT_FILES:
        if os.path.exists(path):
            with open(path) as f:
                sections.append(f.read().strip())
    return '\n\n---\n\n'.join(sections)


def build_system_prompt(context):
    """Build the system prompt for classification."""
    return f"""You are a note classifier for Marvin's personal knowledge base.

You will receive a note (from Google Tasks or Google Keep) with its metadata.
Your job is to classify it with a type, tags, cleaned title, and status.

## Marvin's context (use this to judge relevance and staleness)

{context}

{TYPE_TAXONOMY}

{CLASSIFICATION_RULES}

## Response format

Return ONLY valid JSON:
{{
  "type": "bookmark",
  "tags": ["tag1", "tag2"],
  "title": "Clean descriptive title",
  "status": "active",
  "stale_reason": null,
  "confidence": 8
}}
"""


def build_user_message(fm, body, url_info=None):
    """Build the user message for a single note."""
    parts = []

    # Metadata
    parts.append(f"Source: {fm.get('source', 'unknown')}")
    if fm.get('source_list'):
        parts.append(f"Source list: {fm['source_list']}")
    parts.append(f"Created: {fm.get('created', 'unknown')}")
    if fm.get('type') and fm['type'] != 'unknown':
        parts.append(f"Pre-classified type: {fm['type']}")

    # URL info if we fetched titles
    if url_info:
        for url, title, is_dead in url_info:
            if is_dead:
                parts.append(f"URL (DEAD): {url}")
            elif title:
                parts.append(f"URL title: {title} ({url})")

    parts.append(f"\nTitle: {fm.get('title', '(none)')}")
    parts.append(f"\nContent:\n{body.strip()}")

    return '\n'.join(parts)


def call_ollama(system_prompt, user_message):
    """Call Ollama chat API. Returns parsed JSON response or None."""
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "stream": False,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "options": {"temperature": 0.1},
    }).encode()

    req = urllib.request.Request(OLLAMA_API_URL, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode())
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        log(f"  Ollama error: {e}")
        return None

    text = result.get("message", {}).get("content", "")
    return _parse_llm_json(text)


def call_llm(api_key, system_prompt, user_message):
    """Call Anthropic Messages API. Returns parsed JSON response or None."""
    payload = json.dumps({
        "model": ANTHROPIC_MODEL,
        "max_tokens": 256,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_message}],
    }).encode()

    req = urllib.request.Request(ANTHROPIC_API_URL, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("x-api-key", api_key)
    req.add_header("anthropic-version", "2023-06-01")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        log(f"  API error ({e.code}): {body[:200]}")
        return None
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        log(f"  API connection error: {e}")
        return None

    # Extract text from Anthropic response
    text = ""
    for block in result.get("content", []):
        if block.get("type") == "text":
            text += block["text"]

    return _parse_llm_json(text)


def _parse_llm_json(text):
    """Parse JSON from LLM response — handle markdown fences and trailing commentary."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r'^```\w*\n?', '', text)
        text = re.sub(r'\n?```.*', '', text, flags=re.DOTALL)
        text = text.strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Extract first JSON object if LLM added commentary around it
    match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    log(f"  Failed to parse LLM response: {text[:200]}")
    return None


# ---------------------------------------------------------------------------
# Wave filtering
# ---------------------------------------------------------------------------

ACTIVE_LISTS = {"Today", "Immediate", "Follow up", "Follow up / research"}


def get_wave(fm):
    """Determine which wave a note belongs to.

    Wave 1: items with existing non-empty tags
    Wave 2: items from active lists (Today, Immediate, Follow up)
    Wave 3: items with type=bookmark
    Wave 4: everything else
    """
    tags = fm.get('tags', [])
    if isinstance(tags, list) and len(tags) > 0:
        return 1

    source_list = fm.get('source_list', '')
    if source_list in ACTIVE_LISTS:
        return 2

    ftype = fm.get('type', 'unknown')
    if ftype == 'bookmark':
        return 3

    return 4


def should_process(fm, wave_filter):
    """Check if a note matches the wave filter."""
    if wave_filter == 'all':
        return True
    wave = get_wave(fm)
    return wave == int(wave_filter)


# ---------------------------------------------------------------------------
# Processing
# ---------------------------------------------------------------------------

def process_file(filepath, api_key, system_prompt, dry_run=False, provider='anthropic'):
    """Process a single inbox file. Returns (destination, classification) or None."""
    with open(filepath) as f:
        content = f.read()

    fm, body = parse_frontmatter(content)
    if fm is None:
        log(f"  Skipping {os.path.basename(filepath)} — no frontmatter")
        return None

    # Extract URLs and fetch titles
    all_text = (fm.get('title', '') + ' ' + body).strip()
    urls = extract_urls(all_text)
    url_info = []
    # Limit to first 3 URLs to avoid slow processing
    for url in urls[:3]:
        # Skip Keep links — they're source references, not content
        if 'keep.google.com' in url:
            continue
        title, is_dead = fetch_url_title(url)
        url_info.append((url, title, is_dead))

    # Build LLM message
    user_message = build_user_message(fm, body, url_info)
    if provider == 'ollama':
        result = call_ollama(system_prompt, user_message)
    else:
        result = call_llm(api_key, system_prompt, user_message)
    if result is None:
        return None

    # Validate response
    valid_types = {
        'bookmark', 'recipe', 'media', 'travel', 'idea', 'reference',
        'event', 'task', 'checklist', 'person', 'finance', 'health',
        'quote', 'journal', 'political',
    }
    valid_statuses = {'active', 'needs-context', 'archived'}

    rtype = result.get('type', 'reference')
    if rtype not in valid_types:
        rtype = 'reference'

    confidence = result.get('confidence', 5)
    if not isinstance(confidence, (int, float)):
        confidence = 5

    status = result.get('status', 'active')
    if status not in valid_statuses:
        status = 'active'

    # Override: low confidence → needs-context
    if confidence <= 5 and status != 'archived':
        status = 'needs-context'

    tags = result.get('tags', [])
    if not isinstance(tags, list):
        tags = []
    tags = [str(t).lower().strip() for t in tags[:5]]

    title = result.get('title', fm.get('title', ''))
    stale_reason = result.get('stale_reason')

    # Determine destination
    if status == 'archived':
        dest_dir = ARCHIVE_DIR
    elif status == 'needs-context':
        dest_dir = NEEDS_CONTEXT_DIR
    else:
        dest_dir = NOTES_DIR

    # Build frontmatter updates
    updates = {
        'type': rtype,
        'status': status,
        'tags': tags,
        'title': title,
        'processed': datetime.date.today().isoformat(),
        'confidence': int(confidence),
    }
    if stale_reason and status == 'archived':
        updates['stale_reason'] = stale_reason

    if dry_run:
        return dest_dir, {**updates, '_file': os.path.basename(filepath)}

    # Update file and move
    new_content = update_frontmatter(content, updates)
    with open(filepath, 'w') as f:
        f.write(new_content)

    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, os.path.basename(filepath))
    shutil.move(filepath, dest_path)

    return dest_dir, updates


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def print_summary(results):
    """Print a summary of processing results."""
    total = len(results)
    notes = [r for r in results if r[0] == NOTES_DIR]
    needs = [r for r in results if r[0] == NEEDS_CONTEXT_DIR]
    archived = [r for r in results if r[0] == ARCHIVE_DIR]

    # Count types in notes
    type_counts = {}
    for _, info in notes:
        t = info.get('type', 'unknown')
        type_counts[t] = type_counts.get(t, 0) + 1
    type_summary = ', '.join(f"{c} {t}" for t, c in
                             sorted(type_counts.items(), key=lambda x: -x[1]))

    # Count stale reasons in archived
    reason_counts = {}
    for _, info in archived:
        r = info.get('stale_reason', 'unknown')
        reason_counts[r] = reason_counts.get(r, 0) + 1
    reason_summary = ', '.join(f"{c} {r}" for r, c in
                                sorted(reason_counts.items(), key=lambda x: -x[1]))

    log(f"\nProcessed {total} items:")
    log(f"  notes/: {len(notes)}" + (f" ({type_summary})" if type_summary else ""))
    log(f"  needs-context/: {len(needs)}")
    log(f"  archive/: {len(archived)}" + (f" ({reason_summary})" if reason_summary else ""))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Process vault inbox items with LLM classification")
    parser.add_argument('--wave', default='all',
                        help='Wave to process: 1 (tagged), 2 (active lists), 3 (bookmarks), 4 (rest), all (default)')
    parser.add_argument('--limit', type=int, default=None,
                        help='Max items to process')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show LLM output without moving files')
    parser.add_argument('--provider', default='anthropic', choices=['anthropic', 'ollama'],
                        help='LLM provider: anthropic (default) or ollama (local)')
    args = parser.parse_args()

    # Validate wave
    if args.wave not in ('1', '2', '3', '4', 'all'):
        print("ERROR: --wave must be 1, 2, 3, 4, or all", file=sys.stderr)
        sys.exit(1)

    api_key = None
    if args.provider == 'anthropic':
        api_key = get_env("ANTHROPIC_API_KEY")
    else:
        log(f"Using Ollama ({OLLAMA_MODEL})")

    # Load context and build system prompt
    log("Loading context files...")
    context = load_context()
    system_prompt = build_system_prompt(context)

    # Ensure output directories exist
    for d in [NOTES_DIR, NEEDS_CONTEXT_DIR, ARCHIVE_DIR]:
        os.makedirs(d, exist_ok=True)

    # Gather inbox files
    if not os.path.isdir(INBOX_DIR):
        print(f"ERROR: Inbox directory not found: {INBOX_DIR}", file=sys.stderr)
        sys.exit(1)

    all_files = sorted([
        os.path.join(INBOX_DIR, f)
        for f in os.listdir(INBOX_DIR)
        if f.endswith('.md')
    ])

    # Filter by wave, collecting (filepath, updated_date) for sorting
    candidates = []
    for filepath in all_files:
        with open(filepath) as f:
            content = f.read()
        fm, _ = parse_frontmatter(content)
        if fm and should_process(fm, args.wave):
            updated = fm.get('updated', fm.get('created', '1970-01-01'))
            candidates.append((filepath, updated))

    # Sort newest first — prioritise recent notes
    candidates.sort(key=lambda x: x[1], reverse=True)
    files_to_process = [fp for fp, _ in candidates]

    if args.limit:
        files_to_process = files_to_process[:args.limit]

    total = len(files_to_process)
    log(f"Found {len(all_files)} inbox files, {total} matching wave={args.wave}")
    if args.limit:
        log(f"Limited to {args.limit} items")
    if args.dry_run:
        log("DRY RUN — no files will be moved")
    log("")

    if total == 0:
        log("Nothing to process.")
        return

    # Process files
    results = []
    errors = 0
    start_time = time.time()

    for i, filepath in enumerate(files_to_process):
        filename = os.path.basename(filepath)
        # Progress
        pct = int((i + 1) / total * 100)
        elapsed = time.time() - start_time
        rate = (i + 1) / elapsed if elapsed > 0 else 0
        eta = int((total - i - 1) / rate) if rate > 0 else 0
        eta_str = f"{eta // 60}m{eta % 60:02d}s" if eta > 60 else f"{eta}s"

        log(f"[{i+1}/{total} {pct}% ETA:{eta_str}] {filename[:60]}")

        result = process_file(filepath, api_key, system_prompt, dry_run=args.dry_run, provider=args.provider)
        if result is None:
            errors += 1
            log(f"  FAILED — skipping")
            continue

        dest_dir, info = result
        dest_name = os.path.basename(dest_dir)
        conf = info.get('confidence', '?')
        log(f"  → {dest_name}/ type={info.get('type')} tags={info.get('tags')} confidence={conf}")

        if args.dry_run:
            log(f"    title: {info.get('title', '')[:70]}")
            if info.get('stale_reason'):
                log(f"    stale_reason: {info['stale_reason']}")

        results.append(result)

        # Rate limit: ~10/sec max (100ms between calls)
        time.sleep(0.1)

    # Summary
    elapsed = time.time() - start_time
    print_summary(results)
    log(f"\nCompleted in {elapsed:.0f}s ({errors} errors)")


if __name__ == "__main__":
    main()
