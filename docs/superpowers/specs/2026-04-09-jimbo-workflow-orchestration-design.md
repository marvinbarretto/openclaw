# Jimbo Workflow Orchestration System Design

**Date:** 2026-04-09  
**Status:** Approved  
**Scope:** Unified orchestration system with vault task triage as proof-of-concept  
**Author:** Claude Code + Marvin Barretto

---

## Problem

Jimbo has sophisticated execution infrastructure (runtime, dispatch, routing) but lacks a unified orchestration layer that ties together the canonical loop: `intake → classify → route → delegate → review → log → report`.

Currently:
- Workers are scattered across specialized scripts
- Classification happens inside workers, not centrally
- Review/log/report are async and disconnected from execution
- Workflows are implicit in cron schedules, not managed or iterable

Result: Hard to understand what Jimbo is doing, hard to improve without code changes, hard to delegate and wait for human feedback.

---

## Design Principles

1. **Workflows are first-class, versioned objects** — defined in YAML, source-controlled, iterable without code changes
2. **Sequential execution with human pause points** — process tasks step-by-step, pause when human input needed, resume when available
3. **Assignment model** — every step is owned by either Jimbo or Marvin (human)
4. **Everything is logged** — every decision, every model call, every outcome goes to jimbo-api
5. **Metrics for iteration** — track success rates, model costs, human override rates, enable A/B testing

---

## Architecture

### **1. Workflow Definition (YAML)**

Workflows live in `workspace/workflows/<workflow-id>.yaml` and describe:
- **Intake:** where to get tasks and how to filter them
- **Steps:** classify → route → delegate → review → decide
- **Decision rules:** what to do based on outcomes
- **Integration points:** Telegram, Site UI for human feedback

Example: `workspace/workflows/vault-triage.yaml`

```yaml
id: vault-triage
enabled: true
description: "Classify and route vault tasks through delegation pipeline"

# Schedule: run at 9am, 3pm, 6pm daily
schedule: "0 9,15,18 * * *"

# Phase 1: intake
intake:
  source: vault-api
  filter: "status:unprocessed AND age_days < 30"
  limit: 20
  
# Phase 2-6: process each task through the loop
steps:
  
  # Step 1: Classify the task
  - id: classify
    type: classify
    model: haiku
    prompt_file: prompts/classify-vault-task.md
    output_schema:
      category: "admin|research|copy|coding|scheduling|other"
      confidence: 0.0-1.0
      reasoning: string
      
  # Step 2: Route based on classification
  - id: route
    type: decision
    rules:
      - if: category == research → action: delegate_to:research-worker
      - if: category == coding → action: delegate_to:code-agent
      - if: category == copy → action: delegate_to:edit-worker
      - if: category == admin → action: assign_to:marvin
      - else: → action: assign_to:jimbo
      
  # Step 3: Execute delegation (if routed)
  - id: delegate
    type: delegate
    timeout_seconds: 300
    fallback_model: sonnet
    worker_selection: "from route decision"
    
  # Step 4: Review the outcome
  - id: review
    type: review
    model: haiku
    prompt_file: prompts/review-outcome.md
    criteria:
      - correctness
      - completeness
      - relevance_to_context
      
  # Step 5: Decide final action
  - id: decide
    type: decision
    rules:
      - if: review_score >= 0.8 → action: archive
      - if: review_score >= 0.5 AND review_score < 0.8 → action: assign_to:marvin (partial result)
      - if: review_score < 0.5 → action: needs_context
      - if: any_step_unclear → action: assign_to:marvin (request decision)

# Integration: notify human when needed
human_feedback:
  channels: [telegram, site-ui]
  notify_async: true  # post message, don't wait for response
  decision_override: true  # human can override any Jimbo decision

# Observability
logging:
  destination: jimbo-api
  track:
    - task_id, vault_task_reference
    - current_step
    - assigned_to (jimbo or marvin)
    - decisions (step-by-step)
    - model_calls (which model, cost)
    - outcomes (success/partial/failure)
    - timestamps

# Versioning for iteration
metadata:
  version: "1.0"
  created: "2026-04-09"
  config_hash: null  # auto-computed on load
```

### **2. Task Record in jimbo-api**

Every task entering a workflow gets a record in `jimbo-api`:

```typescript
// Type: WorkflowTaskRecord
{
  id: UUID                          // unique to this run
  workflow_id: "vault-triage"       // which workflow
  source_task_id: UUID              // vault task ID
  
  current_step: "classify" | "route" | "delegate" | "review" | "decide"
  state: "pending" | "in_progress" | "awaiting_human" | "completed" | "failed"
  assigned_to: "jimbo" | "marvin"
  
  decisions: [
    {
      step: "classify",
      decision: { category: "research", confidence: 0.92 },
      model: "haiku",
      reasoning: "...",
      timestamp: ISO
    },
    {
      step: "route",
      decision: "delegate_to:research-worker",
      timestamp: ISO
    },
    {
      step: "delegate",
      worker_id: "research-worker-42",
      result: { status: "completed", ... },
      model_used: "sonnet",
      cost: 0.15,
      timestamp: ISO
    },
    // ... more decisions
  ]
  
  human_input: {
    requested: boolean
    requested_at: ISO
    responded: boolean
    response: string
    responded_at: ISO
  }
  
  final_decision: "archive" | "notes" | "needs_context" | "needs_work"
  
  created_at: ISO
  updated_at: ISO
  completed_at: ISO (if done)
}
```

