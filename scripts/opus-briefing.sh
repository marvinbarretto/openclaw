#!/bin/bash
set -euo pipefail

# Opus briefing analysis — runs on Mac, pulls data from VPS, pushes analysis to jimbo-api.
# Logs errors to stderr (visible in launchd logs). Sends Telegram alert on failure.

SESSION="${1:-morning}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROMPT_DIR="$(dirname "$SCRIPT_DIR")/opus-prompts"

# Required env vars
: "${JIMBO_API_KEY:?JIMBO_API_KEY not set}"
API_URL="https://167.99.206.214/api"

send_alert() {
    local msg="$1"
    if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
        curl -sf -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
            -d chat_id="$TELEGRAM_CHAT_ID" \
            -d text="[opus-briefing] $msg" \
            -d parse_mode=HTML >/dev/null 2>&1 || true
    fi
}

if [ ! -f "$PROMPT_DIR/${SESSION}.md" ]; then
    echo "ERROR: Unknown session: $SESSION" >&2
    exit 1
fi

# Pull briefing-input.json from VPS
echo "Pulling briefing-input.json for $SESSION..." >&2
INPUT=$(ssh jimbo 'cat /home/openclaw/.openclaw/workspace/briefing-input.json' 2>/dev/null) || {
    echo "ERROR: Failed to pull briefing-input.json" >&2
    send_alert "Failed to pull briefing-input.json from VPS"
    exit 1
}
[ -z "$INPUT" ] && { echo "ERROR: briefing-input.json is empty" >&2; send_alert "briefing-input.json is empty"; exit 1; }

# Check it's for the right session
INPUT_SESSION=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('session',''))" 2>/dev/null) || {
    echo "ERROR: Failed to parse session from input" >&2; exit 1
}
if [ "$INPUT_SESSION" != "$SESSION" ]; then
    echo "Input session ($INPUT_SESSION) doesn't match requested ($SESSION), skipping" >&2
    exit 0
fi

# Check it's fresh (less than 10 hours old)
IS_FRESH=$(echo "$INPUT" | python3 -c "
import sys, json, datetime
d = json.load(sys.stdin)
gen = datetime.datetime.fromisoformat(d['generated_at'])
if gen.tzinfo is None:
    gen = gen.replace(tzinfo=datetime.timezone.utc)
age = (datetime.datetime.now(datetime.timezone.utc) - gen).total_seconds()
print('yes' if age < 36000 else 'no')
" 2>/dev/null) || { echo "ERROR: Failed to check freshness" >&2; exit 1; }

if [ "$IS_FRESH" != "yes" ]; then
    echo "briefing-input.json is stale, skipping" >&2
    exit 0
fi

# Run Opus analysis
echo "Running Opus analysis for $SESSION..." >&2
PROMPT=$(cat "$PROMPT_DIR/${SESSION}.md")
ANALYSIS=$(echo "$INPUT" | claude -p "$PROMPT" 2>/dev/null) || {
    echo "ERROR: claude -p failed" >&2
    send_alert "Opus analysis failed (claude -p error) for $SESSION"
    exit 1
}

# Validate JSON
echo "$ANALYSIS" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'day_plan' in d" 2>/dev/null || {
    echo "ERROR: Opus output is not valid JSON or missing day_plan" >&2
    send_alert "Opus output validation failed for $SESSION"
    exit 1
}

# POST to jimbo-api
echo "Posting analysis to jimbo-api..." >&2
HTTP_CODE=$(echo "$ANALYSIS" | curl -sk -o /dev/null -w '%{http_code}' \
    -X POST \
    -H "X-API-Key: $JIMBO_API_KEY" \
    -H "Content-Type: application/json" \
    -d @- \
    "$API_URL/briefing/analysis") || {
    echo "ERROR: Failed to POST to jimbo-api" >&2
    send_alert "Failed to POST analysis to jimbo-api for $SESSION"
    exit 1
}

if [ "$HTTP_CODE" != "201" ]; then
    echo "ERROR: jimbo-api returned $HTTP_CODE" >&2
    send_alert "jimbo-api returned HTTP $HTTP_CODE for $SESSION analysis POST"
    exit 1
fi

echo "Opus analysis posted for $SESSION session (HTTP $HTTP_CODE)" >&2
