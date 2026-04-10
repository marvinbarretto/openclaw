#!/usr/bin/env python3
"""
Vault Triage Orchestration Cron Job

Runs the vault-triage workflow via jimbo_runtime.py:
1. Loads vault tasks from the vault
2. Classifies tasks by category
3. Routes to appropriate handler (delegate/review/decide)
4. Creates task records in jimbo-api
5. Sends Telegram notifications for awaiting_human tasks

Schedule: 0 9,15,18 * * *  (9am, 3pm, 6pm daily)
"""

import json
import subprocess
import sys
import os
from datetime import datetime
from pathlib import Path

# Paths
WORKSPACE_DIR = Path(__file__).parent
WORKFLOW_FILE = WORKSPACE_DIR / "workflows" / "vault-triage.json"
JIMBO_RUNTIME = WORKSPACE_DIR / "jimbo_runtime.py"
JIMBO_API_URL = os.getenv("JIMBO_API_URL", "http://localhost:3100/api/workflows")

def log(msg: str) -> None:
    """Log with timestamp."""
    print(f"[{datetime.now().isoformat()}] {msg}", file=sys.stderr)

def load_workflow() -> dict:
    """Load workflow definition."""
    if not WORKFLOW_FILE.exists():
        raise FileNotFoundError(f"Workflow file not found: {WORKFLOW_FILE}")

    with open(WORKFLOW_FILE) as f:
        return json.load(f)

def run_workflow_executor(workflow: dict) -> None:
    """Execute the workflow via jimbo_runtime.py."""
    log(f"Starting vault-triage orchestration (workflow_id={workflow['id']})")

    # Call jimbo_runtime.py as a subprocess
    # The executor handles task creation via HTTP to jimbo-api
    result = subprocess.run(
        [sys.executable, str(JIMBO_RUNTIME), str(WORKFLOW_FILE)],
        cwd=WORKSPACE_DIR,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        log(f"ERROR: jimbo_runtime.py failed with code {result.returncode}")
        log(f"STDERR: {result.stderr}")
        sys.exit(1)

    log(f"Workflow execution completed successfully")
    if result.stdout:
        log(f"Output: {result.stdout}")

def main() -> None:
    """Main orchestration entry point."""
    try:
        workflow = load_workflow()
        run_workflow_executor(workflow)
    except Exception as e:
        log(f"FATAL: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
