#!/usr/bin/env python3
"""
Dispatch worker — runs on M2, pulls approved tasks from jimbo-api,
executes them with Claude Code locally, posts results back.

Usage:
  python3 dispatch-worker.py              # dry-run (default)
  python3 dispatch-worker.py --live       # actually execute
  python3 dispatch-worker.py --status     # show current state

Runs via cron every 5 minutes on M2. The VPS dispatch.py handles
proposing batches and Telegram notifications — this worker just
picks up approved tasks and runs them.

North Star: Approach 3 upgrades this to a persistent daemon with
worker pool, concurrent execution, and capability registration.
"""

import datetime
import fcntl
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error

from dispatch_intake import hydrate_task
from dispatch_reporting import build_result_summary
from dispatch_utils import parse_result, render_template
from dispatch_review import validate_result
import orchestration_helper

# --- Configuration ---

API_URL = os.environ.get('JIMBO_API_URL', '')
API_KEY = os.environ.get('JIMBO_API_KEY', '')
TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dispatch', 'templates')
WORK_DIR = os.path.expanduser('~/development')
LOCK_FILE = '/tmp/dispatch-worker.lock'
DEFAULT_MODEL = 'claude-sonnet-4-6'

# Approach 3: configurable per-task or via settings API
TIMEOUTS = {'coder': 1800, 'researcher': 900, 'drafter': 1200}  # seconds


# --- Utility functions ---

def log(msg):
    sys.stderr.write(f'[dispatch-worker] {msg}\n')


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


def load_template(agent_type):
    """Load prompt template for an agent type."""
    path = os.path.join(TEMPLATE_DIR, f'{agent_type}.md')
    if not os.path.exists(path):
        log(f'Template not found: {path}')
        return None
    with open(path) as f:
        return f.read()


def fetch_vault_note(task_id):
    return api_request('GET', f'/api/vault/notes/{task_id}')


# --- Core worker logic ---

