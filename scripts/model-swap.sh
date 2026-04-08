#!/usr/bin/env bash
# Model swap helper for OpenClaw VPS
# Usage: ./model-swap.sh <tier>
#
# Tiers:
#   free     - rotate through free OpenRouter models (tracks position)
#   free-list - show the free model stack and current position
#   free-set N - jump to position N in the free stack
#   cheap    - google/gemini-2.5-flash-lite (direct Google AI, ~$0.24/month)
#   daily    - google/gemini-2.5-flash (direct Google AI, ~$0.78/month)
#   coding   - qwen/qwen3-coder-next (~$0.07/1M tokens)
#   haiku    - anthropic/claude-haiku-4.5 (~$2.49/month)
#   sonnet   - claude-sonnet-4-6 (~$4/month briefing window)
#   kimi     - moonshotai/kimi-k2 (~$1/month daily driver)
#   opus     - claude-opus-4-6 (max quality)
#   status   - show current model
#
# Requires: SSH access to VPS as root

set -euo pipefail

VPS="root@167.99.206.214"
CONFIG="/home/openclaw/.openclaw/openclaw.json"
FREE_POS_FILE="/home/openclaw/.openclaw/free-model-position"
CURRENT_MODEL_FILE="/home/openclaw/.openclaw/workspace/current-model.txt"

# Free model stack — ordered by preference (best first)
FREE_MODELS=(
  "google/gemma-4-31b-it:free"
  "qwen/qwen3-next-80b-a3b-instruct:free"
  "google/gemma-4-26b-a4b-it:free"
  "nvidia/nemotron-3-super-120b-a12b:free"
  "meta-llama/llama-3.3-70b-instruct:free"
  "stepfun/step-3.5-flash:free"
)

FREE_NAMES=(
  "Gemma 4 31B IT (262k ctx, multimodal)"
  "Qwen3 Next 80B (262k ctx)"
  "Gemma 4 26B MoE (262k ctx, multimodal)"
  "Nemotron 3 Super 120B (262k ctx)"
  "Llama 3.3 70B (65k ctx)"
  "Step 3.5 Flash (256k ctx)"
)

apply_model() {
  local model_id="$1"
  local provider_model="openrouter/$model_id"

  echo "Switching to: $provider_model"
  ssh "$VPS" "python3 -c '
import json
with open(\"$CONFIG\") as f:
    cfg = json.load(f)

models = cfg[\"models\"][\"providers\"][\"openrouter\"][\"models\"]
ids = [m[\"id\"] for m in models]
if \"$model_id\" not in ids:
    models.append({
        \"id\": \"$model_id\",
        \"name\": \"$model_id\",
        \"reasoning\": False,
        \"input\": [\"text\"],
        \"cost\": {\"input\": 0, \"output\": 0, \"cacheRead\": 0, \"cacheWrite\": 0},
        \"contextWindow\": 128000,
        \"maxTokens\": 8192
    })

cfg[\"agents\"][\"defaults\"][\"model\"][\"primary\"] = \"$provider_model\"

with open(\"$CONFIG\", \"w\") as f:
    json.dump(cfg, f, indent=2)
' && \
    echo '$model_id' > $CURRENT_MODEL_FILE && \
    systemctl restart openclaw
  "
  echo "Done. Model: $model_id"
}

case "${1:-}" in
  free)
    # Read current position, advance to next
    POS=$(ssh "$VPS" "cat $FREE_POS_FILE 2>/dev/null || echo 0")
    NEXT_POS=$(( (POS + 1) % ${#FREE_MODELS[@]} ))
    MODEL="${FREE_MODELS[$NEXT_POS]}"
    NAME="${FREE_NAMES[$NEXT_POS]}"

    echo "Free stack [$((NEXT_POS + 1))/${#FREE_MODELS[@]}]: $NAME"
    apply_model "$MODEL"
    ssh "$VPS" "echo $NEXT_POS > $FREE_POS_FILE"
    ;;

  free-list)
    POS=$(ssh "$VPS" "cat $FREE_POS_FILE 2>/dev/null || echo -1")
    echo "Free model stack:"
    for i in "${!FREE_MODELS[@]}"; do
      MARKER="  "
      if [ "$i" -eq "$POS" ]; then
        MARKER="→ "
      fi
      echo "  ${MARKER}$((i + 1)). ${FREE_NAMES[$i]}"
      echo "       ${FREE_MODELS[$i]}"
    done
    ;;

  free-set)
    N="${2:?Usage: model-swap.sh free-set N}"
    IDX=$((N - 1))
    if [ "$IDX" -lt 0 ] || [ "$IDX" -ge "${#FREE_MODELS[@]}" ]; then
      echo "Error: position must be 1-${#FREE_MODELS[@]}"
      exit 1
    fi
    MODEL="${FREE_MODELS[$IDX]}"
    NAME="${FREE_NAMES[$IDX]}"
    echo "Free stack [$N/${#FREE_MODELS[@]}]: $NAME"
    apply_model "$MODEL"
    ssh "$VPS" "echo $IDX > $FREE_POS_FILE"
    ;;

  cheap)   apply_model "google/gemini-2.5-flash-lite" ;;
  daily)   apply_model "google/gemini-2.5-flash" ;;
  gemma)   apply_model "google/gemma-4-31b-it:free" ;;
  coding)  apply_model "qwen/qwen3-coder-next" ;;
  haiku)   apply_model "anthropic/claude-haiku-4.5" ;;
  sonnet)  apply_model "anthropic/claude-sonnet-4-6" ;;
  kimi)    apply_model "moonshotai/kimi-k2" ;;
  opus)    apply_model "anthropic/claude-opus-4-6" ;;

  status)
    echo "Current model:"
    ssh "$VPS" "cat $CURRENT_MODEL_FILE 2>/dev/null || grep -o '\"primary\": \"[^\"]*\"' $CONFIG"
    ;;

  *)
    echo "Usage: $0 {free|free-list|free-set N|cheap|daily|coding|haiku|sonnet|kimi|opus|status}"
    echo ""
    echo "  Free tier (rotate through stack):"
    echo "    free       switch to next free model in stack"
    echo "    free-list  show the stack and current position"
    echo "    free-set N jump to position N"
    echo ""
    echo "  Paid tiers:"
    echo "    cheap   gemini-2.5-flash-lite    ~\$0.24/month"
    echo "    daily   gemini-2.5-flash         ~\$0.78/month"
    echo "    coding  qwen3-coder-next         ~\$0.07/1M tokens"
    echo "    haiku   claude-haiku-4.5         ~\$2.49/month"
    echo "    sonnet  claude-sonnet-4-6        ~\$4/month"
    echo "    kimi    kimi-k2                  ~\$1/month"
    echo "    opus    claude-opus-4-6          max quality"
    echo ""
    echo "  status  show current model"
    exit 1
    ;;
esac
