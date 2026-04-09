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

    def test_emit_command_prints_producer_output(self):
        runtime_tool = load_runtime_tool()

        with mock.patch.object(runtime_tool, 'emit_producer_output', return_value='[{"task_id":"note_1"}]\n') as emit_output, \
             mock.patch.object(runtime_tool.sys, 'stdout') as stdout:
            exit_code = runtime_tool.main(['emit', '--producer', 'dispatch-proposal'])

        self.assertEqual(exit_code, 0)
        emit_output.assert_called_once_with('dispatch-proposal')
        stdout.write.assert_called_once_with('[{"task_id":"note_1"}]\n')

    def test_request_command_can_delegate_to_emit(self):
        runtime_tool = load_runtime_tool()

        with mock.patch.object(runtime_tool, 'load_runtime_request', return_value={
            'request_id': 'req-1',
            'command': 'emit',
            'producer': 'dispatch-proposal',
        }) as load_runtime_request, \
             mock.patch.object(runtime_tool, 'execute_runtime_request', return_value={
                 'request_id': 'req-1',
                 'command': 'emit',
                 'result': [{'task_id': 'note_1'}],
             }) as execute_runtime_request, \
             mock.patch.object(runtime_tool.json, 'dump') as dump_mock:
            exit_code = runtime_tool.main(['request', '--request-file', '/tmp/request.json'])

        self.assertEqual(exit_code, 0)
        load_runtime_request.assert_called_once_with(request_json=None, request_file='/tmp/request.json')
        execute_runtime_request.assert_called_once_with({
            'request_id': 'req-1',
            'command': 'emit',
            'producer': 'dispatch-proposal',
        })
        dump_mock.assert_called_once()

    def test_request_command_can_delegate_to_summary(self):
        runtime_tool = load_runtime_tool()

        with mock.patch.object(runtime_tool, 'load_runtime_request', return_value={
            'request_id': 'req-2',
            'command': 'summary',
            'producer': 'vault-triage',
            'output_file': '/tmp/summary.json',
        }), \
             mock.patch.object(runtime_tool, 'execute_runtime_request', return_value={
                 'request_id': 'req-2',
                 'command': 'summary',
                 'result': {'mode': 'summary'},
             }) as execute_runtime_request, \
             mock.patch.object(runtime_tool.json, 'dump') as dump_mock:
            exit_code = runtime_tool.main(['request', '--request-json', '{"command":"summary"}'])

        self.assertEqual(exit_code, 0)
        execute_runtime_request.assert_called_once()
        dump_mock.assert_called_once()

    def test_resolve_command_can_load_payloads_from_producer(self):
        runtime_tool = load_runtime_tool()

        with mock.patch.object(runtime_tool, 'build_resolve_output', return_value=[{"mode": "resolved"}]) as build_resolve_output, \
             mock.patch.object(runtime_tool.json, 'dump') as dump_mock:
            exit_code = runtime_tool.main(['resolve', '--producer', 'dispatch-proposal'])

        self.assertEqual(exit_code, 0)
        build_resolve_output.assert_called_once()
        dump_mock.assert_called_once()

    def test_summary_command_can_load_payloads_from_producer(self):
        runtime_tool = load_runtime_tool()

        with mock.patch.object(runtime_tool, 'build_summary_output', return_value={"mode": "summary"}) as build_summary_output, \
             mock.patch.object(runtime_tool.json, 'dump') as dump_mock:
            exit_code = runtime_tool.main(['summary', '--producer', 'dispatch-proposal'])

        self.assertEqual(exit_code, 0)
        build_summary_output.assert_called_once()
        dump_mock.assert_called_once()

    def test_roundtrip_command_delegates_to_resolve_with_producer(self):
        runtime_tool = load_runtime_tool()

        with mock.patch.object(runtime_tool, 'cmd_resolve', return_value=0) as cmd_resolve:
            exit_code = runtime_tool.main(['roundtrip', '--producer', 'dispatch-proposal'])

        self.assertEqual(exit_code, 0)
        delegated_args = cmd_resolve.call_args.args[0]
        self.assertEqual(delegated_args.producer, 'dispatch-proposal')
        self.assertFalse(delegated_args.live)

    def test_roundtrip_command_can_delegate_to_summary_with_producer(self):
        runtime_tool = load_runtime_tool()

        with mock.patch.object(runtime_tool, 'cmd_summary', return_value=0) as cmd_summary:
            exit_code = runtime_tool.main(['roundtrip', '--producer', 'dispatch-proposal', '--summary'])

        self.assertEqual(exit_code, 0)
        delegated_args = cmd_summary.call_args.args[0]
        self.assertEqual(delegated_args.producer, 'dispatch-proposal')

    def test_report_command_reuses_summary_output_with_producer_label(self):
        runtime_tool = load_runtime_tool()

        with mock.patch.object(runtime_tool, 'build_report_output', return_value={'mode': 'summary', 'producer': 'dispatch-proposal'}) as build_report_output, \
             mock.patch.object(runtime_tool.json, 'dump') as dump_mock:
            exit_code = runtime_tool.main(['report', '--producer', 'dispatch-proposal'])

        self.assertEqual(exit_code, 0)
        build_report_output.assert_called_once()
        dump_mock.assert_called_once()

    def test_serve_command_streams_request_responses(self):
        runtime_tool = load_runtime_tool()

        with mock.patch.object(runtime_tool, 'iter_runtime_requests', return_value=[
            {'request_id': 'req-1', 'command': 'emit', 'producer': 'dispatch-proposal'},
            {'request_id': 'req-2', 'command': 'summary', 'producer': 'vault-triage'},
        ]) as iter_runtime_requests, \
             mock.patch.object(runtime_tool, 'stream_runtime_requests', return_value=[
                 {'request_id': 'req-1', 'command': 'emit', 'result': [{'task_id': 'note_1'}]},
                 {'request_id': 'req-2', 'command': 'summary', 'result': {'mode': 'summary'}},
             ]) as stream_runtime_requests, \
             mock.patch.object(runtime_tool.json, 'dump') as dump_mock:
            exit_code = runtime_tool.main(['serve', '--request-file', '-'])

        self.assertEqual(exit_code, 0)
        iter_runtime_requests.assert_called_once_with(request_file='-')
        stream_runtime_requests.assert_called_once()
        self.assertEqual(dump_mock.call_count, 2)


if __name__ == '__main__':
    unittest.main()
