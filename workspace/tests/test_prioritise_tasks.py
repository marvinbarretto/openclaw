"""Tests for vault task prioritisation orchestration hooks."""

import importlib.util
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


class TestPrioritiseTaskRuntimeIntegration(unittest.TestCase):

    def test_logs_dispatch_candidate_via_runtime_selection(self):
        prioritise_tasks = load_prioritise_tasks()
        mock_core = mock.Mock()

        with mock.patch.object(
            prioritise_tasks.RUNTIME,
            'resolve_workflow',
            return_value=SimpleNamespace(core=mock_core),
        ) as resolve_workflow:
            prioritise_tasks.log_dispatch_candidate_classification(
                {
                    'id': 'note_1',
                    'title': 'Fix auth bug',
                },
                priority=1,
                actionability='clear',
                reason='Aligned with active repo work',
                suggested_agent_type='coder',
                suggested_route='jimbo',
                acceptance_criteria='Green tests and PR opened.',
                changed_fields={'ai_priority', 'suggested_agent_type'},
                model='gemini-test',
            )

        resolve_workflow.assert_called_once()
        envelope = resolve_workflow.call_args.args[0]
        self.assertEqual(envelope.source, 'vault')
        self.assertEqual(envelope.trigger, 'vault-task-triage')
        self.assertEqual(envelope.workflow_hint, 'vault-task-triage')
        self.assertEqual(envelope.model, 'gemini-test')
        mock_core.classify.assert_called_once()
        classify_kwargs = mock_core.classify.call_args.kwargs
        self.assertEqual(classify_kwargs['route']['decision'], 'jimbo')
        self.assertEqual(classify_kwargs['delegate']['agent_type'], 'coder')
        self.assertEqual(classify_kwargs['changed']['fields'],
                         ['ai_priority', 'suggested_agent_type'])


if __name__ == '__main__':
    unittest.main()
