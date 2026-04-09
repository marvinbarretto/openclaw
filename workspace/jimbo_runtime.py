"""Jimbo runtime primitives for normalized intake and workflow selection."""

from dataclasses import dataclass, field

from jimbo_core import JimboCore, JimboTask


class UnknownWorkflowError(ValueError):
    """Raised when the runtime cannot match an intake envelope to a workflow."""


@dataclass(frozen=True)
class JimboIntakeEnvelope:
    """Normalized intake envelope passed into the Jimbo runtime."""

    intake_id: str
    source: str
    trigger: str
    task_id: str | None = None
    title: str | None = None
    task_source: str = "vault"
    workflow_hint: str | None = None
    model: str | None = None
    metadata: dict = field(default_factory=dict)
    payload: dict = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, mapping, **overrides):
        payload = dict(mapping or {})
        metadata = dict(payload.get("metadata", {}) or {})
        metadata.update(dict(overrides.pop("metadata", {}) or {}))

        task_id = overrides.pop("task_id", payload.get("task_id"))
        source = overrides.pop("source", payload.get("source") or "unknown")
        trigger = overrides.pop("trigger", payload.get("trigger") or "manual")
        intake_id = overrides.pop("intake_id", payload.get("intake_id") or task_id or "")
        title = overrides.pop("title", payload.get("title"))
        task_source = overrides.pop("task_source", payload.get("task_source", "vault"))
        workflow_hint = overrides.pop("workflow_hint", payload.get("workflow") or payload.get("workflow_hint"))
        model = overrides.pop("model", payload.get("model"))

        return cls(
            intake_id=intake_id,
            source=source,
            trigger=trigger,
            task_id=task_id,
            title=title,
            task_source=task_source,
            workflow_hint=workflow_hint,
            model=model,
            metadata=metadata,
            payload=payload,
            **overrides,
        )

    def to_task(self, *, workflow=None):
        return JimboTask(
            task_id=self.task_id or self.intake_id,
            title=self.title,
            task_source=self.task_source,
            workflow=workflow,
            model=self.model,
            metadata=self.metadata,
        )

    def intake_record(self):
        return {
            "source": self.source,
            "trigger": self.trigger,
            "intake_id": self.intake_id,
            "workflow_hint": self.workflow_hint,
        }


@dataclass(frozen=True)
class JimboWorkflow:
    """Registry entry describing one runtime-owned workflow."""

    name: str
    matcher: object
    description: str | None = None
    aliases: tuple[str, ...] = ()

    def matches(self, envelope):
        hints = {self.name, *self.aliases}
        if envelope.workflow_hint and envelope.workflow_hint in hints:
            return True
        return bool(self.matcher(envelope))


@dataclass(frozen=True)
class JimboWorkflowSelection:
    """Resolved workflow for a normalized intake."""

    workflow: JimboWorkflow
    envelope: JimboIntakeEnvelope
    task: JimboTask
    core: JimboCore


@dataclass(frozen=True)
class JimboRuntimeResult:
    """Result of beginning a runtime-owned orchestration path."""

    selection: JimboWorkflowSelection
    intake_activity_id: str | None
    route_activity_id: str | None


def _matches_dispatch_vault_triage(envelope):
    if envelope.source == "dispatch":
        return True
    if envelope.trigger.startswith("dispatch-"):
        return True
    payload = envelope.payload or {}
    return bool(payload.get("agent_type") and payload.get("flow"))


DEFAULT_WORKFLOWS = (
    JimboWorkflow(
        name="dispatch",
        aliases=("vault-task-triage",),
        description="Vault task triage and dispatch delegation workflow",
        matcher=_matches_dispatch_vault_triage,
    ),
)


class JimboRuntime:
    """Small runtime that normalizes intake and selects an owned workflow."""

    def __init__(self, *, workflows=None, logger=None):
        self.workflows = list(workflows or DEFAULT_WORKFLOWS)
        self.logger = logger

    def register_workflow(self, workflow):
        self.workflows.append(workflow)

    def resolve_workflow(self, envelope):
        for workflow in self.workflows:
            if workflow.matches(envelope):
                task = envelope.to_task(workflow=workflow.name)
                return JimboWorkflowSelection(
                    workflow=workflow,
                    envelope=envelope,
                    task=task,
                    core=JimboCore(task, logger=self.logger),
                )
        raise UnknownWorkflowError(
            f"No Jimbo workflow matched intake {envelope.intake_id or '<unknown>'}"
        )

    def begin(self, envelope, *, intake_reason, route, route_reason=None,
              delegate=None, changed=None, metadata=None):
        selection = self.resolve_workflow(envelope)

        route_payload = dict(route or {})
        route_payload.setdefault("workflow", selection.workflow.name)

        merged_metadata = dict(metadata or {})
        merged_metadata.setdefault("workflow_description", selection.workflow.description)
        merged_metadata.setdefault("workflow_aliases", list(selection.workflow.aliases))

        intake_activity_id = selection.core.intake(
            reason=intake_reason,
            intake=envelope.intake_record(),
            changed=changed,
            metadata=merged_metadata,
        )
        route_activity_id = selection.core.route(
            route=route_payload,
            reason=route_reason or intake_reason,
            delegate=delegate,
            changed=changed,
            metadata=merged_metadata,
        )

        return JimboRuntimeResult(
            selection=selection,
            intake_activity_id=intake_activity_id,
            route_activity_id=route_activity_id,
        )


def create_default_runtime(*, logger=None):
    """Build the canonical Jimbo runtime used by live orchestration scripts."""
    return JimboRuntime(workflows=DEFAULT_WORKFLOWS, logger=logger)


_DEFAULT_RUNTIME = create_default_runtime()


def get_default_runtime():
    """Return the shared Jimbo runtime configuration for this process."""
    return _DEFAULT_RUNTIME
