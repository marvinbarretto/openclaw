"""Routing policy for Jimbo runtime inbox items."""


def build_route_policy(payload, *, producer=None):
    """Infer a runtime inbox route policy from a normalized intake payload."""
    payload = dict(payload or {})
    route = dict(payload.get("route") or {})
    delegate = dict(payload.get("delegate") or {})
    decision = route.get("decision")
    workflow = payload.get("workflow_hint") or payload.get("workflow") or "dispatch"
    capability = delegate.get("agent_type")
    reason = payload.get("route_reason") or route.get("reason")

    if decision == "marvin":
        route_name = "human-required"
        execution = "record"
        status = "waiting-human"
    elif decision in {"defer", "deferred", "skip"}:
        route_name = "defer"
        execution = "record"
        status = "deferred"
    else:
        route_name = "dispatch"
        execution = "execute"
        status = "queued"

    return {
        "route": route_name,
        "execution": execution,
        "status": status,
        "workflow": workflow,
        "capability": capability,
        "decision": decision,
        "reason": reason,
        "producer": producer,
    }


def build_route_response(item, *, status=None):
    """Build a structured non-executing response for runtime-routed inbox items."""
    route_policy = dict(item.get("route_policy") or {})
    return {
        "request_id": item.get("request_id"),
        "command": item.get("request", {}).get("command"),
        "route": route_policy.get("route"),
        "workflow": route_policy.get("workflow"),
        "capability": route_policy.get("capability"),
        "decision": route_policy.get("decision"),
        "status": status or route_policy.get("status"),
        "reason": route_policy.get("reason"),
        "result": {
            "route": route_policy.get("route"),
            "status": status or route_policy.get("status"),
            "workflow": route_policy.get("workflow"),
            "capability": route_policy.get("capability"),
            "decision": route_policy.get("decision"),
            "reason": route_policy.get("reason"),
        },
    }
