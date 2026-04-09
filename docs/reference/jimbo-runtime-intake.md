# Jimbo Runtime Intake Contract

This document defines the normalized payload shape accepted by:

- `workspace/jimbo_runtime_cli.py`
- the shared helpers in `workspace/jimbo_runtime_service.py`

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
