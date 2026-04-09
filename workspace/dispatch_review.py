"""Validation helpers for dispatch worker review."""

import os
import re
import subprocess


PR_URL_PATTERN = re.compile(r"^https://github\.com/[^/]+/[^/]+/pull/\d+/?$")
COMMIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{7,40}$")


def _reject(reason):
    return {
        "accepted": False,
        "review_status": "rejected",
        "reason": reason,
    }


def _accept(status, reason):
    return {
        "accepted": True,
        "review_status": status,
        "reason": reason,
    }


def _verify_commission_result(task, result):
    missing = []
    if not result.get("pr_url"):
        missing.append("pr_url")
    if not result.get("branch"):
        missing.append("branch")
    files_changed = result.get("files_changed")
    if not files_changed:
        missing.append("files_changed")
    elif not isinstance(files_changed, list):
        return _reject("Completed commission result must provide files_changed as a list")

    if missing:
        return _reject(f"Completed result missing required fields: {', '.join(missing)}")

    if not PR_URL_PATTERN.match(result["pr_url"]):
        return _reject("Completed commission result must provide a GitHub PR URL")

    expected_branch = f'dispatch/{task.get("task_id", "")}'
    if result["branch"] != expected_branch:
        return _reject(f"Completed commission result must use branch {expected_branch}")

    if not any(isinstance(path, str) and path.strip() for path in files_changed):
        return _reject("Completed commission result must include at least one changed file path")

    return _accept("completed", "Commission result satisfied the structured output contract and verification checks")


def _verify_recon_result(result, work_dir):
    missing = []
    if not result.get("artifact_path"):
        missing.append("artifact_path")
    if not result.get("commit_sha"):
        missing.append("commit_sha")
    if not result.get("repo"):
        missing.append("repo")

    if missing:
        return _reject(f"Completed result missing required fields: {', '.join(missing)}")

    artifact_path = result["artifact_path"]
    if os.path.isabs(artifact_path):
        return _reject("Recon artifact_path must be relative to the working repository")

    if not COMMIT_SHA_PATTERN.match(result["commit_sha"]):
        return _reject("Recon commit_sha must be a 7-40 character lowercase hex git SHA")

    if work_dir:
        resolved_path = os.path.normpath(os.path.join(work_dir, artifact_path))
        root_path = os.path.abspath(work_dir)
        if not resolved_path.startswith(root_path + os.sep) and resolved_path != root_path:
            return _reject("Recon artifact_path must stay within the working repository")
        if not os.path.exists(resolved_path):
            return _reject(f"Recon artifact_path does not exist: {artifact_path}")

        git_dir = os.path.join(work_dir, ".git")
        if os.path.isdir(git_dir):
            proc = subprocess.run(
                ["git", "-C", work_dir, "rev-parse", "--verify", f'{result["commit_sha"]}^{{commit}}'],
                capture_output=True,
                text=True,
            )
            if proc.returncode != 0:
                return _reject(f'Recon commit_sha not found in repository: {result["commit_sha"]}')

    return _accept("completed", "Recon result satisfied the structured output contract and verification checks")


def validate_result(task, result, *, work_dir=None):
    """Validate a dispatch result against the task's output contract.

    Returns a dict with:
      - accepted: bool
      - review_status: completed|blocked|failed|rejected
      - reason: short explanation
    """
    status = result.get("status")
    flow = task.get("flow", "commission")

    if status == "completed_unstructured":
        return _reject("Agent returned unstructured output instead of the JSON result contract")

    if status == "completed":
        if not result.get("summary"):
            return _reject("Completed result missing required fields: summary")

        if flow == "commission":
            return _verify_commission_result(task, result)
        if flow == "recon":
            return _verify_recon_result(result, work_dir)

        return _accept("completed", "Result satisfied the structured output contract")

    if status == "blocked":
        if not result.get("summary"):
            return _reject("Blocked result missing summary")
        if not result.get("blockers"):
            return _reject("Blocked result missing blockers")
        return _accept("blocked", "Blocked result included structured blocker information")

    if status == "failed":
        return _accept("failed", result.get("summary", "Agent reported failure"))

    return _reject(f"Unknown result status: {status!r}")
