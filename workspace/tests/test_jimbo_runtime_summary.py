"""Tests for the Jimbo runtime summary command."""

import importlib.util
import os
import sys
import unittest
from unittest import mock


WORKSPACE_DIR = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, WORKSPACE_DIR)


def load_runtime_summary():
    module_path = os.path.join(WORKSPACE_DIR, 'jimbo_runtime_summary.py')
    spec = importlib.util.spec_from_file_location('jimbo_runtime_summary_module', module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestJimboRuntimeSummary(unittest.TestCase):

    def test_summarize_results_aggregates_counts(self):
        runtime_summary = load_runtime_summary()

        summary = runtime_summary.summarize_results([
            {
                "task_id": "note_1",
                "title": "Fix auth bug",
                "workflow": "dispatch",
                "source": "dispatch",
                "trigger": "dispatch-propose",
                "route_decision": "proposed",
            },
            {
                "task_id": "note_2",
                "title": "Write blog draft",
                "workflow": "dispatch",
                "source": "dispatch",
                "trigger": "dispatch-next",
                "route_decision": "commission",
            },
        ])

        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["workflows"]["dispatch"], 2)
        self.assertEqual(summary["sources"]["dispatch"], 2)
        self.assertEqual(summary["triggers"]["dispatch-propose"], 1)
        self.assertEqual(summary["route_decisions"]["commission"], 1)

    def test_run_summary_uses_runtime_cli_resolution(self):
        runtime_summary = load_runtime_summary()

        with mock.patch.object(runtime_summary, 'run_intake_batch', return_value=[
            {
                "task_id": "note_1",
                "title": "Fix auth bug",
                "workflow": "dispatch",
                "source": "dispatch",
                "trigger": "dispatch-propose",
                "route_decision": "proposed",
            }
        ]) as run_intake_batch:
            summary = runtime_summary.run_summary([{"task_id": "note_1"}], runtime=mock.Mock())

        run_intake_batch.assert_called_once()
        self.assertEqual(summary["mode"], "summary")
        self.assertEqual(summary["items"][0]["task_id"], "note_1")


if __name__ == '__main__':
    unittest.main()
