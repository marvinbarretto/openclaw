#!/usr/bin/env bash
# Model swap — VPS-local version (for crontab use ON the VPS)
# Unlike model-swap.sh which SSHes in, this runs directly on the VPS.
#
# Usage: model-swap-local.sh <tier>
# Install: rsync to VPS, add to root crontab

set -euo pipefail

CONFIG="/home/openclaw/.openclaw/openclaw.json"

case "${1:-}" in
  free)    MODEL="openrouter/stepfun/step-3.5-flash:free" ;;
  cheap)   MODEL="google/gemini-2.5-flash-lite" ;;
  daily)   MODEL="google/gemini-2.5-flash" ;;
  coding)  MODEL="openrouter/qwen/qwen3-coder-next" ;;
  haiku)   MODEL="openrouter/anthropic/claude-haiku-4.5" ;;
  claude)  MODEL="anthropic/claude-sonnet-4-5" ;;
  opus)    MODEL="anthropic/claude-opus-4-5" ;;
  status)
    echo "Current model:"
    grep primary "$CONFIG"
    exit 0
    ;;
  *)
    echo "Usage: $0 {free|cheap|daily|coding|haiku|claude|opus|status}"
    exit 1
    ;;
esac

echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) Switching to: $MODEL"
sed -i "s|\"primary\": \"[^\"]*\"|\"primary\": \"$MODEL\"|" "$CONFIG"
systemctl restart openclaw
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) Done."
