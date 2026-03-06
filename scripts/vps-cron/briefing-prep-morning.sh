#!/bin/bash
set -euo pipefail
# Morning briefing pipeline - called by cron at 06:15 UTC

export $(grep -v "^#" /opt/openclaw.env | xargs)

docker exec \
  -e GOOGLE_AI_API_KEY="$GOOGLE_AI_API_KEY" \
  -e ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
  -e GOOGLE_CALENDAR_CLIENT_ID="$GOOGLE_CALENDAR_CLIENT_ID" \
  -e GOOGLE_CALENDAR_CLIENT_SECRET="$GOOGLE_CALENDAR_CLIENT_SECRET" \
  -e GOOGLE_CALENDAR_REFRESH_TOKEN="$GOOGLE_CALENDAR_REFRESH_TOKEN" \
  -e TELEGRAM_BOT_TOKEN="$TELEGRAM_BOT_TOKEN" \
  -e TELEGRAM_CHAT_ID="$TELEGRAM_CHAT_ID" \
  -e LANGFUSE_PUBLIC_KEY="$LANGFUSE_PUBLIC_KEY" \
  -e LANGFUSE_SECRET_KEY="$LANGFUSE_SECRET_KEY" \
  -e LANGFUSE_HOST="$LANGFUSE_HOST" \
  $(docker ps -q --filter name=openclaw-sbx) \
  python3 /workspace/briefing-prep.py morning
