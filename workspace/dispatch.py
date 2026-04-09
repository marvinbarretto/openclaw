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

from dispatch_batch_memory import (
    batch_report_status,
    build_batch,
    build_batches,
    dispatch_item_id,
    summarize_batch,
)
from dispatch_intake import hydrate_batch
from dispatch_reporting import build_batch_summary, build_result_summary
from dispatch_transitions import collect_new_items, normalize_seen_state, serialize_seen_state
from dispatch_utils import is_valid_batch_id, parse_result, render_template
from jimbo_core import JimboCore, JimboTask
from jimbo_runtime_service import begin_dispatch_proposal

# --- Configuration ---

API_URL = os.environ.get('JIMBO_API_URL', 'http://localhost:3100')
API_KEY = os.environ.get('JIMBO_API_KEY', os.environ.get('API_KEY', ''))
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')
LOCK_FILE = '/tmp/dispatch.lock'
TRANSITION_STATE_KEY = 'dispatch_transition_state'
DEFAULT_BATCH_SIZE = 3
BATCH_QUEUE_STATUSES = 'proposed,approved,running,completed,failed,rejected'

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


def notify_terminal_outcome(status, task, *, summary=None, review_reason=None,
                            elapsed_seconds=None, title=None, dry_run=False):
    message = build_result_summary(
        task,
        title=title,
        report_status=status,
        summary=summary,
        review_reason=review_reason,
        elapsed_seconds=elapsed_seconds,
    )
    if dry_run:
        log(f'DRY RUN: Would send outcome summary:\n{message}')
        return
    send_telegram(message)


def fetch_vault_note(task_id):
    return api_request('GET', f'/api/vault/notes/{task_id}')


def fetch_queue_items(status, *, limit=20):
    queue = api_request('GET', f'/api/dispatch/queue?status={status}&limit={limit}')
    return queue.get('items', []) if queue else []


def fetch_setting_value(key):
    """Fetch a raw value from the settings store.

    Returns:
      - the stored value when present
      - {} when the setting is missing
      - None when the API request failed
    """
    url = f'{API_URL}/api/settings/{key}'
    req = urllib.request.Request(
        url,
        headers={'X-API-Key': API_KEY, 'Accept': 'application/json'},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode())
            return payload.get('value')
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {}
        body_text = e.read().decode() if e.fp else ''
        log(f'API error: GET /api/settings/{key} -> {e.code}: {body_text[:200]}')
        return None
    except Exception as e:
        log(f'API request failed: GET /api/settings/{key} -> {e}')
        return None


def store_setting_value(key, value):
    result = api_request('PUT', f'/api/settings/{key}', {'value': value})
    return result is not None


def load_transition_state():
    raw_value = fetch_setting_value(TRANSITION_STATE_KEY)
    if raw_value is None:
        return None
    return normalize_seen_state(raw_value)


def save_transition_state(state):
    return store_setting_value(TRANSITION_STATE_KEY, serialize_seen_state(state))


def emit_batch_report(batch_id, batch, *, dry_run=False):
    summary = summarize_batch(batch)
    report_status = batch_report_status(batch)
    activity_id = JimboCore(JimboTask(
        task_id=batch_id,
        title=summary,
        task_source='dispatch-batch',
        workflow='dispatch',
    )).report(
        report={
            'status': report_status,
            'batch_id': batch_id,
            'summary': summary,
        },
        reason='Batch state updated',
        changed={
            'items': len(batch.get('items', {})),
        },
        metadata={
            'batch': batch,
        },
    )
    if not activity_id:
        log(f'Failed to log batch report for {batch_id}')
        return False
    notify_terminal_outcome(
        report_status,
        {'task_id': batch_id, 'flow': 'batch', 'agent_type': 'orchestrator'},
        title=f'batch {batch_id}',
        summary=summary,
        review_reason='Batch state updated',
        dry_run=dry_run,
    )
    return True


def emit_transition(status, item, *, dry_run=False):
    hydrated = hydrate_batch([item], fetch_vault_note)
    if not hydrated:
        log(f'Could not hydrate task for {status} transition: {item.get("task_id")}')
        return False
    task = hydrated[0]
    title = task.get('title', task['task_id'])

    if status == 'approved':
        summary = 'Approved and waiting for worker pickup'
        reason = 'Approval received from the dispatch queue'
    elif status == 'rejected':
        summary = item.get('error_message') or 'Rejected before execution'
        reason = 'Proposal was rejected or expired before execution'
    else:
        summary = item.get('error_message') or status
        reason = f'Dispatch queue entered {status}'

    activity_id = JimboCore(JimboTask(
        task_id=task['task_id'],
        title=title,
        task_source=task.get('task_source', 'vault'),
        workflow='dispatch',
    )).report(
        report={
            'status': status,
            'dispatch_id': item.get('id'),
            'summary': summary,
        },
        reason=reason,
        changed={
            'batch_id': item.get('batch_id'),
            'queue_status': item.get('status'),
        },
    )
    if not activity_id:
        log(f'Failed to log {status} transition for {task["task_id"]}')
        return False
    notify_terminal_outcome(
        status,
        task,
        summary=summary,
        review_reason=reason,
        title=title,
        dry_run=dry_run,
    )
    return True


