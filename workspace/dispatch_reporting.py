"""Structured operator summaries for dispatch events."""


def summarize_task(task, *, title=None):
    flow = task.get("flow", "commission")
    agent_type = task.get("agent_type", "worker")
    label = title or task.get("task_id", "unknown-task")
    return f"[{flow}] {agent_type} -- {label}"


def build_batch_summary(batch_id, items, *, titles=None, approve_url="", reject_url=""):
    """Build a structured Telegram summary for a proposed batch."""
    titles = titles or {}
    lines = [f"[Dispatch] Batch {batch_id} -- {len(items)} tasks ready", ""]

    for idx, item in enumerate(items, 1):
        lines.append(f"{idx}. {summarize_task(item, title=titles.get(item.get('task_id')))}")

    if approve_url or reject_url:
        lines.append("")
    if approve_url:
        lines.append(f'<a href="{approve_url}">Approve all</a>')
    if reject_url:
        lines.append(f'<a href="{reject_url}">Reject</a>')

    return "\n".join(lines)


def build_result_summary(task, *, title=None, report_status=None, summary=None,
                         review_reason=None, elapsed_seconds=None):
    """Build a structured operator summary for task outcomes."""
    status = report_status or "unknown"
    base = f"[Dispatch] {status.upper()} -- {summarize_task(task, title=title)}"

    extras = []
    if elapsed_seconds is not None:
        extras.append(f"{int(elapsed_seconds)}s")
    if summary:
        extras.append(summary.strip()[:240])
    if review_reason and review_reason != summary:
        extras.append(f"reason: {review_reason.strip()[:180]}")

    if not extras:
        return base
    return f"{base}\n" + "\n".join(extras)
