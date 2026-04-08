#!/usr/bin/env bash
# Auto-rotate free models when rate-limited
# Runs on VPS via cron. Only acts when current model is a :free model.
# Checks OpenClaw logs for recent 429 errors and rotates to next free model.

set -euo pipefail

CONFIG="/home/openclaw/.openclaw/openclaw.json"
FREE_POS_FILE="/home/openclaw/.openclaw/free-model-position"
CURRENT_MODEL_FILE="/home/openclaw/.openclaw/workspace/current-model.txt"
LOG_TAG="[auto-rotate]"

# Free model stack — must match model-swap.sh
FREE_MODELS=(
  "google/gemma-4-31b-it:free"
  "qwen/qwen3-next-80b-a3b-instruct:free"
  "google/gemma-4-26b-a4b-it:free"
  "nvidia/nemotron-3-super-120b-a12b:free"
  "meta-llama/llama-3.3-70b-instruct:free"
  "stepfun/step-3.5-flash:free"
)

# Check current model — only act on free models
CURRENT=$(cat "$CURRENT_MODEL_FILE" 2>/dev/null || echo "unknown")
if [[ "$CURRENT" != *":free"* ]]; then
  exit 0
fi

# Check for 429s in the last 5 minutes
RECENT_429S=$(journalctl -u openclaw --since "5 min ago" --no-pager 2>/dev/null | grep -c "rate_limit\|429" || true)

if [ "$RECENT_429S" -lt 2 ]; then
  exit 0
fi

# Rate limited — rotate to next model
POS=$(cat "$FREE_POS_FILE" 2>/dev/null || echo 0)
NEXT_POS=$(( (POS + 1) % ${#FREE_MODELS[@]} ))
MODEL="${FREE_MODELS[$NEXT_POS]}"

echo "$LOG_TAG Rotating from $CURRENT to $MODEL (429 count: $RECENT_429S)"

python3 -c "
import json
with open('$CONFIG') as f:
    cfg = json.load(f)

models = cfg['models']['providers']['openrouter']['models']
ids = [m['id'] for m in models]
if '$MODEL' not in ids:
    models.append({
        'id': '$MODEL',
        'name': '$MODEL',
        'reasoning': False,
        'input': ['text'],
        'cost': {'input': 0, 'output': 0, 'cacheRead': 0, 'cacheWrite': 0},
        'contextWindow': 128000,
        'maxTokens': 8192
    })

cfg['agents']['defaults']['model']['primary'] = 'openrouter/$MODEL'

with open('$CONFIG', 'w') as f:
    json.dump(cfg, f, indent=2)
"

echo "$MODEL" > "$CURRENT_MODEL_FILE"
echo "$NEXT_POS" > "$FREE_POS_FILE"
systemctl restart openclaw

echo "$LOG_TAG Done. Now on $MODEL"