### **3. Execution Loop (Runtime)**

High-level flow in `jimbo_runtime.py`:

```python
def run_workflow(workflow_id: str, run_id: str):
    """
    Execute a workflow end-to-end.
    
    For each task:
      1. Intake (get the task)
      2. For each step in workflow:
         a. Execute the step (classify, route, delegate, review, decide)
         b. Log decision to jimbo-api
         c. If step assigns to human → pause, notify Telegram, wait for response
         d. If step completes → continue to next step
      3. Final state → completed
    """
    
    workflow = load_workflow_yaml(workflow_id)
    run_record = create_workflow_run(workflow_id, run_id)
    
    tasks = intake(workflow)  # get vault tasks
    
    for task in tasks:
        task_record = create_task_record(task, workflow_id, run_id)
        
        for step in workflow.steps:
            task_record.current_step = step.id
            
            # Execute the step
            if step.type == "classify":
                result = call_model(step.model, step.prompt_file, task)
                task_record.decisions.append({
                    step: step.id,
                    decision: result,
                    model: step.model
                })
                
            elif step.type == "decision":
                action = evaluate_rules(step.rules, task_record)
                task_record.decisions.append({
                    step: step.id,
                    decision: action
                })
                
                # If action assigns to human, pause
                if action.startswith("assign_to:marvin"):
                    task_record.assigned_to = "marvin"
                    task_record.state = "awaiting_human"
                    post_to_telegram(task_record)
                    save_to_jimbo_api(task_record)
                    break  # pause here, exit step loop
                    
            elif step.type == "delegate":
                worker = get_worker_for_task(task_record)
                result = dispatch_worker(
                    worker,
                    task,
                    timeout=step.timeout_seconds,
                    fallback_model=step.fallback_model
                )
                task_record.decisions.append({
                    step: step.id,
                    decision: result,
                    worker_id: worker.id,
                    cost: result.cost
                })
                
            elif step.type == "review":
                review_result = call_model(step.model, step.prompt_file, task_record)
                task_record.decisions.append({
                    step: step.id,
                    decision: review_result,
                    model: step.model
                })
        
        # After all steps, task is complete
        task_record.state = "completed"
        save_to_jimbo_api(task_record)
```

### **4. Human Feedback Integration**

When a task is `assigned_to: marvin` and `state: awaiting_human`:

**Telegram (async notification):**
- Jimbo posts a summary: task name, what decision was needed, what Jimbo suggested
- User sees it when they open Telegram
- User can respond at their own pace (immediately, or later)

**Site UI (dashboard):**
- Task appears at `/app/jimbo/workflows/<workflow>/tasks`
- Shows decision history, reasoning, what input is needed
- User can approve, override, or provide additional context

**Update flow:**
- Human responds (Telegram or UI)
- Response updates `task_record.human_input`
- Workflow resumes from where it paused
- Continues to next step or completes

---

## Initial Implementation: Vault Task Triage

The first workflow to implement using this system.

**Proof of concept demonstrates:**
- Workflow YAML loading and parsing
- Task intake from vault API
- Sequential step execution with model calls
- Decision points with human pause
- Task record creation and logging in jimbo-api
- Telegram notifications
- A/B testing capability (config_hash enables trying different classify/review models)

---

## Iteration & Improvement

Once this system is in place, you can:

1. **Manage workflows via Git** — change YAML, commit, deploy
2. **Monitor via jimbo-api dashboard** — see success rates, human override frequency, costs per model
3. **Experiment** — run vault-triage with Haiku for 3 days, then Sonnet, compare results
4. **Add workflows** — email triage, briefing assembly, recommendations follow the same pattern
5. **Refine prompts** — `prompts/` directory is source-controlled, iterate without code changes

---

## Constraints & Trade-offs

**Sequential execution:** Easier to reason about, but slower than concurrent delegation. Trade-off: clarity + debuggability over throughput.

**Human decision blocking:** When Jimbo needs input, the workflow pauses. Async Telegram notification means you'll see it eventually, but won't block Jimbo waiting for response.

**YAML simplicity:** Can't express every possible workflow pattern. If a workflow becomes complex, migrate it to Python class later (but start with YAML).

---

## Success Criteria

You know this is working when:

- ✅ Vault triage workflow runs on schedule (9am, 3pm, 6pm)
- ✅ Tasks move through classify → route → delegate → review → decide
- ✅ When Jimbo needs your input, you get a Telegram notification
- ✅ You can respond asynchronously and the workflow continues
- ✅ Every decision is logged and visible in jimbo-api dashboard
- ✅ You can tweak the YAML and see different outcomes (e.g., swap Haiku for Sonnet)
- ✅ Activity log shows clear story of what happened and why

---

## Next Step

Implementation plan follows in `2026-04-09-jimbo-workflow-orchestration-plan.md`.
