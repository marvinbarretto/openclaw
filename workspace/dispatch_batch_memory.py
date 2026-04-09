"""Batch-level projection helpers for dispatch orchestration."""

TERMINAL_STATUSES = {
    "completed", "blocked", "failed", "rejected", "timeout",
}

QUEUE_STATUS_TO_BATCH_STATUS = {
    "proposed": "proposed",
    "approved": "approved",
    "running": "picked_up",
    "completed": "completed",
    "failed": "failed",
    "rejected": "rejected",
}


def dispatch_item_id(item):
    return str(item.get("id", item.get("dispatch_id", item.get("task_id"))))


def queue_item_batch_status(item):
    """Map a queue item to the orchestration-facing batch status."""
    queue_status = item.get("status")
    mapped_status = QUEUE_STATUS_TO_BATCH_STATUS.get(queue_status)
    if mapped_status != "failed":
        return mapped_status

    error_message = (item.get("error_message") or "").lower()
    if "timeout" in error_message:
        return "timeout"
    return mapped_status


def build_batch(batch_id, items, *, default_status=None, status_overrides=None):
    """Build a batch projection from hydrated tasks or queue items."""
    batch = {
        "batch_id": batch_id,
        "items": {},
    }
    status_overrides = status_overrides or {}

    for item in items:
        dispatch_id = dispatch_item_id(item)
        status = status_overrides.get(dispatch_id)
        if status is None:
            status = queue_item_batch_status(item) or item.get("batch_status") or default_status or item.get("status", "unknown")
        batch["items"][dispatch_id] = {
            "dispatch_id": item.get("id", item.get("dispatch_id")),
            "task_id": item.get("task_id"),
            "title": item.get("title", item.get("task_id")),
            "agent_type": item.get("agent_type"),
            "flow": item.get("flow", "commission"),
            "task_source": item.get("task_source", "vault"),
            "status": status,
        }
    return batch


def build_batches(items, *, batch_ids=None, status_overrides=None):
    """Group queue items into batch projections keyed by batch_id."""
    grouped = {}
    allowed = set(batch_ids) if batch_ids else None
    for item in items:
        batch_id = item.get("batch_id")
        if not batch_id:
            continue
        if allowed is not None and batch_id not in allowed:
            continue
        grouped.setdefault(batch_id, []).append(item)

    return {
        batch_id: build_batch(batch_id, batch_items, status_overrides=status_overrides)
        for batch_id, batch_items in grouped.items()
    }


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