def emit_batch_reports(batch_ids, *, dry_run=False, queue_items=None, status_overrides=None):
    """Rebuild and emit batch narratives from the current queue snapshot."""
    if not batch_ids:
        return True
    if queue_items is None:
        queue_items = fetch_queue_items(BATCH_QUEUE_STATUSES, limit=100)
    batches = build_batches(
        queue_items,
        batch_ids=batch_ids,
        status_overrides=status_overrides,
    )
    success = True
    for batch_id in sorted(batch_ids):
        batch = batches.get(batch_id)
        if batch:
            success = emit_batch_report(batch_id, batch, dry_run=dry_run) and success
        else:
            log(f'Could not rebuild batch report for {batch_id} from queue state')
            success = False
    return success


def check_queue_transitions(dry_run=False):
    """Detect new queue transitions and rebuild affected batch narratives."""
    seen_state = load_transition_state()
    if seen_state is None:
        log('Transition state unavailable, skipping transition detection')
        return
    approved_items = fetch_queue_items('approved')
    rejected_items = fetch_queue_items('rejected')
    running_items = fetch_queue_items('running')
    completed_items = fetch_queue_items('completed')
    failed_items = fetch_queue_items('failed')

    new_approved, next_state = collect_new_items(seen_state, 'approved', approved_items)
    new_rejected, next_state = collect_new_items(next_state, 'rejected', rejected_items)
    new_running, next_state = collect_new_items(next_state, 'running', running_items)
    new_completed, next_state = collect_new_items(next_state, 'completed', completed_items)
    new_failed, next_state = collect_new_items(next_state, 'failed', failed_items)
    affected_batch_ids = set()
    transition_success = True

    for item in new_approved:
        transition_success = emit_transition('approved', item, dry_run=dry_run) and transition_success
        if item.get('batch_id'):
            affected_batch_ids.add(item['batch_id'])
    for item in new_rejected:
        transition_success = emit_transition('rejected', item, dry_run=dry_run) and transition_success
        if item.get('batch_id'):
            affected_batch_ids.add(item['batch_id'])
    for item in new_running:
        if item.get('batch_id'):
            affected_batch_ids.add(item['batch_id'])
    for item in new_completed:
        if item.get('batch_id'):
            affected_batch_ids.add(item['batch_id'])
    for item in new_failed:
        if item.get('batch_id'):
            affected_batch_ids.add(item['batch_id'])

    batch_success = emit_batch_reports(affected_batch_ids, dry_run=dry_run)

    if not dry_run:
        if transition_success and batch_success:
            if not save_transition_state(next_state):
                log('Failed to persist transition state')
        else:
            log('Skipping transition state advance because transition logging was incomplete')
            return


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
                batch_id = task.get('batch_id')
                if batch_id:
                    queue_items = fetch_queue_items(BATCH_QUEUE_STATUSES, limit=100)
                    target_found = any(
                        dispatch_item_id(item) == str(task['id']) and item.get('batch_id') == batch_id
                        for item in queue_items
                    )
                    if not target_found:
                        queue_items = list(queue_items) + [task]
                    emit_batch_reports(
                        {batch_id},
                        dry_run=False,
                        queue_items=queue_items,
                        status_overrides={str(task['id']): 'timeout'},
                    )
                notify_terminal_outcome(
                    'timeout',
                    task,
                    summary=f'Timed out after {int(elapsed)}s',
                    review_reason=f'limit: {timeout}s for {task["agent_type"]}',
                    elapsed_seconds=elapsed,
                    title=task_id,
                    dry_run=dry_run,
                )
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

    if batch_id and not is_valid_batch_id(batch_id):
        log(f'Unexpected batch ID format: {batch_id}')

    hydrated_items = hydrate_batch(all_items, fetch_vault_note)
    if not hydrated_items:
        log('No dispatch items could be hydrated')
        return False

    titles = {item['task_id']: item.get('title', item['task_id']) for item in hydrated_items}

    message = build_batch_summary(
        batch_id,
        hydrated_items,
        titles=titles,
        approve_url=approve_url,
        reject_url=reject_url,
    )

    if dry_run:
        log(f'DRY RUN: Would send batch proposal:\n{message}')
        return True

    send_telegram(message)
    emit_batch_report(batch_id, build_batch(batch_id, hydrated_items, default_status='proposed'), dry_run=dry_run)
    for item in hydrated_items:
        begin_dispatch_proposal(
            item,
            batch_id=batch_id,
            approve_url=approve_url,
            reject_url=reject_url,
        )
    log(f'Proposed batch {batch_id} with {len(hydrated_items)} tasks')
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
    check_queue_transitions(dry_run)
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
