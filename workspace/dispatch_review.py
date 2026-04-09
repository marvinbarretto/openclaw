"""Validation helpers for dispatch worker review."""


def validate_result(task, result):
    """Validate a dispatch result against the task's output contract.

    Returns a dict with:
      - accepted: bool
      - review_status: completed|blocked|failed|rejected
      - reason: short explanation
    """
    status = result.get("status")
    flow = task.get("flow", "commission")

    if status == "completed_unstructured":
        return {
            "accepted": False,
            "review_status": "rejected",
            "reason": "Agent returned unstructured output instead of the JSON result contract",
        }

    if status == "completed":
        missing = []
        if not result.get("summary"):
            missing.append("summary")

        if flow == "commission":
            if not result.get("pr_url"):
                missing.append("pr_url")
        elif flow == "recon":
            if not result.get("artifact_path"):
                missing.append("artifact_path")
            if not result.get("commit_sha"):
                missing.append("commit_sha")

        if missing:
            return {
                "accepted": False,
                "review_status": "rejected",
                "reason": f"Completed result missing required fields: {', '.join(missing)}",
            }

        return {
            "accepted": True,
            "review_status": "completed",
            "reason": "Result satisfied the structured output contract",
        }

    if status == "blocked":
        if not result.get("summary"):
            return {
                "accepted": False,
                "review_status": "rejected",
                "reason": "Blocked result missing summary",
            }
        return {
            "accepted": True,
            "review_status": "blocked",
            "reason": "Blocked result included structured blocker information",
        }

    if status == "failed":
        return {
            "accepted": True,
            "review_status": "failed",
            "reason": result.get("summary", "Agent reported failure"),
        }

    return {
        "accepted": False,
        "review_status": "rejected",
        "reason": f"Unknown result status: {status!r}",
    }
