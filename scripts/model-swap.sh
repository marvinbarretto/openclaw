#!/usr/bin/env bash
# Model swap helper for OpenClaw VPS
# Usage: ./model-swap.sh <tier>
#   free     - stepfun/step-3.5-flash:free (zero cost)
#   cheap    - google/gemini-2.5-flash-lite (direct Google AI, ~$0.24/month)
#   daily    - google/gemini-2.5-flash (direct Google AI, ~$0.78/month)
#   coding   - qwen/qwen3-coder-next (~$0.07/1M tokens)
#   haiku    - anthropic/claude-haiku-4.5 (~$2.49/month)
#   sonnet   - claude-sonnet-4-6 (~$4/month briefing window)
#   kimi     - moonshotai/kimi-k2 (~$1/month daily driver)
#   opus     - claude-opus-4-6 (max quality)
#
# Recommended for daily briefings: "daily" (Gemini 2.5 Flash)
# Requires: SSH access to VPS as root

set -euo pipefail

VPS="root@167.99.206.214"
CONFIG="/home/openclaw/.openclaw/openclaw.json"

case "${1:-}" in
  free)    MODEL="openrouter/stepfun/step-3.5-flash:free" ;;
  cheap)   MODEL="google/gemini-2.5-flash-lite" ;;
  daily)   MODEL="google/gemini-2.5-flash" ;;
  coding)  MODEL="openrouter/qwen/qwen3-coder-next" ;;
  haiku)   MODEL="openrouter/anthropic/claude-haiku-4.5" ;;
  sonnet)  MODEL="openrouter/anthropic/claude-sonnet-4-6" ;;
  kimi)    MODEL="openrouter/moonshotai/kimi-k2" ;;
  opus)    MODEL="openrouter/anthropic/claude-opus-4-6" ;;
  status)
    echo "Current model:"
    ssh "$VPS" "grep primary $CONFIG"
    exit 0
    ;;
  *)
    echo "Usage: $0 {free|cheap|daily|coding|haiku|sonnet|kimi|opus|status}"
    echo ""
    echo "  free    stepfun/step-3.5-flash:free     \$0"
    echo "  cheap   google/gemini-2.5-flash-lite    ~\$0.24/month  (direct Google AI)"
    echo "  daily   google/gemini-2.5-flash         ~\$0.78/month  (direct Google AI)"
    echo "  coding  qwen/qwen3-coder-next           ~\$0.07/1M tokens"
    echo "  haiku   anthropic/claude-haiku-4.5      ~\$2.49/month"
    echo "  sonnet  claude-sonnet-4-6               ~\$4/month (briefing window)"
    echo "  kimi    moonshotai/kimi-k2              ~\$1/month (daily driver)"
    echo "  opus    claude-opus-4-6                 max quality"
    echo "  status  show current model"
    exit 1
    ;;
esac

echo "Switching to: $MODEL"
ssh "$VPS" "sed -i 's|\"primary\": \"[^\"]*\"|\"primary\": \"$MODEL\"|' $CONFIG && systemctl restart openclaw"
echo "Done. Restarted OpenClaw."
