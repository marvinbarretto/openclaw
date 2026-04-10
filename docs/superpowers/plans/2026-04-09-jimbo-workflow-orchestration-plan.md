# Jimbo Workflow Orchestration Implementation Plan

**Date:** 2026-04-09  
**Status:** Ready to Execute  
**Scope:** Build unified orchestration system with vault task triage as proof-of-concept  
**Deliverables:** YAML workflow engine, task record tracking, human pause points, metrics dashboard

---

## Overview

Implement the orchestration system from `2026-04-09-jimbo-workflow-orchestration-design.md`. This plan is incremental: Phase 1 gets vault triage working end-to-end, Phase 2 adds metrics/iteration tools.

---

## Phase 1: Core Orchestration Engine

### Step 1.1: Workflow YAML Schema (Day 1)

**Deliverable:** JSON schema + example YAML files

**Changes:**
- Create `workspace/workflows/schema.json` — validation schema for workflow YAML
- Create `workspace/workflows/vault-triage.yaml` — first workflow definition (from design spec)
- Create `workspace/prompts/` directory structure:
  - `prompts/classify-vault-task.md` — classify task into categories
  - `prompts/review-outcome.md` — review worker result quality

**Files to create:**
- `/workspace/workflows/schema.json`
- `/workspace/workflows/vault-triage.yaml`
- `/workspace/prompts/classify-vault-task.md`
- `/workspace/prompts/review-outcome.md`

**Acceptance criteria:**
- Schema validates the vault-triage.yaml file
- Prompts are focused and testable in isolation

---

### Step 1.2: Workflow Runtime Executor (Days 2-3)

**Deliverable:** `jimbo_runtime.py` — the execution engine

**Changes:**
- Create `workspace/jimbo_runtime.py` with:
  - `WorkflowLoader` class — load and validate YAML
  - `WorkflowRunner` class — execute steps sequentially
  - `StepExecutor` (classify, route, delegate, review, decide) — each step type
  - `TaskRecord` wrapper — track state through execution
  - Main entry point: `run_workflow(workflow_id, run_id)`

