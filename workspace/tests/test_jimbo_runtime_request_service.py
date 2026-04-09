"""Tests for the Jimbo runtime request service helpers."""

import importlib.util
import os
import sys
import unittest
from unittest import mock


WORKSPACE_DIR = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, WORKSPACE_DIR)


def load_runtime_request_service():
    module_path = os.path.join(WORKSPACE_DIR, 'jimbo_runtime_request_service.py')
    spec = importlib.util.spec_from_file_location('jimbo_runtime_request_service_module', module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestJimboRuntimeRequestService(unittest.TestCase):

    def test_execute_runtime_request_delegates_to_executor(self):
        runtime_request_service = load_runtime_request_service()

        with mock.patch.object(runtime_request_service, 'run_runtime_request', return_value={'request_id': 'req-1', 'command': 'emit', 'result': []}) as run_runtime_request:
            response = runtime_request_service.execute_runtime_request({'request_id': 'req-1', 'command': 'emit', 'producer': 'dispatch-proposal'})

        run_runtime_request.assert_called_once_with({'request_id': 'req-1', 'command': 'emit', 'producer': 'dispatch-proposal'})
        self.assertEqual(response['request_id'], 'req-1')
        self.assertEqual(response['command'], 'emit')

    def test_stream_runtime_requests_can_continue_after_errors(self):
        runtime_request_service = load_runtime_request_service()
        requests = [
            {'request_id': 'req-1', 'command': 'emit', 'producer': 'dispatch-proposal'},
            {'request_id': 'req-2', 'command': 'bad'},
            {'request_id': 'req-3', 'command': 'summary', 'producer': 'vault-triage'},
        ]

        with mock.patch.object(runtime_request_service, 'execute_runtime_request', side_effect=[
            {'request_id': 'req-1', 'command': 'emit', 'result': []},
            ValueError('bad request'),
            {'request_id': 'req-3', 'command': 'summary', 'result': {'mode': 'summary'}},
        ]):
            responses = list(runtime_request_service.stream_runtime_requests(requests, continue_on_error=True))

        self.assertEqual(responses[0]['request_id'], 'req-1')
        self.assertEqual(responses[0]['command'], 'emit')
        self.assertFalse(responses[1]['ok'])
        self.assertEqual(responses[1]['request_id'], 'req-2')
        self.assertEqual(responses[1]['request']['command'], 'bad')
        self.assertEqual(responses[2]['request_id'], 'req-3')
        self.assertEqual(responses[2]['command'], 'summary')
