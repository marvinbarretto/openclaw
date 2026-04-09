"""Reusable orchestration helpers for Jimbo's canonical control loop."""

from dataclasses import dataclass, field

import orchestration_helper


CANONICAL_LOOP = (
    "intake",
    "classify",
    "route",
    "delegate",
    "review",
    "report",
)


@dataclass
class JimboTask:
    """Minimal task context for orchestration logging."""

    task_id: str
    title: str | None = None
    task_source: str = "vault"
    workflow: str | None = None
    model: str | None = None
    metadata: dict = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, mapping, **overrides):
        payload = dict(mapping or {})
        metadata = dict(overrides.pop("metadata", {}) or {})
        return cls(
            task_id=overrides.pop("task_id", payload.get("task_id", "")),
            title=overrides.pop("title", payload.get("title")),
            task_source=overrides.pop("task_source", payload.get("task_source", "vault")),
            workflow=overrides.pop("workflow", payload.get("workflow")),
            model=overrides.pop("model", payload.get("model")),
            metadata={**payload.get("metadata", {}), **metadata},
            **overrides,
        )


class JimboCore:
    """Canonical stage logger for orchestration workflows."""

    def __init__(self, task, *, logger=None):
        self.task = task
        self.logger = logger or orchestration_helper.log_decision

    def _build_metadata(self, metadata=None, *, intake=None):
        merged = dict(self.task.metadata or {})
        if metadata:
            merged.update(metadata)
        if self.task.workflow and "workflow" not in merged:
            merged["workflow"] = self.task.workflow
        merged.setdefault("canonical_loop", list(CANONICAL_LOOP))
        if intake is not None:
            merged["intake"] = intake
        return merged or None

    def _log(self, stage, **kwargs):
        return self.logger(
            stage,
            self.task.task_id,
            title=self.task.title,
            task_source=self.task.task_source,
            model=kwargs.pop("model", None) or self.task.model,
            **kwargs,
        )

    def intake(self, *, intake=None, reason=None, changed=None, metadata=None):
        return self._log(
            "intake",
            reason=reason,
            changed=changed,
            metadata=self._build_metadata(metadata, intake=intake),
        )

    def classify(self, *, classification, reason=None, route=None, delegate=None, changed=None, metadata=None):
        return self._log(
            "classify",
            reason=reason,
            classification=classification,
            route=route,
            delegate=delegate,
            changed=changed,
            metadata=self._build_metadata(metadata),
        )

    def route(self, *, route, reason=None, delegate=None, changed=None, metadata=None):
        return self._log(
            "route",
            reason=reason,
            route=route,
            delegate=delegate,
            changed=changed,
            metadata=self._build_metadata(metadata),
        )

    def delegate(self, *, delegate, reason=None, route=None, changed=None, metadata=None):
        return self._log(
            "delegate",
            reason=reason,
            route=route,
            delegate=delegate,
            changed=changed,
            metadata=self._build_metadata(metadata),
        )

    def review(self, *, review, reason=None, changed=None, metadata=None):
        return self._log(
            "review",
            reason=reason,
            review=review,
            changed=changed,
            metadata=self._build_metadata(metadata),
        )

    def report(self, *, report, reason=None, changed=None, metadata=None):
        return self._log(
            "report",
            reason=reason,
            report=report,
            changed=changed,
            metadata=self._build_metadata(metadata),
        )
