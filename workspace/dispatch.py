#!/usr/bin/env python3
"""
Autonomous task dispatch orchestrator.

Runs via cron every 5 minutes on VPS. Proposes batches from jimbo-api,
monitors agent sessions on M2 via SSH+tmux, reports results.

Usage:
  python3 dispatch.py              # dry-run (default)
  python3 dispatch.py --live       # actually dispatch
  python3 dispatch.py --status     # show current queue state

North Star: This is Approach 2 (API-backed dispatch). Code comments
reference Approach 3 (full agent runtime) as the upgrade path:
worker pool, persistent daemon, capability registry, git worktrees.
"""

import fcntl
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import urllib.error

# --- Configuration ---

API_URL = os.environ.get('JIMBO_API_URL', 'http://localhost:3100')
API_KEY = os.environ.get('JIMBO_API_KEY', os.environ.get('API_KEY', ''))
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')
M2_SSH_HOST = 'm2'  # SSH alias configured in ~/.ssh/config
TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), 'dispatch', 'templates')
LOCK_FILE = '/tmp/dispatch.lock'

# Approach 3: These become configurable per-task or via settings API
TIMEOUTS = {'coder': 1800, 'researcher': 900, 'drafter': 1200}  # seconds
DEFAULT_BATCH_SIZE = 3

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


def ssh_cmd(cmd, timeout=30):
    """Run a command on M2 via SSH. Returns (success, stdout, stderr)."""
    try:
        result = subprocess.run(
            ['ssh', '-o', 'ConnectTimeout=5', M2_SSH_HOST, cmd],
            capture_output=True, text=True, timeout=timeout
        )
        return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return False, '', 'SSH timeout'
    except Exception as e:
        return False, '', str(e)


def check_m2_reachable():
    """Quick connectivity check to M2."""
    ok, _, _ = ssh_cmd('true', timeout=10)
    return ok


def parse_result(raw):
    """Parse agent result JSON with fallback for malformed output."""
    if not raw or not raw.strip():
        return {'status': 'failed', 'summary': 'Empty result file'}

    text = raw.strip()

    # Try direct JSON parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting JSON from markdown fences
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Fallback: treat raw text as summary
    return {
        'status': 'completed_unstructured',
        'summary': text[:500],
    }


def render_template(template_text, variables):
    """Render a prompt template with variable substitution."""
    result = template_text
    for key, value in variables.items():
        result = result.replace('{' + key + '}', str(value))
    return result


def is_valid_batch_id(batch_id):
    return bool(batch_id and re.match(r'^batch-\d{8}-\d{6}$', batch_id))


def load_template(agent_type):
    """Load prompt template for an agent type."""
    path = os.path.join(TEMPLATE_DIR, f'{agent_type}.md')
    if not os.path.exists(path):
        log(f'Template not found: {path}')
        return None
    with open(path) as f:
        return f.read()


# --- Core dispatch logic ---