**Design decisions:**
- Use `jsonschema` (stdlib doesn't validate JSON schema, but we can do manual validation)
- API client for jimbo-api calls (already exists in workspace)
- Model calls via `base_worker.py` (Haiku for classify/review, delegate goes to dispatch)
- Telegram integration via `alert.py` when assigning to human

**Acceptance criteria:**
- Can load `vault-triage.yaml` without errors
- Runs through all 5 steps (classify → route → delegate → review → decide) for a single test task
- Logs all decisions to console (jimbo-api logging added in Step 1.3)

**Code structure:**
```python
# workspace/jimbo_runtime.py

class WorkflowLoader:
    def load(self, workflow_id: str) -> dict:
        """Load YAML, validate against schema, return parsed dict"""
        
class TaskRecord:
    """Wrapper around jimbo-api task_record_t"""
    def __init__(self, task, workflow_id, run_id):
        self.source_task_id = task['id']
        self.workflow_id = workflow_id
        self.state = 'in_progress'
        self.assigned_to = 'jimbo'
        self.decisions = []
        
    def log_decision(self, step_id, decision, metadata):
        """Add decision to audit trail"""
        
    def save_to_api(self, api_client):
        """POST to jimbo-api"""

class WorkflowRunner:
    def run(self, workflow_id, run_id, tasks=None):
        """Execute workflow end-to-end"""
        workflow = WorkflowLoader().load(workflow_id)
        
        for task in tasks or self.intake(workflow):
            task_record = TaskRecord(task, workflow_id, run_id)
            
            for step in workflow['steps']:
                if step['type'] == 'classify':
                    result = self.execute_classify(step, task, task_record)
                elif step['type'] == 'route':
                    result = self.execute_route(step, task_record)
                    # If routed to human, pause
                    if result['assigned_to'] == 'marvin':
                        task_record.assigned_to = 'marvin'
                        task_record.state = 'awaiting_human'
                        self.notify_human(task_record)
                        break
                # ... more steps
                
                task_record.log_decision(step['id'], result, {...})
            
            task_record.state = 'completed'
            # save_to_api() in Step 1.3

def run_workflow(workflow_id, run_id):
    runner = WorkflowRunner()
    runner.run(workflow_id, run_id)
```

---

### Step 1.3: jimbo-api Task Record Endpoints (Days 2-3, parallel)

**Deliverable:** API routes for workflow task records

**Changes to jimbo-api:**
- New schema: `WorkflowTaskRecord` (from design spec)
- Routes:
  - `POST /api/workflows/tasks` — create task record
  - `PATCH /api/workflows/tasks/:id` — update decisions/state
  - `GET /api/workflows/tasks` — list all (for dashboard)
  - `GET /api/workflows/tasks/:id` — get single task
  
**SQLite schema additions:**
- Table: `workflow_task_records` (id, workflow_id, source_task_id, current_step, state, assigned_to, decisions JSON, human_input JSON, final_decision, created_at, updated_at, completed_at)

**Acceptance criteria:**
- Can POST a task record and retrieve it
- Decisions array can be appended to
- State transitions work (pending → in_progress → awaiting_human → completed)

---

### Step 1.4: Telegram Human Pause Integration (Day 4)

**Deliverable:** Telegram notification when workflow pauses for human input

**Changes:**
- Update `jimbo_runtime.py`: when `assigned_to: marvin`, call Telegram
- Update `alert.py` to accept workflow context in message:
  - Task name, current step, what decision is needed, suggestion
  - Link to Site UI for detailed review
  
**Telegram message template:**
```
🔄 Workflow Pause: Vault Triage

Task: [task title]
Step: Needs Your Review
Current Status: [step summary]
Jimbo's suggestion: [decision]

Respond here or review at: site.marvinbarretto.workers.dev/app/jimbo/workflows/vault-triage/tasks/[id]
```

**Acceptance criteria:**
- When a task is assigned to marvin, Telegram message is posted
- Message includes enough context to make a decision
- Link to Site UI works

---

### Step 1.5: Vault Triage Workflow Implementation (Days 4-5)

**Deliverable:** Vault triage workflow runs end-to-end on schedule

**Changes:**
- Write intake logic: query vault API for `status:unprocessed AND age_days < 30`
- Write classify prompt: category + confidence + reasoning
- Write route rules: research → research-worker, coding → code-agent, copy → edit-worker, admin → assign to marvin, else → assign to jimbo
- Write delegate wrapper: calls dispatch system (already exists from ADR-025)
- Write review prompt: score outcome on correctness/completeness/relevance
- Write decide rules: score >= 0.8 → archive, >= 0.5 → assign to marvin (partial), < 0.5 → needs_context

**Cron entry** (in VPS root crontab):
```bash
# Vault triage workflows at 9am, 3pm, 6pm
0 9,15,18 * * * cd /home/openclaw/jimbo-workspace && python3 jimbo_runtime.py vault-triage
```

**Acceptance criteria:**
- Runs without errors on 3 test tasks
- Creates task records in jimbo-api
- Routes to different workers correctly
- Pauses when human input needed
- Logs all decisions

---

### Step 1.6: Integration Testing (Day 5)

**Deliverable:** Test suite in `workspace/tests/test_jimbo_runtime.py`

**Test cases:**
- Load vault-triage.yaml schema validation
- Execute classify step, verify output schema
- Route step applies rules correctly
- Delegate step calls dispatch (mock)
- Review step scores outcomes
- Decide step transitions state
- Task record saved to API
- Human assignment pauses workflow

**Run:**
```bash
cd /workspace && python3 -m pytest tests/test_jimbo_runtime.py -v
```

**Acceptance criteria:**
- All tests pass
- Code coverage >= 80% for core paths

---

## Phase 2: Metrics & Iteration Tools (Post-Phase 1)

### Step 2.1: Workflow Dashboard (Day 6)

**Deliverable:** Site UI dashboard showing workflow runs

**Changes to Site:**
- New page: `/app/jimbo/workflows`
  - Lists all workflow runs (with timestamps, status, task counts)
  - Drill-in to single run: all tasks, decisions, costs
  - Drill-in to single task: decision tree, reasoning, model calls
  - Compare runs: Haiku vs Sonnet costs, success rates, override frequency

**Acceptance criteria:**
- Dashboard loads without errors
- Shows real data from jimbo-api

---

### Step 2.2: Metrics & A/B Testing (Days 6-7)

**Deliverable:** Track and compare workflow runs

**Changes:**
- Add `config_hash` to workflow_task_records (auto-computed on load)
- Query endpoint: `GET /api/workflows/metrics?workflow=vault-triage&group_by=config_hash`
- Returns: success rate, avg cost, human override rate per config

**Acceptance criteria:**
- Can compare vault-triage results from 2 different YAML versions
- Metrics show clear differences in cost/success/override rates

---

## Critical Path (What Must Work First)

1. **Workflow YAML + Schema** (Step 1.1) — foundation for everything
2. **jimbo_runtime.py** (Step 1.2) — the executor
3. **jimbo-api endpoints** (Step 1.3) — persistence layer
4. **Telegram integration** (Step 1.4) — human pause points
5. **Vault triage workflow** (Step 1.5) — end-to-end proof of concept
6. **Testing** (Step 1.6) — validation before cron

**Parallel work:** Steps 1.2 and 1.3 can be done simultaneously (different repos).

---

## Technical Notes

### Model Usage

- **Classify step:** Haiku 4.5 (fast, cheap classification)
- **Review step:** Haiku 4.5 (same reasoning)
- **Delegate step:** Dispatch to appropriate worker (Sonnet, code-agent, etc.)

### Error Handling

- Invalid YAML → error logged, workflow skipped
- Model call fails → retry once, then assign to marvin
- Dispatch times out → fallback model (Sonnet) or assign to marvin
- API call fails → exponential backoff, max 3 retries, then manual intervention flag

### No Breaking Changes

- Existing vault triage process (vault-triage.py) stays unchanged during this work
- jimbo-api is backwards-compatible (new routes only)
- Cron can run both old and new systems in parallel during rollover

---

## Rollout (Revised Workflow)

**Session 1 (Current worktree):**
- Step 1.1: Workflow YAML schema + vault-triage.yaml + prompts
- Step 1.2: jimbo_runtime.py executor
- Merge to master, exit worktree

**Session 2 (Separate jimbo-api work):**
- Step 1.3: Task record endpoints in jimbo-api
- Step 1.4: Telegram integration
- Test on jimbo-api side

**Session 3 (Vault triage workflow):**
- Step 1.5: Implement end-to-end vault triage workflow
- Step 1.6: Integration tests
- Dry-run on real vault data

**Session 4 (Deployment):**
- Deploy cron entry
- Monitor: check task records, human pause points, costs
- Build dashboard (Step 2.1)

---

## Success Criteria

- ✅ Core engine loads and executes workflows
- ✅ Vault triage workflow processes real tasks end-to-end
- ✅ Human pause points work (Telegram notification, Site UI review)
- ✅ All decisions logged to jimbo-api
- ✅ Task records queryable and visible in dashboard
- ✅ Can swap models/prompts in YAML and see different results
- ✅ Zero production impact during rollover (old + new run in parallel)

---

## Files to Create/Modify

### New Files
- `workspace/jimbo_runtime.py` — execution engine
- `workspace/workflows/schema.json` — YAML validation
- `workspace/workflows/vault-triage.yaml` — proof-of-concept workflow
- `workspace/prompts/classify-vault-task.md` — classification prompt
- `workspace/prompts/review-outcome.md` — review prompt
- `workspace/tests/test_jimbo_runtime.py` — test suite

### Modified Files (jimbo-api)
- `src/db/schema.ts` — add WorkflowTaskRecord table
- `src/routes/workflows.ts` — new routes (POST/PATCH/GET tasks)
- `src/index.ts` — register routes

### VPS Changes
- VPS root crontab: add vault-triage workflow entry
- `/opt/openclaw.env`: verify ANTHROPIC_API_KEY, GOOGLE_AI_API_KEY present

---

## Next Step

Start with Step 1.1: create workflow schema and vault-triage.yaml template.
