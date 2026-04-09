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

- `afbee61` `feat: add route-aware runtime inbox inspection`
- `24bf2a6` `feat: add runtime inbox routing policy`
- `f916a2c` `feat: add runtime inbox and run inspection commands`
- `566a45c` `feat: add runtime inbox and run ledger`
- `e371031` `feat: add runtime server session stats`
- `f84e25c` `feat: add dedicated runtime server entrypoint`
- `b27124e` `feat: add runtime request correlation ids`
- `c98d013` `refactor: extract runtime request service loop`
- `35ff65b` `refactor: extract runtime request executor`
- `7e47a5e` `feat: add streaming runtime request execution`
- `d81160b` `feat: add machine-readable runtime request surface`
- `ad8502d` `refactor: route runtime aliases through producer-aware commands`

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
  workspace.tests.test_jimbo_runtime \
  workspace.tests.test_jimbo_runtime_service \
  workspace.tests.test_jimbo_runtime_contract \
  workspace.tests.test_jimbo_runtime_executor \
  workspace.tests.test_jimbo_runtime_request_service \
  workspace.tests.test_jimbo_runtime_requests \
  workspace.tests.test_jimbo_runtime_server \
  workspace.tests.test_jimbo_runtime_queue \
  workspace.tests.test_jimbo_runtime_inbox_service \
  workspace.tests.test_jimbo_runtime_routing \
  workspace.tests.test_jimbo_runtime_tool \
  workspace.tests.test_orchestration_helper \
  workspace.tests.test_base_worker \
  workspace.tests.test_vault_connector \
  workspace.tests.test_vault_reader \
  workspace.tests.test_vault_roulette \
  workspace.tests.test_prioritise_tasks_runtime_inbox -q
