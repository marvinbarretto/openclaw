#!/usr/bin/env bash
# Model swap helper for OpenClaw VPS
# Usage: ./model-swap.sh <tier>
#   free     - stepfun/step-3.5-flash:free (zero cost)
#   cheap    - google/gemini-2.5-flash-lite ($0.10/1M tokens)
#   coding   - qwen/qwen3-coder-next ($0.07/1M tokens)
#   claude   - anthropic/claude-sonnet-4-5 (premium, via Anthropic key)
#   opus     - anthropic/claude-opus-4-5 (max quality, expensive)
#
# Requires: SSH access to VPS as root

VPS="root@167.99.206.214"
CONFIG="/home/openclaw/.openclaw/openclaw.json"

case "$1" in
  free)    MODEL="openrouter/stepfun/step-3.5-flash:free" ;;
  cheap)   MODEL="openrouter/google/gemini-2.5-flash-lite" ;;
  coding)  MODEL="openrouter/qwen/qwen3-coder-next" ;;
  claude)  MODEL="anthropic/claude-sonnet-4-5" ;;
  opus)    MODEL="anthropic/claude-opus-4-5" ;;
  status)
    echo "Current model:"
    ssh "$VPS" "grep primary $CONFIG"
    exit 0
    ;;
  *)
    echo "Usage: $0 {free|cheap|coding|claude|opus|status}"
    echo ""
    echo "  free    stepfun/step-3.5-flash:free   \$0"
    echo "  cheap   google/gemini-2.5-flash-lite  ~\$0.10/1M tokens"
    echo "  coding  qwen/qwen3-coder-next         ~\$0.07/1M tokens"
    echo "  claude  claude-sonnet-4-5              premium"
    echo "  opus    claude-opus-4-5                max quality"
    echo "  status  show current model"
    exit 1
    ;;
esac

echo "Switching to: $MODEL"
ssh "$VPS" "sed -i 's|\"primary\": \"[^\"]*\"|\"primary\": \"$MODEL\"|' $CONFIG && systemctl restart openclaw"
echo "Done. Restarted OpenClaw."
