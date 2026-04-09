"""Tests for the top-level Jimbo runtime CLI surface."""

import importlib.util
import json
import os
import sys
import unittest
from unittest import mock


WORKSPACE_DIR = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, WORKSPACE_DIR)


def load_runtime_tool():
    module_path = os.path.join(WORKSPACE_DIR, 'jimbo_runtime_tool.py')
    spec = importlib.util.spec_from_file_location('jimbo_runtime_tool_module', module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestJimboRuntimeTool(unittest.TestCase):

    def test_producers_command_lists_registered_producers(self):
        runtime_tool = load_runtime_tool()

        with mock.patch('builtins.print') as print_mock:
            exit_code = runtime_tool.main(['producers'])

        self.assertEqual(exit_code, 0)
        producers = json.loads(print_mock.call_args.args[0])
        self.assertIn('dispatch-proposal', producers)
        self.assertIn('dispatch-worker', producers)
        self.assertIn('vault-triage', producers)

    def test_report_command_delegates_to_report_wrapper(self):
        runtime_tool = load_runtime_tool()

        with mock.patch.object(runtime_tool, 'run_report', return_value={'mode': 'summary'}) as run_report, \
             mock.patch.object(runtime_tool.json, 'dump') as dump_mock:
            exit_code = runtime_tool.main(['report', '--producer', 'dispatch-proposal'])

        self.assertEqual(exit_code, 0)
        run_report.assert_called_once()
        dump_mock.assert_called_once()

    def test_emit_command_prints_producer_output(self):
        runtime_tool = load_runtime_tool()

        with mock.patch.object(runtime_tool, 'emit_producer_output', return_value='[{"task_id":"note_1"}]\n') as emit_output, \
             mock.patch.object(runtime_tool.sys, 'stdout') as stdout:
            exit_code = runtime_tool.main(['emit', '--producer', 'dispatch-proposal'])

        self.assertEqual(exit_code, 0)
        emit_output.assert_called_once_with('dispatch-proposal')
        stdout.write.assert_called_once_with('[{"task_id":"note_1"}]\n')

    def test_resolve_command_can_load_payloads_from_producer(self):
        runtime_tool = load_runtime_tool()

        with mock.patch.object(runtime_tool, 'load_producer_payloads', return_value=[{"task_id": "note_1"}]) as load_payloads, \
             mock.patch.object(runtime_tool, 'run_intake_batch', return_value=[{"mode": "resolved"}]) as run_intake_batch, \
             mock.patch.object(runtime_tool.json, 'dump') as dump_mock:
            exit_code = runtime_tool.main(['resolve', '--producer', 'dispatch-proposal'])

        self.assertEqual(exit_code, 0)
        load_payloads.assert_called_once_with('dispatch-proposal')
        run_intake_batch.assert_called_once_with([{"task_id": "note_1"}], live=False)
        dump_mock.assert_called_once()

    def test_summary_command_can_load_payloads_from_producer(self):
        runtime_tool = load_runtime_tool()

        with mock.patch.object(runtime_tool, 'load_producer_payloads', return_value=[{"task_id": "note_1"}]) as load_payloads, \
             mock.patch.object(runtime_tool, 'run_summary', return_value={"mode": "summary"}) as run_summary, \
             mock.patch.object(runtime_tool.json, 'dump') as dump_mock:
            exit_code = runtime_tool.main(['summary', '--producer', 'dispatch-proposal'])

        self.assertEqual(exit_code, 0)
        load_payloads.assert_called_once_with('dispatch-proposal')
        run_summary.assert_called_once_with([{"task_id": "note_1"}])
        dump_mock.assert_called_once()


if __name__ == '__main__':
    unittest.main()
