#!/usr/bin/env bash
# Sync the live OpenClaw cron job prompts on jimbo to explicit /workspace skill paths.
# This avoids native skill lookup resolving to /usr/lib/node_modules/openclaw/skills/...,
# which escapes the sandbox root for custom skills.
#
# Usage:
#   ./scripts/openclaw-cron-sync.sh
#   ./scripts/openclaw-cron-sync.sh --dry-run

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SPEC_PATH="$REPO_ROOT/setup/openclaw-cron-skills.json"
REMOTE_JOBS_PATH="/home/openclaw/.openclaw/cron/jobs.json"

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=1
fi

if [[ ! -f "$SPEC_PATH" ]]; then
    echo "ERROR: Spec not found: $SPEC_PATH" >&2
    exit 1
fi

SPEC_B64="$(python3 - "$SPEC_PATH" <<'PY'
import base64
import pathlib
import sys

print(base64.b64encode(pathlib.Path(sys.argv[1]).read_bytes()).decode("ascii"))
PY
)"

echo "Syncing OpenClaw cron skill prompts on jimbo..."
if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "(dry run — no remote changes will be written)"
fi

REMOTE_OUTPUT="$(ssh jimbo "python3 - '$REMOTE_JOBS_PATH' '$SPEC_B64' '$DRY_RUN' <<'PY'
import base64
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

jobs_path = Path(sys.argv[1])
spec = json.loads(base64.b64decode(sys.argv[2]))
dry_run = sys.argv[3] == '1'

data = json.loads(jobs_path.read_text())
original_text = json.dumps(data, indent=2) + '\n'
jobs = data.get('jobs', [])
expected = {entry['name']: entry['message'] for entry in spec.get('jobs', [])}

missing = []
changed = []

for name in expected:
    if not any(job.get('name') == name for job in jobs):
        missing.append(name)

for job in jobs:
    name = job.get('name')
    if name not in expected:
        continue
    payload = job.setdefault('payload', {})
    current = payload.get('message', '')
    target = expected[name]
    if current != target:
        changed.append({
            'name': name,
            'id': job.get('id'),
            'from': current,
            'to': target,
        })
        payload['message'] = target

if missing:
    print('Missing jobs:')
    for name in missing:
        print(f'  - {name}')

if changed:
    print('Updated jobs:')
    for item in changed:
        print(f\"  - {item['name']} ({item['id']})\")
        print(f\"    from: {item['from']}\")
        print(f\"    to:   {item['to']}\")
else:
    print('No message changes needed.')

if dry_run or not changed:
    print('RESULT=noop')
    sys.exit(0)

backup_name = jobs_path.with_name(
    jobs_path.name + '.bak-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
)
backup_name.write_text(original_text)
jobs_path.write_text(json.dumps(data, indent=2) + '\n')
print(f'Wrote {jobs_path}')
print(f'Backup: {backup_name}')
print('RESULT=changed')
PY")"

echo "$REMOTE_OUTPUT"

if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "Dry run complete."
    exit 0
fi

if [[ "$REMOTE_OUTPUT" != *"RESULT=changed"* ]]; then
    echo "No restart needed."
    exit 0
fi

echo "Restarting openclaw..."
ssh jimbo "systemctl restart openclaw && systemctl is-active --quiet openclaw"
echo "Done."
