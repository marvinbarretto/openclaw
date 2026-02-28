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
import urllib.request

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

| Score | Meaning |
|-------|---------|
| 9-10  | Urgent + directly aligned with an active project or goal |
| 7-8   | Clearly relevant to a current priority or goal |
| 5-6   | Vaguely relevant or useful but not pressing |
| 3-4   | Low relevance to current priorities |
| 1-2   | Stale, trivial, or completely unrelated |

## Actionability

- `clear` — the task has a specific, concrete next step
- `vague` — the intent is clear but the next step is unclear
- `needs-breakdown` — too large, needs decomposing into subtasks

## Rules

1. Score based on alignment with PRIORITIES.md (active projects, this week) and GOALS.md (longer-term ambitions).
2. `source_list` is historical context only — "Immediate" means it was urgent when saved, not now.
3. Only suggest `stale` status if ALL of: >18 months old AND no alignment with any priority/goal AND no inherent time-sensitivity.
4. `suggested_status` is advisory — the script never auto-applies it.
5. Be calibrated: most tasks should score 3-6. Reserve 9-10 for things Marvin should do THIS WEEK.

## Response format

IMPORTANT: You will receive multiple tasks. You MUST return a score for EVERY task.
Return ONLY valid JSON — a JSON array containing one object per task. Example for 3 tasks:
```json
[
  {{"id": "note_abc123", "priority": 7, "priority_reason": "Aligns with Build & Ship Products goal", "actionability": "clear", "suggested_status": null}},
  {{"id": "note_def456", "priority": 3, "priority_reason": "No alignment with current priorities", "actionability": "vague", "suggested_status": null}},
  {{"id": "note_ghi789", "priority": 1, "priority_reason": "Stale and irrelevant", "actionability": "vague", "suggested_status": "stale"}}
]
```

`suggested_status` should be `"stale"` or `null`. Nothing else.
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

def load_context():
    """Read PRIORITIES.md and GOALS.md from the context directory."""
    sections = []
    for name in ['PRIORITIES.md', 'GOALS.md']:
        path = os.path.join(CONTEXT_DIR, name)
        if os.path.exists(path):
            with open(path) as f:
                sections.append(f"## {name}\n\n{f.read().strip()}")
        else:
            log(f"WARNING: {path} not found")
    return '\n\n---\n\n'.join(sections)


def context_mtime():
    """Return the latest mtime of the context files (as a date string)."""
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
    fm['priority'] = score_result.get('priority', 5)
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

            priority = score_result.get('priority', 5)
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

    args = parser.parse_args()

    if args.stats:
        cmd_stats(args)
    else:
        cmd_score(args)


if __name__ == "__main__":
    main()
