"""Tests for shared Jimbo runtime service entrypoints."""

import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestJimboRuntimeService(unittest.TestCase):

    def test_begin_dispatch_proposal_builds_dispatch_intake(self):
        from jimbo_runtime_service import begin_dispatch_proposal

        runtime = mock.Mock()
        runtime.begin.return_value = "ok"

        result = begin_dispatch_proposal(
            {
                "id": 11,
                "task_id": "note_1",
                "title": "Fix auth bug",
                "agent_type": "coder",
                "flow": "commission",
            },
            batch_id="batch-1",
            approve_url="https://approve",
            reject_url="https://reject",
            runtime=runtime,
        )

        self.assertEqual(result, "ok")
        runtime.begin.assert_called_once()
        envelope = runtime.begin.call_args.args[0]
        self.assertEqual(envelope.source, "dispatch")
        self.assertEqual(envelope.trigger, "dispatch-propose")
        self.assertEqual(envelope.workflow_hint, "dispatch")
        self.assertEqual(envelope.metadata["batch_id"], "batch-1")
        self.assertEqual(envelope.metadata["dispatch_id"], 11)

    def test_resolve_dispatch_execution_builds_worker_intake(self):
        from jimbo_runtime_service import resolve_dispatch_execution

        runtime = mock.Mock()
        runtime.resolve_workflow.return_value = "selection"

        result = resolve_dispatch_execution(
            {"id": 11, "task_id": "note_1"},
            {
                "task_id": "note_1",
                "title": "Fix auth bug",
                "task_source": "vault",
                "flow": "commission",
            },
            "/tmp",
            model="claude-sonnet-4-6",
            runtime=runtime,
        )

        self.assertEqual(result, "selection")
        runtime.resolve_workflow.assert_called_once()
        envelope = runtime.resolve_workflow.call_args.args[0]
        self.assertEqual(envelope.source, "dispatch")
        self.assertEqual(envelope.trigger, "dispatch-next")
        self.assertEqual(envelope.model, "claude-sonnet-4-6")
        self.assertEqual(envelope.metadata["dispatch_id"], 11)
        self.assertEqual(envelope.metadata["repo"], "/tmp")

    def test_log_dispatch_candidate_classification_uses_runtime_selection(self):
        from jimbo_runtime_service import log_dispatch_candidate_classification

        mock_core = mock.Mock()
        runtime = mock.Mock()
        runtime.resolve_workflow.return_value = SimpleNamespace(core=mock_core)

        log_dispatch_candidate_classification(
            {
                "id": "note_1",
                "title": "Fix auth bug",
            },
            priority=1,
            actionability="clear",
            reason="Aligned with active repo work",
            suggested_agent_type="coder",
            suggested_route="jimbo",
            acceptance_criteria="Green tests and PR opened.",
            changed_fields={"ai_priority", "suggested_agent_type"},
            model="gemini-test",
            runtime=runtime,
        )

        runtime.resolve_workflow.assert_called_once()
        envelope = runtime.resolve_workflow.call_args.args[0]
        self.assertEqual(envelope.source, "vault")
        self.assertEqual(envelope.trigger, "vault-task-triage")
        self.assertEqual(envelope.workflow_hint, "vault-task-triage")
        self.assertEqual(envelope.model, "gemini-test")
        mock_core.classify.assert_called_once()
        classify_kwargs = mock_core.classify.call_args.kwargs
        self.assertEqual(classify_kwargs["route"]["decision"], "jimbo")
        self.assertEqual(classify_kwargs["delegate"]["agent_type"], "coder")
        self.assertEqual(
            classify_kwargs["changed"]["fields"],
            ["ai_priority", "suggested_agent_type"],
        )


if __name__ == '__main__':
    unittest.main()
