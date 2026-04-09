"""Tests for submission and drain helpers around the runtime inbox."""

import importlib.util
import json
import os
import sys
import unittest
from unittest import mock


WORKSPACE_DIR = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, WORKSPACE_DIR)


def load_runtime_inbox_service():
    module_path = os.path.join(WORKSPACE_DIR, 'jimbo_runtime_inbox_service.py')
    spec = importlib.util.spec_from_file_location('jimbo_runtime_inbox_service_module', module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestJimboRuntimeInboxService(unittest.TestCase):

    def test_build_inbox_requests_from_payloads_wraps_live_resolve_requests(self):
        runtime_inbox_service = load_runtime_inbox_service()

        with mock.patch.object(runtime_inbox_service, '_now_stamp', return_value='20260409120000'):
            requests = runtime_inbox_service.build_inbox_requests_from_payloads(
                [{'task_id': 'note_1', 'source': 'vault', 'trigger': 'vault-task-triage'}],
                producer='vault-triage',
                live=True,
            )

        self.assertEqual(requests[0]['command'], 'resolve')
        self.assertTrue(requests[0]['live'])
        self.assertIn('vault-triage-note_1-20260409120000-1', requests[0]['request_id'])
        self.assertEqual(json.loads(requests[0]['intake_json'])['task_id'], 'note_1')

    def test_enqueue_producer_requests_submits_loaded_payloads(self):
        runtime_inbox_service = load_runtime_inbox_service()

        with mock.patch.object(runtime_inbox_service, 'load_producer_payloads', return_value=[{'task_id': 'note_1'}]) as load_producer_payloads, \
             mock.patch.object(runtime_inbox_service, 'enqueue_runtime_requests', return_value=[{'id': 'runtime-inbox-1'}]) as enqueue_runtime_requests, \
             mock.patch.object(runtime_inbox_service, 'build_inbox_requests_from_payloads', return_value=[{'request_id': 'req-1'}]) as build_requests:
            result = runtime_inbox_service.enqueue_producer_requests('vault-triage', live=True)

        load_producer_payloads.assert_called_once_with('vault-triage')
        build_requests.assert_called_once()
        enqueue_runtime_requests.assert_called_once()
        self.assertEqual(result['count'], 1)

    def test_process_next_inbox_item_claims_executes_and_completes(self):
        runtime_inbox_service = load_runtime_inbox_service()
        item = {'id': 'runtime-inbox-1', 'request_id': 'req-1', 'request': {'command': 'resolve'}}
        run = {'id': 'runtime-run-1'}

        with mock.patch.object(runtime_inbox_service, 'claim_next_inbox_item', return_value=item) as claim_next_inbox_item, \
             mock.patch.object(runtime_inbox_service, 'create_runtime_run', return_value=run) as create_runtime_run, \
             mock.patch.object(runtime_inbox_service, 'execute_runtime_request', return_value={'request_id': 'req-1', 'command': 'resolve'}) as execute_runtime_request, \
             mock.patch.object(runtime_inbox_service, 'complete_runtime_run') as complete_runtime_run, \
             mock.patch.object(runtime_inbox_service, 'complete_inbox_item') as complete_inbox_item:
            result = runtime_inbox_service.process_next_inbox_item(claimant='server-1')

        claim_next_inbox_item.assert_called_once_with(claimant='server-1')
        create_runtime_run.assert_called_once_with(item, claimant='server-1')
        execute_runtime_request.assert_called_once_with(item['request'])
        complete_runtime_run.assert_called_once()
        complete_inbox_item.assert_called_once()
        self.assertEqual(result['status'], 'completed')

    def test_drain_runtime_inbox_stops_when_idle(self):
        runtime_inbox_service = load_runtime_inbox_service()

        with mock.patch.object(runtime_inbox_service, 'process_next_inbox_item', side_effect=[
            {'status': 'completed', 'item_id': 'runtime-inbox-1'},
            {'status': 'failed', 'item_id': 'runtime-inbox-2'},
            {'status': 'idle'},
        ]) as process_next_inbox_item:
            result = runtime_inbox_service.drain_runtime_inbox(claimant='server-1')

        self.assertEqual(process_next_inbox_item.call_count, 3)
        self.assertEqual(result['processed'], 2)
        self.assertEqual(result['completed'], 1)
        self.assertEqual(result['failed'], 1)


if __name__ == '__main__':
    unittest.main()
