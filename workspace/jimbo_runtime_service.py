"""Shared service entrypoints for live Jimbo orchestration flows."""

from jimbo_runtime import JimboIntakeEnvelope, get_default_runtime


def begin_dispatch_proposal(item, *, batch_id, approve_url="", reject_url="",
                            runtime=None):
    """Start orchestration for a task proposed onto the dispatch queue."""
    runtime = runtime or get_default_runtime()
    return runtime.begin(
        JimboIntakeEnvelope.from_mapping(
            item,
            intake_id=item.get("id") or item["task_id"],
            source="dispatch",
            trigger="dispatch-propose",
            workflow_hint="dispatch",
            metadata={
                "batch_id": batch_id,
                "dispatch_id": item.get("id"),
            },
        ),
        intake_reason="Task selected from ready queue",
        route={
            "decision": "proposed",
            "reason": "Selected by dispatch proposer from ready queue",
            "batch_id": batch_id,
            "flow": item.get("flow"),
        },
        route_reason="Selected by dispatch proposer from ready queue",
        delegate={
            "agent_type": item.get("agent_type"),
            "approval": "pending",
        },
        metadata={
            "dispatch_id": item.get("id"),
            "approve_url": approve_url,
            "reject_url": reject_url,
        },
    )


def resolve_dispatch_execution(task, normalized_task, work_dir, *, model,
                               runtime=None):
    """Resolve the workflow selection for an approved dispatch execution."""
    runtime = runtime or get_default_runtime()
    return runtime.resolve_workflow(
        JimboIntakeEnvelope.from_mapping(
            normalized_task,
            intake_id=task.get("id") or task.get("task_id"),
            source="dispatch",
            trigger="dispatch-next",
            workflow_hint="dispatch",
            model=model,
            metadata={
                "dispatch_id": task.get("id"),
                "repo": work_dir,
            },
        )
    )


def log_dispatch_candidate_classification(task, *, priority, actionability,
                                          reason, suggested_agent_type,
                                          suggested_route,
                                          acceptance_criteria,
                                          changed_fields, model,
                                          runtime=None):
    """Log vault triage output when a task is suitable for Jimbo dispatch."""
    runtime = runtime or get_default_runtime()
    selection = runtime.resolve_workflow(
        JimboIntakeEnvelope.from_mapping(
            task,
            intake_id=task.get("id") or task["id"],
            source="vault",
            trigger="vault-task-triage",
            workflow_hint="vault-task-triage",
            task_source="vault",
            model=model,
        )
    )
    return selection.core.classify(
        classification={
            "priority": priority,
            "actionability": actionability,
            "reason": reason,
        },
        route={
            "decision": suggested_route,
            "reason": "Task is suitable for delegated execution",
        },
        delegate={
            "agent_type": suggested_agent_type,
            "acceptance_criteria": acceptance_criteria,
        },
        changed={
            "fields": sorted(changed_fields),
        },
    )
