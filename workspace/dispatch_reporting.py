"""Structured operator summaries for dispatch events."""


DASHBOARD_URL = "https://marvinbarretto.dev/app/jimbo/dashboard/dispatch"


def summarize_task(task, *, title=None):
    flow = task.get("flow", "commission")
    agent_type = task.get("agent_type", "worker")
    executor = task.get("executor")
    label = title or task.get("task_id", "unknown-task")
    if executor:
        return f"[{flow}] {agent_type} [{executor}] -- {label}"
    return f"[{flow}] {agent_type} -- {label}"


def _item_detail(item, *, title=None):
    """Build a detailed line for a batch item with title and link."""
    summary = summarize_task(item, title=title)
    parts = [summary]

    issue_title = item.get("issue_title")
    if issue_title:
        parts.append(f"  {issue_title[:80]}")

    issue_repo = item.get("issue_repo")
    issue_number = item.get("issue_number")
    if issue_repo and issue_number:
        parts.append(f'  <a href="https://github.com/{issue_repo}/issues/{issue_number}">#{issue_number}</a>')

    return "\n".join(parts)


def build_batch_summary(batch_id, items, *, titles=None, approve_url="", reject_url=""):
    """Build a structured Telegram summary for a proposed batch."""
    titles = titles or {}
    lines = [f"[Dispatch] Batch {batch_id} -- {len(items)} tasks ready", ""]

    for idx, item in enumerate(items, 1):
        lines.append(f"{idx}. {_item_detail(item, title=titles.get(item.get('task_id')))}")

    lines.append("")
    if approve_url:
        lines.append(f'<a href="{approve_url}">Approve all</a>')
    if reject_url:
        lines.append(f'<a href="{reject_url}">Reject</a>')
    lines.append(f'<a href="{DASHBOARD_URL}">View in dashboard</a>')

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
