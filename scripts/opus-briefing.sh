#!/bin/bash
set -euo pipefail

# Opus briefing analysis — runs on Mac, pulls data from VPS, pushes analysis to jimbo-api.
# Logs errors to stderr (visible in launchd logs). Sends Telegram alert on failure.
# Reports status to /api/pipeline/runs/opus-status for health dashboard visibility.

SESSION="${1:-morning}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROMPT_DIR="$(dirname "$SCRIPT_DIR")/opus-prompts"
MAX_WAIT_SECONDS="${MAX_WAIT_SECONDS:-4200}"
POLL_INTERVAL_SECONDS="${POLL_INTERVAL_SECONDS:-120}"

# Source secrets from env file (mirrors VPS pattern with /opt/openclaw.env)
ENV_FILE="${OPENCLAW_ENV:-$HOME/.openclaw-env}"
if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck source=/dev/null
    source "$ENV_FILE"
    set +a
fi

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

report_opus_status() {
    local status="$1"
    local error="${2:-}"
    local posted_at="${3:-}"

    local body
    if [ -n "$error" ] && [ -n "$posted_at" ]; then
        body="{\"status\":\"$status\",\"error\":$(python3 -c "import json; print(json.dumps('$error'))"),\"posted_at\":\"$posted_at\"}"
    elif [ -n "$error" ]; then
        body="{\"status\":\"$status\",\"error\":$(python3 -c "import json; print(json.dumps('$error'))")}"
    elif [ -n "$posted_at" ]; then
        body="{\"status\":\"$status\",\"posted_at\":\"$posted_at\"}"
    else
        body="{\"status\":\"$status\"}"
    fi

    curl -sk -X PUT \
        -H "X-API-Key: $JIMBO_API_KEY" \
        -H "Content-Type: application/json" \
        -d "$body" \
        "$API_URL/pipeline/runs/opus-status?session=$SESSION" >/dev/null 2>&1 || true
}

if [ ! -f "$PROMPT_DIR/${SESSION}.md" ]; then
    echo "ERROR: Unknown session: $SESSION" >&2
    exit 1
fi

wait_deadline=$(( $(date +%s) + MAX_WAIT_SECONDS ))
INPUT=""

while true; do
    echo "Pulling briefing-input.json for $SESSION..." >&2
    INPUT=$(ssh jimbo 'cat /home/openclaw/.openclaw/workspace/briefing-input.json' 2>/dev/null || true)

    if [ -n "$INPUT" ]; then
        INPUT_STATE=$(echo "$INPUT" | python3 -c "
import sys, json, datetime
target = sys.argv[1]
try:
    data = json.load(sys.stdin)
except Exception:
    print('invalid-json')
    raise SystemExit(0)
session = data.get('session', '')
if session != target:
    print(f'wrong-session:{session}')
    raise SystemExit(0)
generated_at = data.get('generated_at')
if not generated_at:
    print('missing-generated-at')
    raise SystemExit(0)
try:
    gen = datetime.datetime.fromisoformat(generated_at)
except Exception:
    print('invalid-generated-at')
    raise SystemExit(0)
if gen.tzinfo is None:
    gen = gen.replace(tzinfo=datetime.timezone.utc)
age = (datetime.datetime.now(datetime.timezone.utc) - gen).total_seconds()
print('ok' if age < 36000 else 'stale')
" "$SESSION" 2>/dev/null || true)

        if [ "$INPUT_STATE" = "ok" ]; then
            break
        fi
        echo "Waiting for fresh $SESSION input ($INPUT_STATE)" >&2
    else
        echo "Waiting for briefing-input.json to appear" >&2
    fi

    if [ "$(date +%s)" -ge "$wait_deadline" ]; then
        echo "ERROR: Timed out waiting for fresh $SESSION briefing-input.json" >&2
        send_alert "Timed out waiting for fresh $SESSION briefing-input.json"
        report_opus_status "timeout" "Timed out waiting for fresh briefing-input.json ($INPUT_STATE)"
        exit 1
    fi

    sleep "$POLL_INTERVAL_SECONDS"
done

# Run Opus analysis
echo "Running Opus analysis for $SESSION..." >&2
PROMPT=$(cat "$PROMPT_DIR/${SESSION}.md")
ANALYSIS=$(echo "$INPUT" | claude -p "$PROMPT" 2>/dev/null) || {
    echo "ERROR: claude -p failed" >&2
    send_alert "Opus analysis failed (claude -p error) for $SESSION"
    report_opus_status "claude_error" "claude -p returned non-zero"
    exit 1
}

# Validate JSON
echo "$ANALYSIS" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'day_plan' in d" 2>/dev/null || {
    echo "ERROR: Opus output is not valid JSON or missing day_plan" >&2
    send_alert "Opus output validation failed for $SESSION"
    report_opus_status "validation_error" "Output not valid JSON or missing day_plan"
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
    report_opus_status "failed" "curl failed to POST analysis"
    exit 1
}

if [ "$HTTP_CODE" != "200" ] && [ "$HTTP_CODE" != "201" ]; then
    echo "ERROR: jimbo-api returned $HTTP_CODE" >&2
    send_alert "jimbo-api returned HTTP $HTTP_CODE for $SESSION analysis POST"
    report_opus_status "auth_error" "jimbo-api returned HTTP $HTTP_CODE"
    exit 1
fi

POSTED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
report_opus_status "posted" "" "$POSTED_AT"
echo "Opus analysis posted for $SESSION session (HTTP $HTTP_CODE)" >&2
