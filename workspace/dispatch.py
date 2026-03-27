#!/usr/bin/env python3
"""
Dispatch proposer — runs on VPS, proposes batches and sends Telegram notifications.

The M2 worker (dispatch-worker.py) handles actual task execution.
This script handles the queue management side:
  - Proposing batches from ready vault tasks
  - Sending Telegram notifications for proposals and completions
  - Monitoring for timeouts on running tasks
  - Expiring stale proposals

Usage:
  python3 dispatch.py              # dry-run (default)
  python3 dispatch.py --live       # actually propose and notify
  python3 dispatch.py --status     # show current queue state

North Star: Approach 3 upgrades to persistent daemon, inline keyboards,
richer Telegram interactions.
"""

import datetime
import fcntl
import json
import os
import sys
import urllib.request
import urllib.error

# --- Configuration ---

API_URL = os.environ.get('JIMBO_API_URL', 'http://localhost:3100')
API_KEY = os.environ.get('JIMBO_API_KEY', os.environ.get('API_KEY', ''))
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')
LOCK_FILE = '/tmp/dispatch.lock'
DEFAULT_BATCH_SIZE = 3

# Timeout limits — if a task has been running longer than this, mark it failed
TIMEOUTS = {'coder': 1800, 'researcher': 900, 'drafter': 1200}  # seconds


# --- Utility functions ---

def log(msg):
    sys.stderr.write(f'[dispatch] {msg}\n')


def api_request(method, path, body=None):
    """Make an authenticated request to jimbo-api."""
    url = f'{API_URL}{path}'
    data = json.dumps(body).encode() if body else None
    headers = {'X-API-Key': API_KEY, 'Accept': 'application/json'}
    if data:
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode() if e.fp else ''
        log(f'API error: {method} {path} -> {e.code}: {body_text[:200]}')
        return None
    except Exception as e:
        log(f'API request failed: {method} {path} -> {e}')
        return None


def send_telegram(message):
    """Send a Telegram message. Fire-and-forget."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log('Telegram not configured, skipping notification')
        return False
    url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'
    payload = json.dumps({
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': 'HTML',
        'disable_web_page_preview': True,
    }).encode()
    req = urllib.request.Request(url, data=payload,
        headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        log(f'Telegram send failed: {e}')
        return False


# --- Core logic ---

def check_timeouts(dry_run=False):
    """Check for running tasks that have exceeded their timeout."""
    status = api_request('GET', '/api/dispatch/status')
    if not status or not status.get('running'):
        return False

    task = status['running']
    task_id = task['task_id']
    timeout = TIMEOUTS.get(task['agent_type'], 1800)
    started = task.get('started_at', '')

    if not started:
        return True  # running but no start time — leave it for now

    try:
        started_dt = datetime.datetime.fromisoformat(started.replace(' ', 'T'))
        elapsed = (datetime.datetime.utcnow() - started_dt).total_seconds()
        if elapsed > timeout:
            log(f'Task {task_id} timed out after {int(elapsed)}s (limit: {timeout}s)')
            if not dry_run:
                api_request('POST', '/api/dispatch/fail', {
                    'id': task['id'],
                    'error_message': f'Timeout after {int(elapsed)}s (limit: {timeout}s for {task["agent_type"]})',
                })
                send_telegram(f'[Dispatch] Timeout: {task_id} after {int(elapsed)}s')
            return False  # timed out, cleared — continue to propose
        else:
            log(f'Task {task_id} running ({int(elapsed)}s / {timeout}s)')
            return True  # still running, don't propose
    except Exception as e:
        log(f'Error checking timeout: {e}')
        return True  # assume still running


def propose_batch(dry_run=False):
    """Propose a new batch of tasks for approval.

    Tries GitHub commissions first, then vault recon tasks.
    Combines both into a single Telegram notification.
    """
    all_items = []
    batch_id = None
    approve_url = ''
    reject_url = ''

    # 1. Propose commissions from GitHub Issues (ralph label)
    gh_result = api_request('POST', '/api/dispatch/propose/github', {
        'repos': ['marvinbarretto/localshout-next'],
        'batch_size': DEFAULT_BATCH_SIZE,
    })
    if gh_result and gh_result.get('items'):
        all_items.extend(gh_result['items'])
        batch_id = gh_result['batch_id']
        approve_url = gh_result.get('approve_url', '')
        reject_url = gh_result.get('reject_url', '')

    # 2. Propose recon/vault tasks if we have room in the batch
    remaining = DEFAULT_BATCH_SIZE - len(all_items)
    if remaining > 0:
        vault_result = api_request('POST', '/api/dispatch/propose', {
            'batch_size': remaining,
        })
        if vault_result and vault_result.get('items'):
            all_items.extend(vault_result['items'])
            if not batch_id:
                batch_id = vault_result['batch_id']
                approve_url = vault_result.get('approve_url', '')
                reject_url = vault_result.get('reject_url', '')

    if not all_items:
        log('No tasks ready for dispatch')
        return False

    # Build Telegram message
    lines = [f'[Dispatch] Batch {batch_id} -- {len(all_items)} tasks ready:\n']
    for i, item in enumerate(all_items, 1):
        flow = item.get('flow', 'commission')
        if item.get('task_source') == 'github':
            # GitHub-sourced: task_id is "repo#number", use it directly
            lines.append(f'{i}. [{flow}] {item["agent_type"]} -- {item["task_id"]}')
        else:
            # Vault-sourced: look up the vault note for the title
            vault_task = api_request('GET', f'/api/vault/notes/{item["task_id"]}')
            title = vault_task.get('title', item['task_id']) if vault_task else item['task_id']
            lines.append(f'{i}. [{flow}] {item["agent_type"]} -- {title}')

    lines.append(f'\n<a href="{approve_url}">Approve all</a>')
    lines.append(f'<a href="{reject_url}">Reject</a>')

    message = '\n'.join(lines)

    if dry_run:
        log(f'DRY RUN: Would send batch proposal:\n{message}')
        return True

    send_telegram(message)
    log(f'Proposed batch {batch_id} with {len(all_items)} tasks')
    return True


def show_status():
    """Print current dispatch status."""
    status = api_request('GET', '/api/dispatch/status')
    if not status:
        print('Could not reach jimbo-api')
        return

    print(json.dumps(status, indent=2))

    queue = api_request('GET', '/api/dispatch/queue?status=proposed,approved,running')
    if queue:
        print(f'\nActive queue: {queue["total"]} items')
        for item in queue.get('items', []):
            print(f'  [{item["status"]}] {item["task_id"]} ({item["agent_type"]})')


# --- Main ---

def main():
    args = sys.argv[1:]
    dry_run = '--live' not in args

    if '--status' in args:
        show_status()
        return

    if dry_run:
        log('DRY RUN mode (use --live for real dispatch)')

    # Acquire lock
    lock_fd = open(LOCK_FILE, 'w')
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (BlockingIOError, OSError):
        log('Another dispatch instance is running, exiting')
        return

    # The proposer loop (one pass per cron invocation):
    # 1. Check for timeout on running tasks
    if check_timeouts(dry_run):
        return  # task still running, nothing to do

    # 2. Check if there are approved tasks waiting for the worker to pick up
    status = api_request('GET', '/api/dispatch/status')
    if status and status.get('next_approved'):
        log('Approved tasks waiting for M2 worker pickup')
        return

    # 3. Check for proposed batches awaiting approval
    if status and status.get('proposed'):
        log(f'Batch {status["proposed"]["batch_id"]} awaiting approval')
        return

    # 4. Propose new batch
    propose_batch(dry_run)


if __name__ == '__main__':
    main()
