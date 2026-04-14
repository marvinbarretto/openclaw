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
import urllib.parse

from dispatch_intake import hydrate_task
from dispatch_reporting import build_result_summary
from dispatch_utils import parse_result, render_template
from dispatch_review import validate_result
from jimbo_core import JimboCore, JimboTask
from jimbo_runtime_service import (
    build_dispatch_execution_payload,
    resolve_dispatch_execution,
)

# --- Configuration ---

API_URL = os.environ.get('JIMBO_API_URL', '')
API_KEY = os.environ.get('JIMBO_API_KEY', '')
TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dispatch', 'templates')
SKILLS_DIR = os.path.expanduser('~/development/hub/docs/dispatch/skills')
WORK_DIR = os.path.expanduser('~/development')
LOCK_FILE = '/tmp/dispatch-worker.lock'
DEFAULT_MODEL = 'claude-sonnet-4-6'

# Approach 3: configurable per-task or via settings API
TIMEOUTS = {'coder': 1800, 'researcher': 900, 'drafter': 1200, 'extractor': 900}  # seconds
EXECUTOR_DESCRIPTIONS = {
    "boris": "Claude on m2 machine — strong reasoning, complex tasks",
    "ralph": "Ollama on MacBook Air — simple, mechanical tasks",
    "marvin": "Human — judgment calls and approvals",
}


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


def api_write(method, path, body=None, *, action, retries=2, retry_delay_s=0.25):
    """Perform a required API write with retries."""
    attempts = max(1, retries + 1)
    for attempt in range(1, attempts + 1):
        result = api_request(method, path, body)
        if result is not None:
            return True
        if attempt < attempts and retry_delay_s:
            time.sleep(retry_delay_s)
    log(f'Failed to {action} after {attempts} attempts')
    return False


def update_worker_status(payload, *, retries=2):
    """Update worker heartbeat/status in the settings API."""
    return api_write(
        'PUT',
        '/api/settings/dispatch_worker_status',
        {'value': json.dumps(payload)},
        action='update dispatch worker status',
        retries=retries,
    )


def report_dispatch_failure(dispatch_id, error_message, *, retries=2):
    return api_write(
        'POST',
        '/api/dispatch/fail',
        {'id': dispatch_id, 'error_message': error_message},
        action=f'report dispatch failure for {dispatch_id}',
        retries=retries,
    )


def report_dispatch_start(dispatch_id, prompt, repo, *, retries=2):
    return api_write(
        'POST',
        '/api/dispatch/start',
        {'id': dispatch_id, 'prompt': prompt, 'repo': repo},
        action=f'mark dispatch task {dispatch_id} as started',
        retries=retries,
    )


def report_dispatch_complete(dispatch_id, result, *, retries=2):
    return api_write(
        'POST',
        '/api/dispatch/complete',
        {
            'id': dispatch_id,
            'result_summary': result.get('summary', ''),
            'result_artifacts': json.dumps({
                k: v for k, v in result.items() if k not in ('status', 'summary')
            }) if len(result) > 2 else None,
        },
        action=f'mark dispatch task {dispatch_id} as completed',
        retries=retries,
    )


def patch_vault_note(task_id, patch, *, retries=2):
    quoted_id = urllib.parse.quote(task_id, safe='')
    return api_write(
        'PATCH',
        f'/api/vault/notes/{quoted_id}',
        patch,
        action=f'update vault note {task_id}',
        retries=retries,
    )


def preserve_evidence(task_id, reason):
    log(f'Preserving dispatch artifacts for {task_id}: {reason}')
    send_telegram(f'[Dispatch Worker] API write failed for {task_id}: {reason}. Local artifacts preserved.')


def load_skill(skill_name):
    """Load a skill definition from hub/docs/dispatch/skills/{name}/SKILL.md."""
    path = os.path.join(SKILLS_DIR, skill_name, 'SKILL.md')
    if not os.path.exists(path):
        log(f'Skill not found: {path}')
        return None
    with open(path) as f:
        content = f.read()
    # Strip YAML frontmatter if present
    if content.startswith('---'):
        parts = content.split('---', 2)
        if len(parts) >= 3:
            content = parts[2].strip()
    return content


def load_template(agent_type):
    """Load prompt template for an agent type (legacy fallback)."""
    path = os.path.join(TEMPLATE_DIR, f'{agent_type}.md')
    if not os.path.exists(path):
        log(f'Template not found: {path}')
        return None
    with open(path) as f:
        return f.read()


