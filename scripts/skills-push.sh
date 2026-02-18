#!/usr/bin/env bash
# Push custom skills to VPS for Jimbo to use.
# Usage: ./scripts/skills-push.sh [--dry-run]

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SKILLS_DIR="$REPO_ROOT/skills"
REMOTE="jimbo:/home/openclaw/.openclaw/workspace/skills/"

if [ ! -d "$SKILLS_DIR" ]; then
    echo "ERROR: $SKILLS_DIR not found."
    exit 1
fi

# Check that at least one SKILL.md exists
SKILL_COUNT=$(find "$SKILLS_DIR" -name "SKILL.md" | wc -l | tr -d ' ')
if [ "$SKILL_COUNT" -eq 0 ]; then
    echo "ERROR: No SKILL.md files found in $SKILLS_DIR."
    exit 1
fi

echo "Found $SKILL_COUNT skill(s) to deploy:"
find "$SKILLS_DIR" -name "SKILL.md" -exec dirname {} \; | xargs -I{} basename {}

RSYNC_FLAGS="-avz --delete"
if [[ "${1:-}" == "--dry-run" ]]; then
    RSYNC_FLAGS="$RSYNC_FLAGS --dry-run"
    echo "(dry run — no changes will be made)"
fi

echo ""
echo "Pushing skills to VPS..."
rsync $RSYNC_FLAGS "$SKILLS_DIR/" "$REMOTE"
echo "Done. Skills will be picked up on Jimbo's next session."
