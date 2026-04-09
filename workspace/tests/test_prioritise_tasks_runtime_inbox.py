"""Tests for vault triage submission into the Jimbo runtime inbox."""

import importlib.util
import io
import json
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock


WORKSPACE_DIR = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, WORKSPACE_DIR)


def load_prioritise_tasks():
    module_path = os.path.join(WORKSPACE_DIR, 'prioritise-tasks.py')
    spec = importlib.util.spec_from_file_location('prioritise_tasks_module', module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestPrioritiseTasksRuntimeInbox(unittest.TestCase):

    def test_cmd_score_api_can_submit_dispatchable_tasks_to_runtime_inbox(self):
        prioritise_tasks = load_prioritise_tasks()
        args = SimpleNamespace(
            dry_run=False,
            force=False,
            limit=None,
            emit_intake=False,
            submit_runtime_inbox=True,
        )
        task = {
            'id': 'note_1',
            'title': 'Fix auth bug',
            'updated_at': '2026-04-01',
            'tags': ['code'],
            'body': 'Investigate login failure',
        }
        gemini_result = [{
            'id': 'note_1',
            'priority': 1,
            'priority_reason': 'Urgent bug fix',
            'actionability': 'clear',
            'suggested_agent_type': 'coder',
            'suggested_route': 'jimbo',
            'suggested_ac': 'Bug reproduced and fixed.',
        }]
        runtime_payload = {
            'task_id': 'note_1',
            'source': 'vault',
            'trigger': 'vault-task-triage',
        }

        with mock.patch.object(prioritise_tasks, 'get_env', return_value='key'), \
             mock.patch.object(prioritise_tasks, 'load_context', return_value='context'), \
             mock.patch.object(prioritise_tasks, 'context_mtime', return_value='2026-03-01'), \
             mock.patch.object(prioritise_tasks, '_api_request', side_effect=[
                 {'notes': [task]},
                 {'status': 'ok'},
                 {'notes': []},
             ]) as api_request, \
             mock.patch.object(prioritise_tasks, 'call_gemini', return_value=gemini_result), \
             mock.patch.object(prioritise_tasks, 'build_vault_triage_payload', return_value=runtime_payload) as build_vault_triage_payload, \
             mock.patch.object(prioritise_tasks, 'log_dispatch_candidate_classification') as log_dispatch_candidate_classification, \
             mock.patch.object(prioritise_tasks, 'enqueue_payloads', return_value={'count': 1}) as enqueue_payloads, \
             mock.patch.object(prioritise_tasks, 'time') as time_module, \
             mock.patch('builtins.print') as print_mock:
            time_module.sleep = mock.Mock()
            prioritise_tasks.cmd_score_api(args)

        build_vault_triage_payload.assert_called_once()
        log_dispatch_candidate_classification.assert_called_once()
        enqueue_payloads.assert_called_once_with(
            [runtime_payload],
            producer='vault-triage',
            source='vault-triage',
            live=True,
        )
        output = json.loads(print_mock.call_args.args[0])
        self.assertEqual(output['submitted_to_runtime_inbox'], 1)
        self.assertGreaterEqual(api_request.call_count, 2)


if __name__ == '__main__':
    unittest.main()
