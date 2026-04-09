"""Tests for the Jimbo runtime CLI entrypoint."""

import importlib.util
import json
import io
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock


WORKSPACE_DIR = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, WORKSPACE_DIR)


def load_runtime_cli():
    module_path = os.path.join(WORKSPACE_DIR, 'jimbo_runtime_cli.py')
    spec = importlib.util.spec_from_file_location('jimbo_runtime_cli_module', module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestJimboRuntimeCli(unittest.TestCase):

    def test_load_intake_payload_from_file(self):
        runtime_cli = load_runtime_cli()
        payload = {"task_id": "note_1", "source": "dispatch", "trigger": "dispatch-propose"}

        with tempfile.NamedTemporaryFile("w+", delete=False) as tmp:
            json.dump(payload, tmp)
            tmp_path = tmp.name

        try:
            loaded = runtime_cli.load_intake_payload(intake_file=tmp_path)
        finally:
            os.unlink(tmp_path)

        self.assertEqual(loaded, payload)

    def test_load_intake_payload_from_stdin(self):
        runtime_cli = load_runtime_cli()
        payload = {"task_id": "note_1", "source": "dispatch", "trigger": "dispatch-propose"}

        with mock.patch.object(runtime_cli.sys, "stdin", io.StringIO(json.dumps(payload))):
            loaded = runtime_cli.load_intake_payload(intake_file="-")

        self.assertEqual(loaded, payload)

    def test_run_intake_resolves_workflow_in_dry_run(self):
        runtime_cli = load_runtime_cli()
        runtime = mock.Mock()
        runtime.resolve_workflow.return_value = SimpleNamespace(
            workflow=SimpleNamespace(name="dispatch"),
            task=SimpleNamespace(task_id="note_1", title="Fix auth bug"),
        )

        result = runtime_cli.run_intake(
            {
                "task_id": "note_1",
                "title": "Fix auth bug",
                "source": "dispatch",
                "trigger": "dispatch-propose",
                "flow": "commission",
                "agent_type": "coder",
            },
            runtime=runtime,
        )

        self.assertEqual(result["mode"], "resolved")
        self.assertEqual(result["workflow"], "dispatch")
        self.assertEqual(result["task_id"], "note_1")
        runtime.resolve_workflow.assert_called_once()

    def test_run_intake_requires_route_for_live_execution(self):
        runtime_cli = load_runtime_cli()
        runtime = mock.Mock()
        runtime.resolve_workflow.return_value = SimpleNamespace(
            workflow=SimpleNamespace(name="dispatch"),
            task=SimpleNamespace(task_id="note_1", title="Fix auth bug"),
        )

        with self.assertRaisesRegex(ValueError, "payload.route"):
            runtime_cli.run_intake(
                {
                    "task_id": "note_1",
                    "source": "dispatch",
                    "trigger": "dispatch-propose",
                },
                live=True,
                runtime=runtime,
            )

    def test_run_intake_executes_live_runtime_begin(self):
        runtime_cli = load_runtime_cli()
        runtime = mock.Mock()
        runtime.resolve_workflow.return_value = SimpleNamespace(
            workflow=SimpleNamespace(name="dispatch"),
            task=SimpleNamespace(task_id="note_1", title="Fix auth bug"),
        )
        runtime.begin.return_value = SimpleNamespace(
            intake_activity_id="act_1",
            route_activity_id="act_2",
        )

        result = runtime_cli.run_intake(
            {
                "task_id": "note_1",
                "title": "Fix auth bug",
                "source": "dispatch",
                "trigger": "dispatch-propose",
                "route": {"decision": "proposed"},
                "intake_reason": "Task selected from ready queue",
            },
            live=True,
            runtime=runtime,
        )

        self.assertEqual(result["mode"], "executed")
        self.assertEqual(result["intake_activity_id"], "act_1")
        self.assertEqual(result["route_activity_id"], "act_2")
        runtime.begin.assert_called_once()

    def test_run_intake_batch_handles_payload_lists(self):
        runtime_cli = load_runtime_cli()
        runtime = mock.Mock()
        runtime.resolve_workflow.return_value = SimpleNamespace(
            workflow=SimpleNamespace(name="dispatch"),
            task=SimpleNamespace(task_id="note_1", title="Fix auth bug"),
        )

        results = runtime_cli.run_intake_batch(
            [
                {
                    "task_id": "note_1",
                    "title": "Fix auth bug",
                    "source": "dispatch",
                    "trigger": "dispatch-propose",
                },
                {
                    "task_id": "note_2",
                    "title": "Write blog draft",
                    "source": "dispatch",
                    "trigger": "dispatch-propose",
                },
            ],
            runtime=runtime,
        )

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["mode"], "resolved")
        self.assertEqual(results[1]["mode"], "resolved")
        self.assertEqual(runtime.resolve_workflow.call_count, 2)


if __name__ == '__main__':
    unittest.main()
