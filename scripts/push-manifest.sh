#!/usr/bin/env bash
# Push triage manifest to VPS for the triage UI.
#
# Usage: ./scripts/push-manifest.sh [--dry-run]
#
# Prerequisites:
#   - data/triage-manifest.json exists (run process-inbox.py --manifest first)
#   - SSH alias 'jimbo' configured

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MANIFEST="$REPO_ROOT/data/triage-manifest.json"
REMOTE="jimbo:/home/openclaw/.openclaw/workspace/triage/"

DRY_RUN=""
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN="--dry-run"
    echo "(dry run — no changes will be made)"
    echo ""
fi

if [ ! -f "$MANIFEST" ]; then
    echo "ERROR: Manifest not found: $MANIFEST"
    echo "Run: python3 scripts/process-inbox.py --manifest"
    exit 1
fi

# Show manifest stats
TOTAL=$(python3 -c "import json; print(json.load(open('$MANIFEST'))['total'])")
echo "Pushing manifest ($TOTAL items) to VPS..."

# Ensure remote directory exists
ssh jimbo "mkdir -p /home/openclaw/.openclaw/workspace/triage"

rsync -avz $DRY_RUN "$MANIFEST" "$REMOTE"

echo ""
echo "Done. Manifest available at /workspace/triage/triage-manifest.json"
