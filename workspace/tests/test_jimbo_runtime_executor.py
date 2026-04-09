"""Tests for the shared Jimbo runtime request executor."""

import importlib.util
import os
import sys
import unittest
from unittest import mock


WORKSPACE_DIR = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, WORKSPACE_DIR)


def load_runtime_executor():
    module_path = os.path.join(WORKSPACE_DIR, 'jimbo_runtime_executor.py')
    spec = importlib.util.spec_from_file_location('jimbo_runtime_executor_module', module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestJimboRuntimeExecutor(unittest.TestCase):

    def test_build_request_namespace_normalizes_request(self):
        runtime_executor = load_runtime_executor()

        args, command = runtime_executor.build_request_namespace({
            'request_id': 'req-1',
            'command': 'resolve',
            'producer': 'dispatch-proposal',
            'live': True,
        })

        self.assertEqual(command, 'resolve')
        self.assertEqual(args.request_id, 'req-1')
        self.assertEqual(args.producer, 'dispatch-proposal')
        self.assertTrue(args.live)

    def test_build_emit_output_loads_producer_payloads(self):
        runtime_executor = load_runtime_executor()

        with mock.patch.object(runtime_executor, 'load_producer_payloads', return_value=[{'task_id': 'note_1'}]) as load_producer_payloads:
            result = runtime_executor.build_emit_output(type('Args', (), {'producer': 'dispatch-proposal'})())

        load_producer_payloads.assert_called_once_with('dispatch-proposal')
        self.assertEqual(result[0]['task_id'], 'note_1')

    def test_build_resolve_output_can_use_explicit_intake(self):
        runtime_executor = load_runtime_executor()

        args = type('Args', (), {
            'producer': None,
            'intake_json': '{"task_id":"note_1","source":"dispatch","trigger":"dispatch-propose"}',
            'intake_file': None,
            'live': False,
        })()

        with mock.patch.object(runtime_executor, 'run_intake_batch', return_value=[{'mode': 'resolved'}]) as run_intake_batch:
            result = runtime_executor.build_resolve_output(args)

        run_intake_batch.assert_called_once()
        self.assertEqual(result[0]['mode'], 'resolved')

    def test_build_summary_output_can_include_producer(self):
        runtime_executor = load_runtime_executor()

        args = type('Args', (), {
            'producer': 'dispatch-proposal',
            'intake_json': None,
            'intake_file': None,
            'output_file': None,
            'log_activity': False,
            'summary_id': None,
        })()

        with mock.patch.object(runtime_executor, 'load_producer_payloads', return_value=[{'task_id': 'note_1'}]), \
             mock.patch.object(runtime_executor, 'run_summary', return_value={'mode': 'summary'}) as run_summary:
            result = runtime_executor.build_summary_output(args, include_producer=True)

        run_summary.assert_called_once_with([{'task_id': 'note_1'}])
        self.assertEqual(result['producer'], 'dispatch-proposal')

    def test_run_runtime_request_returns_structured_response(self):
        runtime_executor = load_runtime_executor()

        with mock.patch.object(runtime_executor, 'build_emit_output', return_value=[{'task_id': 'note_1'}]) as build_emit_output:
            result = runtime_executor.run_runtime_request({
                'request_id': 'req-emit-1',
                'command': 'emit',
                'producer': 'dispatch-proposal',
            })

        build_emit_output.assert_called_once()
        self.assertEqual(result['request_id'], 'req-emit-1')
        self.assertEqual(result['command'], 'emit')
        self.assertEqual(result['result'][0]['task_id'], 'note_1')