def execute_task(task, dry_run=False):
    """Execute a single approved task using Claude Code locally."""
    task_id = task['task_id']
    agent_type = task['agent_type']
    dispatch_id = task['id']

    log(f'Picking up {task_id} ({agent_type})')

    # Load template
    template = load_template(agent_type)
    if not template:
        log(f'No template for agent type: {agent_type}')
        if not dry_run:
            api_request('POST', '/api/dispatch/fail', {
                'id': dispatch_id,
                'error_message': f'No template for agent type: {agent_type}',
            })
        return False

    normalized_task = hydrate_task(task, fetch_vault_note)
    if not normalized_task:
        log(f'Vault task not found: {task_id}')
        if not dry_run:
            api_request('POST', '/api/dispatch/fail', {
                'id': dispatch_id,
                'error_message': f'Vault task not found: {task_id}',
            })
        return False
    vault_task = normalized_task.get('vault_task') or {}

    # Determine working directory
    dispatch_repo = normalized_task.get('dispatch_repo', '')
    if not dispatch_repo and agent_type == 'coder':
        dispatch_repo = os.path.join(WORK_DIR, 'localshout-next')
    work_dir = dispatch_repo or WORK_DIR

    # Render prompt
    prompt = render_template(template, {
        'title': normalized_task.get('title', ''),
        'definition_of_done': normalized_task.get('definition_of_done', ''),
        'dispatch_repo': work_dir,
        'task_id': task_id,
        'output_path': f'/tmp/dispatch-{task_id}-output',
    })

    if dry_run:
        log(f'DRY RUN: Would execute {task_id} in {work_dir}')
        log(f'Prompt ({len(prompt)} chars):\n{prompt[:300]}...')
        return True

    # Mark as running
    api_request('POST', '/api/dispatch/start', {
        'id': dispatch_id,
        'prompt': prompt,
        'repo': work_dir,
    })
    orchestration_helper.log_decision(
        'delegate',
        task_id,
        title=normalized_task.get('title', ''),
        task_source=normalized_task.get('task_source', 'vault'),
        model=DEFAULT_MODEL,
        route={
            'decision': normalized_task.get('flow', 'dispatch'),
            'reason': 'Approved task picked up by dispatch worker',
        },
        delegate={
            'agent_type': agent_type,
            'executor': 'claude-code',
            'repo': work_dir,
            'dispatch_id': dispatch_id,
        },
    )
    orchestration_helper.log_decision(
        'report',
        task_id,
        title=normalized_task.get('title', ''),
        task_source=normalized_task.get('task_source', 'vault'),
        report={
            'status': 'picked_up',
            'dispatch_id': dispatch_id,
            'summary': 'Task picked up by dispatch worker',
        },
        changed={
            'queue_status': 'running',
            'repo': work_dir,
        },
    )
    send_telegram(build_result_summary(
        normalized_task,
        title=normalized_task.get('title', ''),
        report_status='picked_up',
        summary='Task picked up by dispatch worker',
        review_reason='Execution started on the dispatch worker',
    ))
    # Write prompt to temp file
    prompt_path = f'/tmp/dispatch-{task_id}.prompt'
    with open(prompt_path, 'w') as f:
        f.write(prompt)

    # Run Claude Code locally
    model = DEFAULT_MODEL
    log(f'Running claude -p --model {model} in {work_dir}')

    timeout = TIMEOUTS.get(agent_type, 1800)
    result_path = f'/tmp/dispatch-{task_id}.result'
    log_path = f'/tmp/dispatch-{task_id}.log'

    try:
        with open(prompt_path) as prompt_file:
            prompt_content = prompt_file.read()

        proc = subprocess.run(
            ['claude', '-p', '--model', model, '--bare', '--dangerously-skip-permissions', prompt_content],
            capture_output=True, text=True, timeout=timeout,
            cwd=work_dir,
        )

        # Write stdout to log
        with open(log_path, 'w') as f:
            f.write(proc.stdout or '')
            if proc.stderr:
                f.write(f'\n--- stderr ---\n{proc.stderr}')

        log(f'Claude exited with code {proc.returncode} ({len(proc.stdout or "")} chars output)')

    except subprocess.TimeoutExpired:
        log(f'Task {task_id} timed out after {timeout}s')
        api_request('POST', '/api/dispatch/fail', {
            'id': dispatch_id,
            'error_message': f'Timeout after {timeout}s (limit for {agent_type})',
        })
        send_telegram(build_result_summary(
            normalized_task,
            title=normalized_task.get('title', ''),
            report_status='timeout',
            summary=f'Timed out after {timeout}s',
            review_reason=f'limit for {agent_type}',
            elapsed_seconds=timeout,
        ))
        cleanup(task_id)
        return False
    except Exception as e:
        log(f'Execution error: {e}')
        api_request('POST', '/api/dispatch/fail', {
            'id': dispatch_id,
            'error_message': f'Execution error: {e}',
        })
        send_telegram(build_result_summary(
            normalized_task,
            title=normalized_task.get('title', ''),
            report_status='failed',
            summary='Execution error',
            review_reason=str(e),
        ))
        cleanup(task_id)
        return False

    # Parse result
    if os.path.exists(result_path):
        with open(result_path) as f:
            result = parse_result(f.read())
    else:
        # No result file — try parsing stdout as the result
        result = parse_result(proc.stdout or '')

    # Report back to API
    review_decision = validate_result(normalized_task, result)
    report_status = 'failed'
    if not review_decision['accepted']:
        orchestration_helper.log_decision(
            'review',
            task_id,
            title=normalized_task.get('title', ''),
            task_source=normalized_task.get('task_source', 'vault'),
            model=DEFAULT_MODEL,
            review={
                'status': review_decision['review_status'],
                'summary': result.get('summary', ''),
                'reason': review_decision['reason'],
                'raw_status': result.get('status'),
            },
            changed={
                'result_keys': sorted(result.keys()),
            },
        )
        log(f'Task {task_id} review rejected: {review_decision["reason"]}')
        api_request('POST', '/api/dispatch/fail', {
            'id': dispatch_id,
            'error_message': f'Review rejected: {review_decision["reason"]}',
        })
        report_status = 'rejected'
    elif result['status'] == 'completed':
        orchestration_helper.log_decision(
            'review',
            task_id,
            title=normalized_task.get('title', ''),
            task_source=normalized_task.get('task_source', 'vault'),
            model=DEFAULT_MODEL,
            review={
                'status': review_decision['review_status'],
                'summary': result.get('summary', ''),
                'artifacts_present': len(result) > 2,
                'reason': review_decision['reason'],
            },
        )
        log(f'Task {task_id} completed: {result.get("summary", "")[:100]}')
        api_request('POST', '/api/dispatch/complete', {
            'id': dispatch_id,
            'result_summary': result.get('summary', ''),
            'result_artifacts': json.dumps({
                k: v for k, v in result.items() if k not in ('status', 'summary')
            }) if len(result) > 2 else None,
        })
        report_status = 'completed'
    elif result['status'] == 'blocked':
        orchestration_helper.log_decision(
            'review',
            task_id,
            title=normalized_task.get('title', ''),
            task_source=normalized_task.get('task_source', 'vault'),
            model=DEFAULT_MODEL,
            review={
                'status': review_decision['review_status'],
                'summary': result.get('summary', ''),
                'blockers': result.get('blockers'),
                'reason': review_decision['reason'],
            },
        )
        log(f'Task {task_id} blocked: {result.get("blockers", "")}')
        api_request('POST', '/api/dispatch/fail', {
            'id': dispatch_id,
            'error_message': f'Blocked: {result.get("blockers", "unknown")}',
        })
        api_request('PATCH', f'/api/vault/notes/{task_id}', {
            'dispatch_status': 'needs_grooming',
        })
        report_status = 'blocked'
    else:
        orchestration_helper.log_decision(
            'review',
            task_id,
            title=normalized_task.get('title', ''),
            task_source=normalized_task.get('task_source', 'vault'),
            model=DEFAULT_MODEL,
            review={
                'status': review_decision['review_status'],
                'summary': result.get('summary', ''),
                'reason': review_decision['reason'],
            },
        )
        log(f'Task {task_id} failed: {result.get("summary", "")}')
        api_request('POST', '/api/dispatch/fail', {
            'id': dispatch_id,
            'error_message': result.get('summary', 'Unknown failure'),
        })

    orchestration_helper.log_decision(
        'report',
        task_id,
        title=normalized_task.get('title', ''),
        task_source=normalized_task.get('task_source', 'vault'),
        model=DEFAULT_MODEL,
        report={
            'status': report_status,
            'dispatch_id': dispatch_id,
            'summary': result.get('summary', ''),
        },
        changed={
            'files_changed': result.get('files_changed'),
            'branch': result.get('branch'),
            'pr_url': result.get('pr_url'),
            'artifact_path': result.get('artifact_path'),
        },
    )
    send_telegram(build_result_summary(
        normalized_task,
        title=normalized_task.get('title', ''),
        report_status=report_status,
        summary=result.get('summary', ''),
        review_reason=review_decision.get('reason'),
    ))
    cleanup(task_id)
    return True


