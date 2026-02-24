#!/usr/bin/env python3
"""Apply triage decisions from JSON to vault notes.

Reads a decisions JSON file (from the triage UI) and applies each decision
using review_helper.py to update frontmatter and move files.

Python 3.11 stdlib only. No pip dependencies.

Usage:
    python3 scripts/apply-decisions.py                          # apply from default path
    python3 scripts/apply-decisions.py --input decisions.json   # custom input
    python3 scripts/apply-decisions.py --dry-run                # show what would happen
"""

import argparse
import datetime
import json
import os
import subprocess
import sys

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
REVIEW_HELPER = os.path.join(SCRIPT_DIR, "review_helper.py")
DEFAULT_INPUT = os.path.join(REPO_ROOT, "data", "triage-decisions.json")

INBOX_DIR = os.path.join(REPO_ROOT, "data", "vault", "inbox")
NEEDS_CONTEXT_DIR = os.path.join(REPO_ROOT, "data", "vault", "needs-context")
NOTES_DIR = os.path.join(REPO_ROOT, "data", "vault", "notes")
ARCHIVE_DIR = os.path.join(REPO_ROOT, "data", "vault", "archive")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def log(msg):
    print(msg, file=sys.stderr)


def find_file(filename):
    """Find a file in inbox or needs-context directories. Returns path or None."""
    for directory in [INBOX_DIR, NEEDS_CONTEXT_DIR]:
        path = os.path.join(directory, filename)
        if os.path.isfile(path):
            return path
    return None


def run_helper(args, dry_run=False):
    """Run review_helper.py with given args. Returns True on success."""
    cmd = [sys.executable, REVIEW_HELPER] + args
    if dry_run:
        log(f"    would run: {' '.join(cmd)}")
        return True
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError as e:
        log(f"    ERROR: {e.stderr.strip()}")
        return False


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def apply_direct(filepath, decision, dry_run=False):
    """Move note to notes/ with updated frontmatter."""
    updates = {
        'type': decision.get('type', 'reference'),
        'tags': decision.get('tags', []),
        'status': 'active',
        'processed': datetime.date.today().isoformat(),
    }
    if decision.get('title'):
        updates['title'] = decision['title']

    return run_helper(
        ['move', filepath, NOTES_DIR, json.dumps(updates)],
        dry_run=dry_run,
    )


def apply_archive(filepath, decision, dry_run=False):
    """Move note to archive/ with stale_reason."""
    updates = {
        'status': 'archived',
        'processed': datetime.date.today().isoformat(),
    }
    if decision.get('stale_reason'):
        updates['stale_reason'] = decision['stale_reason']

    return run_helper(
        ['move', filepath, ARCHIVE_DIR, json.dumps(updates)],
        dry_run=dry_run,
    )


def apply_context(filepath, decision, dry_run=False):
    """Add context text to a needs-context note."""
    context_text = decision.get('context', '')
    if not context_text:
        log(f"    WARNING: context action but no context text provided")
        return False

    return run_helper(
        ['context', filepath, context_text],
        dry_run=dry_run,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Apply triage decisions to vault notes")
    parser.add_argument('--input', default=DEFAULT_INPUT,
                        help=f'Decisions JSON file (default: {DEFAULT_INPUT})')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would happen without making changes')
    args = parser.parse_args()

    # Load decisions
    input_path = args.input
    if not os.path.isabs(input_path):
        input_path = os.path.join(REPO_ROOT, input_path)

    if not os.path.isfile(input_path):
        print(f"ERROR: Decisions file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    with open(input_path) as f:
        data = json.load(f)

    decisions = data.get('decisions', [])
    if not decisions:
        log("No decisions to apply.")
        return

    log(f"Loaded {len(decisions)} decisions from {input_path}")
    if args.dry_run:
        log("DRY RUN — no files will be changed\n")
    else:
        log("")

    # Verify review_helper.py exists
    if not os.path.isfile(REVIEW_HELPER):
        print(f"ERROR: review_helper.py not found: {REVIEW_HELPER}", file=sys.stderr)
        sys.exit(1)

    # Apply each decision
    counts = {'direct': 0, 'archive': 0, 'context': 0, 'skip': 0, 'not_found': 0, 'error': 0}

    for i, decision in enumerate(decisions):
        filename = decision.get('filename', '')
        action = decision.get('action', 'skip')
        note_id = decision.get('id', '?')

        log(f"[{i+1}/{len(decisions)}] {filename[:50]} → {action}")

        if action == 'skip':
            counts['skip'] += 1
            continue

        # Find the file
        filepath = find_file(filename)
        if filepath is None:
            log(f"    WARNING: file not found (already processed?)")
            counts['not_found'] += 1
            continue

        # Apply the action
        if action == 'direct':
            ok = apply_direct(filepath, decision, dry_run=args.dry_run)
        elif action == 'archive':
            ok = apply_archive(filepath, decision, dry_run=args.dry_run)
        elif action == 'context':
            ok = apply_context(filepath, decision, dry_run=args.dry_run)
        else:
            log(f"    WARNING: unknown action '{action}', skipping")
            counts['skip'] += 1
            continue

        if ok:
            counts[action] += 1
        else:
            counts['error'] += 1

    # Summary
    total = len(decisions)
    log(f"\nApplied {total} decisions: "
        f"{counts['direct']} direct, "
        f"{counts['archive']} archive, "
        f"{counts['context']} context, "
        f"{counts['skip']} skip, "
        f"{counts['not_found']} not found, "
        f"{counts['error']} errors")


if __name__ == "__main__":
    main()
