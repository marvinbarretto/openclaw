#!/bin/bash
set -euo pipefail

# Opus briefing analysis — runs on Mac, pulls data from VPS, pushes analysis back.
# Exits silently on any failure — VPS fallback handles it.

SESSION="${1:-morning}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROMPT_DIR="$(dirname "$SCRIPT_DIR")/opus-prompts"

if [ ! -f "$PROMPT_DIR/${SESSION}.md" ]; then
    echo "Unknown session: $SESSION" >&2
    exit 1
fi

# Pull briefing-input.json from VPS
INPUT=$(ssh jimbo 'cat /home/openclaw/.openclaw/workspace/briefing-input.json' 2>/dev/null) || exit 0
[ -z "$INPUT" ] && exit 0

# Check it's for the right session
INPUT_SESSION=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('session',''))" 2>/dev/null) || exit 0
if [ "$INPUT_SESSION" != "$SESSION" ]; then
    echo "Input session ($INPUT_SESSION) doesn't match requested ($SESSION), skipping" >&2
    exit 0
fi

# Check it's fresh (less than 10 hours old — wide window so Mac can be asleep at cron time)
IS_FRESH=$(echo "$INPUT" | python3 -c "
import sys, json, datetime
d = json.load(sys.stdin)
gen = datetime.datetime.fromisoformat(d['generated_at'])
if gen.tzinfo is None:
    gen = gen.replace(tzinfo=datetime.timezone.utc)
age = (datetime.datetime.now(datetime.timezone.utc) - gen).total_seconds()
print('yes' if age < 36000 else 'no')
" 2>/dev/null) || exit 0

if [ "$IS_FRESH" != "yes" ]; then
    echo "briefing-input.json is stale, skipping" >&2
    exit 0
fi

# Run Opus analysis
PROMPT=$(cat "$PROMPT_DIR/${SESSION}.md")
ANALYSIS=$(echo "$INPUT" | claude -p "$PROMPT" 2>/dev/null) || exit 0

# Validate JSON and check required fields before pushing
echo "$ANALYSIS" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'day_plan' in d" 2>/dev/null || exit 0

# Push to VPS
echo "$ANALYSIS" | ssh jimbo 'cat > /home/openclaw/.openclaw/workspace/briefing-analysis.json' 2>/dev/null || exit 0

echo "Opus analysis pushed for $SESSION session"
