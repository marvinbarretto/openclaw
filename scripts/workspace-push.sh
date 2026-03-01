#!/usr/bin/env bash
# Push all locally-maintained workspace files to VPS.
#
# This pushes:
#   workspace/SOUL.md, HEARTBEAT.md, TROUBLESHOOTING.md → /workspace/ (brain files)
#   workspace/*.py                   →  /workspace/         (helpers: cost-tracker, activity-log, etc.)
#   workspace/workers/               →  /workspace/workers/  (orchestrator worker scripts)
#   workspace/tasks/                 →  /workspace/tasks/    (task registry configs)
#   workspace/tests/                 →  /workspace/tests/    (worker test suite)
#   context/*.md                     →  /workspace/context/  (interests, priorities, taste, goals)
#   data/vault/notes/                →  /workspace/vault/notes/ (classified vault notes)
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
VAULT_NOTES_DIR="$REPO_ROOT/data/vault/notes"
REMOTE_BASE="jimbo:/home/openclaw/.openclaw/workspace"

DRY_RUN=""
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN="--dry-run"
    echo "(dry run — no changes will be made)"
    echo ""
fi

# --- Brain files (SOUL.md, HEARTBEAT.md) ---
BRAIN_FILES=(SOUL.md HEARTBEAT.md TROUBLESHOOTING.md)
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

# --- Worker directories (workers/, tasks/, tests/) ---
WORKER_DIRS=(workers tasks tests)
WORKER_DIR_COUNT=0
echo ""
echo "Worker directories:"
for d in "${WORKER_DIRS[@]}"; do
    if [ -d "$WORKSPACE_DIR/$d" ]; then
        FILE_COUNT=$(find "$WORKSPACE_DIR/$d" -type f | wc -l | tr -d ' ')
        echo "  $d/ ($FILE_COUNT files)"
        WORKER_DIR_COUNT=$((WORKER_DIR_COUNT + FILE_COUNT))
    else
        echo "  $d/ (not found, skipping)"
    fi
done

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

# --- Vault notes ---
VAULT_COUNT=0
if [ -d "$VAULT_NOTES_DIR" ]; then
    VAULT_COUNT=$(find "$VAULT_NOTES_DIR" -name "*.md" -type f | wc -l | tr -d ' ')
fi

echo ""
echo "Vault notes:"
if [ "$VAULT_COUNT" -gt 0 ]; then
    echo "  notes/ ($VAULT_COUNT files)"
else
    echo "  (not found or empty — skipping)"
fi

TOTAL=$((BRAIN_FOUND + ${#HELPER_FILES[@]} + WORKER_DIR_COUNT + CONTEXT_COUNT + VAULT_COUNT))
if [ "$TOTAL" -eq 0 ]; then
    echo ""
    echo "ERROR: Nothing to push."
    exit 1
fi

# --- Regenerate jimbo-status.json ---
echo ""
echo "Regenerating jimbo-status.json..."
python3 "$REPO_ROOT/scripts/export-status.py"

echo ""
echo "Pushing to VPS..."

# Push brain files + helper scripts in a single rsync (avoids SSH rate-limiting
# that killed individual scp calls — see ADR history / CLAUDE.md)
FLAT_FILES=()
for f in "${BRAIN_FILES[@]}"; do
    if [ -f "$WORKSPACE_DIR/$f" ]; then
        FLAT_FILES+=("$f")
    fi
done
for f in "${HELPER_FILES[@]}"; do
    FLAT_FILES+=("$f")
done
# Include generated status JSON
if [ -f "$WORKSPACE_DIR/jimbo-status.json" ]; then
    FLAT_FILES+=("jimbo-status.json")
fi

if [ ${#FLAT_FILES[@]} -gt 0 ]; then
    # Build rsync --include/--exclude to push only our files (not Jimbo's)
    INCLUDE_ARGS=()
    for f in "${FLAT_FILES[@]}"; do
        INCLUDE_ARGS+=(--include "$f")
    done
    echo "Pushing ${#FLAT_FILES[@]} workspace files..."
    rsync -avz "${INCLUDE_ARGS[@]}" --exclude '*' $DRY_RUN "$WORKSPACE_DIR/" "$REMOTE_BASE/"
fi

# Push worker directories (rsync with --delete so removed files get cleaned up)
for d in "${WORKER_DIRS[@]}"; do
    if [ -d "$WORKSPACE_DIR/$d" ]; then
        echo ""
        echo "Pushing $d/ ..."
        rsync -avz --delete $DRY_RUN "$WORKSPACE_DIR/$d/" "$REMOTE_BASE/$d/"
    fi
done

# Push context directory (backup only — Jimbo now reads context via API/context-helper.py,
# but we keep pushing files as a fallback in case the API is unavailable)
if [ "$CONTEXT_COUNT" -gt 0 ]; then
    echo ""
    echo "Pushing context/ (backup — primary source is now context API)..."
    rsync -avz --delete $DRY_RUN "$CONTEXT_DIR/" "$REMOTE_BASE/context/"
fi

# Push vault notes (rsync with --delete so removed/archived notes get cleaned up)
if [ "$VAULT_COUNT" -gt 0 ]; then
    echo ""
    echo "Pushing vault/notes/ ($VAULT_COUNT files)..."
    rsync -avz --delete $DRY_RUN "$VAULT_NOTES_DIR/" "$REMOTE_BASE/vault/notes/"
fi

echo ""
echo "Done. Changes take effect on Jimbo's next session (no restart needed)."
