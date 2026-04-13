#!/usr/bin/env python3
"""
Jimbo Workflow Orchestration Runtime
Executes workflows (JSON-defined) through pipeline: intake → classify → route → delegate → review → decide
"""

import sys
import json
import uuid
import datetime
import hashlib
import os
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

try:
    from workers.base_worker import call_model
except ImportError:
    call_model = None

try:
    from alert import send_telegram as send_telegram_alert
except ImportError:
    send_telegram_alert = None


# ============================================================================
# Task Record
# ============================================================================

@dataclass
class Decision:
    """Single decision in workflow execution."""
    step: str
    decision: Dict[str, Any]
    model: Optional[str] = None
    worker_id: Optional[str] = None
    cost: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.datetime.utcnow().isoformat())


@dataclass
class TaskRecord:
    """Workflow task record tracking state through execution."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    workflow_id: str = ""
    source_task_id: str = ""
    run_id: str = ""

    current_step: str = ""
    state: str = "pending"
    assigned_to: str = "jimbo"

    decisions: List[Decision] = field(default_factory=list)
    final_decision: Optional[str] = None

    created_at: str = field(default_factory=lambda: datetime.datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.datetime.utcnow().isoformat())
    completed_at: Optional[str] = None

    def log_decision(self, step_id: str, decision: Dict[str, Any], model: Optional[str] = None, worker_id: Optional[str] = None, cost: float = 0.0):
        """Add decision to audit trail."""
        self.decisions.append(Decision(step=step_id, decision=decision, model=model, worker_id=worker_id, cost=cost))
        self.updated_at = datetime.datetime.utcnow().isoformat()


# ============================================================================
# Task Record API Client
# ============================================================================

class TaskRecordAPI:
    """HTTP client for creating/updating task records in jimbo-api."""

    def __init__(self, base_url: str = "http://localhost:3100/api/workflows", api_key: str = None):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key or os.getenv("JIMBO_API_KEY", "")

    def create(self, workflow_id: str, source_task_id: str, run_id: str, current_step: str, state: str, assigned_to: str, config_hash: Optional[str] = None, title: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Create a task record."""
        url = f"{self.base_url}/tasks"
        payload = {
            'workflow_id': workflow_id,
            'source_task_id': source_task_id,
            'run_id': run_id,
            'current_step': current_step,
            'state': state,
            'assigned_to': assigned_to,
        }
        if config_hash:
            payload['config_hash'] = config_hash
        if title:
            payload['title'] = title

        try:
            req = Request(url, data=json.dumps(payload).encode('utf-8'), method='POST')
            req.add_header('Content-Type', 'application/json')
            if self.api_key:
                req.add_header('X-API-Key', self.api_key)
            with urlopen(req) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except URLError as e:
            print(f"ERROR: Failed to create task record: {e}")
            return None

    def update(self, task_id: str, current_step: str = None, state: str = None, assigned_to: str = None, decisions: List[Dict[str, Any]] = None, final_decision: str = None) -> Optional[Dict[str, Any]]:
        """Update a task record."""
        url = f"{self.base_url}/tasks/{task_id}"
        payload = {}
        if current_step is not None:
            payload['current_step'] = current_step
        if state is not None:
            payload['state'] = state
        if assigned_to is not None:
            payload['assigned_to'] = assigned_to
        if decisions is not None:
            payload['decisions'] = decisions
        if final_decision is not None:
            payload['final_decision'] = final_decision

        try:
            req = Request(url, data=json.dumps(payload).encode('utf-8'), method='PATCH')
            req.add_header('Content-Type', 'application/json')
            if self.api_key:
                req.add_header('X-API-Key', self.api_key)
            with urlopen(req) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except HTTPError as e:
            error_body = e.read().decode('utf-8') if e.fp else ""
            print(f"ERROR: HTTP {e.code} updating task record: {error_body}")
            print(f"DEBUG: Payload was: {json.dumps(payload, indent=2)}")
            return None
        except URLError as e:
            print(f"ERROR: Failed to update task record: {e}")
            return None


