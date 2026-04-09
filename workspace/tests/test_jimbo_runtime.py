"""Tests for the Jimbo runtime workflow registry."""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestJimboRuntime(unittest.TestCase):

    def test_resolves_dispatch_workflow_from_registry_alias(self):
        from jimbo_runtime import JimboIntakeEnvelope, JimboRuntime

        runtime = JimboRuntime(logger=mock.Mock())
        selection = runtime.resolve_workflow(
            JimboIntakeEnvelope.from_mapping(
                {
                    "task_id": "note_1",
                    "title": "Fix auth bug",
                    "workflow": "vault-task-triage",
                },
                intake_id="dispatch-1",
                source="vault",
                trigger="manual-triage",
            )
        )

        self.assertEqual(selection.workflow.name, "dispatch")
        self.assertEqual(selection.task.workflow, "dispatch")
        self.assertEqual(selection.task.task_id, "note_1")

    def test_begin_logs_intake_and_route_with_workflow_metadata(self):
        from jimbo_runtime import JimboIntakeEnvelope, JimboRuntime

        logger = mock.Mock(side_effect=["act_1", "act_2"])
        runtime = JimboRuntime(logger=logger)

        result = runtime.begin(
            JimboIntakeEnvelope.from_mapping(
                {
                    "task_id": "note_1",
                    "title": "Fix auth bug",
                    "agent_type": "coder",
                    "flow": "commission",
                },
                intake_id="dispatch-1",
                source="dispatch",
                trigger="dispatch-propose",
                metadata={"batch_id": "batch-1"},
            ),
            intake_reason="Task selected from ready queue",
            route={"decision": "proposed"},
            route_reason="Workflow selected by runtime",
            delegate={"agent_type": "coder"},
        )

        self.assertEqual(result.intake_activity_id, "act_1")
        self.assertEqual(result.route_activity_id, "act_2")
        self.assertEqual(logger.call_count, 2)

        intake_call = logger.call_args_list[0]
        route_call = logger.call_args_list[1]

        self.assertEqual(intake_call.args[0], "intake")
        self.assertEqual(route_call.args[0], "route")
        self.assertEqual(route_call.kwargs["route"]["workflow"], "dispatch")
        self.assertEqual(route_call.kwargs["metadata"]["workflow_description"],
                         "Vault task triage and dispatch delegation workflow")
        self.assertEqual(intake_call.kwargs["metadata"]["workflow_aliases"], ["vault-task-triage"])


if __name__ == '__main__':
    unittest.main()
