# Jimbo Orchestration Handover Prompt

Use this as the starter prompt for a fresh LLM session continuing Jimbo orchestration work in this repository.

---

You are continuing orchestration work in the `openclaw` repo at:

- `/Users/marvinbarretto/development/openclaw`

The user is Marvin. The system under construction is **Jimbo**, a self-hosted orchestration layer. Jimbo is not a worker. Jimbo is the control plane.

## Core vision

Jimbo should:

- receive input
- understand intent
- decide what should happen
- delegate execution
- review outcomes
- record decisions
- report back

Canonical loop:

- `intake -> classify -> route -> delegate -> review -> log -> report`

Jimbo should be:

- API-first
- source controlled everywhere
- cautious about production quality
- explicit and traceable in every decision

The short-term target workflow is:

- **Vault Task Triage with Delegation**

That means:

- select a batch of tasks
- classify each task
- delegate when appropriate
- log each decision
- return a useful summary

## Current repo state

Assume current branch is `master`.

Recent orchestration commits, newest first:

- `184076f` `feat: add jimbo orchestration core`
- `e472b37` `feat: harden dispatch worker api writes`
- `7f1ee26` `feat: harden orchestration api writes`
- `282070b` `feat: verify dispatch completion evidence`
- `3b0fadb` `refactor: store dispatch transitions in settings api`
- `1a0bb2e` `refactor: rebuild batch narratives from queue state`
- `15cd137` merge of PR `#26`
- `df4e83f` merge of PR `#25`
- `e7822a4` merge of PR `#24`

At last verification, this targeted suite passed:

```bash
python3 -m unittest \
  workspace.tests.test_dispatch \
  workspace.tests.test_dispatch_worker \
  workspace.tests.test_dispatch_review \
  workspace.tests.test_dispatch_reporting \
  workspace.tests.test_dispatch_intake \
  workspace.tests.test_dispatch_transitions \
  workspace.tests.test_dispatch_batch_memory \
  workspace.tests.test_jimbo_core \
  workspace.tests.test_orchestration_helper \
  workspace.tests.test_base_worker \
  workspace.tests.test_vault_connector \
  workspace.tests.test_vault_reader \
  workspace.tests.test_vault_roulette -q
```

Result at handoff:

- `Ran 81 tests ... OK`

## Important files

Control-plane and orchestration:

- [workspace/jimbo_core.py](/Users/marvinbarretto/development/openclaw/workspace/jimbo_core.py)
- [workspace/orchestration_helper.py](/Users/marvinbarretto/development/openclaw/workspace/orchestration_helper.py)

Dispatch proposer / queue monitoring:

- [workspace/dispatch.py](/Users/marvinbarretto/development/openclaw/workspace/dispatch.py)
- [workspace/dispatch_transitions.py](/Users/marvinbarretto/development/openclaw/workspace/dispatch_transitions.py)
- [workspace/dispatch_batch_memory.py](/Users/marvinbarretto/development/openclaw/workspace/dispatch_batch_memory.py)
- [workspace/dispatch_reporting.py](/Users/marvinbarretto/development/openclaw/workspace/dispatch_reporting.py)
- [workspace/dispatch_intake.py](/Users/marvinbarretto/development/openclaw/workspace/dispatch_intake.py)

Dispatch worker / execution / verification:

- [workspace/dispatch-worker.py](/Users/marvinbarretto/development/openclaw/workspace/dispatch-worker.py)
- [workspace/dispatch_review.py](/Users/marvinbarretto/development/openclaw/workspace/dispatch_review.py)
- [workspace/dispatch_utils.py](/Users/marvinbarretto/development/openclaw/workspace/dispatch_utils.py)

Task classification:

- [workspace/prioritise-tasks.py](/Users/marvinbarretto/development/openclaw/workspace/prioritise-tasks.py)

Docs and architecture:

- [ARCHITECTURE.md](/Users/marvinbarretto/development/openclaw/ARCHITECTURE.md)
- [README.md](/Users/marvinbarretto/development/openclaw/README.md)
- [decisions/046-openclaw-is-jimbo-not-airflow.md](/Users/marvinbarretto/development/openclaw/decisions/046-openclaw-is-jimbo-not-airflow.md)

Focused tests:

