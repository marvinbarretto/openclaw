"""Tests for the Jimbo runtime summary helpers."""

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from unittest import mock


WORKSPACE_DIR = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, WORKSPACE_DIR)


def load_runtime_summary():
    module_path = os.path.join(WORKSPACE_DIR, 'jimbo_runtime_summary_core.py')
    spec = importlib.util.spec_from_file_location('jimbo_runtime_summary_core_module', module_path)
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
        self.assertTrue(summary["generated_at"].endswith("Z"))

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

    def test_write_summary_artifact_persists_json_file(self):
        runtime_summary = load_runtime_summary()
        summary = {
            "mode": "summary",
            "generated_at": "2026-04-09T12:00:00Z",
            "total": 1,
            "workflows": {"dispatch": 1},
            "sources": {"dispatch": 1},
            "triggers": {"dispatch-propose": 1},
            "route_decisions": {"proposed": 1},
            "items": [{"task_id": "note_1"}],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "runtime-summary.json")
            runtime_summary.write_summary_artifact(summary, output_path)

            with open(output_path) as f:
                written = json.load(f)

        self.assertEqual(written["total"], 1)
        self.assertEqual(written["items"][0]["task_id"], "note_1")

    def test_log_summary_activity_records_orchestration_report(self):
        runtime_summary = load_runtime_summary()
        logger = mock.Mock(return_value="act_123")
        summary = {
            "mode": "summary",
            "generated_at": "2026-04-09T12:00:00Z",
            "total": 2,
            "workflows": {"dispatch": 2},
            "sources": {"dispatch": 2},
            "triggers": {"dispatch-propose": 1, "dispatch-next": 1},
            "route_decisions": {"proposed": 1, "commission": 1},
            "items": [{"task_id": "note_1"}, {"task_id": "note_2"}],
        }

        activity_id = runtime_summary.log_summary_activity(
            summary,
            summary_id="summary-1",
            logger=logger,
        )

        self.assertEqual(activity_id, "act_123")
        logger.assert_called_once()
        args, kwargs = logger.call_args
        self.assertEqual(args[0], "report")
        self.assertEqual(args[1], "summary-1")
        self.assertEqual(kwargs["task_source"], "runtime-summary")
        self.assertEqual(kwargs["report"]["status"], "summarized")
        self.assertEqual(kwargs["changed"]["total"], 2)
        self.assertEqual(kwargs["metadata"]["summary"]["generated_at"], "2026-04-09T12:00:00Z")


if __name__ == '__main__':
    unittest.main()