```

Result at handoff:

- `Ran 172 tests ... OK`

## Important files

Control-plane and orchestration:

- [workspace/jimbo_core.py](/Users/marvinbarretto/development/openclaw/workspace/jimbo_core.py)
- [workspace/orchestration_helper.py](/Users/marvinbarretto/development/openclaw/workspace/orchestration_helper.py)
- [workspace/jimbo_runtime.py](/Users/marvinbarretto/development/openclaw/workspace/jimbo_runtime.py)
- [workspace/jimbo_runtime_service.py](/Users/marvinbarretto/development/openclaw/workspace/jimbo_runtime_service.py)
- [workspace/jimbo_runtime_contract.py](/Users/marvinbarretto/development/openclaw/workspace/jimbo_runtime_contract.py)
- [workspace/jimbo_runtime_executor.py](/Users/marvinbarretto/development/openclaw/workspace/jimbo_runtime_executor.py)
- [workspace/jimbo_runtime_request_service.py](/Users/marvinbarretto/development/openclaw/workspace/jimbo_runtime_request_service.py)
- [workspace/jimbo_runtime_server.py](/Users/marvinbarretto/development/openclaw/workspace/jimbo_runtime_server.py)
- [workspace/jimbo_runtime_queue.py](/Users/marvinbarretto/development/openclaw/workspace/jimbo_runtime_queue.py)
- [workspace/jimbo_runtime_inbox_service.py](/Users/marvinbarretto/development/openclaw/workspace/jimbo_runtime_inbox_service.py)
- [workspace/jimbo_runtime_routing.py](/Users/marvinbarretto/development/openclaw/workspace/jimbo_runtime_routing.py)
- [workspace/jimbo_runtime_tool.py](/Users/marvinbarretto/development/openclaw/workspace/jimbo_runtime_tool.py)

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
- [workspace/tests/test_jimbo_runtime.py](/Users/marvinbarretto/development/openclaw/workspace/tests/test_jimbo_runtime.py)
- [workspace/tests/test_jimbo_runtime_service.py](/Users/marvinbarretto/development/openclaw/workspace/tests/test_jimbo_runtime_service.py)
- [workspace/tests/test_jimbo_runtime_contract.py](/Users/marvinbarretto/development/openclaw/workspace/tests/test_jimbo_runtime_contract.py)
- [workspace/tests/test_jimbo_runtime_executor.py](/Users/marvinbarretto/development/openclaw/workspace/tests/test_jimbo_runtime_executor.py)
- [workspace/tests/test_jimbo_runtime_request_service.py](/Users/marvinbarretto/development/openclaw/workspace/tests/test_jimbo_runtime_request_service.py)
- [workspace/tests/test_jimbo_runtime_requests.py](/Users/marvinbarretto/development/openclaw/workspace/tests/test_jimbo_runtime_requests.py)
- [workspace/tests/test_jimbo_runtime_server.py](/Users/marvinbarretto/development/openclaw/workspace/tests/test_jimbo_runtime_server.py)
- [workspace/tests/test_jimbo_runtime_queue.py](/Users/marvinbarretto/development/openclaw/workspace/tests/test_jimbo_runtime_queue.py)
- [workspace/tests/test_jimbo_runtime_inbox_service.py](/Users/marvinbarretto/development/openclaw/workspace/tests/test_jimbo_runtime_inbox_service.py)
- [workspace/tests/test_jimbo_runtime_routing.py](/Users/marvinbarretto/development/openclaw/workspace/tests/test_jimbo_runtime_routing.py)
- [workspace/tests/test_jimbo_runtime_tool.py](/Users/marvinbarretto/development/openclaw/workspace/tests/test_jimbo_runtime_tool.py)
- [workspace/tests/test_prioritise_tasks_runtime_inbox.py](/Users/marvinbarretto/development/openclaw/workspace/tests/test_prioritise_tasks_runtime_inbox.py)
- [workspace/tests/test_orchestration_helper.py](/Users/marvinbarretto/development/openclaw/workspace/tests/test_orchestration_helper.py)

## What is already done

The dispatch path is materially hardened, and the first runtime-owned control
plane now exists.

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
- normalized runtime intake contract and examples
- shared runtime workflow registry for dispatch / vault triage
- shared top-level runtime CLI and compatibility shims
- machine-readable runtime request contract
- streamed runtime request execution with correlation IDs
- dedicated runtime server entrypoint
- runtime batch summary, artifact export, and activity logging surfaces
- shared producer registry for `dispatch-proposal`, `dispatch-worker`, and `vault-triage`
- API-backed runtime inbox and run ledger stored in settings
- server-side inbox draining with claim / execute / persist semantics
- explicit inbox routing policy (`dispatch`, `human-required`, `defer`)
- vault triage submission into the runtime inbox
- route-aware runtime inspection (`inbox` / `runs` filters by status, route, workflow, capability)

Current dispatch-stage coverage:

- `intake`: now explicit in proposer and worker through `JimboCore`
- `classify`: vault task classification path in `prioritise-tasks.py`
- `route`: proposer path in `dispatch.py`
- `delegate`: worker path in `dispatch-worker.py`
- `review`: worker verification in `dispatch_review.py`
- `report`: proposer and worker reporting paths

Current runtime-owned surfaces:

- `request`: single machine-readable runtime request
- `serve`: newline-delimited streamed request processing
- `server`: dedicated process entrypoint over the streamed request service
- `inbox`: API-backed queue of pending runtime work
- `runs`: API-backed run ledger for claimed/executed inbox work
- `routing`: explicit route policy before execution rather than blind `resolve`

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

1. Routing is still dispatch-centric.
   The inbox can now distinguish `dispatch`, `human-required`, and `defer`,
   but there is still no broader capability/workflow registry choosing between
   admin, research, coding, writing, scheduling, or richer human-review flows.

2. Intake is not unified across sources.
   Current strongest intake is still dispatch/vault. Jimbo still needs a common
   submission layer for chat, cron, Ralph, and API triggers.

3. The inbox/run ledger is implemented on top of the settings API.
   That was the right expedient move, but it is not a permanent queueing model.
   There is no true atomic claim, no indexed query surface, no TTL/lease model,
   and no server-side concurrency guarantees.

4. There is still no durable lifecycle policy for stuck claims.
   Claimed inbox items and running runs do not yet have expiry, requeue, retry,
   or operator repair tooling.

5. Ralph is still conceptual.
   There is not yet a distinct background-agent runtime with clear “suggest, queue, prepare, but do not decide” behavior.

6. Reflection is not first-class.
   Logs are much better, but the “logs -> summaries -> reflection -> blog drafts” pipeline is not yet a core orchestration product.

7. Permission and risk policy are not centralized.
   Dangerous action gating still lives in scattered code/prompt behavior rather than one orchestration policy layer.

8. The canonical loop is only partially runtime-owned.
   `JimboCore` standardizes stage logging and the inbox can own `request -> run`,
   but there is not yet a generic stageful runtime-run record that moves through
   `intake -> classify -> route -> delegate -> review -> log -> report` as
   first-class persisted state.

## Recommended next step

Build the next real **runtime routing layer** on top of the inbox/run ledger.

That layer should:

- promote routing from `dispatch`-shaped policy to a true workflow/capability registry
- define what happens for each route beyond `dispatch` vs `human-required`
- keep inbox submission explicit about workflow, route, capability, and required review
- preserve API-first shared-state semantics
- avoid introducing local-only queue state or daemon-only truth

Good concrete next slice:

1. Add a registry that maps inbox route/workflow/capability to an owned execution path.
2. Make `dispatch` one registry entry, not the implicit default.
3. Add at least one non-dispatch route with explicit persisted behavior:
   for example `human-review`, `manual-scheduling`, or `research-brief`.
4. Persist richer run metadata so operators can see why a route was chosen and what state it is in.
5. Start designing the migration path off settings-backed queue state toward real API tables/endpoints.

## Risks and watchouts

Things most likely to bite next:

1. Settings-store queue contention.
   The inbox and runs currently live in `/api/settings`. That is workable for one
   runtime process and careful tests, but it is not safe to treat as a high-write,
   concurrent queue forever.

2. Hidden double-claim or lost-update bugs.
   There is no true compare-and-swap claim. Two workers or retries could race if
   we are not disciplined about only one active drain loop.

3. Route-policy drift.
   It is now possible to encode route/workflow/capability explicitly. If that
   logic gets copied into producers ad hoc, the control plane will fragment again.
   Keep routing policy centralized.

4. Mixing operator tooling with source-of-truth behavior.
   The CLI/server/tooling surfaces are useful, but they are not the product.
   The product is shared orchestration state and its lifecycle.

5. Silent pile-up of `human-required` and `defer` work.
   We can now queue these routes, but without expiry, reminders, escalation, or
   dashboards they may become a graveyard.

6. Overfitting to vault triage.
   The current inbox is heavily informed by vault/disptach flows. Keep the next
   route registry generic enough for chat/API/cron sources.

7. Review/report stages are still not runtime-owned for all paths.
   We should not confuse “request executed and logged” with the full canonical loop
   being persisted as one runtime-run lifecycle.

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

- treat the runtime inbox/run ledger as the new foundation and build the next routing layer on top of it, starting by turning `dispatch` into one explicit registry entry instead of the implicit execution default

Do not start by widening feature scope. Consolidate control-plane behavior first.
