#!/usr/bin/env python3
"""
Vault task prioritisation using Gemini Flash.

Batch-scores all active vault tasks against PRIORITIES.md and GOALS.md,
writing priority, actionability, and scoring metadata back into each note's
YAML frontmatter. Designed to run daily at 04:30 UTC on VPS cron — before
the tasks sweep (05:00) and email fetch (06:00), so the morning briefing
(07:00) has pre-scored tasks to surface.

Python 3.11 stdlib only. No pip dependencies.

Environment variables:
    GOOGLE_AI_API_KEY — Google AI API key (Gemini Flash)

Usage:
    python3 prioritise-tasks.py                    # score tasks, skip fresh
    python3 prioritise-tasks.py --dry-run          # preview without writing
    python3 prioritise-tasks.py --force            # re-score everything
    python3 prioritise-tasks.py --limit 50         # process first N tasks
    python3 prioritise-tasks.py --stats            # show scoring distribution
"""

import argparse
import datetime
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from jimbo_runtime_service import (
    build_vault_triage_payload,
    log_dispatch_candidate_classification,
)
from jimbo_runtime_inbox_service import enqueue_payloads

# ---------------------------------------------------------------------------
# Paths — all relative to /workspace/ (sandbox) or script dir (laptop)
# ---------------------------------------------------------------------------

_script_dir = os.path.dirname(os.path.abspath(__file__))
VAULT_NOTES = os.path.join(_script_dir, "vault", "notes")
CONTEXT_DIR = os.path.join(_script_dir, "context")

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

BATCH_SIZE = 5

# ---------------------------------------------------------------------------
# Scoring prompt
# ---------------------------------------------------------------------------

