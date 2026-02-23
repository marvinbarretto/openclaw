#!/usr/bin/env python3
"""Vault note review helper — update frontmatter and move files.

Used by the /manual-review Claude Code command.
Python 3.11 stdlib only. No pip dependencies.

Usage (from Claude Code command):
    python3 scripts/review_helper.py direct <filepath> <dest_dir> <json_updates>
    python3 scripts/review_helper.py context <filepath> <context_text>
"""

import json
import os
import re
import shutil
import sys


def _parse_frontmatter(content):
    """Split content into (yaml_lines, body). Returns (list, str) or (None, content)."""
    match = re.match(r'^---\n(.*?)\n---\n?(.*)', content, re.DOTALL)
    if not match:
        return None, content
    return match.group(1).split('\n'), match.group(2)


def _update_yaml_lines(lines, updates):
    """Update YAML lines in place, preserving order. Add new keys at end."""
    remaining = dict(updates)
    new_lines = []
    for line in lines:
        m = re.match(r'^(\w[\w-]*)\s*:', line)
        if m and m.group(1) in remaining:
            key = m.group(1)
            val = remaining.pop(key)
            new_lines.append(_format_line(key, val))
        else:
            new_lines.append(line)
    for key, val in remaining.items():
        new_lines.append(_format_line(key, val))
    return new_lines


def _format_line(key, val):
    """Format a single YAML key-value line."""
    if isinstance(val, list):
        return f'{key}: {json.dumps(val)}'
    s = str(val)
    if ':' in s or '"' in s or s.startswith('[') or s.startswith('{') or s == '':
        return f'{key}: "{s}"'
    return f'{key}: {s}'


def _rebuild(yaml_lines, body):
    """Rebuild markdown content from YAML lines and body."""
    return '---\n' + '\n'.join(yaml_lines) + '\n---\n' + body


def update_and_move(filepath, dest_dir, updates):
    """Update frontmatter fields and move file to dest_dir."""
    with open(filepath) as f:
        content = f.read()

    yaml_lines, body = _parse_frontmatter(content)
    if yaml_lines is None:
        raise ValueError(f"No frontmatter found in {filepath}")

    yaml_lines = _update_yaml_lines(yaml_lines, updates)
    new_content = _rebuild(yaml_lines, body)

    os.makedirs(dest_dir, exist_ok=True)

    with open(filepath, 'w') as f:
        f.write(new_content)

    dest_path = os.path.join(dest_dir, os.path.basename(filepath))
    shutil.move(filepath, dest_path)


def add_context(filepath, context_text):
    """Add review context to frontmatter and prepend to body."""
    with open(filepath) as f:
        content = f.read()

    yaml_lines, body = _parse_frontmatter(content)
    if yaml_lines is None:
        raise ValueError(f"No frontmatter found in {filepath}")

    yaml_lines = _update_yaml_lines(yaml_lines, {
        'review_context': context_text,
    })

    new_body = context_text + '\n\n' + body
    new_content = _rebuild(yaml_lines, new_body)

    with open(filepath, 'w') as f:
        f.write(new_content)


# ---------------------------------------------------------------------------
# CLI interface for use from Claude Code command
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 3:
        print("Usage:", file=sys.stderr)
        print("  review_helper.py move <filepath> <dest_dir> '<json_updates>'", file=sys.stderr)
        print("  review_helper.py context <filepath> '<context_text>'", file=sys.stderr)
        sys.exit(1)

    action = sys.argv[1]

    if action == 'move':
        filepath = sys.argv[2]
        dest_dir = sys.argv[3]
        updates = json.loads(sys.argv[4])
        update_and_move(filepath, dest_dir, updates)

    elif action == 'context':
        filepath = sys.argv[2]
        context_text = sys.argv[3]
        add_context(filepath, context_text)

    else:
        print(f"Unknown action: {action}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
