#!/bin/bash
set -euo pipefail

# Push workspace files to VPS via rsync
# Usage: ./workspace-push.sh [--live]
# Default is dry-run; use --live to actually push

REMOTE_HOST="jimbo"
REMOTE_PATH="/home/openclaw/.openclaw/workspace/"
LOCAL_PATH="./workspace/"

DRY_RUN=true
if [[ "${1:-}" == "--live" ]]; then
  DRY_RUN=false
fi

RSYNC_ARGS=(
  -av
  --delete
)

if [[ "$DRY_RUN" == true ]]; then
  RSYNC_ARGS+=(--dry-run)
fi

# Exclude build artifacts and local-only files
RSYNC_ARGS+=(
  --exclude='__pycache__'
  --exclude='*.pyc'
  --exclude='.pytest_cache'
  --exclude='*.db'
  --exclude='.DS_Store'
  --exclude='tests/'
  --exclude='*.test.py'
)

# Exclude OpenClaw-managed directories (--delete must not wipe these)
RSYNC_ARGS+=(
  --exclude='.git'
  --exclude='.gitignore'
  --exclude='.openclaw'
  --exclude='.npm-cache'
  --exclude='skills/'
  --exclude='vault/'
  --exclude='memory/'
  --exclude='state/'
  --exclude='context/'
  --exclude='ssl-certs/'
  --exclude='AGENTS.md'
  --exclude='BOOTSTRAP.md'
  --exclude='IDENTITY.md'
  --exclude='MEMORY.md'
  --exclude='TOOLS.md'
  --exclude='USER.md'
  --exclude='current-model.txt'
  --exclude='.calendar-access-token*'
  --exclude='.gmail-access-token*'
  --exclude='.tasks-access-token*'
  --exclude='.tasks-last-fetch*'
  --exclude='.worker-shortlist*'
  --exclude='.worker-gems*'
  --exclude='blog-src/'
  --exclude='/*.json'
)

echo "Pushing workspace to $REMOTE_HOST:$REMOTE_PATH"
if [[ "$DRY_RUN" == true ]]; then
  echo "[DRY RUN] Use --live to actually push"
fi
echo ""

rsync "${RSYNC_ARGS[@]}" "$LOCAL_PATH" "$REMOTE_HOST:$REMOTE_PATH"

echo ""
if [[ "$DRY_RUN" == true ]]; then
  echo "Dry run complete. Use --live flag to push for real."
else
  echo "Push complete!"
fi