def compose_skills_prompt(required_skills, context):
    """Compose a dispatch prompt from multiple skill definitions.

    Loads each SKILL.md from hub, combines them with execution context
    (executor, task details, output contract). This replaces the old
    fixed-template approach where one agent_type = one template.
    """
    skills = []
    if isinstance(required_skills, str):
        try:
            skills = json.loads(required_skills)
        except json.JSONDecodeError:
            skills = [required_skills]
    elif isinstance(required_skills, list):
        skills = required_skills

    if not skills:
        return None

    # Load each skill definition
    skill_docs = []
    for skill_name in skills:
        content = load_skill(skill_name)
        if content:
            skill_docs.append((skill_name, content))
        else:
            log(f'Warning: skill "{skill_name}" not found in {SKILLS_DIR}, skipping')

    if not skill_docs:
        return None

    # Load output contract if it exists
    output_contract = ''
    contract_path = os.path.join(TEMPLATE_DIR, '_output-contract.md')
    if os.path.exists(contract_path):
        with open(contract_path) as f:
            output_contract = f.read()

    # Compose the prompt
    executor = context.get('executor', 'unknown')
    executor_desc = EXECUTOR_DESCRIPTIONS.get(executor, '')

    sections = []

    # Header
    sections.append(f"""You are an autonomous dispatch agent executing a task that requires {len(skills)} skill(s): {', '.join(skills)}.

## Agent Context

You are executing as **{executor}** ({executor_desc}).

## Task
**Title:** {context.get('title', '')}
**Acceptance Criteria:** {context.get('definition_of_done', '')}
**Task ID:** {context.get('task_id', '')}
**Working Directory:** {context.get('dispatch_repo', '')}""")

    # Skill instructions
    if len(skill_docs) == 1:
        sections.append(f"\n## Skill: {skill_docs[0][0]}\n\n{skill_docs[0][1]}")
    else:
        sections.append("\n## Skills\n\nThis task requires multiple skills. Follow the instructions for each:")
        for skill_name, content in skill_docs:
            sections.append(f"\n### {skill_name}\n\n{content}")

    # Execution instructions
    sections.append(f"""
## Execution

1. Create a feature branch: `dispatch/{context.get('task_id', '')}`
2. Apply each skill's instructions to complete the task
3. Commit using conventional commits (`type: description`)
4. Run tests — fix any failures your changes introduced
5. Push branch and open PR

## Constraints
- Do not modify files unrelated to the task
- Do not add dependencies without clear justification
- If you get stuck or the task is ambiguous, write your findings and stop — do not guess
- A task is NOT complete without a pushed branch and an open PR""")

    # Output contract
    if output_contract:
        sections.append(f"\n---\n\n**Output:** Follow the dispatch output contract for branching, pushing, PR format, evidence upload, and result JSON.\n\n{output_contract}")

    return '\n'.join(sections)


def fetch_vault_note(task_id):
    return api_request('GET', f'/api/vault/notes/{task_id}')


def determine_work_dir(task, normalized_task):
    """Resolve the working directory for a dispatch task."""
    dispatch_repo = normalized_task.get('dispatch_repo', '')
    if not dispatch_repo:
        # Infer from skills or agent_type — coder tasks need a repo
        skills_raw = (normalized_task.get('vault_task') or {}).get('required_skills') or ''
        has_coder = 'coder' in skills_raw or task.get('agent_type') == 'coder'
        if has_coder:
            dispatch_repo = os.path.join(WORK_DIR, 'localshout-next')
    return dispatch_repo or WORK_DIR


# --- Core worker logic ---

