#!/usr/bin/env python3
"""
Jimbo Workflow Orchestration Runtime
Executes workflows (JSON-defined) through pipeline: intake → classify → route → delegate → review → decide
"""

import sys
import json
import uuid
import datetime
import os
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError

try:
    from workers.base_worker import BaseWorker
    from alert import send_telegram_alert
except ImportError:
    BaseWorker = None
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

    def create(self, workflow_id: str, source_task_id: str, run_id: str, current_step: str, state: str, assigned_to: str) -> Optional[Dict[str, Any]]:
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

    def update(self, task_id: str, current_step: str = None, state: str = None, assigned_to: str = None, decisions: List[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
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

        try:
            req = Request(url, data=json.dumps(payload).encode('utf-8'), method='PATCH')
            req.add_header('Content-Type', 'application/json')
            if self.api_key:
                req.add_header('X-API-Key', self.api_key)
            with urlopen(req) as resp:
                return json.loads(resp.read().decode('utf-8'))
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
            workflow = json.load(f)

        required = ['id', 'enabled', 'schedule', 'intake', 'steps']
        for req in required:
            if req not in workflow:
                print(f"ERROR: Missing required field '{req}'")
                return None

        return workflow


# ============================================================================
# Step Executors
# ============================================================================

class ClassifyExecutor:
    """Classify vault task."""

    def __init__(self, workspace_dir: Path):
        self.prompts_dir = workspace_dir / 'prompts'
        self.worker = BaseWorker() if BaseWorker else None

    def execute(self, step: Dict[str, Any], task: Dict[str, Any], task_record: TaskRecord) -> Dict[str, Any]:
        """Call model to classify task."""
        prompt_file = step.get('prompt_file', 'classify-vault-task.md')
        prompt_path = self.prompts_dir / prompt_file
        model = step.get('model', 'haiku')

        if not prompt_path.exists():
            return {'error': 'prompt_not_found', 'category': 'other', 'confidence': 0.0}

        with open(prompt_path, 'r') as f:
            prompt_text = f.read()

        task_context = f"Task: {task.get('title', 'Untitled')}\nDescription: {task.get('description', '')}"

        if self.worker:
            try:
                response = self.worker.call_model(model=model, messages=[
                    {'role': 'system', 'content': prompt_text},
                    {'role': 'user', 'content': task_context}
                ])
                result = json.loads(response)
                task_record.log_decision('classify', result, model=model, cost=0.01)
                return result
            except Exception as e:
                print(f"ERROR in classify: {e}")
                return {'error': str(e), 'category': 'other', 'confidence': 0.0}
        else:
            stub = {'category': 'research', 'confidence': 0.8, 'reasoning': 'Stub'}
            task_record.log_decision('classify', stub, model=model, cost=0.01)
            return stub


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
    """Delegate to worker."""

    def execute(self, step: Dict[str, Any], task: Dict[str, Any], task_record: TaskRecord) -> Dict[str, Any]:
        """Stub delegation."""
        result = {'status': 'completed', 'output': 'Stub result'}
        task_record.log_decision('delegate', result, cost=0.05)
        return result


class ReviewExecutor:
    """Review task outcome."""

    def __init__(self, workspace_dir: Path):
        self.prompts_dir = workspace_dir / 'prompts'
        self.worker = BaseWorker() if BaseWorker else None

    def execute(self, step: Dict[str, Any], task: Dict[str, Any], task_record: TaskRecord) -> Dict[str, Any]:
        """Review outcome."""
        model = step.get('model', 'haiku')
        stub = {'score': 0.85, 'correctness': 0.9, 'completeness': 0.8, 'relevance': 0.85}
        task_record.log_decision('review', stub, model=model, cost=0.01)
        return stub


class DecideExecutor:
    """Make final decision."""

    def execute(self, step: Dict[str, Any], task: Dict[str, Any], task_record: TaskRecord) -> Dict[str, Any]:
        """Apply decide rules."""
        rules = step.get('rules', [])
        review_dec = task_record.decisions[-1].decision if task_record.decisions else {}
        score = review_dec.get('score', 0.5)

        for rule in rules:
            if self._eval_rule(rule.get('if', ''), score):
                action = rule.get('action', '')
                result = {'action': action}
                task_record.final_decision = self._extract_decision(action)
                task_record.log_decision('decide', result)
                return result

        result = {'action': 'assign_to:marvin'}
        task_record.final_decision = 'needs_context'
        task_record.log_decision('decide', result)
        return result

    def _eval_rule(self, rule_if: str, score: float) -> bool:
        """Evaluate score rule."""
        if '>=' in rule_if and '<' not in rule_if:
            return score >= float(rule_if.split('>=')[1].strip())
        elif '<' in rule_if and '>=' not in rule_if:
            return score < float(rule_if.split('<')[1].strip())
        return False

    def _extract_decision(self, action: str) -> str:
        """Extract final decision."""
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
        self.api = TaskRecordAPI(os.getenv("JIMBO_API_URL", "http://localhost:3100/api/workflows"))
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
                assigned_to='jimbo'
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
                    decisions_json = [{'step': d.step, 'decision': d.decision, 'model': d.model, 'worker_id': d.worker_id, 'cost': d.cost, 'timestamp': d.timestamp} for d in tr.decisions]
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
                tr.state = 'completed'
                tr.completed_at = datetime.datetime.utcnow().isoformat()
                self.api.update(task_id=tr.id, state='completed')

            print(f"  Final: {tr.state}\n")

        print(f"{'='*60}\nComplete\n")
        return True

    def _intake(self, workflow: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Test tasks."""
        return [
            {'id': 'task-1', 'title': 'Research LLM fine-tuning', 'description': 'Papers', 'tags': ['research']},
            {'id': 'task-2', 'title': 'Fix auth bug', 'description': 'Debug', 'tags': ['coding']},
            {'id': 'task-3', 'title': 'Schedule dentist', 'description': 'Appointment', 'tags': ['admin']},
        ]


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
