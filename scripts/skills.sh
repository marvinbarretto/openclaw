#!/usr/bin/env bash
# List all custom Claude Code skills from ~/.claude/commands/ and ~/.claude/skills/
set -euo pipefail

COMMANDS_DIR="$HOME/.claude/commands"
SKILLS_DIR="$HOME/.claude/skills"

echo ""
echo "Claude Code Skills"
echo "=================="
echo ""

# Track printed skills to avoid duplicates (commands take priority)
seen=""

# Scan ~/.claude/commands/ (slash commands)
if [ -d "$COMMANDS_DIR" ]; then
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
        seen="$seen|$name|"
    done
fi

# Scan ~/.claude/skills/ (skill directories with SKILL.md)
if [ -d "$SKILLS_DIR" ]; then
    for f in "$SKILLS_DIR"/*/SKILL.md; do
        [ -f "$f" ] || continue
        name=$(basename "$(dirname "$f")")
        echo "$seen" | grep -q "|$name|" && continue

        desc=$(sed -n 's/^description: *//p' "$f" | head -1)

        printf "  /%s\n" "$name"
        [ -n "$desc" ] && printf "    %s\n" "$desc"
        echo ""
        seen="$seen|$name|"
    done
fi
