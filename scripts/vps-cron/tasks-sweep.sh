#!/bin/bash
set -euo pipefail
# Google Tasks sweep - called by cron at 05:00 UTC

export $(grep -v "^#" /opt/openclaw.env | xargs)

docker exec \
  -e GOOGLE_CALENDAR_CLIENT_ID="$GOOGLE_CALENDAR_CLIENT_ID" \
  -e GOOGLE_CALENDAR_CLIENT_SECRET="$GOOGLE_CALENDAR_CLIENT_SECRET" \
  -e GOOGLE_CALENDAR_REFRESH_TOKEN="$GOOGLE_CALENDAR_REFRESH_TOKEN" \
  -e GOOGLE_AI_API_KEY="$GOOGLE_AI_API_KEY" \
  -e TELEGRAM_BOT_TOKEN="$TELEGRAM_BOT_TOKEN" \
  -e TELEGRAM_CHAT_ID="$TELEGRAM_CHAT_ID" \
  $(docker ps -q --filter name=openclaw-sbx) \
  sh -c 'python3 /workspace/tasks-helper.py pipeline || python3 /workspace/alert.py "05:00 tasks sweep FAILED"'