def check_running(dry_run=False):
    """Check if there's a running task and monitor it."""
    status = api_request('GET', '/api/dispatch/status')
    if not status or not status.get('running'):
        return False  # nothing running

    task = status['running']
    task_id = task['task_id']
    timeout = TIMEOUTS.get(task['agent_type'], 1800)

    # Check for completion signal
    ok, signal, _ = ssh_cmd(f'cat /tmp/dispatch-{task_id}.signal 2>/dev/null')
    if ok and 'DISPATCH_DONE' in signal:
        # Collect result
        _, result_raw, _ = ssh_cmd(f'cat /tmp/dispatch-{task_id}.result 2>/dev/null')
        result = parse_result(result_raw)

        if result['status'] in ('completed', 'completed_unstructured'):
            log(f'Task {task_id} completed: {result.get("summary", "")[:100]}')
            if not dry_run:
                api_request('POST', '/api/dispatch/complete', {
                    'id': task['id'],
                    'result_summary': result.get('summary', ''),
                    'result_artifacts': json.dumps({
                        k: v for k, v in result.items() if k not in ('status', 'summary')
                    }) if len(result) > 2 else None,
                })
                send_telegram(f'[Dispatch] Done: {task_id} ({task["agent_type"]})\n{result.get("summary", "")[:200]}')
                ssh_cmd(f'rm -f /tmp/dispatch-{task_id}.{{prompt,log,signal,result}}')
        elif result['status'] == 'blocked':
            log(f'Task {task_id} blocked: {result.get("blockers", "")}')
            if not dry_run:
                api_request('POST', '/api/dispatch/fail', {
                    'id': task['id'],
                    'error_message': f'Blocked: {result.get("blockers", "unknown")}',
                })
                api_request('PATCH', f'/api/vault/notes/{task_id}', {
                    'dispatch_status': 'needs_grooming',
                })
                send_telegram(f'[Dispatch] Blocked: {task_id}\n{result.get("blockers", "")[:200]}')
                ssh_cmd(f'rm -f /tmp/dispatch-{task_id}.{{prompt,log,signal,result}}')
        else:
            log(f'Task {task_id} failed: {result.get("summary", "")}')
            if not dry_run:
                api_request('POST', '/api/dispatch/fail', {
                    'id': task['id'],
                    'error_message': result.get('summary', 'Unknown failure'),
                })
                send_telegram(f'[Dispatch] Failed: {task_id}\n{result.get("summary", "")[:200]}')
                ssh_cmd(f'rm -f /tmp/dispatch-{task_id}.{{prompt,log,signal,result}}')

        return True  # was running, now handled

    # Check for timeout
    started = task.get('started_at', '')
    if started:
        try:
            import datetime
            started_dt = datetime.datetime.fromisoformat(started.replace(' ', 'T'))
            elapsed = (datetime.datetime.utcnow() - started_dt).total_seconds()
            if elapsed > timeout:
                log(f'Task {task_id} timed out after {int(elapsed)}s')
                if not dry_run:
                    ssh_cmd(f'tmux kill-session -t dispatch-{task_id} 2>/dev/null')
                    api_request('POST', '/api/dispatch/fail', {
                        'id': task['id'],
                        'error_message': f'Timeout after {int(elapsed)}s (limit: {timeout}s)',
                    })
                    send_telegram(f'[Dispatch] Timeout: {task_id} after {int(elapsed)}s')
                    ssh_cmd(f'rm -f /tmp/dispatch-{task_id}.{{prompt,log,signal,result}}')
                return True
        except Exception as e:
            log(f'Error parsing start time: {e}')

    log(f'Task {task_id} still running')
    return True  # still running


