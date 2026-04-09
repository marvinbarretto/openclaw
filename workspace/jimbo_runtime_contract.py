"""Validation helpers for normalized Jimbo runtime intake payloads."""


class InvalidIntakePayloadError(ValueError):
    """Raised when a runtime intake payload is missing required structure."""


def _require_mapping(payload, field_name):
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise InvalidIntakePayloadError(f"{field_name} must be an object")
    return dict(payload)


def normalize_intake_payload(payload, *, live=False):
    """Validate and normalize one runtime intake payload."""
    normalized = _require_mapping(payload, "payload")

    source = normalized.get("source")
    if not source or not isinstance(source, str):
        raise InvalidIntakePayloadError("payload.source must be a non-empty string")

    trigger = normalized.get("trigger")
    if not trigger or not isinstance(trigger, str):
        raise InvalidIntakePayloadError("payload.trigger must be a non-empty string")

    intake_id = normalized.get("intake_id")
    task_id = normalized.get("task_id")
    if not intake_id and not task_id:
        raise InvalidIntakePayloadError("payload must include intake_id or task_id")

    if intake_id is not None and not isinstance(intake_id, str):
        raise InvalidIntakePayloadError("payload.intake_id must be a string")
    if task_id is not None and not isinstance(task_id, str):
        raise InvalidIntakePayloadError("payload.task_id must be a string")

    for key in ("title", "task_source", "workflow_hint", "workflow", "model",
                "intake_reason", "route_reason"):
        if key in normalized and normalized[key] is not None and not isinstance(normalized[key], str):
            raise InvalidIntakePayloadError(f"payload.{key} must be a string")

    normalized["metadata"] = _require_mapping(normalized.get("metadata"), "payload.metadata")
    normalized["runtime_metadata"] = _require_mapping(
        normalized.get("runtime_metadata"), "payload.runtime_metadata"
    )

    for key in ("route", "delegate", "changed"):
        if key in normalized:
            normalized[key] = _require_mapping(normalized.get(key), f"payload.{key}")

    if "workflow" in normalized and "workflow_hint" not in normalized:
        normalized["workflow_hint"] = normalized["workflow"]

    if live and not normalized.get("route"):
        raise InvalidIntakePayloadError("live payloads must include payload.route")

    return normalized


def intake_payload_example(*, live=False):
    """Return a representative runtime intake payload."""
    payload = {
        "intake_id": "dispatch-11",
        "task_id": "note_1",
        "title": "Fix auth bug",
        "source": "dispatch",
        "trigger": "dispatch-propose",
        "task_source": "vault",
        "workflow_hint": "dispatch",
        "metadata": {
            "batch_id": "batch-20260409-090000",
            "dispatch_id": 11,
        },
    }
    if live:
        payload.update({
            "intake_reason": "Task selected from ready queue",
            "route": {
                "decision": "proposed",
                "reason": "Selected by dispatch proposer from ready queue",
            },
            "delegate": {
                "agent_type": "coder",
                "approval": "pending",
            },
            "runtime_metadata": {
                "approve_url": "https://example.com/approve",
                "reject_url": "https://example.com/reject",
            },
        })
    return payload
