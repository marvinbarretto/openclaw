#!/usr/bin/env bash
# Push email-digest.json to VPS for Jimbo to read.
# Usage: ./scripts/sift-push.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIGEST="$REPO_ROOT/data/email-digest.json"
REMOTE="jimbo:/home/openclaw/.openclaw/workspace/email-digest.json"

if [ ! -f "$DIGEST" ]; then
    echo "ERROR: $DIGEST not found. Run sift-classify.py first."
    exit 1
fi

echo "Pushing email-digest.json to VPS..."
rsync -avz "$DIGEST" "$REMOTE"
echo "Done. Jimbo can now read the digest."