def dispatch_next(dry_run=False):
    """Dispatch the next approved task to M2."""
    task = api_request('GET', '/api/dispatch/next')
    if not task or 'id' not in task:
        return False  # nothing to dispatch

    task_id = task['task_id']
    agent_type = task['agent_type']
    log(f'Dispatching {task_id} ({agent_type})')

    # Load and render template
    template = load_template(agent_type)
    if not template:
        log(f'No template for agent type: {agent_type}')
        if not dry_run:
            api_request('POST', '/api/dispatch/fail', {
                'id': task['id'],
                'error_message': f'No template for agent type: {agent_type}',
            })
        return False

    # Get vault task details for template variables
    vault_task = api_request('GET', f'/api/vault/notes/{task_id}')
    if not vault_task:
        log(f'Vault task not found: {task_id}')
        return False

    # Determine repo path for coder tasks
    dispatch_repo = task.get('dispatch_repo', '')
    if not dispatch_repo and agent_type == 'coder':
        # Default: try to infer from task title/body
        dispatch_repo = '~/development/localshout-next'  # sensible default for now
        # Approach 3: agent capability registry maps task metadata to repos

    # Get model preference from agent type config
    agent_config = api_request('GET', '/api/dispatch/agent-types')
    model = 'claude-opus-4-6'  # default
    if agent_config and agent_type in agent_config:
        model = agent_config[agent_type].get('model', model)

    prompt = render_template(template, {
        'title': vault_task.get('title', ''),
        'definition_of_done': vault_task.get('definition_of_done', ''),
        'dispatch_repo': dispatch_repo,
        'task_id': task_id,
        'output_path': f'/tmp/dispatch-{task_id}-output',
    })

    if dry_run:
        log(f'DRY RUN: Would dispatch {task_id} to M2 with model {model}')
        log(f'Prompt preview ({len(prompt)} chars):\n{prompt[:300]}...')
        return True

    # Push prompt to M2
    try:
        proc = subprocess.run(
            ['ssh', M2_SSH_HOST, f'cat > /tmp/dispatch-{task_id}.prompt'],
            input=prompt.encode(), capture_output=True, timeout=15
        )
        if proc.returncode != 0:
            raise Exception(f'Push failed: {proc.stderr.decode()[:200]}')
    except Exception as e:
        log(f'Failed to push prompt: {e}')
        api_request('POST', '/api/dispatch/fail', {
            'id': task['id'], 'error_message': f'SSH prompt push failed: {e}',
        })
        return False

    # Start tmux session with model flag
    tmux_cmd = (
        f'tmux new-session -d -s dispatch-{task_id} '
        f'"claude -p --model {model} --bare --dangerously-skip-permissions '
        f'\\"$(cat /tmp/dispatch-{task_id}.prompt)\\" '
        f'> /tmp/dispatch-{task_id}.log 2>&1; '
        f'echo DISPATCH_DONE > /tmp/dispatch-{task_id}.signal"'
    )
    ok, _, err = ssh_cmd(tmux_cmd, timeout=15)
    if not ok:
        log(f'Failed to start tmux: {err}')
        api_request('POST', '/api/dispatch/fail', {
            'id': task['id'], 'error_message': f'tmux start failed: {err}',
        })
        return False

    # Mark as running
    api_request('POST', '/api/dispatch/start', {
        'id': task['id'], 'prompt': prompt, 'repo': dispatch_repo,
    })
    send_telegram(f'[Dispatch] Running: {vault_task.get("title", task_id)} ({agent_type}, {model})')
    return True


def propose_batch(dry_run=False):
    """Propose a new batch of tasks for approval."""
    result = api_request('POST', '/api/dispatch/propose', {
        'batch_size': DEFAULT_BATCH_SIZE,
    })
    if not result or not result.get('items'):
        log('No tasks ready for dispatch')
        return False

    items = result['items']
    batch_id = result['batch_id']
    approve_url = result.get('approve_url', '')
    reject_url = result.get('reject_url', '')

    # Build Telegram message
    lines = [f'[Dispatch] Batch {batch_id} -- {len(items)} tasks ready:\n']
    for i, item in enumerate(items, 1):
        vault_task = api_request('GET', f'/api/vault/notes/{item["task_id"]}')
        title = vault_task.get('title', item['task_id']) if vault_task else item['task_id']
        lines.append(f'{i}. {item["agent_type"]} -- {title}')

    lines.append(f'\n<a href="{approve_url}">Approve all</a>')
    lines.append(f'<a href="{reject_url}">Reject</a>')

    message = '\n'.join(lines)

    if dry_run:
        log(f'DRY RUN: Would send batch proposal:\n{message}')
        return True

    send_telegram(message)
    log(f'Proposed batch {batch_id} with {len(items)} tasks')
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

    # Acquire lock (Approach 3: persistent daemon replaces this)
    lock_fd = open(LOCK_FILE, 'w')
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (BlockingIOError, OSError):
        log('Another dispatch instance is running, exiting')
        return

    # Check M2 connectivity
    if not check_m2_reachable():
        log('M2 unreachable via SSH')
        # Only alert once — check if we already know it's offline
        # Approach 3: proper health tracking with backoff
        send_telegram('[Dispatch] M2 unreachable -- pausing dispatch')
        return

    # The dispatch loop (one pass per cron invocation)
    # 1. Check running tasks
    if check_running(dry_run):
        return  # handled a running task, check again next cycle

    # 2. Dispatch next approved task
    if dispatch_next(dry_run):
        return  # dispatched, check again next cycle

    # 3. Check for proposed batches (waiting for approval)
    status = api_request('GET', '/api/dispatch/status')
    if status and status.get('proposed'):
        log(f'Batch {status["proposed"]["batch_id"]} awaiting approval')
        return  # still waiting

    # 4. Propose new batch
    propose_batch(dry_run)


if __name__ == '__main__':
    main()