- [workspace/tests/test_dispatch.py](/Users/marvinbarretto/development/openclaw/workspace/tests/test_dispatch.py)
- [workspace/tests/test_dispatch_worker.py](/Users/marvinbarretto/development/openclaw/workspace/tests/test_dispatch_worker.py)
- [workspace/tests/test_dispatch_review.py](/Users/marvinbarretto/development/openclaw/workspace/tests/test_dispatch_review.py)
- [workspace/tests/test_dispatch_intake.py](/Users/marvinbarretto/development/openclaw/workspace/tests/test_dispatch_intake.py)
- [workspace/tests/test_dispatch_reporting.py](/Users/marvinbarretto/development/openclaw/workspace/tests/test_dispatch_reporting.py)
- [workspace/tests/test_dispatch_transitions.py](/Users/marvinbarretto/development/openclaw/workspace/tests/test_dispatch_transitions.py)
- [workspace/tests/test_dispatch_batch_memory.py](/Users/marvinbarretto/development/openclaw/workspace/tests/test_dispatch_batch_memory.py)
- [workspace/tests/test_jimbo_core.py](/Users/marvinbarretto/development/openclaw/workspace/tests/test_jimbo_core.py)
- [workspace/tests/test_orchestration_helper.py](/Users/marvinbarretto/development/openclaw/workspace/tests/test_orchestration_helper.py)

## What is already done

The dispatch path has been materially hardened.

Implemented:

- API-backed orchestration decision logging
- normalized dispatch intake
- stricter structured review gate
- standardized operator summaries
- queue transition logging
- batch narrative reporting derived from API queue state
- API-backed transition dedupe state via settings store
- retry logic for orchestration activity writes
- retry logic for worker-side required dispatch writes
- evidence-preserving behavior when required worker terminal writes fail
- first reusable orchestration wrapper via `JimboCore`
- intake is now a first-class logged stage in the dispatch path

Current dispatch-stage coverage:

- `intake`: now explicit in proposer and worker through `JimboCore`
- `classify`: vault task classification path in `prioritise-tasks.py`
- `route`: proposer path in `dispatch.py`
- `delegate`: worker path in `dispatch-worker.py`
- `review`: worker verification in `dispatch_review.py`
- `report`: proposer and worker reporting paths

## Current design boundaries

The system deliberately follows ADR-046:

- Python/scripts own mechanical scheduled work
- OpenClaw is not Airflow
- Jimbo should be the conversational and orchestration shell, not a cron tax
- `jimbo-api` is the shared state backbone

Do not regress into:

- many separate heavyweight OpenClaw cron jobs
- local-only state that becomes the source of truth
- silent best-effort writes for critical orchestration state
- ad hoc stage names outside the canonical loop without a good reason

## Remaining gaps

The initial target workflow is in decent shape, but the broader Jimbo vision is still incomplete.

Most important remaining gaps:

1. There is still no single always-on Jimbo runtime/service.
   The repo has shared helpers and hardened scripts, but not one orchestration process that owns normalized intake end to end.

2. Routing is still dispatch-centric.
   There is no general worker/model/capability registry that can choose between admin, research, coding, writing, scheduling, or human-required work.

3. Intake is not unified across sources.
   Current strongest intake is dispatch/vault. Jimbo still needs a common intake layer for chat, cron, Ralph, and API triggers.

4. Ralph is still conceptual.
   There is not yet a distinct background-agent runtime with clear “suggest, queue, prepare, but do not decide” behavior.

5. Reflection is not first-class.
   Logs are much better, but the “logs -> summaries -> reflection -> blog drafts” pipeline is not yet a core orchestration product.

6. Permission and risk policy are not centralized.
   Dangerous action gating still lives in scattered code/prompt behavior rather than one orchestration policy layer.

7. The canonical loop exists as a wrapper, not yet as a runtime.
   `JimboCore` currently standardizes stage logging, but it does not yet execute or enforce a generic orchestration lifecycle for arbitrary workflows.

## Recommended next step

Build the first real **Jimbo runtime** module/process.

That runtime should:

- accept normalized intake objects from multiple sources
- identify workflow type
- run the canonical loop through one orchestration path
- use the new `JimboCore` wrapper for stages
- centralize workflow selection and routing
- preserve API-first state semantics

Good concrete next slice:

- create a `workspace/jimbo_runtime.py` or similarly named module
- define normalized intake envelopes
- define a workflow registry
- register the current dispatch/vault-triage workflow as workflow one
- move dispatch-specific “mini-controller” logic toward that runtime without breaking the existing scripts

## Working style expected by the user

- prefer small, production-grade increments
- keep everything source controlled
- push regularly to GitHub
- avoid hand-wavy “it should be fine” changes
- run the targeted test suite regularly
- use the API wherever possible
- do not cut corners

## Suggested starter instruction for the next model

Start by reading:

1. `docs/reference/jimbo-orchestration-handover.md`
2. `workspace/jimbo_core.py`
3. `workspace/dispatch.py`
4. `workspace/dispatch-worker.py`
5. `workspace/prioritise-tasks.py`
6. `workspace/dispatch_review.py`
7. `ARCHITECTURE.md`
8. `decisions/046-openclaw-is-jimbo-not-airflow.md`

Then continue with the next high-value step:

- implement a first real `Jimbo runtime` module that makes the canonical orchestration loop executable and reusable, starting with the existing dispatch/vault-triage flow

Do not start by widening feature scope. Consolidate control-plane behavior first.