SCORING_SYSTEM_PROMPT = """You are a task prioritisation engine for Marvin's personal vault.

You will receive a batch of tasks from his vault, plus his current PRIORITIES and GOALS.
Score each task on how relevant and actionable it is RIGHT NOW.

## Scoring rubric

| Bucket | Meaning |
|--------|---------|
| 0 (P0) | Do today / blocking. Due this week AND blocks a current project. Requires immediate action. |
| 1 (P1) | This week. Important, clearly actionable, connects to active priorities. |
| 2 (P2) | This month. Useful but not urgent, worth doing. |
| 3 (P3) | Backlog / someday. Nice to have, no time pressure, or unclear value. |

Output the number only (0, 1, 2, or 3).

## Actionability

- `clear` — the task has a specific, concrete next step
- `vague` — the intent is clear but the next step is unclear
- `needs-breakdown` — too large, needs decomposing into subtasks

## Rules

1. Score based on alignment with PRIORITIES.md (active projects, this week) and GOALS.md (longer-term ambitions).
2. `source_list` is historical context only — "Immediate" means it was urgent when saved, not now.
3. Only suggest `stale` status if ALL of: >18 months old AND no alignment with any priority/goal AND no inherent time-sensitivity.
4. `suggested_status` is advisory — the script never auto-applies it.
5. Be calibrated: most tasks should be P2 or P3. Reserve P0 for things that are blocking right now, P1 for things Marvin should do THIS WEEK.

## Dispatch suggestions

For tasks with actionability `clear` and priority <= 2 (P0, P1, or P2), also suggest dispatch fields:

### Skill Suggestions

**required_skills** — array of one or more skills this task needs. Available skills:
- `coder` — implement code changes, fix bugs, refactor
- `researcher` — investigate topics, compare options, validate assumptions
- `extractor` — screenshot URLs, extract structured data from web pages
- `drafter` — write structured text output (summaries, docs, specs)

Inference rules:
- Tags contain software/code/repo names, technical content → include `coder`
- "compare", "research", "find", "evaluate", type=bookmark → include `researcher`
- "screenshot", "capture", "extract from URL" → include `extractor`
- "write", "draft", "blog", "document" → include `drafter`
- Tasks may need multiple skills (e.g. research + code = ["researcher", "coder"])

**suggested_executor** — who should run this task:
- `boris` — complex tasks, multi-skill, high-priority, requires strong reasoning
- `ralph` — simple single-skill tasks, CSS/style, basic extraction, non-urgent
- `marvin` — needs human judgment, product decisions, approval required

Inference rules:
- Multiple skills → `boris`
- Priority 0-1 (urgent/this week) → `boris`
- Single skill + low complexity + priority 2-3 → `ralph`
- Personal decision, physical action, approval needed → `marvin`

**suggested_route** — where the task runs:
- `jimbo` — automation can handle (boris or ralph will execute)
- `marvin` — requires human action

### acceptance_criteria
For tasks where you suggest skills, draft concise acceptance criteria — concrete, verifiable conditions.
Keep it to 1-3 short sentences. Focus on WHAT must be true when done, not HOW to do it.
If the task is too vague to write AC for, leave it null.

## Response format

IMPORTANT: You will receive multiple tasks. You MUST return a score for EVERY task.
Return ONLY valid JSON — a JSON array containing one object per task. Example for 3 tasks:
```json
[
  {{"id": "note_abc123", "priority": 1, "priority_reason": "Aligns with Build & Ship Products goal", "actionability": "clear", "suggested_status": null, "suggested_skills": ["coder"], "suggested_executor": "boris", "suggested_route": "jimbo", "suggested_ac": "Dark mode toggle in settings. CSS variables for theming. Persists to localStorage. Tests pass."}},
  {{"id": "note_def456", "priority": 3, "priority_reason": "No alignment with current priorities", "actionability": "vague", "suggested_status": null, "suggested_skills": null, "suggested_executor": null, "suggested_route": null, "suggested_ac": null}},
  {{"id": "note_ghi789", "priority": 3, "priority_reason": "Stale and irrelevant", "actionability": "vague", "suggested_status": "stale", "suggested_skills": null, "suggested_executor": null, "suggested_route": null, "suggested_ac": null}}
]
```

`suggested_status` should be `"stale"` or `null`. Nothing else.
`suggested_skills` should be a JSON array of strings (e.g. `["coder", "researcher"]`) or `null`.
`suggested_executor` should be `"boris"`, `"ralph"`, `"marvin"`, or `null`.
`suggested_agent_type` — deprecated, use `suggested_skills`. Still accepted for backwards compat.
`suggested_route` should be `"jimbo"`, `"marvin"`, or `null`.
`suggested_ac` should be a short string or `null`.
The array MUST contain exactly one entry per task in the input. Do not skip any.
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_env(name):
    val = os.environ.get(name)
    if not val:
        print(f"ERROR: {name} environment variable not set", file=sys.stderr)
        sys.exit(1)
    return val


def log(msg):
    print(msg, file=sys.stderr)


# ---------------------------------------------------------------------------
# Frontmatter parsing (same as tasks-helper.py)
# ---------------------------------------------------------------------------

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
# Context loading
# ---------------------------------------------------------------------------

def _load_context_files():
    """Read PRIORITIES.md and GOALS.md from the local context directory (fallback)."""
    sections = []
    for name in ['PRIORITIES.md', 'GOALS.md']:
        path = os.path.join(CONTEXT_DIR, name)
        if os.path.exists(path):
            with open(path) as f:
                sections.append(f"## {name}\n\n{f.read().strip()}")
        else:
            log(f"WARNING: {path} not found")
    return '\n\n---\n\n'.join(sections)


def _format_context(data):
    """Format API context response as readable text."""
    lines = [f"# {data.get('display_name', 'Context')}"]
    lines.append("")

    for section in data.get("sections", []):
        lines.append(f"## {section['name']}")
        lines.append("")

        for item in section.get("items", []):
            if item.get("label"):
                lines.append(f"- **{item['label']}** — {item['content']}")
            else:
                lines.append(f"- {item['content']}")

        lines.append("")

    return "\n".join(lines).strip()


def load_context():
    """Load priorities and goals from context API, falling back to files."""
    api_url = os.environ.get('JIMBO_API_URL', '')
    api_key = os.environ.get('JIMBO_API_KEY', '')

    if not api_url or not api_key:
        log("No API credentials — falling back to context files")
        return _load_context_files()

    context_parts = []
    for slug in ['priorities', 'goals']:
        try:
            req = urllib.request.Request(
                f'{api_url}/api/context/files/{slug}',
                headers={
                    'X-API-Key': api_key,
                    'Accept': 'application/json',
                }
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                context_parts.append(_format_context(data))
        except Exception as e:
            log(f'Warning: failed to fetch {slug} from API: {e}')
            log('Falling back to context files')
            return _load_context_files()

    return '\n\n---\n\n'.join(context_parts)


def _context_mtime_files():
    """Return the latest mtime of the local context files (as a date string)."""
    latest = 0
    for name in ['PRIORITIES.md', 'GOALS.md']:
        path = os.path.join(CONTEXT_DIR, name)
        if os.path.exists(path):
            mtime = os.path.getmtime(path)
            if mtime > latest:
                latest = mtime
    if latest == 0:
        return None
    return datetime.date.fromtimestamp(latest).isoformat()


def context_mtime():
    """Return the latest updated_at from the API, falling back to file mtime."""
    api_url = os.environ.get('JIMBO_API_URL', '')
    api_key = os.environ.get('JIMBO_API_KEY', '')

    if not api_url or not api_key:
        return _context_mtime_files()

    latest = None
    for slug in ['priorities', 'goals']:
        try:
            req = urllib.request.Request(
                f'{api_url}/api/context/files/{slug}',
                headers={
                    'X-API-Key': api_key,
                    'Accept': 'application/json',
                }
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                updated = data.get('updated_at', '')
                if updated:
                    # Extract date portion from ISO timestamp
                    date_str = updated[:10]
                    if latest is None or date_str > latest:
                        latest = date_str
        except Exception as e:
            log(f'Warning: failed to fetch {slug} mtime from API: {e}')
            return _context_mtime_files()

    return latest or _context_mtime_files()


# ---------------------------------------------------------------------------
# Vault loading
# ---------------------------------------------------------------------------

def load_vault_tasks(vault_dir):
    """Walk vault notes/, return list of (filepath, fm, body) for active tasks."""
    tasks = []
    if not os.path.isdir(vault_dir):
        log(f"WARNING: Vault directory not found: {vault_dir}")
        return tasks

    for fname in sorted(os.listdir(vault_dir)):
        if not fname.endswith('.md'):
            continue
        filepath = os.path.join(vault_dir, fname)
        with open(filepath, encoding='utf-8') as f:
            content = f.read()

        fm, body = parse_frontmatter(content)
        if fm is None:
            continue

        # Only score active tasks
        if fm.get('type') != 'task':
            continue
        if fm.get('status') != 'active':
            continue

        tasks.append((filepath, fm, body))

    return tasks


def needs_scoring(fm, context_cutoff, force):
    """Check if a note needs (re-)scoring.

    Skip if scored date is after the latest context file change,
    unless --force is set.
    """
    if force:
        return True

    scored = fm.get('scored', '')
    if not scored:
        return True

    # If context files changed after the note was scored, re-score
    if context_cutoff and scored < context_cutoff:
        return True

    return False


# ---------------------------------------------------------------------------
# Gemini API
# ---------------------------------------------------------------------------

def call_gemini(api_key, system_prompt, user_prompt):
    """Call Gemini Flash and return parsed JSON response."""
    url = GEMINI_API_URL.format(model=GEMINI_MODEL) + f"?key={api_key}"
    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"parts": [{"text": user_prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 4096,
        },
    }

    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        log(f"  Gemini API error ({e.code}): {body[:200]}")
        return None
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        log(f"  Gemini connection error: {e}")
        return None

    try:
        text = result["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        log(f"  Gemini unexpected response: {json.dumps(result)[:200]}")
        return None

    return _parse_llm_json(text)


def _parse_llm_json(text):
    """Parse JSON from LLM response — handle markdown fences and trailing commentary."""
    text = text.strip()

    # Strip markdown fences
    fence_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()
    elif text.startswith("```"):
        text = re.sub(r'^```\w*\n?', '', text)
        text = re.sub(r'\n?```.*', '', text, flags=re.DOTALL)
        text = text.strip()

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Find JSON array or object
    for start_char, end_char in [('[', ']'), ('{', '}')]:
        start = text.find(start_char)
        if start != -1:
            depth = 0
            for i in range(start, len(text)):
                if text[i] == start_char:
                    depth += 1
                elif text[i] == end_char:
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[start:i+1])
                        except json.JSONDecodeError:
                            break

    log(f"  Failed to parse LLM response: {text[:200]}")
    return None


# ---------------------------------------------------------------------------
# Batch building
# ---------------------------------------------------------------------------

def build_batch_prompt(tasks_batch, context):
    """Format a batch of tasks for the scoring prompt."""
    parts = [f"## Marvin's current context\n\n{context}\n\n## Tasks to score\n"]

    for filepath, fm, body in tasks_batch:
        note_id = fm.get('id', os.path.basename(filepath))
        title = fm.get('title', '(untitled)')
        created = fm.get('created', 'unknown')
        source_list = fm.get('source_list', '')
        tags = fm.get('tags', [])
        body_preview = body.strip()[:200]

        parts.append(f"### {note_id}")
        parts.append(f"Title: {title}")
        parts.append(f"Created: {created}")
        if source_list:
            parts.append(f"Source list: {source_list}")
        if tags:
            parts.append(f"Tags: {', '.join(tags) if isinstance(tags, list) else tags}")
        if body_preview:
            parts.append(f"Body: {body_preview}")
        parts.append("")

    return '\n'.join(parts)


# ---------------------------------------------------------------------------
# Score application
# ---------------------------------------------------------------------------

def apply_scores(filepath, fm, body, score_result):
    """Write scoring fields into frontmatter and save file."""
    fm['priority'] = score_result.get('priority', 2)
    fm['priority_reason'] = score_result.get('priority_reason', '')
    fm['actionability'] = score_result.get('actionability', 'vague')
    fm['scored'] = datetime.date.today().isoformat()

    suggested = score_result.get('suggested_status')
    if suggested == 'stale':
        fm['suggested_status'] = 'stale'
    elif 'suggested_status' in fm:
        # Clear previous suggestion if no longer suggested
        del fm['suggested_status']

    new_content = build_frontmatter(fm) + '\n' + body
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_score(args):
    """Score vault tasks using Gemini Flash."""
    api_key = get_env("GOOGLE_AI_API_KEY")

    # Load context
    context = load_context()
    if not context:
        log("ERROR: No context files found")
        sys.exit(1)
    ctx_cutoff = context_mtime()
    log(f"Context last changed: {ctx_cutoff or 'unknown'}")

    # Build system prompt with context baked in
    system_prompt = SCORING_SYSTEM_PROMPT

    # Load tasks
    tasks = load_vault_tasks(VAULT_NOTES)
    log(f"Found {len(tasks)} active tasks in vault")

    # Filter to those needing scoring
    to_score = [(fp, fm, body) for fp, fm, body in tasks
                if needs_scoring(fm, ctx_cutoff, args.force)]
    log(f"{len(to_score)} need scoring ({len(tasks) - len(to_score)} skipped as fresh)")

    if args.limit:
        to_score = to_score[:args.limit]
        log(f"Limited to {args.limit}")

    if not to_score:
        log("Nothing to score.")
        print(json.dumps({"status": "ok", "scored": 0, "skipped": len(tasks)}))
        return

    # Process in batches
    scored = 0
    errors = 0
    batches = [to_score[i:i + BATCH_SIZE] for i in range(0, len(to_score), BATCH_SIZE)]
    log(f"Processing {len(to_score)} tasks in {len(batches)} batches...")

    for batch_idx, batch in enumerate(batches):
        if batch_idx > 0:
            time.sleep(1)
        log(f"\nBatch {batch_idx + 1}/{len(batches)} ({len(batch)} tasks)")

        user_prompt = build_batch_prompt(batch, context)
        results = call_gemini(api_key, system_prompt, user_prompt)

        if results is None:
            log("  FAILED — skipping batch")
            errors += len(batch)
            continue

        # Handle single-object response (shouldn't happen but be safe)
        if isinstance(results, dict):
            results = [results]

        if not isinstance(results, list):
            log(f"  Unexpected response type: {type(results)}")
            errors += len(batch)
            continue

        # Index results by id
        results_by_id = {}
        for r in results:
            rid = r.get('id', '')
            if rid:
                results_by_id[rid] = r

        for filepath, fm, body in batch:
            note_id = fm.get('id', '')
            score_result = results_by_id.get(note_id)

            if score_result is None:
                log(f"  WARNING: No score for {note_id}")
                errors += 1
                continue

            priority = score_result.get('priority', 2)
            actionability = score_result.get('actionability', 'vague')
            reason = score_result.get('priority_reason', '')[:80]
            suggested = score_result.get('suggested_status')

            if args.dry_run:
                log(f"  {note_id}: priority={priority} actionability={actionability}"
                    f" reason=\"{reason}\""
                    + (f" suggested_status={suggested}" if suggested else ""))
            else:
                apply_scores(filepath, fm, body, score_result)

            scored += 1

    log(f"\nScored: {scored}, Errors: {errors}, Skipped: {len(tasks) - len(to_score)}")
    if args.dry_run:
        log("(Dry run — no files written)")

    print(json.dumps({"status": "ok", "scored": scored, "errors": errors,
                       "skipped": len(tasks) - len(to_score)}))




# ---------------------------------------------------------------------------
# API-based scoring (vault task system — replaces file-based scoring)
# ---------------------------------------------------------------------------

def _api_request(method, path, body=None):
    """Make an authenticated request to jimbo-api."""
    api_url = os.environ.get("JIMBO_API_URL", "")
    api_key = os.environ.get("JIMBO_API_KEY", "")
    if not api_url or not api_key:
        log("ERROR: JIMBO_API_URL and JIMBO_API_KEY must be set for --api mode")
        sys.exit(1)

    url = f"{api_url}{urllib.parse.quote(path, safe='/:?=&')}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("X-API-Key", api_key)
    if body:
        req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()
        log(f"  API error ({e.code}): {err_body[:200]}")
        return None
    except (urllib.error.URLError, TimeoutError) as e:
        log(f"  API connection error: {e}")
        return None


def cmd_score_api(args):
    """Score vault tasks via jimbo-api instead of files."""
    gemini_key = get_env("GOOGLE_AI_API_KEY")

    # Load context (same as file-based mode)
    context = load_context()
    if not context:
        log("ERROR: No context available")
        sys.exit(1)

    system_prompt = SCORING_SYSTEM_PROMPT

    # Fetch tasks from API — active and inbox, excluding subtasks
    result = _api_request("GET", "/api/vault/notes?status=active,inbox&has_parent=false&limit=200&sort=updated_at&order=asc")
    if not result or not result.get("notes"):
        log("No tasks found in API")
        print(json.dumps({"status": "ok", "scored": 0}))
        return

    all_tasks = result["notes"]
    log(f"Fetched {len(all_tasks)} tasks from API")

    # Filter to those needing scoring (no ai_priority, or force)
    if args.force:
        to_score = all_tasks
    else:
        ctx_cutoff = context_mtime()
        to_score = []
        for t in all_tasks:
            if t.get("ai_priority") is None:
                to_score.append(t)
            elif ctx_cutoff and (t.get("updated_at") or "") < ctx_cutoff:
                to_score.append(t)
            # Skip freshly scored tasks
        log(f"{len(to_score)} need scoring ({len(all_tasks) - len(to_score)} skipped as fresh)")

    if args.limit:
        to_score = to_score[:args.limit]

    if not to_score:
        log("Nothing to score.")
        # Still do deferred resurfacing
        _resurface_deferred()
        print(json.dumps({"status": "ok", "scored": 0, "skipped": len(all_tasks)}))
        return

    # Build batches using task data from API
    scored = 0
    errors = 0
    emitted_payloads = []
    queued_payloads = []
    batches = [to_score[i:i + BATCH_SIZE] for i in range(0, len(to_score), BATCH_SIZE)]
    log(f"Processing {len(to_score)} tasks in {len(batches)} batches...")

    for batch_idx, batch in enumerate(batches):
        if batch_idx > 0:
            time.sleep(1)
        log(f"\nBatch {batch_idx + 1}/{len(batches)} ({len(batch)} tasks)")

        # Build prompt from API task data
        prompt_parts = [f"## Marvin's current context\n\n{context}\n\n## Tasks to score\n"]
        for t in batch:
            prompt_parts.append(f"### {t['id']}")
            prompt_parts.append(f"Title: {t['title']}")
            prompt_parts.append(f"Created: {t.get('created_at', 'unknown')}")
            if t.get('tags'):
                prompt_parts.append(f"Tags: {t['tags']}")
            if t.get('body'):
                prompt_parts.append(f"Body: {t['body'][:200]}")
            prompt_parts.append("")

        user_prompt = '\n'.join(prompt_parts)
        results = call_gemini(gemini_key, system_prompt, user_prompt)

        if results is None:
            log("  FAILED — skipping batch")
            errors += len(batch)
            continue

        if isinstance(results, dict):
            results = [results]

        results_by_id = {r.get('id', ''): r for r in results if isinstance(r, dict)}

        for t in batch:
            score_result = results_by_id.get(t['id'])
            if score_result is None:
                log(f"  WARNING: No score for {t['id']}")
                errors += 1
                continue

            priority = score_result.get('priority', 2)
            actionability = score_result.get('actionability', 'vague')
            reason = score_result.get('priority_reason', '')[:200]

            # Dispatch suggestions (only for dispatchable tasks)
            s_agent = score_result.get('suggested_agent_type')
            s_route = score_result.get('suggested_route')
            s_ac = score_result.get('suggested_ac')
            s_skills = score_result.get('suggested_skills')
            s_executor = score_result.get('suggested_executor')

            # Backwards compat: derive agent_type from primary skill
            if s_skills and not s_agent:
                s_agent = s_skills[0]

            if args.dry_run:
                line = f"  {t['id']}: priority={priority} actionability={actionability} reason=\"{reason[:60]}\""
                if s_skills:
                    line += f" skills={s_skills}"
                if s_executor:
                    line += f" executor={s_executor}"
                if s_ac:
                    line += f" AC: \"{s_ac[:50]}...\""
                log(line)
            elif args.emit_intake:
                if s_route in {'jimbo', 'marvin'}:
                    emitted_payloads.append(build_vault_triage_payload(
                        t,
                        priority=priority,
                        actionability=actionability,
                        reason=reason,
                        suggested_agent_type=s_agent,
                        suggested_route=s_route,
                        acceptance_criteria=s_ac,
                        changed_fields={
                            "ai_priority",
                            "ai_rationale",
                            "actionability",
                            "suggested_agent_type",
                            "suggested_route",
                            "suggested_ac",
                            "suggested_skills",
                            "suggested_executor",
                        },
                        model=GEMINI_MODEL,
                    ))
            else:
                patch = {
                    "ai_priority": priority,
                    "ai_rationale": reason,
                    "actionability": actionability,
                }
                if s_skills and isinstance(s_skills, list):
                    patch["suggested_skills"] = json.dumps(s_skills)
                if s_executor:
                    patch["suggested_executor"] = s_executor
                if s_agent:
                    patch["suggested_agent_type"] = s_agent
                if s_route:
                    patch["suggested_route"] = s_route
                if s_ac:
                    patch["suggested_ac"] = s_ac
                _api_request("PATCH", f"/api/vault/notes/{t['id']}", patch)
                if s_agent and s_route == 'jimbo':
                    runtime_payload = build_vault_triage_payload(
                        t,
                        priority=priority,
                        actionability=actionability,
                        reason=reason,
                        suggested_agent_type=s_agent,
                        suggested_route=s_route,
                        acceptance_criteria=s_ac,
                        changed_fields=patch.keys(),
                        model=GEMINI_MODEL,
                    )
                    log_dispatch_candidate_classification(
                        t,
                        priority=priority,
                        actionability=actionability,
                        reason=reason,
                        suggested_agent_type=s_agent,
                        suggested_route=s_route,
                        acceptance_criteria=s_ac,
                        changed_fields=patch.keys(),
                        model=GEMINI_MODEL,
                    )
                    if args.submit_runtime_inbox:
                        queued_payloads.append(runtime_payload)
                elif args.submit_runtime_inbox and s_route == 'marvin':
                    queued_payloads.append(build_vault_triage_payload(
                        t,
                        priority=priority,
                        actionability=actionability,
                        reason=reason,
                        suggested_agent_type=s_agent,
                        suggested_route=s_route,
                        acceptance_criteria=s_ac,
                        changed_fields=patch.keys(),
                        model=GEMINI_MODEL,
                    ))

            scored += 1

    if args.emit_intake:
        print(json.dumps(emitted_payloads, indent=2))
        return

    inbox_submission = {"count": 0}
    if args.submit_runtime_inbox and not args.dry_run:
        inbox_submission = enqueue_payloads(
            queued_payloads,
            producer="vault-triage",
            source="vault-triage",
            live=True,
        )

    # Resurface deferred tasks
    if not args.dry_run:
        _resurface_deferred()

    log(f"\nScored: {scored}, Errors: {errors}, Skipped: {len(all_tasks) - len(to_score)}")
    if args.dry_run:
        log("(Dry run — no API calls made)")

    print(json.dumps({"status": "ok", "scored": scored, "errors": errors,
                       "skipped": len(all_tasks) - len(to_score),
                       "submitted_to_runtime_inbox": inbox_submission["count"]}))


def _resurface_deferred():
    """Move deferred tasks with past due_date back to active."""
    today = datetime.date.today().isoformat()
    result = _api_request("GET", f"/api/vault/notes?status=deferred&due_before={today}&limit=50")
    if not result or not result.get("notes"):
        return

    count = 0
    for t in result["notes"]:
        if t.get("due_date") and t["due_date"] <= today:
            _api_request("PATCH", f"/api/vault/notes/{t['id']}", {"status": "active", "due_date": None})
            log(f"  Resurfaced deferred task: {t['title'][:60]}")
            count += 1

    if count:
        log(f"Resurfaced {count} deferred tasks")


def cmd_stats(args):
    """Show scoring distribution across vault tasks."""
    tasks = load_vault_tasks(VAULT_NOTES)
    log(f"Total active tasks: {len(tasks)}")

    if not tasks:
        return

    scored_count = 0
    unscored_count = 0
    priority_dist = {}
    actionability_dist = {}
    stale_count = 0

    for filepath, fm, body in tasks:
        if fm.get('priority'):
            scored_count += 1
            p = int(fm['priority'])
            bucket = f"{p}"
            priority_dist[bucket] = priority_dist.get(bucket, 0) + 1
        else:
            unscored_count += 1

        act = fm.get('actionability')
        if act:
            actionability_dist[act] = actionability_dist.get(act, 0) + 1

        if fm.get('suggested_status') == 'stale':
            stale_count += 1

    log(f"\nScored: {scored_count}, Unscored: {unscored_count}")

    if priority_dist:
        log("\nPriority distribution:")
        for p in sorted(priority_dist.keys(), key=int, reverse=True):
            count = priority_dist[p]
            bar = "#" * count
            log(f"  {p:>2}: {count:>3} {bar}")

    if actionability_dist:
        log("\nActionability:")
        for act, count in sorted(actionability_dist.items()):
            log(f"  {act}: {count}")

    if stale_count:
        log(f"\nSuggested stale: {stale_count}")

    # Top 5 highest priority
    scored_tasks = [(fm, filepath) for filepath, fm, body in tasks if fm.get('priority')]
    scored_tasks.sort(key=lambda x: int(x[0].get('priority', 0)), reverse=True)
    if scored_tasks:
        log("\nTop 5 highest priority:")
        for fm, filepath in scored_tasks[:5]:
            title = fm.get('title', os.path.basename(filepath))[:60]
            log(f"  [{fm['priority']}] {title}")

    print(json.dumps({"status": "ok", "total": len(tasks), "scored": scored_count,
                       "unscored": unscored_count}))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Vault task prioritisation using Gemini Flash")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--force", action="store_true", help="Re-score everything")
    parser.add_argument("--limit", type=int, default=None, help="Max tasks to score")
    parser.add_argument("--stats", action="store_true", help="Show scoring distribution")
    parser.add_argument("--api", action="store_true", help="Score via jimbo-api (vault task system)")
    parser.add_argument("--emit-intake", action="store_true", help="Emit runtime intake payloads instead of writing task updates")
    parser.add_argument("--submit-runtime-inbox", action="store_true", help="Submit eligible Jimbo tasks into the runtime inbox after API updates")

    args = parser.parse_args()

    if args.stats:
        cmd_stats(args)
    elif args.api:
        cmd_score_api(args)
    else:
        cmd_score(args)


if __name__ == "__main__":
    main()
