#!/usr/bin/env bash
# List all custom Claude Code skills from ~/.claude/commands/
set -euo pipefail

COMMANDS_DIR="$HOME/.claude/commands"

if [ ! -d "$COMMANDS_DIR" ]; then
    echo "No skills directory found at ~/.claude/commands/"
    exit 1
fi

echo ""
echo "Claude Code Skills"
echo "=================="
echo ""

for f in "$COMMANDS_DIR"/*.md; do
    [ -f "$f" ] || continue
    name=$(basename "$f" .md)
    [ "$name" = "README" ] && continue

    desc=$(sed -n 's/^description: *//p' "$f" | head -1)
    hint=$(sed -n 's/^argument-hint: *"*//p' "$f" | head -1 | tr -d '"')

    printf "  /%s\n" "$name"
    [ -n "$desc" ] && printf "    %s\n" "$desc"
    [ -n "$hint" ] && printf "    Usage: /%s %s\n" "$name" "$hint"
    echo ""
done
