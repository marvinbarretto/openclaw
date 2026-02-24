#!/usr/bin/env bash
# Pull triage decisions from VPS after UI review.
#
# Usage: ./scripts/pull-decisions.sh [--dry-run]
#
# Prerequisites:
#   - SSH alias 'jimbo' configured
#   - Decisions file exists on VPS (created by triage UI)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REMOTE="jimbo:/home/openclaw/.openclaw/workspace/triage/decisions.json"
LOCAL="$REPO_ROOT/data/triage-decisions.json"

DRY_RUN=""
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN="--dry-run"
    echo "(dry run — no changes will be made)"
    echo ""
fi

echo "Pulling decisions from VPS..."

rsync -avz $DRY_RUN "$REMOTE" "$LOCAL"

if [ -z "$DRY_RUN" ] && [ -f "$LOCAL" ]; then
    COUNT=$(python3 -c "import json; print(len(json.load(open('$LOCAL')).get('decisions', [])))")
    echo ""
    echo "Done. $COUNT decisions saved to $LOCAL"
    echo "Apply with: python3 scripts/apply-decisions.py --dry-run"
fi
