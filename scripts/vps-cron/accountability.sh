#!/bin/bash
set -euo pipefail
# Daily accountability report - called by cron at 20:00 UTC

export $(grep -v "^#" /opt/openclaw.env | xargs)

docker exec \
  -e TELEGRAM_BOT_TOKEN="$TELEGRAM_BOT_TOKEN" \
  -e TELEGRAM_CHAT_ID="$TELEGRAM_CHAT_ID" \
  -e JIMBO_API_URL="$JIMBO_API_URL" \
  -e JIMBO_API_KEY="$JIMBO_API_KEY" \
  $(docker ps -q --filter name=openclaw-sbx) \
  python3 /workspace/accountability-check.py
