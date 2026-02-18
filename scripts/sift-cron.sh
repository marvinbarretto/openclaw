#!/usr/bin/env bash
# Automated Sift pipeline: sync email, classify, push digest to Jimbo.
# Designed to run via launchd (macOS) or cron.
#
# Usage:
#   ./scripts/sift-cron.sh              # full pipeline (sync + classify + push)
#   ./scripts/sift-cron.sh --no-sync    # skip mbsync, just reclassify and push
#
# Suggested launchd schedule: daily at 06:00
# See comments at bottom for launchd plist setup.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MAILDIR="$HOME/Mail/gmail/INBOX"
LOG_FILE="$REPO_ROOT/data/sift-cron.log"
HOURS=24

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

# Parse args
SKIP_SYNC=false
if [[ "${1:-}" == "--no-sync" ]]; then
    SKIP_SYNC=true
fi

log "=== Sift cron starting ==="

# Step 1: Sync email
if [ "$SKIP_SYNC" = false ]; then
    log "Syncing Gmail via mbsync..."
    if mbsync -a >> "$LOG_FILE" 2>&1; then
        log "mbsync complete"
    else
        log "ERROR: mbsync failed (exit $?). Continuing with existing Maildir."
    fi
else
    log "Skipping mbsync (--no-sync)"
fi

# Step 2: Check Ollama is running
if ! curl -s --max-time 3 http://localhost:11434/api/tags > /dev/null 2>&1; then
    log "ERROR: Ollama is not running. Start it with: ollama serve"
    exit 1
fi

# Step 3: Classify
log "Classifying emails from last ${HOURS}h..."
if python3 "$REPO_ROOT/scripts/sift-classify.py" \
    --input "$MAILDIR" \
    --hours "$HOURS" \
    --output data/email-digest.json >> "$LOG_FILE" 2>&1; then
    log "Classification complete"
else
    log "ERROR: sift-classify.py failed (exit $?)"
    exit 1
fi

# Step 4: Push to VPS
log "Pushing digest to Jimbo..."
if "$REPO_ROOT/scripts/sift-push.sh" >> "$LOG_FILE" 2>&1; then
    log "Digest pushed to VPS"
else
    log "ERROR: sift-push.sh failed (exit $?). VPS may be unreachable."
    exit 1
fi

log "=== Sift cron complete ==="

# --- launchd setup (macOS) ---
# Save this as ~/Library/LaunchAgents/com.openclaw.sift-cron.plist:
#
# <?xml version="1.0" encoding="UTF-8"?>
# <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
# <plist version="1.0">
# <dict>
#     <key>Label</key>
#     <string>com.openclaw.sift-cron</string>
#     <key>ProgramArguments</key>
#     <array>
#         <string>/Users/marvinbarretto/development/openclaw/scripts/sift-cron.sh</string>
#     </array>
#     <key>StartCalendarInterval</key>
#     <dict>
#         <key>Hour</key>
#         <integer>6</integer>
#         <key>Minute</key>
#         <integer>0</integer>
#     </dict>
#     <key>StandardOutPath</key>
#     <string>/Users/marvinbarretto/development/openclaw/data/sift-cron-stdout.log</string>
#     <key>StandardErrorPath</key>
#     <string>/Users/marvinbarretto/development/openclaw/data/sift-cron-stderr.log</string>
#     <key>EnvironmentVariables</key>
#     <dict>
#         <key>PATH</key>
#         <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
#     </dict>
# </dict>
# </plist>
#
# To install:
#   launchctl load ~/Library/LaunchAgents/com.openclaw.sift-cron.plist
#
# To test immediately:
#   launchctl start com.openclaw.sift-cron
#
# To uninstall:
#   launchctl unload ~/Library/LaunchAgents/com.openclaw.sift-cron.plist
