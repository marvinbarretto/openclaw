"""Tests for dispatch worker API write semantics."""

import importlib.util
import os
import sys
import unittest
from unittest import mock


WORKSPACE_DIR = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, WORKSPACE_DIR)


def load_dispatch_worker():
    module_path = os.path.join(WORKSPACE_DIR, 'dispatch-worker.py')
    spec = importlib.util.spec_from_file_location('dispatch_worker_module', module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestDispatchWorkerApiWrites(unittest.TestCase):

    def test_api_write_retries_until_success(self):
        worker = load_dispatch_worker()
        with mock.patch.object(worker, 'api_request', side_effect=[None, {'ok': True}]) as api_mock:
            ok = worker.api_write(
                'POST',
                '/api/dispatch/complete',
                {'id': 1},
                action='mark task complete',
                retries=1,
                retry_delay_s=0,
            )
        self.assertTrue(ok)
        self.assertEqual(api_mock.call_count, 2)

    def test_execute_task_preserves_artifacts_when_complete_write_fails(self):
        worker = load_dispatch_worker()
        task = {'id': 11, 'task_id': 'note_1', 'agent_type': 'coder'}
        normalized_task = {
            'task_id': 'note_1',
            'title': 'Fix auth bug',
            'definition_of_done': 'Green tests',
            'task_source': 'vault',
            'flow': 'commission',
            'dispatch_repo': '/tmp',
        }
        completed_result = {
            'status': 'completed',
            'summary': 'Done',
            'pr_url': 'https://github.com/o/r/pull/1',
            'branch': 'dispatch/note_1',
            'files_changed': ['src/app.ts'],
        }
        proc = mock.Mock(stdout='ignored', stderr='', returncode=0)

        with mock.patch.object(worker, 'load_template', return_value='Task: {title}'), \
             mock.patch.object(worker, 'hydrate_task', return_value=normalized_task), \
             mock.patch.object(worker, 'report_dispatch_start', return_value=True), \
             mock.patch.object(worker, 'validate_result', return_value={
                 'accepted': True,
                 'review_status': 'completed',
                 'reason': 'ok',
             }), \
             mock.patch.object(worker, 'report_dispatch_complete', return_value=False), \
             mock.patch.object(worker, 'preserve_evidence') as preserve_mock, \
             mock.patch.object(worker, 'cleanup') as cleanup_mock, \
             mock.patch.object(worker, 'send_telegram'), \
             mock.patch.object(worker.JimboCore, 'intake', return_value='act_1'), \
             mock.patch.object(worker.JimboCore, 'delegate', return_value='act_2'), \
             mock.patch.object(worker.JimboCore, 'review', return_value='act_3'), \
             mock.patch.object(worker.JimboCore, 'report', return_value='act_4'), \
             mock.patch.object(worker.subprocess, 'run', return_value=proc), \
             mock.patch.object(worker, 'parse_result', return_value=completed_result), \
             mock.patch.object(worker.os.path, 'exists', return_value=False):
            ok = worker.execute_task(task, dry_run=False)

        self.assertFalse(ok)
        preserve_mock.assert_called_once()
        cleanup_mock.assert_not_called()


if __name__ == '__main__':
    unittest.main()