def cleanup(task_id):
    """Remove temp files for a task."""
    for ext in ('prompt', 'log', 'result', 'sh', 'signal'):
        path = f'/tmp/dispatch-{task_id}.{ext}'
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


def show_status():
    """Print current dispatch status."""
    if not API_URL or not API_KEY:
        print('JIMBO_API_URL and JIMBO_API_KEY must be set')
        return
    status = api_request('GET', '/api/dispatch/status')
    if not status:
        print('Could not reach jimbo-api')
        return
    print(json.dumps(status, indent=2))


# --- Worker Stats ---

class WorkerStats:
    """Tracks worker health and performance for monitoring and dashboards."""

    def __init__(self):
        self.started_at = datetime.datetime.now(datetime.UTC)
        self.loop_count = 0
        self.tasks_completed = 0
        self.tasks_failed = 0
        self.tasks_blocked = 0
        self.consecutive_errors = 0
        self.consecutive_idle = 0
        self.total_errors = 0
        self.total_task_time_s = 0
        self.last_task_at = None
        self.last_error = None
        self.last_error_at = None
        self.api_reachable = True

    def record_loop(self):
        self.loop_count += 1
        self.consecutive_idle += 1

    def record_task_complete(self, duration_s):
        self.tasks_completed += 1
        self.total_task_time_s += duration_s
        self.last_task_at = datetime.datetime.now(datetime.UTC)
        self.consecutive_idle = 0
        self.consecutive_errors = 0

    def record_task_failed(self, duration_s):
        self.tasks_failed += 1
        self.total_task_time_s += duration_s
        self.last_task_at = datetime.datetime.now(datetime.UTC)
        self.consecutive_idle = 0

    def record_task_blocked(self):
        self.tasks_blocked += 1
        self.last_task_at = datetime.datetime.now(datetime.UTC)
        self.consecutive_idle = 0

    def record_error(self, error):
        self.consecutive_errors += 1
        self.total_errors += 1
        self.last_error = str(error)
        self.last_error_at = datetime.datetime.now(datetime.UTC)

    def record_api_ok(self):
        self.api_reachable = True
        self.consecutive_errors = 0

    def record_api_down(self):
        self.api_reachable = False

    @property
    def uptime_s(self):
        return (datetime.datetime.now(datetime.UTC) - self.started_at).total_seconds()

    @property
    def uptime_human(self):
        s = int(self.uptime_s)
        if s < 3600:
            return f'{s // 60}m'
        if s < 86400:
            return f'{s // 3600}h {(s % 3600) // 60}m'
        return f'{s // 86400}d {(s % 86400) // 3600}h'

    def summary_line(self):
        """One-line status for logging."""
        parts = [
            f'loop={self.loop_count}',
            f'up={self.uptime_human}',
            f'done={self.tasks_completed}',
            f'fail={self.tasks_failed}',
            f'block={self.tasks_blocked}',
        ]
        if self.total_task_time_s > 0:
            avg = self.total_task_time_s / max(self.tasks_completed + self.tasks_failed, 1)
            parts.append(f'avg={int(avg)}s')
        if self.consecutive_errors > 0:
            parts.append(f'errors={self.consecutive_errors}x')
        if not self.api_reachable:
            parts.append('API_DOWN')
        return ' | '.join(parts)

    def to_dict(self):
        """Full stats for API reporting."""
        return {
            'started_at': self.started_at.isoformat() + 'Z',
            'uptime_s': int(self.uptime_s),
            'uptime_human': self.uptime_human,
            'loop_count': self.loop_count,
            'tasks_completed': self.tasks_completed,
            'tasks_failed': self.tasks_failed,
            'tasks_blocked': self.tasks_blocked,
            'total_errors': self.total_errors,
            'consecutive_errors': self.consecutive_errors,
            'consecutive_idle': self.consecutive_idle,
            'avg_task_time_s': round(self.total_task_time_s / max(self.tasks_completed + self.tasks_failed, 1), 1),
            'total_task_time_s': round(self.total_task_time_s, 1),
            'api_reachable': self.api_reachable,
            'last_task_at': self.last_task_at.isoformat() + 'Z' if self.last_task_at else None,
            'last_error': self.last_error,
            'last_error_at': self.last_error_at.isoformat() + 'Z' if self.last_error_at else None,
        }


