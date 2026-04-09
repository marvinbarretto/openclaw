"""Batch-level memory for dispatch orchestration."""

import json
import os


TERMINAL_STATUSES = {
    "completed", "blocked", "failed", "rejected", "timeout",
}


def load_batch_state(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_batch_state(path, state):
    with open(path, "w") as f:
        json.dump(state, f, sort_keys=True)


def initialize_batch(state, batch_id, items):
    """Create or refresh a batch entry from a set of hydrated items."""
    batch = {
        "batch_id": batch_id,
        "items": {},
    }
    for item in items:
        dispatch_id = str(item.get("id", item.get("task_id")))
        batch["items"][dispatch_id] = {
            "dispatch_id": item.get("id"),
            "task_id": item.get("task_id"),
            "title": item.get("title", item.get("task_id")),
            "agent_type": item.get("agent_type"),
            "flow": item.get("flow", "commission"),
            "task_source": item.get("task_source", "vault"),
            "status": "proposed",
        }
    next_state = dict(state)
    next_state[batch_id] = batch
    return next_state


def record_item_status(state, batch_id, item, status):
    """Update one batch item to its latest status."""
    next_state = dict(state)
    batch = dict(next_state.get(batch_id, {"batch_id": batch_id, "items": {}}))
    items = dict(batch.get("items", {}))
    dispatch_id = str(item.get("id", item.get("dispatch_id", item.get("task_id"))))

    existing = dict(items.get(dispatch_id, {}))
    existing.update({
        "dispatch_id": item.get("id", item.get("dispatch_id")),
        "task_id": item.get("task_id"),
        "title": item.get("title", item.get("task_id")),
        "agent_type": item.get("agent_type"),
        "flow": item.get("flow", "commission"),
        "task_source": item.get("task_source", "vault"),
        "status": status,
    })
    items[dispatch_id] = existing
    batch["items"] = items
    next_state[batch_id] = batch
    return next_state


def summarize_batch(batch):
    """Return a compact human summary for a batch."""
    items = list((batch or {}).get("items", {}).values())
    total = len(items)
    counts = {}
    for item in items:
        status = item.get("status", "unknown")
        counts[status] = counts.get(status, 0) + 1

    ordered_statuses = [
        "proposed", "approved", "picked_up", "completed",
        "blocked", "failed", "rejected", "timeout",
    ]
    parts = []
    for status in ordered_statuses:
        count = counts.get(status, 0)
        if count:
            parts.append(f"{count} {status}")

    summary = f"{total} tasks"
    if parts:
        summary += ": " + ", ".join(parts)
    return summary


def batch_report_status(batch):
    """Infer the current batch-level status from item statuses."""
    items = list((batch or {}).get("items", {}).values())
    statuses = {item.get("status") for item in items}
    if not items:
        return "empty"
    if statuses == {"proposed"}:
        return "proposed"
    if statuses <= {"approved", "proposed"} and "approved" in statuses:
        return "approved"
    if "picked_up" in statuses and not (statuses & TERMINAL_STATUSES):
        return "in_progress"
    if statuses <= TERMINAL_STATUSES:
        if statuses == {"completed"}:
            return "completed"
        if statuses == {"rejected"}:
            return "rejected"
        if statuses == {"blocked"}:
            return "blocked"
        if statuses == {"failed"}:
            return "failed"
        if statuses == {"timeout"}:
            return "timeout"
        return "mixed_terminal"
    return "mixed"
