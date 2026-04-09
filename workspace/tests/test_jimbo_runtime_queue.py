"""Tests for the API-backed Jimbo runtime inbox and run ledger."""

import importlib.util
import os
import sys
import unittest
from unittest import mock


WORKSPACE_DIR = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, WORKSPACE_DIR)


def load_runtime_queue():
    module_path = os.path.join(WORKSPACE_DIR, 'jimbo_runtime_queue.py')
    spec = importlib.util.spec_from_file_location('jimbo_runtime_queue_module', module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestJimboRuntimeQueue(unittest.TestCase):

    def test_enqueue_runtime_requests_appends_pending_items(self):
        runtime_queue = load_runtime_queue()

        with mock.patch.object(runtime_queue, 'load_inbox_state', return_value={'items': [], 'updated_at': None}), \
             mock.patch.object(runtime_queue, 'save_inbox_state') as save_inbox_state, \
             mock.patch.object(runtime_queue, '_new_id', side_effect=['runtime-inbox-1', 'runtime-inbox-2']), \
             mock.patch.object(runtime_queue, '_now_iso', return_value='2026-04-09T12:00:00Z'):
            items = runtime_queue.enqueue_runtime_requests(
                [
                    {'request_id': 'req-1', 'command': 'resolve'},
                    {'request_id': 'req-2', 'command': 'resolve'},
                ],
                source='producer:vault-triage',
                producer='vault-triage',
            )

        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]['status'], 'pending')
        self.assertEqual(items[1]['producer'], 'vault-triage')
        save_inbox_state.assert_called_once()

    def test_claim_next_inbox_item_marks_first_pending(self):
        runtime_queue = load_runtime_queue()
        state = {
            'items': [
                {'id': 'runtime-inbox-1', 'status': 'completed'},
                {'id': 'runtime-inbox-2', 'status': 'pending', 'claimed_at': None, 'claimed_by': None},
            ],
            'updated_at': None,
        }

        with mock.patch.object(runtime_queue, 'load_inbox_state', return_value=state), \
             mock.patch.object(runtime_queue, 'save_inbox_state') as save_inbox_state, \
             mock.patch.object(runtime_queue, '_now_iso', return_value='2026-04-09T12:00:00Z'):
            item = runtime_queue.claim_next_inbox_item(claimant='server-1')

        self.assertEqual(item['id'], 'runtime-inbox-2')
        self.assertEqual(item['status'], 'claimed')
        self.assertEqual(item['claimed_by'], 'server-1')
        save_inbox_state.assert_called_once_with(state)

    def test_complete_runtime_run_updates_response(self):
        runtime_queue = load_runtime_queue()
        state = {
            'runs': [
                {'id': 'runtime-run-1', 'status': 'running', 'completed_at': None, 'response': None, 'error': None},
            ],
            'updated_at': None,
        }

        with mock.patch.object(runtime_queue, 'load_run_state', return_value=state), \
             mock.patch.object(runtime_queue, 'save_run_state') as save_run_state, \
             mock.patch.object(runtime_queue, '_now_iso', return_value='2026-04-09T12:00:00Z'):
            run = runtime_queue.complete_runtime_run('runtime-run-1', response={'command': 'resolve'})

        self.assertEqual(run['status'], 'completed')
        self.assertEqual(run['response']['command'], 'resolve')
        save_run_state.assert_called_once_with(state)

    def test_list_runtime_runs_filters_by_status(self):
        runtime_queue = load_runtime_queue()

        with mock.patch.object(runtime_queue, 'load_run_state', return_value={
            'runs': [
                {'id': 'runtime-run-1', 'status': 'running'},
                {'id': 'runtime-run-2', 'status': 'completed'},
            ],
            'updated_at': None,
        }):
            runs = runtime_queue.list_runtime_runs(status='completed')

        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]['id'], 'runtime-run-2')


if __name__ == '__main__':
    unittest.main()
