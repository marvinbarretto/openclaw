#!/usr/bin/env bash
# Deploy Google Calendar credentials and helper script to VPS.
#
# Prerequisites:
#   1. Run calendar-auth.py first to generate data/.calendar-tokens.json
#   2. SSH alias 'jimbo' must be configured
#
# Usage: ./scripts/calendar-setup.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TOKENS_FILE="$REPO_ROOT/data/.calendar-tokens.json"
HELPER_SCRIPT="$REPO_ROOT/workspace/calendar-helper.py"
REMOTE_ENV="/opt/openclaw.env"
REMOTE_WORKSPACE="jimbo:/home/openclaw/.openclaw/workspace/calendar-helper.py"

# --- Check prerequisites ---

if [ ! -f "$TOKENS_FILE" ]; then
    echo "ERROR: $TOKENS_FILE not found."
    echo "Run calendar-auth.py first:"
    echo "  python3 scripts/calendar-auth.py --client-id YOUR_ID --client-secret YOUR_SECRET"
    exit 1
fi

if [ ! -f "$HELPER_SCRIPT" ]; then
    echo "ERROR: $HELPER_SCRIPT not found."
    exit 1
fi

# --- Read credentials ---

CLIENT_ID=$(python3 -c "import json; print(json.load(open('$TOKENS_FILE'))['client_id'])")
CLIENT_SECRET=$(python3 -c "import json; print(json.load(open('$TOKENS_FILE'))['client_secret'])")
REFRESH_TOKEN=$(python3 -c "import json; print(json.load(open('$TOKENS_FILE'))['refresh_token'])")

echo "Read credentials from $TOKENS_FILE"
echo "  Client ID: ${CLIENT_ID:0:20}..."
echo "  Refresh token: ${REFRESH_TOKEN:0:20}..."
echo ""

# --- Check if already deployed ---

echo "Checking if calendar env vars already exist on VPS..."
EXISTING=$(ssh jimbo "grep -c 'GOOGLE_CALENDAR_' $REMOTE_ENV 2>/dev/null || echo 0")

if [ "$EXISTING" -gt 0 ]; then
    echo "WARNING: Found $EXISTING existing GOOGLE_CALENDAR_ entries in $REMOTE_ENV"
    echo "Remove them first if you want to re-deploy:"
    echo "  ssh jimbo \"sed -i '/^GOOGLE_CALENDAR_/d' $REMOTE_ENV\""
    echo ""
    read -p "Continue anyway and append? (y/N) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 1
    fi
fi

# --- Deploy env vars ---

echo "Adding calendar credentials to $REMOTE_ENV on VPS..."
ssh jimbo "cat >> $REMOTE_ENV" <<EOF

# Google Calendar API (added $(date +%Y-%m-%d))
GOOGLE_CALENDAR_CLIENT_ID=$CLIENT_ID
GOOGLE_CALENDAR_CLIENT_SECRET=$CLIENT_SECRET
GOOGLE_CALENDAR_REFRESH_TOKEN=$REFRESH_TOKEN
EOF

echo "  Done."
echo ""

# --- Deploy helper script ---

echo "Copying calendar-helper.py to VPS workspace..."
scp "$HELPER_SCRIPT" "$REMOTE_WORKSPACE"
echo "  Done."
echo ""

# --- Print manual config steps ---

echo "==========================================="
echo "  MANUAL STEPS REQUIRED"
echo "==========================================="
echo ""
echo "1. Add these to the docker.env section of openclaw.json:"
echo ""
echo "   ssh jimbo"
echo "   nano /home/openclaw/.openclaw/openclaw.json"
echo ""
echo "   In agents.defaults.sandbox.docker.env, add:"
echo ""
cat <<'JSONEOF'
   "GOOGLE_CALENDAR_CLIENT_ID": "${GOOGLE_CALENDAR_CLIENT_ID}",
   "GOOGLE_CALENDAR_CLIENT_SECRET": "${GOOGLE_CALENDAR_CLIENT_SECRET}",
   "GOOGLE_CALENDAR_REFRESH_TOKEN": "${GOOGLE_CALENDAR_REFRESH_TOKEN}"
JSONEOF
echo ""
echo "2. Restart OpenClaw:"
echo ""
echo "   ssh jimbo \"systemctl daemon-reload && systemctl restart openclaw\""
echo ""
echo "3. Verify (check for config errors):"
echo ""
echo "   ssh jimbo \"journalctl -u openclaw -n 15 --no-pager\""
echo ""
echo "4. Test via Telegram: message Jimbo 'What's on my calendar this week?'"
echo ""