# --- Main loop ---

DEFAULT_POLL_INTERVAL = 300  # 5 minutes
HEARTBEAT_EVERY = 12  # log heartbeat every N loops (every hour at 5min interval)
ERROR_ALERT_THRESHOLD = 3  # send Telegram alert after N consecutive errors
AUTH_CHECK_EVERY = 60  # verify Claude auth every N loops (~5 hours at 5min interval)


def check_claude_auth():
    """Verify Claude Code is still authenticated."""
    try:
        proc = subprocess.run(
            ['claude', '-p', '--bare', 'respond with exactly: AUTH_OK'],
            capture_output=True, text=True, timeout=30,
            cwd=os.path.expanduser('~/development'),
        )
        return 'AUTH_OK' in (proc.stdout or '')
    except Exception:
        return False


def send_telegram(message):
    """Send a Telegram alert. Fire-and-forget."""
    token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID', '')
    if not token or not chat_id:
        return
    url = f'https://api.telegram.org/bot{token}/sendMessage'
    payload = json.dumps({'chat_id': chat_id, 'text': message}).encode()
    req = urllib.request.Request(url, data=payload,
        headers={'Content-Type': 'application/json'}, method='POST')
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


def run_once(dry_run=False, stats=None):
    """Check for one approved task and execute it. Returns True if a task was found."""
    task = api_request('GET', '/api/dispatch/next')
    if task is None:
        # API unreachable (not just "no tasks" — actual failure)
        if stats:
            stats.record_api_down()
        return False
    if 'id' not in task:
        if stats:
            stats.record_api_ok()
        return False

    if stats:
        stats.record_api_ok()

    start_time = time.time()
    result = execute_task(task, dry_run)
    duration = time.time() - start_time

    if stats and result:
        # Check what happened by re-reading the queue item
        updated = api_request('GET', f'/api/dispatch/queue?status=completed,failed&limit=1')
        if updated and updated.get('items'):
            latest = updated['items'][0]
            if latest['task_id'] == task['task_id']:
                if latest['status'] == 'completed':
                    stats.record_task_complete(duration)
                elif latest['status'] == 'failed' and 'Blocked' in (latest.get('error_message') or ''):
                    stats.record_task_blocked()
                else:
                    stats.record_task_failed(duration)

    return result