def execute_task(task, dry_run=False):
    """Execute a single approved task using Claude Code locally."""
    task_id = task['task_id']
    agent_type = task['agent_type']
    dispatch_id = task['id']

    log(f'Picking up {task_id} ({agent_type})')

    normalized_task = hydrate_task(task, fetch_vault_note)
    if not normalized_task:
        log(f'Vault task not found: {task_id}')
        if not dry_run:
            report_dispatch_failure(dispatch_id, f'Vault task not found: {task_id}')
        return False
    vault_task = normalized_task.get('vault_task') or {}

    # Determine working directory
    work_dir = determine_work_dir(task, normalized_task)

    # Resolve executor and skills
    executor = task.get('executor') or vault_task.get('executor') or 'unknown'
    required_skills = vault_task.get('required_skills') or vault_task.get('suggested_skills') or None

    # Build prompt: compose from skills first, fall back to legacy template
    context = {
        'title': normalized_task.get('title', ''),
        'definition_of_done': normalized_task.get('definition_of_done', ''),
        'dispatch_repo': work_dir,
        'task_id': task_id,
        'output_path': f'/tmp/dispatch-{task_id}-output',
        'executor': executor,
        'executor_description': EXECUTOR_DESCRIPTIONS.get(executor, ''),
        'required_skills': required_skills or '[]',
    }

    prompt = None
    if required_skills:
        prompt = compose_skills_prompt(required_skills, context)
        if prompt:
            log(f'Composed prompt from skills: {required_skills}')

    if not prompt:
        # Legacy fallback: load fixed template by agent_type
        template = load_template(agent_type)
        if not template:
            log(f'No skills or template for task: {task_id} (agent_type={agent_type}, skills={required_skills})')
            if not dry_run:
                report_dispatch_failure(dispatch_id, f'No skills or template available')
            return False
        prompt = render_template(template, context)
        log(f'Using legacy template: {agent_type}')

    if dry_run:
        log(f'DRY RUN: Would execute {task_id} in {work_dir}')
        log(f'Prompt ({len(prompt)} chars):\n{prompt[:300]}...')
        return True

    # Mark as running
    if not report_dispatch_start(dispatch_id, prompt, work_dir):
        preserve_evidence(task_id, 'could not mark task as started in jimbo-api')
        return False
    selection = resolve_dispatch_execution(
        task,
        normalized_task,
        work_dir,
        model=DEFAULT_MODEL,
    )
    core = selection.core
    core.intake(
        reason='Approved task fetched from dispatch queue',
        intake={
            'trigger': 'dispatch-next',
            'dispatch_id': dispatch_id,
            'repo': work_dir,
        },
    )
    core.delegate(
        route={
            'decision': normalized_task.get('flow', 'dispatch'),
            'reason': 'Approved task picked up by dispatch worker',
        },
        reason='Approved task picked up by dispatch worker',
        delegate={
            'agent_type': agent_type,
            'executor': 'claude-code',
            'repo': work_dir,
            'dispatch_id': dispatch_id,
        },
    )
    core.report(
        report={
            'status': 'picked_up',
            'dispatch_id': dispatch_id,
            'summary': 'Task picked up by dispatch worker',
        },
        reason='Execution started on the dispatch worker',
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

    # Timeout based on primary skill (from required_skills) or legacy agent_type
    primary_skill = agent_type
    if required_skills:
        try:
            parsed = json.loads(required_skills) if isinstance(required_skills, str) else required_skills
            if parsed:
                primary_skill = parsed[0]
        except (json.JSONDecodeError, IndexError):
            pass
    timeout = TIMEOUTS.get(primary_skill, 1800)
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
        if not report_dispatch_failure(dispatch_id, f'Timeout after {timeout}s (limit for {agent_type})'):
            preserve_evidence(task_id, 'could not report timeout to jimbo-api')
            return False
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
        if not report_dispatch_failure(dispatch_id, f'Execution error: {e}'):
            preserve_evidence(task_id, 'could not report execution error to jimbo-api')
            return False
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
    review_decision = validate_result(normalized_task, result, work_dir=work_dir)
    report_status = 'failed'
    if not review_decision['accepted']:
        core.review(
            review={
                'status': review_decision['review_status'],
                'summary': result.get('summary', ''),
                'reason': review_decision['reason'],
                'raw_status': result.get('status'),
            },
            reason=review_decision['reason'],
            changed={
                'result_keys': sorted(result.keys()),
            },
        )
        log(f'Task {task_id} review rejected: {review_decision["reason"]}')
        if not report_dispatch_failure(dispatch_id, f'Review rejected: {review_decision["reason"]}'):
            preserve_evidence(task_id, 'could not report review rejection to jimbo-api')
            return False
        report_status = 'rejected'
    elif result['status'] == 'completed':
        core.review(
            review={
                'status': review_decision['review_status'],
                'summary': result.get('summary', ''),
                'artifacts_present': len(result) > 2,
                'reason': review_decision['reason'],
            },
            reason=review_decision['reason'],
        )
        log(f'Task {task_id} completed: {result.get("summary", "")[:100]}')
        if not report_dispatch_complete(dispatch_id, result):
            preserve_evidence(task_id, 'could not report completion to jimbo-api')
            return False
        report_status = 'completed'
    elif result['status'] == 'blocked':
        core.review(
            review={
                'status': review_decision['review_status'],
                'summary': result.get('summary', ''),
                'blockers': result.get('blockers'),
                'reason': review_decision['reason'],
            },
            reason=review_decision['reason'],
        )
        log(f'Task {task_id} blocked: {result.get("blockers", "")}')
        if not report_dispatch_failure(dispatch_id, f'Blocked: {result.get("blockers", "unknown")}'):
            preserve_evidence(task_id, 'could not report blocked status to jimbo-api')
            return False
        if not patch_vault_note(task_id, {'dispatch_status': 'needs_grooming'}):
            preserve_evidence(task_id, 'could not update vault note after blocked result')
            return False
        report_status = 'blocked'
    else:
        core.review(
            review={
                'status': review_decision['review_status'],
                'summary': result.get('summary', ''),
                'reason': review_decision['reason'],
            },
            reason=review_decision['reason'],
        )
        log(f'Task {task_id} failed: {result.get("summary", "")}')
        if not report_dispatch_failure(dispatch_id, result.get('summary', 'Unknown failure')):
            preserve_evidence(task_id, 'could not report failure to jimbo-api')
            return False

    core.report(
        report={
            'status': report_status,
            'dispatch_id': dispatch_id,
            'summary': result.get('summary', ''),
        },
        reason=review_decision.get('reason'),
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


def process_approved_proposals():
    """Create sub-tasks from approved grooming proposals."""
    proposals_result = api_request('GET', '/api/grooming/proposals?status=approved&limit=10')
    if not proposals_result:
        return

    # Handle both list and dict response formats
    if isinstance(proposals_result, dict):
        proposals = proposals_result.get('proposals', [])
    else:
        proposals = proposals_result

    if not proposals:
        return

    for proposal in proposals:
        parent_id = proposal.get("parent_note_id")
        if not parent_id:
            continue

        try:
            data = json.loads(proposal["proposal"]) if isinstance(proposal["proposal"], str) else proposal["proposal"]
        except (json.JSONDecodeError, KeyError):
            log(f'Invalid proposal data for {parent_id}')
            continue

        log(f'Creating sub-tasks for: {data.get("analysis", parent_id)[:80]}')

        for sub in data.get("sub_tasks", []):
            note_body = {
                "title": sub["title"],
                "type": "task",
                "status": "active",
                "suggested_ac": sub.get("acceptance_criteria"),
                "suggested_skills": json.dumps(sub.get("required_skills", [])),
                "parent_note_id": parent_id,
            }

            if sub.get("suggested_executor"):
                note_body["suggested_executor"] = sub["suggested_executor"]

            result = api_request('POST', '/api/vault/notes', note_body)
            if result:
                log(f'  Created: {sub["title"]}')
            else:
                log(f'  Failed: {sub["title"]}')

        # Mark parent as needing review (type stays task, grooming_status updates)
        api_request('PATCH', f'/api/vault/notes/{parent_id}', {
            "grooming_status": "approved",
            "actionability": "needs-breakdown",
        })

        # Mark proposal as processed
        proposal_id = proposal.get('id')
        if proposal_id:
            api_request('PATCH', f'/api/grooming/proposals/{proposal_id}', {
                "status": "processed",
            })

    log(f'Processed {len(proposals)} approved proposals')


def run_once(dry_run=False, stats=None):
    """Check for one approved task and execute it. Returns True if a task was found."""
    # Process any approved decomposition proposals first
    if not dry_run:
        try:
            process_approved_proposals()
        except Exception as e:
            log(f'Error processing proposals: {e}')

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


def emit_next_intake():
    """Print the next approved dispatch task as a runtime intake payload."""
    task = api_request('GET', '/api/dispatch/next')
    if task is None or 'id' not in task:
        log('No approved tasks')
        return False

    normalized_task = hydrate_task(task, fetch_vault_note)
    if not normalized_task:
        log(f'Vault task not found: {task.get("task_id")}')
        return False

    work_dir = determine_work_dir(task, normalized_task)
    print(json.dumps(
        build_dispatch_execution_payload(
            task,
            normalized_task,
            work_dir,
            model=DEFAULT_MODEL,
        ),
        indent=2,
    ))
    return True


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
    update_worker_status(stats.to_dict())

    while True:
        try:
            stats.record_loop()

            # Periodic heartbeat log
            if stats.loop_count % HEARTBEAT_EVERY == 0:
                log(f'Heartbeat: {stats.summary_line()}')
                # Update worker status in API
                update_worker_status(stats.to_dict())

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
            update_worker_status({**stats.to_dict(), 'status': 'stopped'})
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
    emit_intake = '--emit-intake' in args
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

    if emit_intake:
        log('EMIT INTAKE mode')
        dry_run = False
    elif dry_run:
        log('DRY RUN mode (use --live for real execution)')

    # Acquire lock — one task at a time
    # Approach 3: worker pool replaces this
    lock_fd = open(LOCK_FILE, 'w')
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (BlockingIOError, OSError):
        log('Another worker instance is running, exiting')
        return

    if emit_intake:
        emit_next_intake()
    elif loop_mode:
        run_loop(dry_run, poll_interval)
    else:
        if not run_once(dry_run):
            log('No approved tasks')


if __name__ == '__main__':
    main()
