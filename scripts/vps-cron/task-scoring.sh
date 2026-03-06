#!/bin/bash
set -euo pipefail
# Vault task scoring - called by cron at 04:30 UTC

export $(grep -v "^#" /opt/openclaw.env | xargs)

docker exec \
  -e GOOGLE_AI_API_KEY="$GOOGLE_AI_API_KEY" \
  $(docker ps -q --filter name=openclaw-sbx) \
  python3 /workspace/prioritise-tasks.py
