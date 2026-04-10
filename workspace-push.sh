#!/bin/bash
set -euo pipefail

# Push workspace files to VPS via rsync
# Usage: ./workspace-push.sh [--live]
# Default is dry-run; use --live to actually push

REMOTE_HOST="jimbo"
REMOTE_PATH="/home/openclaw/workspace/"
LOCAL_PATH="./workspace/"

DRY_RUN=true
if [[ "${1:-}" == "--live" ]]; then
  DRY_RUN=false
fi

# Build rsync command
RSYNC_CMD="rsync -av --delete"
if [[ "$DRY_RUN" == true ]]; then
  RSYNC_CMD="$RSYNC_CMD --dry-run"
fi

# Exclude patterns (don't sync these)
RSYNC_CMD="$RSYNC_CMD \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.pytest_cache' \
  --exclude='*.db' \
  --exclude='.DS_Store' \
  --exclude='tests/' \
  --exclude='*.test.py' \
  "

echo "Pushing workspace to $REMOTE_HOST:$REMOTE_PATH"
if [[ "$DRY_RUN" == true ]]; then
  echo "[DRY RUN] Use --live to actually push"
fi
echo ""

$RSYNC_CMD "$LOCAL_PATH" "$REMOTE_HOST:$REMOTE_PATH"

echo ""
if [[ "$DRY_RUN" == true ]]; then
  echo "Dry run complete. Use --live flag to push for real."
else
  echo "Push complete!"
fi
