"""Tests for dispatch.py parsing and template logic."""
import json
import os
import sys
import unittest

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


if __name__ == '__main__':
    unittest.main()
