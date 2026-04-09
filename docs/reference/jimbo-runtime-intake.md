# Jimbo Runtime Intake Contract

This document defines the normalized payload shape accepted by:

- `workspace/jimbo_runtime_cli.py`
- the shared helpers in `workspace/jimbo_runtime_service.py`
- `python3 workspace/dispatch.py --emit-intake`
- `python3 workspace/dispatch-worker.py --emit-intake`

The goal is simple: one explicit intake object shape for runtime-owned orchestration.

## Required fields

Every intake payload must include:

- `source`: string
- `trigger`: string
- one of `task_id` or `intake_id`

## Optional envelope fields

- `intake_id`: string
- `task_id`: string
- `title`: string
- `task_source`: string
- `workflow_hint`: string
- `workflow`: string
- `model`: string
- `metadata`: object

`workflow` is accepted as an alias and is normalized to `workflow_hint`.

## Live execution fields

When the runtime is invoked in live mode, the payload must also include:

- `route`: object

Optional live-only fields:

- `intake_reason`: string
- `route_reason`: string
- `delegate`: object
- `changed`: object
- `runtime_metadata`: object

## Dry-run example

```json
{
  "intake_id": "dispatch-11",
  "task_id": "note_1",
  "title": "Fix auth bug",
  "source": "dispatch",
  "trigger": "dispatch-propose",
  "task_source": "vault",
  "workflow_hint": "dispatch",
  "metadata": {
    "batch_id": "batch-20260409-090000",
    "dispatch_id": 11
  }
}
```

## Live example

```json
{
  "intake_id": "dispatch-11",
  "task_id": "note_1",
  "title": "Fix auth bug",
  "source": "dispatch",
  "trigger": "dispatch-propose",
  "task_source": "vault",
  "workflow_hint": "dispatch",
  "metadata": {
    "batch_id": "batch-20260409-090000",
    "dispatch_id": 11
  },
  "intake_reason": "Task selected from ready queue",
  "route": {
    "decision": "proposed",
    "reason": "Selected by dispatch proposer from ready queue"
  },
  "delegate": {
    "agent_type": "coder",
    "approval": "pending"
  },
  "runtime_metadata": {
    "approve_url": "https://example.com/approve",
    "reject_url": "https://example.com/reject"
  }
}
```

## CLI usage

Dry-run resolution:

```bash
python3 workspace/jimbo_runtime_cli.py \
  --intake-file /tmp/intake.json
```

Live execution:

```bash
python3 workspace/jimbo_runtime_cli.py \
  --intake-file /tmp/intake.json \
  --live
```

## Producer example

The dispatch proposer can now emit real runtime intake payloads for the batch it
would propose:

```bash
python3 workspace/dispatch.py --emit-intake
```

That prints a JSON array of normalized intake payloads using the same contract
consumed by the runtime CLI and service helpers.

The dispatch worker can emit the next approved execution payload:

```bash
python3 workspace/dispatch-worker.py --emit-intake
```

That prints a single normalized intake payload for the next approved task the
worker would pick up.

The runtime CLI accepts either:

- a single intake payload object
- a JSON array of intake payload objects

That means the proposer output can be passed straight into the runtime CLI via
`--intake-file`.

You can also pipe directly over stdin:

```bash
python3 workspace/dispatch.py --emit-intake \
  | python3 workspace/jimbo_runtime_cli.py --intake-file -
```

## Roundtrip helper

To avoid composing the producer and runtime commands manually, use:

```bash
python3 workspace/jimbo_runtime_roundtrip.py --producer dispatch-proposal
python3 workspace/jimbo_runtime_roundtrip.py --producer dispatch-worker
```

Live runtime execution is also supported:

```bash
python3 workspace/jimbo_runtime_roundtrip.py --producer dispatch-proposal --live
```

To get a control-plane summary instead of raw resolved items:

```bash
python3 workspace/jimbo_runtime_roundtrip.py --producer dispatch-proposal --summary
```

There is also a direct summary command for one payload or a batch:

```bash
python3 workspace/jimbo_runtime_summary.py --intake-file /tmp/intake.json
python3 workspace/jimbo_runtime_summary.py --intake-file -
```

To persist a machine-readable summary artifact:

```bash
python3 workspace/jimbo_runtime_summary.py \
  --intake-file /tmp/intake.json \
  --output-file /tmp/jimbo-runtime-summary.json
```

To also write the summary into the orchestration activity trail:

```bash
python3 workspace/jimbo_runtime_summary.py \
  --intake-file /tmp/intake.json \
  --log-activity
```

You can provide an explicit activity task id when logging:

```bash
python3 workspace/jimbo_runtime_summary.py \
  --intake-file /tmp/intake.json \
  --log-activity \
  --summary-id runtime-summary-2026-04-09
```

## Operational wrapper

For a single scheduled-facing command that runs a producer, summarizes its
intake payloads, optionally writes an artifact, and optionally logs activity:

```bash
python3 workspace/jimbo_runtime_report.py --producer dispatch-proposal
python3 workspace/jimbo_runtime_report.py --producer dispatch-worker
python3 workspace/jimbo_runtime_report.py \
  --producer dispatch-proposal \
  --output-file /tmp/jimbo-runtime-summary.json \
  --log-activity \
  --summary-id runtime-summary-2026-04-09
```
