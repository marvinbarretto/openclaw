"""Tests for dispatch.py parsing and template logic."""
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestResultParsing(unittest.TestCase):
    """Test the result JSON parsing with fallback."""

    def test_valid_json(self):
        from dispatch import parse_result
        raw = '{"status": "completed", "summary": "Did the thing", "pr_url": "https://github.com/..."}'
        result = parse_result(raw)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['summary'], 'Did the thing')

    def test_json_with_markdown_fences(self):
        from dispatch import parse_result
        raw = '```json\n{"status": "completed", "summary": "Did it"}\n```'
        result = parse_result(raw)
        self.assertEqual(result['status'], 'completed')

    def test_malformed_json_falls_back(self):
        from dispatch import parse_result
        raw = 'I completed the task and opened PR #42. Everything works.'
        result = parse_result(raw)
        self.assertEqual(result['status'], 'completed_unstructured')
        self.assertIn('PR #42', result['summary'])

    def test_empty_result(self):
        from dispatch import parse_result
        result = parse_result('')
        self.assertEqual(result['status'], 'failed')
        self.assertIn('empty', result['summary'].lower())

    def test_blocked_status(self):
        from dispatch import parse_result
        raw = '{"status": "blocked", "summary": "tried", "blockers": "missing config"}'
        result = parse_result(raw)
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['blockers'], 'missing config')


class TestTemplateRendering(unittest.TestCase):
    """Test prompt template variable substitution."""

    def test_renders_variables(self):
        from dispatch import render_template
        template = "Task: {title}\nDoD: {definition_of_done}\nRepo: {dispatch_repo}"
        result = render_template(template, {
            'title': 'Add dark mode',
            'definition_of_done': 'Toggle works, persists in localStorage',
            'dispatch_repo': '~/development/localshout-next',
            'task_id': 'note_abc123',
        })
        self.assertIn('Add dark mode', result)
        self.assertIn('~/development/localshout-next', result)

    def test_missing_variable_preserved(self):
        from dispatch import render_template
        template = "Task: {title}\nOptional: {output_path}"
        result = render_template(template, {'title': 'Research flights', 'task_id': 'note_xyz'})
        self.assertIn('Research flights', result)
        self.assertIn('{output_path}', result)

    def test_double_braces_preserved(self):
        from dispatch import render_template
        template = "Write JSON: {{\n  \"status\": \"completed\"\n}}"
        result = render_template(template, {'title': 'test'})
        # Double braces in templates are literal JSON examples, not variables
        self.assertIn('{{', result)


class TestBatchIdParsing(unittest.TestCase):

    def test_valid_batch_id(self):
        from dispatch import is_valid_batch_id
        self.assertTrue(is_valid_batch_id('batch-20260325-143000'))
        self.assertFalse(is_valid_batch_id('not-a-batch'))
        self.assertFalse(is_valid_batch_id(''))


class TestTransitionPersistence(unittest.TestCase):

    def test_does_not_advance_transition_state_when_transition_logging_fails(self):
        import dispatch
        approved_item = {'id': 1, 'task_id': 'note_1', 'batch_id': 'batch-1'}
        with mock.patch.object(dispatch, 'load_transition_state', return_value={}), \
             mock.patch.object(dispatch, 'fetch_queue_items', side_effect=[[approved_item], [], [], [], []]), \
             mock.patch.object(dispatch, 'emit_transition', return_value=False), \
             mock.patch.object(dispatch, 'emit_batch_reports', return_value=True), \
             mock.patch.object(dispatch, 'save_transition_state') as save_state:
            dispatch.check_queue_transitions(dry_run=False)
        save_state.assert_not_called()

    def test_advances_transition_state_when_logging_succeeds(self):
        import dispatch
        approved_item = {'id': 1, 'task_id': 'note_1', 'batch_id': 'batch-1'}
        with mock.patch.object(dispatch, 'load_transition_state', return_value={}), \
             mock.patch.object(dispatch, 'fetch_queue_items', side_effect=[[approved_item], [], [], [], []]), \
             mock.patch.object(dispatch, 'emit_transition', return_value=True), \
             mock.patch.object(dispatch, 'emit_batch_reports', return_value=True), \
             mock.patch.object(dispatch, 'save_transition_state', return_value=True) as save_state:
            dispatch.check_queue_transitions(dry_run=False)
        save_state.assert_called_once()


class TestRuntimeIntegration(unittest.TestCase):

    def test_propose_batch_routes_items_through_jimbo_runtime(self):
        import dispatch

        proposed_item = {
            'id': 11,
            'task_id': 'note_1',
            'title': 'Fix auth bug',
            'agent_type': 'coder',
            'flow': 'commission',
        }

        with mock.patch.object(dispatch, 'api_request', side_effect=[
            {
                'items': [proposed_item],
                'batch_id': 'batch-20260325-143000',
                'approve_url': 'https://approve',
                'reject_url': 'https://reject',
            },
            None,
        ]), \
             mock.patch.object(dispatch, 'hydrate_batch', return_value=[proposed_item]), \
             mock.patch.object(dispatch, 'build_batch_summary', return_value='batch message'), \
             mock.patch.object(dispatch, 'build_batch', return_value={'items': {'11': proposed_item}}), \
             mock.patch.object(dispatch, 'emit_batch_report', return_value=True), \
             mock.patch.object(dispatch, 'send_telegram', return_value=True), \
             mock.patch.object(dispatch, 'begin_dispatch_proposal') as begin_dispatch_proposal:
            ok = dispatch.propose_batch(dry_run=False)

        self.assertTrue(ok)
        begin_dispatch_proposal.assert_called_once_with(
            proposed_item,
            batch_id='batch-20260325-143000',
            approve_url='https://approve',
            reject_url='https://reject',
        )


if __name__ == '__main__':
    unittest.main()
