"""Core intake loading and execution helpers for the Jimbo runtime."""

import json
import sys

from jimbo_runtime import JimboIntakeEnvelope, get_default_runtime
from jimbo_runtime_contract import normalize_intake_payload


def load_intake_payload(*, intake_json=None, intake_file=None):
    """Load one normalized intake payload or a payload list."""
    if bool(intake_json) == bool(intake_file):
        raise ValueError("Provide exactly one of intake_json or intake_file")

    if intake_json:
        return json.loads(intake_json)

    if intake_file == "-":
        return json.load(sys.stdin)

    with open(intake_file) as f:
        return json.load(f)


def run_intake(payload, *, live=False, runtime=None):
    """Resolve or execute one normalized intake payload through the runtime."""
    runtime = runtime or get_default_runtime()
    payload = normalize_intake_payload(payload, live=live)
    envelope = JimboIntakeEnvelope.from_mapping(payload)
    selection = runtime.resolve_workflow(envelope)

    result = {
        "workflow": selection.workflow.name,
        "task_id": selection.task.task_id,
        "title": selection.task.title,
        "source": envelope.source,
        "trigger": envelope.trigger,
        "route_decision": (payload.get("route") or {}).get("decision"),
        "live": bool(live),
    }

    if not live:
        result["mode"] = "resolved"
        return result

    runtime_result = runtime.begin(
        envelope,
        intake_reason=payload.get("intake_reason") or "Runtime intake received",
        route=payload["route"],
        route_reason=payload.get("route_reason"),
        delegate=payload.get("delegate"),
        changed=payload.get("changed"),
        metadata=payload.get("runtime_metadata") or payload.get("metadata"),
    )
    result["mode"] = "executed"
    result["intake_activity_id"] = runtime_result.intake_activity_id
    result["route_activity_id"] = runtime_result.route_activity_id
    return result


def run_intake_batch(payloads, *, live=False, runtime=None):
    """Resolve or execute one or more intake payloads through the runtime."""
    runtime = runtime or get_default_runtime()
    if isinstance(payloads, list):
        return [run_intake(payload, live=live, runtime=runtime) for payload in payloads]
    return run_intake(payloads, live=live, runtime=runtime)
