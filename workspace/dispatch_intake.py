"""Normalize dispatch tasks into a consistent intake shape."""


def hydrate_task(task, fetch_vault_note):
    """Return a normalized dispatch task payload.

    fetch_vault_note should be a callable taking task_id and returning a note
    dict or None. For non-vault tasks it will not be called.
    """
    normalized = dict(task)
    normalized["task_source"] = task.get("task_source", "vault")
    normalized["flow"] = task.get("flow", "commission")

    if normalized["task_source"] == "github":
        normalized["title"] = task.get("title") or task.get("task_id")
        normalized["definition_of_done"] = task.get("definition_of_done", "")
        normalized["vault_task"] = None
        return normalized

    vault_task = fetch_vault_note(task["task_id"])
    if not vault_task:
        return None

    normalized["vault_task"] = vault_task
    normalized["title"] = vault_task.get("title", task["task_id"])
    normalized["definition_of_done"] = vault_task.get("definition_of_done", "")
    return normalized


def hydrate_batch(items, fetch_vault_note):
    """Hydrate a list of dispatch items, skipping vault items that cannot load."""
    hydrated = []
    for item in items:
        normalized = hydrate_task(item, fetch_vault_note)
        if normalized:
            hydrated.append(normalized)
    return hydrated