def run_loop(dry_run=False, poll_interval=DEFAULT_POLL_INTERVAL):
    """Run continuously — poll for tasks, execute, sleep, repeat.
    Designed to run in a persistent tmux session where Claude auth is active."""
    stats = WorkerStats()

    log(f'=== Dispatch Worker Starting ===')
    log(f'Mode: {"DRY RUN" if dry_run else "LIVE"}')
    log(f'Poll interval: {poll_interval}s')
    log(f'API: {API_URL}')
    log(f'Templates: {TEMPLATE_DIR}')
    log(f'Work dir: {WORK_DIR}')
    log(f'Ctrl-C to stop')
    log(f'================================')

    # Initial auth check
    log('Checking Claude auth...')
    if check_claude_auth():
        log('Claude auth OK')
    else:
        log('WARNING: Claude auth check failed — tasks may fail')
        send_telegram('[Dispatch Worker] WARNING: Claude auth check failed on startup')

    # Report worker online
    send_telegram(f'[Dispatch Worker] Online — polling every {poll_interval // 60}min')
    # Post stats to API so dashboard can show worker status
    api_request('PUT', '/api/settings/dispatch_worker_status', {
        'value': json.dumps(stats.to_dict())
    })

    while True:
        try:
            stats.record_loop()

            # Periodic heartbeat log
            if stats.loop_count % HEARTBEAT_EVERY == 0:
                log(f'Heartbeat: {stats.summary_line()}')
                # Update worker status in API
                api_request('PUT', '/api/settings/dispatch_worker_status', {
                    'value': json.dumps(stats.to_dict())
                })

            # Periodic auth check
            if stats.loop_count % AUTH_CHECK_EVERY == 0 and stats.loop_count > 0:
                log('Periodic auth check...')
                if check_claude_auth():
                    log('Claude auth still valid')
                else:
                    log('ERROR: Claude auth expired — pausing until fixed')
                    send_telegram('[Dispatch Worker] Claude auth expired — worker paused. Run: tmux attach -t dispatch → claude /login')
                    # Wait longer before retrying — don't burn loops
                    time.sleep(poll_interval * 6)
                    continue

            # Check for work
            found = run_once(dry_run, stats)

            if found:
                # Task completed — check immediately for more
                continue
            else:
                if not stats.api_reachable:
                    stats.record_error('API unreachable')
                    if stats.consecutive_errors == ERROR_ALERT_THRESHOLD:
                        send_telegram(f'[Dispatch Worker] API unreachable ({stats.consecutive_errors}x in a row)')
                        log(f'API unreachable {stats.consecutive_errors}x — sent alert')
                    # Back off when API is down
                    time.sleep(poll_interval * 2)
                else:
                    time.sleep(poll_interval)

        except KeyboardInterrupt:
            log(f'Stopped by user after {stats.loop_count} loops')
            log(f'Final stats: {stats.summary_line()}')
            send_telegram(f'[Dispatch Worker] Stopped — {stats.summary_line()}')
            api_request('PUT', '/api/settings/dispatch_worker_status', {
                'value': json.dumps({**stats.to_dict(), 'status': 'stopped'})
            })
            break
        except Exception as e:
            stats.record_error(e)
            log(f'Unexpected error (attempt {stats.consecutive_errors}): {e}')
            if stats.consecutive_errors == ERROR_ALERT_THRESHOLD:
                send_telegram(f'[Dispatch Worker] {stats.consecutive_errors} consecutive errors: {e}')
            time.sleep(poll_interval)


def main():
    args = sys.argv[1:]
    dry_run = '--live' not in args
    loop_mode = '--loop' in args
    poll_interval = DEFAULT_POLL_INTERVAL
    for arg in args:
        if arg.startswith('--interval='):
            poll_interval = int(arg.split('=')[1])

    if '--status' in args:
        show_status()
        return

    if not API_URL or not API_KEY:
        log('JIMBO_API_URL and JIMBO_API_KEY must be set')
        return

    if dry_run:
        log('DRY RUN mode (use --live for real execution)')

    # Acquire lock — one task at a time
    # Approach 3: worker pool replaces this
    lock_fd = open(LOCK_FILE, 'w')
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (BlockingIOError, OSError):
        log('Another worker instance is running, exiting')
        return

    if loop_mode:
        run_loop(dry_run, poll_interval)
    else:
        if not run_once(dry_run):
            log('No approved tasks')


if __name__ == '__main__':
    main()