# ============================================================================
# Workflow Loader
# ============================================================================

class WorkflowLoader:
    """Load workflow JSON definitions."""

    def __init__(self, workspace_dir: Path):
        self.workflows_dir = workspace_dir / 'workflows'

    def load(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Load workflow JSON by ID."""
        workflow_path = self.workflows_dir / f"{workflow_id}.json"

        if not workflow_path.exists():
            print(f"ERROR: Workflow not found: {workflow_path}")
            return None

        with open(workflow_path, 'r') as f:
            raw = f.read()
            workflow = json.loads(raw)

        required = ['id', 'enabled', 'schedule', 'intake', 'steps']
        for req in required:
            if req not in workflow:
                print(f"ERROR: Missing required field '{req}'")
                return None

        canonical = json.dumps(workflow, sort_keys=True, separators=(',', ':'))
        workflow['config_hash'] = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
        return workflow


# ============================================================================
# Helpers
# ============================================================================

def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Rough cost estimate per model. Returns USD."""
    rates = {
        'gemini-2.5-flash': (0.15 / 1_000_000, 0.60 / 1_000_000),
        'gemini-2.0-flash': (0.10 / 1_000_000, 0.40 / 1_000_000),
        'claude-haiku-4.5': (0.80 / 1_000_000, 4.00 / 1_000_000),
        'claude-sonnet-4-5': (3.00 / 1_000_000, 15.00 / 1_000_000),
    }
    in_rate, out_rate = rates.get(model, (0.50 / 1_000_000, 2.00 / 1_000_000))
    return round(input_tokens * in_rate + output_tokens * out_rate, 6)


# ============================================================================
# Step Executors
# ============================================================================

class ClassifyExecutor:
    """Classify vault task using LLM."""

    def __init__(self, workspace_dir: Path):
        self.prompts_dir = workspace_dir / 'prompts'

    def execute(self, step: Dict[str, Any], task: Dict[str, Any], task_record: TaskRecord) -> Dict[str, Any]:
        """Call model to classify task."""
        prompt_file = step.get('prompt_file', 'classify-vault-task.md')
        prompt_path = self.prompts_dir / prompt_file
        model = step.get('model', 'gemini-2.5-flash')

        if not prompt_path.exists():
            result = {'error': 'prompt_not_found', 'category': 'other', 'confidence': 0.0, '_stub': True}
            task_record.log_decision('classify', result, model='none', cost=0)
            return result

        with open(prompt_path, 'r') as f:
            prompt_text = f.read()

        tags = task.get('tags', [])
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except (json.JSONDecodeError, TypeError):
                tags = [t.strip() for t in tags.split(',') if t.strip()]

        task_context = (
            f"Task: {task.get('title', 'Untitled')}\n"
            f"Description: {task.get('description', '')}\n"
            f"Tags: {', '.join(tags) if tags else 'none'}\n"
            f"Created: {task.get('created_at', 'unknown')}"
        )

        if not call_model:
            stub = {'category': 'other', 'confidence': 0.0, 'reasoning': 'call_model unavailable', '_stub': True}
            task_record.log_decision('classify', stub, model='none', cost=0)
            return stub

        try:
            response = call_model(task_context, model=model, system=prompt_text)
            text = response.get('text', '').strip()
            # Extract JSON from response (may be wrapped in markdown code block)
            json_match = text
            if '```' in text:
                import re
                m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
                if m:
                    json_match = m.group(1)
            result = json.loads(json_match)
            cost = _estimate_cost(model, response.get('input_tokens', 0), response.get('output_tokens', 0))
            task_record.log_decision('classify', result, model=model, cost=cost)
            return result
        except Exception as e:
            print(f"  ERROR in classify: {e}")
            result = {'error': str(e), 'category': 'other', 'confidence': 0.0, '_stub': True}
            task_record.log_decision('classify', result, model='none', cost=0)
            return result


class RouteExecutor:
    """Route task based on classification."""

    def execute(self, step: Dict[str, Any], task: Dict[str, Any], task_record: TaskRecord) -> Dict[str, Any]:
        """Apply routing rules."""
        rules = step.get('rules', [])
        classify_dec = task_record.decisions[-1].decision if task_record.decisions else {}
        category = classify_dec.get('category', 'other')
        confidence = classify_dec.get('confidence', 0.0)

        for rule in rules:
            if self._eval_rule(rule.get('if', ''), category, confidence):
                action = rule.get('action', '')
                result = {'action': action, 'assigned_to': 'marvin' if 'marvin' in action else 'jimbo'}
                task_record.assigned_to = result['assigned_to']
                task_record.log_decision('route', result)
                return result

        result = {'action': 'assign_to:jimbo', 'assigned_to': 'jimbo'}
        task_record.log_decision('route', result)
        return result

    def _eval_rule(self, rule_if: str, category: str, confidence: float) -> bool:
        """Evaluate rule expression."""
        if 'category' in rule_if and '==' in rule_if:
            target = rule_if.split('==')[1].strip().strip("'\"")
            return category == target
        elif 'confidence' in rule_if and '<' in rule_if:
            return confidence < float(rule_if.split('<')[1].strip())
        return False


class DelegateExecutor:
    """Produce dispatch recommendation — does NOT execute work."""

    DISPATCH_PROMPT = """You are deciding how a vault task should be handled. You do NOT do the work — you recommend a dispatch path.

Task: {title}
Description: {description}
Category: {category}
Route: {route_action}

Return JSON with exactly these fields:
{{
  "dispatch": "agent" | "marvin" | "archive",
  "agent_type": "research" | "coding" | "writing" | null,
  "reason": "1 sentence why this dispatch path",
  "effort": "trivial" | "small" | "medium" | "large"
}}

Rules:
- "agent": task can be done by an AI agent (research, code generation, writing drafts)
- "marvin": task requires human judgment, physical action, or account access
- "archive": task is stale, duplicate, or already done
- agent_type is null when dispatch is "marvin" or "archive"
- effort estimates how much work the task is, not how hard the decision is"""

    def execute(self, step: Dict[str, Any], task: Dict[str, Any], task_record: TaskRecord) -> Dict[str, Any]:
        """Recommend dispatch path for task."""
        model = step.get('fallback_model', 'gemini-2.5-flash')
        title = task.get('title', 'Untitled')
        description = task.get('description', '')

        classify_dec = next((d for d in task_record.decisions if d.step == 'classify'), None)
        category = classify_dec.decision.get('category', 'other') if classify_dec else 'other'

        route_dec = next((d for d in task_record.decisions if d.step == 'route'), None)
        route_action = route_dec.decision.get('action', '') if route_dec else ''

        if not call_model:
            result = {'dispatch': 'marvin', 'agent_type': None, 'reason': 'no model available', 'effort': 'unknown', '_stub': True}
            task_record.log_decision('delegate', result, cost=0)
            return result

        prompt = self.DISPATCH_PROMPT.format(
            title=title, description=description, category=category, route_action=route_action
        )

        try:
            response = call_model(prompt, model=model)
            text = response.get('text', '').strip()
            if '```' in text:
                import re
                m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
                if m:
                    text = m.group(1)
            result = json.loads(text)
            cost = _estimate_cost(model, response.get('input_tokens', 0), response.get('output_tokens', 0))
            task_record.log_decision('delegate', result, model=model, cost=cost)
            return result
        except Exception as e:
            print(f"  ERROR in delegate: {e}")
            result = {'dispatch': 'marvin', 'agent_type': None, 'reason': f'assessment failed: {e}', 'effort': 'unknown', '_stub': True}
            task_record.log_decision('delegate', result, cost=0)
            return result


class ReviewExecutor:
    """Review task outcome using LLM."""

    def __init__(self, workspace_dir: Path):
        self.prompts_dir = workspace_dir / 'prompts'

    def execute(self, step: Dict[str, Any], task: Dict[str, Any], task_record: TaskRecord) -> Dict[str, Any]:
        """Review delegate output quality."""
        prompt_file = step.get('prompt_file', 'review-outcome.md')
        prompt_path = self.prompts_dir / prompt_file
        model = step.get('model', 'gemini-2.5-flash')

        # Gather context from prior decisions
        classify_dec = next((d for d in task_record.decisions if d.step == 'classify'), None)
        delegate_dec = next((d for d in task_record.decisions if d.step == 'delegate'), None)

        if not prompt_path.exists() or not call_model:
            stub = {'score': 0.5, 'correctness': 0.5, 'completeness': 0.5, 'relevance': 0.5,
                    'issues': ['no model available' if not call_model else 'prompt not found'],
                    'recommendation': 'assign_to_marvin', '_stub': True}
            task_record.log_decision('review', stub, model='none', cost=0)
            return stub

        with open(prompt_path, 'r') as f:
            prompt_text = f.read()

        review_context = (
            f"Original Task: {task.get('title', 'Untitled')}\n"
            f"Description: {task.get('description', '')}\n\n"
            f"Classification: {json.dumps(classify_dec.decision) if classify_dec else 'none'}\n\n"
            f"Worker Output: {json.dumps(delegate_dec.decision) if delegate_dec else 'none'}"
        )

        try:
            response = call_model(review_context, model=model, system=prompt_text)
            text = response.get('text', '').strip()
            if '```' in text:
                import re
                m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
                if m:
                    text = m.group(1)
            result = json.loads(text)
            cost = _estimate_cost(model, response.get('input_tokens', 0), response.get('output_tokens', 0))
            task_record.log_decision('review', result, model=model, cost=cost)
            return result
        except Exception as e:
            print(f"  ERROR in review: {e}")
            stub = {'score': 0.5, 'correctness': 0.5, 'completeness': 0.5, 'relevance': 0.5,
                    'issues': [str(e)], 'recommendation': 'assign_to_marvin', '_stub': True}
            task_record.log_decision('review', stub, model='none', cost=0)
            return stub


class DecideExecutor:
    """Make final decision based on review scores and dispatch recommendation."""

    def execute(self, step: Dict[str, Any], task: Dict[str, Any], task_record: TaskRecord) -> Dict[str, Any]:
        """Apply decide rules against review output."""
        rules = step.get('rules', [])
        review_dec = next((d for d in reversed(task_record.decisions) if d.step == 'review'), None)
        delegate_dec = next((d for d in reversed(task_record.decisions) if d.step == 'delegate'), None)
        review = review_dec.decision if review_dec else {}
        delegate = delegate_dec.decision if delegate_dec else {}
        score = review.get('score', 0.5)

        for rule in rules:
            if self._eval_rule(rule.get('if', ''), score):
                action = rule.get('action', '')

                if 'accept_recommendation' in action:
                    # Use the delegate's dispatch recommendation as the final decision
                    dispatch = delegate.get('dispatch', 'marvin')
                    agent_type = delegate.get('agent_type')
                    reason = delegate.get('reason', '')
                    effort = delegate.get('effort', 'unknown')

                    if dispatch == 'archive':
                        task_record.final_decision = 'archive'
                    elif dispatch == 'agent':
                        task_record.final_decision = f'dispatch:{agent_type or "general"}'
                    else:
                        task_record.final_decision = 'needs_marvin_review'
                        task_record.assigned_to = 'marvin'

                    result = {
                        'action': f'accepted:{dispatch}',
                        'dispatch': dispatch, 'agent_type': agent_type,
                        'reason': reason, 'effort': effort, 'score': score,
                    }
                else:
                    task_record.final_decision = self._extract_decision(action)
                    if 'marvin' in action:
                        task_record.assigned_to = 'marvin'
                    result = {'action': action, 'score': score}

                task_record.log_decision('decide', result)
                return result

        # Default: assign to marvin
        result = {'action': 'assign_to:marvin', 'score': score}
        task_record.final_decision = 'needs_marvin_review'
        task_record.assigned_to = 'marvin'
        task_record.log_decision('decide', result)
        return result

    def _eval_rule(self, rule_if: str, score: float) -> bool:
        """Evaluate score rule. Handles: 'score >= 0.8', 'score < 0.5', '0.5 <= score < 0.8'."""
        import re
        m = re.match(r'([\d.]+)\s*<=\s*score\s*<\s*([\d.]+)', rule_if)
        if m:
            return float(m.group(1)) <= score < float(m.group(2))
        if '>=' in rule_if:
            return score >= float(rule_if.split('>=')[1].strip())
        if '<' in rule_if:
            return score < float(rule_if.split('<')[1].strip())
        return False

    def _extract_decision(self, action: str) -> str:
        """Extract final decision label from action string."""
        if 'archive' in action:
            return 'archive'
        elif 'needs_context' in action:
            return 'needs_context'
        elif 'marvin' in action:
            return 'needs_marvin_review'
        return 'unknown'


# ============================================================================
# Workflow Runner
# ============================================================================

class WorkflowRunner:
    """Execute workflows end-to-end."""

    def __init__(self, workspace_dir: Path):
        self.workspace_dir = workspace_dir
        self.loader = WorkflowLoader(workspace_dir)
        api_base = os.getenv("JIMBO_API_URL", "http://localhost:3100").rstrip('/')
        self.api = TaskRecordAPI(f"{api_base}/api/workflows")
        self.executors = {
            'classify': ClassifyExecutor(workspace_dir),
            'route': RouteExecutor(),
            'delegate': DelegateExecutor(),
            'review': ReviewExecutor(workspace_dir),
            'decide': DecideExecutor(),
        }

    def run(self, workflow_id: str, run_id: str, test_tasks: Optional[List[Dict[str, Any]]] = None):
        """Execute workflow end-to-end."""
        print(f"\n{'='*60}\nWorkflow: {workflow_id}, Run: {run_id}\n{'='*60}\n")

        workflow = self.loader.load(workflow_id)
        if not workflow:
            return False

        tasks = test_tasks or self._intake(workflow)
        if not tasks:
            print("No tasks")
            return True

        print(f"Processing {len(tasks)} task(s)\n")

        for i, task in enumerate(tasks, 1):
            print(f"--- Task {i}: {task.get('title', 'Untitled')} ---")
            tr = TaskRecord(workflow_id=workflow_id, source_task_id=task.get('id', f'task-{i}'), run_id=run_id)

            # Create task record in API
            api_task = self.api.create(
                workflow_id=workflow_id,
                source_task_id=tr.source_task_id,
                run_id=run_id,
                current_step='',
                state='pending',
                assigned_to='jimbo',
                config_hash=workflow.get('config_hash'),
                title=task.get('title'),
            )
            if api_task:
                tr.id = api_task.get('id', tr.id)
                print(f"  Created task record: {tr.id}")

            for step in workflow.get('steps', []):
                tr.current_step = step.get('id')
                tr.state = 'in_progress'

                executor = self.executors.get(step.get('type'))
                if not executor:
                    continue

                try:
                    executor.execute(step, task, tr)
                    print(f"  [{tr.current_step}] OK")

                    # Update task record after step
                    # Serialize decisions, excluding null fields (Zod schema validation)
                    decisions_json = []
                    for d in tr.decisions:
                        dec = {'step': d.step, 'decision': d.decision, 'timestamp': d.timestamp}
                        if d.model is not None:
                            dec['model'] = d.model
                        if d.worker_id is not None:
                            dec['worker_id'] = d.worker_id
                        if d.cost > 0:
                            dec['cost'] = d.cost
                        decisions_json.append(dec)
                    self.api.update(
                        task_id=tr.id,
                        current_step=tr.current_step,
                        state=tr.state,
                        assigned_to=tr.assigned_to,
                        decisions=decisions_json
                    )

                    if tr.assigned_to == 'marvin':
                        print(f"  [PAUSE] Assigned to marvin")
                        tr.state = 'awaiting_human'
                        self.api.update(task_id=tr.id, state='awaiting_human')
                        break

                except Exception as e:
                    print(f"  ERROR: {e}")
                    tr.state = 'failed'
                    self.api.update(task_id=tr.id, state='failed')
                    break

            if tr.state == 'in_progress':
                # If final decision needs human, don't mark completed
                if tr.final_decision in ('needs_context', 'needs_marvin_review'):
                    tr.state = 'awaiting_human'
                    tr.assigned_to = 'marvin'
                    self.api.update(task_id=tr.id, state='awaiting_human', assigned_to='marvin', final_decision=tr.final_decision)
                else:
                    tr.state = 'completed'
                    tr.completed_at = datetime.datetime.utcnow().isoformat()
                    self.api.update(task_id=tr.id, state='completed', final_decision=tr.final_decision)

            print(f"  Final: {tr.state}\n")

        print(f"{'='*60}\nComplete\n")
        return True

    def _intake(self, workflow: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fetch tasks from vault API based on workflow intake config."""
        intake = workflow.get('intake', {})
        source = intake.get('source', 'vault-api')
        limit = intake.get('limit', 20)

        if source != 'vault-api':
            print(f"  Unsupported intake source: {source}")
            return []

        api_url = os.getenv("JIMBO_API_URL", "http://localhost:3100")
        api_key = os.getenv("JIMBO_API_KEY", "")
        url = f"{api_url}/api/vault/notes?status=active&ready=true&limit={limit}&sort=created_at&order=asc"

        try:
            req = Request(url, method='GET')
            if api_key:
                req.add_header('X-API-Key', api_key)
            with urlopen(req) as resp:
                data = json.loads(resp.read().decode('utf-8'))
        except (URLError, HTTPError) as e:
            print(f"  ERROR: Failed to fetch vault tasks: {e}")
            return []

        notes = data.get('items', data.get('notes', []))
        if not notes:
            print("  No inbox tasks found in vault")
            return []

        print(f"  Fetched {len(notes)} inbox task(s) from vault")
        tasks = []
        for i, note in enumerate(notes, 1):
            # Tags may be a JSON array string like '["tag1","tag2"]' or null
            raw_tags = note.get('tags')
            if isinstance(raw_tags, str):
                try:
                    tags = json.loads(raw_tags)
                except (json.JSONDecodeError, ValueError):
                    tags = [t.strip() for t in raw_tags.split(',') if t.strip()]
            elif isinstance(raw_tags, list):
                tags = raw_tags
            else:
                tags = []

            tasks.append({
                'id': note.get('id', f'note-{i}'),
                'title': note.get('title', 'Untitled'),
                'description': note.get('body', ''),
                'tags': tags,
                'type': note.get('type', 'task'),
            })
        return tasks


# ============================================================================
# Main
# ============================================================================

def run_workflow(workflow_id: str, run_id: Optional[str] = None, workspace_dir: Optional[Path] = None):
    """Execute workflow by ID or file path."""
    if not workspace_dir:
        workspace_dir = Path(__file__).parent
    if not run_id:
        run_id = f"run-{datetime.datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"

    # If workflow_id looks like a file path, extract the workflow ID from the filename
    if '/' in workflow_id or '\\' in workflow_id:
        workflow_path = Path(workflow_id)
        if workflow_path.exists():
            workflow_id = workflow_path.stem  # Get filename without extension
        else:
            print(f"ERROR: Workflow file not found: {workflow_path}")
            return False

    return WorkflowRunner(workspace_dir).run(workflow_id, run_id)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python3 jimbo_runtime.py <workflow_id|workflow_file> [run_id]")
        sys.exit(1)
    workflow_input = sys.argv[1]
    run_id = sys.argv[2] if len(sys.argv) > 2 else None
    success = run_workflow(workflow_input, run_id)
    sys.exit(0 if success else 1)
