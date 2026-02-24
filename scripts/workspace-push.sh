#!/usr/bin/env bash
# Push all locally-maintained workspace files to VPS.
#
# This pushes:
#   workspace/SOUL.md, HEARTBEAT.md  →  /workspace/         (brain files)
#   workspace/*.py                   →  /workspace/         (helpers: cost-tracker, activity-log, etc.)
#   context/*.md                     →  /workspace/context/  (interests, priorities, taste, goals)
#
# Files Jimbo writes himself (IDENTITY.md, USER.md, MEMORY.md, JIMBO_DIARY.md)
# are NOT tracked here and won't be overwritten.
#
# Usage: ./scripts/workspace-push.sh [--dry-run]
#
# No restart needed — changes take effect on Jimbo's next session.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORKSPACE_DIR="$REPO_ROOT/workspace"
CONTEXT_DIR="$REPO_ROOT/context"
REMOTE_BASE="jimbo:/home/openclaw/.openclaw/workspace"

DRY_RUN=""
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN="--dry-run"
    echo "(dry run — no changes will be made)"
    echo ""
fi

# --- Brain files (SOUL.md, HEARTBEAT.md) ---
BRAIN_FILES=(SOUL.md HEARTBEAT.md)
BRAIN_FOUND=0

echo "Brain files:"
for f in "${BRAIN_FILES[@]}"; do
    if [ -f "$WORKSPACE_DIR/$f" ]; then
        echo "  $f"
        BRAIN_FOUND=$((BRAIN_FOUND + 1))
    else
        echo "  $f (not found, skipping)"
    fi
done

# --- Helper scripts (*.py) ---
HELPER_FILES=()
for f in "$WORKSPACE_DIR"/*.py; do
    if [ -f "$f" ]; then
        HELPER_FILES+=("$(basename "$f")")
    fi
done

echo ""
echo "Helper scripts:"
if [ ${#HELPER_FILES[@]} -gt 0 ]; then
    for f in "${HELPER_FILES[@]}"; do
        echo "  $f"
    done
else
    echo "  (none found)"
fi

# --- Context files ---
CONTEXT_COUNT=0
if [ -d "$CONTEXT_DIR" ]; then
    CONTEXT_COUNT=$(find "$CONTEXT_DIR" -name "*.md" | wc -l | tr -d ' ')
fi

echo ""
echo "Context files:"
if [ "$CONTEXT_COUNT" -gt 0 ]; then
    for f in "$CONTEXT_DIR"/*.md; do
        echo "  $(basename "$f")"
    done
else
    echo "  (none found)"
fi

TOTAL=$((BRAIN_FOUND + ${#HELPER_FILES[@]} + CONTEXT_COUNT))
if [ "$TOTAL" -eq 0 ]; then
    echo ""
    echo "ERROR: Nothing to push."
    exit 1
fi

echo ""
echo "Pushing to VPS..."

# Push brain files individually (don't clobber Jimbo's files)
for f in "${BRAIN_FILES[@]}"; do
    if [ -f "$WORKSPACE_DIR/$f" ]; then
        if [[ -n "$DRY_RUN" ]]; then
            echo "  Would push: $f → /workspace/$f"
        else
            scp "$WORKSPACE_DIR/$f" "$REMOTE_BASE/$f"
            echo "  Pushed: $f"
        fi
    fi
done

# Push helper scripts individually (same approach as brain files)
if [ ${#HELPER_FILES[@]} -gt 0 ]; then
    echo ""
    echo "Pushing helper scripts..."
    for f in "${HELPER_FILES[@]}"; do
        if [[ -n "$DRY_RUN" ]]; then
            echo "  Would push: $f → /workspace/$f"
        else
            scp "$WORKSPACE_DIR/$f" "$REMOTE_BASE/$f"
            echo "  Pushed: $f"
        fi
    done
fi

# Push context directory (rsync with --delete so removed files get cleaned up)
if [ "$CONTEXT_COUNT" -gt 0 ]; then
    echo ""
    echo "Pushing context/ ..."
    rsync -avz --delete $DRY_RUN "$CONTEXT_DIR/" "$REMOTE_BASE/context/"
fi

echo ""
echo "Done. Changes take effect on Jimbo's next session (no restart needed)."
