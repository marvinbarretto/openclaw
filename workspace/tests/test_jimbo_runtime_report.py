"""Tests for the Jimbo runtime report wrapper."""

import importlib.util
import os
import sys
import unittest
from unittest import mock


WORKSPACE_DIR = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, WORKSPACE_DIR)


def load_runtime_report():
    module_path = os.path.join(WORKSPACE_DIR, 'jimbo_runtime_report.py')
    spec = importlib.util.spec_from_file_location('jimbo_runtime_report_module', module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestJimboRuntimeReport(unittest.TestCase):

    def test_load_producer_payloads_runs_emit_command(self):
        runtime_report = load_runtime_report()

        with mock.patch.object(runtime_report, 'get_producer_command', return_value=['python', 'dispatch.py', '--emit-intake']) as get_producer_command, \
             mock.patch.object(runtime_report, 'run_subprocess', return_value='[{"task_id":"note_1"}]') as run_subprocess:
            payloads = runtime_report.load_producer_payloads('dispatch-proposal')

        self.assertEqual(payloads, [{"task_id": "note_1"}])
        get_producer_command.assert_called_once_with('dispatch-proposal')
        run_subprocess.assert_called_once()
        self.assertIn('dispatch.py', run_subprocess.call_args.args[0][1])

    def test_run_report_can_write_artifact_and_log_activity(self):
        runtime_report = load_runtime_report()
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

        with mock.patch.object(runtime_report, 'load_producer_payloads', return_value=[{"task_id": "note_1"}]) as load_payloads, \
             mock.patch.object(runtime_report, 'run_summary', return_value=dict(summary)) as run_summary, \
             mock.patch.object(runtime_report, 'write_summary_artifact') as write_summary_artifact, \
             mock.patch.object(runtime_report, 'log_summary_activity', return_value='act_123') as log_summary_activity:
            result = runtime_report.run_report(
                'dispatch-proposal',
                output_file='/tmp/runtime-summary.json',
                log_activity=True,
                summary_id='runtime-summary-test',
            )

        load_payloads.assert_called_once_with('dispatch-proposal')
        run_summary.assert_called_once()
        write_summary_artifact.assert_called_once_with(result, '/tmp/runtime-summary.json')
        log_summary_activity.assert_called_once_with(
            result,
            summary_id='runtime-summary-test',
            logger=None,
        )
        self.assertEqual(result['producer'], 'dispatch-proposal')
        self.assertEqual(result['activity_id'], 'act_123')


if __name__ == '__main__':
    unittest.main()
